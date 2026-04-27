import logging

import httpx
import psutil

from auth.token import load_config, save_config
from config.settings import settings
from core.ollama import ollama
from core.poller import polling_loop

logger = logging.getLogger(__name__)


async def run() -> None:
    """
    Agent Hostのメインエントリー。
    1. Ollamaの起動確認
    2. 設定ファイルに保存済みagent_idがあれば直接ポーリングへ
    3. なければ招待トークンで登録
    4. ポーリングループ開始
    """
    logger.info("Starting agent host...")

    # Ollama起動確認
    if not await ollama.is_available():
        logger.error("Ollama is not available at %s. Exiting.", settings.ollama_url)
        raise SystemExit(1)

    models = await ollama.list_models()
    logger.info("Discovered Ollama models: %s", models)

    # 保存済み設定を確認
    agent_state = load_config()

    if agent_state is None:
        if not settings.invitation_token:
            logger.error("No saved config and INVITATION_TOKEN is not set. Exiting.")
            raise SystemExit(1)
        agent_state = await _register(models)
    else:
        # 再起動時にモデルリストを更新（Ollamaにモデルが追加された可能性あり）
        agent_state["available_models"] = models
        logger.info("Resuming with agent_id=%s", agent_state["agent_id"])

    logger.info("Agent %s ready. Starting polling loop...", agent_state["agent_id"])
    await polling_loop(agent_state)


async def _register(models: list[str]) -> dict:
    """
    POST /agents/register を呼んでagent_stateを取得・保存する。
    """
    payload = {
        "hostname": settings.hostname,
        "available_models": models,
        "capabilities": {"max_concurrent_jobs": settings.max_concurrent_jobs},
        "resources": {
            "cpu_cores": psutil.cpu_count(logical=True),
            "gpu_count": 0,
            # gpu_vram_mb は現時点で静的な値。将来的には nvidia-smi / nvml で動的取得する（MVPスコープ外）
            "gpu_vram_mb": 16000,
            "total_memory_mb": int(psutil.virtual_memory().total / 1024 / 1024),
            "os": "Linux",
            "arch": "x86_64",
        },
    }

    logger.info("Registering with Controller at %s ...", settings.controller_url)

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{settings.controller_url}/agents/register",
            json=payload,
            headers={"Authorization": f"Bearer {settings.invitation_token}"},
        )
        resp.raise_for_status()

    data = resp.json()
    agent_state = {
        "agent_id": data["agent_id"],
        "pool_id": data["pool_id"],
        "listener_token": data["listener_token"],
        "refresh_token": data["refresh_token"],
        "poll_interval": data.get("poll_interval", settings.poll_interval),
        "available_models": models,
    }
    save_config(agent_state)
    logger.info("Registration successful. agent_id=%s", agent_state["agent_id"])
    return agent_state
