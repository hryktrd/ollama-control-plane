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
async def test_messages_no_api_key(client):
    resp = await client.post(
        "/v1/messages",
        json={"model": "qwen2.5-coder:14b", "max_tokens": 100, "messages": [{"role": "user", "content": "Hello"}]},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_messages_no_agent(client):
    api_key = await _create_api_key(client)

    resp = await client.post(
        "/v1/messages",
        json={"model": "qwen2.5-coder:14b", "max_tokens": 100, "messages": [{"role": "user", "content": "Hello"}]},
        headers={"x-api-key": api_key},
    )
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_messages_no_agent_bearer_auth(client):
    api_key = await _create_api_key(client)

    resp = await client.post(
        "/v1/messages",
        json={"model": "qwen2.5-coder:14b", "max_tokens": 100, "messages": [{"role": "user", "content": "Hello"}]},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_messages_streaming_rejected(client):
    api_key = await _create_api_key(client)

    resp = await client.post(
        "/v1/messages",
        json={
            "model": "qwen2.5-coder:14b",
            "max_tokens": 100,
            "messages": [{"role": "user", "content": "Hello"}],
            "stream": True,
        },
        headers={"x-api-key": api_key},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "streaming_not_supported"


@pytest.mark.asyncio
async def test_messages_with_agent_x_api_key(client):
    api_key = await _create_api_key(client)
    agent_data = await _register_agent(client)
    agent_id = agent_data["agent_id"]
    listener_token = agent_data["listener_token"]

    async def agent_side():
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
                    "prompt_tokens": 15,
                    "completion_tokens": 25,
                    "total_tokens": 40,
                },
                "result": {"message": {"role": "assistant", "content": "Hello from agent"}},
            },
            headers={"Authorization": f"Bearer {listener_token}"},
        )
        assert result_resp.status_code == 200

    async def client_side():
        await asyncio.sleep(0.05)
        return await client.post(
            "/v1/messages",
            json={
                "model": "qwen2.5-coder:14b",
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": "Hello"}],
            },
            headers={"x-api-key": api_key},
        )

    agent_task = asyncio.create_task(agent_side())
    client_task = asyncio.create_task(client_side())

    resp = await client_task
    await agent_task

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["type"] == "message"
    assert data["role"] == "assistant"
    assert len(data["content"]) == 1
    assert data["content"][0]["type"] == "text"
    assert data["content"][0]["text"] == "Hello from agent"
    assert data["stop_reason"] == "end_turn"
    assert data["usage"]["input_tokens"] == 15
    assert data["usage"]["output_tokens"] == 25


@pytest.mark.asyncio
async def test_messages_with_system_prompt(client):
    api_key = await _create_api_key(client)
    agent_data = await _register_agent(client)
    agent_id = agent_data["agent_id"]
    listener_token = agent_data["listener_token"]

    async def agent_side():
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
        assert poll_resp.status_code == 200
        job = poll_resp.json()
        # Verify system message is present in job payload
        messages = job["payload"]["messages"]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are a helpful assistant."

        await client.post(
            f"/jobs/{job['job_id']}/result",
            json={
                "agent_id": agent_id,
                "status": "completed",
                "execution_time_ms": 200,
                "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
                "result": {"message": {"role": "assistant", "content": "Hi!"}},
            },
            headers={"Authorization": f"Bearer {listener_token}"},
        )

    async def client_side():
        await asyncio.sleep(0.05)
        return await client.post(
            "/v1/messages",
            json={
                "model": "qwen2.5-coder:14b",
                "max_tokens": 100,
                "system": "You are a helpful assistant.",
                "messages": [{"role": "user", "content": "Hi"}],
            },
            headers={"x-api-key": api_key},
        )

    agent_task = asyncio.create_task(agent_side())
    client_task = asyncio.create_task(client_side())

    resp = await client_task
    await agent_task

    assert resp.status_code == 200
    assert resp.json()["content"][0]["text"] == "Hi!"
