"""エージェント登録フローと Ollama モデル検出のテスト。"""

import json
import os

import pytest
import respx
from httpx import Response

from config.settings import Settings


FAKE_LISTENER_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiJhZy0xMjMiLCJleHAiOjk5OTk5OTk5OTl9"
    ".signature"
)

REGISTER_RESPONSE = {
    "agent_id": "ag-123",
    "pool_id": "default",
    "listener_token": FAKE_LISTENER_TOKEN,
    "refresh_token": "ref_abc",
    "poll_interval": 30,
    "available_models": ["qwen2.5-coder:14b"],
}

TAGS_RESPONSE = {
    "models": [
        {"name": "qwen2.5-coder:14b"},
        {"name": "gemma3:12b"},
    ]
}


@pytest.mark.anyio
async def test_register_success(tmp_path, monkeypatch):
    """正常な登録フローで agent_state が正しく構成されることを確認する。"""
    # config_dir を tmp_path に差し替えてファイル保存先を隔離する
    monkeypatch.setattr("config.settings.settings.config_dir", str(tmp_path))
    monkeypatch.setattr("auth.token.settings.config_dir", str(tmp_path))

    # 登録に使う invitation_token を設定する
    monkeypatch.setattr("config.settings.settings.invitation_token", "inv_test")
    monkeypatch.setattr("core.agent.settings.invitation_token", "inv_test")
    monkeypatch.setattr("core.agent.settings.controller_url", "https://controller.test")
    monkeypatch.setattr("core.agent.settings.poll_interval", 30)
    monkeypatch.setattr("core.agent.settings.max_concurrent_jobs", 1)
    monkeypatch.setattr("core.agent.settings.hostname", "test-host")

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://controller.test/agents/register").mock(
            return_value=Response(201, json=REGISTER_RESPONSE)
        )

        from core.agent import _register

        agent_state = await _register(["qwen2.5-coder:14b"])

    assert agent_state["agent_id"] == "ag-123"
    assert agent_state["pool_id"] == "default"
    assert agent_state["poll_interval"] == 30
    assert agent_state["available_models"] == ["qwen2.5-coder:14b"]
    # トークン値自体は確認するが、ログ出力には現れない
    assert "listener_token" in agent_state
    assert "refresh_token" in agent_state

    # 設定ファイルが保存されていることを確認する
    config_path = os.path.join(str(tmp_path), "agent.json")
    assert os.path.exists(config_path)
    with open(config_path) as f:
        saved = json.load(f)
    assert saved["agent_id"] == "ag-123"

    # パーミッションが0o600であることを確認する（Windows以外）
    if os.name != "nt":
        mode = oct(os.stat(config_path).st_mode)[-3:]
        assert mode == "600"


@pytest.mark.anyio
async def test_ollama_list_models(monkeypatch):
    """OllamaClient.list_models() が正しくモデル名リストを返すことを確認する。"""
    monkeypatch.setattr("core.ollama.settings.ollama_url", "http://ollama.test")
    monkeypatch.setattr("core.ollama.ollama._base", "http://ollama.test")

    with respx.mock(assert_all_called=True) as mock:
        mock.get("http://ollama.test/api/tags").mock(
            return_value=Response(200, json=TAGS_RESPONSE)
        )

        from core.ollama import OllamaClient

        client = OllamaClient.__new__(OllamaClient)
        client._base = "http://ollama.test"
        models = await client.list_models()

    assert models == ["qwen2.5-coder:14b", "gemma3:12b"]
