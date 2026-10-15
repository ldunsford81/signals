"""The commands, callable from the CLI, the API and the scheduler. Each loads config fresh and is safe to re-run."""
from __future__ import annotations

import sqlite3
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

from app.core.config import Settings, load_settings
from app.core.logging import get_logger
from app.core.paths import backups_dir, database_file
from app.db.session import session_factory, upgrade_db
from app.pipeline.evaluate import run_evaluate
from app.pipeline.ingest import run_ingest
from app.pipeline.replay import run_replay
from app.pipeline.scan import run_scan
from app.pipeline.seed import seed

log = get_logger("jobs")


def seed_job(reset: bool = False, settings: Settings | None = None) -> dict:
    settings = settings or load_settings()
    anchor, runs = seed(settings, reset=reset)
    return {"anchor_date": anchor.isoformat(), "sources": [asdict(r) for r in runs]}


def ingest_job(as_of: date | None = None, sources: list[str] | None = None, settings: Settings | None = None) -> dict:
    settings = settings or load_settings()
    upgrade_db()
    with session_factory()() as s:
        runs = run_ingest(s, settings, as_of=as_of, only=sources)
    return {"sources": [asdict(r) for r in runs]}


def scan_job(as_of: date | None = None, trigger: str = "manual", settings: Settings | None = None) -> dict:
    settings = settings or load_settings()   # invalid config raises ConfigError before anything changes
    upgrade_db()
    with session_factory()() as s:
        return asdict(run_scan(s, settings, as_of=as_of, trigger=trigger))


def backup_job() -> dict:
    db = database_file()
    if not db or not db.exists():
        return {"backup": None, "message": "no database file to back up"}
    dest = backups_dir() / f"socialarb-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.db"
    src = sqlite3.connect(db)
    try:
        with sqlite3.connect(dest) as out:
            src.backup(out)
    finally:
        src.close()
    log.info("backup written to %s", dest)
    return {"backup": str(dest)}


def replay_job(start: date | None = None, end: date | None = None, settings: Settings | None = None) -> dict:
    settings = settings or load_settings()
    upgrade_db()
    with session_factory()() as s:
        return run_replay(s, settings, start=start, end=end)


def evaluate_job(settings: Settings | None = None) -> dict:
    settings = settings or load_settings()
    upgrade_db()
    with session_factory()() as s:
        return run_evaluate(s, settings)


def daily_job(as_of: date | None = None, trigger: str = "schedule") -> dict:
    """Backup, then ingest, then scan, then evaluate."""
    settings = load_settings()
    out = {"backup": backup_job()}
    out["ingest"] = ingest_job(as_of=as_of, settings=settings)
    out["scan"] = scan_job(as_of=as_of, trigger=trigger, settings=settings)
    out["evaluate"] = evaluate_job(settings=settings)
    return out


def _json(x):
    if isinstance(x, (date, datetime)):
        return x.isoformat()
    if isinstance(x, Path):
        return str(x)
    if isinstance(x, dict):
        return {k: _json(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_json(v) for v in x]
    return x


def to_json(x):
    return _json(x)
