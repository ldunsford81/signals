"""Ingest health: one failing source never blocks the others, and failures never delete data."""
from sqlalchemy import func, select

from app.core.config import load_settings
from app.db.models import Observation, SourceRun
from app.db.session import session_factory
from app.pipeline.ingest import run_ingest
from app.pipeline.seed import seed
from app.sources import registry
from conftest import ANCHOR


def count(s, source):
    return s.scalar(select(func.count()).select_from(Observation).where(Observation.source == source))


def test_failing_source_does_not_block_others_or_delete_data(tmp_env, settings, monkeypatch):
    seed(settings)

    class Boom:
        name, family, entity_type, metrics, rescales_history = "price", "price", "company", ["close"], False

        def required_settings(self):
            return []

        def fetch(self, entities, start, end):
            raise RuntimeError("vendor down")

    monkeypatch.setitem(registry.REGISTRY, "price", {"demo": lambda st, cfg: Boom()})
    with session_factory()() as s:
        before = count(s, "price")
        runs = {r.source: r for r in run_ingest(s, settings, as_of=ANCHOR)}
        assert runs["price"].status == "error" and "vendor down" in runs["price"].message
        assert runs["price"].last_good_obs_date == ANCHOR          # carried from the last good run
        assert all(r.status in ("ok", "partial") for n, r in runs.items() if n != "price")
        assert count(s, "price") == before


def test_live_without_implementation_or_credentials_is_skipped(tmp_env, settings, monkeypatch):
    seed(settings)

    class NeedsKey:
        name, family, entity_type, metrics, rescales_history = "social_mentions", "attention", "product", ["mentions"], False

        def required_settings(self):
            return ["YOUTUBE_API_KEY"]

        def fetch(self, entities, start, end):
            raise AssertionError("must not be called without credentials")

    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.setitem(registry.REGISTRY, "social_mentions", {"live": lambda st, cfg: NeedsKey()})
    live = load_settings(overrides={"demo": {"anchor_date": ANCHOR.isoformat()},
                                    "sources": {"cashtag_mentions": {"mode": "live"},
                                                "social_mentions": {"mode": "live"}}})
    with session_factory()() as s:
        runs = {r.source: r for r in run_ingest(s, live, as_of=ANCHOR)}
    assert runs["cashtag_mentions"].status == "skipped"
    assert runs["social_mentions"].status == "skipped" and "YOUTUBE_API_KEY" in runs["social_mentions"].message
    assert runs["price"].status in ("ok", "partial")


def test_reingest_is_idempotent(tmp_env, settings):
    seed(settings)
    with session_factory()() as s:
        before = count(s, "social_mentions")
        run_ingest(s, settings, as_of=ANCHOR, only=["social_mentions"])
        run_ingest(s, settings, as_of=ANCHOR, only=["social_mentions"])
        assert count(s, "social_mentions") == before
        assert s.scalar(select(func.count()).select_from(SourceRun)) >= 8
