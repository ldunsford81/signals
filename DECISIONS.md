# Decisions

Simple, reasonable choices made while building, recorded so they can be revisited.

## Repo and stack

- **Repo root is the project root.** The prompt's `trend-monitor/` folder maps to this repository's
  root (`backend/`, `frontend/`, `config/`, `data/` sit at the top level).
- **Python ≥ 3.12.** Developed and tested on 3.13; `pyproject.toml` requires 3.12+.
- **`ctm` is a console script** from `backend/pyproject.toml` (`pip install -e backend`).
- **Typed frontend client:** `openapi-typescript` generates `src/api/schema.d.ts` from the FastAPI
  schema; `src/api/client.ts` is a thin `fetch` wrapper using those types. `openapi.json` is
  committed so the client can be regenerated without a running server.
- **Paths are overridable** with `CTM_DATA_DIR`, `CTM_DATABASE_URL`, `CTM_CONFIG`, `CTM_BACKUP_DIR`
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
  at seed time. It is written to `data/demo_state.json` so later `ctm ingest` runs extend the same
  deterministic history instead of shifting it. `ctm seed --reset` re-anchors to today. Dates after
  the anchor continue in the regime the anchor day was in (scenarios will drift after a few days;
  re-seed to refresh).
- **Seed = catalog + full-history ingest.** `ctm seed` loads the catalog, then runs the normal ingest
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
- **Scan triggers.** CLI `ctm scan` = `manual`, `ctm daily` (cron) = `schedule`, the UI's Run daily
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
