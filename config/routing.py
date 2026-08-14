import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django_plotly_dash.routing import application  # noqa: E402
