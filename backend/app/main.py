"""FastAPI app. Run with `socialarb serve` (binds to 127.0.0.1; there is no auth)."""
from __future__ import annotations

import re
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from app.api.admin_routes import router as admin_router
from app.api.auth_routes import router as auth_router
from app.api.deps import require_admin, require_user
from app.api.routes import router
from app.core.config import ConfigError, load_settings
from app.core.logging import get_logger, setup_logging
from app.db.session import upgrade_db
from app.pipeline import jobs

log = get_logger("api")


_DOW = ["sun", "mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def cron_trigger(expr: str, tz: str):
    """Standard 5-field cron (0/7 = Sunday). APScheduler 3 numbers weekdays from Monday, so use names."""
    from apscheduler.triggers.cron import CronTrigger

    minute, hour, day, month, dow = expr.split()
    dow = re.sub(r"\d", lambda m: _DOW[int(m.group())], dow)
    return CronTrigger(minute=minute, hour=hour, day=day, month=month, day_of_week=dow, timezone=tz)


def start_scheduler():
    """Optional in-process scheduler (off by default; cron is the documented path)."""
    try:
        settings = load_settings()
    except ConfigError as e:
        log.error("scheduler not started: %s", e)
        return None
    if not settings.schedule.in_process_enabled:
        return None
    from apscheduler.schedulers.background import BackgroundScheduler

    sched = BackgroundScheduler(timezone=settings.schedule.timezone)
    sched.add_job(jobs.daily_job, cron_trigger(settings.schedule.cron_local, settings.schedule.timezone),
                  kwargs={"trigger": "schedule"}, id="daily", max_instances=1, coalesce=True)
    sched.start()
    log.info("in-process scheduler started: '%s' %s", settings.schedule.cron_local, settings.schedule.timezone)
    return sched


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    upgrade_db()
    sched = start_scheduler()
    yield
    if sched:
        sched.shutdown(wait=False)


app = FastAPI(title="SocialArb API", version="0.1.0", lifespan=lifespan,
              description="SocialArb (socialarb.trade): product buzz, price response and retail chatter, kept separate.")
app.include_router(auth_router)
app.include_router(router, dependencies=[Depends(require_user)])
app.include_router(admin_router, dependencies=[Depends(require_admin)])


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}
