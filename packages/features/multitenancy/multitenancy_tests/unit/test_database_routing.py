from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cqrs_ddd_multitenancy.database_routing import (
    DatabaseRouter,
    TenantConnectionPool,
    TenantDatabaseConfig,
)
from cqrs_ddd_multitenancy.isolation import IsolationConfig, TenantIsolationStrategy


@pytest.fixture
def mock_engine():
    engine = AsyncMock()
    engine.dispose = AsyncMock()
    return engine


@pytest.mark.asyncio
@patch("sqlalchemy.ext.asyncio.create_async_engine")
async def test_tenant_connection_pool_get_engine(mock_create_engine, mock_engine):
    mock_create_engine.return_value = mock_engine

    pool = TenantConnectionPool(
        get_database_url=lambda tid: f"sqlite+aiosqlite:///{tid}.db",
        default_config=TenantDatabaseConfig(database_url=""),
    )

    engine = await pool.get_engine("t1")
    assert engine is mock_engine
    mock_create_engine.assert_called_once()
    assert "t1.db" in mock_create_engine.call_args[0][0]

    # Should use cache the second time
    engine2 = await pool.get_engine("t1")
    assert engine2 is mock_engine
    assert mock_create_engine.call_count == 1


@pytest.mark.asyncio
@patch("sqlalchemy.ext.asyncio.create_async_engine")
async def test_tenant_connection_pool_close_all(mock_create_engine, mock_engine):
    mock_create_engine.return_value = mock_engine

    pool = TenantConnectionPool(
        get_database_url=lambda tid: f"sqlite+aiosqlite:///{tid}.db"
    )

    await pool.get_engine("t1")
    await pool.get_engine("t2")

    await pool.close_all()
    assert mock_engine.dispose.call_count == 2
    assert len(pool._engines) == 0


def test_database_router_get_database_name():
    config = IsolationConfig(
        strategy=TenantIsolationStrategy.DATABASE_PER_TENANT, database_prefix="db_"
    )
    router = DatabaseRouter(config, base_url="postgresql+asyncpg://localhost")

    assert router.get_database_name("t1") == "db_t1"
    assert router._get_database_url("t1") == "postgresql+asyncpg://localhost/db_t1"


@pytest.mark.asyncio
@patch("sqlalchemy.ext.asyncio.create_async_engine")
@patch("sqlalchemy.ext.asyncio.async_sessionmaker")
async def test_database_router_session_for_tenant(
    mock_sessionmaker, mock_create_engine, mock_engine
):
    mock_create_engine.return_value = mock_engine

    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session_factory = MagicMock(return_value=mock_session)
    mock_sessionmaker.return_value = mock_session_factory

    config = IsolationConfig(strategy=TenantIsolationStrategy.DATABASE_PER_TENANT)
    router = DatabaseRouter(config, base_url="postgresql+asyncpg://localhost")

    async with router.session_for_tenant("t1") as session:
        assert session is mock_session

    mock_session_factory.assert_called_once()
