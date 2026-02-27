"""Tests for ProjectionWorker — replay from position, catch_up, position in same UoW."""

from __future__ import annotations

import pytest

from cqrs_ddd_advanced_core.projections.worker import ProjectionWorker
from cqrs_ddd_core.adapters.memory.event_store import InMemoryEventStore
from cqrs_ddd_core.ports.event_store import StoredEvent


class InMemoryPositionStore:
    """Minimal IProjectionPositionStore for tests."""

    def __init__(self) -> None:
        self._positions: dict[str, int] = {}

    async def get_position(
        self,
        projection_name: str,
        *,
        uow: object | None = None,
    ) -> int | None:
        return self._positions.get(projection_name)

    async def save_position(
        self,
        projection_name: str,
        position: int,
        *,
        uow: object | None = None,
    ) -> None:
        self._positions[projection_name] = position

    async def reset_position(
        self,
        projection_name: str,
        *,
        uow: object | None = None,
    ) -> None:
        self._positions.pop(projection_name, None)


class InMemoryUnitOfWork:
    """Minimal UoW for tests; worker only needs context manager."""

    async def __aenter__(self) -> InMemoryUnitOfWork:
        return self

    async def __aexit__(self, *args: object) -> None:
        pass


@pytest.fixture
def event_store():
    return InMemoryEventStore()


@pytest.fixture
def position_store():
    return InMemoryPositionStore()


@pytest.fixture
def uow_factory():
    return lambda: InMemoryUnitOfWork()


@pytest.mark.asyncio
async def test_worker_replay_from_position_advances_position(
    event_store,
    position_store,
    uow_factory,
):
    """Worker processes events and saves position after each in same UoW.

    get_events_from_position(start) yields events with position > start (exclusive).
    So start_position=0 yields events at 1, 2, ...; we append two events (positions 0, 1).
    """
    await event_store.append(
        StoredEvent(
            event_type="OrderCreated",
            aggregate_id="a1",
            aggregate_type="Order",
            version=1,
            position=0,
        )
    )
    await event_store.append(
        StoredEvent(
            event_type="OrderCreated",
            aggregate_id="a2",
            aggregate_type="Order",
            version=1,
            position=1,
        )
    )
    handled: list[int] = []

    class Handler:
        async def handle(
            self, event: StoredEvent, *, uow: object | None = None
        ) -> None:
            assert event.position is not None
            handled.append(event.position)

    worker = ProjectionWorker(
        event_store=event_store,
        position_store=position_store,
        writer=None,
        handler_map={"OrderCreated": Handler()},
        uow_factory=uow_factory,
        catch_up=False,
    )
    await worker.run("test_projection")
    # start_position=0 → events with position > 0 only, i.e. [1]
    assert handled == [1]
    assert await position_store.get_position("test_projection") == 1


@pytest.mark.asyncio
async def test_worker_resumes_from_last_position(
    event_store,
    position_store,
    uow_factory,
):
    """Worker starts from last saved position."""
    await event_store.append(
        StoredEvent(
            event_type="E",
            aggregate_id="a1",
            aggregate_type="A",
            version=1,
            position=0,
        )
    )
    await event_store.append(
        StoredEvent(
            event_type="E",
            aggregate_id="a2",
            aggregate_type="A",
            version=1,
            position=1,
        )
    )
    await position_store.save_position("p", 0)  # Already processed position 0
    handled: list[int] = []

    class Handler:
        async def handle(
            self, event: StoredEvent, *, uow: object | None = None
        ) -> None:
            handled.append(event.position or -1)

    worker = ProjectionWorker(
        event_store=event_store,
        position_store=position_store,
        writer=None,
        handler_map={"E": Handler()},
        uow_factory=uow_factory,
        catch_up=False,
    )
    await worker.run("p")
    assert handled == [1]
    assert await position_store.get_position("p") == 1


@pytest.mark.asyncio
async def test_worker_catch_up_skips_to_latest_when_no_position(
    event_store,
    position_store,
    uow_factory,
):
    """When catch_up=True and no last_position, set position to latest and then stream."""
    await event_store.append(
        StoredEvent(
            event_type="E",
            aggregate_id="a1",
            aggregate_type="A",
            version=1,
            position=0,
        )
    )
    await event_store.append(
        StoredEvent(
            event_type="E",
            aggregate_id="a2",
            aggregate_type="A",
            version=1,
            position=1,
        )
    )
    handled: list[int] = []

    class Handler:
        async def handle(
            self, event: StoredEvent, *, uow: object | None = None
        ) -> None:
            handled.append(event.position or -1)

    worker = ProjectionWorker(
        event_store=event_store,
        position_store=position_store,
        writer=None,
        handler_map={"E": Handler()},
        uow_factory=uow_factory,
        catch_up=True,
    )
    await worker.run("p")
    # Catch-up: position set to latest (1), so no historical events processed
    assert handled == []
    assert await position_store.get_position("p") == 1
