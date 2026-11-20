"""Passwords (bcrypt) and session tokens (JWT)."""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def make_token(user_id: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=settings().jwt_hours)
    return jwt.encode({"sub": user_id, "exp": exp}, settings().jwt_secret, algorithm="HS256")


def read_token(token: str) -> str | None:
    try:
        return jwt.decode(token, settings().jwt_secret, algorithms=["HS256"]).get("sub")
    except jwt.PyJWTError:
        return None
