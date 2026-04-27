import asyncio
import logging

import httpx
import psutil

from auth.token import is_token_expiring_soon, save_config
from config.settings import settings
from job.executor import execute_job

logger = logging.getLogger(__name__)

BACKOFF_INITIAL = 1.0
BACKOFF_MAX = 60.0


async def polling_loop(agent_state: dict) -> None:
    """
    メインポーリングループ。agent_stateには以下が含まれる:
      agent_id, pool_id, listener_token, refresh_token, poll_interval

    シグナルで中断されるまでループを継続する。
    """
    backoff = BACKOFF_INITIAL

    while True:
        try:
            # トークン期限が30分以内なら先にリフレッシュ
            if is_token_expiring_soon(agent_state["listener_token"]):
                await _refresh_token(agent_state)

            job = await _poll_once(agent_state)

            if job is not None:
                logger.info("Received job %s (model=%s)", job["job_id"], job.get("model"))
                result = await execute_job(job)
                await _submit_result(agent_state, job["job_id"], result)

            backoff = BACKOFF_INITIAL  # 成功したらリセット

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.warning("Listener token rejected, refreshing...")
                try:
                    await _refresh_token(agent_state)
                except Exception as refresh_err:
                    logger.error("Token refresh failed: %s", refresh_err)
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, BACKOFF_MAX)
            else:
                logger.error("HTTP error during poll: %s", e)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, BACKOFF_MAX)

        except (httpx.ConnectError, httpx.TimeoutException) as e:
            logger.warning("Controller unreachable: %s", e)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, BACKOFF_MAX)

        except Exception as e:
            logger.error("Unexpected polling error: %s", e)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, BACKOFF_MAX)


async def _poll_once(agent_state: dict) -> dict | None:
    """
    Controller に POST /agents/poll を送信する。
    200 → job dict を返す。204 → None。その他 → raise HTTPStatusError。
    """
    cpu_load = psutil.cpu_percent(interval=None) / 100

    payload = {
        "agent_id": agent_state["agent_id"],
        "status": "idle",
        "current_jobs": 0,
        "available_slots": settings.max_concurrent_jobs,
        "resource_info": {
            "cpu_load": cpu_load,
            "gpu_utilization": 0.0,
            "gpu_vram_used_mb": 0,
            "memory_used_mb": int(psutil.virtual_memory().used / 1024 / 1024),
            "loaded_models": [],
        },
    }

    # read タイムアウトはポーリング間隔 + 余裕を持たせる
    timeout = httpx.Timeout(
        connect=10.0,
        read=float(agent_state["poll_interval"]) + 10,
        write=10.0,
        pool=5.0,
    )

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{settings.controller_url}/agents/poll",
            json=payload,
            headers={"Authorization": f"Bearer {agent_state['listener_token']}"},
        )

    if resp.status_code == 204:
        return None
    resp.raise_for_status()
    return resp.json()


async def _submit_result(agent_state: dict, job_id: str, result: dict) -> None:
    """
    Controller に POST /jobs/{job_id}/result を送信する。最大3回リトライ。
    """
    body = {"agent_id": agent_state["agent_id"], **result}

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{settings.controller_url}/jobs/{job_id}/result",
                    json=body,
                    headers={"Authorization": f"Bearer {agent_state['listener_token']}"},
                )
                resp.raise_for_status()
                return
        except Exception as e:
            if attempt < 2:
                await asyncio.sleep(2**attempt)
            else:
                logger.error(
                    "Failed to submit result for job %s after 3 attempts: %s",
                    job_id,
                    e,
                )


async def _refresh_token(agent_state: dict) -> None:
    """
    POST /agents/token/refresh を呼び出し、agent_state と設定ファイルを更新する。
    """
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{settings.controller_url}/agents/token/refresh",
            json={
                "agent_id": agent_state["agent_id"],
                "refresh_token": agent_state["refresh_token"],
            },
        )
        resp.raise_for_status()

    data = resp.json()
    agent_state["listener_token"] = data["listener_token"]
    if "refresh_token" in data:
        agent_state["refresh_token"] = data["refresh_token"]

    save_config(agent_state)
    logger.info("Listener token refreshed successfully")
