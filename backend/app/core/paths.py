"""Filesystem locations. Everything can be overridden with environment variables (see .env.example)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPO_ROOT / ".env")


def data_dir() -> Path:
    p = Path(os.environ.get("CTM_DATA_DIR", REPO_ROOT / "data"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_path() -> Path:
    return Path(os.environ.get("CTM_CONFIG", REPO_ROOT / "config" / "settings.yaml"))


def database_url() -> str:
    return os.environ.get("CTM_DATABASE_URL", f"sqlite:///{data_dir() / 'ctm.db'}")


def database_file() -> Path | None:
    url = database_url()
    if url.startswith("sqlite:///"):
        return Path(url.removeprefix("sqlite:///"))
    return None


def backups_dir() -> Path:
    p = Path(os.environ.get("CTM_BACKUP_DIR", REPO_ROOT / "backups"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def logs_dir() -> Path:
    p = data_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p
