"""Request guards: who is signed in, admin-only routes, and a cross-site request check."""
from __future__ import annotations

from typing import Iterator

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth import accounts
from app.db.models import User
from app.db.session import session_factory

COOKIE = "socialarb_session"
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def get_session() -> Iterator[Session]:
    s = session_factory()()
    try:
        yield s
    finally:
        s.close()


def csrf_guard(request: Request) -> None:
    """Writes must come from our own pages: a JSON body or our header. A cross-site HTML form can send
    neither, and a cross-site fetch with them needs a CORS preflight this API never grants."""
    if request.method in UNSAFE:
        ctype = request.headers.get("content-type", "")
        if not (ctype.startswith("application/json") or request.headers.get("x-requested-with")):
            raise HTTPException(status_code=403, detail="Request blocked: missing the app's request header.")


def require_user(request: Request, session: Session = Depends(get_session)) -> User:
    csrf_guard(request)
    user = accounts.user_for_token(session, request.cookies.get(COOKIE))
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can do that.")
    return user
