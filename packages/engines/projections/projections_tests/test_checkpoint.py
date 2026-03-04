"""Tests for InMemoryCheckpointStore and SQLAlchemyProjectionCheckpointStore."""

from __future__ import annotations

import pytest

from cqrs_ddd_projections.checkpoint import InMemoryCheckpointStore


@pytest.mark.asyncio
async def test_save_and_get_position() -> None:
    store = InMemoryCheckpointStore()
    assert await store.get_position("p1") is None
    await store.save_position("p1", 10)
    assert await store.get_position("p1") == 10


@pytest.mark.asyncio
async def test_clear() -> None:
    store = InMemoryCheckpointStore()
    await store.save_position("p1", 5)
    store.clear()
    assert await store.get_position("p1") is None
