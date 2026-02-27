# Event Sourcing — Production Usage

Complete guide to implementing event-sourced aggregates with the CQRS-DDD Toolkit.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Core Components](#core-components)
   - [EventSourcedRepository](#1-eventsourcedrepository)
   - [EventSourcedMediator](#2-eventsourcedmediator)
   - [EventSourcedMediatorFactory](#3-eventsourcedmediatorfactory)
   - [@non_event_sourced Decorator](#4-non_event_sourced-decorator)
   - [PersistenceOrchestrator](#5-persistenceorchestrator)
4. [Quick Start](#quick-start)
5. [Integration with Projections](#integration-with-projections)
6. [Event Evolution & Upcasting](#event-evolution--upcasting)
7. [Snapshots](#snapshots)
8. [Best Practices](#best-practices)

---

## Overview

**Event Sourcing** persists the state of an aggregate as a sequence of events rather than just its current state. Every state change is captured as an immutable event that can be replayed to reconstruct the aggregate's state.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         EVENT SOURCING FLOW                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Command Handler                                                        │
│  ┌──────────────────┐                                                   │
│  │ 1. Load Events   │                                                   │
│  │ 2. Rebuild State │                                                   │
│  │ 3. Execute Cmd   │                                                   │
│  │ 4. Collect Event │                                                   │
│  │ 5. Persist Event │                                                   │
│  └────────┬─────────┘                                                   │
│           │                                                             │
│           ▼                                                             │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │                      EVENT STORE                              │      │
│  ├──────────────────────────────────────────────────────────────┤      │
│  │                                                               │      │
│  │  Order #123                                                   │      │
│  │  ┌─────────────────────────────────────────────────────────┐│      │
│  │  │ v1: OrderCreated (amount=100, currency=EUR)             ││      │
│  │  │ v2: OrderItemAdded (product=ABC, qty=2, price=50)       ││      │
│  │  │ v3: OrderSubmitted (submitted_at=2026-02-21)            ││      │
│  │  └─────────────────────────────────────────────────────────┘│      │
│  │                                                               │      │
│  │  Event Stream: [OrderCreated → OrderItemAdded → Submitted]  │      │
│  │                                                               │      │
│  └──────────────────────────────────────────────────────────────┘      │
│           │                                                             │
│           ├──────────────────────┬─────────────────────┐                │
│           │                      │                     │                │
│           ▼                      ▼                     ▼                │
│  ┌────────────────┐    ┌─────────────────┐   ┌──────────────────┐     │
│  │  Aggregate     │    │  Snapshot       │   │  Projections     │     │
│  │  Reconstruction│    │  Store          │   │  (Read Models)   │     │
│  │                │    │                 │   │                  │     │
│  │  Replay Events │    │  Every N events │   │  OrderSummary    │     │
│  │  → Current     │    │  → Fast load    │   │  CustomerStats   │     │
│  │    State       │    │                 │   │  ProductSales    │     │
│  └────────────────┘    └─────────────────┘   └──────────────────┘     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Key Benefits

| Benefit | Description |
|---------|-------------|
| **Complete Audit Trail** | Every state change captured as immutable event |
| **Temporal Queries** | Reconstruct aggregate state at any point in time |
| **Debugging** | Replay events to understand how state evolved |
| **Event Replay** | Rebuild read models/projections from event history |
| **Schema Evolution** | Upcast events to migrate to new schemas |
| **Undo/Rollback** | Reverse events to restore previous state |

---

## Architecture

### Event Sourcing vs State Storage

| Aspect | State Storage | Event Sourcing |
|--------|--------------|----------------|
| **Persists** | Current state only | All state changes as events |
| **Query** | `SELECT * FROM orders WHERE id = ?` | Replay events for aggregate |
| **Update** | `UPDATE orders SET status = ?` | Append `OrderSubmitted` event |
| **Delete** | `DELETE FROM orders` | Append `OrderDeleted` event |
| **Audit** | Optional audit log | Built-in complete audit trail |
| **Schema Evolution** | Migrations (destructive) | Upcasting (non-destructive) |
| **Replay** | Not possible | Rebuild any time |

### Event Structure

```python
from cqrs_ddd_core.ports.event_store import StoredEvent

@dataclass
class StoredEvent:
    event_id: str              # Unique event identifier
    event_type: str            # "OrderCreated", "OrderSubmitted"
    aggregate_id: str          # "order_123"
    aggregate_type: str        # "Order"
    version: int               # 1, 2, 3... (aggregate sequence)
    schema_version: int        # 1, 2, 3... (event schema version)
    payload: dict              # Event data {"amount": 100, "currency": "EUR"}
    metadata: dict             # {"user_id": "user_456", "ip": "192.168.1.1"}
    occurred_at: datetime      # When event occurred
    correlation_id: str | None # For distributed tracing
    causation_id: str | None   # What caused this event
    position: int | None       # Global event position (for projections)
```

**Key Fields for Projections:**

- **`version`**: Aggregate-level sequence number (1st, 2nd, 3rd event for this aggregate)
- **`position`**: Global sequence number across all aggregates (used by projections for ordering)

---

## Core Components

### 1. EventSourcedRepository

Combines retrieval and persistence for event-sourced aggregates.

```python
from cqrs_ddd_advanced_core.event_sourcing import EventSourcedRepository
from cqrs_ddd_core.ports.event_store import IEventStore

class OrderRepository(EventSourcedRepository[Order, str]):
    """Event-sourced order repository."""

    async def retrieve(self, ids: Sequence[str], uow: UnitOfWork) -> list[Order]:
        # 1. Check for snapshot
        # 2. Load events after snapshot version
        # 3. Upcast events to current schema
        # 4. Replay events to rebuild state
        # 5. Return fully hydrated aggregate
        ...

    async def persist(self, entity: Order, uow: UnitOfWork) -> str:
        # 1. Collect new events from aggregate
        # 2. Convert to StoredEvent with version, position
        # 3. Append to event store (transactional)
        # 4. Maybe save snapshot (if strategy says so)
        ...
```

### 2. EventSourcedMediator

Extended Mediator with **mandatory transactional event persistence**.

**Purpose**: Ensures events are persisted in the **same transaction** as command execution, guaranteeing data integrity.

```python
from cqrs_ddd_advanced_core.cqrs.event_sourced_mediator import EventSourcedMediator
from cqrs_ddd_advanced_core.event_sourcing.persistence_orchestrator import (
    EventSourcedPersistenceOrchestrator,
)

# Setup orchestrator
orchestrator = EventSourcedPersistenceOrchestrator(
    default_event_store=event_store,
    enforce_registration=True,
)
orchestrator.register_event_sourced_type("Order")

# Configure Mediator
mediator = EventSourcedMediator(
    registry=handler_registry,
    uow_factory=uow_factory,
    event_dispatcher=event_dispatcher,
    event_persistence_orchestrator=orchestrator,
)

# Command handler (events persisted automatically)
async def handle_create_order(command: CreateOrder, uow: UnitOfWork):
    order = Order(id=command.order_id)
    order.create(command.customer_id, command.amount, command.currency)

    # Just return - events persisted by mediator!
    return CommandResponse(
        result=order.id,
        events=order.collect_events(),  # Mediator persists these
    )
```

**Event Persistence Flow**:

```
┌────────────────────────────────────────────────────────────────┐
│            EVENTSOURCED MEDIATOR FLOW                          │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  1. mediator.send(CreateOrder(...))                           │
│     ↓                                                          │
│  2. Core Mediator creates UnitOfWork scope                     │
│     ↓                                                          │
│  3. Command handler executes within UoW transaction            │
│     ↓                                                          │
│  4. Handler returns CommandResponse with events                │
│     ↓                                                          │
│  5. Core Mediator calls EventDispatcher (in-transaction)      │
│     ↓                                                          │
│  6. ⭐ EventSourcedPersistenceOrchestrator persists events     │
│     ↓                                                          │
│  7. UoW commits:                                               │
│     - Aggregate state changes                                  │
│     - EventStore records                                       │
│     - Any other database changes                               │
│                                                                │
│     OR rollback (if any step fails):                           │
│     - Everything rolls back together                           │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

**Key Benefits**:
- ✅ **Data Integrity**: Events and state changes commit atomically
- ✅ **No Lost Events**: If command fails, events rollback
- ✅ **Drop-in Replacement**: Extends core Mediator without breaking changes
- ✅ **Flexible Configuration**: Can register event-sourced and non-event-sourced types

**Configuration Methods**:

```python
# Method 1: Via orchestrator
orchestrator = EventSourcedPersistenceOrchestrator(event_store)
orchestrator.register_event_sourced_type("Order")
orchestrator.register_non_event_sourced_type("CacheEntry")

# Method 2: Via mediator convenience methods
mediator = EventSourcedMediator(
    registry=handler_registry,
    uow_factory=uow_factory,
    event_persistence_orchestrator=orchestrator,
)

mediator.configure_event_sourced_type("Order")
mediator.configure_non_event_sourced_type("CacheEntry")
```

### 3. EventSourcedMediatorFactory

Factory for creating pre-configured EventSourcedMediator instances.

**Purpose**: Simplifies setup with commonly used configurations.

```python
from cqrs_ddd_advanced_core.cqrs.factory import EventSourcedMediatorFactory

# Create factory (simplified setup)
factory = EventSourcedMediatorFactory(
    event_store=event_store,
    uow_factory=uow_factory,
    handler_registry=handler_registry,
    event_dispatcher=event_dispatcher,
    enforce_registration=True,
)

# Register event-sourced types
factory.register_event_sourced_type("Order")
factory.register_event_sourced_type("Invoice")

# Create mediator (ready to use)
mediator = factory.create()

# Use mediator
result = await mediator.send(CreateOrder(...))
# ✓ Events persisted transactionally
```

**Factory Benefits**:
- ✅ **Simplified Setup**: All configuration in one place
- ✅ **Type Safety**: Ensures all aggregates are registered
- ✅ **Validation**: Can enforce registration with `enforce_registration=True`

### 4. @non_event_sourced Decorator

Marks aggregates that should **NOT** persist events to EventStore.

**Use Cases**:
- In-memory caches
- Ephemeral state
- Audit logs (stored elsewhere)
- Temporary aggregates

```python
from cqrs_ddd_advanced_core.decorators.event_sourcing import non_event_sourced
from cqrs_ddd_core.domain.aggregate import AggregateRoot

@non_event_sourced
class CacheEntry(AggregateRoot[str]):
    """Cache entry with events that are NOT persisted."""

    def apply_CacheUpdated(self, event: CacheUpdated) -> None:
        self.value = event.new_value
        self.updated_at = event.updated_at

    def update(self, new_value: str):
        event = CacheUpdated(
            aggregate_id=self.id,
            new_value=new_value,
            updated_at=datetime.now(timezone.utc),
        )
        self.add_event(event)  # Event emitted but NOT persisted
```

**Important**:
- ⚠️ **Not for Critical Data**: Non-event-sourced aggregates should NOT be used for business-critical state
- ⚠️ **No Replay**: Events cannot be replayed to reconstruct state
- ⚠️ **No Audit Trail**: Events are lost after handling

**Integration with Factory**:

```python
# Mark aggregate as non-event-sourced
@non_event_sourced
class CacheEntry(AggregateRoot[str]):
    # ... events not persisted
    pass

# Register with factory
factory.register_non_event_sourced_type("CacheEntry")

# Or let decorator work automatically
factory.register_event_sourced_type("Order")  # Event-sourced
# CacheEntry events will be skipped (marked with @non_event_sourced)
```

### 5. PersistenceOrchestrator

Manages event persistence for event-sourced aggregates.

```python
from cqrs_ddd_advanced_core.event_sourcing.persistence_orchestrator import (
    EventSourcedPersistenceOrchestrator,
)

# Create orchestrator
orchestrator = EventSourcedPersistenceOrchestrator(
    default_event_store=event_store,
    enforce_registration=True,
)

# Register event-sourced types
orchestrator.register_event_sourced_type("Order")
orchestrator.register_event_sourced_type("Invoice")

# Register non-event-sourced types (events will be skipped)
orchestrator.register_non_event_sourced_type("CacheEntry")

# Use in mediator
mediator = EventSourcedMediator(
    registry=handler_registry,
    uow_factory=uow_factory,
    event_persistence_orchestrator=orchestrator,
)
```

**Orchestrator Responsibilities**:
1. **Type Registration**: Track which aggregates are event-sourced
2. **Event Routing**: Route events to correct EventStore
3. **Persistence**: Persist events within UoW transaction
4. **Validation**: Optionally enforce registration for all aggregate types

---

## Quick Start

### 1. Define Domain Events (Pydantic v2)

**Note**: Domain events use Pydantic v2 `BaseModel` with `frozen=True` for immutability, NOT `@dataclass`.

```python
from cqrs_ddd_core.domain.events import DomainEvent
from decimal import Decimal
from datetime import datetime

class OrderCreated(DomainEvent):
    """Order created event - inherits from Pydantic BaseModel."""
    order_id: str
    customer_id: str
    amount: Decimal
    currency: str = "EUR"

class OrderItemAdded(DomainEvent):
    """Item added to order."""
    order_id: str
    product_id: str
    product_name: str
    quantity: int
    unit_price: Decimal
    new_total: Decimal

class OrderSubmitted(DomainEvent):
    """Order submitted for processing."""
    order_id: str
    submitted_at: datetime
```

**Key Points**:
- ✅ `DomainEvent` extends Pydantic v2 `BaseModel` with `frozen=True`
- ✅ Events are immutable (frozen) by default
- ✅ Auto-generated fields: `event_id`, `occurred_at`, `version` (schema version)
- ✅ Metadata fields: `aggregate_id`, `aggregate_type`, `correlation_id`, `causation_id`

### 2. Define Aggregate with Event Handlers & Versioning

```python
from cqrs_ddd_core.domain.aggregate import AggregateRoot
from decimal import Decimal

class Order(AggregateRoot[str]):
    """Order aggregate with automatic version tracking."""
    customer_id: str = ""
    status: str = "pending"
    total: Decimal = Decimal("0.00")
    items: list[dict] = []

    def apply_OrderCreated(self, event: OrderCreated) -> None:
        """Apply OrderCreated event."""
        self.customer_id = event.customer_id
        self.total = event.amount
        self.status = "created"
        self.items = []

    def apply_OrderItemAdded(self, event: OrderItemAdded) -> None:
        """Apply OrderItemAdded event."""
        self.items.append({
            "product_id": event.product_id,
            "product_name": event.product_name,
            "quantity": event.quantity,
            "unit_price": event.unit_price,
        })
        self.total = event.new_total

    def apply_OrderSubmitted(self, event: OrderSubmitted) -> None:
        """Apply OrderSubmitted event."""
        self.status = "submitted"

    # Business methods
    def add_item(self, product_id: str, product_name: str, quantity: int, unit_price: Decimal):
        if self.status != "created":
            raise CannotModifyOrder("Order already submitted")

        new_total = self.total + (quantity * unit_price)

        event = OrderItemAdded(
            aggregate_id=self.id,
            aggregate_type="Order",
            order_id=self.id,
            product_id=product_id,
            product_name=product_name,
            quantity=quantity,
            unit_price=unit_price,
            new_total=new_total,
        )
        self.add_event(event)  # Triggers apply_OrderItemAdded
```

**How Aggregate Version Works**:

```
┌────────────────────────────────────────────────────────────────┐
│          AGGREGATE ROOT VERSIONING FLOW                        │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  1. Initial State (New Aggregate)                              │
│     Order(id="123", _version=0)                                │
│     ↓                                                          │
│  2. Create Order                                                │
│     order.create(...)                                          │
│     - Emits: OrderCreated event                                │
│     - _version still 0 (in memory)                             │
│     ↓                                                          │
│  3. Persist to EventStore                                       │
│     await repository.persist(order, uow)                       │
│     - Collects events from order                               │
│     - Converts to StoredEvent:                                 │
│       * version: 1 (first event for this aggregate)            │
│       * position: 1001 (global sequence)                       │
│     - Appends to EventStore                                    │
│     ↓                                                          │
│  4. Load Aggregate (Later)                                      │
│     order = await repository.retrieve(["123"], uow)            │
│     - Loads events: [OrderCreated(v1)]                         │
│     - Replays events                                           │
│     - Sets _version = 1 (from last event)                      │
│     ↓                                                          │
│  5. Add Item                                                    │
│     order.add_item(...)                                        │
│     - Emits: OrderItemAdded event                              │
│     - _version still 1 (in memory)                             │
│     ↓                                                          │
│  6. Persist Again                                               │
│     await repository.persist(order, uow)                       │
│     - Collects new events                                      │
│     - Converts to StoredEvent:                                 │
│       * version: 2 (second event for this aggregate)           │
│       * position: 1002 (global sequence)                       │
│     - Appends to EventStore                                    │
│     ↓                                                          │
│  7. Load Again (Later)                                          │
│     order = await repository.retrieve(["123"], uow)            │
│     - Loads events: [OrderCreated(v1), OrderItemAdded(v2)]     │
│     - Replays events                                           │
│     - Sets _version = 2 (from last event)                      │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

**Key Points**:
- **`_version`**: Private attribute managed by persistence layer
- **In Memory**: Version reflects last loaded/applied event
- **On Persist**: Repository increments version for each new event
- **On Load**: Repository sets version from last event in stream
- **Read-Only**: Access via `order.version` property

**Versioning Implementation**:

```python
# In EventSourcedRepository.persist()
async def persist(self, entity: Order, uow: UnitOfWork) -> str:
    events = entity.collect_events()
    current_version = entity.version  # Current aggregate version

    for i, event in enumerate(events):
        stored = StoredEvent(
            event_id=str(uuid4()),
            event_type=event.__class__.__name__,
            aggregate_id=entity.id,
            aggregate_type="Order",
            version=current_version + i + 1,  # Increment for each event
            payload=event.model_dump(),
            # position assigned by EventStore
        )
        await self._event_store.append(stored)

    # Update in-memory version
    object.__setattr__(entity, "_version", current_version + len(events))

# In EventSourcedRepository.retrieve()
async def retrieve(self, ids: Sequence[str], uow: UnitOfWork) -> list[Order]:
    orders = []
    for agg_id in ids:
        # Load all events for aggregate
        events = await self._event_store.get_events(agg_id)

        if events:
            # Create empty aggregate
            order = Order.reconstitute(aggregate_id=agg_id)

            # Replay events
            for stored in events:
                event = hydrate(stored)
                order.apply_event(event)  # Calls apply_OrderCreated, etc.

            # Set version from last event
            last_version = events[-1].version
            object.__setattr__(order, "_version", last_version)

            orders.append(order)

    return orders
```

**Version vs Position**:

| Aspect | `version` | `position` |
|--------|-----------|------------|
| **Scope** | Per-aggregate | Global (all aggregates) |
| **Purpose** | Aggregate event sequence | Event store ordering |
| **Example** | Order #123: 1, 2, 3 | Global: 1001, 1002, 1003 |
| **Used For** | Snapshots, loading events | Projections, pagination |
| **Assigned By** | Repository | EventStore (database sequence) |

**Snapshot Integration**:

```python
# When snapshot exists
async def retrieve(self, ids: Sequence[str], uow: UnitOfWork) -> list[Order]:
    for agg_id in ids:
        # Try to load snapshot
        snapshot = await self._snapshot_store.load(agg_id, uow)

        if snapshot:
            # Start from snapshot state
            order = Order.reconstitute(agg_id, **snapshot.state)
            object.__setattr__(order, "_version", snapshot.version)

            # Load only events after snapshot
            events = await self._event_store.get_events(
                agg_id,
                after_version=snapshot.version
            )
        else:
            # No snapshot, load all events
            order = Order.reconstitute(agg_id)
            events = await self._event_store.get_events(agg_id)

        # Replay events
        for stored in events:
            event = hydrate(stored)
            order.apply_event(event)

        # Update version
        if events:
            last_version = events[-1].version
            object.__setattr__(order, "_version", last_version)
```
```

### 3. Setup Registries

```python
from cqrs_ddd_core.domain.event_registry import EventTypeRegistry
from cqrs_ddd_advanced_core.upcasting import UpcasterRegistry
from cqrs_ddd_advanced_core.snapshots import SnapshotStrategyRegistry, EveryNEventsStrategy

# Event registry (maps event type names to classes)
event_registry = EventTypeRegistry()
event_registry.register("OrderCreated", OrderCreated)
event_registry.register("OrderItemAdded", OrderItemAdded)
event_registry.register("OrderSubmitted", OrderSubmitted)

# Upcaster registry (optional - for schema evolution)
upcaster_registry = UpcasterRegistry()
# upcaster_registry.register(OrderCreatedV1ToV2())

# Snapshot strategy (optional - for performance)
snapshot_strategy_registry = SnapshotStrategyRegistry()
snapshot_strategy_registry.register("Order", EveryNEventsStrategy(n=50))
```

### 4. Create Repository

```python
from cqrs_ddd_persistence_sqlalchemy.core.event_store import SQLAlchemyEventStore
from cqrs_ddd_persistence_sqlalchemy.advanced.snapshots import SQLAlchemySnapshotStore

def get_event_store(uow: UnitOfWork) -> IEventStore:
    return SQLAlchemyEventStore(uow.session)

def get_snapshot_store(uow: UnitOfWork) -> SQLAlchemySnapshotStore | None:
    return SQLAlchemySnapshotStore(uow_factory=lambda: uow)

order_repository = EventSourcedRepository(
    aggregate_type=Order,
    get_event_store=get_event_store,
    event_registry=event_registry,
    get_snapshot_store=get_snapshot_store,
    snapshot_strategy_registry=snapshot_strategy_registry,
    upcaster_registry=upcaster_registry,
    create_aggregate=lambda aid: Order(id=aid),
)
```

### 5. Use in Command Handler

```python
async def handle_add_item_to_order(
    order_id: str,
    product_id: str,
    product_name: str,
    quantity: int,
    unit_price: Decimal,
    uow: UnitOfWork,
) -> str:
    # Load aggregate
    orders = await order_repository.retrieve([order_id], uow)
    if not orders:
        raise OrderNotFound(order_id)

    order = orders[0]

    # Execute business logic
    order.add_item(product_id, product_name, quantity, unit_price)

    # Persist
    await order_repository.persist(order, uow)

    return order.id
```

### 6. Use EventSourcedMediator (Alternative - Transactional Event Persistence)

**Option A: Direct Configuration**

```python
from cqrs_ddd_advanced_core.cqrs.event_sourced_mediator import EventSourcedMediator
from cqrs_ddd_advanced_core.event_sourcing.persistence_orchestrator import (
    EventSourcedPersistenceOrchestrator,
)

# Setup orchestrator
orchestrator = EventSourcedPersistenceOrchestrator(
    default_event_store=event_store,
    enforce_registration=True,
)
orchestrator.register_event_sourced_type("Order")

# Configure Mediator
mediator = EventSourcedMediator(
    registry=handler_registry,
    uow_factory=uow_factory,
    event_dispatcher=event_dispatcher,
    event_persistence_orchestrator=orchestrator,
)

# Command handler (events persisted automatically)
async def handle_create_order(command: CreateOrder, uow: UnitOfWork):
    order = Order(id=command.order_id)
    order.create(command.customer_id, command.amount, command.currency)

    # Just return - events persisted by mediator!
    return CommandResponse(
        result=order.id,
        events=order.collect_events(),  # Mediator persists these
    )
```

**Option B: Using Factory (Recommended)**

```python
from cqrs_ddd_advanced_core.cqrs.factory import EventSourcedMediatorFactory

# Create factory (simplified setup)
factory = EventSourcedMediatorFactory(
    event_store=event_store,
    uow_factory=uow_factory,
    handler_registry=handler_registry,
    event_dispatcher=event_dispatcher,
    enforce_registration=True,
)

# Register event-sourced types
factory.register_event_sourced_type("Order")
factory.register_event_sourced_type("Invoice")

# Create mediator (ready to use)
mediator = factory.create()

# Use mediator
result = await mediator.send(CreateOrder(...))
# ✓ Events persisted transactionally
```

**Key Benefits**:
- ✅ **Automatic Persistence**: Events persisted in same transaction as command
- ✅ **No Manual Persist**: Don't need to call `repository.persist()`
- ✅ **Data Integrity**: Events and state changes commit together
- ✅ **Simplified Handlers**: Focus on business logic only

---

## Integration with Projections

### Event Flow to Projections

```
┌─────────────────────────────────────────────────────────────────────────┐
│               EVENT SOURCING → PROJECTIONS INTEGRATION                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Command Handler                                                        │
│  ┌──────────────────┐                                                   │
│  │ 1. Load Order    │                                                   │
│  │ 2. Modify        │                                                   │
│  │ 3. Persist       │──────────┐                                        │
│  └──────────────────┘          │                                        │
│                                ▼                                        │
│                   ┌────────────────────────┐                            │
│                   │      EVENT STORE       │                            │
│                   │  - position: 1001      │                            │
│                   │  - event_id: abc123    │                            │
│                   │  - version: 3          │                            │
│                   └────────┬───────────────┘                            │
│                            │                                            │
│                            │ Events with position & event_id            │
│                            ▼                                            │
│                   ┌────────────────────────┐                            │
│                   │  PROJECTION WORKER     │                            │
│                   │                        │                            │
│                   │  - Tracks position     │                            │
│                   │  - Calls handlers      │                            │
│                   │  - Updates projections │                            │
│                   └────────┬───────────────┘                            │
│                            │                                            │
│                            ▼                                            │
│                   ┌────────────────────────┐                            │
│                   │  PROJECTION STORE      │                            │
│                   │                        │                            │
│                   │  - order_summaries     │                            │
│                   │  - _version: 3         │◀─┐                         │
│                   │  - _last_event_id: ... │  │ Idempotency             │
│                   │  - _last_event_pos: .. │──┘ Optimistic Concurrency  │
│                   └────────────────────────┘                            │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Key Integration Points

#### 1. Event Position Tracking

**Event Store assigns `position`:**
```python
# In EventSourcedRepository._persist_internal()
stored = StoredEvent(
    event_id=str(uuid4()),
    event_type="OrderSubmitted",
    aggregate_id="order_123",
    version=3,  # Aggregate sequence
    position=1001,  # Global sequence (assigned by event store)
    payload={...},
)
await event_store.append(stored)
```

**Projection Worker uses `position`:**
```python
# In ProjectionWorker
async def run(self, projection_name: str):
    # Resume from last position
    last_position = await self.position_store.get_position(projection_name)

    # Stream events after position
    async for event in self.event_store.get_events_from_position(last_position or 0):
        # Handle event
        await self.handle_event(event, uow)

        # Save position (in same UoW)
        await self.position_store.save_position(
            projection_name,
            event.position,  # Use global position
            uow=uow,
        )
```

#### 2. Idempotency via event_id

**Projection handlers use `event_id` for idempotency:**

```python
class OrderSummaryHandler:
    def __init__(self, writer: IProjectionWriter):
        self.writer = writer

    async def handle(self, event: StoredEvent, uow: UnitOfWork):
        data = json.loads(event.payload)

        # Upsert with event_id for idempotency
        await self.writer.upsert(
            collection="order_summaries",
            doc_id=event.aggregate_id,
            data={
                "id": event.aggregate_id,
                "status": data["status"],
                "total": data["total"],
            },
            event_position=event.position,  # For version check
            event_id=event.event_id,  # For idempotency check
            uow=uow,
        )
```

**How it works:**
1. First time: `event_id` not in projection → Insert
2. Replay (same `event_id`): Already exists → Skip (idempotent)
3. Newer event: Higher `position` → Update (version check)

#### 3. Version-based Concurrency

**Projections use `position` for optimistic locking:**

```python
# In SQLAlchemyProjectionStore.upsert()
if event_position is not None:
    # Load existing
    existing = await self.get(collection, doc_id, uow=uow)

    if existing:
        existing_version = existing.get("_version", 0)

        # Optimistic concurrency check
        if existing_version >= event_position:
            logger.debug(
                f"Skipping stale update: {event_position} <= {existing_version}"
            )
            return False  # Skip older/duplicate event

    # Set version fields
    data["_version"] = event_position
    data["_last_event_id"] = event_id
    data["_last_event_position"] = event_position
```

**Example:**
```
Event #1: OrderCreated (position=1001) → Projection v1
Event #2: OrderItemAdded (position=1002) → Projection v2
Event #3: OrderSubmitted (position=1003) → Projection v3

Replay Scenario:
- Event #1 replayed → position=1001 < current v3 → Skip
- Event #2 replayed → position=1002 < current v3 → Skip
- Event #3 replayed → position=1003 == current v3 → Skip (idempotent)
- New Event #4 → position=1004 > current v3 → Update to v4
```

---

## Event Evolution & Upcasting

### When Schema Changes

```python
# V1 event (old schema)
class OrderCreatedV1(DomainEvent):
    """Old schema with float amount."""
    order_id: str
    customer_id: str
    amount: float  # Old: float

# V2 event (new schema)
class OrderCreatedV2(DomainEvent):
    """New schema with Decimal amount and currency."""
    order_id: str
    customer_id: str
    amount: Decimal  # New: Decimal
    currency: str = "EUR"  # New field
```

### Implement Upcaster

```python
from cqrs_ddd_advanced_core.upcasting import EventUpcaster

class OrderCreatedV1ToV2(EventUpcaster):
    event_type = "OrderCreated"
    from_version = 1
    to_version = 2

    def upcast(self, payload: dict) -> dict:
        # Migrate payload
        return {
            **payload,
            "amount": Decimal(str(payload["amount"])),  # float → Decimal
            "currency": payload.get("currency", "EUR"),  # Add default
        }

# Register
upcaster_registry.register(OrderCreatedV1ToV2())
```

### Load with Upcasting

```python
# All events automatically upcast to latest schema
loader = EventSourcedLoader(
    Order,
    event_store,
    event_registry,
    upcaster_registry=upcaster_registry,  # Automatic upcasting
)

order = await loader.load("order_123")  # All events at v2 schema
```

---

## Snapshots

### Why Snapshots?

Loading an aggregate with 1000+ events is slow. Snapshots store the aggregate state at a specific version, allowing the loader to:
1. Load snapshot
2. Load only events after snapshot version
3. Apply events to snapshot state

### Configure Snapshot Strategy

```python
from cqrs_ddd_advanced_core.snapshots import EveryNEventsStrategy

# Snapshot every 50 events
strategy = EveryNEventsStrategy(n=50)

# Register for aggregate type
snapshot_strategy_registry.register("Order", strategy)
```

### Snapshot Storage

```python
# Snapshots stored in same DB as events (transactional)
snapshot_store = SQLAlchemySnapshotStore(uow_factory)

# Snapshot structure
{
    "aggregate_id": "order_123",
    "aggregate_type": "Order",
    "version": 50,
    "state": {
        "customer_id": "cust_456",
        "status": "submitted",
        "total": "150.00",
        "items": [...]
    },
    "created_at": "2026-02-21T10:30:00Z"
}
```

---

## Best Practices

### 1. Use Explicit Event Handlers

```python
# ✅ GOOD: Explicit handlers
class Order(AggregateRoot[str]):
    def apply_OrderCreated(self, event: OrderCreated) -> None:
        self.customer_id = event.customer_id
        self.status = "created"

    def apply_OrderSubmitted(self, event: OrderSubmitted) -> None:
        self.status = "submitted"

# ❌ BAD: Generic handler
class Order(AggregateRoot[str]):
    def apply_event(self, event: DomainEvent) -> None:
        # Loses type safety, harder to debug
        if isinstance(event, OrderCreated):
            ...
```

### 2. Keep Events Immutable

```python
# ✅ GOOD: Frozen events (DomainEvent is frozen by default via Pydantic)
class OrderCreated(DomainEvent):
    """Immutable event - frozen by default."""
    order_id: str
    customer_id: str

# ❌ BAD: Mutable events (this won't work - DomainEvent is already frozen)
# class OrderCreated(DomainEvent):
#     def __init__(self, order_id, customer_id):
#         self.order_id = order_id  # Can be mutated!
```

**Note**: `DomainEvent` extends Pydantic v2 `BaseModel` with `frozen=True`, so all events are immutable by default.

### 3. Version All Events

```python
# ✅ GOOD: Schema versioning (version field inherited from DomainEvent)
class OrderCreated(DomainEvent):
    """Event with schema version."""
    order_id: str
    customer_id: str
    amount: Decimal
    currency: str = "EUR"

    # version field is inherited from DomainEvent base class
    # Defaults to 1, increment when schema changes

# ❌ BAD: No versioning (hard to evolve)
# DomainEvent always has version field, so this is not possible
```

### 4. Use UnitOfWork for Transactions

```python
# ✅ GOOD: Explicit UoW
async with uow_factory() as uow:
    order = await repo.retrieve([order_id], uow)
    order.submit()
    await repo.persist(order, uow)
    # Transactional commit

# ❌ BAD: No transaction boundary
order = await repo.retrieve([order_id], None)
order.submit()
await repo.persist(order, None)  # Auto-creates UoW (less control)
```

### 5. Integrate with Projections

```python
# ✅ GOOD: Projection handlers use event metadata
class OrderSummaryHandler:
    async def handle(self, event: StoredEvent, uow: UnitOfWork):
        await self.writer.upsert(
            "order_summaries",
            event.aggregate_id,
            data,
            event_position=event.position,  # For versioning
            event_id=event.event_id,  # For idempotency
            uow=uow,
        )

# ❌ BAD: Ignoring event metadata
class OrderSummaryHandler:
    async def handle(self, event: StoredEvent, uow: UnitOfWork):
        # No version or idempotency checks
        await self.writer.upsert("order_summaries", event.aggregate_id, data)
```

---

## Summary

| Component | Purpose | When to Use |
|-----------|---------|-------------|
| `EventSourcedRepository` | High-level repository for loading/persisting aggregates | Command handlers with manual persistence |
| `EventSourcedMediator` | Mediator with automatic transactional event persistence | **Recommended** for most use cases |
| `EventSourcedMediatorFactory` | Factory for creating pre-configured mediators | Simplified setup with multiple aggregates |
| `@non_event_sourced` | Decorator to skip event persistence | Caches, ephemeral state, non-critical data |
| `PersistenceOrchestrator` | Manages event persistence for different aggregate types | Advanced configuration |
| `EventSourcedLoader` | Low-level loader for rebuilding aggregates | Custom loading logic, sagas |
| `UpcastingEventReader` | Reads events with automatic schema migration | Projections, event replay |
| `SnapshotStore` | Performance optimization for large event streams | Aggregates with many events |

**Recommended Setup**:

1. **Simple Projects**: Use `EventSourcedRepository` directly in command handlers
2. **Most Projects**: Use `EventSourcedMediatorFactory` for automatic event persistence
3. **Advanced**: Customize `EventSourcedMediator` with `PersistenceOrchestrator`

**Complete Flow with EventSourcedMediator**:

```
┌────────────────────────────────────────────────────────────────┐
│          COMPLETE EVENT SOURCING ARCHITECTURE                  │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  1. Command: CreateOrder                                       │
│     ↓                                                          │
│  2. EventSourcedMediator.send(command)                        │
│     ↓                                                          │
│  3. Command Handler:                                           │
│     - Load Order from EventSourcedRepository                   │
│     - Execute business logic                                   │
│     - Return CommandResponse with events                       │
│     ↓                                                          │
│  4. EventSourcedMediator:                                      │
│     - Calls EventDispatcher (in-transaction handlers)         │
│     - Calls PersistenceOrchestrator.persist_events()          │
│     - Events appended to EventStore                            │
│     ↓                                                          │
│  5. UnitOfWork.commit():                                       │
│     - Aggregate state changes committed                        │
│     - Events committed to EventStore                           │
│     - All in ONE transaction                                   │
│     ↓                                                          │
│  6. ProjectionWorker:                                          │
│     - Streams events from EventStore (by position)            │
│     - Updates projections with optimistic concurrency         │
│     - Saves checkpoint for resume                              │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

**Key Takeaways**:

- ✅ **Use EventSourcedMediator** for automatic transactional event persistence
- ✅ **Use EventSourcedMediatorFactory** for simplified setup
- ✅ **Mark non-event-sourced aggregates** with `@non_event_sourced` decorator
- ✅ **Projections use `event.position`** for optimistic concurrency and idempotency
- ✅ **Events are immutable** and provide complete audit trail
- ✅ **Snapshots optimize** aggregates with many events

Event sourcing provides a complete audit trail, temporal queries, and seamless integration with projections for building scalable CQRS systems.
