"""`ctm` command line. Every command calls the same code as the API and the scheduler."""
from __future__ import annotations

import json
from datetime import date
from typing import Optional

import typer

from app.core.config import ConfigError
from app.core.logging import setup_logging
from app.pipeline import jobs

app = typer.Typer(add_completion=False, no_args_is_help=True, help="Consumer Product Trend Monitor")


def _parse(d: Optional[str]) -> Optional[date]:
    if d is None:
        return None
    try:
        return date.fromisoformat(d)
    except ValueError:
        raise typer.BadParameter(f"'{d}' is not a date (use YYYY-MM-DD)")


def _print(obj) -> None:
    typer.echo(json.dumps(jobs.to_json(obj), indent=2))


def _run(fn, *a, **kw):
    setup_logging()
    try:
        _print(fn(*a, **kw))
    except ConfigError as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(2)
    except Exception as e:  # noqa: BLE001
        typer.secho(f"{type(e).__name__}: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)


@app.command()
def seed(reset: bool = typer.Option(False, "--reset", help="Delete the database and demo state first")) -> None:
    """Create the database, run migrations, load the demo catalog and demo observations."""
    _run(jobs.seed_job, reset=reset)


@app.command()
def ingest(source: list[str] = typer.Option(None, "--source", "-s", help="Only this source (repeatable)"),
           as_of: Optional[str] = typer.Option(None, "--as-of", help="Exchange date YYYY-MM-DD")) -> None:
    """Run every enabled adapter, write observations and source_runs."""
    _run(jobs.ingest_job, as_of=_parse(as_of), sources=source or None)


@app.command()
def scan(as_of: Optional[str] = typer.Option(None, "--as-of", help="Exchange date (default: last completed US session)"),
         trigger: str = typer.Option("manual", help="manual | schedule")) -> None:
    """Compute statuses, stages and alerts as of a date."""
    _run(jobs.scan_job, as_of=_parse(as_of), trigger=trigger)


@app.command()
def daily(as_of: Optional[str] = typer.Option(None, "--as-of")) -> None:
    """Backup, ingest, then scan. This is what cron runs."""
    _run(jobs.daily_job, as_of=_parse(as_of), trigger="schedule")


@app.command()
def backup() -> None:
    """Copy the SQLite database to backups/ with a timestamp."""
    _run(jobs.backup_job)


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000, reload: bool = False) -> None:
    """Start the API (binds to 127.0.0.1 by default: there is no auth)."""
    import uvicorn
    setup_logging()
    uvicorn.run("app.main:app", host=host, port=port, reload=reload)


@app.command()
def openapi(out: str = typer.Option("../frontend/openapi.json", help="Where to write the schema")) -> None:
    """Write the OpenAPI schema (the frontend client types are generated from it)."""
    from app.main import app as fastapi_app
    with open(out, "w") as f:
        json.dump(fastapi_app.openapi(), f, indent=2)
    typer.echo(f"wrote {out}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
