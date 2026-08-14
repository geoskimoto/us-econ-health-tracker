# Economy Tracker — Project Context

A Django + Plotly Dash macroeconomic dashboard that tracks ~40 economic indicators, computes a composite health score and recession probability, and generates daily AI narratives using Claude.

---

## Cross-App Data Dependency

The **fundamental-analysis-alert-system** (`/home/geoskimoto/projects/fundamental-analysis-alert-system`) reads this app's SQLite database **read-only** to fetch macro context for its AI narrative generation.

- **DB path:** `/home/geoskimoto/projects/economy_tracker/db.sqlite3`
- **Table read:** `economy_dailyanalysis` — latest row only
- **Fields consumed:** `composite_health_score`, `recession_probability`, `snapshot_json`, `date`

Do not rename or restructure these fields without updating `analysis/market_context.py` in the fundamental-analysis-alert-system. If this app ever moves to a separate server, a `/api/latest/` JSON endpoint should be added here and the FAAS app updated to call it over HTTP.
