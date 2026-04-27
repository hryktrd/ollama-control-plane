import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import require_listener_token
from core.scheduler import scheduler
from db.base import get_session
from db.ops import create_audit_log, get_job_by_id, update_job

router = APIRouter()


class JobResultRequest(BaseModel):
    agent_id: str
    status: str
    execution_time_ms: int | None = None
    usage: dict | None = None
    result: dict | None = None
    error: str | None = None


@router.post("/{job_id}/result")
async def submit_job_result(
    job_id: str,
    body: JobResultRequest,
    claims: dict = Depends(require_listener_token),
    session: AsyncSession = Depends(get_session),
):
    agent_id = claims["sub"]
    if body.agent_id != agent_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "forbidden", "error_description": "agent_id does not match token"},
        )

    job = await get_job_by_id(session, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "not_found", "error_description": "Job not found"},
        )
    if job.agent_id != agent_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "forbidden", "error_description": "Job does not belong to agent"},
        )

    now = datetime.now(timezone.utc)
    await update_job(
        session,
        job,
        status=body.status,
        result=body.result,
        error=body.error,
        execution_time_ms=body.execution_time_ms,
        completed_at=now,
    )

    result_payload = {
        "result": body.result,
        "usage": body.usage,
        "status": body.status,
        "error": body.error,
    }
    scheduler.complete(job_id, result_payload)

    await create_audit_log(
        session,
        log_id="log-" + str(uuid.uuid4()),
        event_type="job_completed",
        actor_type="agent",
        actor_id=agent_id,
        resource_type="job",
        resource_id=job_id,
        details={"status": body.status, "execution_time_ms": body.execution_time_ms},
        status="success",
        timestamp=now,
    )

    return {"status": "accepted"}
