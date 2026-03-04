"""Tests for SQLAlchemy projections module (ProjectionCheckpoint, SQLAlchemyProjectionCheckpointStore)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from cqrs_ddd_persistence_sqlalchemy import SQLAlchemyProjectionCheckpointStore
from cqrs_ddd_persistence_sqlalchemy.core.models import Base

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_checkpoint_store_get_position_none(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = SQLAlchemyProjectionCheckpointStore(session_factory)
    assert await store.get_position("unknown") is None


@pytest.mark.asyncio
async def test_checkpoint_store_save_and_get_position(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = SQLAlchemyProjectionCheckpointStore(session_factory)
    await store.save_position("proj_a", 100)
    assert await store.get_position("proj_a") == 100


@pytest.mark.asyncio
async def test_checkpoint_store_save_updates_position(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = SQLAlchemyProjectionCheckpointStore(session_factory)
    await store.save_position("proj_b", 5)
    await store.save_position("proj_b", 20)
    assert await store.get_position("proj_b") == 20
