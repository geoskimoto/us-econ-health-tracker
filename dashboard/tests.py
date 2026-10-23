"""The SSO gate on econ-tracker.

This app had no authentication of its own, so these tests are the first
specification of who may reach it: a holder of a valid apps_auth cookie
carrying the required group, and nobody else. Validation is local to the
process, so the dashboard keeps working while the portal is down.

The gated path is "/" (dashboard.urls maps "" directly to the index view --
unlike the companion app, there is no separate "/dashboard/" path and no
intermediate redirect from "/" to it, so no "root redirect is also gated"
test is carried over: it would be a duplicate of the anonymous-redirect test
below under this app's URL layout).
"""
import dataclasses

from apps_auth.config import load_config
from apps_auth.tokens import issue_token
from django.contrib.auth import get_user_model
from django.test import TestCase

REQUIRED_GROUP = "econ"
PORTAL = "https://apps.restore-trust.com"


def cookie_for(groups, username="nick", cfg=None):
    """A signed apps_auth cookie value carrying the given groups."""
    cfg = cfg or load_config()
    return issue_token(username, groups, config=cfg)


class GateTests(TestCase):
    def test_anonymous_request_redirects_to_the_portal_login(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp["Location"].startswith(f"{PORTAL}/login"))

    def test_redirect_preserves_the_requested_url(self):
        resp = self.client.get("/")
        self.assertIn("next=", resp["Location"])
        # The gated path is "/" itself, so the thing to pin is that the
        # *actual* requesting host made it into next=, not a generic target.
        self.assertIn("testserver", resp["Location"])

    def test_a_member_of_the_required_group_is_admitted(self):
        self.client.cookies["apps_auth"] = cookie_for([REQUIRED_GROUP])
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_the_admin_group_bypasses_the_group_check(self):
        self.client.cookies["apps_auth"] = cookie_for(["admin"])
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_a_valid_token_for_the_wrong_group_is_refused(self):
        self.client.cookies["apps_auth"] = cookie_for(["tools"])
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"].rstrip("/"), PORTAL)

    def test_a_garbage_cookie_does_not_pass(self):
        self.client.cookies["apps_auth"] = "not-a-real-token"
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_a_token_signed_with_the_wrong_secret_does_not_pass(self):
        forged = dataclasses.replace(load_config(), jwt_secret="x" * 64)
        self.client.cookies["apps_auth"] = cookie_for([REQUIRED_GROUP], cfg=forged)
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_an_expired_token_does_not_pass(self):
        expired = dataclasses.replace(load_config(), token_ttl_hours=-1)
        self.client.cookies["apps_auth"] = cookie_for([REQUIRED_GROUP], cfg=expired)
        self.assertEqual(self.client.get("/").status_code, 302)


class UserProvisioningTests(TestCase):
    """JWTRemoteUserBackend creates a local row so request.user works and any
    future ForeignKey(User) keeps working. The password must be unusable, or
    the portal stops being the only way in."""

    def test_a_local_user_row_is_created_on_first_request(self):
        User = get_user_model()
        self.assertEqual(User.objects.filter(username="nick").count(), 0)
        self.client.cookies["apps_auth"] = cookie_for([REQUIRED_GROUP], username="nick")
        self.client.get("/")
        self.assertEqual(User.objects.filter(username="nick").count(), 1)

    def test_the_created_user_has_an_unusable_password(self):
        User = get_user_model()
        self.client.cookies["apps_auth"] = cookie_for([REQUIRED_GROUP], username="nick")
        self.client.get("/")
        self.assertFalse(User.objects.get(username="nick").has_usable_password())

    def test_a_second_request_reuses_the_row_rather_than_duplicating(self):
        User = get_user_model()
        self.client.cookies["apps_auth"] = cookie_for([REQUIRED_GROUP], username="nick")
        self.client.get("/")
        self.client.get("/")
        self.assertEqual(User.objects.filter(username="nick").count(), 1)

    def test_request_user_is_the_sso_username(self):
        self.client.cookies["apps_auth"] = cookie_for([REQUIRED_GROUP], username="nick")
        resp = self.client.get("/")
        self.assertEqual(resp.wsgi_request.user.username, "nick")
        self.assertTrue(resp.wsgi_request.user.is_authenticated)


class ClientSuppliedHeaderTests(TestCase):
    """The adapter sets header = "APPS_AUTH_REMOTE_USER" rather than the
    default "REMOTE_USER" precisely so Django's get_username() cannot read a
    client-supplied header. This is the security reason for that choice and it
    has never been exercised in production — pin it."""

    def test_a_client_supplied_remote_user_header_is_ignored(self):
        resp = self.client.get("/", REMOTE_USER="attacker")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(get_user_model().objects.filter(username="attacker").count(), 0)

    def test_a_client_supplied_apps_auth_remote_user_header_is_ignored(self):
        resp = self.client.get("/", HTTP_APPS_AUTH_REMOTE_USER="attacker")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(get_user_model().objects.filter(username="attacker").count(), 0)


class ConfigurationTests(TestCase):
    def test_health_is_exempt_so_monitoring_keeps_working(self):
        resp = self.client.get("/health")
        self.assertIn(resp.status_code, (200, 404))
        self.assertNotEqual(resp.status_code, 302)


class DashGatingTests(TestCase):
    """django_plotly_dash mounts everything under /django_plotly_dash/, so the
    library's DEFAULT_EXEMPT_PREFIXES ("/_dash-component-suites/", "/assets/")
    match nothing here and no exemption is configured. That makes the callback
    endpoint gated by default rather than by careful prefix choice -- pin it,
    because a future exemption added casually would reopen it.
    """

    DASH_BASE = "/django_plotly_dash/app/EconDashboard"

    def test_the_dash_layout_endpoint_is_gated(self):
        resp = self.client.get(f"{self.DASH_BASE}/_dash-layout")
        self.assertEqual(resp.status_code, 302)

    def test_the_dash_callback_endpoint_is_gated(self):
        """_dash-update-component executes server-side callbacks. Exempting it
        would hand an anonymous caller the app's compute."""
        resp = self.client.post(f"{self.DASH_BASE}/_dash-update-component")
        self.assertEqual(resp.status_code, 302)

    def test_the_dash_dependencies_endpoint_is_gated(self):
        resp = self.client.get(f"{self.DASH_BASE}/_dash-dependencies")
        self.assertEqual(resp.status_code, 302)

    def test_a_member_reaches_the_dash_app(self):
        self.client.cookies["apps_auth"] = cookie_for([REQUIRED_GROUP])
        resp = self.client.get(f"{self.DASH_BASE}/_dash-layout")
        self.assertIn(resp.status_code, (200, 404))
        self.assertNotEqual(resp.status_code, 302)

    def test_no_exempt_prefix_covers_the_dash_mount(self):
        """Guards the decision directly: if someone later sets
        AUTH_EXEMPT_PREFIXES to something matching the Dash mount, this fails."""
        from apps_auth.config import load_config
        for prefix in load_config().exempt_prefixes:
            self.assertFalse(
                self.DASH_BASE.startswith(prefix),
                f"exempt prefix {prefix!r} covers the Dash mount",
            )
