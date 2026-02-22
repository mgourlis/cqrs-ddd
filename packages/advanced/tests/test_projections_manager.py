"""Tests for ProjectionManager — concurrent initialize_all does not duplicate work."""

from __future__ import annotations

import asyncio

import pytest

from cqrs_ddd_core.adapters.memory.locking import InMemoryLockStrategy

from cqrs_ddd_advanced_core.projections.manager import ProjectionManager
from cqrs_ddd_advanced_core.projections.schema import (
    ProjectionSchema,
    ProjectionSchemaRegistry,
)


class InMemoryWriter:
    """Minimal IProjectionWriter for tests; records ensure_collection calls."""

    def __init__(self) -> None:
        self.ensured: list[str] = []
        self._exists: set[str] = set()

    async def ensure_collection(
        self,
        collection: str,
        *,
        schema: object | None = None,
    ) -> None:
        self.ensured.append(collection)
        self._exists.add(collection)

    async def collection_exists(self, collection: str) -> bool:
        return collection in self._exists

    async def truncate_collection(self, collection: str) -> None:
        pass

    async def drop_collection(self, collection: str) -> None:
        self._exists.discard(collection)

    async def upsert(
        self,
        collection: str,
        doc_id: object,
        data: object,
        *,
        event_position: int | None = None,
        event_id: str | None = None,
        uow: object | None = None,
    ) -> bool:
        return True

    async def upsert_batch(
        self,
        collection: str,
        docs: list,
        *,
        id_field: str = "id",
        uow: object | None = None,
    ) -> None:
        pass

    async def delete(
        self,
        collection: str,
        doc_id: object,
        *,
        cascade: bool = False,
        uow: object | None = None,
    ) -> None:
        pass

    async def ensure_ttl_index(
        self,
        collection: str,
        field: str,
        expire_after_seconds: int,
    ) -> None:
        pass


@pytest.fixture
def writer():
    return InMemoryWriter()


@pytest.fixture
def registry():
    reg = ProjectionSchemaRegistry()
    reg.register(ProjectionSchema(name="orders", columns=[]))
    reg.register(ProjectionSchema(name="items", columns=[]))
    return reg


@pytest.fixture
def lock_strategy():
    return InMemoryLockStrategy()


@pytest.mark.asyncio
async def test_manager_initialize_once_creates_collection(writer, registry, lock_strategy):
    manager = ProjectionManager(writer, registry, lock_strategy)
    await manager.initialize_once("orders")
    assert "orders" in writer.ensured
    assert await writer.collection_exists("orders")


@pytest.mark.asyncio
async def test_manager_initialize_once_double_check_skips_if_exists(writer, registry, lock_strategy):
    manager = ProjectionManager(writer, registry, lock_strategy)
    writer._exists.add("orders")
    await manager.initialize_once("orders")
    assert writer.ensured == []  # ensure_collection not called due to double-check


@pytest.mark.asyncio
async def test_manager_initialize_all_calls_ensure_for_each(writer, registry, lock_strategy):
    manager = ProjectionManager(writer, registry, lock_strategy)
    await manager.initialize_all()
    assert "orders" in writer.ensured
    assert "items" in writer.ensured


@pytest.mark.asyncio
async def test_manager_concurrent_initialize_all_single_creation(writer, registry, lock_strategy):
    """Concurrent initialize_all does not duplicate ensure_collection (lock serializes)."""
    manager = ProjectionManager(writer, registry, lock_strategy)
    await asyncio.gather(
        manager.initialize_all(timeout=2.0),
        manager.initialize_all(timeout=2.0),
        manager.initialize_all(timeout=2.0),
    )
    # Each collection should be ensured at most once (lock prevents duplicate DDL)
    assert writer.ensured.count("orders") <= 1
    assert writer.ensured.count("items") <= 1
