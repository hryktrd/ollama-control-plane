import asyncio

import pytest

ADMIN_KEY = "test-admin-key"

REGISTER_BODY = {
    "hostname": "gpu-pc-01",
    "available_models": ["qwen2.5-coder:14b"],
    "capabilities": {"max_concurrent_jobs": 1},
    "resources": {},
}


async def _create_api_key(client) -> str:
    resp = await client.post(
        "/admin/api-keys",
        json={"name": "test-key", "user_id": "user-1", "scopes": ["read", "write"]},
        headers={"Authorization": f"Bearer {ADMIN_KEY}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["key"]


async def _register_agent(client) -> dict:
    inv_resp = await client.post(
        "/admin/tokens/invite",
        json={"pool_id": "default", "expires_in_days": 7, "max_uses": 1},
        headers={"Authorization": f"Bearer {ADMIN_KEY}"},
    )
    assert inv_resp.status_code == 201
    invite_token = inv_resp.json()["token"]

    reg_resp = await client.post(
        "/agents/register",
        json=REGISTER_BODY,
        headers={"Authorization": f"Bearer {invite_token}"},
    )
    assert reg_resp.status_code == 201
    return reg_resp.json()


@pytest.mark.asyncio
async def test_chat_completions_no_agent(client):
    api_key = await _create_api_key(client)

    resp = await client.post(
        "/v1/chat/completions",
        json={
            "model": "qwen2.5-coder:14b",
            "messages": [{"role": "user", "content": "Hello"}],
        },
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_chat_completions_with_agent(client):
    api_key = await _create_api_key(client)
    agent_data = await _register_agent(client)
    agent_id = agent_data["agent_id"]
    listener_token = agent_data["listener_token"]

    async def agent_side():
        # Poll to receive the job, then submit the result.
        poll_resp = await client.post(
            "/agents/poll",
            json={
                "agent_id": agent_id,
                "status": "idle",
                "current_jobs": 0,
                "available_slots": 1,
                "resource_info": {},
            },
            headers={"Authorization": f"Bearer {listener_token}"},
        )
        assert poll_resp.status_code == 200, f"Expected job, got {poll_resp.status_code}"
        job = poll_resp.json()
        job_id = job["job_id"]

        result_resp = await client.post(
            f"/jobs/{job_id}/result",
            json={
                "agent_id": agent_id,
                "status": "completed",
                "execution_time_ms": 500,
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 20,
                    "total_tokens": 30,
                },
                "result": {"message": {"role": "assistant", "content": "Hello from agent"}},
            },
            headers={"Authorization": f"Bearer {listener_token}"},
        )
        assert result_resp.status_code == 200

    async def client_side():
        # Small delay so agent poll is already waiting when job arrives.
        await asyncio.sleep(0.05)
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "qwen2.5-coder:14b",
                "messages": [{"role": "user", "content": "Hello"}],
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        return resp

    agent_task = asyncio.create_task(agent_side())
    client_task = asyncio.create_task(client_side())

    resp = await client_task
    await agent_task

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["object"] == "chat.completion"
    assert len(data["choices"]) == 1
    assert data["choices"][0]["message"]["content"] == "Hello from agent"
    assert data["choices"][0]["message"]["role"] == "assistant"
    assert data["usage"]["total_tokens"] == 30
