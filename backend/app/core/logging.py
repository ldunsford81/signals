"""Logging to stdout and a rotating file under data/logs/."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from app.core.paths import logs_dir

_configured = False


def setup_logging(level: int = logging.INFO) -> None:
    global _configured
    if _configured:
        return
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger("socialarb")
    root.setLevel(level)
    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    root.addHandler(stream)
    try:
        fh = RotatingFileHandler(logs_dir() / "socialarb.log", maxBytes=2_000_000, backupCount=5)
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError:
        root.warning("could not open log file; logging to stdout only")
    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"socialarb.{name}")
