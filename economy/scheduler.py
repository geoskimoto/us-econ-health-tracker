"""
economy/scheduler.py — APScheduler jobs registered in EconomyConfig.ready().
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django_apscheduler.jobstores import DjangoJobStore

logger = logging.getLogger(__name__)

_scheduler = None


def _run_fetch():
    from economy.fetcher import fetch_all_series
    from economy.models import FetchLog
    from django.utils import timezone
    log = FetchLog.objects.create(started_at=timezone.now(), status="failed")
    try:
        result = fetch_all_series()
        log.status = "partial" if result.failed > 0 else "success"
        log.series_fetched = result.fetched
        log.series_failed = result.failed
        log.points_written = result.points_written
        log.error_detail = "\n".join(result.errors) if result.errors else ""
    except Exception as exc:
        log.error_detail = str(exc)
        logger.error("Scheduled fetch failed: %s", exc)
    finally:
        log.finished_at = timezone.now()
        log.save()


def _run_analysis():
    from economy.analysis import generate_analysis
    generate_analysis(model="claude-haiku-4-5-20251001")


def start_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        return

    _scheduler = BackgroundScheduler(timezone="America/New_York")
    _scheduler.add_jobstore(DjangoJobStore(), "default")

    # Fetch data at 6:30 AM ET on weekdays
    _scheduler.add_job(
        _run_fetch,
        trigger=CronTrigger(day_of_week="mon-fri", hour=6, minute=30),
        id="fetch_data",
        replace_existing=True,
        max_instances=1,
    )

    # Run analysis at 7:00 AM ET on weekdays (after fetch)
    _scheduler.add_job(
        _run_analysis,
        trigger=CronTrigger(day_of_week="mon-fri", hour=7, minute=0),
        id="run_analysis",
        replace_existing=True,
        max_instances=1,
    )

    _scheduler.start()
    logger.info("APScheduler started — fetch at 6:30 AM ET, analysis at 7:00 AM ET (weekdays).")
