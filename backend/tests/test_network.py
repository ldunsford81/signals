"""Demo mode makes zero outbound network requests."""
import socket

import pytest

from app.db.session import session_factory
from app.pipeline.ingest import run_ingest
from app.pipeline.scan import run_scan
from app.pipeline.seed import seed
from conftest import ANCHOR


def test_demo_mode_makes_no_network_calls(tmp_env, settings, monkeypatch):
    calls = []

    def guard(*args, **kwargs):
        calls.append(args)
        raise AssertionError(f"outbound network call attempted: {args}")

    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket.socket, "connect_ex", guard)
    monkeypatch.setattr(socket, "create_connection", guard)
    monkeypatch.setattr(socket, "getaddrinfo", guard)

    seed(settings)
    with session_factory()() as s:
        runs = run_ingest(s, settings, as_of=ANCHOR)
        run_scan(s, settings, as_of=ANCHOR)
    assert all(r.status in ("ok", "partial") for r in runs)
    assert calls == []
