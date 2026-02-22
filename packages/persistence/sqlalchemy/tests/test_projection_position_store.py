"""Tests for SQLAlchemyProjectionStore and SQLAlchemyProjectionPositionStore."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from cqrs_ddd_persistence_sqlalchemy import (
    SQLAlchemyProjectionPositionStore,
    SQLAlchemyProjectionStore,
)


@pytest.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE projection_positions (
                    projection_name TEXT PRIMARY KEY,
                    position INTEGER NOT NULL
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE TABLE test_projections (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    _version INTEGER,
                    _last_event_id TEXT,
                    _last_event_position INTEGER
                )
                """
            )
        )
    yield eng
    await eng.dispose()


@pytest.fixture
def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.mark.asyncio
async def test_position_store_save_and_get(session_factory):
    store = SQLAlchemyProjectionPositionStore(session_factory)
    await store.save_position("proj_a", 100)
    pos = await store.get_position("proj_a")
    assert pos == 100


@pytest.mark.asyncio
async def test_position_store_get_none_when_never_saved(session_factory):
    store = SQLAlchemyProjectionPositionStore(session_factory)
    pos = await store.get_position("unknown")
    assert pos is None


@pytest.mark.asyncio
async def test_position_store_reset(session_factory):
    store = SQLAlchemyProjectionPositionStore(session_factory)
    await store.save_position("proj_a", 50)
    await store.reset_position("proj_a")
    pos = await store.get_position("proj_a")
    assert pos is None


@pytest.mark.asyncio
async def test_position_store_overwrites(session_factory):
    store = SQLAlchemyProjectionPositionStore(session_factory)
    await store.save_position("proj_a", 10)
    await store.save_position("proj_a", 20)
    assert await store.get_position("proj_a") == 20


@pytest.mark.asyncio
async def test_projection_store_upsert_and_collection_exists(session_factory):
    store = SQLAlchemyProjectionStore(session_factory)
    exists_before = await store.collection_exists("test_projections")
    assert exists_before is True
    ok = await store.upsert(
        "test_projections",
        "doc1",
        {"id": "doc1", "name": "first"},
        event_position=1,
        event_id="e1",
    )
    assert ok is True
    # Re-upsert same position/event_id idempotent behavior is impl-dependent
    ok2 = await store.upsert(
        "test_projections",
        "doc1",
        {"id": "doc1", "name": "second"},
        event_position=2,
        event_id="e2",
    )
    assert ok2 is True


@pytest.mark.asyncio
async def test_projection_store_ensure_collection_raises_without_auto_ddl(session_factory):
    store = SQLAlchemyProjectionStore(session_factory, allow_auto_ddl=False)
    with pytest.raises(RuntimeError, match="Auto-DDL disabled"):
        await store.ensure_collection("new_table")
