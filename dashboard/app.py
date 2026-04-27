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
                {"range": [0, max_val * 0.33], "color": low_color + "33"},
                {"range": [max_val * 0.33, max_val * 0.66], "color": C_YELLOW + "33"},
                {"range": [max_val * 0.66, max_val], "color": high_color + "33"},
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
