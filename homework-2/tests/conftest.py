import os
import subprocess
from collections.abc import AsyncIterator

import asyncpg
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from src.config import get_settings
from src.db.session import get_session
from src.main import app


def _test_database_url() -> str:
    base = get_settings().database_url
    if not base.endswith("/tickets"):
        raise RuntimeError(f"Unexpected DATABASE_URL: {base}")
    return base.removesuffix("/tickets") + "/tickets_test"


def _admin_dsn() -> str:
    base = get_settings().database_url
    plain = base.replace("+asyncpg", "")
    return plain.rsplit("/", 1)[0] + "/postgres"


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_engine() -> AsyncIterator[AsyncEngine]:
    conn = await asyncpg.connect(_admin_dsn())
    try:
        await conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = 'tickets_test' AND pid <> pg_backend_pid()"
        )
        await conn.execute("DROP DATABASE IF EXISTS tickets_test")
        await conn.execute("CREATE DATABASE tickets_test")
    finally:
        await conn.close()

    env = os.environ.copy()
    env["DATABASE_URL"] = _test_database_url()
    subprocess.run(
        [".venv/bin/alembic", "upgrade", "head"],
        env=env,
        check=True,
        capture_output=True,
    )

    engine = create_async_engine(
        _test_database_url(),
        poolclass=NullPool,
    )
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session
    async with test_engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE tickets RESTART IDENTITY CASCADE"))


@pytest_asyncio.fixture(scope="function")
async def client(test_engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    factory = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()
        async with test_engine.begin() as conn:
            await conn.execute(text("TRUNCATE TABLE tickets RESTART IDENTITY CASCADE"))
