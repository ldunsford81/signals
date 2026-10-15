"""Accounts: sign-up (owner first, then invite-only), sign-in, sessions, invites and user management."""
from __future__ import annotations

import os
import re
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.auth import security as sec
from app.db.models import Invite, User, UserSession, utcnow

SESSION_DAYS = 14
INVITE_DAYS = 7
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def _aware(d: datetime | None) -> datetime | None:
    """SQLite drops tzinfo; everything is stored in UTC."""
    return d.replace(tzinfo=timezone.utc) if d is not None and d.tzinfo is None else d


def signup_mode() -> str:
    """invite (default): sign-up needs an invite once an owner exists. open: anyone. closed: nobody."""
    mode = (os.environ.get("SOCIALARB_SIGNUP") or "invite").lower()
    return mode if mode in ("invite", "open", "closed") else "invite"


def user_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(User)) or 0


def normalize_email(email: str) -> str:
    e = (email or "").strip().lower()
    if not EMAIL_RE.match(e) or len(e) > 254:
        raise AuthError("Enter a valid email address.")
    return e


# ---- rate limiting (in memory, per process) ------------------------------------------------
_FAILS: dict[str, deque] = defaultdict(deque)
WINDOW_S, MAX_FAILS = 15 * 60, 8
MAX_FAILS_PER_EMAIL = 30   # across all clients, so a spoofed or rotating IP can't guess forever


def _check_rate(key: str, limit: int = MAX_FAILS) -> None:
    q = _FAILS[key]
    now = time.monotonic()
    while q and now - q[0] > WINDOW_S:
        q.popleft()
    if len(q) >= limit:
        raise AuthError("Too many attempts. Wait 15 minutes and try again.", 429)


def _fail(*keys: str) -> None:
    for key in keys:
        _FAILS[key].append(time.monotonic())


def reset_rate_limits() -> None:
    _FAILS.clear()


# ---- users ------------------------------------------------------------------------------------
def create_user(session: Session, email: str, name: str, password: str, role: str = "member") -> User:
    email = normalize_email(email)
    name = (name or "").strip() or email.split("@")[0]
    if len(name) > 120:
        raise AuthError("That name is too long.")
    problem = sec.password_problem(password, email)
    if problem:
        raise AuthError(problem)
    if session.scalar(select(User).where(User.email == email)):
        raise AuthError("An account with that email already exists. Sign in instead.", 409)
    u = User(email=email, name=name, password_hash=sec.hash_password(password), role=role, active=True)
    session.add(u)
    session.flush()
    return u


def signup(session: Session, email: str, name: str, password: str, invite_code: str | None) -> User:
    """The first account becomes the owner (admin). After that the signup mode decides."""
    if user_count(session) == 0:
        u = create_user(session, email, name, password, role="admin")
        session.commit()
        return u
    mode = signup_mode()
    if mode == "closed":
        raise AuthError("Sign-up is closed. Ask an admin to create your account.", 403)
    role = "member"
    inv = None
    if mode == "invite":
        code = sec.normalize_code(invite_code or "")
        if not code:
            raise AuthError("Sign-up needs an invite code. Ask an admin for one.", 403)
        inv = session.scalar(select(Invite).where(Invite.code_hash == sec.token_hash(code)))
        now = utcnow()
        if inv is None or inv.revoked or inv.used_by is not None or _aware(inv.expires_at) < now:
            raise AuthError("That invite code isn't valid. It may have expired or already been used.", 403)
        if inv.email and inv.email != normalize_email(email):
            raise AuthError("That invite is for a different email address.", 403)
        role = inv.role
    u = create_user(session, email, name, password, role=role)
    if inv is not None:
        inv.used_by, inv.used_at = u.id, utcnow()
    session.commit()
    return u


def authenticate(session: Session, email: str, password: str, client: str = "") -> User:
    who = (email or "").strip().lower()
    key, email_key = f"{who}|{client}", f"{who}|*"
    _check_rate(key)
    _check_rate(email_key, MAX_FAILS_PER_EMAIL)
    try:
        e = normalize_email(email)
    except AuthError:
        _fail(key, email_key)
        raise AuthError("Email or password is incorrect.", 401)
    u = session.scalar(select(User).where(User.email == e))
    ok = sec.verify_password(password or "", u.password_hash if u else sec.DUMMY_HASH)
    if not u or not ok or not u.active:
        _fail(key, email_key)
        raise AuthError("Email or password is incorrect.", 401)
    _FAILS.pop(key, None)
    u.last_login_at = utcnow()
    session.commit()
    return u


# ---- sessions -------------------------------------------------------------------------------------
def start_session(session: Session, user: User, user_agent: str | None) -> tuple[str, datetime]:
    token = sec.new_token()
    expires = utcnow() + timedelta(days=SESSION_DAYS)
    session.add(UserSession(user_id=user.id, token_hash=sec.token_hash(token), expires_at=expires,
                            user_agent=(user_agent or "")[:300]))
    session.commit()
    return token, expires


def user_for_token(session: Session, token: str | None) -> User | None:
    if not token:
        return None
    s = session.scalar(select(UserSession).where(UserSession.token_hash == sec.token_hash(token)))
    if s is None or _aware(s.expires_at) < utcnow():
        return None
    u = session.get(User, s.user_id)
    if u is None or not u.active:
        return None
    now = utcnow()
    if (now - _aware(s.last_seen_at)) > timedelta(minutes=5):   # don't write on every request
        s.last_seen_at = now
        session.commit()
    return u


def end_session(session: Session, token: str | None) -> None:
    if token:
        s = session.scalar(select(UserSession).where(UserSession.token_hash == sec.token_hash(token)))
        if s is not None:
            session.delete(s)
            session.commit()


def end_all_sessions(session: Session, user_id: int, keep_token: str | None = None) -> None:
    keep = sec.token_hash(keep_token) if keep_token else None
    for s in session.scalars(select(UserSession).where(UserSession.user_id == user_id)):
        if s.token_hash != keep:
            session.delete(s)
    session.commit()


def change_password(session: Session, user: User, current: str, new: str, token: str | None) -> None:
    if not sec.verify_password(current or "", user.password_hash):
        raise AuthError("Your current password is incorrect.", 400)
    problem = sec.password_problem(new, user.email)
    if problem:
        raise AuthError(problem)
    user.password_hash = sec.hash_password(new)
    session.commit()
    end_all_sessions(session, user.id, keep_token=token)   # sign out every other browser


def set_password(session: Session, email: str, new: str) -> User:
    """Admin / CLI reset. Signs the user out everywhere."""
    u = session.scalar(select(User).where(User.email == normalize_email(email)))
    if u is None:
        raise AuthError("No account with that email.", 404)
    problem = sec.password_problem(new, u.email)
    if problem:
        raise AuthError(problem)
    u.password_hash = sec.hash_password(new)
    session.commit()
    end_all_sessions(session, u.id)
    return u


# ---- invites and user management ------------------------------------------------------------------
def create_invite(session: Session, created_by: int | None, email: str | None = None, role: str = "member",
                  days: int = INVITE_DAYS) -> tuple[Invite, str]:
    if role not in ("member", "admin"):
        raise AuthError("Role must be member or admin.")
    code = sec.new_invite_code()
    norm = sec.normalize_code(code)
    inv = Invite(code_hash=sec.token_hash(norm), hint=norm[:4], email=normalize_email(email) if email else None,
                 role=role, created_by=created_by, expires_at=utcnow() + timedelta(days=days))
    session.add(inv)
    session.commit()
    return inv, code


def invite_status(inv: Invite) -> str:
    if inv.used_by is not None:
        return "used"
    if inv.revoked:
        return "revoked"
    if _aware(inv.expires_at) < utcnow():
        return "expired"
    return "open"


def revoke_invite(session: Session, invite_id: int) -> None:
    inv = session.get(Invite, invite_id)
    if inv is None:
        raise AuthError("Invite not found.", 404)
    inv.revoked = True
    session.commit()


def update_user(session: Session, actor: User, user_id: int, role: str | None, active: bool | None) -> User:
    u = session.get(User, user_id)
    if u is None:
        raise AuthError("User not found.", 404)
    if role is not None and role not in ("member", "admin"):
        raise AuthError("Role must be member or admin.")
    removing_admin = (role == "member" and u.role == "admin") or (active is False and u.role == "admin")
    if removing_admin:
        admins = session.scalar(select(func.count()).select_from(User).where(User.role == "admin", User.active.is_(True)))
        if admins <= 1:
            raise AuthError("There must always be at least one active admin.", 409)
    if role is not None:
        u.role = role
    if active is not None:
        u.active = active
        if not active:
            session.execute(update(UserSession).where(UserSession.user_id == u.id).values(expires_at=utcnow()))
    session.commit()
    return u
