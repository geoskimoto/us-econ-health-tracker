"""
economy/indicators.py

Computes derived indicators from stored DataPoints:
  - Z-scores vs 10-year window
  - Composite economic health score (0-100)
  - Yield curve spreads and inversion tracking
  - Recession probability score (0-100)
  - Beveridge curve data
  - Real vs. nominal adjustments

Public API:
    get_series_df(series_id, days) -> pd.Series
    get_latest_value(series_id) -> float | None
    get_yoy_change(series_id) -> float | None
    compute_zscore(series, window_years) -> float | None
    compute_yield_spreads() -> dict
    compute_recession_probability() -> float
    compute_composite_score() -> float
    compute_real_wage_growth() -> float | None
    get_beveridge_curve_data(months) -> pd.DataFrame
    build_snapshot() -> dict
"""
import logging
from datetime import date, timedelta

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_ZSCORE_WINDOW_YEARS = 10

# Domain weights for composite health score
_DOMAIN_WEIGHTS = {
    "labor": 0.30,
    "macro": 0.20,
    "markets": 0.15,
    "housing": 0.15,
    "consumer": 0.20,
}

# Series contributing to the composite score
_COMPOSITE_SERIES = [
    ("UNRATE", "labor"),
    ("ICSA", "labor"),
    ("CIVPART", "labor"),
    ("JTSJOL", "labor"),
    ("JTSQUL", "labor"),
    ("GDPC1", "macro"),
    ("CPIAUCSL", "macro"),
    ("FEDFUNDS", "macro"),
    ("INDPRO", "macro"),
    ("^GSPC", "markets"),
    ("^VIX", "markets"),
    ("DGS10", "markets"),
    ("HOUST", "housing"),
    ("MORTGAGE30US", "housing"),
    ("CSUSHPISA", "housing"),
    ("UMCSENT", "consumer"),
    ("RSAFS", "consumer"),
    ("PSAVERT", "consumer"),
]


# ─── Series retrieval ─────────────────────────────────────────────────────────

def get_series_df(series_id: str, days: int = 3650) -> pd.Series:
    """Return a DatetimeIndex Series of values for the given series_id."""
    from economy.models import DataPoint
    cutoff = date.today() - timedelta(days=days)
    qs = (
        DataPoint.objects
        .filter(series_id=series_id, date__gte=cutoff)
        .order_by("date")
        .values_list("date", "value")
    )
    if not qs:
        return pd.Series(dtype=float, name=series_id)
    dates, values = zip(*qs)
    return pd.Series(list(values), index=pd.to_datetime(list(dates)), name=series_id)


def get_latest_value(series_id: str) -> float | None:
    """Return the most recent non-null value for a series."""
    from economy.models import DataPoint
    dp = DataPoint.objects.filter(series_id=series_id).order_by("-date").first()
    return dp.value if dp else None


def get_yoy_change(series_id: str) -> float | None:
    """Year-over-year percentage change for the most recent data point."""
    series = get_series_df(series_id, days=420)
    if len(series) < 2:
        return None
    latest = series.iloc[-1]
    year_ago_idx = series.index.searchsorted(series.index[-1] - pd.DateOffset(years=1))
    if year_ago_idx >= len(series):
        return None
    year_ago = series.iloc[year_ago_idx]
    if year_ago == 0:
        return None
    return round(((latest - year_ago) / abs(year_ago)) * 100, 2)


# ─── Z-score ──────────────────────────────────────────────────────────────────

def compute_zscore(series: pd.Series, window_years: int = _ZSCORE_WINDOW_YEARS) -> float | None:
    """Z-score of the latest value against the trailing window."""
    if series.empty:
        return None
    cutoff = series.index[-1] - pd.DateOffset(years=window_years)
    window = series[series.index >= cutoff].dropna()
    if len(window) < 12:
        return None
    mean = window.mean()
    std = window.std()
    if std == 0:
        return 0.0
    return float((series.iloc[-1] - mean) / std)


# ─── Yield curve ──────────────────────────────────────────────────────────────

def compute_yield_spreads() -> dict:
    """Current yield curve spreads and inversion counts (spreads in pct points)."""
    dgs10 = get_series_df("DGS10", days=1000)
    dgs2 = get_series_df("DGS2", days=1000)
    dgs3mo = get_series_df("DGS3MO", days=1000)
    dgs30 = get_series_df("DGS30", days=1000)

    def _latest(s: pd.Series) -> float | None:
        return float(s.iloc[-1]) if not s.empty else None

    ten = _latest(dgs10)
    two = _latest(dgs2)
    three_mo = _latest(dgs3mo)
    thirty = _latest(dgs30)

    spread_10_2 = (ten - two) if (ten is not None and two is not None) else None
    spread_10_3m = (ten - three_mo) if (ten is not None and three_mo is not None) else None

    days_inverted_10_3m = 0
    if not dgs10.empty and not dgs3mo.empty:
        combined = pd.DataFrame({"dgs10": dgs10, "dgs3mo": dgs3mo}).dropna()
        spread_series = combined["dgs10"] - combined["dgs3mo"]
        days_inverted_10_3m = int((spread_series < 0).sum())

    return {
        "dgs3mo": three_mo,
        "dgs2": two,
        "dgs10": ten,
        "dgs30": thirty,
        "spread_10_2": spread_10_2,
        "spread_10_3m": spread_10_3m,
        "days_inverted_10_3m": days_inverted_10_3m,
        "inverted_10_2": (spread_10_2 < 0) if spread_10_2 is not None else False,
        "inverted_10_3m": (spread_10_3m < 0) if spread_10_3m is not None else False,
    }


# ─── Recession probability ────────────────────────────────────────────────────

def compute_recession_probability() -> float:
    """
    Rule-based recession probability score (0-100).
    Combines yield curve inversion, Sahm Rule, claims trend, industrial production.
    """
    score = 0.0

    # Yield curve 10Y-3M inversion (weight: 35)
    spreads = compute_yield_spreads()
    if spreads["inverted_10_3m"]:
        score += 35.0
    elif spreads["spread_10_3m"] is not None and spreads["spread_10_3m"] < 0.25:
        score += 15.0

    # Sahm Rule (weight: 30) — >= 0.5 triggers recession signal
    sahm = get_latest_value("SAHMREALTIME")
    if sahm is not None:
        if sahm >= 0.5:
            score += 30.0
        elif sahm >= 0.3:
            score += 15.0
        elif sahm >= 0.1:
            score += 5.0

    # Initial claims 4-week MA rising (weight: 20)
    claims = get_series_df("ICSA", days=365)
    if len(claims) >= 8:
        recent_4wk = claims.iloc[-4:].mean()
        prior_4wk = claims.iloc[-8:-4].mean()
        if prior_4wk > 0:
            pct_change = (recent_4wk - prior_4wk) / prior_4wk * 100
            if pct_change >= 10:
                score += 20.0
            elif pct_change >= 5:
                score += 10.0

    # Industrial production YoY contraction (weight: 15)
    yoy = get_yoy_change("INDPRO")
    if yoy is not None:
        if yoy < 0:
            score += 15.0
        elif yoy < 1.0:
            score += 5.0

    return round(min(score, 100.0), 1)


# ─── Composite health score ────────────────────────────────────────────────────

def compute_composite_score() -> float:
    """
    Domain-weighted composite economic health score (0-100).
    Z-scores each active indicator series and normalizes.
    """
    from economy.models import EconomicSeries

    domain_scores: dict[str, list[float]] = {d: [] for d in _DOMAIN_WEIGHTS}

    for series_id, domain in _COMPOSITE_SERIES:
        try:
            meta = EconomicSeries.objects.get(series_id=series_id, is_active=True)
        except EconomicSeries.DoesNotExist:
            continue

        series_data = get_series_df(series_id, days=_ZSCORE_WINDOW_YEARS * 365 + 400)
        if series_data.empty:
            continue

        z = compute_zscore(series_data)
        if z is None:
            continue

        if meta.invert_for_score:
            z = -z

        # Clamp to [-3, 3], normalize to [0, 1]
        z_clamped = max(-3.0, min(3.0, z))
        normalized = (z_clamped + 3.0) / 6.0

        if domain in domain_scores:
            domain_scores[domain].append(normalized)

    if not any(domain_scores.values()):
        return 50.0

    total = 0.0
    weight_used = 0.0
    for domain, weight in _DOMAIN_WEIGHTS.items():
        vals = domain_scores.get(domain, [])
        if vals:
            total += float(np.mean(vals)) * weight
            weight_used += weight

    if weight_used == 0:
        return 50.0

    return round((total / weight_used) * 100, 1)


# ─── Real vs. nominal ─────────────────────────────────────────────────────────

def compute_real_wage_growth() -> float | None:
    """AHE YoY minus CPI YoY = real wage growth (percentage points)."""
    ahe_yoy = get_yoy_change("CES0500000003")
    cpi_yoy = get_yoy_change("CPIAUCSL")
    if ahe_yoy is None or cpi_yoy is None:
        return None
    return round(ahe_yoy - cpi_yoy, 2)


# ─── Beveridge curve ──────────────────────────────────────────────────────────

def get_beveridge_curve_data(months: int = 36) -> pd.DataFrame:
    """Job openings (thousands) vs unemployment rate — for scatter plot."""
    openings = get_series_df("JTSJOL", days=months * 31)
    unrate = get_series_df("UNRATE", days=months * 31)
    combined = pd.DataFrame({"openings": openings, "unrate": unrate}).dropna()
    return combined


# ─── Snapshot builder ─────────────────────────────────────────────────────────

def build_snapshot() -> dict:
    """
    Structured snapshot of all current indicator values.
    Serialized to DailyAnalysis.snapshot_json and fed to Claude Haiku.
    """
    spreads = compute_yield_spreads()
    composite = compute_composite_score()
    recession_prob = compute_recession_probability()
    real_wages = compute_real_wage_growth()

    def _val(sid): return get_latest_value(sid)
    def _yoy(sid): return get_yoy_change(sid)

    return {
        "date": date.today().isoformat(),
        "composite_health_score": composite,
        "recession_probability": recession_prob,
        "macro": {
            "real_gdp_growth_pct": _val("A191RL1Q225SBEA"),
            "cpi_headline_yoy": _yoy("CPIAUCSL"),
            "cpi_core_yoy": _yoy("CPILFESL"),
            "pce_core_yoy": _yoy("PCEPILFE"),
            "fed_funds_rate": _val("FEDFUNDS"),
            "m2_yoy": _yoy("M2SL"),
            "trade_balance_bn": _val("BOPGSTB"),
            "debt_to_gdp": _val("GFDEGDQ188S"),
        },
        "yield_curve": {
            "dgs3mo": spreads["dgs3mo"],
            "dgs2": spreads["dgs2"],
            "dgs10": spreads["dgs10"],
            "dgs30": spreads["dgs30"],
            "spread_10_2": spreads["spread_10_2"],
            "spread_10_3m": spreads["spread_10_3m"],
            "inverted_10_3m": spreads["inverted_10_3m"],
            "days_inverted_10_3m": spreads["days_inverted_10_3m"],
        },
        "labor": {
            "unemployment_u3": _val("UNRATE"),
            "unemployment_u6": _val("U6RATE"),
            "nonfarm_payrolls_yoy": _yoy("PAYEMS"),
            "initial_claims": _val("ICSA"),
            "prime_age_lfpr": _val("LNS11300060"),
            "job_openings_k": _val("JTSJOL"),
            "quits_rate": _val("JTSQUL"),
            "sahm_rule": _val("SAHMREALTIME"),
            "real_wage_growth": real_wages,
            "unit_labor_costs_yoy": _yoy("ULCNFB"),
        },
        "housing": {
            "housing_starts_k": _val("HOUST"),
            "building_permits_k": _val("PERMIT"),
            "case_shiller_yoy": _yoy("CSUSHPISA"),
            "mortgage_rate_30y": _val("MORTGAGE30US"),
        },
        "markets": {
            "sp500": _val("^GSPC"),
            "sp500_yoy": _yoy("^GSPC"),
            "vix": _val("^VIX"),
            "gold": _val("GC=F"),
            "wti_crude": _val("CL=F"),
            "copper": _val("HG=F"),
        },
        "consumer": {
            "umich_sentiment": _val("UMCSENT"),
            "retail_sales_yoy": _yoy("RSAFS"),
            "personal_savings_rate": _val("PSAVERT"),
            "industrial_production_yoy": _yoy("INDPRO"),
            "capacity_utilization": _val("TCU"),
        },
    }
