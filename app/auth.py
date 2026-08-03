import secrets
import time
from typing import Dict

import bcrypt
from fastapi import Header, HTTPException, status

# token -> (admin_id, expires_at)
_sessions: Dict[str, tuple[str, float]] = {}

SESSION_TTL_SECONDS = 12 * 60 * 60  # 12 hours


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_session(admin_id: str) -> str:
    token = secrets.token_urlsafe(32)
    _sessions[token] = (admin_id, time.time() + SESSION_TTL_SECONDS)
    return token


def require_admin(authorization: str = Header(default="")) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    token = authorization.removeprefix("Bearer ").strip()
    session = _sessions.get(token)
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")
    admin_id, expires_at = session
    if time.time() > expires_at:
        _sessions.pop(token, None)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")
    return admin_id
