"""
Management command: fetch_data
Pull all active series from FRED and yfinance into the database.
Usage: python manage.py fetch_data
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from economy.fetcher import fetch_all_series
from economy.models import FetchLog


class Command(BaseCommand):
    help = "Fetch all active economic series from FRED and yfinance."

    def handle(self, *args, **options):
        self.stdout.write("Starting data fetch...")
        log = FetchLog.objects.create(started_at=timezone.now(), status="failed")
        try:
            result = fetch_all_series()
            status = "partial" if result.failed > 0 else "success"
            log.status = status
            log.series_fetched = result.fetched
            log.series_failed = result.failed
            log.points_written = result.points_written
            if result.errors:
                log.error_detail = "\n".join(result.errors)
            log.finished_at = timezone.now()
            log.save()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Fetch complete: {result.fetched} series fetched, "
                    f"{result.failed} failed, {result.points_written} new points."
                )
            )
            if result.errors:
                for err in result.errors:
                    self.stdout.write(self.style.WARNING(f"  {err}"))
        except Exception as exc:
            log.error_detail = str(exc)
            log.finished_at = timezone.now()
            log.save()
            self.stdout.write(self.style.ERROR(f"Fetch failed: {exc}"))
            raise
