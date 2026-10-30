"""Runs against a real PostgreSQL. Set TEST_ADMIN_DSN (default: local postgres) and it creates vista_test."""
import os

for _k in ("STAFF_ACCESS_CODE", "SECRET_KEY", "CRON_KEY", "AUTO_BOOTSTRAP", "AUTO_SEED", "DB_PGBOUNCER"):
    os.environ.pop(_k, None)  # tests must not inherit a deployment's settings

import asyncpg
import httpx
import pytest
import pytest_asyncio

ADMIN = os.getenv("TEST_ADMIN_DSN", "postgresql://vista:vista@localhost:5432/postgres")
TEST_DSN = os.getenv("TEST_APP_DSN", ADMIN.rsplit("/", 1)[0] + "/vista_test")  # e.g. a pooler URL


@pytest_asyncio.fixture(scope="session")
async def app_pool():
    a = await asyncpg.connect(ADMIN)
    await a.execute("DROP DATABASE IF EXISTS vista_test WITH (FORCE)")
    await a.execute("CREATE DATABASE vista_test")
    await a.close()
    from app.db import create_pool, migrate
    from app.seed import seed
    pool = await create_pool(TEST_DSN)
    await migrate(pool)
    await seed(pool)
    await seed(pool, slug="other-village-1a2b")  # second property for isolation tests
    from app.main import app
    app.state.pool = pool
    yield pool
    await pool.close()


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    """The limiter keeps its counters in memory per IP; every test shares one fake IP, so start each test with empty counters."""
    from app import core
    core._hits.clear()
    yield


@pytest_asyncio.fixture(scope="session")
async def client(app_pool):
    from app.main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


def H(role, lot=None, prop=None):
    h = {"X-Role": role}
    if lot:
        h["X-Household"] = lot
    if prop:
        h["X-Property"] = prop
    return h


# Smallest valid JPEG (1x1 pixel), base64: what the UI sends as the entry photo.
JPEG_B64 = ("/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////"
            "wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA=")


def visit_when(days: int = 0) -> str:
    """A visit date and time as the form sends it (datetime-local), in the village's time zone. days=0 is today."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    return (datetime.now(ZoneInfo("Asia/Manila")) + timedelta(days=days)).replace(hour=10, minute=0).strftime("%Y-%m-%dT%H:%M")


def public_visit(**over):
    """A complete public visitor request: every documented field is present. Tests change only what they are about."""
    base = {"name": "Test Visitor", "phone": "0999 111 2222", "house": "B1-L4", "host": "", "purpose": "Visit", "when": visit_when(),
            "arrival": "Walking", "friends": [], "id_photo": JPEG_B64}
    return {**base, **over}
