# Consumer Product Trend Monitor

A local review tool that tracks three separate signals per consumer product (**product attention**,
**price response**, **retail interest**) plus earnings timing, maps them to a stage with an explicit
rule table, and logs every alert so the rules can be scored later. It never trades and makes no
claim that the signal has alpha.

Everything runs on seeded, synthetic demo data with **zero API keys and zero paid services**.

> **Build status:** steps 1–9 of the build prompt are done (skeleton, config, calendar, models and
> migration, six demo adapters, ingest with health recording, signal calculators, stage engine,
> scan with alerts and change detection, CLI, API, and the Watchlist, product Detail and Review feed
> screens). Replay/evaluate, the Alerts and Admin screens, and the live stubs come in steps 10–12.

## Requirements

- Python 3.12 or newer. macOS ships Python 3.9, which is too old: install a newer one with
  [Homebrew](https://brew.sh) (`brew install python@3.12`) and use `python3.12` below.
- Node.js 18 or newer (with npm): `brew install node` on macOS.

## Install and run — macOS / Linux

```bash
# 1. Backend
cd backend
python3.12 -m venv .venv          # macOS: not plain python3, which is 3.9
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"

# 2. Seed the demo (creates data/ctm.db, runs migrations, loads 400 days of synthetic history)
ctm seed

# 3. Scan as of the last completed US trading session
ctm scan

# 4. Start the API (http://127.0.0.1:8000, docs at /docs)
ctm serve
```

In a second terminal:

```bash
cd frontend
npm install
npm run dev          # http://127.0.0.1:5173
```

Click any product name on the watchlist to open its Detail page. **Review feed** (top nav) lists
today's entry, early-recognition and exit cases with the reason each one fired, what changed since
the last scan, and buttons to record your decision (acted / passed / exited + a note).

Next time, you only need `cd backend && source .venv/bin/activate && ctm serve` in one terminal and
`cd frontend && npm run dev` in another.

## Install and run — Windows (PowerShell)

```powershell
# 1. Backend
cd backend
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# 2-4. Seed, scan, serve
ctm seed
ctm scan
ctm serve
```

In a second PowerShell window:

```powershell
cd frontend
npm install
npm run dev
```

Then open http://127.0.0.1:5173.

## Commands

| Command | API | What it does |
| --- | --- | --- |
| `ctm seed [--reset]` | — | Create the DB, run migrations, load the demo catalog and demo observations. `--reset` deletes the DB and re-anchors the demo to today. |
| `ctm ingest [--source S] [--as-of D]` | `POST /api/ingest` | Run every enabled adapter; write observations and `source_runs`. |
| `ctm scan [--as-of D]` | `POST /api/scan` | Compute statuses, stages and alerts as of D (default: last completed US session). |
| `ctm daily [--as-of D]` | `POST /api/daily` | Backup, then ingest, then scan. The UI's **Run daily** button calls the same code. |
| `ctm backup` | — | Copy the SQLite file to `backups/` with a timestamp. |
| `ctm serve` | — | Start the API on 127.0.0.1:8000. |
| `ctm openapi` | — | Write `frontend/openapi.json`; `npm run gen:api` regenerates the typed client from it. |

`ctm replay` and `ctm evaluate` arrive with step 10.

## What the demo shows

The demo is anchored to the last completed US trading session at seed time (stored in
`data/demo_state.json`; set `demo.anchor_date` in config to pin it). On that date:

| # | Product | Expected |
| --- | --- | --- |
| 1 | CROX · Charm clog collab | `entry_review` (two sources, price flat, retail quiet, 70 days to earnings) |
| 2 | ONON · Cloudtilt trainer | `exit_review` (price early_move on volume, ticker search and cashtags rising) |
| 3 | ELF · Glow reviver lip oil | `early_recognition` |
| 4 | YETI · Hopper backpack cooler | attention `seasonal`, no alert |
| 5 | SONO · Ace headphones | one-day search spike → attention `normal` |
| 6 | BOOT · Western work boot | cashtags up ~4x from few accounts → retail `rising`, never `elevated` |
| 7 | BIRK · Boston clog suede | price feed 6 days stale → `data_gap`, no entry |
| 8 | WRBY · Contact lens subscription | `entry_review` with `single_source` |
| 9 | COTY · Burberry Goddess fragrance | `entry_review`, reporting quarter closed |
| 10 | OLPX · No.4 bond shampoo | `watch` (150 days to earnings, hidden by the default filter) |
| 11 | FIVE · both products | earnings `unknown` (date in the past) |
| 12 | everything else | `normal`, no alert |

The watchlist defaults to the 6–14 week earnings window; untick the box to see all 26 products.

## Schedule

Run `ctm daily` at 08:30 Australia/Sydney, Tuesday to Saturday (after the US close).

**macOS / Linux cron** (`crontab -e`; `CRON_TZ` is honoured by cronie/Linux; on macOS the machine's
local time zone is used, so set the Mac to Sydney time or adjust the hour):

```cron
CRON_TZ=Australia/Sydney
30 8 * * 2-6  cd /path/to/signals/backend && .venv/bin/ctm daily >> ../data/logs/cron.log 2>&1
```

**Windows Task Scheduler:**

```powershell
schtasks /Create /TN "Trend Monitor daily" /SC WEEKLY /D TUE,WED,THU,FRI,SAT /ST 08:30 `
  /TR "C:\path\to\signals\backend\.venv\Scripts\ctm.exe daily"
```

A missed day is harmless: the next run ingests any gap and scans as of the last completed session.

There is also an optional in-process scheduler (APScheduler) for an always-on machine: set
`schedule.in_process_enabled: true` in `config/settings.yaml` and keep `ctm serve` running.

## Configuration

Every threshold, window, stage rule and source setting is in `config/settings.yaml`. Each scan
validates it (an invalid file stops the scan with a readable message and changes nothing), hashes
it and stores it in `config_versions`. Alerts record the hash of the config that produced them and
are never rewritten. Secrets go in `.env` (see `.env.example`); they are never stored in the database
or logged.

## Security

There is no authentication, so the API binds to `127.0.0.1` only. If it ever runs on another
machine, put it behind a private network such as Tailscale; do not expose it to the internet.

## Tests

```bash
cd backend
pytest
```

Covers each status rule on fixture series, the stage engine (order, `data_gap` first, exit before
entry, entry never on unknown inputs), the 12 seeded scenarios end to end, zero outbound network
calls in demo mode, alert immutability across re-scans and config changes, and ingest fault isolation.

## Layout

```
backend/app/
  api/         FastAPI routers and response models (no business logic)
  core/        config loading + hashing, trading calendar, paths, logging
  db/          SQLAlchemy models, session, Alembic migrations
  sources/     one file per adapter, registry.py, base.py; demo/ holds the synthetic universe
  signals/     health, attention, price, retail, earnings, point-in-time observation store
  stages/      rule engine reading config
  pipeline/    seed, ingest, scan, jobs (shared by CLI, API and scheduler)
  cli.py
frontend/src/
  api/         typed client (types generated from OpenAPI)
  components/  badges, layout, TimeChart (shared time axis + crosshair)
  pages/       Watchlist, Detail, Feed (Alerts, Admin to follow)
config/settings.yaml
DECISIONS.md
```
