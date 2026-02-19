# Event Sourcing — Production usage

Example of wiring **EventSourcedLoader**, **EventSourcedRepository**, and **UpcastingEventReader** with SQLAlchemy and the persistence dispatcher.

## 1. Domain: aggregate and events

```python
# your_app/domain/order.py
from cqrs_ddd_core.domain.aggregate import AggregateRoot
from cqrs_ddd_core.domain.events import DomainEvent


class OrderCreated(DomainEvent):
    order_id: str = ""
    amount: float = 0.0
    currency: str = "EUR"


class OrderPaid(DomainEvent):
    order_id: str = ""
    transaction_id: str = ""


class Order(AggregateRoot[str]):
    status: str = "pending"
    amount: float = 0.0
    currency: str = "EUR"

    def apply_OrderCreated(self, event: OrderCreated) -> None:
        object.__setattr__(self, "status", "created")
        object.__setattr__(self, "amount", event.amount)
        object.__setattr__(self, "currency", getattr(event, "currency", "EUR"))

    def apply_OrderPaid(self, event: OrderPaid) -> None:
        object.__setattr__(self, "status", "paid")
```

**Handler naming:** Both styles are supported: `apply_OrderCreated` (PascalCase) and `apply_order_created` (snake_case). Snake_case is recommended for ruff (N802) compliance.

## 2. Registries and upcasters

```python
# your_app/infrastructure/registries.py
from cqrs_ddd_core.domain.event_registry import EventTypeRegistry

from cqrs_ddd_advanced_core.upcasting import EventUpcaster, UpcasterRegistry
from cqrs_ddd_advanced_core.snapshots import EveryNEventsStrategy, SnapshotStrategyRegistry

from your_app.domain.order import Order, OrderCreated, OrderPaid


def build_event_registry() -> EventTypeRegistry:
    reg = EventTypeRegistry()
    reg.register("OrderCreated", OrderCreated)
    reg.register("OrderPaid", OrderPaid)
    return reg


def build_upcaster_registry() -> UpcasterRegistry:
    reg = UpcasterRegistry()
    # Optional: add upcasters when you evolve event schemas
    # reg.register(OrderCreatedV1ToV2())
    return reg


def build_snapshot_strategy_registry() -> SnapshotStrategyRegistry:
    reg = SnapshotStrategyRegistry()
    reg.register("Order", EveryNEventsStrategy(n=50))
    return reg
```

## 3. Wiring with SQLAlchemy UoW

Assume you have a `SQLAlchemyUnitOfWork` (or a factory that returns it) and access to `uow.session` inside a request.

```python
# your_app/infrastructure/event_sourcing.py
from cqrs_ddd_core.ports.event_store import IEventStore
from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

from cqrs_ddd_advanced_core.event_sourcing import EventSourcedRepository
from cqrs_ddd_persistence_sqlalchemy.core.event_store import SQLAlchemyEventStore
from cqrs_ddd_persistence_sqlalchemy.advanced.snapshots import SQLAlchemySnapshotStore

from your_app.domain.order import Order
from your_app.infrastructure.registries import (
    build_event_registry,
    build_snapshot_strategy_registry,
    build_upcaster_registry,
)


def get_event_store(uow: UnitOfWork | None) -> IEventStore:
    if uow is None:
        raise ValueError("UnitOfWork required for event store")
    session = uow.session  # type: ignore[union-attr]
    return SQLAlchemyEventStore(session)


def get_snapshot_store(uow: UnitOfWork | None) -> SQLAlchemySnapshotStore | None:
    if uow is None:
        return None
    return SQLAlchemySnapshotStore(uow_factory=lambda: uow)


_event_registry = build_event_registry()
_upcaster_registry = build_upcaster_registry()
_snapshot_strategy_registry = build_snapshot_strategy_registry()


def create_order_repository() -> EventSourcedRepository[Order, str]:
    return EventSourcedRepository(
        Order,
        get_event_store=get_event_store,
        event_registry=_event_registry,
        get_snapshot_store=get_snapshot_store,
        snapshot_strategy_registry=_snapshot_strategy_registry,
        upcaster_registry=_upcaster_registry,
        create_aggregate=lambda aid: Order(id=aid),
    )
```

## 4. Using the repository (command handler)

Use **EventSourcedRepository** for retrieve + persist so load and save stay in the same transaction.

```python
# your_app/application/commands.py
from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

from your_app.domain.order import Order, OrderCreated, OrderPaid
from your_app.infrastructure.event_sourcing import create_order_repository


async def handle_pay_order(
    order_id: str,
    transaction_id: str,
    uow: UnitOfWork,
) -> str:
    repo = create_order_repository()
    orders = await repo.retrieve([order_id], uow)
    if not orders:
        raise ValueError(f"Order {order_id} not found")
    order = orders[0]
    event = OrderPaid(
        aggregate_id=order_id,
        aggregate_type="Order",
        order_id=order_id,
        transaction_id=transaction_id,
    )
    order.add_event(event)
    events = order.collect_events()
    await repo.persist(order, uow, events=events)
    return order_id
```

## 5. Using the loader directly (when you are not using the dispatcher)

Use **EventSourcedLoader** when you need to load an aggregate by ID without going through the persistence dispatcher (e.g. in a saga or a custom service).

```python
from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

from cqrs_ddd_advanced_core.event_sourcing import EventSourcedLoader
from your_app.infrastructure.event_sourcing import (
    get_event_store,
    get_snapshot_store,
)
from your_app.infrastructure.registries import (
    build_event_registry,
    build_snapshot_strategy_registry,
    build_upcaster_registry,
)
from your_app.domain.order import Order


async def load_order(order_id: str, uow: UnitOfWork) -> Order | None:
    loader = EventSourcedLoader(
        Order,
        get_event_store(uow),
        build_event_registry(),
        snapshot_store=get_snapshot_store(uow),
        upcaster_registry=build_upcaster_registry(),
        snapshot_strategy_registry=build_snapshot_strategy_registry(),
        create_aggregate=lambda aid: Order(id=aid),
    )
    return await loader.load(order_id)
```

## 6. Using UpcastingEventReader (projections / catch-up)

Use **UpcastingEventReader** when you read events for projections or rebuilds and want payloads upcast to the current schema.

```python
from cqrs_ddd_advanced_core.event_sourcing import UpcastingEventReader
from cqrs_ddd_core.domain.event_registry import EventTypeRegistry
from your_app.infrastructure.event_sourcing import get_event_store
from your_app.infrastructure.registries import build_upcaster_registry, build_event_registry


async def rebuild_order_projection(uow: UnitOfWork) -> None:
    event_store = get_event_store(uow)
    reader = UpcastingEventReader(event_store, build_upcaster_registry())
    event_registry = build_event_registry()
    all_events = await reader.get_all()
    for stored in all_events:
        if stored.aggregate_type != "Order":
            continue
        event = event_registry.hydrate(stored.event_type, stored.payload)
        if event:
            # Update read model / projection
            ...
```

## 7. Register with PersistenceDispatcher (optional)

To use **EventSourcedRepository** via the dispatcher’s `fetch_domain` and `apply`:

```python
from cqrs_ddd_advanced_core.persistence import PersistenceDispatcher, PersistenceRegistry
from your_app.infrastructure.event_sourcing import create_order_repository
from your_app.infrastructure.uow import create_uow_factory

registry = PersistenceRegistry()
registry.register_retrieval(Order, create_order_repository())
registry.register_operation(Order, create_order_repository())

dispatcher = PersistenceDispatcher(
    uow_factories={"default": create_uow_factory()},
    registry=registry,
)

# Then: orders = await dispatcher.fetch_domain(Order, [order_id], uow=uow)
#       await dispatcher.apply(entity, uow=uow, events=events)
```

## 8. Event Handler Formalization

The advanced package provides comprehensive formalization for event handlers in aggregates, including optional mixins, validation, and decorators.

### 8.1 Optional Mixin for Helper Methods

Add `EventSourcedAggregateMixin` for introspection and validation support:

```python
from cqrs_ddd_core.domain.aggregate import AggregateRoot
from cqrs_ddd_advanced_core.domain.aggregate_mixin import EventSourcedAggregateMixin

class Order(AggregateRoot[str], EventSourcedAggregateMixin[str]):
    status: str = "pending"
    amount: float = 0.0
    currency: str = "EUR"

    def apply_OrderCreated(self, event: OrderCreated) -> None:
        self.status = "created"
        self.amount = event.amount
        self.currency = event.currency

    def apply_OrderPaid(self, event: OrderPaid) -> None:
        self.status = "paid"

# Use mixin methods for introspection
order = Order(id="1")
order.has_handler_for_event("OrderCreated")  # True
order.get_handler_for_event("OrderCreated")  # Returns apply_OrderCreated
order._get_supported_event_types()  # {"OrderCreated", "OrderPaid"}
```

### 8.2 Validation Configuration

Enable or disable runtime validation with configurable modes:

```python
from cqrs_ddd_advanced_core.domain.event_validation import (
    EventValidationConfig,
    EventValidator,
)

# Lenient mode (default) - allows apply_event fallback
lenient_validator = EventValidator(EventValidationConfig(
    enabled=True,
    strict_mode=False,
))

# Strict mode - requires exact apply_<EventType> methods
strict_validator = EventValidator(EventValidationConfig(
    enabled=True,
    strict_mode=True,
))

# Disabled - no validation (performance mode)
no_validation = EventValidator(EventValidationConfig(
    enabled=False,
))

# Use with DefaultEventApplicator
from cqrs_ddd_advanced_core.event_sourcing.loader import DefaultEventApplicator

applicator = DefaultEventApplicator(validator=strict_validator)
```

### 8.3 Optional Decorators

Use decorators for metadata and per-aggregate validation configuration:

```python
from cqrs_ddd_advanced_core.domain.event_handlers import (
    aggregate_event_handler,
    aggregate_event_handler_validator,
)

# Configure validation at aggregate level
@aggregate_event_handler_validator(enabled=True, strict=True)
class Order(AggregateRoot[str], EventSourcedAggregateMixin[str]):
    status: str = "pending"

    @aggregate_event_handler()
    def apply_OrderCreated(self, event: OrderCreated) -> None:
        self.status = "created"

    @aggregate_event_handler(event_type=OrderCreated)
    def handle_creation(self, event: OrderCreated) -> None:
        # Alternative handler name with explicit event type
        self.status = "created"
```

### 8.4 Enhanced DefaultEventApplicator

The `DefaultEventApplicator` now supports validation flags:

```python
from cqrs_ddd_advanced_core.domain.event_validation import EventValidator
from cqrs_ddd_advanced_core.event_sourcing.loader import (
    DefaultEventApplicator,
)

# With validation (default)
validator = EventValidator(EventValidationConfig(enabled=True))
applicator = DefaultEventApplicator(
    validator=validator,
    raise_on_missing_handler=True,  # Raise if no handler found
)

# Without validation (performance)
no_validation = EventValidator(EventValidationConfig(enabled=False))
applicator = DefaultEventApplicator(validator=no_validation)

# Apply events
result = applicator.apply(aggregate, event)
```

### 8.5 Error Handling

Formalization provides clear, specific error messages:

```python
from cqrs_ddd_advanced_core.exceptions import (
    MissingEventHandlerError,
    StrictValidationViolationError,
)

try:
    validator.validate_handler_exists(aggregate, event)
except MissingEventHandlerError as e:
    # Clear error: "Aggregate 'Order' has no handler for event 'OrderCreated'"
    print(f"Aggregate: {e.aggregate_type}")
    print(f"Event: {e.event_type}")

except StrictValidationViolationError as e:
    # Clear error: "Strict validation violation for Order.OrderCreated: ..."
    print(f"Aggregate: {e.aggregate_type}")
    print(f"Event: {e.event_type}")
    print(f"Reason: {e.reason}")
```

## Summary

| Component                 | Use when                                                                 |
|--------------------------|--------------------------------------------------------------------------|
| **EventSourcedRepository** | Load/save aggregates in app code or via PersistenceDispatcher (same UoW). |
| **EventSourcedLoader**     | Load a single aggregate by ID when you have event_store + optional snapshot/upcast. |
| **UpcastingEventReader**   | Read events for projections/rebuilds with payloads upcast to current schema. |
| **EventSourcedAggregateMixin** | Add introspection and validation support to event-sourced aggregates. |
| **EventValidator**         | Configure validation modes (lenient/strict/enabled/disabled). |
| **@aggregate_event_handler**         | Decorate methods to mark them as event handlers (metadata only). |
| **@aggregate_event_handler_validator** | Configure validation at aggregate class level. |
