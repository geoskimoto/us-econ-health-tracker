"""
economy/fetcher.py

Fetches economic data from FRED and yfinance, writes DataPoints to the DB.
Raw API responses are cached via diskcache (24-hour TTL) to avoid redundant calls.

Public API:
    fetch_all_series() -> FetchResult
"""
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

import diskcache
import pandas as pd
from django.conf import settings

logger = logging.getLogger(__name__)

_cache = diskcache.Cache(settings.CACHE_DIR, size_limit=500_000_000)
_CACHE_TTL = 86_400  # 24 hours


@dataclass
class FetchResult:
    fetched: int = 0
    failed: int = 0
    points_written: int = 0
    errors: list = field(default_factory=list)


# ─── FRED ─────────────────────────────────────────────────────────────────────

def _fred_client():
    from fredapi import Fred
    api_key = settings.FRED_API_KEY
    if not api_key or api_key == "your-fred-api-key-here":
        raise RuntimeError("FRED_API_KEY not configured in .env")
    return Fred(api_key=api_key)


def _fetch_fred_series(fred, series_id: str, start: date) -> pd.Series | None:
    cache_key = f"fred:{series_id}:{start}"
    if cache_key in _cache:
        return _cache[cache_key]
    try:
        data = fred.get_series(series_id, observation_start=start.isoformat())
        _cache.set(cache_key, data, expire=_CACHE_TTL)
        return data
    except Exception as exc:
        logger.error("FRED fetch failed for %s: %s", series_id, exc)
        return None


# ─── yfinance ─────────────────────────────────────────────────────────────────

def _fetch_yfinance_series(yf_symbol: str, start: date) -> pd.Series | None:
    cache_key = f"yf:{yf_symbol}:{start}"
    if cache_key in _cache:
        return _cache[cache_key]
    try:
        import yfinance as yf
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(start=start.isoformat(), auto_adjust=True)
        if df.empty:
            return None
        series = df["Close"].rename(yf_symbol)
        series.index = series.index.tz_localize(None).normalize()
        _cache.set(cache_key, series, expire=_CACHE_TTL)
        return series
    except Exception as exc:
        logger.error("yfinance fetch failed for %s: %s", yf_symbol, exc)
        return None


# ─── DB write ─────────────────────────────────────────────────────────────────

def _upsert_series(series_id: str, data: pd.Series) -> int:
    from economy.models import DataPoint, EconomicSeries
    try:
        econ_series = EconomicSeries.objects.get(series_id=series_id)
    except EconomicSeries.DoesNotExist:
        logger.warning("EconomicSeries %s not found — skipping write.", series_id)
        return 0

    written = 0
    for ts, value in data.items():
        if pd.isna(value):
            continue
        obs_date = ts.date() if hasattr(ts, "date") else ts
        _, created = DataPoint.objects.update_or_create(
            series=econ_series,
            date=obs_date,
            defaults={"value": float(value)},
        )
        if created:
            written += 1

    return written


# ─── Public API ───────────────────────────────────────────────────────────────

def fetch_all_series(lookback_years: int = 12) -> FetchResult:
    """
    Fetch all active EconomicSeries from their sources and write to DB.
    Uses a 12-year lookback to support 10-year z-score windows with buffer.
    """
    from economy.models import EconomicSeries

    result = FetchResult()
    start = date.today() - timedelta(days=lookback_years * 365)

    fred_series = EconomicSeries.objects.filter(is_active=True, source="fred")
    yf_series = EconomicSeries.objects.filter(is_active=True, source="yfinance")

    # ── FRED ──────────────────────────────────────────────────────────────────
    fred = None
    if fred_series.exists():
        try:
            fred = _fred_client()
        except RuntimeError as exc:
            logger.error("Cannot initialize FRED client: %s", exc)
            result.errors.append(str(exc))

    if fred:
        for series in fred_series:
            data = _fetch_fred_series(fred, series.series_id, start)
            if data is None or data.empty:
                result.failed += 1
                result.errors.append(f"FRED: no data for {series.series_id}")
                continue
            written = _upsert_series(series.series_id, data)
            result.fetched += 1
            result.points_written += written
            logger.info("FRED %s: %d obs, %d new points.", series.series_id, len(data), written)

    # ── yfinance ──────────────────────────────────────────────────────────────
    for series in yf_series:
        data = _fetch_yfinance_series(series.series_id, start)
        if data is None or data.empty:
            result.failed += 1
            result.errors.append(f"yfinance: no data for {series.series_id}")
            continue
        written = _upsert_series(series.series_id, data)
        result.fetched += 1
        result.points_written += written
        logger.info("yfinance %s: %d obs, %d new points.", series.series_id, len(data), written)

    return result
