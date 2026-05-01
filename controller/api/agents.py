import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_client_ip, require_listener_token
from core.auth import (
    create_listener_token,
    generate_refresh_token,
    hash_token,
)
from core.config import settings
from core.scheduler import scheduler
from db.base import get_session
from db.ops import (
    create_agent,
    create_audit_log,
    create_token,
    get_agent_by_hostname,
    get_agent_by_id,
    get_token_by_hash,
    increment_token_uses,
    revoke_agent_tokens,
    update_agent,
)

router = APIRouter()


class RegisterRequest(BaseModel):
    hostname: str
    available_models: list[str] = []
    capabilities: dict = {}
    resources: dict = {}


class PollRequest(BaseModel):
    agent_id: str
    status: str = "idle"
    current_jobs: int = 0
    available_slots: int = 1
    available_models: list[str] = []
    resource_info: dict = {}


class TokenRefreshRequest(BaseModel):
    agent_id: str
    refresh_token: str


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_agent(
    body: RegisterRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "error_description": "Missing Bearer token"},
        )
    raw_token = auth_header.removeprefix("Bearer ").strip()
    token_hash = hash_token(raw_token)

    inv_token = await get_token_by_hash(session, token_hash)
    if inv_token is None or inv_token.token_type != "invitation":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "error_description": "Token expired or not found"},
        )
    if inv_token.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "error_description": "Token revoked"},
        )
    if inv_token.uses >= inv_token.max_uses:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "error_description": "Token max uses exceeded"},
        )
    if inv_token.expires_at is not None:
        expires_at = inv_token.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "invalid_token", "error_description": "Token expired"},
            )

    await increment_token_uses(session, inv_token)
    pool_id = inv_token.pool_id or "default"

    existing_agent = await get_agent_by_hostname(session, body.hostname)
    now = datetime.now(timezone.utc)

    if existing_agent is not None:
        agent = await update_agent(
            session,
            existing_agent,
            status="registered",
            available_models=body.available_models,
            capabilities=body.capabilities,
            resources=body.resources,
            pool_id=pool_id,
            updated_at=now,
        )
    else:
        agent_id = "ag-" + str(uuid.uuid4())
        agent = await create_agent(
            session,
            agent_id=agent_id,
            pool_id=pool_id,
            hostname=body.hostname,
            status="registered",
            available_models=body.available_models,
            capabilities=body.capabilities,
            resources=body.resources,
            created_at=now,
            updated_at=now,
        )

    scheduler.register_agent(agent.agent_id)

    # Revoke old refresh tokens for this agent so only the newest is valid.
    await revoke_agent_tokens(session, agent.agent_id, "refresh")

    listener_jwt = create_listener_token(agent.agent_id, pool_id)
    refresh_raw = generate_refresh_token()

    await create_token(
        session,
        token_id="tok-" + str(uuid.uuid4()),
        token_type="refresh",
        agent_id=agent.agent_id,
        token_hash=hash_token(refresh_raw),
        pool_id=pool_id,
        max_uses=9999,
        uses=0,
        expires_at=now + timedelta(days=30),
        created_at=now,
    )

    await create_audit_log(
        session,
        log_id="log-" + str(uuid.uuid4()),
        event_type="agent_registered",
        actor_type="agent",
        actor_id=agent.agent_id,
        resource_type="agent",
        resource_id=agent.agent_id,
        details={"hostname": body.hostname, "pool_id": pool_id},
        status="success",
        ip_address=get_client_ip(request),
        timestamp=now,
    )

    return {
        "agent_id": agent.agent_id,
        "pool_id": pool_id,
        "listener_token": listener_jwt,
        "refresh_token": refresh_raw,
        "expires_in": settings.listener_token_ttl_hours * 3600,
        "poll_interval": settings.poll_timeout_seconds,
        "available_models": body.available_models,
    }


@router.post("/poll")
async def poll_for_job(
    body: PollRequest,
    claims: dict = Depends(require_listener_token),
    session: AsyncSession = Depends(get_session),
):
    agent_id = claims["sub"]
    now = datetime.now(timezone.utc)

    agent = await get_agent_by_id(session, agent_id)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_agent", "error_description": "Agent not found"},
        )

    update_kwargs: dict = {
        "status": "online",
        "resource_info": body.resource_info,
        "last_seen_at": now,
    }
    if body.available_models:
        update_kwargs["available_models"] = body.available_models
    await update_agent(session, agent, **update_kwargs)

    # Register in scheduler in case this is a fresh process restart.
    scheduler.register_agent(agent_id)

    job = await scheduler.poll(agent_id, timeout=float(settings.poll_timeout_seconds))
    if job is None:
        from fastapi.responses import Response
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return job


@router.post("/token/refresh")
async def refresh_token(
    body: TokenRefreshRequest,
    session: AsyncSession = Depends(get_session),
):
    token_hash = hash_token(body.refresh_token)
    ref_token = await get_token_by_hash(session, token_hash)

    if ref_token is None or ref_token.token_type != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "error_description": "Refresh token not found"},
        )
    if ref_token.agent_id != body.agent_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "error_description": "Token does not belong to agent"},
        )
    if ref_token.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "error_description": "Refresh token revoked"},
        )
    if ref_token.expires_at is not None:
        expires_at = ref_token.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "invalid_token", "error_description": "Refresh token expired"},
            )

    agent = await get_agent_by_id(session, body.agent_id)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "not_found", "error_description": "Agent not found"},
        )

    pool_id = ref_token.pool_id or agent.pool_id or "default"
    new_listener_jwt = create_listener_token(body.agent_id, pool_id)

    # Rotate refresh token.
    await revoke_agent_tokens(session, body.agent_id, "refresh")
    new_refresh_raw = generate_refresh_token()
    now = datetime.now(timezone.utc)
    await create_token(
        session,
        token_id="tok-" + str(uuid.uuid4()),
        token_type="refresh",
        agent_id=body.agent_id,
        token_hash=hash_token(new_refresh_raw),
        pool_id=pool_id,
        max_uses=9999,
        uses=0,
        expires_at=now + timedelta(days=30),
        created_at=now,
    )

    return {
        "listener_token": new_listener_jwt,
        "expires_in": settings.listener_token_ttl_hours * 3600,
        "refresh_token": new_refresh_raw,
    }
