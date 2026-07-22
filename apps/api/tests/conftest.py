from __future__ import annotations

import os
import tempfile

# Use an isolated temp SQLite DB for the whole test session. MUST be set before
# any app module imports the engine.
_TMP_DB = os.path.join(tempfile.gettempdir(), "job_os_test.db")
if os.path.exists(_TMP_DB):
    os.remove(_TMP_DB)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP_DB}"
TEST_TOKEN = "test-token-not-a-real-secret"
os.environ["API_TOKEN"] = TEST_TOKEN

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.db.session import SessionLocal, engine  # noqa: E402
from app.models import Base  # noqa: E402


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _create_schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest_asyncio.fixture
async def session():
    async with SessionLocal() as s:
        yield s


@pytest_asyncio.fixture
async def client():
    """Authenticated client — carries the bearer token like the real frontend."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    ) as c:
        yield c


@pytest_asyncio.fixture
async def anon_client():
    """Unauthenticated client — used to prove protected routes reject anonymers."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
