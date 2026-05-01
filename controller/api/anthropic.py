import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Union

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import require_api_key_anthropic
from core.config import settings
from core.scheduler import scheduler
from db.base import get_session
from db.models import ApiKey
from db.ops import create_audit_log, create_job, get_online_agents, update_job

router = APIRouter()


class TextContentBlock(BaseModel):
    type: str = "text"
    text: str


class AnthropicMessage(BaseModel):
    role: str
    content: Union[str, list[TextContentBlock]]


class AnthropicMessagesRequest(BaseModel):
    model: str
    max_tokens: int
    messages: list[AnthropicMessage]
    system: str | None = None
    temperature: float | None = None
    stream: bool = False


def _normalize_content(content: Union[str, list[TextContentBlock]]) -> str:
    if isinstance(content, str):
        return content
    return "".join(block.text for block in content if block.type == "text")


@router.post("/messages")
async def messages(
    body: AnthropicMessagesRequest,
    request: Request,
    api_key: ApiKey = Depends(require_api_key_anthropic),
    session: AsyncSession = Depends(get_session),
):
    if body.stream:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "streaming_not_supported", "error_description": "Streaming is not supported in the current version"},
        )

    job_messages = []
    if body.system:
        job_messages.append({"role": "system", "content": body.system})
    for msg in body.messages:
        job_messages.append({"role": msg.role, "content": _normalize_content(msg.content)})

    online_agents = await get_online_agents(session)
    matching_agents = [
        a for a in online_agents
        if a.available_models and body.model in a.available_models
    ]
    if not matching_agents:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "no_agent_available", "error_description": f"No online agent has model {body.model!r}"},
        )

    target_agent = matching_agents[0]
    now = datetime.now(timezone.utc)
    job_id = "job-" + str(uuid.uuid4())

    payload = {
        "messages": job_messages,
        "temperature": body.temperature,
        "max_tokens": body.max_tokens,
        "stream": False,
    }

    job = await create_job(
        session,
        job_id=job_id,
        agent_id=target_agent.agent_id,
        job_type="chat-completion",
        model=body.model,
        status="pending",
        priority="normal",
        payload=payload,
        created_at=now,
    )

    job_dict = {
        "job_id": job_id,
        "type": "chat-completion",
        "model": body.model,
        "timeout_seconds": settings.job_timeout_seconds,
        "priority": "normal",
        "payload": payload,
    }

    await update_job(session, job, status="running", started_at=now)
    await scheduler.dispatch(target_agent.agent_id, job_dict)

    try:
        result = await scheduler.wait_result(job_id, timeout=float(settings.job_timeout_seconds))
    except asyncio.TimeoutError:
        await update_job(session, job, status="timeout", completed_at=datetime.now(timezone.utc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "timeout", "error_description": "Job timed out waiting for agent"},
        )

    if result is None or result.get("status") == "failed":
        error_msg = (result or {}).get("error", "Unknown error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "job_failed", "error_description": error_msg},
        )

    message_data = (result.get("result") or {}).get("message", {})
    usage_data = result.get("usage") or {}
    content_text = message_data.get("content", "")

    await create_audit_log(
        session,
        log_id="log-" + str(uuid.uuid4()),
        event_type="anthropic_message",
        actor_type="api_key",
        actor_id=api_key.api_key_id,
        resource_type="job",
        resource_id=job_id,
        details={"model": body.model},
        status="success",
        timestamp=datetime.now(timezone.utc),
    )

    return {
        "id": "msg-" + str(uuid.uuid4()),
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": content_text}],
        "model": body.model,
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage_data.get("prompt_tokens", 0),
            "output_tokens": usage_data.get("completion_tokens", 0),
        },
    }
