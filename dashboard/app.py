"""
dashboard/app.py — US Economy Dashboard (Plotly Dash via django-plotly-dash).

Seven tabs:
  Overview | Macro | Labor | Housing | Markets | Consumer/Business | AI Analysis
"""
import logging

import dash
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import Input, Output, State, dcc, html
from django_plotly_dash import DjangoDash
from plotly.subplots import make_subplots

logger = logging.getLogger(__name__)

# ─── Colour palette (colorblind-safe) ────────────────────────────────────────

C_BLUE   = "#0077BB"
C_RED    = "#CC3311"
C_ORANGE = "#EE7733"
C_GREEN  = "#117733"
C_TEAL   = "#44AA99"
C_YELLOW = "#DDCC77"
C_PURPLE = "#785EF0"
C_GRAY   = "#AAAAAA"

_PLOT_LAYOUT = dict(
    paper_bgcolor="white",
    plot_bgcolor="white",
    margin={"t": 40, "b": 40, "l": 60, "r": 20},
    hovermode="x unified",
    legend={"orientation": "h", "yanchor": "bottom", "y": 1.01, "x": 0, "font": {"size": 11}},
)

# ─── Indicator descriptions per tab ───────────────────────────────────────────

MACRO_INDICATOR_INFO = {
    "gdp": {
        "name": "Real GDP Growth Rate (annualized %)",
        "source": "FRED: A191RL1Q225SBEA — quarterly",
        "what": (
            "Inflation-adjusted quarterly GDP growth, annualized. "
            "The broadest single measure of economic output."
        ),
        "watch": (
            "Above 2%: healthy expansion | Below 1%: slowdown | "
            "Two consecutive negative quarters: technical recession"
        ),
        "limitation": (
            "Quarterly frequency means recessions are confirmed 1–2 quarters late. "
            "Subject to significant revision."
        ),
    },
    "inflation": {
        "name": "CPI, Core CPI & Core PCE Year-over-Year %",
        "source": "FRED: CPIAUCSL, CPILFESL, PCEPILFE — monthly",
        "what": (
            "Headline CPI includes food and energy. Core strips those out. "
            "Core PCE is the Fed's preferred inflation target (2%)."
        ),
        "watch": (
            "Below 2.5%: approaching target | 2.5–4%: elevated | "
            "Above 4%: high — pressure on Fed to remain restrictive"
        ),
        "limitation": (
            "Shelter inflation in CPI lags real-time market rents by 12–18 months. "
            "Basket weights are updated with a lag."
        ),
    },
    "fed_funds": {
        "name": "Federal Funds Rate (%)",
        "source": "FRED: FEDFUNDS — monthly effective rate",
        "what": (
            "Overnight interbank lending rate set by the FOMC. "
            "Primary lever for managing inflation and employment."
        ),
        "watch": (
            "Rising: restrictive — suppresses inflation and growth | "
            "Falling: accommodative — stimulus mode"
        ),
        "limitation": (
            "Rate changes transmit to the real economy with a 12–18 month lag. "
            "A lagging policy tool, not a leading economic indicator."
        ),
    },
    "m2": {
        "name": "M2 Money Supply YoY %",
        "source": "FRED: M2SL — monthly",
        "what": (
            "Broad money supply: cash, checking, savings, and money market funds. "
            "Rapid M2 growth can be inflationary; contraction is historically rare."
        ),
        "watch": (
            "Positive YoY: liquidity expanding | Negative YoY: tightening — "
            "occurred 2022–23 for the first time since 1930s"
        ),
        "limitation": (
            "Relationship between M2 and inflation is unstable over time. "
            "Useful as context, not a direct predictor."
        ),
    },
    "trade": {
        "name": "Trade Balance ($M)",
        "source": "FRED: BOPGSTB — monthly BEA",
        "what": (
            "Net exports of goods and services. "
            "Deficit = imports exceed exports."
        ),
        "watch": (
            "Narrowing deficit: domestic production improving or dollar weakening | "
            "Widening: strong domestic demand absorbing imports"
        ),
        "limitation": (
            "Sensitive to dollar strength and global demand cycles. "
            "A trade deficit is not inherently negative for growth."
        ),
    },
    "debt_gdp": {
        "name": "Federal Debt to GDP (%)",
        "source": "FRED: GFDEGDQ188S — quarterly Treasury/BEA",
        "what": (
            "Total federal debt as a share of GDP. "
            "Broad measure of fiscal sustainability."
        ),
        "watch": (
            "Below 60%: low concern | 60–100%: moderate | "
            "Above 100%: elevated — US is currently in this range"
        ),
        "limitation": (
            "Threshold levels are contested. The US borrows in its own currency, "
            "which reduces but does not eliminate long-run fiscal risk."
        ),
    },
}

LABOR_INDICATOR_INFO = {
    "u3_u6": {
        "name": "U-3 & U-6 Unemployment Rates (%)",
        "source": "FRED: UNRATE (U-3), U6RATE (U-6) — monthly BLS CPS",
        "what": (
            "U-3: officially unemployed. "
            "U-6: adds discouraged workers and involuntary part-timers. "
            "U-6 is the broader, more complete measure."
        ),
        "watch": (
            "U-3 below 4%: tight labor market | U-3 above 5%: slack building | "
            "U-6/U-3 gap widening: quality of employment deteriorating"
        ),
        "limitation": (
            "Neither metric captures people who've fully stopped searching "
            "or gig workers who are economically underemployed."
        ),
    },
    "initial_claims": {
        "name": "Initial Jobless Claims (weekly, thousands)",
        "source": "FRED: ICSA — weekly DOL UI filings",
        "what": (
            "New unemployment insurance filings. The most timely labor market signal — "
            "published weekly, 4-day lag."
        ),
        "watch": (
            "Below 250K: strong labor market | 250–300K: normalizing | "
            "Above 350K: deteriorating | 4-week trend matters more than any single week"
        ),
        "limitation": (
            "Affected by seasonality, weather, and eligibility rule changes. "
            "High-frequency noise; always interpret using the 4-week moving average."
        ),
    },
    "lfpr": {
        "name": "Labor Force Participation Rate (%)",
        "source": "FRED: CIVPART (overall), LNS11300060 (prime-age 25–54) — monthly BLS",
        "what": (
            "Share of working-age population employed or actively seeking work. "
            "Prime-age (25–54) filters out retirement-driven demographic decline."
        ),
        "watch": (
            "Prime-age LFPR near pre-pandemic peak (~83%): fully recovered | "
            "Declining: hidden labor slack — may suppress wage growth"
        ),
        "limitation": (
            "Long-run demographic trends structurally lower the headline LFPR. "
            "Use prime-age as the cleaner cyclical signal."
        ),
    },
    "jolts": {
        "name": "JOLTS — Openings, Hires, Quits, Layoffs (thousands)",
        "source": "FRED: JTSJOL, JTSHIL, JTSQUL, JTSLDL — monthly BLS, ~2-month lag",
        "what": (
            "Openings = unmet labor demand. Quits = worker confidence in finding better jobs. "
            "Layoffs = employer stress. Together they paint a full picture of labor flows."
        ),
        "watch": (
            "Openings above 8M: very tight | Quits rate above 2.5%: workers have bargaining power | "
            "Layoffs rising: early deterioration — often leads claims by 1–2 months"
        ),
        "limitation": (
            "2-month publication lag. Opening counts don't distinguish "
            "active recruiting from posted-but-neglected positions."
        ),
    },
    "beveridge": {
        "name": "Beveridge Curve (Openings vs Unemployment)",
        "source": "FRED: JTSJOL × UNRATE — monthly, plotted as scatter",
        "what": (
            "Scatter of job openings vs unemployment over time. "
            "An upward shift of the curve indicates structural mismatch. "
            "Movement toward the origin = market cooling."
        ),
        "watch": (
            "Upper-left (high openings, low unemployment): extremely tight | "
            "Lower-right: slack building | Curve shifting up: skills or geography mismatch"
        ),
        "limitation": (
            "Curve shifts can reflect structural changes (remote work, skills mismatch) "
            "that are difficult to disentangle from cyclical labor market conditions."
        ),
    },
    "sahm": {
        "name": "Sahm Rule Indicator",
        "source": "FRED: SAHMREALTIME — monthly BLS/FRED calculation",
        "what": (
            "3-month average unemployment rate minus the prior 12-month low. "
            "Values ≥ 0.5 have historically coincided with the start of every US recession since 1970."
        ),
        "watch": (
            "Below 0.3: low near-term risk | 0.3–0.5: warning zone — monitor closely | "
            "≥ 0.5: recession signal triggered"
        ),
        "limitation": (
            "Backward-looking — triggers after a recession has already begun. "
            "Designed for real-time calling, not forecasting. "
            "One false signal (2019) exists in the historical record."
        ),
    },
}

HOUSING_INDICATOR_INFO = {
    "starts_permits": {
        "name": "Housing Starts & Building Permits (thousands, annualized)",
        "source": "FRED: HOUST, PERMIT — monthly Census Bureau",
        "what": (
            "Starts = construction newly begun. "
            "Permits lead starts by 1–3 months and are the more forward-looking signal."
        ),
        "watch": (
            "Starts above 1.5M: healthy construction | Below 1.0M: significant weakness | "
            "Permits diverging above starts: pipeline building"
        ),
        "limitation": (
            "Highly weather-sensitive. Single-family vs multi-family mix matters — "
            "a multi-family surge has different economic implications than single-family."
        ),
    },
    "mortgage": {
        "name": "30-Year Fixed Mortgage Rate (%)",
        "source": "FRED: MORTGAGE30US — weekly Freddie Mac PMMS",
        "what": (
            "Benchmark rate for home purchase financing. "
            "Directly determines monthly payment and purchasing power for buyers."
        ),
        "watch": (
            "Below 5%: broadly affordable | 5–7%: moderate restraint on demand | "
            "Above 7%: significant affordability stress — reduces buyer pool"
        ),
        "limitation": (
            "Lock-in effect: existing homeowners with low rates won't sell, reducing supply. "
            "Rate matters in context of incomes and home prices, not in isolation."
        ),
    },
    "case_shiller": {
        "name": "Case-Shiller National Home Price Index",
        "source": "FRED: CSUSHPISA — monthly, 2-month publication lag",
        "what": (
            "Repeat-sale price index tracking the same properties over time. "
            "Isolates price changes from compositional shifts in what's being sold."
        ),
        "watch": (
            "Sustained rises: appreciation continuing | Flat or declining: correction underway | "
            "YoY below 0: outright home price deflation — historically rare"
        ),
        "limitation": (
            "2-month lag. National average masks large regional variation. "
            "Does not reflect rental market conditions."
        ),
    },
    "case_shiller_yoy": {
        "name": "Case-Shiller YoY % Change",
        "source": "FRED: CSUSHPISA pct_change(12) — monthly",
        "what": (
            "Annual rate of home price appreciation or depreciation. "
            "Useful for identifying turning points in the housing cycle."
        ),
        "watch": (
            "Above 5%: rapid appreciation, affordability risk | Near 0%: stabilizing | "
            "Negative: price decline underway"
        ),
        "limitation": (
            "YoY can appear flat during a soft landing if appreciation slows without reversing. "
            "Negative readings are historically rare outside recessions."
        ),
    },
}

MARKETS_INDICATOR_INFO = {
    "equities": {
        "name": "S&P 500 & Russell 2000",
        "source": "yfinance: ^GSPC (large-cap S&P 500), ^RUT (small-cap Russell 2000)",
        "what": (
            "SPX tracks large-cap US equities; RUT tracks small-caps. "
            "Comparing them reveals the breadth of equity market participation."
        ),
        "watch": (
            "RUT outperforming SPX: risk appetite is broad-based | "
            "RUT underperforming: defensive rotation or credit stress | "
            "SPX new highs without RUT: narrow, potentially fragile leadership"
        ),
        "limitation": (
            "Equity markets are forward-looking but frequently wrong. "
            "Short-term price action is driven by positioning and flows, not just fundamentals."
        ),
    },
    "vix": {
        "name": "VIX — CBOE Volatility Index",
        "source": "yfinance: ^VIX — daily CBOE 30-day implied vol",
        "what": (
            "30-day implied volatility derived from S&P 500 options. "
            "Measures market uncertainty — often called the 'fear gauge.'"
        ),
        "watch": (
            "Below 15: complacent | 15–20: normal | 20–30: elevated uncertainty | "
            "Above 30: high stress | Spikes above 40: panic or crisis"
        ),
        "limitation": (
            "Measures options pricing (implied vol), not realized volatility. "
            "VIX can remain elevated for months in genuine bear markets — mean reversion is not guaranteed."
        ),
    },
    "yield_curve": {
        "name": "Yield Curve Snapshot (current maturities)",
        "source": "FRED: DGS3MO, DGS2, DGS10, DGS30 — daily Treasury CMT",
        "what": (
            "Current yield at 3M, 2Y, 10Y, 30Y maturities. "
            "Normal curve slopes upward. Inversion = short rates above long rates."
        ),
        "watch": (
            "Normal upward slope: healthy growth expectations | "
            "Flat: market pricing stagnation | Inverted: recession leading indicator"
        ),
        "limitation": (
            "Fed QE/QT and foreign demand for Treasuries can suppress long rates, "
            "complicating the traditional inversion signal."
        ),
    },
    "spreads": {
        "name": "Yield Curve Spreads — 10Y-2Y and 10Y-3M (pp)",
        "source": "FRED: DGS10 − DGS2, DGS10 − DGS3MO — daily",
        "what": (
            "10Y-3M spread (NY Fed recession model) is the stronger historical predictor. "
            "10Y-2Y is more widely watched by practitioners."
        ),
        "watch": (
            "10Y-3M below 0 pp: inversion — has preceded every US recession since 1970 | "
            "Steepening after inversion: may signal imminent recession (bull steepening)"
        ),
        "limitation": (
            "Inversion must be sustained — days don't count. "
            "Lead time to recession ranges from 6 to 24 months, with high variance."
        ),
    },
    "commodities": {
        "name": "WTI Crude Oil & Gold",
        "source": "yfinance: CL=F (WTI crude), GC=F (gold)",
        "what": (
            "Crude reflects global growth expectations and supply dynamics. "
            "Gold is a safe-haven asset and inflation hedge."
        ),
        "watch": (
            "Crude rising: growth optimism or supply tightening | "
            "Crude falling sharply: demand destruction | "
            "Gold rising amid falling equities: risk-off positioning"
        ),
        "limitation": (
            "Both are heavily influenced by geopolitical supply shocks (OPEC+, sanctions) "
            "that are unrelated to US domestic economic conditions."
        ),
    },
    "copper_gold": {
        "name": "Copper/Gold Ratio — Economic Activity Proxy",
        "source": "yfinance: HG=F / GC=F × 100",
        "what": (
            "Copper is industrial; gold is a safe haven. "
            "A rising ratio signals growth expectations outpacing fear. "
            "Falling ratio signals flight to safety."
        ),
        "watch": (
            "Rising: economically constructive, global demand expanding | "
            "Falling: risk-off, growth concerns | "
            "Diverging from equities: potential leading indicator of equity direction"
        ),
        "limitation": (
            "Can move on copper supply disruptions (mining strikes, reserve changes) "
            "unrelated to economic growth expectations."
        ),
    },
}

CONSUMER_INDICATOR_INFO = {
    "umich": {
        "name": "University of Michigan Consumer Sentiment",
        "source": "FRED: UMCSENT — monthly U of M survey (~500 households)",
        "what": (
            "Survey of consumer confidence in personal finances and the broader economy. "
            "Scale roughly 0–120; historical average ~85."
        ),
        "watch": (
            "Above 90: strong confidence | 70–90: moderate | "
            "Below 70: pessimistic | Sharp drops: leading indicator of spending pullback"
        ),
        "limitation": (
            "Surveys measure mood, not spending. Sentiment and actual consumption can diverge — "
            "consumers can feel pessimistic yet keep spending."
        ),
    },
    "retail": {
        "name": "Retail Sales YoY %",
        "source": "FRED: RSAFS — monthly Census Bureau advance retail trade survey",
        "what": (
            "Year-over-year change in retail and food service sales. "
            "Proxy for consumer spending, which drives ~70% of US GDP."
        ),
        "watch": (
            "Above 3%: healthy spending growth | Near 0%: stagnating | "
            "Negative: contraction — often precedes or accompanies recession"
        ),
        "limitation": (
            "Nominal (not inflation-adjusted). High inflation produces positive nominal growth "
            "even when real spending is flat or declining."
        ),
    },
    "savings": {
        "name": "Personal Savings Rate (%)",
        "source": "FRED: PSAVERT — monthly BEA personal income accounts",
        "what": (
            "Personal savings as a percent of disposable income. "
            "Low savings means consumers are spending down financial buffers."
        ),
        "watch": (
            "Above 6%: consumers rebuilding cushion | 3–6%: normal consumption mode | "
            "Below 3%: stretched — spending may not be sustainable without income gains"
        ),
        "limitation": (
            "Volatile around income timing events (tax refunds, bonuses, stimulus). "
            "Doesn't capture wealth-effect spending from rising home or equity values."
        ),
    },
    "industrial": {
        "name": "Industrial Production YoY % & Capacity Utilization (%)",
        "source": "FRED: INDPRO, TCU — monthly Federal Reserve G.17 release",
        "what": (
            "Industrial output change vs a year ago, plus what fraction of factory/utility "
            "capacity is currently in use. Together measure manufacturing sector health."
        ),
        "watch": (
            "INDPRO positive YoY: manufacturing expanding | "
            "Capacity utilization above 80%: tight, upward pressure on goods prices | "
            "Below 75%: significant slack"
        ),
        "limitation": (
            "Manufacturing is ~10% of US GDP. Services dominate the modern economy, "
            "so industrial indicators are less predictive than in prior decades."
        ),
    },
}

# ─── App initialisation ───────────────────────────────────────────────────────

app = DjangoDash(
    "EconDashboard",
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    add_bootstrap_links=True,
)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _line_chart(series_dict: dict, title: str = "", height: int = 350) -> go.Figure:
    """Build a simple multi-series line chart from {label: pd.Series} dict."""
    colours = [C_BLUE, C_RED, C_ORANGE, C_TEAL, C_PURPLE, C_GREEN, C_YELLOW]
    fig = go.Figure()
    for i, (label, series) in enumerate(series_dict.items()):
        if series is None or series.empty:
            continue
        fig.add_trace(go.Scatter(
            x=series.index, y=series.values,
            name=label,
            line={"color": colours[i % len(colours)], "width": 1.8},
        ))
    fig.update_layout(**_PLOT_LAYOUT, height=height, title=title)
    fig.update_xaxes(showgrid=True, gridcolor="#eeeeee")
    fig.update_yaxes(showgrid=True, gridcolor="#eeeeee")
    return fig


def _hex_alpha(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _gauge(value: float | None, title: str, max_val: float = 100,
           low_color: str = C_RED, high_color: str = C_GREEN) -> go.Figure:
    """Gauge indicator for composite score or recession probability."""
    display = value if value is not None else 0
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=display,
        title={"text": title, "font": {"size": 14}},
        gauge={
            "axis": {"range": [0, max_val], "tickwidth": 1},
            "bar": {"color": C_BLUE},
            "steps": [
                {"range": [0, max_val * 0.33], "color": _hex_alpha(low_color, 0.2)},
                {"range": [max_val * 0.33, max_val * 0.66], "color": _hex_alpha(C_YELLOW, 0.2)},
                {"range": [max_val * 0.66, max_val], "color": _hex_alpha(high_color, 0.2)},
            ],
            "threshold": {
                "line": {"color": C_RED, "width": 3},
                "thickness": 0.75,
                "value": display,
            },
        },
    ))
    fig.update_layout(height=220, margin={"t": 60, "b": 10, "l": 20, "r": 20})
    return fig


def _stat_card(label: str, value: str, delta: str = "", color: str = "primary") -> dbc.Card:
    return dbc.Card(
        dbc.CardBody([
            html.P(label, className="text-muted mb-1", style={"fontSize": "12px"}),
            html.H5(value, className="mb-0 fw-bold"),
            html.Small(delta, className=f"text-{'success' if delta.startswith('+') else 'danger' if delta.startswith('-') else 'muted'}"),
        ], style={"padding": "10px 14px"}),
        color=color, outline=True, className="mb-2",
    )


def _fmt(v, decimals=2, suffix=""):
    if v is None:
        return "n/a"
    return f"{v:.{decimals}f}{suffix}"


# ─── Indicator notes builder ──────────────────────────────────────────────────

def _build_indicator_notes(info_dict: dict, current_values: dict, tab_label: str) -> list:
    """Render a reference card grid for a tab's economic indicators."""
    cards = []
    for key, info in info_dict.items():
        val_str = current_values.get(key) or "—"
        cards.append(
            dbc.Card(
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col(
                            html.Strong(info["name"], style={"fontSize": "13px"}),
                            width=8,
                        ),
                        dbc.Col(
                            dbc.Badge(
                                val_str,
                                color="primary",
                                className="ms-auto",
                                style={"fontSize": "11px"},
                            ),
                            width=4,
                            className="text-end",
                        ),
                    ], className="mb-1"),
                    html.P(
                        [html.Span("Source: ", style={"fontWeight": "600"}), info.get("source", "")],
                        style={"fontSize": "11px", "color": "#666", "marginBottom": "4px"},
                    ),
                    html.P(
                        info.get("what", ""),
                        style={"fontSize": "12px", "color": "#444", "marginBottom": "4px"},
                    ),
                    html.P(
                        [html.Span("Watch for: ", style={"fontWeight": "600"}), info.get("watch", "")],
                        style={"fontSize": "12px", "marginBottom": "4px"},
                    ),
                    html.P(
                        [
                            html.Span("Limitation: ", style={"fontWeight": "600", "color": "#888"}),
                            html.Span(info.get("limitation", ""), style={"color": "#888"}),
                        ],
                        style={"fontSize": "11px", "marginBottom": 0},
                    ),
                ], style={"padding": "10px 14px"}),
                className="mb-2",
                style={"border": "1px solid #dee2e6"},
            )
        )

    return [
        html.Hr(className="mt-3 mb-3"),
        html.H6(
            f"Indicator Reference — {tab_label}",
            className="text-muted mb-2",
            style={"fontSize": "13px", "letterSpacing": "0.05em"},
        ),
        dbc.Row([dbc.Col(c, md=6) for c in cards]),
        html.P(
            "Data sourced from FRED, BLS, Census Bureau, BEA, and yfinance. "
            "Not financial advice.",
            className="text-muted mt-2",
            style={"fontSize": "11px"},
        ),
    ]


def _macro_values(snapshot: dict) -> dict:
    m = snapshot.get("macro", {})
    gdp = m.get("real_gdp_growth_pct")
    cpi = m.get("cpi_headline_yoy")
    pce = m.get("pce_core_yoy")
    return {
        "gdp":      f"{gdp:.1f}% annualized" if gdp is not None else None,
        "inflation": f"CPI {_fmt(cpi, 1)}% / Core PCE {_fmt(pce, 1)}%",
        "fed_funds": f"{_fmt(m.get('fed_funds_rate'), 2)}%",
        "m2":        f"YoY {_fmt(m.get('m2_yoy'), 1)}%",
        "trade":     f"${_fmt(m.get('trade_balance_bn'), 0)}M",
        "debt_gdp":  f"{_fmt(m.get('debt_to_gdp'), 1)}% of GDP",
    }


def _labor_values(snapshot: dict) -> dict:
    lb = snapshot.get("labor", {})
    return {
        "u3_u6":        f"U-3 {_fmt(lb.get('unemployment_u3'), 1)}% / U-6 {_fmt(lb.get('unemployment_u6'), 1)}%",
        "initial_claims": f"{_fmt(lb.get('initial_claims'), 0)}K weekly",
        "lfpr":         f"Prime-age {_fmt(lb.get('prime_age_lfpr'), 1)}%",
        "jolts":        f"Openings {_fmt(lb.get('job_openings_k'), 0)}K",
        "beveridge":    f"U-3 {_fmt(lb.get('unemployment_u3'), 1)}% / Openings {_fmt(lb.get('job_openings_k'), 0)}K",
        "sahm":         f"Sahm = {_fmt(lb.get('sahm_rule'), 2)}",
    }


def _housing_values(snapshot: dict) -> dict:
    ho = snapshot.get("housing", {})
    return {
        "starts_permits":   f"Starts {_fmt(ho.get('housing_starts_k'), 0)}K",
        "mortgage":         f"{_fmt(ho.get('mortgage_rate_30y'), 2)}%",
        "case_shiller":     "Index level",
        "case_shiller_yoy": f"YoY {_fmt(ho.get('case_shiller_yoy'), 1)}%",
    }


def _markets_values(snapshot: dict) -> dict:
    mk = snapshot.get("markets", {})
    yc = snapshot.get("yield_curve", {})
    cu_au = None
    copper = mk.get("copper")
    gold = mk.get("gold")
    if copper and gold:
        cu_au = round(copper / gold * 100, 3)
    return {
        "equities":    f"SPX YoY {_fmt(mk.get('sp500_yoy'), 1)}%",
        "vix":         f"VIX {_fmt(mk.get('vix'), 1)}",
        "yield_curve": f"10Y {_fmt(yc.get('dgs10'), 2)}% / 2Y {_fmt(yc.get('dgs2'), 2)}%",
        "spreads":     f"10Y-2Y {_fmt(yc.get('spread_10_2'), 2)} pp / 10Y-3M {_fmt(yc.get('spread_10_3m'), 2)} pp",
        "commodities": f"WTI ${_fmt(mk.get('wti_crude'), 1)} / Gold ${_fmt(mk.get('gold'), 0)}",
        "copper_gold": f"Cu/Au ratio {_fmt(cu_au, 3)}" if cu_au else "—",
    }


def _consumer_values(snapshot: dict) -> dict:
    co = snapshot.get("consumer", {})
    return {
        "umich":      f"Sentiment {_fmt(co.get('umich_sentiment'), 1)}",
        "retail":     f"Retail YoY {_fmt(co.get('retail_sales_yoy'), 1)}%",
        "savings":    f"Savings rate {_fmt(co.get('personal_savings_rate'), 1)}%",
        "industrial": f"IndPro YoY {_fmt(co.get('industrial_production_yoy'), 1)}% / CapUtil {_fmt(co.get('capacity_utilization'), 1)}%",
    }


# ─── Layout ───────────────────────────────────────────────────────────────────

app.layout = dbc.Container(
    fluid=True,
    style={"padding": "16px 24px", "backgroundColor": "#f8f9fa", "minHeight": "100vh"},
    children=[
        dcc.Store(id="snapshot-store"),
        dcc.Interval(id="refresh-interval", interval=3_600_000, n_intervals=0),

        # Header
        dbc.Row(align="center", className="mb-2", children=[
            dbc.Col(width="auto", children=[
                html.H4("US Economy Tracker", className="mb-0", style={"color": "#1a1a2e", "fontWeight": "700"}),
                html.Small("Powered by FRED · yfinance · Claude Haiku", className="text-muted"),
            ]),
            dbc.Col(children=[html.Div(id="header-meta")], className="text-end"),
        ]),
        html.Hr(className="my-2"),

        # Tabs
        dcc.Tabs(id="main-tabs", value="overview", className="mb-3", children=[
            dcc.Tab(label="Overview",            value="overview"),
            dcc.Tab(label="Macro",               value="macro"),
            dcc.Tab(label="Labor",               value="labor"),
            dcc.Tab(label="Housing",             value="housing"),
            dcc.Tab(label="Markets",             value="markets"),
            dcc.Tab(label="Consumer & Business", value="consumer"),
            dcc.Tab(label="AI Analysis",         value="analysis"),
        ]),

        html.Div(id="tab-content"),
    ],
)


# ─── Tab content builder ──────────────────────────────────────────────────────

@app.callback(
    Output("tab-content", "children"),
    Output("header-meta", "children"),
    Output("snapshot-store", "data"),
    Input("refresh-interval", "n_intervals"),
    Input("main-tabs", "value"),
)
def render_tab(n_intervals, tab):
    from dashboard.data import (
        get_latest_analysis, get_analysis_history, get_last_fetch,
        get_series_for_chart, get_yield_curve_snapshot,
    )

    analysis = get_latest_analysis()
    fetch_log = get_last_fetch()
    snapshot = analysis["snapshot"] if analysis else {}

    # Header meta
    parts = []
    if fetch_log:
        parts.append(f"Data: {fetch_log['started_at'].strftime('%-m/%-d/%Y %-I:%M %p ET')}")
    if analysis:
        parts.append(f"Analysis: {analysis['date'].strftime('%-m/%-d/%Y')} ({analysis['analysis_model']})")
    header = html.Small(" | ".join(parts), className="text-muted") if parts else ""

    # ── Overview ──────────────────────────────────────────────────────────────
    if tab == "overview":
        composite = analysis["composite_health_score"] if analysis else None
        recession = analysis["recession_probability"] if analysis else None

        m = snapshot.get("macro", {})
        lb = snapshot.get("labor", {})
        yc = snapshot.get("yield_curve", {})
        mk = snapshot.get("markets", {})
        co = snapshot.get("consumer", {})
        ho = snapshot.get("housing", {})

        def _tl(label, value, good_condition, warn_text=""):
            color = "success" if good_condition else "danger"
            return dbc.Badge(f"{label}: {value}", color=color, className="me-1 mb-1", style={"fontSize": "12px"})

        traffic_lights = [
            _tl("GDP Growth", _fmt(m.get("real_gdp_growth_pct"), 1, "%"),  (m.get("real_gdp_growth_pct") or 0) > 1),
            _tl("CPI YoY",    _fmt(m.get("cpi_headline_yoy"), 1, "%"),     (m.get("cpi_headline_yoy") or 99) < 3.5),
            _tl("Fed Funds",  _fmt(m.get("fed_funds_rate"), 2, "%"),       True),
            _tl("Unemp U-3",  _fmt(lb.get("unemployment_u3"), 1, "%"),     (lb.get("unemployment_u3") or 99) < 5.0),
            _tl("Sahm Rule",  _fmt(lb.get("sahm_rule"), 2),               (lb.get("sahm_rule") or 99) < 0.5),
            _tl("10Y-2Y",     _fmt(yc.get("spread_10_2"), 2, " pp"),      (yc.get("spread_10_2") or -1) > 0),
            _tl("10Y-3M",     _fmt(yc.get("spread_10_3m"), 2, " pp"),     (yc.get("spread_10_3m") or -1) > 0),
            _tl("VIX",        _fmt(mk.get("vix"), 1),                     (mk.get("vix") or 99) < 20),
            _tl("Mortgage",   _fmt(ho.get("mortgage_rate_30y"), 2, "%"),   True),
            _tl("Sentiment",  _fmt(co.get("umich_sentiment"), 1),         (co.get("umich_sentiment") or 0) > 70),
        ]

        content = [
            dbc.Row([
                dbc.Col(dcc.Graph(figure=_gauge(composite, "Economic Health Score (0=worst, 100=best)")), md=4),
                dbc.Col(dcc.Graph(figure=_gauge(recession, "Recession Probability (%)",
                                                low_color=C_GREEN, high_color=C_RED)), md=4),
                dbc.Col([
                    html.H6("Indicator Traffic Lights", className="text-muted mb-2"),
                    html.Div(traffic_lights),
                    html.Hr(),
                    html.P(
                        "Green = healthy reading vs threshold | Red = concern. "
                        "See individual tabs for full time series.",
                        style={"fontSize": "11px"}, className="text-muted",
                    ),
                ], md=4),
            ], className="mb-3"),
        ]

        # Mini analysis excerpt on overview
        if analysis and analysis.get("analysis"):
            excerpt = analysis["analysis"][:400] + "..." if len(analysis["analysis"]) > 400 else analysis["analysis"]
            content.append(
                dbc.Alert([
                    html.Strong(f"AI Assessment ({analysis['date'].strftime('%-m/%-d/%Y')}): "),
                    excerpt,
                    html.Br(),
                    html.Small("→ See AI Analysis tab for full report.", className="text-muted"),
                ], color="info", className="mt-2", style={"fontSize": "13px"}),
            )

        return content, header, snapshot

    # ── Macro ─────────────────────────────────────────────────────────────────
    elif tab == "macro":
        gdp = get_series_for_chart("A191RL1Q225SBEA", days=3650)
        cpi = get_series_for_chart("CPIAUCSL", days=3650)
        core_cpi = get_series_for_chart("CPILFESL", days=3650)
        pce = get_series_for_chart("PCEPILFE", days=3650)
        fedfunds = get_series_for_chart("FEDFUNDS", days=3650)
        m2 = get_series_for_chart("M2SL", days=3650)
        trade = get_series_for_chart("BOPGSTB", days=3650)
        debt_gdp = get_series_for_chart("GFDEGDQ188S", days=3650)

        # YoY for CPI/PCE
        cpi_yoy = cpi.pct_change(12) * 100 if not cpi.empty else cpi
        core_yoy = core_cpi.pct_change(12) * 100 if not core_cpi.empty else core_cpi
        pce_yoy = pce.pct_change(12) * 100 if not pce.empty else pce

        content = [
            dbc.Row([
                dbc.Col(dcc.Graph(figure=_line_chart({"Real GDP Growth %": gdp}, "Real GDP Growth Rate (% annualized)")), md=6),
                dbc.Col(dcc.Graph(figure=_line_chart(
                    {"CPI YoY %": cpi_yoy, "Core CPI YoY %": core_yoy, "Core PCE YoY %": pce_yoy},
                    "Inflation — CPI & PCE Year-over-Year %",
                )), md=6),
            ]),
            dbc.Row([
                dbc.Col(dcc.Graph(figure=_line_chart({"Fed Funds Rate": fedfunds}, "Federal Funds Rate (%)")), md=6),
                dbc.Col(dcc.Graph(figure=_line_chart({"M2 ($B)": m2}, "M2 Money Supply ($B)")), md=6),
            ]),
            dbc.Row([
                dbc.Col(dcc.Graph(figure=_line_chart({"Trade Balance ($M)": trade}, "Trade Balance ($M)")), md=6),
                dbc.Col(dcc.Graph(figure=_line_chart({"Debt/GDP %": debt_gdp}, "Federal Debt to GDP (%)")), md=6),
            ]),
            *_build_indicator_notes(MACRO_INDICATOR_INFO, _macro_values(snapshot), "Macro"),
        ]
        return content, header, snapshot

    # ── Labor ─────────────────────────────────────────────────────────────────
    elif tab == "labor":
        u3 = get_series_for_chart("UNRATE", days=3650)
        u6 = get_series_for_chart("U6RATE", days=3650)
        payems = get_series_for_chart("PAYEMS", days=3650)
        icsa = get_series_for_chart("ICSA", days=3650)
        prime_lfpr = get_series_for_chart("LNS11300060", days=3650)
        civpart = get_series_for_chart("CIVPART", days=3650)
        openings = get_series_for_chart("JTSJOL", days=3650)
        quits = get_series_for_chart("JTSQUL", days=3650)
        hires = get_series_for_chart("JTSHIL", days=3650)
        layoffs = get_series_for_chart("JTSLDL", days=3650)
        sahm = get_series_for_chart("SAHMREALTIME", days=3650)

        from dashboard.data import get_series_for_chart as gsc
        from economy.indicators import get_beveridge_curve_data, compute_real_wage_growth

        beveridge = get_beveridge_curve_data(months=48)
        real_wage = compute_real_wage_growth()

        # Beveridge curve scatter
        bev_fig = go.Figure()
        if not beveridge.empty:
            bev_fig.add_trace(go.Scatter(
                x=beveridge["unrate"], y=beveridge["openings"],
                mode="markers+lines",
                marker={"color": list(range(len(beveridge))), "colorscale": "Blues", "size": 6},
                line={"color": C_GRAY, "width": 0.5},
                text=beveridge.index.strftime("%b %Y"),
                hovertemplate="Unemp: %{x:.1f}%<br>Openings: %{y:.0f}K<br>%{text}",
                name="",
            ))
        bev_fig.update_layout(**_PLOT_LAYOUT, height=350,
                              title="Beveridge Curve (36 months)",
                              xaxis_title="Unemployment Rate (%)",
                              yaxis_title="Job Openings (K)")

        # Sahm Rule with 0.5 threshold line
        sahm_fig = go.Figure()
        if not sahm.empty:
            sahm_fig.add_trace(go.Scatter(x=sahm.index, y=sahm.values, name="Sahm Rule",
                                          line={"color": C_PURPLE, "width": 1.8}))
            sahm_fig.add_hline(y=0.5, line_dash="dash", line_color=C_RED, line_width=1.5,
                               annotation_text="Recession trigger (0.50)")
        sahm_fig.update_layout(**_PLOT_LAYOUT, height=280, title="Sahm Rule Indicator")

        content = [
            dbc.Row([
                dbc.Col(dcc.Graph(figure=_line_chart(
                    {"U-3 Unemployment %": u3, "U-6 Unemployment %": u6},
                    "Unemployment Rate — U-3 vs U-6",
                )), md=6),
                dbc.Col(dcc.Graph(figure=_line_chart(
                    {"Initial Claims (K)": icsa},
                    "Initial Jobless Claims (weekly, thousands)",
                )), md=6),
            ]),
            dbc.Row([
                dbc.Col(dcc.Graph(figure=_line_chart(
                    {"Prime-Age LFPR (25-54)": prime_lfpr, "Overall LFPR": civpart},
                    "Labor Force Participation Rate (%)",
                )), md=6),
                dbc.Col(dcc.Graph(figure=_line_chart(
                    {"Job Openings (K)": openings, "Hires (K)": hires, "Quits (K)": quits, "Layoffs (K)": layoffs},
                    "JOLTS — Openings, Hires, Quits, Layoffs (thousands)",
                )), md=6),
            ]),
            dbc.Row([
                dbc.Col(dcc.Graph(figure=bev_fig), md=6),
                dbc.Col(dcc.Graph(figure=sahm_fig), md=6),
            ]),
            dbc.Row([
                dbc.Col(
                    dbc.Alert(
                        f"Real wage growth: {_fmt(real_wage, 2, ' pp')} "
                        "(Average Hourly Earnings YoY minus CPI YoY). "
                        "Positive = workers gaining purchasing power.",
                        color="success" if (real_wage or -1) > 0 else "warning",
                        style={"fontSize": "13px"},
                    ),
                ),
            ]),
            *_build_indicator_notes(LABOR_INDICATOR_INFO, _labor_values(snapshot), "Labor"),
        ]
        return content, header, snapshot

    # ── Housing ───────────────────────────────────────────────────────────────
    elif tab == "housing":
        starts = get_series_for_chart("HOUST", days=3650)
        permits = get_series_for_chart("PERMIT", days=3650)
        case_shiller = get_series_for_chart("CSUSHPISA", days=3650)
        mortgage = get_series_for_chart("MORTGAGE30US", days=3650)

        cs_yoy = case_shiller.pct_change(12) * 100 if not case_shiller.empty else case_shiller

        content = [
            dbc.Row([
                dbc.Col(dcc.Graph(figure=_line_chart(
                    {"Housing Starts (K)": starts, "Building Permits (K)": permits},
                    "Housing Starts & Permits (thousands, annualized)",
                )), md=6),
                dbc.Col(dcc.Graph(figure=_line_chart(
                    {"30Y Mortgage Rate (%)": mortgage},
                    "30-Year Fixed Mortgage Rate (%)",
                )), md=6),
            ]),
            dbc.Row([
                dbc.Col(dcc.Graph(figure=_line_chart(
                    {"Case-Shiller Index": case_shiller},
                    "Case-Shiller National Home Price Index",
                )), md=6),
                dbc.Col(dcc.Graph(figure=_line_chart(
                    {"Case-Shiller YoY %": cs_yoy},
                    "Case-Shiller Home Price YoY %",
                )), md=6),
            ]),
            *_build_indicator_notes(HOUSING_INDICATOR_INFO, _housing_values(snapshot), "Housing"),
        ]
        return content, header, snapshot

    # ── Markets ───────────────────────────────────────────────────────────────
    elif tab == "markets":
        sp500 = get_series_for_chart("^GSPC", days=3650)
        rut = get_series_for_chart("^RUT", days=3650)
        vix = get_series_for_chart("^VIX", days=3650)
        gold = get_series_for_chart("GC=F", days=3650)
        crude = get_series_for_chart("CL=F", days=3650)
        copper = get_series_for_chart("HG=F", days=3650)

        yc = get_yield_curve_snapshot()

        # Yield curve bar chart (current snapshot)
        yc_fig = go.Figure()
        maturities = ["3M", "2Y", "10Y", "30Y"]
        yields = [yc.get("dgs3mo"), yc.get("dgs2"), yc.get("dgs10"), yc.get("dgs30")]
        colours_yc = [C_RED if (y or 0) < (yc.get("dgs10") or 0) else C_BLUE for y in yields]
        yc_fig.add_trace(go.Bar(x=maturities, y=yields, marker_color=colours_yc, name="Yield"))
        yc_fig.update_layout(**_PLOT_LAYOUT, height=280, title="Yield Curve (current snapshot, %)",
                             xaxis_title="Maturity", yaxis_title="Yield (%)")
        if yc.get("inverted_10_3m"):
            yc_fig.add_annotation(text="⚠ 10Y-3M INVERTED", xref="paper", yref="paper",
                                  x=0.5, y=0.95, showarrow=False,
                                  font={"color": C_RED, "size": 13})

        # Yield spreads time series
        dgs10_s = get_series_for_chart("DGS10", days=3650)
        dgs2_s = get_series_for_chart("DGS2", days=3650)
        dgs3mo_s = get_series_for_chart("DGS3MO", days=3650)
        import pandas as pd
        spread_10_2 = (dgs10_s - dgs2_s).dropna()
        spread_10_3m = (dgs10_s - dgs3mo_s).dropna()

        spread_fig = go.Figure()
        spread_fig.add_trace(go.Scatter(x=spread_10_2.index, y=spread_10_2.values,
                                        name="10Y-2Y Spread", line={"color": C_BLUE, "width": 1.5}))
        spread_fig.add_trace(go.Scatter(x=spread_10_3m.index, y=spread_10_3m.values,
                                        name="10Y-3M Spread", line={"color": C_ORANGE, "width": 1.5}))
        spread_fig.add_hline(y=0, line_dash="dash", line_color=C_RED, line_width=1)
        spread_fig.update_layout(**_PLOT_LAYOUT, height=300,
                                 title="Yield Curve Spreads (pp) — Inversion = Recession Risk",
                                 yaxis_title="Spread (pp)")

        # Copper/gold ratio
        cu_au = (copper / gold * 100).dropna() if (not copper.empty and not gold.empty) else None

        content = [
            dbc.Row([
                dbc.Col(dcc.Graph(figure=_line_chart(
                    {"S&P 500": sp500, "Russell 2000": rut},
                    "S&P 500 & Russell 2000",
                )), md=6),
                dbc.Col(dcc.Graph(figure=_line_chart(
                    {"VIX": vix}, "VIX Volatility Index"
                )), md=6),
            ]),
            dbc.Row([
                dbc.Col(dcc.Graph(figure=yc_fig), md=4),
                dbc.Col(dcc.Graph(figure=spread_fig), md=8),
            ]),
            dbc.Row([
                dbc.Col(dcc.Graph(figure=_line_chart(
                    {"WTI Crude ($/bbl)": crude, "Gold ($/oz ÷10)": gold / 10},
                    "WTI Crude Oil & Gold",
                )), md=6),
                dbc.Col(dcc.Graph(figure=_line_chart(
                    {"Copper/Gold Ratio (×100)": cu_au},
                    "Copper/Gold Ratio — Economic Activity Proxy",
                )), md=6) if cu_au is not None else dbc.Col(),
            ]),
            *_build_indicator_notes(MARKETS_INDICATOR_INFO, _markets_values(snapshot), "Markets"),
        ]
        return content, header, snapshot

    # ── Consumer & Business ───────────────────────────────────────────────────
    elif tab == "consumer":
        umich = get_series_for_chart("UMCSENT", days=3650)
        retail = get_series_for_chart("RSAFS", days=3650)
        savings = get_series_for_chart("PSAVERT", days=3650)
        indpro = get_series_for_chart("INDPRO", days=3650)
        tcu = get_series_for_chart("TCU", days=3650)

        retail_yoy = retail.pct_change(12) * 100 if not retail.empty else retail
        indpro_yoy = indpro.pct_change(12) * 100 if not indpro.empty else indpro

        content = [
            dbc.Row([
                dbc.Col(dcc.Graph(figure=_line_chart(
                    {"UMich Sentiment": umich}, "University of Michigan Consumer Sentiment"
                )), md=6),
                dbc.Col(dcc.Graph(figure=_line_chart(
                    {"Retail Sales YoY %": retail_yoy}, "Retail Sales YoY %"
                )), md=6),
            ]),
            dbc.Row([
                dbc.Col(dcc.Graph(figure=_line_chart(
                    {"Personal Savings Rate %": savings}, "Personal Savings Rate (%)"
                )), md=6),
                dbc.Col(dcc.Graph(figure=_line_chart(
                    {"Industrial Production YoY %": indpro_yoy, "Capacity Utilization %": tcu},
                    "Industrial Production YoY % & Capacity Utilization",
                )), md=6),
            ]),
            *_build_indicator_notes(CONSUMER_INDICATOR_INFO, _consumer_values(snapshot), "Consumer & Business"),
        ]
        return content, header, snapshot

    # ── AI Analysis ───────────────────────────────────────────────────────────
    elif tab == "analysis":
        from dashboard.data import get_analysis_history

        history = get_analysis_history(days=90)
        history_dates = [h["date"] for h in history]
        composite_hist = [h["composite_health_score"] for h in history]
        recession_hist = [h["recession_probability"] for h in history]

        # History chart
        hist_fig = go.Figure()
        if history_dates:
            hist_fig.add_trace(go.Scatter(
                x=history_dates, y=composite_hist,
                name="Health Score", line={"color": C_BLUE, "width": 2},
                yaxis="y1",
            ))
            hist_fig.add_trace(go.Scatter(
                x=history_dates, y=recession_hist,
                name="Recession Prob %", line={"color": C_RED, "width": 2, "dash": "dash"},
                yaxis="y2",
            ))
        hist_fig.update_layout(
            **_PLOT_LAYOUT,
            height=280,
            title="90-Day History — Health Score & Recession Probability",
            yaxis={"title": "Health Score (0-100)", "side": "left"},
            yaxis2={"title": "Recession Prob (%)", "side": "right", "overlaying": "y"},
        )

        # Analysis card
        analysis = get_latest_analysis()
        if analysis:
            snap = analysis.get("snapshot", {})
            model_badge = dbc.Badge(
                analysis["analysis_model"].upper(), color="primary", className="ms-2"
            )
            sonnet_btn = dbc.Button(
                "Re-run with Sonnet", id="run-sonnet-btn", color="secondary",
                outline=True, size="sm", className="ms-2",
            )
            analysis_card = dbc.Card([
                dbc.CardHeader([
                    html.Strong(f"Economy Assessment — {analysis['date'].strftime('%-m/%-d/%Y')}"),
                    model_badge,
                    sonnet_btn,
                ]),
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col([
                            html.P(analysis["analysis"], style={"lineHeight": "1.7", "fontSize": "14px"}),
                        ], md=8),
                        dbc.Col([
                            _stat_card("Health Score", _fmt(analysis["composite_health_score"], 1) + " / 100", ""),
                            _stat_card("Recession Probability", _fmt(analysis["recession_probability"], 1) + "%", ""),
                            _stat_card("10Y-2Y Spread", _fmt(snap.get("yield_curve", {}).get("spread_10_2"), 2, " pp"), ""),
                            _stat_card("Sahm Rule", _fmt(snap.get("labor", {}).get("sahm_rule"), 2), ""),
                        ], md=4),
                    ]),
                ]),
            ], className="mb-3")
        else:
            analysis_card = dbc.Alert(
                [
                    html.Strong("No analysis available."),
                    html.Br(),
                    "Run ",
                    html.Code("python manage.py run_analysis"),
                    " to generate the first assessment.",
                ],
                color="info",
            )

        sonnet_result = html.Div(id="sonnet-result")

        content = [
            analysis_card,
            sonnet_result,
            dcc.Graph(figure=hist_fig),
        ]
        return content, header, snapshot

    return [], header, snapshot


# ─── On-demand Sonnet re-run ──────────────────────────────────────────────────

@app.callback(
    Output("sonnet-result", "children"),
    Input("run-sonnet-btn", "n_clicks"),
    prevent_initial_call=True,
)
def run_sonnet(n_clicks):
    if not n_clicks:
        return dash.no_update
    from economy.analysis import generate_analysis
    result = generate_analysis(model="claude-sonnet-4-6")
    if result:
        return dbc.Alert(
            ["Sonnet analysis complete — refresh the page to see it.", html.Br(),
             html.Small(result[:300] + "..." if len(result) > 300 else result)],
            color="success", dismissable=True, style={"fontSize": "13px"},
        )
    return dbc.Alert("Sonnet analysis failed — check logs.", color="danger", dismissable=True)
