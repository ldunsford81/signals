"""Filesystem locations. Everything can be overridden with environment variables (see .env.example).

Variables are named SOCIALARB_*; the older CTM_* names are still read so existing setups keep working.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPO_ROOT / ".env")

APP_NAME = "SocialArb"
DOMAIN = "socialarb.trade"


def env(name: str, default: str | Path | None = None) -> str | None:
    """SOCIALARB_<name>, falling back to the legacy CTM_<name>, then the default."""
    v = os.environ.get(f"SOCIALARB_{name}") or os.environ.get(f"CTM_{name}")
    return v if v else (str(default) if default is not None else None)


def data_dir() -> Path:
    p = Path(env("DATA_DIR", REPO_ROOT / "data"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_path() -> Path:
    return Path(env("CONFIG", REPO_ROOT / "config" / "settings.yaml"))


def database_url() -> str:
    url = env("DATABASE_URL")
    if url:
        return url
    db = data_dir() / "socialarb.db"
    legacy = data_dir() / "ctm.db"
    if not db.exists() and legacy.exists():   # installs from before the rename keep their data
        db = legacy
    return f"sqlite:///{db}"


def database_file() -> Path | None:
    url = database_url()
    if url.startswith("sqlite:///"):
        return Path(url.removeprefix("sqlite:///"))
    return None


def backups_dir() -> Path:
    p = Path(env("BACKUP_DIR", REPO_ROOT / "backups"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def logs_dir() -> Path:
    p = data_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p
