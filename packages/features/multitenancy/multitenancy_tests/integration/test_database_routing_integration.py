"""Integration tests for database-per-tenant routing using real SQLite databases.

Uses aiosqlite so no PostgreSQL instance is required. A custom engine_factory
is injected so TenantConnectionPool creates SQLite files instead of connecting
to a remote server.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from cqrs_ddd_multitenancy.context import reset_tenant, set_tenant
from cqrs_ddd_multitenancy.database_routing import (
    DatabaseRouter,
    TenantConnectionPool,
    TenantDatabaseConfig,
)
from cqrs_ddd_multitenancy.exceptions import TenantIsolationError
from cqrs_ddd_multitenancy.isolation import IsolationConfig, TenantIsolationStrategy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def sqlite_engine_factory(db_dir: Path):
    """Return an engine_factory that creates per-tenant SQLite files."""

    def factory(tenant_id: str, config: TenantDatabaseConfig) -> AsyncEngine:
        url = f"sqlite+aiosqlite:///{db_dir}/{tenant_id}.db"
        return create_async_engine(url, echo=False)

    return factory


def make_pool(db_dir: Path, *, max_pools: int = 10) -> TenantConnectionPool:
    return TenantConnectionPool(
        get_database_url=lambda tid: f"sqlite+aiosqlite:///{db_dir}/{tid}.db",
        max_pools=max_pools,
        engine_factory=sqlite_engine_factory(db_dir),
    )


def make_router(db_dir: Path, *, max_pools: int = 10) -> DatabaseRouter:
    config = IsolationConfig(
        strategy=TenantIsolationStrategy.DATABASE_PER_TENANT,
        database_prefix="",
    )
    pool = make_pool(db_dir, max_pools=max_pools)
    return DatabaseRouter(
        config=config, base_url="sqlite+aiosqlite:///", connection_pool=pool
    )


# ---------------------------------------------------------------------------
# TenantConnectionPool — engine lifecycle
# ---------------------------------------------------------------------------


async def test_pool_creates_engine_on_first_access(tmp_path: Path):
    pool = make_pool(tmp_path)
    engine = await pool.get_engine("acme")
    assert engine is not None
    await pool.close_all()


async def test_pool_returns_same_engine_for_same_tenant(tmp_path: Path):
    pool = make_pool(tmp_path)
    e1 = await pool.get_engine("acme")
    e2 = await pool.get_engine("acme")
    assert e1 is e2
    await pool.close_all()


async def test_pool_returns_different_engines_for_different_tenants(tmp_path: Path):
    pool = make_pool(tmp_path)
    e1 = await pool.get_engine("tenant-a")
    e2 = await pool.get_engine("tenant-b")
    assert e1 is not e2
    await pool.close_all()


async def test_pool_close_engine_removes_it(tmp_path: Path):
    pool = make_pool(tmp_path)
    await pool.get_engine("acme")
    await pool.close_engine("acme")
    # After close, a new engine is created on next access
    new_engine = await pool.get_engine("acme")
    assert new_engine is not None
    await pool.close_all()


async def test_pool_close_all_clears_cache(tmp_path: Path):
    pool = make_pool(tmp_path)
    await pool.get_engine("a")
    await pool.get_engine("b")
    await pool.close_all()
    # Internal caches cleared — accessing after close_all creates fresh engines
    engine = await pool.get_engine("a")
    assert engine is not None
    await pool.close_all()


async def test_pool_lru_eviction_at_max_capacity(tmp_path: Path):
    """When max_pools=2, adding a third tenant evicts the oldest."""
    pool = make_pool(tmp_path, max_pools=2)
    e_a = await pool.get_engine("a")  # pool: [a]
    e_b = await pool.get_engine("b")  # pool: [a, b]
    assert e_a is not e_b

    # Adding a third tenant should evict "a" (oldest)
    await pool.get_engine("c")  # pool: [b, c] — "a" evicted

    # "a" is gone from cache; a fresh engine is created
    e_a_new = await pool.get_engine("a")
    assert e_a_new is not e_a  # different object — was re-created

    await pool.close_all()


# ---------------------------------------------------------------------------
# TenantConnectionPool — session factory
# ---------------------------------------------------------------------------


async def test_pool_get_session_factory_returns_callable(tmp_path: Path):
    pool = make_pool(tmp_path)
    factory = await pool.get_session_factory("acme")
    assert callable(factory)
    await pool.close_all()


async def test_pool_session_factory_opens_real_session(tmp_path: Path):
    pool = make_pool(tmp_path)
    factory = await pool.get_session_factory("acme")
    async with factory() as session:
        result = await session.execute(text("SELECT 1"))
        assert result.scalar() == 1
    await pool.close_all()


async def test_pool_different_tenants_have_isolated_sessions(tmp_path: Path):
    """Sessions from different tenants connect to different SQLite files."""
    pool = make_pool(tmp_path)
    factory_a = await pool.get_session_factory("tenant-a")
    factory_b = await pool.get_session_factory("tenant-b")

    # Create a table in tenant-a's DB
    async with factory_a() as sess_a:
        await sess_a.execute(text("CREATE TABLE IF NOT EXISTS marker (id INTEGER)"))
        await sess_a.execute(text("INSERT INTO marker VALUES (1)"))
        await sess_a.commit()

    # tenant-b should NOT see that table
    async with factory_b() as sess_b:
        try:
            await sess_b.execute(text("SELECT * FROM marker"))
            found = True
        except Exception:
            found = False

    assert not found, "tenant-b must not see tenant-a's data"
    await pool.close_all()


# ---------------------------------------------------------------------------
# DatabaseRouter
# ---------------------------------------------------------------------------


async def test_router_get_engine(tmp_path: Path):
    router = make_router(tmp_path)
    engine = await router.get_engine("acme")
    assert engine is not None
    await router.close_all()


async def test_router_session_for_tenant_explicit(tmp_path: Path):
    router = make_router(tmp_path)
    async with router.session_for_tenant("acme") as session:
        result = await session.execute(text("SELECT 42"))
        assert result.scalar() == 42
    await router.close_all()


async def test_router_session_for_tenant_uses_context(tmp_path: Path):
    """session_for_tenant(None) reads tenant from ContextVar."""
    router = make_router(tmp_path)
    token = set_tenant("ctx-tenant")
    try:
        async with router.session_for_tenant() as session:
            result = await session.execute(text("SELECT 99"))
            assert result.scalar() == 99
    finally:
        reset_tenant(token)
    await router.close_all()


async def test_router_session_for_tenant_no_context_raises(tmp_path: Path):
    """Without tenant context and no explicit id, raises TenantIsolationError."""
    router = make_router(tmp_path)
    with pytest.raises(TenantIsolationError):
        async with router.session_for_tenant():
            pass
    await router.close_all()


async def test_router_session_for_current_tenant(tmp_path: Path):
    router = make_router(tmp_path)
    token = set_tenant("current")
    try:
        async with router.session_for_current_tenant() as session:
            result = await session.execute(text("SELECT 1"))
            assert result.scalar() == 1
    finally:
        reset_tenant(token)
    await router.close_all()


async def test_router_different_tenants_get_different_sessions(tmp_path: Path):
    """Two tenants using DatabaseRouter connect to separate SQLite DBs."""
    router = make_router(tmp_path)

    async with router.session_for_tenant("x") as sess_x:
        await sess_x.execute(text("CREATE TABLE IF NOT EXISTS t (v INTEGER)"))
        await sess_x.execute(text("INSERT INTO t VALUES (7)"))
        await sess_x.commit()

    async with router.session_for_tenant("y") as sess_y:
        try:
            await sess_y.execute(text("SELECT * FROM t"))
            found = True
        except Exception:
            found = False

    assert not found
    await router.close_all()
