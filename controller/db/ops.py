from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Agent, ApiKey, AuditLog, Job, Token


# --- Agent ---

async def get_agent_by_id(session: AsyncSession, agent_id: str) -> Agent | None:
    result = await session.execute(select(Agent).where(Agent.agent_id == agent_id))
    return result.scalar_one_or_none()


async def get_agent_by_hostname(session: AsyncSession, hostname: str) -> Agent | None:
    result = await session.execute(select(Agent).where(Agent.hostname == hostname))
    return result.scalar_one_or_none()


async def create_agent(session: AsyncSession, **kwargs: Any) -> Agent:
    agent = Agent(**kwargs)
    session.add(agent)
    await session.commit()
    await session.refresh(agent)
    return agent


async def update_agent(session: AsyncSession, agent: Agent, **kwargs: Any) -> Agent:
    for key, value in kwargs.items():
        setattr(agent, key, value)
    agent.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(agent)
    return agent


async def get_online_agents(session: AsyncSession) -> list[Agent]:
    result = await session.execute(select(Agent).where(Agent.status == "online"))
    return list(result.scalars().all())


# --- Token ---

async def get_token_by_hash(session: AsyncSession, token_hash: str) -> Token | None:
    result = await session.execute(select(Token).where(Token.token_hash == token_hash))
    return result.scalar_one_or_none()


async def create_token(session: AsyncSession, **kwargs: Any) -> Token:
    token = Token(**kwargs)
    session.add(token)
    await session.commit()
    await session.refresh(token)
    return token


async def increment_token_uses(session: AsyncSession, token: Token) -> None:
    token.uses += 1
    await session.commit()


async def revoke_token(session: AsyncSession, token: Token) -> None:
    token.revoked_at = datetime.now(timezone.utc)
    await session.commit()


async def revoke_agent_tokens(session: AsyncSession, agent_id: str, token_type: str) -> None:
    result = await session.execute(
        select(Token).where(
            Token.agent_id == agent_id,
            Token.token_type == token_type,
            Token.revoked_at.is_(None),
        )
    )
    for token in result.scalars().all():
        token.revoked_at = datetime.now(timezone.utc)
    await session.commit()


# --- Job ---

async def get_job_by_id(session: AsyncSession, job_id: str) -> Job | None:
    result = await session.execute(select(Job).where(Job.job_id == job_id))
    return result.scalar_one_or_none()


async def create_job(session: AsyncSession, **kwargs: Any) -> Job:
    job = Job(**kwargs)
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def update_job(session: AsyncSession, job: Job, **kwargs: Any) -> Job:
    for key, value in kwargs.items():
        setattr(job, key, value)
    await session.commit()
    await session.refresh(job)
    return job


# --- ApiKey ---

async def get_api_key_by_hash(session: AsyncSession, key_hash: str) -> ApiKey | None:
    result = await session.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
    return result.scalar_one_or_none()


async def create_api_key(session: AsyncSession, **kwargs: Any) -> ApiKey:
    api_key = ApiKey(**kwargs)
    session.add(api_key)
    await session.commit()
    await session.refresh(api_key)
    return api_key


async def touch_api_key(session: AsyncSession, api_key: ApiKey) -> None:
    api_key.last_used_at = datetime.now(timezone.utc)
    await session.commit()


# --- AuditLog ---

async def create_audit_log(session: AsyncSession, **kwargs: Any) -> AuditLog:
    log = AuditLog(**kwargs)
    session.add(log)
    await session.commit()
    return log
