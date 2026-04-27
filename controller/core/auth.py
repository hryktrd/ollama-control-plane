import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from jose import JWTError, jwt

from core.config import settings


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_invitation_token() -> str:
    return "inv_" + secrets.token_urlsafe(32)


def generate_refresh_token() -> str:
    return "ref_" + secrets.token_urlsafe(32)


def generate_api_key() -> str:
    return "sk-proj-" + secrets.token_urlsafe(48)


def create_listener_token(agent_id: str, pool_id: str) -> str:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=settings.listener_token_ttl_hours)
    payload = {
        "sub": agent_id,
        "pool_id": pool_id,
        "type": "listener",
        "iat": now,
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.controller_secret, algorithm=settings.jwt_algorithm)


def verify_listener_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.controller_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "error_description": "Token invalid or expired"},
        )
    if payload.get("type") != "listener":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "error_description": "Token type must be listener"},
        )
    return payload
