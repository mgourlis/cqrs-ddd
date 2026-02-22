# MongoDB Core Persistence

**Production-ready repository and event sourcing implementations for CQRS/DDD applications using MongoDB.**

---

## Overview

The `core` package provides the **foundational persistence layer** for MongoDB-based CQRS/DDD applications, implementing the repository pattern, unit of work, event store, and outbox pattern with native MongoDB features.

**Key Features:**
- ✅ **Repository Pattern** - Generic `MongoRepository` with full CRUD + specification support
- ✅ **Unit of Work** - Transaction management with MongoDB 4.0+ replica sets
- ✅ **Event Store** - Event sourcing with atomic counter-based positioning
- ✅ **Outbox Pattern** - Transactional outbox for reliable event publishing
- ✅ **Model Mapping** - Automatic domain entity ↔ MongoDB document conversion
- ✅ **Flexible Sessions** - Support for both client-managed and self-managed sessions

**MongoDB Version:** 4.0+ (transactions require replica set)

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
│  │  MongoRepository                                      │  │
│  │  - add(), get(), delete(), list_all()               │  │
│  │  - search(spec, options) → SearchResult             │  │
│  │  - to_doc() / from_doc()                             │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  MongoUnitOfWork                                      │  │
│  │  - Transaction management (replica set)               │  │
│  │  - Automatic commit/abort                             │  │
│  │  - Client-managed or self-managed sessions            │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  MongoEventStore                                      │  │
│  │  - append(), append_batch()                           │  │
│  │  - get_events(), get_events_after()                  │  │
│  │  - Atomic counter-based positioning                   │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  MongoOutboxStorage                                   │  │
│  │  - save_messages() (same transaction)                │  │
│  │  - get_pending(), mark_published()                    │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    MONGODB DATABASE                          │
│                                                              │
│  Collections: aggregates, domain_events, outbox, counters   │
└─────────────────────────────────────────────────────────────┘
```

---

## Components

### 1. `MongoRepository` - Generic Repository

**Purpose:** Implements `IRepository[T, ID]` for any aggregate root.

**Key Methods:**
- `add(entity, uow)` - Insert or replace document (upsert)
- `get(entity_id, uow)` - Retrieve by ID
- `delete(entity_id, uow)` - Delete by ID
- `list_all(entity_ids, uow)` - List all or by IDs
- `search(spec, options, uow)` - Search by specification

**Usage:**
```python
from cqrs_ddd_persistence_mongo.core import MongoRepository
from cqrs_ddd_persistence_mongo.connection import MongoConnectionManager
from cqrs_ddd_persistence_mongo.core.uow import MongoUnitOfWork

# Domain model
class Order(AggregateRoot):
    id: str
    customer_id: str
    total: float
    status: str

# Setup connection
connection = MongoConnectionManager(
    url="mongodb://localhost:27017",
    database="myapp",
)
await connection.connect()

# Repository setup
order_repo = MongoRepository(
    connection=connection,
    collection="orders",
    model_cls=Order,
    id_field="id",  # Maps to _id in MongoDB
)

# Usage with Unit of Work
async with MongoUnitOfWork(connection=connection) as uow:
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
async with MongoUnitOfWork(connection=connection) as uow:
    order = await order_repo.get("order-123", uow=uow)
    assert order.status == "pending"
```

**Search with Specifications:**
```python
from cqrs_ddd_specifications import SpecificationBuilder, build_default_registry
from cqrs_ddd_persistence_mongo.core import MongoRepository

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

**Document Mapping:**
```python
# Automatic conversion
doc = repo._mapper.to_doc(entity)  # Order → MongoDB document
entity = repo._mapper.from_doc(doc)  # MongoDB document → Order

# Example document structure
{
    "_id": "order-123",
    "customer_id": "customer-456",
    "total": 99.99,
    "status": "pending",
    "_version": 1,
    "created_at": ISODate("2024-01-01T00:00:00Z"),
}
```

**MongoDB-Specific Features:**

```python
# Nested field queries (dot notation)
spec = builder.where("address.city", "eq", "New York").build()
# MongoDB query: {"address.city": "New York"}

# Array queries
spec = builder.where("tags", "in", ["premium", "featured"]).build()
# MongoDB query: {"tags": {"$in": ["premium", "featured"]}}

# JSON queries
spec = builder.where("metadata.customer_tier", "eq", "gold").build()
# MongoDB query: {"metadata.customer_tier": "gold"}
```

---

### 2. `MongoUnitOfWork` - Transaction Management

**Purpose:** Manages MongoDB transactions with automatic commit/abort.

**Important:** MongoDB 4.0+ transactions **require a replica set** (not standalone).

**Two Usage Patterns:**

#### Pattern 1: Client-Managed Sessions

```python
from motor.motor_asyncio import AsyncIOMotorClient

client = AsyncIOMotorClient("mongodb://localhost:27017/?replicaSet=rs0")
session = await client.start_session()

async with MongoUnitOfWork(session=session) as uow:
    await order_repo.add(order, uow=uow)
    await uow.commit()  # Commits transaction, keeps session open

await session.end_session()
```

#### Pattern 2: Self-Managed Sessions (Recommended)

```python
from cqrs_ddd_persistence_mongo.connection import MongoConnectionManager

connection = MongoConnectionManager(
    url="mongodb://localhost:27017/?replicaSet=rs0",
    database="myapp",
)
await connection.connect()

# UoW creates and closes session
async with MongoUnitOfWork(connection=connection) as uow:
    await order_repo.add(order, uow=uow)
    await uow.commit()  # Commits and closes session
```

**Transaction Requirements:**

```python
# ✅ GOOD: Replica set (supports transactions)
connection = MongoConnectionManager(
    url="mongodb://localhost:27017/?replicaSet=rs0",
    database="myapp",
)

# ❌ BAD: Standalone (no transactions, raises error)
connection = MongoConnectionManager(
    url="mongodb://localhost:27017",  # No replicaSet
    database="myapp",
)
async with MongoUnitOfWork(connection=connection) as uow:  # RuntimeError!
    ...

# ⚠️ TESTING ONLY: Disable replica set check
async with MongoUnitOfWork(
    connection=connection,
    require_replica_set=False,  # Skips check, but no transactions
) as uow:
    # Operations succeed but aren't transactional
    ...
```

**Error Handling:**
```python
async with MongoUnitOfWork(connection=connection) as uow:
    try:
        await order_repo.add(order, uow=uow)
        await payment_repo.add(payment, uow=uow)
        await uow.commit()  # Both succeed or both fail
    except Exception as e:
        # Automatic abort on exception
        # Session closed
        logger.error(f"Transaction failed: {e}")
        raise
```

**Standalone Mode (Development):**

```python
# For local development without replica set
connection = MongoConnectionManager(
    url="mongodb://localhost:27017",
    database="myapp_dev",
)

# Repository operations work without transactions
order = await order_repo.get("order-123", uow=None)  # No UoW needed
await order_repo.add(order)  # Individual operations succeed
```

---

### 3. `MongoEventStore` - Event Sourcing

**Purpose:** Stores domain events with atomic counter-based positioning.

**Features:**
- Atomic position assignment via counters collection
- Cursor-based pagination for large event histories
- Batch append for performance
- Streaming support for memory-efficient processing
- No race conditions (atomic find_one_and_update)

**Usage:**
```python
from cqrs_ddd_persistence_mongo.core import MongoEventStore
from cqrs_ddd_core.ports.event_store import StoredEvent

event_store = MongoEventStore(
    connection=connection,
    database="myapp",
)

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

**Atomic Position Assignment:**

```python
# MongoDB document structure
{
    "_id": "evt-123",
    "event_type": "OrderCreated",
    "aggregate_id": "order-456",
    "aggregate_type": "Order",
    "version": 1,
    "payload": {...},
    "metadata": {...},
    "occurred_at": ISODate("2024-01-01T00:00:00Z"),
    "position": 1001,  # Auto-incremented atomically
}

// Counter collection
{
    "_id": "domain_events_position",
    "seq": 1001
}
```

**Position Generation:**
```python
async def _next_position(self) -> int:
    """
    Atomically increment and return next position.
    
    Uses find_one_and_update with upsert:
    - Atomic: No race conditions
    - No gaps: Sequential even with failures
    - Fast: Single round-trip
    """
    result = await self._counters_collection().find_one_and_update(
        {"_id": self.POSITION_COUNTER},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return result["seq"]
```

**Event Reconstitution:**
```python
async def reconstitute_order(order_id: str, event_store: MongoEventStore) -> Order:
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

### 4. `MongoOutboxStorage` - Transactional Outbox

**Purpose:** Ensures reliable event publishing via transactional outbox pattern.

**How It Works:**
1. Domain events saved to `outbox` collection in same transaction as aggregate
2. Background worker polls `outbox` collection for pending messages
3. Worker publishes to message broker (Kafka, RabbitMQ, etc.)
4. Marks message as published on success

**Usage:**
```python
from cqrs_ddd_persistence_mongo.core import MongoOutboxStorage

outbox = MongoOutboxStorage(
    connection=connection,
    database="myapp",
)

# Save events in same transaction as aggregate
async with MongoUnitOfWork(connection=connection) as uow:
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

**Outbox Document Structure:**
```python
{
    "_id": "msg-123",
    "event_type": "OrderShipped",
    "payload": {
        "order_id": "order-456",
        "shipped_at": "2024-01-01T00:00:00Z",
    },
    "status": "pending",  # pending, published, failed
    "retry_count": 0,
    "error": None,
    "created_at": ISODate("2024-01-01T00:00:00Z"),
    "published_at": None,
}
```

---

### 5. `MongoDBModelMapper` - Entity/Document Conversion

**Purpose:** Automates bidirectional conversion between domain entities and MongoDB documents.

**Features:**
- Automatic field mapping by name
- `_id` ↔ `id` field mapping
- Nested document handling
- Type conversion (datetime, ObjectId, etc.)

**Usage:**
```python
from cqrs_ddd_persistence_mongo.core.model_mapper import MongoDBModelMapper

# Domain entity
class Customer(AggregateRoot):
    id: str
    name: str
    email: str
    addresses: list[Address]  # Nested objects

# Create mapper
mapper = MongoDBModelMapper(
    model_cls=Customer,
    id_field="id",  # Maps to MongoDB _id
)

# Entity → Document
customer = Customer(id="c1", name="John", email="john@example.com")
doc = mapper.to_doc(customer)
# doc = {"_id": "c1", "name": "John", "email": "john@example.com", ...}

# Document → Entity
doc = {"_id": "c2", "name": "Jane", "email": "jane@example.com"}
entity = mapper.from_doc(doc)
# entity.id = "c2", entity.name = "Jane", etc.
```

**Custom Field Mapping:**
```python
class OrderRepository(MongoRepository[Order, str]):
    def _mapper_to_doc(self, entity: Order) -> dict[str, Any]:
        """Custom mapping with computed fields."""
        doc = self._mapper.to_doc(entity)
        # Add computed fields
        doc["total_items"] = len(entity.items)
        doc["discounted_total"] = entity.total * 0.9  # 10% discount
        return doc
    
    def _mapper_from_doc(self, doc: dict[str, Any]) -> Order:
        """Custom mapping with derived fields."""
        entity = self._mapper.from_doc(doc)
        # Reconstruct derived fields
        entity._total_items = doc.get("total_items", 0)
        return entity
```

---

## Integration Patterns

### Pattern 1: Simple CRUD Application

```python
from fastapi import FastAPI, Depends

app = FastAPI()

# Dependency
async def get_uow() -> MongoUnitOfWork:
    async with MongoUnitOfWork(connection=connection) as uow:
        yield uow

@app.post("/orders")
async def create_order(
    order_data: CreateOrderRequest,
    uow: MongoUnitOfWork = Depends(get_uow),
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
    async with MongoUnitOfWork(connection=connection) as uow:
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
    async with MongoUnitOfWork(connection=connection) as uow:
        # Read from read model (projection)
        summary = await projection_repo.get(order_id, uow=uow)
        return summary

async def ship_order_handler(cmd: ShipOrderCommand):
    """Command handler updating write model and emitting events."""
    async with MongoUnitOfWork(connection=connection) as uow:
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
async with MongoUnitOfWork(connection=connection) as uow:
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

### 4. Index Optimization

```python
from cqrs_ddd_persistence_mongo.indexes import ensure_indexes

# Create indexes for common queries
await ensure_indexes(
    db["orders"],
    [
        ("status", 1),  # Single field index
        ("customer_id", 1),  # Single field index
        ("customer_id", 1, "status", 1),  # Compound index
        ("created_at", -1),  # Descending index
    ],
)
```

---

## Error Handling

### Transaction Errors

```python
from pymongo.errors import OperationFailure

try:
    async with MongoUnitOfWork(connection=connection) as uow:
        await order_repo.add(order, uow=uow)
        await uow.commit()
except OperationFailure as e:
    if e.code == 112:  # WriteConflict
        logger.warning(f"Concurrent write detected: {e}")
        # Retry logic
    elif e.code == 251:  # NoSuchTransaction
        logger.error(f"Transaction expired: {e}")
    raise
```

### Connection Errors

```python
from pymongo.errors import ServerSelectionTimeoutError

try:
    order = await order_repo.get("order-123", uow=uow)
except ServerSelectionTimeoutError as e:
    logger.error(f"MongoDB connection failed: {e}")
    raise ServiceUnavailableError("Database temporarily unavailable")
```

---

## MongoDB Infrastructure Requirements

### Replica Set (Required for Transactions)

```bash
# Development: Single-node replica set
mongod --replSet rs0 --port 27017 --dbpath /data/db

# Initialize replica set
mongo --eval "rs.initiate()"
```

**Docker Compose:**
```yaml
version: '3.8'
services:
  mongodb:
    image: mongo:7.0
    command: mongod --replSet rs0
    ports:
      - "27017:27017"
    volumes:
      - mongodb_data:/data/db

volumes:
  mongodb_data:
```

**Connection String:**
```python
url = "mongodb://localhost:27017/?replicaSet=rs0"
```

### Standalone (Development Only)

```bash
# No transactions, but simpler setup
mongod --port 27017 --dbpath /data/db
```

**Connection String:**
```python
url = "mongodb://localhost:27017"  # No replicaSet
```

---

## Dependencies

- `motor>=3.0` - Async MongoDB driver
- `pymongo>=4.0` - MongoDB driver (sync, used by motor)
- `cqrs-ddd-core` - Domain primitives and ports
- `cqrs-ddd-specifications` - Specification pattern

---

## Testing

```python
import pytest
from mongomock_motor import AsyncMongoMockClient

@pytest.fixture
async def connection():
    """Mock MongoDB connection for testing."""
    connection = MongoConnectionManager(
        client=AsyncMongoMockClient(),
        database="test_db",
    )
    await connection.connect()
    yield connection
    await connection.disconnect()

@pytest.fixture
async def uow(connection):
    async with MongoUnitOfWork(
        connection=connection,
        require_replica_set=False,  # Mock doesn't support replica sets
    ) as uow:
        yield uow

async def test_repository_add(uow: MongoUnitOfWork):
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
| `MongoRepository` | Generic CRUD + search | `add`, `get`, `delete`, `search` |
| `MongoUnitOfWork` | Transaction management | `commit`, `rollback` |
| `MongoEventStore` | Event sourcing | `append`, `get_events`, `get_events_after` |
| `MongoOutboxStorage` | Reliable event publishing | `save_messages`, `get_pending`, `mark_published` |
| `MongoDBModelMapper` | Entity ↔ Document conversion | `to_doc`, `from_doc` |

**Total Lines:** ~1100  
**Dependencies:** Motor 3.0+, pymongo 4.0+, cqrs-ddd-core, cqrs-ddd-specifications  
**Python Version:** 3.11+  
**MongoDB Version:** 4.0+ (replica set required for transactions)
