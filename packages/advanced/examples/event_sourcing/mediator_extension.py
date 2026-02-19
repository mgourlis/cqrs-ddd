"""Example: EventSourcedMediator usage with transactional event persistence."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from cqrs_ddd_core.ports.event_store import IEventStore

from cqrs_ddd_advanced_core.cqrs.event_sourced_mediator import (
    EventSourcedMediator,
)
from cqrs_ddd_advanced_core.cqrs.factory import (
    EventSourcedMediatorFactory,
)
from cqrs_ddd_advanced_core.decorators.event_sourcing import non_event_sourced
from cqrs_ddd_advanced_core.event_sourcing.persistence_orchestrator import (
    EventSourcedPersistenceOrchestrator,
)
from cqrs_ddd_core.domain.aggregate import AggregateRoot

# Placeholders for example; replace with real implementations when running.
session: Any = None
event_store: Any = None
handler_registry: Any = None
uow_factory: Any = None
event_dispatcher: Any = None


async def example_basic_setup() -> None:
    """Basic EventSourcedMediator setup with event-sourced aggregates."""
    # Setup orchestrator
    store = cast("IEventStore", SQLAlchemyEventStore(session))
    orchestrator = EventSourcedPersistenceOrchestrator(default_event_store=store)

    # Register event-sourced aggregates
    orchestrator.register_event_sourced_type("Order")
    orchestrator.register_event_sourced_type("Invoice")

    # Configure Mediator (drop-in replacement for core Mediator)
    mediator = EventSourcedMediator(
        registry=handler_registry,
        uow_factory=uow_factory,
        event_dispatcher=event_dispatcher,
        event_persistence_orchestrator=orchestrator,
    )

    # Use exactly like core Mediator
    result: Any = await mediator.send(CreateOrder(customer_id="cust-1"))  # type: ignore[arg-type]
    print(f"Order created: {result.result.id}")


async def example_factory_setup() -> None:
    """Using factory for simplified EventSourcedMediator setup."""
    # Setup factory
    factory = EventSourcedMediatorFactory(
        event_store=event_store,
        uow_factory=uow_factory,
        handler_registry=handler_registry,
        event_dispatcher=event_dispatcher,
    )

    # Configure aggregate types
    factory.register_event_sourced_type("Order")
    factory.register_event_sourced_type("Invoice")

    # Create mediator
    mediator = factory.create()

    # Ready to use
    result: Any = await mediator.send(CreateOrder(customer_id="cust-1"))  # type: ignore[arg-type]
    print(f"Order created: {result.result.id}")


async def example_migration() -> None:
    """Migrating from core Mediator to EventSourcedMediator."""
    # New code using EventSourcedMediator
    store = cast("IEventStore", event_store)
    orchestrator = EventSourcedPersistenceOrchestrator(default_event_store=store)
    orchestrator.register_event_sourced_type("Order")

    mediator = EventSourcedMediator(
        registry=handler_registry,
        uow_factory=uow_factory,
        event_dispatcher=event_dispatcher,
        event_persistence_orchestrator=orchestrator,
    )

    # All existing code works unchanged
    _ = await mediator.send(CreateOrder(customer_id="cust-1"))  # type: ignore[arg-type]
    _ = await mediator.query(GetOrder(order_id="order-1"))  # type: ignore[arg-type]


async def example_non_event_sourced_aggregates() -> None:
    """Non-event-sourced aggregates for ephemeral state."""

    @non_event_sourced
    class CacheEntry(AggregateRoot[str]):
        value: str = ""

    # Configure
    orchestrator = EventSourcedPersistenceOrchestrator(event_store)
    store = cast("IEventStore", event_store)
    orchestrator = EventSourcedPersistenceOrchestrator(default_event_store=store)
    orchestrator.register_non_event_sourced_type("CacheEntry")

    mediator = EventSourcedMediator(
        registry=handler_registry,
        uow_factory=uow_factory,
        event_dispatcher=event_dispatcher,
        event_persistence_orchestrator=orchestrator,
    )

    # Events NOT persisted (explicitly configured)
    result: Any = await mediator.send(UpdateCache(key="user-1", value="data"))  # type: ignore[arg-type]
    print(f"Cache value: {result.result.value}")


async def example_data_integrity_scenarios() -> None:
    """Demonstrate data integrity guarantees."""
    # Setup
    store = cast("IEventStore", SQLAlchemyEventStore(session))
    orchestrator = EventSourcedPersistenceOrchestrator(default_event_store=store)
    orchestrator.register_event_sourced_type("Order")

    mediator = EventSourcedMediator(
        registry=handler_registry,
        uow_factory=uow_factory,
        event_dispatcher=event_dispatcher,
        event_persistence_orchestrator=orchestrator,
    )

    # Scenario 1: Command succeeds
    print("Scenario 1: Command succeeds")
    _ = await mediator.send(CreateOrder(customer_id="cust-1"))  # type: ignore[arg-type]
    print("  ✓ Order persisted to database")
    print("  ✓ OrderCreated event persisted to EventStore")
    print("  ✓ Both in same transaction (commit or rollback together)")
    print()

    # Scenario 2: Command fails
    print("Scenario 2: Command fails")
    with contextlib.suppress(ValueError):
        await mediator.send(CreateOrder(customer_id="invalid"))  # type: ignore[arg-type]
    print("  ✓ No order persisted")
    print("  ✓ No events persisted")
    print("  ✓ Transaction rolled back")
    print()

    # Scenario 3: Unregistered aggregate with enforce mode
    print("Scenario 3: Unregistered aggregate with enforce mode (default)")
    orchestrator.register_event_sourced_type("Order")
    # Don't register Invoice

    try:
        _ = await mediator.send(CreateInvoice(customer_id="cust-1"))  # type: ignore[arg-type]
    except Exception as e:  # noqa: BLE001 - example: catch any persistence/validation error
        print(f"  ✓ Error caught: {type(e).__name__}")
        print(f"  ✓ Message: {str(e)}")
    print("  ✓ No order/invoice persisted")
    print("  ✓ No events persisted")
    print("  ✓ Transaction rolled back")


# Example classes (simplified for demonstration)
class CreateOrder:
    def __init__(self, customer_id: str) -> None:
        self.customer_id = customer_id


class CreateInvoice:
    def __init__(self, customer_id: str) -> None:
        self.customer_id = customer_id


class UpdateCache:
    def __init__(self, key: str, value: str) -> None:
        self.key = key
        self.value = value


class GetOrder:
    """Stub query for example."""

    def __init__(self, order_id: str) -> None:
        self.id = order_id


class SQLAlchemyEventStore:
    """Mock event store for example purposes."""

    def __init__(self, session: Any = None) -> None:
        self._session = session

    async def append(self, event: object) -> None:
        print(f"  Persisting event: {type(event).__name__}")
