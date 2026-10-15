"""Sign-up, sign-in, sessions, invites and user management."""
from __future__ import annotations

import secrets
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import COOKIE, csrf_guard, get_session, require_admin, require_user
from app.auth import accounts
from app.auth.accounts import AuthError
from app.core.paths import env
from app.db.models import Invite, User, utcnow

router = APIRouter(prefix="/api/auth")


class AuthStatus(BaseModel):
    has_users: bool
    signup_mode: str
    invite_required: bool


class UserOut(BaseModel):
    id: int
    email: str
    name: str
    role: str
    active: bool
    created_at: datetime
    last_login_at: datetime | None


class SignupIn(BaseModel):
    email: str = Field(max_length=254)
    name: str = Field("", max_length=120)
    password: str = Field(max_length=256)
    invite_code: str | None = Field(None, max_length=40)


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)


class PasswordIn(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


class InviteIn(BaseModel):
    email: str | None = Field(None, max_length=254)
    role: Literal["member", "admin"] = "member"
    days: int = Field(7, ge=1, le=30)


class InviteOut(BaseModel):
    id: int
    hint: str
    email: str | None
    role: str
    status: str
    created_at: datetime
    expires_at: datetime
    used_by_email: str | None = None


class NewInviteOut(InviteOut):
    code: str


class UserPatch(BaseModel):
    role: Literal["member", "admin"] | None = None
    active: bool | None = None


class TempPasswordOut(BaseModel):
    email: str
    temporary_password: str


def _err(e: AuthError):
    raise HTTPException(status_code=e.status, detail=str(e))


def _user(u: User) -> UserOut:
    return UserOut.model_validate(u, from_attributes=True)


def _set_cookie(request: Request, response: Response, token: str) -> None:
    https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").startswith("https")
    response.set_cookie(COOKIE, token, max_age=accounts.SESSION_DAYS * 86400, httponly=True, secure=https,
                        samesite="lax", path="/")


def _client(request: Request) -> str:
    # The visitor's IP header is only trusted behind Cloudflare; anyone can send it otherwise.
    if (env("BEHIND_CLOUDFLARE") or "").lower() in ("1", "true", "yes"):
        ip = request.headers.get("cf-connecting-ip")
        if ip:
            return ip
    return request.client.host if request.client else ""


@router.get("/status", response_model=AuthStatus)
def status(session: Session = Depends(get_session)) -> AuthStatus:
    has = accounts.user_count(session) > 0
    mode = accounts.signup_mode()
    return AuthStatus(has_users=has, signup_mode=mode if has else "owner", invite_required=has and mode == "invite")


@router.post("/signup", response_model=UserOut, dependencies=[Depends(csrf_guard)])
def signup(body: SignupIn, request: Request, response: Response, session: Session = Depends(get_session)) -> UserOut:
    try:
        u = accounts.signup(session, body.email, body.name, body.password, body.invite_code)
    except AuthError as e:
        _err(e)
    u.last_login_at = utcnow()   # signing up signs you in
    token, _ = accounts.start_session(session, u, request.headers.get("user-agent"))
    _set_cookie(request, response, token)
    return _user(u)


@router.post("/login", response_model=UserOut, dependencies=[Depends(csrf_guard)])
def login(body: LoginIn, request: Request, response: Response, session: Session = Depends(get_session)) -> UserOut:
    try:
        u = accounts.authenticate(session, body.email, body.password, _client(request))
    except AuthError as e:
        _err(e)
    token, _ = accounts.start_session(session, u, request.headers.get("user-agent"))
    _set_cookie(request, response, token)
    return _user(u)


@router.post("/logout", dependencies=[Depends(csrf_guard)])
def logout(request: Request, response: Response, session: Session = Depends(get_session)) -> dict:
    accounts.end_session(session, request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(require_user)) -> UserOut:
    return _user(user)


@router.post("/password")
def change_password(body: PasswordIn, request: Request, user: User = Depends(require_user),
                    session: Session = Depends(get_session)) -> dict:
    try:
        accounts.change_password(session, session.get(User, user.id), body.current_password, body.new_password,
                                 request.cookies.get(COOKIE))
    except AuthError as e:
        _err(e)
    return {"ok": True}


# ---- admin: users and invites ---------------------------------------------------------------
@router.get("/users", response_model=list[UserOut], dependencies=[Depends(require_admin)])
def users(session: Session = Depends(get_session)) -> list[UserOut]:
    return [_user(u) for u in session.scalars(select(User).order_by(User.created_at))]


@router.patch("/users/{user_id}", response_model=UserOut)
def patch_user(user_id: int, body: UserPatch, admin: User = Depends(require_admin),
               session: Session = Depends(get_session)) -> UserOut:
    try:
        return _user(accounts.update_user(session, admin, user_id, body.role, body.active))
    except AuthError as e:
        _err(e)


@router.post("/users/{user_id}/reset-password", response_model=TempPasswordOut, dependencies=[Depends(require_admin)])
def reset_password(user_id: int, session: Session = Depends(get_session)) -> TempPasswordOut:
    u = session.get(User, user_id)
    if u is None:
        raise HTTPException(status_code=404, detail="User not found.")
    temp = secrets.token_urlsafe(12)
    accounts.set_password(session, u.email, temp)
    return TempPasswordOut(email=u.email, temporary_password=temp)


def _invite(session: Session, inv: Invite) -> dict:
    used = session.get(User, inv.used_by) if inv.used_by else None
    return {"id": inv.id, "hint": inv.hint, "email": inv.email, "role": inv.role,
            "status": accounts.invite_status(inv), "created_at": inv.created_at, "expires_at": inv.expires_at,
            "used_by_email": used.email if used else None}


@router.get("/invites", response_model=list[InviteOut], dependencies=[Depends(require_admin)])
def invites(session: Session = Depends(get_session)) -> list[InviteOut]:
    rows = session.scalars(select(Invite).order_by(Invite.created_at.desc())).all()
    return [InviteOut.model_validate(_invite(session, i)) for i in rows]


@router.post("/invites", response_model=NewInviteOut)
def create_invite(body: InviteIn, admin: User = Depends(require_admin),
                  session: Session = Depends(get_session)) -> NewInviteOut:
    try:
        inv, code = accounts.create_invite(session, admin.id, body.email, body.role, body.days)
    except AuthError as e:
        _err(e)
    return NewInviteOut.model_validate({**_invite(session, inv), "code": code})


@router.delete("/invites/{invite_id}", dependencies=[Depends(require_admin)])
def revoke_invite(invite_id: int, session: Session = Depends(get_session)) -> dict:
    try:
        accounts.revoke_invite(session, invite_id)
    except AuthError as e:
        _err(e)
    return {"ok": True}
