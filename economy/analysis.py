"""
economy/analysis.py — Claude Haiku daily economy assessment.
Mirrors stock-alert-system scanner/analysis.py pattern.
"""
import logging
import datetime

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

MODEL_LABELS = {
    "claude-haiku-4-5-20251001": "haiku",
    "claude-sonnet-4-6": "sonnet",
}

_SYSTEM_PROMPT = """You are a macroeconomic research analyst providing a daily assessment of \
the US economy for an economic monitoring dashboard.

You receive a structured JSON snapshot of current economic indicators across six domains:
  - Macro: GDP growth, inflation (CPI/PCE), Fed policy, money supply, trade, fiscal
  - Yield Curve: Treasury yields (3M, 2Y, 10Y, 30Y) and key spreads
  - Labor: Unemployment (U-3, U-6), payrolls, JOLTS, claims, LFPR, Sahm Rule, wages
  - Housing: Starts, permits, home prices, mortgage rates
  - Markets: S&P 500, VIX, commodities (gold, oil, copper)
  - Consumer & Business: Sentiment, retail sales, savings rate, industrial production

The snapshot also includes:
  - composite_health_score: 0-100, domain-weighted z-score index (50 = historical average)
  - recession_probability: 0-100, rules-based score (yield curve + Sahm + claims + IP)

Be concise, technically precise, and intellectually honest about uncertainty. \
This is an informational research tool, not financial or policy advice."""


def _build_user_prompt(snapshot: dict) -> str:
    def _fmt(v, decimals=2, suffix=""):
        if v is None:
            return "n/a"
        return f"{v:.{decimals}f}{suffix}"

    m = snapshot.get("macro", {})
    yc = snapshot.get("yield_curve", {})
    lb = snapshot.get("labor", {})
    ho = snapshot.get("housing", {})
    mk = snapshot.get("markets", {})
    co = snapshot.get("consumer", {})

    inv = ""
    if yc.get("inverted_10_3m"):
        inv = f" [INVERTED — {yc.get('days_inverted_10_3m', 0)} days]"

    return f"""Analyze the following US economy snapshot as of {snapshot.get('date', 'today')}:

COMPOSITE SCORES
  Economic Health Score: {_fmt(snapshot.get('composite_health_score'), 1)}/100  (50 = historical avg)
  Recession Probability: {_fmt(snapshot.get('recession_probability'), 1)}/100

MACRO
  Real GDP Growth: {_fmt(m.get('real_gdp_growth_pct'), 1, '%')} annualized
  CPI Headline YoY: {_fmt(m.get('cpi_headline_yoy'), 1, '%')}
  CPI Core YoY: {_fmt(m.get('cpi_core_yoy'), 1, '%')}
  Core PCE YoY: {_fmt(m.get('pce_core_yoy'), 1, '%')}
  Fed Funds Rate: {_fmt(m.get('fed_funds_rate'), 2, '%')}
  M2 YoY: {_fmt(m.get('m2_yoy'), 1, '%')}
  Trade Balance: ${_fmt(m.get('trade_balance_bn'), 1)}B
  Debt/GDP: {_fmt(m.get('debt_to_gdp'), 1, '%')}

YIELD CURVE
  3M: {_fmt(yc.get('dgs3mo'), 2, '%')} | 2Y: {_fmt(yc.get('dgs2'), 2, '%')} | 10Y: {_fmt(yc.get('dgs10'), 2, '%')} | 30Y: {_fmt(yc.get('dgs30'), 2, '%')}
  10Y-2Y Spread: {_fmt(yc.get('spread_10_2'), 2, ' pp')}{inv}
  10Y-3M Spread: {_fmt(yc.get('spread_10_3m'), 2, ' pp')}{inv}

LABOR
  Unemployment U-3: {_fmt(lb.get('unemployment_u3'), 1, '%')}
  Unemployment U-6: {_fmt(lb.get('unemployment_u6'), 1, '%')}
  Payrolls YoY: {_fmt(lb.get('nonfarm_payrolls_yoy'), 1, '%')}
  Initial Claims (wk): {_fmt(lb.get('initial_claims'), 0, 'K')}
  Prime-Age LFPR: {_fmt(lb.get('prime_age_lfpr'), 1, '%')}
  Job Openings: {_fmt(lb.get('job_openings_k'), 0, 'K')}
  Sahm Rule: {_fmt(lb.get('sahm_rule'), 2)}  (>=0.5 = recession signal)
  Real Wage Growth: {_fmt(lb.get('real_wage_growth'), 2, ' pp')}
  Unit Labor Costs YoY: {_fmt(lb.get('unit_labor_costs_yoy'), 1, '%')}

HOUSING
  Housing Starts: {_fmt(ho.get('housing_starts_k'), 0, 'K')} annualized
  Building Permits: {_fmt(ho.get('building_permits_k'), 0, 'K')} annualized
  Case-Shiller YoY: {_fmt(ho.get('case_shiller_yoy'), 1, '%')}
  30Y Mortgage Rate: {_fmt(ho.get('mortgage_rate_30y'), 2, '%')}

MARKETS
  S&P 500: {_fmt(mk.get('sp500'), 0)} ({_fmt(mk.get('sp500_yoy'), 1, '% YoY')})
  VIX: {_fmt(mk.get('vix'), 1)}
  WTI Crude: ${_fmt(mk.get('wti_crude'), 2)}/bbl
  Gold: ${_fmt(mk.get('gold'), 0)}/oz
  Copper: ${_fmt(mk.get('copper'), 3)}/lb

CONSUMER & BUSINESS
  UMich Sentiment: {_fmt(co.get('umich_sentiment'), 1)}
  Retail Sales YoY: {_fmt(co.get('retail_sales_yoy'), 1, '%')}
  Personal Savings Rate: {_fmt(co.get('personal_savings_rate'), 1, '%')}
  Industrial Production YoY: {_fmt(co.get('industrial_production_yoy'), 1, '%')}
  Capacity Utilization: {_fmt(co.get('capacity_utilization'), 1, '%')}

Write a 200-300 word analysis covering:
1. Overall economic phase (expansion / slowdown / contraction) and confidence level
2. Top 2-3 signals of strength or concern — lead with leading indicators
3. Key divergence between leading and lagging indicators (if any)
4. One sentence on the most significant risk to the current trajectory
Close with one sentence noting this is informational only."""


def generate_analysis(model: str = "claude-haiku-4-5-20251001") -> str | None:
    """Build snapshot, call Claude, persist to DailyAnalysis, return text."""
    api_key = getattr(settings, "ANTHROPIC_API_KEY", "")
    if not api_key or api_key == "your-anthropic-api-key-here":
        logger.warning("ANTHROPIC_API_KEY not set — skipping analysis.")
        return None

    try:
        import anthropic
    except ImportError:
        logger.error("anthropic package not installed.")
        return None

    from economy.indicators import build_snapshot
    from economy.models import DailyAnalysis

    snapshot = build_snapshot()

    try:
        client = anthropic.Anthropic(api_key=api_key)

        message = client.messages.create(
            model=model,
            max_tokens=600,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": _build_user_prompt(snapshot)}],
        )

        analysis_text = message.content[0].text.strip()
        label = MODEL_LABELS.get(model, model)
        today = datetime.date.today()

        DailyAnalysis.objects.update_or_create(
            date=today,
            defaults={
                "analysis": analysis_text,
                "analysis_model": label,
                "generated_at": timezone.now(),
                "snapshot_json": snapshot,
                "recession_probability": snapshot.get("recession_probability"),
                "composite_health_score": snapshot.get("composite_health_score"),
            },
        )

        logger.info(
            "Analysis generated for %s using %s (%d chars, input_tokens=%d, cache_read=%d).",
            today, label, len(analysis_text),
            message.usage.input_tokens,
            getattr(message.usage, "cache_read_input_tokens", 0),
        )
        return analysis_text

    except Exception as exc:
        logger.error("Analysis generation failed: %s", exc)
        return None
