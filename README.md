# SocialArb

**[socialarb.trade](https://socialarb.trade)**

SocialArb watches consumer products for a gap between **product buzz** (search and social attention),
the **stock's price** (versus a benchmark) and **retail chatter** about the ticker. The idea under test:
buzz about a product shows up before the stock moves and before retail traders start talking about it.

It is a review tool for a small team, not a trading bot. Each morning it shows:

- **Entry signals** (buy-side): buzz is up, the price hasn't moved yet, chatter is quiet, and earnings
  are 6–14 weeks out.
- **Early movers**: buzz is up and the price has started to follow.
- **Exit signals** (sell-side): after a buzz run, the price has moved and retail chatter has caught up.

The three signals are never blended into one score. Every signal is logged unchanged and later scored
against what the stock actually did, so the rules can be judged and tuned.

Everything runs locally on seeded, **synthetic demo data with zero API keys and zero paid services**.
Each data source is a plug-in that can later be switched to a live provider.

## Requirements

- Python 3.12 or newer. macOS ships Python 3.9, which is too old: install one with
  [Homebrew](https://brew.sh) (`brew install python@3.12`) and use `python3.12` below.
- Node.js 18 or newer with npm (`brew install node` on macOS).

## Install and first run: macOS / Linux

```bash
# Backend
cd backend
python3.12 -m venv .venv          # macOS: not plain python3, which is 3.9
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"

socialarb seed       # creates data/socialarb.db and 400 days of synthetic history (~10 s)
socialarb scan       # today's statuses, signals and alerts
socialarb replay     # re-runs the scan for every past trading day (~1 min)
socialarb evaluate   # scores every signal against what the stock did next
socialarb serve      # API on http://127.0.0.1:8000 (interactive docs at /docs)
```

In a second terminal:

```bash
cd frontend
npm install
npm run dev          # open http://127.0.0.1:5173
```

## Install and first run: Windows (PowerShell)

```powershell
cd backend
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
socialarb seed
socialarb scan
socialarb replay
socialarb evaluate
socialarb serve
```

In a second PowerShell window: `cd frontend`, `npm install`, `npm run dev`, then open
http://127.0.0.1:5173.

## Accounts

Every screen needs a signed-in account. The **first person to open the app creates the owner account**
(an admin). After that, sign-up is invite-only:

1. An admin opens **Data & settings → Team → Invites**, optionally types the person's email (the invite
   then only works for that address), picks Member or Admin and an expiry, and presses **Create invite**.
2. The admin sends the link that appears (`…/signup?invite=XXXXX-XXXXX-XXXXX`). It is shown once.
3. The person opens the link, enters a name, email and password, and is signed in.

| Role | Can |
| --- | --- |
| **Admin** | Everything: run jobs, edit the catalog and earnings dates, import CSVs, manage users and invites. |
| **Member** | View the dashboard, tickers and performance, and record their own decisions. |

There is no email server, so a forgotten password is reset by an admin (**Team → Reset password** shows
a one-time temporary password) or from the command line. Everyone can change their own password under
**Account** (click your name at the bottom of the sidebar); doing so signs out their other browsers.

```bash
socialarb user create you@example.com --name "Your Name" --admin   # prompts for a password
socialarb user reset-password you@example.com                       # prints a temporary password
socialarb user list
socialarb user invite --email friend@example.com [--admin] [--days 7]
```

`SOCIALARB_SIGNUP` in `.env` changes the sign-up rule once an owner exists: `invite` (default), `open`
(anyone can sign up as a member) or `closed` (accounts are only made by admins or the CLI).

## Day to day

Two terminals:

```bash
cd backend && source .venv/bin/activate && socialarb serve
cd frontend && npm run dev
```

Open http://127.0.0.1:5173 and sign in (the first visit asks you to create the owner account). As an
admin, press **Run daily** on the Dashboard (or let the schedule below do it). It backs up the database,
ingests every source, scans and scores. `socialarb seed --reset` rebuilds the demo around today's date;
it also deletes your saved decisions.

**Updating from an earlier version:** `git pull`, then `pip install -e ".[dev]"` in `backend/` if the
command list changed. The database is upgraded in place when the server starts (or run `socialarb seed`). Before the rename the command was `ctm`; it still works as an alias.

## The screens

- **Dashboard**: one sentence summing up the day, counts of entry signals, early movers, exit signals
  and names being watched, buy-side and sell-side signal cards, an "also on the radar" list (watching,
  data gaps, missing earnings dates, chatter without buzz), and one row per ticker. Quiet tickers are
  hidden until you ask for them.
- **Ticker page** (click any ticker): a plain-English verdict and the checks behind it, your decision
  (acted / passed / exited + a note), the three signals, one chart of buzz against the stock, earnings
  timing, the company's products and a timeline. **Show all the numbers** opens every raw series,
  baseline and component.
- **Tickers**: every product and every status in one filterable table.
- **Performance**: how each kind of signal performed (hit rate, median and mean return versus the
  benchmark at 5, 20 and 60 trading days or through earnings), split by config version and by live
  versus replayed history, plus the full signal log with each signal's input snapshot.
- **Data & settings** (admins): run any job, see each source's last run and errors, add or edit
  companies, products and announcements, fix earnings dates, import companies or products from CSV,
  and manage the team (roles, deactivation, password resets, invites).
- **Account**: your profile and a change-password form.

## Commands

| Command | API | What it does |
| --- | --- | --- |
| `socialarb seed [--reset]` | n/a | Create the database, run migrations, load the demo catalog and history. `--reset` starts over, anchored to today. |
| `socialarb ingest [--source S] [--as-of D]` | `POST /api/ingest` | Run every enabled source; store observations and per-source run health. |
| `socialarb scan [--as-of D]` | `POST /api/scan` | Compute statuses, signals and alerts as of D (default: the last completed US trading session). |
| `socialarb daily [--as-of D]` | `POST /api/daily` | Backup, ingest, scan, evaluate. The **Run daily** button calls the same code. |
| `socialarb replay [--start D1] [--end D2]` | `POST /api/replay` | Scan every trading day in the range (default: all stored history). Alerts are tagged `replay`; already-replayed days are skipped. |
| `socialarb evaluate` | `POST /api/evaluate` | Fill forward returns for every alert; unfinished horizons hold the return so far. |
| `socialarb backup` | n/a | Copy the SQLite database to `backups/socialarb-<timestamp>.db`. |
| `socialarb serve` | n/a | Start the API on 127.0.0.1:8000. |
| `socialarb user create\|reset-password\|list\|invite` | n/a | Manage accounts from the command line (see Accounts). |
| `socialarb openapi` | n/a | Write `frontend/openapi.json`; `npm run gen:api` regenerates the frontend's typed client. |

## The demo

The demo is anchored to the last completed US trading session when you seed (stored in
`data/demo_state.json`; set `demo.anchor_date` in config to pin it). Real tickers are used for realism,
but every number is synthetic. On the anchor date:

| # | Product | Shows as | Rule (internal stage name) |
| --- | --- | --- | --- |
| 1 | CROX · Charm clog collab | Entry signal | `entry_review`: buzz up on two sources, price flat, chatter quiet, 70 days to earnings |
| 2 | ONON · Cloudtilt trainer | Exit signal | `exit_review`: price up on volume, ticker searches and cashtags rising |
| 3 | ELF · Glow reviver lip oil | Early mover | `early_recognition` |
| 4 | YETI · Hopper backpack cooler | Seasonal, no alert | attention `seasonal` |
| 5 | SONO · Ace headphones | Quiet | a one-day search spike stays `normal` |
| 6 | BOOT · Western work boot | Quiet, chatter on the radar | cashtags up ~4× from a few accounts: retail `rising`, never `elevated` |
| 7 | BIRK · Boston clog suede | Data gap | price feed 6 days stale → `data_gap`, never an entry |
| 8 | WRBY · Contact lens subscription | Entry signal (single source) | only one attention source is healthy |
| 9 | COTY · Burberry Goddess fragrance | Entry signal, quarter closed | reporting quarter already ended |
| 10 | OLPX · No.4 bond shampoo | Watching | 150 days to earnings, outside the window |
| 11 | FIVE · both products | Earnings date needed | the earnings date is in the past |
| 12 | Everything else | Quiet | no alert |

24 earlier episodes are planted in the history (15 where buzz led the price, 9 where it didn't), so
`replay` + `evaluate` fill the Performance page with a mixed record.

## Data sources and going live

Each source has a mode in `config/settings.yaml`: `demo` (default), `live`, `off`, and for earnings
also `csv`.

| Source | Feeds | Live provider (stub today) | Key in `.env` |
| --- | --- | --- | --- |
| `search_interest` | product buzz | Google Trends via a third-party provider | `TRENDS_PROVIDER_API_KEY` |
| `social_mentions` | product buzz | YouTube Data API | `YOUTUBE_API_KEY` |
| `price` | price response | a daily-bars vendor | `PRICE_VENDOR_API_KEY` |
| `earnings` | earnings timing | `csv`: `data/earnings.csv`; `live`: a calendar API | `EARNINGS_CALENDAR_API_KEY` (live only) |
| `ticker_search_interest` | retail chatter | same provider as search interest | `TRENDS_PROVIDER_API_KEY` |
| `cashtag_mentions` | retail chatter | X API (counts + capped post sample, monthly budget) | `X_BEARER_TOKEN` |

**Switching a source to live** (e.g. `cashtag_mentions: {mode: live, ...}`) without its key records a
`skipped` run with a message naming the missing key. You'll see it on the Dashboard's feed chip and in
Data & settings, and everything else keeps working. With the key set, the run is still skipped and the
message says the live adapter isn't built yet. Each stub documents its provider and constraints in
`backend/app/sources/<source>.py`; building one means writing its `fetch()`, with no schema or UI
changes.

**Earnings from CSV:** set `earnings: {mode: csv}` (it reads `data/earnings.csv`; add `csv: path/to/file.csv` to use another file). Columns are
`ticker`, `next_earnings_date`, `confirmed` (yes/no), `fiscal_quarter_end` and an optional `as_of` (the
date the row was known; add a new row when a date changes to keep point-in-time history). The
checked-in file matches the demo, except FIVE has a corrected date. Dates you type in Data & settings
override both the feed and the CSV until they pass.

## Schedule

Run `socialarb daily` at 08:30 Australia/Sydney, Tuesday to Saturday (after the US close).

**macOS / Linux cron** (`crontab -e`). `CRON_TZ` works on Linux; macOS cron uses the Mac's own time
zone, so set the Mac to Sydney time or shift the hour:

```cron
CRON_TZ=Australia/Sydney
30 8 * * 2-6  cd /path/to/signals/backend && .venv/bin/socialarb daily >> ../data/logs/cron.log 2>&1
```

**Windows Task Scheduler:**

```powershell
schtasks /Create /TN "SocialArb daily" /SC WEEKLY /D TUE,WED,THU,FRI,SAT /ST 08:30 `
  /TR "C:\path\to\signals\backend\.venv\Scripts\socialarb.exe daily"
```

A missed day is harmless: the next run fetches the gap. For an always-on machine there is also a
built-in scheduler: set `schedule.in_process_enabled: true` and keep `socialarb serve` running.

## Configuration

Every threshold, window, stage rule and source setting is in `config/settings.yaml`. Each scan
validates it (an invalid file stops the scan with a readable message and changes nothing), fingerprints
it and stores it. Alerts record the config version that produced them and are never rewritten, so
changing a threshold produces new alerts under a new version and leaves the old ones as they were.
Secrets go in `.env` (copy `.env.example`); they are never stored in the database or logged.

## Done-when checklist

How to see each item from the build prompt, with no API keys:

| Item | Where to look |
| --- | --- |
| Install and run on a clean machine in under 10 minutes | The install steps above (about 2 minutes plus downloads) |
| Three separate signals plus a stage, default 6–14 week earnings filter | **Tickers** page (filter on by default); the Dashboard shows the same per ticker |
| Whether price has lagged the product signal, with a signal-start marker | Any ticker page: the "Buzz vs the stock" chart marks the signal start |
| An entry, an early-recognition and an exit case, each with a reason | Dashboard cards, then each ticker's verdict and checks |
| The stale-price case as a data gap, not an entry | Dashboard → "Also on the radar" → BIRK |
| Replay and evaluate fill the rules-performance table | `socialarb replay` + `socialarb evaluate`, then **Performance** |
| Add a product, run daily, see the alert log update | **Data & settings** → Products → Add → Run daily; then **Performance** → signal log |
| Change a threshold, rescan, new alerts carry a new config version, old ones unchanged | Edit `config/settings.yaml`, `socialarb scan`, then filter the signal log by config |
| Switch a source to live without credentials: clear skipped status, app still works | Set a source's mode to `live`, Run daily, check **Data & settings** → Sources |

## Security

- **Accounts:** passwords are hashed with scrypt (per-user salt). Sessions are random 256-bit tokens in
  an `HttpOnly`, `SameSite=Lax` cookie (marked `Secure` when served over HTTPS); only a SHA-256 of
  each token is stored, so a copied database can't be used to sign in. Sessions last 14 days.
- **Every API route except `/api/health` and `/api/auth/status|login|signup` needs a session.** Jobs,
  catalog edits, imports and team management also need the admin role (checked on the server, not
  just hidden in the UI).
- **Cross-site requests:** every write must be JSON or carry the `X-Requested-With` header the app
  sends, which a form on another site can't do.
- **Guessing:** 8 failed sign-ins per email per client in 15 minutes, and 30 per email from anywhere,
  get a "too many attempts" error. Error messages don't say whether an email has an account. Invite
  codes are single use, expire, and are stored hashed.
- **Behind Cloudflare** set `SOCIALARB_BEHIND_CLOUDFLARE=1` so the rate limit sees each visitor's IP
  (from `CF-Connecting-IP`); leave it unset otherwise, because anyone can send that header.
- The API still listens on `127.0.0.1` by default. Put a TLS-terminating proxy or tunnel in front of it
  to serve socialarb.trade.

## Tests

```bash
cd backend
pytest
```

About two minutes. Covers every status rule on fixture series, the stage engine (rule order, data gap
first, exit before entry, entry never on unknown inputs), the 12 demo scenarios end to end, a full
replay and evaluation, zero network calls in demo mode and for live stubs, alerts never rewritten by
rescans or config changes, ingest fault isolation, earnings CSV mode, the Admin flows and the
Dashboard and Ticker read models.

## Layout

```
backend/app/
  api/         FastAPI routes and response models (no business logic)
  core/        config loading and fingerprinting, trading calendar, paths, logging
  db/          SQLAlchemy models, session, Alembic migrations
  sources/     one file per source (demo, live stub, earnings CSV), registry.py, base.py;
               demo/ holds the synthetic universe and generators
  signals/     input health, attention, price, retail, earnings, point-in-time store
  stages/      rule engine reading config
  pipeline/    seed, ingest, scan, replay, evaluate, jobs, and the read models behind each screen
  cli.py
frontend/src/
  api/         typed client (types generated from OpenAPI)
  components/  sidebar layout, signal pills and sparklines, TimeChart
  pages/       Dashboard, Ticker, Watchlist (Tickers), Alerts (Performance), Admin (Data & settings),
               Detail (the "all the numbers" drill-down)
config/settings.yaml
data/earnings.csv
DECISIONS.md   every judgement call made while building
```
