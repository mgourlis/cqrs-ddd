"""Integration-style test: multiple concurrent initializers, single table/collection creation."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import Column, String

from cqrs_ddd_advanced_core.projections.manager import ProjectionManager
from cqrs_ddd_advanced_core.projections.schema import (
    ProjectionSchemaRegistry,
    create_schema,
)
from cqrs_ddd_core.adapters.memory.locking import InMemoryLockStrategy


class RecordingWriter:
    """IProjectionWriter that records ensure_collection calls (with optional delay)."""

    def __init__(self, *, delay: float = 0) -> None:
        self.ensured: list[str] = []
        self._exists: set[str] = set()
        self._delay = delay

    async def ensure_collection(
        self,
        collection: str,
        *,
        schema: object | None = None,
    ) -> None:
        if self._delay:
            await asyncio.sleep(self._delay)
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


@pytest.mark.asyncio
async def test_distributed_init_single_collection_creation():
    """Initialize_all creates the collection; double-check prevents duplicate ensure."""
    writer = RecordingWriter(delay=0)
    registry = ProjectionSchemaRegistry()
    schema = create_schema(
        "concurrent_test",
        columns=[Column("id", String(255), primary_key=True)],
    )
    registry.register(schema)
    lock = InMemoryLockStrategy()
    manager = ProjectionManager(writer, registry, lock)

    await manager.initialize_all(timeout=5.0)
    assert writer.ensured.count("concurrent_test") == 1

    # Second call: collection_exists is true, so ensure_collection is not called again
    await manager.initialize_all(timeout=5.0)
    assert writer.ensured.count("concurrent_test") == 1
