import os
from datetime import date

import pytest

ANCHOR = date(2026, 10, 13)


@pytest.fixture()
def tmp_env(tmp_path, monkeypatch):
    """Isolated data dir, database and backups for a test."""
    monkeypatch.setenv("SOCIALARB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SOCIALARB_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.delenv("SOCIALARB_DATABASE_URL", raising=False)
    monkeypatch.delenv("CTM_DATABASE_URL", raising=False)
    from app.db.session import get_engine
    get_engine.cache_clear()
    yield tmp_path
    get_engine.cache_clear()


@pytest.fixture()
def settings():
    from app.core.config import load_settings
    return load_settings(overrides={"demo": {"anchor_date": ANCHOR.isoformat()}})


@pytest.fixture(scope="session")
def seeded_db(tmp_path_factory):
    """One seeded + scanned database shared by read-only tests (seeding takes a few seconds)."""
    root = tmp_path_factory.mktemp("seeded")
    mp = pytest.MonkeyPatch()
    mp.setenv("SOCIALARB_DATA_DIR", str(root / "data"))
    mp.setenv("SOCIALARB_BACKUP_DIR", str(root / "backups"))
    from app.core.config import load_settings
    from app.db.session import get_engine, session_factory
    from app.pipeline.scan import run_scan
    from app.pipeline.seed import seed
    get_engine.cache_clear()
    s = load_settings(overrides={"demo": {"anchor_date": ANCHOR.isoformat()}})
    seed(s)
    with session_factory()() as ses:
        result = run_scan(ses, s, as_of=ANCHOR)
    yield {"settings": s, "scan": result, "root": root}
    get_engine.cache_clear()
    mp.undo()
