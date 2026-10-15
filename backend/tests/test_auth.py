"""Login and invite-only sign-up: owner bootstrap, invites, roles, sessions, protections."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import accounts
from app.db.models import AlertReview, Invite, User, UserSession
from app.db.session import session_factory
from app.main import app
from app.pipeline.scan import run_scan
from app.pipeline.seed import seed
from conftest import ANCHOR

pytestmark = pytest.mark.real_auth
OWNER = {"email": "Owner@Example.com", "name": "Owner", "password": "owner-password-1"}
H = {"X-Requested-With": "SocialArb"}


@pytest.fixture()
def env(tmp_env, settings):
    seed(settings)
    with session_factory()() as s:
        run_scan(s, settings, as_of=ANCHOR)
    accounts.reset_rate_limits()
    yield


def client() -> TestClient:
    return TestClient(app)


def owner_client() -> TestClient:
    c = client()
    assert c.post("/api/auth/signup", json=OWNER).status_code == 200
    return c


def invite(c: TestClient, **kw) -> str:
    r = c.post("/api/auth/invites", json=kw)
    assert r.status_code == 200, r.text
    return r.json()["code"]


def test_everything_needs_a_login_except_health_and_auth(env):
    with client() as c:
        assert c.get("/api/health").status_code == 200
        assert c.get("/api/auth/status").json() == {"has_users": False, "signup_mode": "owner", "invite_required": False}
        for path in ["/api/dashboard", "/api/watchlist", "/api/tickers/CROX", "/api/feed", "/api/alerts",
                     "/api/evaluation", "/api/status", "/api/admin/companies", "/api/auth/me"]:
            assert c.get(path).status_code == 401, path
        assert c.post("/api/daily", json={}).status_code == 401


def test_first_signup_becomes_owner_then_invites_are_required(env):
    with owner_client() as c:
        me = c.get("/api/auth/me").json()
        assert me["role"] == "admin" and me["email"] == "owner@example.com"
        assert c.get("/api/dashboard").status_code == 200
        assert c.get("/api/auth/status").json()["invite_required"] is True
        code = invite(c)
        targeted = invite(c, email="ann@example.com")
    with client() as anon:
        new = {"email": "bob@example.com", "name": "Bob", "password": "bob-password-12"}
        assert anon.post("/api/auth/signup", json=new).status_code == 403                       # no code
        assert anon.post("/api/auth/signup", json={**new, "invite_code": "WRONG-CODE"}).status_code == 403
        assert anon.post("/api/auth/signup", json={**new, "invite_code": targeted}).status_code == 403  # other email
        r = anon.post("/api/auth/signup", json={**new, "invite_code": code.lower().replace("-", "")})
        assert r.status_code == 200 and r.json()["role"] == "member"
    with client() as again:
        r = again.post("/api/auth/signup", json={"email": "eve@example.com", "password": "eve-password-12",
                                                 "invite_code": code})
        assert r.status_code == 403                                                              # single use


def test_members_can_view_and_decide_but_not_administer(env):
    with owner_client() as owner:
        code = invite(owner)
        alert_id = owner.get("/api/feed").json()["groups"][0]["cards"][0]["alert_id"]
    with client() as m:
        m.post("/api/auth/signup", json={"email": "m@example.com", "password": "member-pass-12", "invite_code": code})
        assert m.get("/api/dashboard").status_code == 200
        assert m.post(f"/api/alerts/{alert_id}/review", json={"decision": "acted"}).status_code == 200
        assert m.post("/api/daily", json={}).status_code == 403
        assert m.post("/api/scan", json={}).status_code == 403
        assert m.get("/api/admin/companies").status_code == 403
        assert m.post("/api/auth/invites", json={}).status_code == 403
        me = m.get("/api/auth/me").json()
    with session_factory()() as s:
        r = s.scalars(select(AlertReview).where(AlertReview.alert_id == alert_id)).all()[-1]
        assert r.user_id == me["id"]


def test_login_logout_and_generic_errors(env):
    owner_client().close()
    with client() as c:
        bad = c.post("/api/auth/login", json={"email": OWNER["email"], "password": "wrong-password"})
        unknown = c.post("/api/auth/login", json={"email": "nobody@example.com", "password": "wrong-password"})
        assert bad.status_code == unknown.status_code == 401
        assert bad.json()["detail"] == unknown.json()["detail"]          # doesn't reveal which emails exist
        ok = c.post("/api/auth/login", json={"email": "owner@example.com", "password": OWNER["password"]})
        assert ok.status_code == 200 and "httponly" in ok.headers["set-cookie"].lower()
        assert "samesite=lax" in ok.headers["set-cookie"].lower()
        assert c.get("/api/dashboard").status_code == 200
        assert c.post("/api/auth/logout", json={}).status_code == 200
        assert c.get("/api/dashboard").status_code == 401


def test_rate_limit_on_failed_logins(env):
    owner_client().close()
    with client() as c:
        codes = [c.post("/api/auth/login", json={"email": OWNER["email"], "password": "nope-nope-nope"}).status_code
                 for _ in range(9)]
        assert codes[:8] == [401] * 8 and codes[8] == 429


def test_rate_limit_ignores_spoofed_ip_headers(env, monkeypatch):
    owner_client().close()
    bad = {"email": OWNER["email"], "password": "nope-nope-nope"}
    with client() as c:
        codes = [c.post("/api/auth/login", json=bad, headers={"cf-connecting-ip": f"10.0.0.{i}"}).status_code
                 for i in range(9)]
        assert codes[8] == 429   # header not trusted unless configured
    accounts.reset_rate_limits()
    monkeypatch.setenv("SOCIALARB_BEHIND_CLOUDFLARE", "1")
    with client() as c:   # trusted header, rotating IPs: the per-email cap still applies
        codes = [c.post("/api/auth/login", json=bad, headers={"cf-connecting-ip": f"10.0.1.{i}"}).status_code
                 for i in range(31)]
        assert codes[:30] == [401] * 30 and codes[30] == 429


def test_cookie_is_secure_behind_https_proxy(env):
    with client() as c:
        r = c.post("/api/auth/signup", json=OWNER, headers={"x-forwarded-proto": "https"})
        assert "secure" in r.headers["set-cookie"].lower()


def test_cross_site_style_writes_are_blocked(env):
    with owner_client() as c:
        r = c.post("/api/evaluate", content="x=1", headers={"content-type": "application/x-www-form-urlencoded"})
        assert r.status_code == 403
        assert c.post("/api/evaluate", headers=H).status_code == 200
        r = c.post("/api/auth/logout", content="x", headers={"content-type": "text/plain"})
        assert r.status_code == 403


def test_secrets_are_stored_hashed(env):
    with owner_client() as c:
        token = c.cookies.get("socialarb_session")
        code = invite(c)
    with session_factory()() as s:
        u = s.scalar(select(User))
        assert OWNER["password"] not in u.password_hash and u.password_hash.startswith("scrypt$")
        assert s.scalar(select(UserSession)).token_hash != token
        assert all(code.replace("-", "") not in i.code_hash for i in s.scalars(select(Invite)))


def test_change_password_signs_out_other_browsers(env):
    owner_client().close()
    with client() as a, client() as b:
        for x in (a, b):
            x.post("/api/auth/login", json={"email": OWNER["email"], "password": OWNER["password"]})
        assert a.post("/api/auth/password", json={"current_password": "wrong", "new_password": "x" * 12}).status_code == 400
        assert a.post("/api/auth/password", json={"current_password": OWNER["password"],
                                                  "new_password": "short"}).status_code == 400
        assert a.post("/api/auth/password", json={"current_password": OWNER["password"],
                                                  "new_password": "brand-new-pass-9"}).status_code == 200
        assert a.get("/api/dashboard").status_code == 200      # this browser stays signed in
        assert b.get("/api/dashboard").status_code == 401      # the other one is signed out
    with client() as c:
        assert c.post("/api/auth/login", json={"email": OWNER["email"], "password": "brand-new-pass-9"}).status_code == 200


def test_admin_user_management(env):
    with owner_client() as owner:
        code = invite(owner)
        with client() as m:
            m.post("/api/auth/signup", json={"email": "m@example.com", "password": "member-pass-12", "invite_code": code})
            users = {u["email"]: u for u in owner.get("/api/auth/users").json()}
            mid, oid = users["m@example.com"]["id"], users["owner@example.com"]["id"]
            assert owner.patch(f"/api/auth/users/{oid}", json={"role": "member"}).status_code == 409   # last admin
            assert owner.patch(f"/api/auth/users/{mid}", json={"active": False}).status_code == 200
            assert m.get("/api/dashboard").status_code == 401                                         # deactivated
            owner.patch(f"/api/auth/users/{mid}", json={"active": True})
            temp = owner.post(f"/api/auth/users/{mid}/reset-password", headers=H).json()["temporary_password"]
            assert m.post("/api/auth/login", json={"email": "m@example.com", "password": temp}).status_code == 200
        inv = owner.get("/api/auth/invites").json()
        assert inv[0]["status"] == "used" and inv[0]["used_by_email"] == "m@example.com"
        open_code = invite(owner)
        oid_inv = owner.get("/api/auth/invites").json()[0]["id"]
        assert owner.delete(f"/api/auth/invites/{oid_inv}", headers=H).status_code == 200
    with client() as late:
        r = late.post("/api/auth/signup", json={"email": "z@example.com", "password": "zed-password-12",
                                                "invite_code": open_code})
        assert r.status_code == 403                                                                    # revoked


def test_expired_session_and_invite(env):
    with owner_client() as c:
        code = invite(c)
        with session_factory()() as s:
            for x in s.scalars(select(UserSession)):
                x.expires_at = x.expires_at - timedelta(days=30)
            for i in s.scalars(select(Invite)):
                i.expires_at = i.expires_at - timedelta(days=30)
            s.commit()
        assert c.get("/api/dashboard").status_code == 401
    with client() as anon:
        r = anon.post("/api/auth/signup", json={"email": "q@example.com", "password": "qqq-password-12", "invite_code": code})
        assert r.status_code == 403


def test_signup_modes(env, monkeypatch):
    owner_client().close()
    monkeypatch.setenv("SOCIALARB_SIGNUP", "closed")
    with client() as c:
        assert c.post("/api/auth/signup", json={"email": "a@example.com", "password": "aaa-password-12"}).status_code == 403
    monkeypatch.setenv("SOCIALARB_SIGNUP", "open")
    with client() as c:
        r = c.post("/api/auth/signup", json={"email": "a@example.com", "password": "aaa-password-12"})
        assert r.status_code == 200 and r.json()["role"] == "member"
