# US Economy Health Tracker — Deployment Runbook

Domain: `econ-tracker.3rdplaces.io`  
Port: `8095`  
User: `geoskimoto`  
Server: Hostinger VPS — Ubuntu + CloudPanel

---

## Pre-flight checklist

Before running any steps below, verify `.env` is filled in:

```
DJANGO_SECRET_KEY=        # already generated and set
DJANGO_DEBUG=False        # already set
DJANGO_ALLOWED_HOSTS=econ-tracker.3rdplaces.io,localhost,127.0.0.1  # already set

FRED_API_KEY=             # fred.stlouisfed.org → My Account → API Keys (free)
ANTHROPIC_API_KEY=        # console.anthropic.com → API Keys
```

---

## Step 1 — DNS A record

In your DNS provider (Hostinger), create:

```
Type: A
Name: econ-tracker
Value: <your VPS IP>
TTL: 300
```

Verify propagation before proceeding:

```bash
dig econ-tracker.3rdplaces.io +short
```

Should return your VPS IP. Typically propagates within 5 minutes.

---

## Step 2 — Pull the repo

```bash
cd /home/geoskimoto/projects
git clone git@github.com:geoskimoto/us-econ-health-tracker.git current_stock_of_econ
cd current_stock_of_econ
```

If the directory already exists (you've been developing here), just make sure it's up to date:

```bash
cd /home/geoskimoto/projects/current_stock_of_econ
git pull origin main
```

---

## Step 3 — Virtualenv and dependencies

```bash
cd /home/geoskimoto/projects/current_stock_of_econ
python3.12 -m venv venv
venv/bin/pip install -r requirements.txt
```

---

## Step 4 — Configure .env

Copy the example and fill in your keys:

```bash
cp .env.example .env
nano .env
```

Set:
- `FRED_API_KEY` — from fred.stlouisfed.org (free account, instant)
- `ANTHROPIC_API_KEY` — from console.anthropic.com

---

## Step 5 — Database migrations

```bash
source venv/bin/activate
python manage.py migrate
```

---

## Step 6 — Seed series definitions

Populates the 57 `EconomicSeries` records (FRED + yfinance metadata). Safe to re-run.

```bash
python manage.py seed_series
```

Expected output: `seed_series complete: 57 created, 0 updated (57 total).`

---

## Step 7 — Collect static files

```bash
python manage.py collectstatic --noinput
```

Static files land in `staticfiles/` — served directly by nginx.

---

## Step 8 — Install nginx config

```bash
sudo cp deploy/econ-tracker.3rdplaces.io.conf \
        /etc/nginx/sites-enabled/econ-tracker.3rdplaces.io.conf

sudo nginx -t          # must return "syntax is ok" and "test is successful"
sudo systemctl reload nginx
```

---

## Step 9 — SSL certificate

DNS must be propagated before this step or it will fail.

```bash
sudo clpctl lets-encrypt:install:certificate \
     --domainName=econ-tracker.3rdplaces.io
```

This writes the cert/key to `/etc/nginx/ssl-certificates/` and reloads nginx automatically.

---

## Step 10 — Install and start systemd service

```bash
sudo cp deploy/econ-dashboard.service \
        /etc/systemd/system/econ-dashboard.service

sudo systemctl daemon-reload
sudo systemctl enable econ-dashboard
sudo systemctl start econ-dashboard
sudo systemctl status econ-dashboard
```

Expected: `Active: active (running)`. If it fails, see Troubleshooting below.

---

## Step 11 — Initial data fetch

First run pulls 12 years of history for all 57 series. Takes 3–8 minutes depending on FRED API response times. The diskcache means subsequent runs are fast (only new data is fetched).

```bash
python manage.py fetch_data
```

Expected output:
```
Starting data fetch...
Fetch complete: 57 series fetched, 0 failed, XXXXX new points.
```

If a few series fail (usually yfinance timeouts), re-run — they'll be retried.

---

## Step 12 — First AI analysis

```bash
python manage.py run_analysis
```

Expected: prints the first 200 characters of the Haiku assessment and saves it to the DB.

Visit `https://econ-tracker.3rdplaces.io` — the dashboard should be live with data.

---

## Step 13 — Verify the dashboard

Open `https://econ-tracker.3rdplaces.io` and confirm:

- [ ] Overview tab loads with composite health score gauge
- [ ] Macro tab shows GDP and inflation charts
- [ ] Labor tab shows unemployment and JOLTS charts
- [ ] AI Analysis tab shows today's Haiku assessment
- [ ] No 404s on static files (JS, CSS)

---

## Ongoing operations

| Task | Command |
|---|---|
| Restart service | `sudo systemctl restart econ-dashboard` |
| View live logs | `sudo journalctl -u econ-dashboard -f` |
| Manual data fetch | `python manage.py fetch_data` |
| Manual Haiku analysis | `python manage.py run_analysis` |
| Manual Sonnet analysis | `python manage.py run_analysis --model sonnet` |
| Re-seed series (after updates) | `python manage.py seed_series` |
| Collect static after code update | `python manage.py collectstatic --noinput` |
| Deploy code update | `git pull && python manage.py migrate && python manage.py collectstatic --noinput && sudo systemctl restart econ-dashboard` |

---

## Scheduled jobs

APScheduler starts automatically with the Django process (wired in `economy/apps.py`).

| Time (ET, weekdays) | Job |
|---|---|
| 6:30 AM | `fetch_data` — pulls all FRED + yfinance series |
| 7:00 AM | `run_analysis` — Claude Haiku daily assessment |

No cron job or Celery required.

---

## Troubleshooting

**Service won't start:**
```bash
sudo journalctl -u econ-dashboard -n 50 --no-pager
```
Common causes: missing `.env` variable, port 8095 already in use, wrong venv path.

Check port conflict:
```bash
sudo ss -tlnp | grep 8095
```

**Dashboard is blank / "No data available":**  
Run `python manage.py fetch_data` with venv active. Check that `FRED_API_KEY` is set correctly.

**AI Analysis tab shows nothing:**  
Run `python manage.py run_analysis`. Check `ANTHROPIC_API_KEY` is set. Check logs for API errors:
```bash
sudo journalctl -u econ-dashboard -f | grep analysis
```

**Static files returning 404:**  
Re-run `python manage.py collectstatic --noinput`.  
Verify the nginx alias path matches `STATIC_ROOT` in settings (`staticfiles/`).

**FRED API errors on fetch:**  
- Verify `FRED_API_KEY` in `.env` is correct (no extra spaces)
- FRED has rate limits (~120 requests/min) — the fetcher runs series sequentially, should be fine
- Temporary FRED outages: re-run `python manage.py fetch_data` — diskcache means successful series aren't re-fetched

**yfinance fetch failures:**  
yfinance occasionally has connection issues. Re-run `fetch_data` — FRED series that already succeeded are cached and skipped. Only failed yfinance series are retried.

**Scheduler not running (no daily updates):**  
```bash
sudo journalctl -u econ-dashboard | grep -i "scheduler\|fetch\|analysis"
```
The scheduler starts with gunicorn's `--preload` flag. If logs show it's not firing, restart the service:
```bash
sudo systemctl restart econ-dashboard
```

**SSL certificate renewal:**  
Let's Encrypt certificates auto-renew via CloudPanel. Manual renewal if needed:
```bash
sudo clpctl lets-encrypt:install:certificate --domainName=econ-tracker.3rdplaces.io
```
