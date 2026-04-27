"""
dashboard/data.py — lean DB query layer for dashboard callbacks.
All functions return plain Python types so callbacks stay thin.
"""
import logging
from datetime import date

import pandas as pd

logger = logging.getLogger(__name__)


def get_latest_analysis() -> dict | None:
    from economy.models import DailyAnalysis
    obj = DailyAnalysis.objects.order_by("-date").first()
    if not obj:
        return None
    return {
        "date": obj.date,
        "analysis": obj.analysis,
        "analysis_model": obj.analysis_model,
        "generated_at": obj.generated_at,
        "recession_probability": obj.recession_probability,
        "composite_health_score": obj.composite_health_score,
        "snapshot": obj.snapshot_json,
    }


def get_analysis_history(days: int = 90) -> list[dict]:
    from economy.models import DailyAnalysis
    from datetime import timedelta
    cutoff = date.today() - timedelta(days=days)
    qs = DailyAnalysis.objects.filter(date__gte=cutoff).order_by("date")
    return [
        {
            "date": o.date,
            "composite_health_score": o.composite_health_score,
            "recession_probability": o.recession_probability,
        }
        for o in qs
    ]


def get_last_fetch() -> dict | None:
    from economy.models import FetchLog
    log = FetchLog.objects.filter(status__in=["success", "partial"]).order_by("-started_at").first()
    if not log:
        return None
    return {
        "started_at": log.started_at,
        "status": log.status,
        "series_fetched": log.series_fetched,
        "points_written": log.points_written,
    }


def get_series_for_chart(series_id: str, days: int = 3650) -> pd.Series:
    from economy.indicators import get_series_df
    return get_series_df(series_id, days=days)


def get_yield_curve_snapshot() -> dict:
    from economy.indicators import compute_yield_spreads
    return compute_yield_spreads()


def get_composite_and_recession() -> tuple[float, float]:
    from economy.indicators import compute_composite_score, compute_recession_probability
    return compute_composite_score(), compute_recession_probability()
