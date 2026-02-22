# Persistence Dispatcher

Unified dispatcher for command-side (write) and query-side (read) persistence operations.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Core Components](#core-components)
   - [PersistenceRegistry](#persistenceregistry)
   - [PersistenceDispatcher](#persistencedispatcher)
   - [CachingPersistenceDispatcher](#cachingpersistencedispatcher)
4. [Usage Examples](#usage-examples)
5. [Integration Patterns](#integration-patterns)
6. [Best Practices](#best-practices)

---

## Overview

The Persistence Dispatcher provides a **unified interface** for:

- **Command-side operations**: Persist aggregates (event-sourced or state-stored)
- **Domain entity retrieval**: Load aggregates by ID
- **Query-side operations**: Fetch read models by ID or specification

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         PERSISTENCE ARCHITECTURE                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────────┐         ┌──────────────────┐                     │
│  │  APPLICATION     │         │   DISPATCHER     │                     │
│  │  LAYER           │────────▶│                  │                     │
│  │                  │         │  - apply()       │                     │
│  │  - Commands      │         │  - fetch_domain()│                     │
│  │  - Queries       │         │  - fetch()       │                     │
│  │  - Handlers      │         │                  │                     │
│  └──────────────────┘         └────────┬─────────┘                     │
│                                        │                                │
│                         ┌──────────────┴──────────────┐                │
│                         │                             │                │
│                         ▼                             ▼                │
│              ┌──────────────────┐          ┌──────────────────┐       │
│              │  COMMAND SIDE    │          │   QUERY SIDE     │       │
│              │  (WRITE)         │          │   (READ)         │       │
│              ├──────────────────┤          ├──────────────────┤       │
│              │                  │          │                  │       │
│              │  IOperation      │          │  IQuery          │       │
│              │  Persistence     │          │  Persistence     │       │
│              │                  │          │                  │       │
│              │  - Event Store   │          │  - Projections   │       │
│              │  - Snapshots     │          │  - DTOs          │       │
│              │  - Aggregates    │          │  - Specifications│       │
│              └──────────────────┘          └──────────────────┘       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Key Benefits

| Benefit | Description |
|---------|-------------|
| **Type Safety** | Strongly typed handlers per entity/DTO type |
| **Separation of Concerns** | Write and read models handled independently |
| **UnitOfWork Integration** | Automatic transaction management |
| **Specification Support** | Specification-based queries for complex filters |
| **Caching Layer** | Optional read-through caching with write invalidation |
| **Hook System** | Instrumentation for logging, metrics, tracing |

---

## Architecture

### Command vs Query Separation

```python
# Command side (write model)
class OrderRepository(
    IOperationPersistence[Order, str],
    IRetrievalPersistence[Order, str]
):
    """Event-sourced or state-stored aggregate persistence."""
    
    async def persist(self, entity: Order, uow: UnitOfWork) -> str:
        # Save aggregate state or events
        ...
    
    async def retrieve(self, ids: Sequence[str], uow: UnitOfWork) -> list[Order]:
        # Load aggregate by ID
        ...

# Query side (read model)
class OrderSummaryQuery(IQueryPersistence[OrderSummaryDTO, str]):
    """Projection-backed read model."""
    
    async def fetch(self, ids: Sequence[str], uow: UnitOfWork) -> list[OrderSummaryDTO]:
        # Load denormalized read model
        ...

class OrderSummarySpecQuery(IQuerySpecificationPersistence[OrderSummaryDTO]):
    """Specification-based read model queries."""
    
    async def fetch(self, criteria: ISpecification, uow: UnitOfWork) -> SearchResult[OrderSummaryDTO]:
        # Query by specification
        ...
```

---

## Core Components

### PersistenceRegistry

Registry for mapping entity/result types to their persistence handlers.

```python
from cqrs_ddd_advanced_core.persistence import PersistenceRegistry

registry = PersistenceRegistry()

# Register command-side handlers
registry.register_operation(
    entity_type=Order,
    handler_cls=OrderRepository,
    source="default",
    priority=0  # Higher priority = first in chain
)

registry.register_retrieval(
    entity_type=Order,
    handler_cls=OrderRepository,
    source="default"
)

# Register query-side handlers
registry.register_query(
    result_type=OrderSummaryDTO,
    handler_cls=OrderSummaryQuery,
    source="read_replica"
)

registry.register_query_spec(
    result_type=OrderSummaryDTO,
    handler_cls=OrderSummarySpecQuery,
    source="read_replica"
)
```

**Handler Types:**

| Registration | Interface | Purpose |
|--------------|-----------|---------|
| `register_operation()` | `IOperationPersistence` | Write operations (persist) |
| `register_retrieval()` | `IRetrievalPersistence` | Domain entity retrieval |
| `register_query()` | `IQueryPersistence` | ID-based read model queries |
| `register_query_spec()` | `IQuerySpecificationPersistence` | Specification-based queries |

### PersistenceDispatcher

Main dispatcher that routes operations to registered handlers.

```python
from cqrs_ddd_advanced_core.persistence import (
    PersistenceDispatcher,
    PersistenceRegistry,
)

# Setup
registry = PersistenceRegistry()
# ... register handlers ...

dispatcher = PersistenceDispatcher(
    uow_factories={
        "default": sqlalchemy_uow_factory,
        "read_replica": read_replica_uow_factory,
    },
    registry=registry,
    handler_factory=lambda cls: cls(),  # Optional custom instantiation
)
```

#### Methods

##### `apply()` - Persist Aggregates

```python
async def apply(
    entity: AggregateRoot[T_ID],
    uow: UnitOfWork | None = None,
    events: list[Any] | None = None,
) -> T_ID
```

Persist an aggregate (command-side write).

```python
# With explicit UnitOfWork
async with uow_factory() as uow:
    order = Order(id="order_123", customer_id="cust_456")
    order.add_event(OrderCreated(...))
    
    await dispatcher.apply(order, uow=uow)
    # UnitOfWork commits

# Without UnitOfWork (dispatcher creates one)
order = Order(id="order_123")
await dispatcher.apply(order)  # Auto-creates UoW from registered factory
```

##### `fetch_domain()` - Load Aggregates

```python
async def fetch_domain(
    entity_type: type[T_Entity],
    ids: Sequence[T_ID],
    uow: UnitOfWork | None = None,
) -> list[T_Entity]
```

Load domain entities by ID (command-side read).

```python
# Load single aggregate
orders = await dispatcher.fetch_domain(Order, ["order_123"], uow=uow)
order = orders[0] if orders else None

# Load multiple aggregates
orders = await dispatcher.fetch_domain(
    Order, 
    ["order_1", "order_2", "order_3"],
    uow=uow
)
```

##### `fetch()` - Query Read Models

```python
async def fetch(
    result_type: type[T_Result],
    criteria: T_Criteria[Any],
    uow: UnitOfWork | None = None,
) -> SearchResult[T_Result]
```

Fetch read models by ID or specification (query-side).

```python
from cqrs_ddd_specifications import SpecificationBuilder, QueryOptions

# ID-based query
result = await dispatcher.fetch(
    OrderSummaryDTO,
    ["order_1", "order_2"],
    uow=uow
)
orders = await result  # SearchResult -> list

# Specification-based query
spec = (
    SpecificationBuilder()
    .where("customer_id", "=", "cust_123")
    .where("status", "=", "submitted")
    .build()
)

options = QueryOptions().with_specification(spec).with_pagination(limit=10)

result = await dispatcher.fetch(OrderSummaryDTO, options, uow=uow)
orders = await result

# Stream results (requires UnitOfWork)
async for order in result.stream(batch_size=100):
    process_order(order)
```

### CachingPersistenceDispatcher

Decorator that adds caching to any `IPersistenceDispatcher`.

```python
from cqrs_ddd_advanced_core.persistence import CachingPersistenceDispatcher
from cqrs_ddd_core.ports.cache import ICacheService

# Wrap dispatcher with caching
cached_dispatcher = CachingPersistenceDispatcher(
    inner=dispatcher,
    cache_service=redis_cache_service,
    default_ttl=300,  # 5 minutes
)

# Use exactly like regular dispatcher
orders = await cached_dispatcher.fetch_domain(Order, ["order_1"], uow=uow)
```

**Caching Behavior:**

| Operation | Cache Strategy | Invalidates |
|-----------|---------------|-------------|
| `apply()` | Write-through | Yes (invalidates entity cache) |
| `fetch_domain()` | Read-through | No |
| `fetch()` (IDs) | Read-through | No |
| `fetch()` (Spec) | Not cached | N/A |

---

## Usage Examples

### Complete Example: E-Commerce Order System

#### 1. Domain Layer

```python
# domain/order.py
from cqrs_ddd_core.domain.aggregate import AggregateRoot
from cqrs_ddd_core.domain.events import DomainEvent

class OrderCreated(DomainEvent):
    order_id: str
    customer_id: str
    total: Decimal

class OrderSubmitted(DomainEvent):
    order_id: str
    submitted_at: datetime

class Order(AggregateRoot[str]):
    customer_id: str
    status: str = "pending"
    total: Decimal = Decimal("0.00")
    
    def apply_OrderCreated(self, event: OrderCreated):
        self.customer_id = event.customer_id
        self.total = event.total
        self.status = "created"
    
    def apply_OrderSubmitted(self, event: OrderSubmitted):
        self.status = "submitted"
```

#### 2. Infrastructure Layer

```python
# infrastructure/persistence.py
from cqrs_ddd_advanced_core.event_sourcing import EventSourcedRepository
from cqrs_ddd_advanced_core.projections import ProjectionBackedDualPersistence
from cqrs_ddd_persistence_sqlalchemy.advanced import (
    SQLAlchemyProjectionStore,
    SQLAlchemyProjectionDualPersistence,
)

# Command-side repository
class OrderRepository(EventSourcedRepository[Order, str]):
    """Event-sourced order repository."""
    pass

# Query-side persistence
class OrderSummaryQueryPersistence(
    SQLAlchemyProjectionDualPersistence[OrderSummaryDTO, str]
):
    collection = "order_summaries"
    
    def to_dto(self, doc: dict) -> OrderSummaryDTO:
        return OrderSummaryDTO(**doc)
```

#### 3. Registration

```python
# infrastructure/container.py
from cqrs_ddd_advanced_core.persistence import PersistenceRegistry, PersistenceDispatcher

def setup_dispatcher():
    registry = PersistenceRegistry()
    
    # Command-side
    registry.register_operation(Order, OrderRepository, source="default")
    registry.register_retrieval(Order, OrderRepository, source="default")
    
    # Query-side
    registry.register_query(OrderSummaryDTO, OrderSummaryQueryPersistence, source="default")
    registry.register_query_spec(OrderSummaryDTO, OrderSummaryQueryPersistence, source="default")
    
    return PersistenceDispatcher(
        uow_factories={"default": create_uow_factory()},
        registry=registry,
    )
```

#### 4. Application Layer

```python
# application/commands.py
class SubmitOrderCommand:
    order_id: str

async def handle_submit_order(
    command: SubmitOrderCommand,
    dispatcher: PersistenceDispatcher,
    uow: UnitOfWork,
) -> str:
    # Load aggregate
    orders = await dispatcher.fetch_domain(Order, [command.order_id], uow=uow)
    if not orders:
        raise OrderNotFound(command.order_id)
    
    order = orders[0]
    
    # Business logic
    event = OrderSubmitted(
        aggregate_id=order.id,
        order_id=order.id,
        submitted_at=datetime.now(timezone.utc),
    )
    order.add_event(event)
    
    # Persist
    await dispatcher.apply(order, uow=uow)
    
    return order.id

# application/queries.py
class GetCustomerOrdersQuery:
    customer_id: str
    limit: int = 10

async def handle_get_customer_orders(
    query: GetCustomerOrdersQuery,
    dispatcher: PersistenceDispatcher,
    uow: UnitOfWork,
) -> list[OrderSummaryDTO]:
    from cqrs_ddd_specifications import SpecificationBuilder, QueryOptions
    
    # Build specification
    spec = (
        SpecificationBuilder()
        .where("customer_id", "=", query.customer_id)
        .build()
    )
    
    # Build query options
    options = (
        QueryOptions()
        .with_specification(spec)
        .with_ordering("-created_at")
        .with_pagination(limit=query.limit)
    )
    
    # Execute query
    result = await dispatcher.fetch(OrderSummaryDTO, options, uow=uow)
    return await result
```

---

## Integration Patterns

### Pattern 1: Event Sourcing + Projections

```
┌─────────────────────────────────────────────────────────────────────────┐
│                EVENT SOURCING + PROJECTIONS PATTERN                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Command Handler                      Projection Worker                 │
│  ┌──────────────────┐                ┌──────────────────┐              │
│  │                  │                │                  │              │
│  │  1. Load Order   │                │  5. Read Events  │              │
│  │  2. Modify       │                │  6. Update Proj  │              │
│  │  3. Save Events  │───────────────▶│  7. Save Proj    │              │
│  │  4. Commit       │                │                  │              │
│  │                  │                │                  │              │
│  └────────┬─────────┘                └────────┬─────────┘              │
│           │                                   │                         │
│           │                                   │                         │
│           ▼                                   ▼                         │
│  ┌──────────────────┐                ┌──────────────────┐              │
│  │  EVENT STORE     │                │  PROJECTION      │              │
│  │  (Write Side)    │                │  STORE           │              │
│  │                  │                │  (Read Side)     │              │
│  └──────────────────┘                └──────────────────┘              │
│                                                                         │
│  Dispatcher uses:                     Dispatcher uses:                 │
│  - EventSourcedRepository             - ProjectionBackedPersistence    │
│  - IOperationPersistence              - IQueryPersistence              │
│  - IRetrievalPersistence                                               │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Key Points:**
- Command side: `EventSourcedRepository` persists to event store
- Query side: `ProjectionBackedPersistence` reads from projection tables
- Projections updated asynchronously by `ProjectionWorker`
- Same `PersistenceDispatcher` handles both sides

### Pattern 2: State-Stored Aggregates

```python
# For non-event-sourced aggregates
class CustomerRepository(
    IOperationPersistence[Customer, str],
    IRetrievalPersistence[Customer, str]
):
    async def persist(self, entity: Customer, uow: UnitOfWork) -> str:
        # Direct state persistence (no events)
        session = uow.session
        async with session.begin():
            await session.merge(entity)
        return entity.id
    
    async def retrieve(self, ids: Sequence[str], uow: UnitOfWork) -> list[Customer]:
        session = uow.session
        result = await session.execute(
            select(CustomerModel).where(CustomerModel.id.in_(ids))
        )
        return [self._to_entity(row) for row in result.scalars().all()]
```

### Pattern 3: Multi-Source (Database per Bounded Context)

```python
registry = PersistenceRegistry()

# Orders bounded context
registry.register_operation(Order, OrderRepository, source="orders_db")
registry.register_retrieval(Order, OrderRepository, source="orders_db")

# Invoicing bounded context
registry.register_operation(Invoice, InvoiceRepository, source="invoicing_db")
registry.register_retrieval(Invoice, InvoiceRepository, source="invoicing_db")

dispatcher = PersistenceDispatcher(
    uow_factories={
        "orders_db": orders_uow_factory,
        "invoicing_db": invoicing_uow_factory,
    },
    registry=registry,
)
```

---

## Best Practices

### 1. Use UnitOfWork Explicitly

```python
# ✅ GOOD: Explicit UoW management
async def handle_command(command, dispatcher: PersistenceDispatcher):
    async with uow_factory() as uow:
        order = await load_order(command.order_id, uow)
        order.submit()
        await dispatcher.apply(order, uow=uow)
        # UoW commits

# ❌ BAD: Implicit UoW (harder to test, less control)
async def handle_command(command, dispatcher: PersistenceDispatcher):
    order = await load_order(command.order_id, None)
    order.submit()
    await dispatcher.apply(order)  # Creates its own UoW
```

### 2. Separate Command and Query Handlers

```python
# ✅ GOOD: Separate handlers
class SubmitOrderHandler:  # Command handler
    async def handle(self, command: SubmitOrder, uow: UnitOfWork):
        # Use dispatcher.apply() and fetch_domain()
        ...

class GetOrderSummaryHandler:  # Query handler
    async def handle(self, query: GetOrderSummary, uow: UnitOfWork):
        # Use dispatcher.fetch()
        ...

# ❌ BAD: Mixing command and query logic
class OrderHandler:
    async def handle(self, request, uow: UnitOfWork):
        if request.is_command:
            # Modify state
            ...
        else:
            # Query state
            ...
```

### 3. Use Specifications for Complex Queries

```python
# ✅ GOOD: Specification-based query
from cqrs_ddd_specifications import SpecificationBuilder, QueryOptions

spec = (
    SpecificationBuilder()
    .where("customer_id", "=", customer_id)
    .where("status", "=", "submitted")
    .where("total", ">=", min_total)
    .build()
)

options = QueryOptions().with_specification(spec).with_pagination(limit=10)
result = await dispatcher.fetch(OrderSummaryDTO, options, uow=uow)

# ❌ BAD: Manual query building
# (Violates CQRS separation, ties query logic to handler)
class OrderSummaryQuery:
    async def fetch_by_customer_and_status(self, customer_id, status):
        # Manual SQL/query building in handler
        ...
```

### 4. Register All Required Handlers

```python
# ✅ GOOD: Complete registration
registry.register_operation(Order, OrderRepository, source="default")
registry.register_retrieval(Order, OrderRepository, source="default")
registry.register_query(OrderSummaryDTO, OrderSummaryQueryPersistence, source="default")
registry.register_query_spec(OrderSummaryDTO, OrderSummarySpecPersistence, source="default")

# ❌ BAD: Missing handlers (will fail at runtime)
registry.register_operation(Order, OrderRepository)
# Missing: retrieval, query, query_spec
# Will raise HandlerNotRegisteredError when used
```

### 5. Leverage Caching for Read Models

```python
# ✅ GOOD: Cache read models
from cqrs_ddd_advanced_core.persistence import CachingPersistenceDispatcher

cached_dispatcher = CachingPersistenceDispatcher(
    inner=dispatcher,
    cache_service=redis_cache,
    default_ttl=300,
)

# Read-through cache
orders = await cached_dispatcher.fetch(OrderSummaryDTO, ["order_1"], uow=uow)

# Cache invalidation on write
await cached_dispatcher.apply(order, uow=uow)  # Invalidates order cache
```

---

## Summary

| Component | Purpose | Key Features |
|-----------|---------|--------------|
| `PersistenceRegistry` | Handler registration | Type-safe mappings, priority support |
| `PersistenceDispatcher` | Operation routing | UoW management, specification support |
| `CachingPersistenceDispatcher` | Read caching | Read-through cache, write invalidation |
| `IOperationPersistence` | Write operations | Persist aggregates |
| `IRetrievalPersistence` | Domain reads | Load aggregates by ID |
| `IQueryPersistence` | Read model queries | ID-based DTO retrieval |
| `IQuerySpecificationPersistence` | Complex queries | Specification-based filtering |

The Persistence Dispatcher provides a clean separation between command-side and query-side operations while maintaining type safety and transactional integrity.
