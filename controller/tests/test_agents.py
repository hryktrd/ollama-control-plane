import pytest

ADMIN_KEY = "test-admin-key"

REGISTER_BODY = {
    "hostname": "test-pc-01",
    "available_models": ["qwen2.5-coder:14b", "gemma3:12b"],
    "capabilities": {"max_concurrent_jobs": 1},
    "resources": {
        "cpu_cores": 16,
        "gpu_count": 1,
        "gpu_vram_mb": 16000,
        "total_memory_mb": 32000,
        "os": "Linux",
        "arch": "x86_64",
    },
}


async def _get_invite_token(client) -> str:
    resp = await client.post(
        "/admin/tokens/invite",
        json={"pool_id": "default", "expires_in_days": 7, "max_uses": 1},
        headers={"Authorization": f"Bearer {ADMIN_KEY}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["token"]


@pytest.mark.asyncio
async def test_register_with_valid_invitation_token(client):
    invite_token = await _get_invite_token(client)

    resp = await client.post(
        "/agents/register",
        json=REGISTER_BODY,
        headers={"Authorization": f"Bearer {invite_token}"},
    )

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert "agent_id" in data
    assert data["agent_id"].startswith("ag-")
    assert "listener_token" in data
    assert "refresh_token" in data
    assert data["refresh_token"].startswith("ref_")
    assert data["pool_id"] == "default"
    assert "qwen2.5-coder:14b" in data["available_models"]


@pytest.mark.asyncio
async def test_register_with_invalid_token(client):
    resp = await client.post(
        "/agents/register",
        json=REGISTER_BODY,
        headers={"Authorization": "Bearer inv_thisisnotarealtoken"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_poll_returns_204_when_no_job(client):
    invite_token = await _get_invite_token(client)
    reg = await client.post(
        "/agents/register",
        json=REGISTER_BODY,
        headers={"Authorization": f"Bearer {invite_token}"},
    )
    assert reg.status_code == 201
    data = reg.json()
    agent_id = data["agent_id"]
    listener_token = data["listener_token"]

    resp = await client.post(
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
    # Scheduler has no job queued; poll_timeout in tests will expire quickly.
    # With the in-memory scheduler and no job, should return 204.
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_token_refresh(client):
    invite_token = await _get_invite_token(client)
    reg = await client.post(
        "/agents/register",
        json=REGISTER_BODY,
        headers={"Authorization": f"Bearer {invite_token}"},
    )
    assert reg.status_code == 201
    reg_data = reg.json()
    agent_id = reg_data["agent_id"]
    refresh_token = reg_data["refresh_token"]

    resp = await client.post(
        "/agents/token/refresh",
        json={"agent_id": agent_id, "refresh_token": refresh_token},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "listener_token" in data
    assert "refresh_token" in data
    assert data["refresh_token"].startswith("ref_")
    assert data["expires_in"] > 0
    # Old refresh token must not be reusable.
    resp2 = await client.post(
        "/agents/token/refresh",
        json={"agent_id": agent_id, "refresh_token": refresh_token},
    )
    assert resp2.status_code == 401
