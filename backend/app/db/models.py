"""SQLAlchemy models. Twelve tables in four groups: catalog, observations, runs/config, review log.

Every data point from every source lives in `observations`; there is no per-source table.
`alerts` rows are written once and never updated or deleted by application code.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# ---- catalog ------------------------------------------------------------
class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    exchange: Mapped[str | None] = mapped_column(String(32))
    sector: Mapped[str | None] = mapped_column(String(64))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    market_cap_usd_m: Mapped[float | None] = mapped_column(Float)
    analyst_count: Mapped[int | None] = mapped_column(Integer)
    benchmark_ticker: Mapped[str] = mapped_column(String(16), default="XLY")
    next_earnings_date: Mapped[date | None] = mapped_column(Date)
    earnings_date_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    fiscal_quarter_end: Mapped[date | None] = mapped_column(Date)
    cashtag_exclusions: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)

    products: Mapped[list["Product"]] = relationship(back_populates="company")


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    name: Mapped[str] = mapped_column(String(200))
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    launched_on: Mapped[date | None] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    company: Mapped[Company] = relationship(back_populates="products")


class Announcement(Base):
    __tablename__ = "announcements"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))
    event_date: Mapped[date] = mapped_column(Date)
    type: Mapped[str] = mapped_column(String(32))  # new_product, partnership, distribution, negative_event, other
    title: Mapped[str] = mapped_column(String(300))
    url: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)


# ---- observations -------------------------------------------------------
class Snapshot(Base):
    __tablename__ = "snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(64))
    entity_key: Mapped[str] = mapped_column(String(64))
    pulled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    window_start: Mapped[date] = mapped_column(Date)
    window_end: Mapped[date] = mapped_column(Date)

    __table_args__ = (Index("ix_snapshots_source_entity", "source", "entity_key", "window_end"),)


class Observation(Base):
    __tablename__ = "observations"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(16))  # product, company, benchmark
    entity_key: Mapped[str] = mapped_column(String(64))
    metric: Mapped[str] = mapped_column(String(64))
    obs_date: Mapped[date] = mapped_column(Date)
    value: Mapped[float] = mapped_column(Float)
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("snapshots.id"))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint("source", "entity_type", "entity_key", "metric", "obs_date", "snapshot_id",
                         name="uq_observation"),
        Index("ix_obs_lookup", "source", "entity_key", "metric", "obs_date"),
        Index("ix_obs_snapshot", "snapshot_id"),
    )


# ---- runs and config ----------------------------------------------------
class SourceRun(Base):
    __tablename__ = "source_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16))  # ok, partial, error, skipped
    rows_written: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    last_good_obs_date: Mapped[date | None] = mapped_column(Date)


class ConfigVersion(Base):
    __tablename__ = "config_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    config_hash: Mapped[str] = mapped_column(String(64), unique=True)
    content: Mapped[dict] = mapped_column(JSON)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Scan(Base):
    __tablename__ = "scans"
    id: Mapped[int] = mapped_column(primary_key=True)
    as_of: Mapped[date] = mapped_column(Date, index=True)
    trigger: Mapped[str] = mapped_column(String(16))  # manual, schedule, replay
    config_hash: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16))  # running, ok, error
    error_message: Mapped[str | None] = mapped_column(Text)


class SignalState(Base):
    __tablename__ = "signal_states"
    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("scans.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    attention_status: Mapped[str] = mapped_column(String(16))
    attention_score: Mapped[float | None] = mapped_column(Float)
    attention_components: Mapped[dict] = mapped_column(JSON)
    price_response: Mapped[str] = mapped_column(String(32))
    price_components: Mapped[dict] = mapped_column(JSON)
    retail_status: Mapped[str] = mapped_column(String(16))
    retail_components: Mapped[dict] = mapped_column(JSON)
    signal_start_date: Mapped[date | None] = mapped_column(Date)
    days_to_earnings: Mapped[int | None] = mapped_column(Integer)
    days_left_in_quarter: Mapped[int | None] = mapped_column(Integer)
    stage: Mapped[str] = mapped_column(String(32))
    input_health: Mapped[dict] = mapped_column(JSON)


# ---- review log ---------------------------------------------------------
class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("scans.id"), index=True)
    as_of: Mapped[date] = mapped_column(Date, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    stage: Mapped[str] = mapped_column(String(32))
    prior_stage: Mapped[str | None] = mapped_column(String(32))
    changed_fields: Mapped[list] = mapped_column(JSON)
    summary: Mapped[str] = mapped_column(Text)
    input_snapshot: Mapped[dict] = mapped_column(JSON)
    config_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AlertOutcome(Base):
    __tablename__ = "alert_outcomes"
    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id"), index=True)
    horizon: Mapped[str] = mapped_column(String(32))  # 5d, 20d, 60d, through_earnings
    stock_return: Mapped[float | None] = mapped_column(Float)
    benchmark_return: Mapped[float | None] = mapped_column(Float)
    excess_return: Mapped[float | None] = mapped_column(Float)
    complete: Mapped[bool] = mapped_column(Boolean, default=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("alert_id", "horizon", name="uq_alert_outcome"),)


class AlertReview(Base):
    __tablename__ = "alert_reviews"
    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id"), index=True)
    decision: Mapped[str] = mapped_column(String(16), default="unreviewed")  # unreviewed, acted, passed, exited
    note: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)  # who decided (null: before accounts)


# ---- accounts (added after the MVP: login and invite-only sign-up) ---------------
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="member")  # admin, member
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserSession(Base):
    """A signed-in browser. Only a SHA-256 of the cookie token is stored."""
    __tablename__ = "user_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    user_agent: Mapped[str | None] = mapped_column(String(300))


class Invite(Base):
    """A one-time sign-up code created by an admin. Only a SHA-256 of the code is stored."""
    __tablename__ = "invites"
    id: Mapped[int] = mapped_column(primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    hint: Mapped[str] = mapped_column(String(8))           # first characters, to tell invites apart
    email: Mapped[str | None] = mapped_column(String(254))  # optional: only this email may use it
    role: Mapped[str] = mapped_column(String(16), default="member")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
