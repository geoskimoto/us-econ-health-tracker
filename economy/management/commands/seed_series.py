"""
Management command: seed_series
Populates EconomicSeries definitions. Run once after initial migrations.
Usage: python manage.py seed_series
"""
from django.core.management.base import BaseCommand
from economy.models import EconomicSeries

SERIES = [
    # ── Macro ──────────────────────────────────────────────────────────────────
    ("A191RL1Q225SBEA", "Real GDP Growth Rate", "macro", "fred", "percent", "quarterly", False),
    ("GDPC1",           "Real GDP",             "macro", "fred", "billions_chained_2017", "quarterly", False),
    ("CPIAUCSL",        "CPI Headline",         "macro", "fred", "index", "monthly", False),
    ("CPILFESL",        "CPI Core",             "macro", "fred", "index", "monthly", False),
    ("CPIUFDSL",        "CPI Food",             "macro", "fred", "index", "monthly", False),
    ("CPIENGSL",        "CPI Energy",           "macro", "fred", "index", "monthly", False),
    ("PCEPILFE",        "Core PCE",             "macro", "fred", "index", "monthly", False),
    ("PPIACO",          "PPI All Commodities",  "macro", "fred", "index", "monthly", False),
    ("T5YIE",           "5Y Inflation Breakeven","macro","fred", "percent", "daily",   False),
    ("T10YIE",          "10Y Inflation Breakeven","macro","fred","percent", "daily",   False),
    ("FEDFUNDS",        "Fed Funds Rate",       "macro", "fred", "percent", "monthly", False),
    ("M2SL",            "M2 Money Supply",      "macro", "fred", "billions", "monthly", False),
    ("WALCL",           "Fed Balance Sheet",    "macro", "fred", "millions", "weekly",  False),
    ("BOPGSTB",         "Trade Balance",        "macro", "fred", "millions", "monthly", False),
    ("DTWEXBGS",        "USD Broad Dollar Index","macro","fred", "index",   "daily",   False),
    ("MTSDS133FMS",     "Federal Surplus/Deficit","macro","fred","millions","monthly", False),
    ("GFDEGDQ188S",     "Federal Debt to GDP",  "macro", "fred", "percent", "quarterly", False),
    # Treasury yields
    ("DGS3MO",  "3M Treasury Yield",  "macro", "fred", "percent", "daily", False),
    ("DGS2",    "2Y Treasury Yield",  "macro", "fred", "percent", "daily", False),
    ("DGS10",   "10Y Treasury Yield", "macro", "fred", "percent", "daily", False),
    ("DGS30",   "30Y Treasury Yield", "macro", "fred", "percent", "daily", False),
    # ── Labor ──────────────────────────────────────────────────────────────────
    ("UNRATE",          "Unemployment Rate U-3",        "labor", "fred", "percent",   "monthly", True),
    ("U6RATE",          "Unemployment Rate U-6",        "labor", "fred", "percent",   "monthly", True),
    ("PAYEMS",          "Nonfarm Payrolls",             "labor", "fred", "thousands", "monthly", False),
    ("ICSA",            "Initial Jobless Claims",       "labor", "fred", "thousands", "weekly",  True),
    ("CCSA",            "Continuing Claims",            "labor", "fred", "thousands", "weekly",  True),
    ("CIVPART",         "Labor Force Participation",    "labor", "fred", "percent",   "monthly", False),
    ("LNS11300060",     "Prime-Age LFPR (25-54)",       "labor", "fred", "percent",   "monthly", False),
    ("JTSJOL",          "JOLTS Job Openings",           "labor", "fred", "thousands", "monthly", False),
    ("JTSHIL",          "JOLTS Hires",                  "labor", "fred", "thousands", "monthly", False),
    ("JTSQUL",          "JOLTS Quits",                  "labor", "fred", "thousands", "monthly", False),
    ("JTSLDL",          "JOLTS Layoffs",                "labor", "fred", "thousands", "monthly", True),
    ("CES0500000003",   "Avg Hourly Earnings",          "labor", "fred", "dollars",   "monthly", False),
    ("ECIALLCIV",       "Employment Cost Index",        "labor", "fred", "index",     "quarterly",False),
    ("LNS13025703",     "Long-Term Unemployment (27+wk)","labor","fred","thousands", "monthly", True),
    ("OPHNFB",          "Labor Productivity",           "labor", "fred", "index",     "quarterly",False),
    ("ULCNFB",          "Unit Labor Costs",             "labor", "fred", "index",     "quarterly",False),
    ("SAHMREALTIME",    "Sahm Rule Indicator",          "labor", "fred", "percent",   "monthly", True),
    # ── Housing ────────────────────────────────────────────────────────────────
    ("HOUST",           "Housing Starts",               "housing","fred","thousands","monthly", False),
    ("PERMIT",          "Building Permits",             "housing","fred","thousands","monthly", False),
    ("CSUSHPISA",       "Case-Shiller Home Price Index","housing","fred","index",    "monthly", False),
    ("MORTGAGE30US",    "30Y Fixed Mortgage Rate",      "housing","fred","percent",  "weekly",  True),
    ("RHORUSQ156N",     "Homeowner Vacancy Rate",       "housing","fred","percent",  "quarterly",True),
    # ── Consumer & Business ────────────────────────────────────────────────────
    ("UMCSENT",         "UMich Consumer Sentiment",     "consumer","fred","index",   "monthly", False),
    ("RSAFS",           "Retail Sales",                 "consumer","fred","millions","monthly", False),
    ("PSAVERT",         "Personal Savings Rate",        "consumer","fred","percent", "monthly", False),
    ("TOTALSL",         "Consumer Credit Outstanding",  "consumer","fred","millions","monthly", False),
    ("INDPRO",          "Industrial Production Index",  "consumer","fred","index",   "monthly", False),
    ("TCU",             "Capacity Utilization",         "consumer","fred","percent", "monthly", False),
    ("DPCERA3M086SBEA", "Real Personal Consumption",   "consumer","fred","index",   "monthly", False),
    # ── Markets (yfinance) ─────────────────────────────────────────────────────
    ("^GSPC",  "S&P 500",         "markets", "yfinance", "index",   "daily", False),
    ("^RUT",   "Russell 2000",    "markets", "yfinance", "index",   "daily", False),
    ("^NDX",   "Nasdaq 100",      "markets", "yfinance", "index",   "daily", False),
    ("^VIX",   "VIX Volatility",  "markets", "yfinance", "index",   "daily", True),
    ("GC=F",   "Gold Futures",    "markets", "yfinance", "usd_oz",  "daily", False),
    ("CL=F",   "WTI Crude Oil",   "markets", "yfinance", "usd_bbl", "daily", False),
    ("HG=F",   "Copper Futures",  "markets", "yfinance", "usd_lb",  "daily", False),
]


class Command(BaseCommand):
    help = "Populate EconomicSeries definitions (run once after initial migrations)."

    def handle(self, *args, **options):
        created = updated = 0
        for (sid, name, cat, source, units, freq, invert) in SERIES:
            _, was_created = EconomicSeries.objects.update_or_create(
                series_id=sid,
                defaults={
                    "name": name,
                    "category": cat,
                    "source": source,
                    "units": units,
                    "frequency": freq,
                    "invert_for_score": invert,
                    "is_active": True,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"seed_series complete: {created} created, {updated} updated ({created + updated} total)."
            )
        )
