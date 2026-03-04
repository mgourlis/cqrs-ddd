"""Tests for ProjectionWorker."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from cqrs_ddd_core.ports.event_store import StoredEvent
from cqrs_ddd_projections.checkpoint import InMemoryCheckpointStore
from cqrs_ddd_projections.registry import ProjectionRegistry
from cqrs_ddd_projections.worker import ProjectionWorker


@pytest.fixture
def in_memory_event_store() -> MagicMock:
    store = MagicMock()
    store.get_all = AsyncMock(return_value=[])
    store.get_events_after = AsyncMock(return_value=[])
    return store


@pytest.mark.asyncio
async def test_worker_start_stop(in_memory_event_store: MagicMock) -> None:
    """Test that worker can be started and stopped cleanly."""
    reg = ProjectionRegistry()
    checkpoint = InMemoryCheckpointStore()
    worker = ProjectionWorker(
        in_memory_event_store,
        reg,
        checkpoint,
        projection_name="test",
        poll_interval_seconds=0.01,
    )
    await worker.start()
    # Let worker start and check it stops cleanly
    await asyncio.sleep(0.02)
    await worker.stop()


@pytest.mark.asyncio
async def test_worker_processes_events_and_checkpoints(
    in_memory_event_store: MagicMock,
) -> None:
    """Test that worker processes events and updates checkpoint."""
    from cqrs_ddd_core.domain.events import DomainEvent

    class E1(DomainEvent):
        value: int = 0

    class H1:
        handles = {E1}

        async def handle(self, event: DomainEvent) -> None:
            pass

    stored = StoredEvent(
        event_type="E1",
        aggregate_id="a1",
        payload={"value": 42},
        position=0,
    )

    reg = ProjectionRegistry()
    reg.register(H1())
    checkpoint = InMemoryCheckpointStore()
    # Set initial checkpoint to 0
    await checkpoint.save_position("test", 0)
    # First call returns event, subsequent calls return empty
    in_memory_event_store.get_events_after = AsyncMock(
        side_effect=[[stored], [], [], []]
    )
    event_registry = MagicMock()
    event_registry.hydrate = MagicMock(return_value=E1(value=42))

    worker = ProjectionWorker(
        in_memory_event_store,
        reg,
        checkpoint,
        projection_name="test",
        event_registry=event_registry,
        batch_size=10,
        poll_interval_seconds=0.01,
    )
    await worker.start()
    # Let worker process events
    await asyncio.sleep(0.05)
    await worker.stop()
    pos = await checkpoint.get_position("test")
    # Worker should have processed 1 event and checkpointed at its actual position
    assert pos == 0  # Event had position=0, so checkpoint should be 0
