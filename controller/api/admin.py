import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import require_admin
from core.auth import generate_api_key, generate_invitation_token, hash_token
from db.base import get_session
from db.models import ApiKey
from db.ops import create_api_key, create_token, get_online_agents

router = APIRouter()


class InviteTokenRequest(BaseModel):
    pool_id: str = "default"
    expires_in_days: int = 7
    max_uses: int = 1


class CreateApiKeyRequest(BaseModel):
    name: str
    user_id: str
    scopes: list[str] = []
    expires_in_days: int | None = 365


@router.post("/tokens/invite", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
async def create_invite_token(
    body: InviteTokenRequest,
    session: AsyncSession = Depends(get_session),
):
    now = datetime.now(timezone.utc)
    raw_token = generate_invitation_token()
    expires_at = now + timedelta(days=body.expires_in_days)

    await create_token(
        session,
        token_id="tok-" + str(uuid.uuid4()),
        token_type="invitation",
        agent_id=None,
        token_hash=hash_token(raw_token),
        pool_id=body.pool_id,
        max_uses=body.max_uses,
        uses=0,
        expires_at=expires_at,
        created_at=now,
    )

    return {
        "token": raw_token,
        "pool_id": body.pool_id,
        "expires_at": expires_at.isoformat(),
        "max_uses": body.max_uses,
    }


@router.post("/api-keys", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
async def create_api_key_endpoint(
    body: CreateApiKeyRequest,
    session: AsyncSession = Depends(get_session),
):
    now = datetime.now(timezone.utc)
    raw_key = generate_api_key()
    expires_at = now + timedelta(days=body.expires_in_days) if body.expires_in_days else None

    api_key_id = "key-" + str(uuid.uuid4())
    await create_api_key(
        session,
        api_key_id=api_key_id,
        user_id=body.user_id,
        key_hash=hash_token(raw_key),
        name=body.name,
        scopes=body.scopes,
        rate_limit_rpm=60,
        created_at=now,
        expires_at=expires_at,
    )

    return {
        "api_key_id": api_key_id,
        "key": raw_key,
        "name": body.name,
        "scopes": body.scopes,
        "created_at": now.isoformat(),
        "expires_at": expires_at.isoformat() if expires_at else None,
    }


@router.get("/agents", dependencies=[Depends(require_admin)])
async def list_agents(
    session: AsyncSession = Depends(get_session),
):
    from sqlalchemy import select
    from db.models import Agent

    result = await session.execute(select(Agent))
    agents = result.scalars().all()
    return {
        "agents": [
            {
                "agent_id": a.agent_id,
                "hostname": a.hostname,
                "status": a.status,
                "available_models": a.available_models or [],
                "last_seen_at": a.last_seen_at.isoformat() if a.last_seen_at else None,
            }
            for a in agents
        ],
        "total": len(agents),
    }
