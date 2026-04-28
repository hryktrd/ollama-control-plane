from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.auth import hash_token, verify_listener_token
from core.config import settings
from db.base import get_session
from db.models import Agent, ApiKey
from db.ops import get_agent_by_id, get_api_key_by_hash, touch_api_key
from sqlalchemy.ext.asyncio import AsyncSession

bearer = HTTPBearer()


async def require_listener_token(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
) -> dict:
    return verify_listener_token(credentials.credentials)


async def require_admin(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
) -> None:
    if credentials.credentials != settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "error_description": "Invalid admin API key"},
        )


async def _validate_api_key(raw_key: str, session: AsyncSession) -> ApiKey:
    key_hash = hash_token(raw_key)
    api_key = await get_api_key_by_hash(session, key_hash)
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "error_description": "API key not found"},
        )
    if api_key.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "error_description": "API key revoked"},
        )
    if api_key.expires_at is not None:
        expires_at = api_key.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "invalid_token", "error_description": "API key expired"},
            )
    await touch_api_key(session, api_key)
    return api_key


async def require_api_key(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    session: AsyncSession = Depends(get_session),
) -> ApiKey:
    return await _validate_api_key(credentials.credentials, session)


async def require_api_key_anthropic(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ApiKey:
    # Anthropic clients use x-api-key; fall back to Authorization: Bearer
    raw_key = request.headers.get("x-api-key")
    if not raw_key:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            raw_key = auth[7:].strip()
    if not raw_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "error_description": "API key required (x-api-key or Authorization: Bearer)"},
        )
    return await _validate_api_key(raw_key, session)


def get_client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("X-Real-IP") or request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None
