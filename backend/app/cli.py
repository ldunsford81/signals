"""`socialarb` command line (`ctm` still works as an alias). Every command calls the same code as the API and the scheduler."""
from __future__ import annotations

import json
from datetime import date
from typing import Optional

import typer

from app.core.config import ConfigError
from app.core.logging import setup_logging
from app.pipeline import jobs

app = typer.Typer(add_completion=False, no_args_is_help=True, help="SocialArb (socialarb.trade): product buzz vs. price vs. retail chatter")


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
    """Backup, ingest, scan, then evaluate. This is what cron runs."""
    _run(jobs.daily_job, as_of=_parse(as_of), trigger="schedule")


@app.command()
def replay(start: Optional[str] = typer.Option(None, "--start", help="First exchange date (default: earliest with enough history)"),
           end: Optional[str] = typer.Option(None, "--end", help="Last exchange date (default: latest price data)")) -> None:
    """Run the scan for every trading day in a range (alerts tagged trigger=replay)."""
    _run(jobs.replay_job, start=_parse(start), end=_parse(end))


@app.command()
def evaluate() -> None:
    """Fill alert_outcomes (5/20/60 trading days and through earnings) for every alert."""
    _run(jobs.evaluate_job)


@app.command()
def backup() -> None:
    """Copy the SQLite database to backups/ with a timestamp."""
    _run(jobs.backup_job)


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000, reload: bool = False) -> None:
    """Start the API (binds to 127.0.0.1 by default; every page needs a signed-in account)."""
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


users = typer.Typer(no_args_is_help=True, help="Accounts: create users, reset passwords, make invites.")
app.add_typer(users, name="user")


def _accounts_session():
    from app.db.session import session_factory, upgrade_db
    upgrade_db()
    return session_factory()()


@users.command("create")
def user_create(email: str = typer.Option(..., prompt=True), name: str = typer.Option("", prompt="Name (optional)"),
                admin: bool = typer.Option(False, "--admin", help="Give admin rights"),
                password: str = typer.Option(..., prompt=True, hide_input=True, confirmation_prompt=True)) -> None:
    """Create an account directly (no invite needed)."""
    from app.auth import accounts
    with _accounts_session() as s:
        try:
            u = accounts.create_user(s, email, name, password, role="admin" if admin else "member")
            s.commit()
        except accounts.AuthError as e:
            typer.secho(str(e), fg=typer.colors.RED, err=True)
            raise typer.Exit(1)
        typer.echo(f"created {u.email} ({u.role})")


@users.command("reset-password")
def user_reset(email: str = typer.Option(..., prompt=True),
               password: str = typer.Option(..., prompt="New password", hide_input=True, confirmation_prompt=True)) -> None:
    """Set a new password and sign the user out everywhere."""
    from app.auth import accounts
    with _accounts_session() as s:
        try:
            u = accounts.set_password(s, email, password)
        except accounts.AuthError as e:
            typer.secho(str(e), fg=typer.colors.RED, err=True)
            raise typer.Exit(1)
        typer.echo(f"password reset for {u.email}; they have been signed out everywhere")


@users.command("list")
def user_list() -> None:
    """List accounts."""
    from sqlalchemy import select
    from app.db.models import User
    with _accounts_session() as s:
        for u in s.scalars(select(User).order_by(User.created_at)):
            typer.echo(f"{u.email:32} {u.role:7} {'active' if u.active else 'disabled':9} last login {u.last_login_at or 'never'}")


@users.command("invite")
def user_invite(email: Optional[str] = typer.Option(None, help="Only this email may use it"),
                admin: bool = typer.Option(False, "--admin", help="The new account gets admin rights"),
                days: int = typer.Option(7, help="Days until it expires")) -> None:
    """Create a one-time sign-up code."""
    from app.auth import accounts
    with _accounts_session() as s:
        inv, code = accounts.create_invite(s, None, email, "admin" if admin else "member", days)
        typer.echo(f"invite code: {code}  (expires {inv.expires_at:%Y-%m-%d}, role {inv.role}"
                   f"{', for ' + inv.email if inv.email else ''})")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
