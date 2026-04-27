import httpx

from config.settings import settings


class OllamaClient:
    def __init__(self) -> None:
        self._base = settings.ollama_url.rstrip("/")

    async def list_models(self) -> list[str]:
        """GET /api/tags でインストール済みモデル名リストを返す。"""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{self._base}/api/tags")
            resp.raise_for_status()
            data = resp.json()
            return [m["name"] for m in data.get("models", [])]

    async def is_available(self) -> bool:
        """Ollamaが起動しているか確認する。"""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self._base}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False

    async def chat(self, model: str, messages: list[dict], options: dict | None = None) -> dict:
        """POST /api/chat (非ストリーミング) でチャット補完を実行する。"""
        payload: dict = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        if options:
            payload["options"] = options

        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(f"{self._base}/api/chat", json=payload)
            resp.raise_for_status()
            return resp.json()


ollama = OllamaClient()
