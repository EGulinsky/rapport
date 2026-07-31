"""
Passwort-Hashing (bcrypt via passlib) sowie JWT-Erstellung/-Prüfung.

JWT_SECRET_KEY wird — analog zum bestehenden fernet.key-Muster in
app/ai/provider.py — automatisch generiert und neben der DB abgelegt, wenn
keine Umgebungsvariable gesetzt ist.
"""
from __future__ import annotations

import os
import pathlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_DATA_DIR = pathlib.Path(
    os.getenv("DATABASE_URL", "sqlite:///./data/jobtracker.db")
    .replace("sqlite:///", "")
    .replace("sqlite://", "")
).parent

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 60 * 24 * 7  # 7 Tage


def _jwt_secret() -> str:
    env_key = os.getenv("JWT_SECRET_KEY")
    if env_key:
        return env_key
    key_file = _DATA_DIR / "jwt_secret.key"
    if key_file.exists():
        return key_file.read_text().strip()
    key = secrets.token_urlsafe(48)
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_text(key)
    return key


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[int]:
    """Return the user id encoded in the token, or None if invalid/expired."""
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None
    sub = payload.get("sub")
    if sub is None:
        return None
    try:
        return int(sub)
    except ValueError:
        return None
