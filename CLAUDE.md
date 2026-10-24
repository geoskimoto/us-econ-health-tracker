# Economy Tracker — Project Context

A Django + Plotly Dash macroeconomic dashboard that tracks ~40 economic indicators, computes a composite health score and recession probability, and generates daily AI narratives using Claude.

---

## Authentication — SSO, not this app's concern

Since 2026-10-24 this app has **no authentication of its own**. It is gated by the
`restore-trust.com` SSO portal at `apps.restore-trust.com`.

- Served at **`econ-tracker.restore-trust.com`**. The old `econ-tracker.3rdplaces.io`
  path-preserving-301s to it; don't use it for anything new.
- `config/settings.py` carries `apps_auth.django.JWTRemoteUserMiddleware` (after
  `AuthenticationMiddleware`, before `django_plotly_dash`'s `BaseMiddleware`) and
  `AUTHENTICATION_BACKENDS = ["apps_auth.django.JWTRemoteUserBackend"]`. The JWT cookie
  is validated locally with no network call, so the dashboard survives portal downtime.
- **`AUTH_REQUIRED_GROUP=econ` is the single source of truth** for who gets in. Never
  hardcode a group. `config/groups.yaml` in the portal repo is authoritative for the
  value. The middleware raises `ImproperlyConfigured` if it is unset, so a misconfigured
  deploy fails rather than admitting everyone.
- **`AUTHENTICATION_BACKENDS` no longer includes `ModelBackend`**, so password login is
  gone — including Django admin at `/admin/`. Intended: the portal is the only way in.
  Don't quietly re-add `ModelBackend`.
- **No exempt prefixes are configured, deliberately.** Every Dash URL sits under
  `/django_plotly_dash/app/EconDashboard/`, so the library's defaults
  (`/_dash-component-suites/`, `/assets/`) match nothing here and the **callback
  endpoint is gated by default** rather than by getting a prefix exactly right.
  `dashboard/tests.py` pins this, including a test that fails if an exempt prefix is ever
  added that covers the Dash mount. Before changing it, know that
  `_dash-update-component` executes server-side callbacks.
- `whitenoise` serves `/static/` from inside Django because nginx no longer aliases it
  off disk (that alias outranked `location /` and became a gating bypass). It sits
  *before* the SSO middleware, so assets are served unauthenticated — deliberate, and
  the same posture as the sibling apps.
- `SECURE_PROXY_SSL_HEADER` is set because nginx terminates TLS and proxies plain HTTP.
  Without it `request.build_absolute_uri()` returns `http://` and the login redirect's
  `next=` is plaintext.

### Deployment — gated in place

This app has **no site user and no separate htdocs tree**: it runs as `geoskimoto`
straight out of `/home/geoskimoto/projects/`, so the **development tree is the deployed
tree**. There is no `git pull` deploy step — the deploy step is
`sudo systemctl restart econ-dashboard`. An uncommitted edit here is **live** on the next
restart, and the unit is `Restart=on-failure`, so a crash reloads whatever is in the tree.
"Committed but not deployed" is not a safe pause.

---

## Cross-App Data Dependency

The **fundamental-analysis-alert-system** (`/home/geoskimoto/projects/fundamental-analysis-alert-system`) reads this app's SQLite database **read-only** to fetch macro context for its AI narrative generation.

- **DB path:** `/home/geoskimoto/projects/economy_tracker/db.sqlite3`
- **Table read:** `economy_dailyanalysis` — latest row only
- **Fields consumed:** `composite_health_score`, `recession_probability`, `snapshot_json`, `date`

Do not rename or restructure these fields without updating `analysis/market_context.py` in the fundamental-analysis-alert-system. If this app ever moves to a separate server, a `/api/latest/` JSON endpoint should be added here and the FAAS app updated to call it over HTTP.
