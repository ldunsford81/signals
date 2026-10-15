"""Password hashing and tokens, standard library only.

Passwords: scrypt (n=2**14, r=8, p=1, 16-byte salt), stored as "scrypt$n$r$p$salt$hash" (hex).
Tokens: 32 random bytes, URL-safe. Only their SHA-256 is stored, so a leaked database can't be used
to sign in.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

N, R, P, DKLEN = 2**14, 8, 1, 32
MIN_PASSWORD = 10


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P, dklen=DKLEN)
    return f"scrypt${N}${R}${P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, digest = stored.split("$")
        if algo != "scrypt":
            return False
        got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p),
                             dklen=len(bytes.fromhex(digest)))
        return hmac.compare_digest(got.hex(), digest)
    except (ValueError, TypeError):
        return False


# A real hash of a random password, checked when the email is unknown so both paths take the same time.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_invite_code() -> str:
    # 15 chars from an unambiguous alphabet, grouped for reading aloud: XXXXX-XXXXX-XXXXX
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    raw = "".join(secrets.choice(alphabet) for _ in range(15))
    return f"{raw[:5]}-{raw[5:10]}-{raw[10:]}"


def normalize_code(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


def password_problem(password: str, email: str = "") -> str | None:
    if len(password) < MIN_PASSWORD:
        return f"Use at least {MIN_PASSWORD} characters."
    if len(password) > 256:
        return "That password is too long."
    if email and password.lower() == email.lower():
        return "Don't use your email as your password."
    if len(set(password)) < 4:
        return "That password is too easy to guess."
    return None
