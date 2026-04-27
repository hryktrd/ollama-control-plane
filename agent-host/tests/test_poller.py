"""ポーリングループのコア動作テスト。"""

import pytest
import respx
from httpx import Response


FAKE_LISTENER_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiJhZy0xMjMiLCJleHAiOjk5OTk5OTk5OTl9"
    ".signature"
)

AGENT_STATE = {
    "agent_id": "ag-123",
    "pool_id": "default",
    "listener_token": FAKE_LISTENER_TOKEN,
    "refresh_token": "ref_abc",
    "poll_interval": 5,
    "available_models": ["qwen2.5-coder:14b"],
}

JOB_RESPONSE = {
    "job_id": "job-456",
    "type": "chat-completion",
    "model": "qwen2.5-coder:14b",
    "payload": {
        "messages": [{"role": "user", "content": "Hello"}],
    },
}


@pytest.fixture(autouse=True)
def patch_settings(monkeypatch):
    """テスト用に Controller URL と psutil をパッチする。"""
    monkeypatch.setattr("core.poller.settings.controller_url", "https://controller.test")
    monkeypatch.setattr("core.poller.settings.max_concurrent_jobs", 1)

    # psutil の実際の呼び出しを避けるためスタブを挿入する
    import types

    fake_psutil = types.SimpleNamespace(
        cpu_percent=lambda interval=None: 10.0,
        virtual_memory=lambda: types.SimpleNamespace(used=1024 * 1024 * 500),
    )
    monkeypatch.setattr("core.poller.psutil", fake_psutil)


@pytest.mark.anyio
async def test_poll_returns_job():
    """200レスポンスでjob dictが返ることを確認する。"""
    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://controller.test/agents/poll").mock(
            return_value=Response(200, json=JOB_RESPONSE)
        )

        from core.poller import _poll_once

        job = await _poll_once(AGENT_STATE)

    assert job is not None
    assert job["job_id"] == "job-456"
    assert job["type"] == "chat-completion"
    assert job["model"] == "qwen2.5-coder:14b"


@pytest.mark.anyio
async def test_poll_returns_none_on_204():
    """204レスポンスでNoneが返ることを確認する（ジョブなし）。"""
    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://controller.test/agents/poll").mock(
            return_value=Response(204)
        )

        from core.poller import _poll_once

        job = await _poll_once(AGENT_STATE)

    assert job is None


@pytest.mark.anyio
async def test_submit_result():
    """結果送信が正常に完了することを確認する。"""
    result = {
        "status": "completed",
        "execution_time_ms": 1500,
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        "result": {"message": {"role": "assistant", "content": "Hi there!"}},
    }

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://controller.test/jobs/job-123/result").mock(
            return_value=Response(200, json={"status": "accepted"})
        )

        from core.poller import _submit_result

        # 例外が発生しなければ成功
        await _submit_result(AGENT_STATE, "job-123", result)
