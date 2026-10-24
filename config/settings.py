from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

# ─── Security ─────────────────────────────────────────────────────────────────

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

DEBUG = os.environ.get("DJANGO_DEBUG", "False") == "True"

ALLOWED_HOSTS = os.environ.get(
    "DJANGO_ALLOWED_HOSTS",
    "econ-tracker.3rdplaces.io,econ-tracker.restore-trust.com,localhost,127.0.0.1",
).split(",")

# ─── Applications ─────────────────────────────────────────────────────────────

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    # Third-party
    "daphne",
    "django.contrib.staticfiles",
    "channels",
    "django_plotly_dash.apps.DjangoPlotlyDashConfig",
    "dpd_static_support",
    "django_apscheduler",
    # Local
    "economy.apps.EconomyConfig",
    "dashboard.apps.DashboardConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Serves /static/ from within the app. nginx no longer aliases it off
    # disk: `location ^~ /static/` outranks `location /`, so nginx was
    # serving those files without the request reaching Django, which became a
    # gating bypass once JWTRemoteUserMiddleware was added. It matters more
    # here than elsewhere because this app's staticfiles/ carries the Dash
    # component bundles (dpd_static_support / PLOTLY_COMPONENTS), so losing
    # them leaves the dashboard rendering but non-interactive.
    #
    # Note this sits BEFORE JWTRemoteUserMiddleware, so static assets are
    # served without authentication. Deliberate: they are CSS and JS with no
    # user data, every gated app here already serves them to anonymous
    # clients, and placing whitenoise after the gate would put a token decode
    # and a database lookup on every asset request. The exposure this
    # migration closes is anonymous access to the dashboard, its layout and
    # its callback endpoint -- not to stylesheets.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Gates every request on the portal's apps_auth cookie. MUST come after
    # AuthenticationMiddleware: it subclasses RemoteUserMiddleware, which
    # needs request.user to already exist. AUTH_REQUIRED_GROUP is the single
    # source of truth for the required group and the middleware raises
    # ImproperlyConfigured if it is unset, so a misconfigured deploy fails
    # rather than admitting everyone.
    #
    # Placed BEFORE BaseMiddleware (django_plotly_dash) so a Dash request is
    # already authenticated -- request.user set, redirect-to-login already
    # issued for an anonymous caller -- before Dash's own middleware runs.
    # Confirmed by testing: dashboard/tests.py's DashGatingTests pass in this
    # position (20/20); the alternative (after BaseMiddleware) was not tried
    # since this one worked and there is no other reason to prefer it --
    # BaseMiddleware does its own dispatch-table bookkeeping per request and
    # has no auth-adjacent behavior that this ordering could interact with.
    "apps_auth.django.JWTRemoteUserMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_plotly_dash.middleware.BaseMiddleware",
]

# Replaces the default ModelBackend. This disables password login, including
# Django admin at /admin/ -- intended: the restore-trust.com portal becomes
# the only way in. JWTRemoteUserBackend creates a local User row (unusable
# password) for an SSO-authenticated username so request.user and any future
# ForeignKey(User) keep working.
AUTHENTICATION_BACKENDS = [
    "apps_auth.django.JWTRemoteUserBackend",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.routing.application"

# ─── Database ─────────────────────────────────────────────────────────────────

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ─── Password Validation ──────────────────────────────────────────────────────

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ─── Internationalisation ─────────────────────────────────────────────────────

LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/New_York"
USE_I18N = True
USE_TZ = True

# ─── Static files ─────────────────────────────────────────────────────────────

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
    "django_plotly_dash.finders.DashComponentFinder",
    "django_plotly_dash.finders.DashAppDirectoryFinder",
    "django_plotly_dash.finders.DashAssetFinder",
]

# ─── FRED & Anthropic ─────────────────────────────────────────────────────────

FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ─── Diskcache (raw API response cache, 24-hour TTL) ──────────────────────────

CACHE_DIR = BASE_DIR / "cache"

# ─── APScheduler ──────────────────────────────────────────────────────────────

APSCHEDULER_DATETIME_FORMAT = "N j, Y, f:s a"
APSCHEDULER_RUN_NOW_TIMEOUT = 25

# ─── Django Channels ──────────────────────────────────────────────────────────

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}

# ─── django-plotly-dash ───────────────────────────────────────────────────────

X_FRAME_OPTIONS = "SAMEORIGIN"

# Extra Dash component libraries to collect into staticfiles. The finder's
# built-ins only cover the dash and plotly packages themselves.
PLOTLY_COMPONENTS = [
    "dash_bootstrap_components",
    "dpd_components",
    "dpd_static_support",
]

PLOTLY_DASH = {
    # Serve Dash component JS from local staticfiles. CDN mode (serve_locally
    # False) is broken with Dash 2.x: the npm packages on unpkg don't bundle
    # plotly.js and pin dash-renderer 1.x, so dcc.Graph never renders.
    "serve_locally": True,
}
