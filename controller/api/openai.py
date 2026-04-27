import asyncio
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import require_api_key
from core.config import settings
from core.scheduler import scheduler
from db.base import get_session
from db.models import ApiKey
from db.ops import create_audit_log, create_job, get_online_agents, update_job

router = APIRouter()


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    temperature: float | None = None
    max_tokens: int | None = None
    stream: bool = False


@router.post("/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest,
    api_key: ApiKey = Depends(require_api_key),
    session: AsyncSession = Depends(get_session),
):
    # Find an online agent that has the requested model.
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
        "messages": [m.model_dump() for m in body.messages],
        "temperature": body.temperature,
        "max_tokens": body.max_tokens,
        "stream": False,  # streaming not supported in MVP
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

    await create_audit_log(
        session,
        log_id="log-" + str(uuid.uuid4()),
        event_type="chat_completion",
        actor_type="api_key",
        actor_id=api_key.api_key_id,
        resource_type="job",
        resource_id=job_id,
        details={"model": body.model},
        status="success",
        timestamp=datetime.now(timezone.utc),
    )

    return {
        "id": "chatcmpl-" + str(uuid.uuid4()),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": body.model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": message_data.get("role", "assistant"),
                    "content": message_data.get("content", ""),
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": usage_data.get("prompt_tokens", 0),
            "completion_tokens": usage_data.get("completion_tokens", 0),
            "total_tokens": usage_data.get("total_tokens", 0),
        },
    }


@router.get("/models")
async def list_models(
    api_key: ApiKey = Depends(require_api_key),
    session: AsyncSession = Depends(get_session),
):
    online_agents = await get_online_agents(session)
    seen: set[str] = set()
    model_list = []
    for agent in online_agents:
        for model_name in (agent.available_models or []):
            if model_name not in seen:
                seen.add(model_name)
                model_list.append(
                    {
                        "id": model_name,
                        "object": "model",
                        "created": int(time.time()),
                        "owned_by": "control-plane",
                    }
                )

    return {"object": "list", "data": model_list}
