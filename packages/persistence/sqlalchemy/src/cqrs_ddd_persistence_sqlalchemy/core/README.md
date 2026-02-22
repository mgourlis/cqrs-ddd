# SQLAlchemy Core Persistence

**Production-ready repository and event sourcing implementations for CQRS/DDD applications.**

---

## Overview

The `core` package provides the **foundational persistence layer** for SQLAlchemy-based CQRS/DDD applications, implementing the repository pattern, unit of work, event store, and outbox pattern.

**Key Features:**
- ✅ **Repository Pattern** - Generic `SQLAlchemyRepository` with full CRUD + specification support
- ✅ **Unit of Work** - Transaction management with automatic commit/rollback
- ✅ **Event Store** - Event sourcing with sequence-based positioning
- ✅ **Outbox Pattern** - Transactional outbox for reliable event publishing
- ✅ **Model Mapping** - Automatic domain entity ↔ SQLAlchemy model conversion
- ✅ **Optimistic Concurrency** - Built-in version checking

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    APPLICATION LAYER                         │
│                                                              │
│  Command Handlers / Application Services                     │
│       ↓                                                      │
│  async with uow:                                             │
│      await repo.add(entity, uow=uow)                        │
│      await uow.commit()                                      │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    CORE PERSISTENCE                          │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  SQLAlchemyRepository                                 │  │
│  │  - add(), get(), delete(), list_all()               │  │
│  │  - search(spec, options) → SearchResult             │  │
│  │  - to_model() / from_model()                         │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  SQLAlchemyUnitOfWork                                 │  │
│  │  - Transaction management                             │  │
│  │  - Automatic commit/rollback                          │  │
│  │  - Caller-managed or self-managed sessions            │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  SQLAlchemyEventStore                                 │  │
│  │  - append(), append_batch()                           │  │
│  │  - get_events(), get_events_after()                  │  │
│  │  - Sequence-based positioning                         │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  SQLAlchemyOutboxStorage                              │  │
│  │  - save_messages() (same transaction)                │  │
│  │  - get_pending(), mark_published()                    │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    DATABASE (PostgreSQL/SQLite)              │
│                                                              │
│  Tables: aggregates, events, outbox                         │
└─────────────────────────────────────────────────────────────┘
```

---

## Components

### 1. `SQLAlchemyRepository` - Generic Repository

**Purpose:** Implements `IRepository[T, ID]` for any aggregate root.

**Key Methods:**
- `add(entity, uow)` - Insert or update (with OCC)
- `get(entity_id, uow)` - Retrieve by ID
- `delete(entity_id, uow)` - Delete by ID
- `list_all(entity_ids, uow)` - List all or by IDs
- `search(spec, options, uow)` - Search by specification

**Usage:**
```python
from cqrs_ddd_persistence_sqlalchemy.core import SQLAlchemyRepository
from cqrs_ddd_persistence_sqlalchemy.core.uow import SQLAlchemyUnitOfWork

# Domain model
class Order(AggregateRoot):
    id: str
    customer_id: str
    total: float
    status: str

# SQLAlchemy model
class OrderModel(Base):
    __tablename__ = "orders"
    
    id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_id: Mapped[str] = mapped_column(String, ForeignKey("customers.id"))
    total: Mapped[float] = mapped_column(Numeric(10, 2))
    status: Mapped[str] = mapped_column(String(50))

# Repository setup
order_repo = SQLAlchemyRepository(
    entity_cls=Order,
    db_model_cls=OrderModel,
)

# Usage with Unit of Work
async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow:
    # Create new order
    order = Order(
        id="order-123",
        customer_id="customer-456",
        total=99.99,
        status="pending",
    )
    await order_repo.add(order, uow=uow)
    await uow.commit()

# Retrieve order
async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow:
    order = await order_repo.get("order-123", uow=uow)
    assert order.status == "pending"
```

**Search with Specifications:**
```python
from cqrs_ddd_specifications import SpecificationBuilder, build_default_registry
from cqrs_ddd_persistence_sqlalchemy.core import SQLAlchemyRepository

# Build specification
registry = build_default_registry()
builder = SpecificationBuilder()
spec = builder.where("status", "eq", "pending").build()

# Search with QueryOptions
options = (
    QueryOptions()
    .with_specification(spec, registry=registry)
    .with_ordering("-created_at")
    .with_pagination(limit=20, offset=0)
)

result = await order_repo.search(options=options, uow=uow)
orders = await result  # List[Order]

# Or stream for large datasets
async for order in (await order_repo.search(options=options, uow=uow)).stream():
    process(order)
```

**Model Mapping:**
```python
# Automatic conversion
model = repo.to_model(entity)  # Order → OrderModel
entity = repo.from_model(model)  # OrderModel → Order

# Custom mapping (override in subclass)
class OrderRepository(SQLAlchemyRepository[Order, str]):
    def to_model(self, entity: Order) -> OrderModel:
        model = super().to_model(entity)
        # Custom mapping logic
        model.items = [item.model_dump() for item in entity.items]
        return model
```

---

### 2. `SQLAlchemyUnitOfWork` - Transaction Management

**Purpose:** Manages database transactions with automatic commit/rollback.

**Two Usage Patterns:**

#### Pattern 1: Caller-Managed Sessions (DI Container)

```python
from sqlalchemy.ext.asyncio import AsyncSession
from dependency_injector import containers, providers

class Container(containers.DeclarativeContainer):
    session_factory = providers.Factory(
        sessionmaker(engine, class_=AsyncSession)
    )
    
    uow = providers.Factory(
        SQLAlchemyUnitOfWork,
        session=session_factory,  # DI container manages session lifecycle
    )

# Usage
async with Container.uow() as uow:
    await order_repo.add(order, uow=uow)
    await uow.commit()  # Commits transaction, keeps session open
```

#### Pattern 2: Self-Managed Sessions (Factory)

```python
from sqlalchemy.ext.asyncio import async_sessionmaker

session_factory = async_sessionmaker(engine, expire_on_commit=False)

# UoW creates and closes session
async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow:
    await order_repo.add(order, uow=uow)
    await uow.commit()  # Commits and closes session
```

**Error Handling:**
```python
async with SQLAlchemyUnitOfWork(session_factory) as uow:
    try:
        await order_repo.add(order, uow=uow)
        await payment_repo.add(payment, uow=uow)
        await uow.commit()  # Both succeed or both fail
    except IntegrityError as e:
        # Automatic rollback on exception
        # Session closed if self-managed
        logger.error(f"Transaction failed: {e}")
        raise
```

**Hooks:**
```python
from cqrs_ddd_core.ports.unit_of_work import UnitOfWorkHooks

class LoggingHooks(UnitOfWorkHooks):
    async def pre_commit(self, uow: UnitOfWork) -> None:
        logger.info("About to commit transaction")
    
    async def post_commit(self, uow: UnitOfWork) -> None:
        logger.info("Transaction committed successfully")
    
    async def pre_rollback(self, uow: UnitOfWork) -> None:
        logger.warning("Rolling back transaction")
    
    async def post_rollback(self, uow: UnitOfWork) -> None:
        logger.info("Transaction rolled back")

# Usage
async with SQLAlchemyUnitOfWork(session_factory, hooks=LoggingHooks()) as uow:
    await order_repo.add(order, uow=uow)
    await uow.commit()  # Hooks fire automatically
```

---

### 3. `SQLAlchemyEventStore` - Event Sourcing

**Purpose:** Stores domain events with sequence-based positioning.

**Features:**
- Atomic position assignment via database sequences
- Cursor-based pagination for large event histories
- Batch append for performance
- Streaming support for memory-efficient processing

**Usage:**
```python
from cqrs_ddd_persistence_sqlalchemy.core import SQLAlchemyEventStore
from cqrs_ddd_core.ports.event_store import StoredEvent

event_store = SQLAlchemyEventStore(session)

# Append single event
event = StoredEvent(
    event_id="evt-123",
    event_type="OrderCreated",
    aggregate_id="order-456",
    aggregate_type="Order",
    version=1,
    payload={"customer_id": "cust-789", "total": 99.99},
    metadata={"user_id": "user-123"},
    occurred_at=datetime.now(timezone.utc),
)
await event_store.append(event)

# Append batch (atomic)
events = [event1, event2, event3]
await event_store.append_batch(events)

# Get events for aggregate
events = await event_store.get_events("order-456")

# Get events after version (for reconstitution)
events = await event_store.get_events("order-456", after_version=5)

# Cursor-based pagination
position = 0
while True:
    batch = await event_store.get_events_after(position, limit=1000)
    if not batch:
        break
    for event in batch:
        await process_event(event)
        position = event.position

# Streaming (memory-efficient)
async for event in await event_store.get_events_from_position(0):
    await process_event(event)
```

**Event Reconstitution:**
```python
async def reconstitute_order(order_id: str, event_store: SQLAlchemyEventStore) -> Order:
    """Rebuild order from event history."""
    # Get all events for aggregate
    events = await event_store.get_events(order_id)
    
    # Start with empty order
    order = Order(id=order_id)
    
    # Apply each event
    for event in events:
        if event.event_type == "OrderCreated":
            order.apply(OrderCreated(**event.payload))
        elif event.event_type == "OrderShipped":
            order.apply(OrderShipped(**event.payload))
        # ... more event handlers
    
    return order
```

---

### 4. `SQLAlchemyOutboxStorage` - Transactional Outbox

**Purpose:** Ensures reliable event publishing via transactional outbox pattern.

**How It Works:**
1. Domain events saved to `outbox` table in same transaction as aggregate
2. Background worker polls `outbox` table for pending messages
3. Worker publishes to message broker (Kafka, RabbitMQ, etc.)
4. Marks message as published on success

**Usage:**
```python
from cqrs_ddd_persistence_sqlalchemy.core import SQLAlchemyOutboxStorage

outbox = SQLAlchemyOutboxStorage(session)

# Save events in same transaction as aggregate
async with SQLAlchemyUnitOfWork(session_factory) as uow:
    # Modify aggregate
    order.ship()
    await order_repo.add(order, uow=uow)
    
    # Save domain events to outbox
    domain_events = order.pull_domain_events()
    outbox_messages = [
        OutboxMessage(
            message_id=event.event_id,
            event_type=event.event_type,
            payload=event.model_dump(),
            created_at=datetime.now(timezone.utc),
        )
        for event in domain_events
    ]
    await outbox.save_messages(outbox_messages, uow=uow)
    
    # Both aggregate and outbox committed atomically
    await uow.commit()

# Background worker (separate process)
async def outbox_publisher():
    while True:
        # Get pending messages
        messages = await outbox.get_pending(limit=100)
        
        for msg in messages:
            try:
                # Publish to message broker
                await kafka_producer.send(
                    topic=f"domain.{msg.event_type}",
                    key=msg.message_id,
                    value=msg.payload,
                )
                
                # Mark as published
                await outbox.mark_published([msg.message_id])
                
            except Exception as e:
                # Mark as failed (will be retried)
                await outbox.mark_failed(msg.message_id, str(e))
        
        await asyncio.sleep(1)
```

**Outbox Model:**
```python
from cqrs_ddd_persistence_sqlalchemy.core.models import OutboxMessage, OutboxStatus

class OutboxMessage(Base):
    __tablename__ = "outbox"
    
    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(200))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[OutboxStatus] = mapped_column(default=OutboxStatus.PENDING)
    retry_count: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
```

---

### 5. `ModelMapper` - Entity/Model Conversion

**Purpose:** Automates bidirectional conversion between domain entities and SQLAlchemy models.

**Features:**
- Automatic field mapping by name
- Relationship handling with configurable depth
- Custom field transformers
- Support for nested objects and collections

**Usage:**
```python
from cqrs_ddd_persistence_sqlalchemy.core.model_mapper import ModelMapper

# Domain entity
class Customer(AggregateRoot):
    id: str
    name: str
    email: str
    addresses: list[Address]  # Nested objects

# SQLAlchemy model
class CustomerModel(Base):
    __tablename__ = "customers"
    
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(200))
    addresses: Mapped[list] = mapped_column(JSON)  # Stored as JSON

# Create mapper
mapper = ModelMapper(
    entity_cls=Customer,
    model_cls=CustomerModel,
    relationship_depth=1,  # Load 1 level of relationships
)

# Entity → Model
customer = Customer(id="c1", name="John", email="john@example.com")
model = mapper.to_model(customer)
# model.id = "c1", model.name = "John", etc.

# Model → Entity
model = CustomerModel(id="c2", name="Jane", email="jane@example.com")
entity = mapper.from_model(model)
# entity.id = "c2", entity.name = "Jane", etc.
```

**Custom Field Mapping:**
```python
class OrderRepository(SQLAlchemyRepository[Order, str]):
    def to_model(self, entity: Order) -> OrderModel:
        """Custom mapping with computed fields."""
        model = super().to_model(entity)
        # Add computed fields
        model.total_items = len(entity.items)
        model.discounted_total = entity.total * 0.9  # 10% discount
        return model
    
    def from_model(self, model: OrderModel) -> Order:
        """Custom mapping with derived fields."""
        entity = super().from_model(model)
        # Reconstruct derived fields
        entity._total_items = model.total_items
        return entity
```

---

## Integration Patterns

### Pattern 1: Simple CRUD Application

```python
from fastapi import FastAPI, Depends
from sqlalchemy.ext.asyncio import AsyncSession

app = FastAPI()

# Dependency
async def get_uow() -> SQLAlchemyUnitOfWork:
    async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow:
        yield uow

@app.post("/orders")
async def create_order(
    order_data: CreateOrderRequest,
    uow: SQLAlchemyUnitOfWork = Depends(get_uow),
):
    order = Order(**order_data.dict())
    await order_repo.add(order, uow=uow)
    await uow.commit()
    return {"id": order.id}
```

### Pattern 2: Event Sourcing with Outbox

```python
async def create_order_handler(cmd: CreateOrderCommand):
    """Command handler with event sourcing and outbox."""
    async with SQLAlchemyUnitOfWork(session_factory) as uow:
        # Create order
        order = Order.create(cmd.customer_id, cmd.items)
        
        # Save order
        await order_repo.add(order, uow=uow)
        
        # Save events to outbox
        events = order.pull_domain_events()
        await outbox.save_messages([
            OutboxMessage(
                message_id=e.event_id,
                event_type=e.event_type,
                payload=e.model_dump(),
                created_at=datetime.now(timezone.utc),
            )
            for e in events
        ], uow=uow)
        
        # Atomic commit
        await uow.commit()
        
        # Events will be published by background worker
```

### Pattern 3: CQRS with Projections

```python
async def get_order_summary(order_id: str):
    """Query handler reading from projection."""
    async with SQLAlchemyUnitOfWork(session_factory) as uow:
        # Read from read model (projection)
        summary = await projection_repo.get(order_id, uow=uow)
        return summary

async def ship_order_handler(cmd: ShipOrderCommand):
    """Command handler updating write model and emitting events."""
    async with SQLAlchemyUnitOfWork(session_factory) as uow:
        # Load from write model
        order = await order_repo.get(cmd.order_id, uow=uow)
        
        # Business logic
        order.ship()
        
        # Save to write model
        await order_repo.add(order, uow=uow)
        
        # Events will update projections asynchronously
        await uow.commit()
```

---

## Performance Considerations

### 1. Batch Operations

```python
# ❌ SLOW: Individual inserts
for order in orders:
    await repo.add(order, uow=uow)
    await uow.commit()

# ✅ FAST: Batch insert
async with SQLAlchemyUnitOfWork(session_factory) as uow:
    for order in orders:
        await repo.add(order, uow=uow)
    await uow.commit()  # Single transaction
```

### 2. Streaming Large Datasets

```python
# ❌ SLOW: Load all into memory
orders = await (await repo.search(options=options, uow=uow))

# ✅ FAST: Stream results
async for order in (await repo.search(options=options, uow=uow)).stream(batch_size=100):
    process(order)
```

### 3. Event Store Pagination

```python
# ❌ SLOW: Load all events
events = await event_store.get_all()  # O(n) memory

# ✅ FAST: Paginated loading
position = 0
while True:
    events = await event_store.get_events_after(position, limit=1000)
    if not events:
        break
    for event in events:
        process(event)
        position = event.position
```

---

## Error Handling

### Optimistic Concurrency

```python
from cqrs_ddd_persistence_sqlalchemy.exceptions import OptimisticConcurrencyError

try:
    await order_repo.add(order, uow=uow)
    await uow.commit()
except OptimisticConcurrencyError as e:
    # Handle concurrent modification
    logger.warning(f"Concurrent update detected: {e}")
    # Reload and retry
    order = await order_repo.get(order.id, uow=uow)
    # ... reapply changes
```

### Constraint Violations

```python
from sqlalchemy.exc import IntegrityError

try:
    await customer_repo.add(customer, uow=uow)
    await uow.commit()
except IntegrityError as e:
    # Handle duplicate key, foreign key violation, etc.
    if "unique constraint" in str(e):
        raise DuplicateCustomerError(f"Customer {customer.email} already exists")
    raise
```

---

## Dependencies

- `sqlalchemy>=2.0` - ORM framework
- `asyncpg` / `aiosqlite` - Async database drivers
- `cqrs-ddd-core` - Domain primitives and ports
- `cqrs-ddd-specifications` - Specification pattern

---

## Testing

```python
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

@pytest.fixture
async def engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest.fixture
async def uow(engine):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow:
        yield uow

async def test_repository_add(uow: SQLAlchemyUnitOfWork):
    """Test adding entity to repository."""
    order = Order(id="order-1", customer_id="cust-1", total=99.99)
    await order_repo.add(order, uow=uow)
    await uow.commit()
    
    # Verify
    loaded = await order_repo.get("order-1", uow=uow)
    assert loaded.id == "order-1"
    assert loaded.total == 99.99
```

---

## Summary

| Component | Purpose | Key Methods |
|-----------|---------|-------------|
| `SQLAlchemyRepository` | Generic CRUD + search | `add`, `get`, `delete`, `search` |
| `SQLAlchemyUnitOfWork` | Transaction management | `commit`, `rollback` |
| `SQLAlchemyEventStore` | Event sourcing | `append`, `get_events`, `get_events_after` |
| `SQLAlchemyOutboxStorage` | Reliable event publishing | `save_messages`, `get_pending`, `mark_published` |
| `ModelMapper` | Entity ↔ Model conversion | `to_model`, `from_model` |

**Total Lines:** ~1200  
**Dependencies:** SQLAlchemy 2.0+, cqrs-ddd-core, cqrs-ddd-specifications  
**Python Version:** 3.11+
