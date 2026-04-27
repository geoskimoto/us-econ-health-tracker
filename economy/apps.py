import logging
from django.apps import AppConfig

logger = logging.getLogger(__name__)


class EconomyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "economy"

    def ready(self):
        import sys
        # Skip scheduler during management commands that don't need it
        if any(cmd in sys.argv for cmd in ("makemigrations", "migrate", "test", "shell", "seed_series", "fetch_data", "run_analysis", "collectstatic")):
            return
        try:
            from economy.scheduler import start_scheduler
            start_scheduler()
        except Exception as exc:
            logger.warning("Scheduler failed to start: %s", exc)
