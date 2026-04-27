import logging
import time

from job.handlers.chat import handle_chat_completion

logger = logging.getLogger(__name__)


async def execute_job(job: dict) -> dict:
    """
    Controllerから受け取ったjobを実行してresultを返す。

    job: {"job_id": "...", "type": "chat-completion", "model": "...", "payload": {...}}

    returns: {
      "status": "completed" | "failed",
      "execution_time_ms": int,
      "usage": {...},
      "result": {...}
    }
    """
    job_type = job.get("type")
    model = job.get("model", "")
    payload = dict(job.get("payload", {}))
    payload["model"] = model  # handlerがmodelを参照できるよう付与

    start = time.monotonic()

    try:
        if job_type == "chat-completion":
            result = await handle_chat_completion(payload)
        else:
            raise ValueError(f"Unsupported job type: {job_type}")

        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {
            "status": "completed",
            "execution_time_ms": elapsed_ms,
            "usage": result.get("usage", {}),
            "result": {"message": result.get("message", {})},
        }

    except Exception as e:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.error("Job execution failed: %s", e)
        return {
            "status": "failed",
            "execution_time_ms": elapsed_ms,
            "error": str(e),
            "usage": {},
            "result": {},
        }
