"""Tests for EventSourcedMediator and related components."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from cqrs_ddd_advanced_core.cqrs.event_sourced_mediator import EventSourcedMediator
from cqrs_ddd_advanced_core.cqrs.factory import EventSourcedMediatorFactory
from cqrs_ddd_advanced_core.domain.exceptions import EventSourcingConfigurationError
from cqrs_ddd_advanced_core.event_sourcing.persistence_orchestrator import (
    EventSourcedPersistenceOrchestrator,
)

# CommandResponse needed so mock handlers return correct type
from cqrs_ddd_core.cqrs.response import CommandResponse
from cqrs_ddd_core.domain.aggregate import AggregateRoot
from cqrs_ddd_core.domain.events import DomainEvent
from cqrs_ddd_core.ports.event_store import IEventStore


# Mock classes for testing
class MockEventStore(IEventStore):
    """Mock event store for testing."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def append(self, event: Any) -> None:
        """Store an event."""
        self.events.append(
            {
                "event_type": event.event_type,
                "aggregate_id": event.aggregate_id,
            }
        )

    async def append_batch(self, events: list[Any]) -> None:
        """Store multiple events."""
        self.events.extend(
            [
                {"event_type": e.event_type, "aggregate_id": e.aggregate_id}
                for e in events
            ]
        )

    async def get_events(
        self,
        aggregate_id: str | None = None,
        event_type: str | None = None,
    ) -> list[Any]:
        """Retrieve events."""
        return self.events.copy()


class MockUnitOfWork:
    """Mock UnitOfWork for testing."""

    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> Any:
        self.committed = False
        self.rolled_back = False
        return self

    async def __aexit__(self, exc_type, exc_val, traceback) -> None:
        if exc_type is not None:
            self.rolled_back = True
        else:
            self.committed = True
        return


class MockDomainEvent(DomainEvent):
    """Mock domain event for testing."""

    model_config = {"frozen": True}
    event_id: str = ""
    aggregate_id: str = ""
    aggregate_type: str = ""
    occurred_at: Any = None
    metadata: dict[str, Any] = {}
    version: int = 1


class MockAggregate(AggregateRoot[str]):
    """Mock aggregate for testing."""

    status: str = "pending"
    revision: int = 0  # avoid shadowing parent AggregateRootMixin.version

    def apply_order_created(self, event: MockDomainEvent) -> None:
        self.status = "created"
        self.revision += 1


# Tests
async def test_event_sourced_mediator_extends_core_mediator() -> None:
    """Verify EventSourcedMediator extends core Mediator."""
    from cqrs_ddd_core.cqrs.mediator import Mediator

    assert issubclass(EventSourcedMediator, Mediator)
    print("✓ EventSourcedMediator extends core Mediator")


async def test_send_command_with_persistence() -> None:
    """Test that events are persisted when using EventSourcedMediator."""
    event_store = MockEventStore()
    orchestrator = EventSourcedPersistenceOrchestrator(event_store)
    orchestrator.register_event_sourced_type("MockAggregate")

    event = MockDomainEvent(
        aggregate_id="1",
        aggregate_type="MockAggregate",
    )
    response = CommandResponse(
        result=MockAggregate(id="1"),
        events=[event],
        correlation_id="test-correlation-id",
    )
    handler_registry = MagicMock()
    handler_registry.get_command_handler = MagicMock(
        return_value=_make_handler_class(response)
    )

    uow_factory = MockUnitOfWork

    mediator = EventSourcedMediator(
        registry=handler_registry,
        uow_factory=uow_factory,
        event_persistence_orchestrator=orchestrator,
    )

    command = CreateOrder()
    _ = await mediator.send(command)

    # Verify events were persisted
    assert len(event_store.events) == 1
    assert event_store.events[0]["event_type"] == "MockDomainEvent"
    print("✓ Events persisted within transaction")


async def test_non_event_sourced_aggregate_events_skipped() -> None:
    """Test that events from non-event-sourced aggregates are not persisted."""
    event_store = MockEventStore()
    orchestrator = EventSourcedPersistenceOrchestrator(event_store)
    orchestrator.register_event_sourced_type("MockAggregate")
    orchestrator.register_non_event_sourced_type("NonEventSourced")

    event = MockDomainEvent(
        aggregate_id="1",
        aggregate_type="NonEventSourced",
    )
    response = CommandResponse(
        result=MockAggregate(id="1"),
        events=[event],
        correlation_id="test-correlation-id",
    )
    handler_registry = MagicMock()
    handler_registry.get_command_handler = MagicMock(
        return_value=_make_handler_class(response)
    )

    uow_factory = MockUnitOfWork

    mediator = EventSourcedMediator(
        registry=handler_registry,
        uow_factory=uow_factory,
        event_persistence_orchestrator=orchestrator,
    )

    command = CreateOrder()
    _ = await mediator.send(command)

    # Verify events were NOT persisted
    assert len(event_store.events) == 0
    print("✓ Non-event-sourced aggregate events skipped")


async def test_configure_event_sourced_type() -> None:
    """Test configure_event_sourced_type convenience method."""
    event_store = MockEventStore()

    uow_factory = MockUnitOfWork
    handler_registry = MagicMock()
    handler_registry.get_command_handler = MagicMock(return_value=type(AsyncMock()))

    orchestrator = EventSourcedPersistenceOrchestrator(event_store)

    mediator = EventSourcedMediator(
        registry=handler_registry,
        uow_factory=uow_factory,
        event_persistence_orchestrator=orchestrator,
    )

    # Configure aggregate type
    mediator.configure_event_sourced_type("TestAggregate")

    # Verify registration
    assert orchestrator.is_event_sourced("TestAggregate")
    print("✓ Aggregate type configured as event-sourced")


async def test_configure_non_event_sourced_type() -> None:
    """Test configure_non_event_sourced_type convenience method."""
    event_store = MockEventStore()

    uow_factory = MockUnitOfWork
    handler_registry = MagicMock()
    handler_registry.get_command_handler = MagicMock(return_value=type(AsyncMock()))

    orchestrator = EventSourcedPersistenceOrchestrator(event_store)

    mediator = EventSourcedMediator(
        registry=handler_registry,
        uow_factory=uow_factory,
        event_persistence_orchestrator=orchestrator,
    )

    # Configure non-event-sourced aggregate type
    mediator.configure_non_event_sourced_type("TestAggregate")

    # Verify registration
    assert not orchestrator.is_event_sourced("TestAggregate")
    print("✓ Aggregate type configured as non-event-sourced")


async def test_factory_creates_configured_mediator() -> None:
    """Test EventSourcedMediatorFactory."""
    event_store = MockEventStore()

    uow_factory = MockUnitOfWork
    handler_registry = MagicMock()
    handler_registry.get_command_handler = MagicMock(return_value=type(AsyncMock()))

    factory = EventSourcedMediatorFactory(
        event_store=event_store,
        uow_factory=uow_factory,
        handler_registry=handler_registry,
    )

    # Configure aggregate types
    factory.register_event_sourced_type("Order")
    factory.register_event_sourced_type("Invoice")

    # Create mediator
    mediator = factory.create()

    # Verify orchestrator is configured
    assert mediator._event_persistence_orchestrator is not None
    assert mediator._event_persistence_orchestrator.is_event_sourced("Order")
    assert mediator._event_persistence_orchestrator.is_event_sourced("Invoice")

    print("✓ Factory creates configured mediator")


async def test_configure_without_orchestrator_raises() -> None:
    """Test that configure_event_sourced_type raises without orchestrator."""
    uow_factory = MockUnitOfWork
    handler_registry = MagicMock()
    handler_registry.get_command_handler = MagicMock(return_value=type(AsyncMock()))

    mediator = EventSourcedMediator(
        registry=handler_registry,
        uow_factory=uow_factory,
        # event_persistence_orchestrator not provided
    )

    # Should raise EventSourcingConfigurationError
    with pytest.raises(
        EventSourcingConfigurationError, match="Cannot configure event-sourced types"
    ):
        mediator.configure_event_sourced_type("TestAggregate")

    print("✓ Raises error without orchestrator")


# Helper classes for tests
class CreateOrder:
    """Mock command for testing."""

    def __init__(self, correlation_id: str = "test-correlation-id") -> None:
        self.correlation_id = correlation_id


def _make_handler_class(response: CommandResponse[Any]) -> type:
    """Create a handler class that returns the given CommandResponse (for mediator factory)."""

    class _Handler:
        async def handle(self, command: Any) -> CommandResponse[Any]:
            return response

    return _Handler
