import os

# Use test values before settings are loaded.
os.environ.setdefault("CONTROLLER_SECRET", "test-secret-key-for-testing-only")
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key")
# Keep polling short so 204 tests don't wait 30 s.
os.environ.setdefault("POLL_TIMEOUT_SECONDS", "1")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.base import Base, get_session
from main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def client(monkeypatch):
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    TestSession = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_session():
        async with TestSession() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    await engine.dispose()
