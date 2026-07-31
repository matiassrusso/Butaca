import hashlib
import hmac
import secrets
import sqlite3
import time

from fastapi import Header, HTTPException

from . import db

PBKDF2_ITERATIONS = 260_000
RESET_TOKEN_TTL_SECONDS = 60 * 60
# email verification links live longer than a reset — people open signup mail late
EMAIL_VERIFICATION_TTL_SECONDS = 24 * 60 * 60


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS
    )
    return derived.hex(), salt


def verify_password(password: str, password_hash: str, password_salt: str) -> bool:
    candidate, _ = hash_password(password, password_salt)
    return hmac.compare_digest(candidate, password_hash)


def create_token() -> str:
    return secrets.token_urlsafe(32)


def create_password_reset_token() -> tuple[str, str]:
    token = create_token()
    return token, hash_token(token)


def create_email_verification_token() -> tuple[str, str]:
    token = create_token()
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def now_ts() -> int:
    return int(time.time())


def login_lock_seconds(failed_attempts: int) -> int:
    if failed_attempts < 3:
        return 0
    return min(30 * (2 ** (failed_attempts - 3)), 15 * 60)


def get_current_user(authorization: str | None = Header(default=None)) -> sqlite3.Row:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Falta autenticación.")

    token = authorization.removeprefix("Bearer ").strip()
    user = db.get_user_by_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada.")

    return user


def get_optional_user(authorization: str | None = Header(default=None)) -> sqlite3.Row | None:
    """Como get_current_user, pero para endpoints públicos que personalizan
    SI hay sesión en vez de exigirla — nunca 401, devuelve None sin token o
    con uno inválido/expirado en vez de cortar la request."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return db.get_user_by_token(authorization.removeprefix("Bearer ").strip())
