# MongoDB Persistence for CQRS/DDD

**Production-ready persistence layer for Domain-Driven Design and CQRS applications using MongoDB 4.0+**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![MongoDB 4.0+](https://img.shields.io/badge/mongodb-4.0+-green.svg)](https://www.mongodb.com/)
[![Motor 3.0+](https://img.shields.io/badge/motor-3.0+-orange.svg)](https://motor.readthedocs.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## Overview

`cqrs-ddd-persistence-mongo` provides a **complete persistence solution** for CQRS/DDD applications using MongoDB, implementing the repository pattern, event sourcing, projections, and advanced MongoDB features.

**Why MongoDB for CQRS/DDD?**
- ✅ **Document Model** - Natural fit for aggregates and domain models
- ✅ **Flexible Schema** - Easy evolution of domain models
- ✅ **Embedded Documents** - Efficient aggregate storage without joins
- ✅ **Rich Query Language** - Powerful filtering and aggregation
- ✅ **Horizontal Scaling** - Built-in sharding for large-scale applications
- ✅ **Change Streams** - Real-time event propagation

**Key Features:**
- ✅ **Core CQRS/DDD Stack** - Repository, UoW, Event Store, Outbox, Projections
- ✅ **Type-Safe** - Full type hints with Pydantic integration
- ✅ **Async-First** - Built for asyncio with Motor async driver
- ✅ **Transaction Support** - Multi-document ACID transactions (replica set required)
- ✅ **Optimistic Concurrency** - Atomic version checking using MongoDB operators
- ✅ **Specification Pattern** - Compile domain specifications to MongoDB queries
- ✅ **Saga Repository** - Long-running process management
- ✅ **Background Jobs** - Job queue with atomic claiming
- ⚠️ **See Limitations** - Some features differ from SQL implementation

---

## Quick Start

### Installation

```bash
# Core functionality
pip install cqrs-ddd-persistence-mongo

# With advanced features (projections, snapshots)
pip install cqrs-ddd-persistence-mongo[advanced]
```

### Basic Usage

```python
from motor.motor_asyncio import AsyncIOMotorClient
from cqrs_ddd_persistence_mongo.core import (
    MongoRepository,
    MongoUnitOfWork,
)
from cqrs_ddd_persistence_mongo.connection import MongoConnectionManager
from cqrs_ddd_core.domain.aggregate_root import AggregateRoot

# 1. Define domain model
class Order(AggregateRoot):
    id: str
    customer_id: str
    total: float
    status: str = "pending"

# 2. Setup connection (with replica set for transactions)
connection = MongoConnectionManager(
    url="mongodb://localhost:27017/?replicaSet=rs0",
    database="myapp",
)
await connection.connect()

# 3. Setup repository
order_repo = MongoRepository(
    connection=connection,
    collection="orders",
    model_cls=Order,
    id_field="id",  # Maps to _id in MongoDB
)

# 4. Use in application
async def create_order(order_data: dict):
    async with MongoUnitOfWork(connection=connection) as uow:
        order = Order(**order_data)
        await order_repo.add(order, uow=uow)
        await uow.commit()
        return order

async def get_order(order_id: str):
    # No transaction needed for reads
    return await order_repo.get(order_id)
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    APPLICATION LAYER                         │
│                                                              │
│  Command Handlers / Query Handlers / Event Handlers          │
│                                                              │
│  Features:                                                   │
│  - Transaction management (Unit of Work)                     │
│  - Domain event handling                                     │
│  - Specification-based queries                               │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                  PERSISTENCE LAYER                           │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │     CORE     │  │   ADVANCED   │  │   OPERATORS  │     │
│  │              │  │              │  │              │     │
│  │  Repository  │  │  Projections │  │  Standard    │     │
│  │  UoW         │  │  Snapshots   │  │  String      │     │
│  │  EventStore  │  │  Positions   │  │  Set         │     │
│  │  Outbox      │  │              │  │  Null        │     │
│  │              │  │              │  │  JSONB       │     │
│  │              │  │              │  │  Geometry    │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ CONNECTION   │  │    QUERY     │  │    UTILS     │     │
│  │              │  │   BUILDER    │  │              │     │
│  │  Connection  │  │              │  │  Indexes     │     │
│  │  Manager     │  │  build_match │  │  Search      │     │
│  │              │  │  build_sort  │  │  Helpers     │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    MONGODB DATABASE                          │
│                                                              │
│  Replica Set (Required for transactions)                     │
│  Collections: aggregates, domain_events, outbox, projections│
└─────────────────────────────────────────────────────────────┘
```

---

## Package Structure

### 1. Core Package (`core/`)

**Foundation for all CQRS/DDD applications.**

**Components:**
- `MongoRepository` - Generic CRUD with specification support
- `MongoUnitOfWork` - Transaction management with ACID guarantees
- `MongoEventStore` - Event sourcing with atomic counter positioning
- `MongoOutboxStorage` - Transactional outbox pattern
- `MongoDBModelMapper` - Entity ↔ Document conversion

**Use When:**
- Building simple CRUD applications
- Implementing domain-driven design
- Need event sourcing capabilities
- Want reliable event publishing

**[📖 Full Documentation →](src/cqrs_ddd_persistence_mongo/core/README.md)**

**Example:**
```python
from cqrs_ddd_persistence_mongo.core import (
    MongoRepository,
    MongoUnitOfWork,
)

# Repository setup
order_repo = MongoRepository(
    connection=connection,
    collection="orders",
    model_cls=Order,
)

# Usage with transaction
async with MongoUnitOfWork(connection=connection) as uow:
    order = Order(id="123", customer_id="456", total=99.99)
    await order_repo.add(order, uow=uow)
    await uow.commit()
```

---

### 2. Advanced Package (`advanced/`)

**Advanced patterns for complex CQRS/DDD scenarios.**

**Components:**
- `MongoProjectionStore` - Materialized views with version control
- `MongoSnapshotStore` - Aggregate state snapshots
- `MongoProjectionPositionStore` - Cursor tracking for projections

**Use When:**
- Building read models (projections)
- Optimizing aggregate reconstitution (snapshots)
- Implementing continuous projection builders
- Need cursor-based event processing

**[📖 Full Documentation →](src/cqrs_ddd_persistence_mongo/advanced/README.md)**

**Example:**
```python
from cqrs_ddd_persistence_mongo.advanced import (
    MongoProjectionStore,
    MongoSnapshotStore,
)

# Projections
projection_store = MongoProjectionStore(connection=connection)
await projection_store.upsert(
    collection="order_summaries",
    doc_id="123",
    doc={"order_id": "123", "total": 99.99, "_version": 1},
)

# Snapshots
snapshot_store = MongoSnapshotStore(connection=connection)
await snapshot_store.save_snapshot(
    aggregate_type="Order",
    aggregate_id="123",
    snapshot_data=order.model_dump(),
    version=50,
)
```

---

### 3. Operators Package (`operators/`)

**Compile domain specifications to MongoDB queries.**

**Components:**
- `compile_standard` - Basic comparisons ($eq, $gt, $lt, etc.)
- `compile_string` - String matching ($regex)
- `compile_set` - Set membership ($in, $nin)
- `compile_null` - Null checks ($exists)
- `compile_jsonb` - Document queries (dot notation, $all)
- `compile_geometry` - Spatial queries ($geoWithin, $near)

**Use When:**
- Building dynamic queries from UI filters
- Need complex search functionality
- Want to decouple query logic from persistence
- Implementing specification pattern

**[📖 Full Documentation →](src/cqrs_ddd_persistence_mongo/operators/README.md)**

**Example:**
```python
from cqrs_ddd_persistence_mongo.query_builder import MongoQueryBuilder
from cqrs_ddd_specifications import SpecificationBuilder

# Build specification
builder = SpecificationBuilder()
spec = (
    builder
    .where("status", "eq", "active")
    .and_where("total", "gte", 100)
    .build()
)

# Compile to MongoDB query
query_builder = MongoQueryBuilder()
filter_dict = query_builder.build_match(spec)
# {"$and": [{"status": {"$eq": "active"}}, {"total": {"$gte": 100}}]}

# Execute
cursor = db["orders"].find(filter_dict)
```

---

## Features

### 1. Repository Pattern

**Type-safe CRUD operations with specification support.**

```python
# Create
order = Order(id="123", total=99.99)
await repo.add(order, uow=uow)

# Read
order = await repo.get("123", uow=uow)

# Update
order.status = "shipped"
await repo.add(order, uow=uow)  # Upsert

# Delete
await repo.delete("123", uow=uow)

# Search with specifications
from cqrs_ddd_specifications import SpecificationBuilder

spec = builder.where("status", "eq", "active").build()
orders = await repo.search(spec, options, uow=uow)
```

### 2. Document Model

**Natural fit for domain aggregates with embedded documents.**

```python
# Domain model with nested objects
class Order(AggregateRoot):
    id: str
    customer: Customer  # Embedded document
    items: list[OrderItem]  # Array of embedded documents
    shipping_address: Address  # Embedded document
    status: str

# MongoDB document (automatic conversion)
{
    "_id": "order-123",
    "customer": {
        "id": "cust-456",
        "name": "John Doe",
        "email": "john@example.com",
    },
    "items": [
        {"product_id": "prod-1", "quantity": 2, "price": 29.99},
        {"product_id": "prod-2", "quantity": 1, "price": 49.99},
    ],
    "shipping_address": {
        "street": "123 Main St",
        "city": "New York",
        "country": "USA",
    },
    "status": "pending",
    "_version": 1,
}
```

### 3. Event Sourcing

**Complete event sourcing support with atomic positioning.**

```python
from cqrs_ddd_persistence_mongo.core import MongoEventStore

# Append events
event = StoredEvent(
    event_id="evt-123",
    event_type="OrderCreated",
    aggregate_id="order-456",
    payload={"customer_id": "cust-789"},
)
await event_store.append(event)

# Replay events
events = await event_store.get_events("order-456")
for event in events:
    order.apply(event)
```

### 4. Transactions (ACID)

**Multi-document ACID transactions with replica sets.**

```python
async with MongoUnitOfWork(connection=connection) as uow:
    # Both operations succeed or fail together
    await order_repo.add(order, uow=uow)
    await inventory_repo.decrement(item_id, uow=uow)

    # Atomic commit
    await uow.commit()
```

**Important:** Requires replica set (not standalone).

### 5. Projections (Read Models)

**Materialized views for optimized queries.**

```python
# Build projection
async def handle_order_created(event: OrderCreated):
    doc = {
        "id": event.order_id,
        "customer_name": event.customer_name,
        "total_amount": event.total,
        "_version": 1,
    }

    await projection_store.upsert(
        collection="order_summaries",
        doc_id=event.order_id,
        doc=doc,
    )

# Query projection
summary = await projection_store.find_one(
    collection="order_summaries",
    doc_id="order-123",
)
```

### 6. Optimistic Concurrency

**Automatic version checking for concurrent updates.**

```python
# First transaction
async with MongoUnitOfWork(connection=connection) as uow:
    order = await repo.get("123", uow=uow)
    order.status = "shipped"
    # version = 1 → 2
    await repo.add(order, uow=uow)
    await uow.commit()

# Concurrent transaction (fails)
async with MongoUnitOfWork(connection=connection) as uow:
    order = await repo.get("123", uow=uow)  # version = 1 (stale)
    order.status = "delivered"
    try:
        await repo.add(order, uow=uow)  # Version mismatch
    except VersionMismatchError:
        # Reload and retry
        ...
```

### 7. Transactional Outbox

**Reliable event publishing with outbox pattern.**

```python
async def ship_order(order_id: str):
    async with MongoUnitOfWork(connection=connection) as uow:
        # Update aggregate
        order = await repo.get(order_id, uow=uow)
        order.ship()
        await repo.add(order, uow=uow)

        # Save events to outbox (same transaction)
        events = order.pull_domain_events()
        await outbox.save_messages([
            OutboxMessage(
                message_id=e.event_id,
                event_type=e.event_type,
                payload=e.model_dump(),
            )
            for e in events
        ], uow=uow)

        # Atomic commit
        await uow.commit()

# Background publisher (separate process)
async def outbox_publisher():
    while True:
        messages = await outbox.get_pending(limit=100)
        for msg in messages:
            await kafka_producer.send(msg.event_type, msg.payload)
            await outbox.mark_published([msg.message_id])
        await asyncio.sleep(1)
```

### 8. Rich Query Language

**Leverage MongoDB's powerful query capabilities.**

```python
# Complex queries with MongoDB operators
projections = await projection_store.find(
    collection="order_summaries",
    filter={
        "status": {"$in": ["pending", "processing"]},
        "total_amount": {"$gte": 100},
        "created_at": {"$gte": datetime.now() - timedelta(days=7)},
    },
    sort=[("total_amount", -1)],
    limit=20,
)

# Aggregation pipeline
pipeline = [
    {"$match": {"status": "completed"}},
    {"$group": {
        "_id": "$customer_id",
        "total_spent": {"$sum": "$total_amount"},
        "order_count": {"$sum": 1},
    }},
    {"$sort": {"total_spent": -1}},
    {"$limit": 10},
]

results = await db["orders"].aggregate(pipeline).to_list(None)
```

---

## Integration Examples

### FastAPI Integration

```python
from fastapi import FastAPI, Depends

app = FastAPI()

# Dependency
async def get_uow():
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

@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    # No transaction needed for reads
    order = await order_repo.get(order_id)
    return order
```

### Dependency Injection Container

```python
from dependency_injector import containers, providers

class Container(containers.DeclarativeContainer):
    config = providers.Configuration()

    # Infrastructure
    connection = providers.Singleton(
        MongoConnectionManager,
        url=config.mongodb_url,
        database=config.database,
    )

    # Unit of Work
    uow = providers.Factory(
        MongoUnitOfWork,
        connection=connection,
    )

    # Repositories
    order_repo = providers.Singleton(
        MongoRepository,
        connection=connection,
        collection="orders",
        model_cls=Order,
    )

    # Services
    order_service = providers.Factory(
        OrderService,
        order_repo=order_repo,
        uow=uow,
    )
```

### Testing

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

async def test_create_order(uow: MongoUnitOfWork):
    """Test order creation."""
    order = Order(id="123", customer_id="456", total=99.99)
    await order_repo.add(order, uow=uow)
    await uow.commit()

    loaded = await order_repo.get("123")
    assert loaded.id == "123"
    assert loaded.total == 99.99
```

---

## Configuration

### Connection URLs

```python
# Replica set (required for transactions)
url = "mongodb://localhost:27017,localhost:27018,localhost:27019/?replicaSet=rs0"

# MongoDB Atlas (cloud)
url = "mongodb+srv://user:pass@cluster0.mongodb.net/myapp?retryWrites=true"

# Standalone (development only, no transactions)
url = "mongodb://localhost:27017"
```

### Connection Manager

```python
from cqrs_ddd_persistence_mongo.connection import MongoConnectionManager

connection = MongoConnectionManager(
    url="mongodb://localhost:27017/?replicaSet=rs0",
    database="myapp",
    max_pool_size=100,
    min_pool_size=10,
    max_idle_time_ms=60000,
    connect_timeout_ms=10000,
    socket_timeout_ms=0,  # No timeout
)

await connection.connect()
# ... use connection
await connection.disconnect()
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

## Performance Optimization

### 1. Connection Pooling

```python
# ✅ GOOD: Use connection pool
connection = MongoConnectionManager(
    url=url,
    max_pool_size=100,
    min_pool_size=10,
)

# ❌ BAD: Create new connection per request
async def get_order(order_id: str):
    client = AsyncIOMotorClient(url)
    # ... query
    client.close()
```

### 2. Index Optimization

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

### 3. Batch Operations

```python
# ✅ GOOD: Single transaction
async with MongoUnitOfWork(connection=connection) as uow:
    for order in orders:
        await repo.add(order, uow=uow)
    await uow.commit()  # Single commit

# ❌ BAD: Multiple transactions
for order in orders:
    async with MongoUnitOfWork(connection=connection) as uow:
        await repo.add(order, uow=uow)
        await uow.commit()
```

### 4. Projection Streaming

```python
# ✅ GOOD: Stream large results
async cursor = db["orders"].find(filter_dict).batch_size(100)
async for order in cursor:
    process(order)

# ❌ BAD: Load all into memory
orders = await db["orders"].find(filter_dict).to_list(None)
for order in orders:
    process(order)
```

---

## Migration to Production

### 1. Use Connection Pooling

```python
# Production connection configuration
connection = MongoConnectionManager(
    url=MONGODB_URL,
    database="production_db",
    max_pool_size=100,
    min_pool_size=20,
    max_idle_time_ms=60000,
    connect_timeout_ms=10000,
)
```

### 2. Create Indexes

```python
# Create indexes before deploying
from cqrs_ddd_persistence_mongo.indexes import ensure_indexes

await ensure_indexes(
    db["orders"],
    [
        ("customer_id", 1),
        ("status", 1),
        ("created_at", -1),
        ("customer_id", 1, "status", 1),
    ],
    background=True,  # Don't block operations
)
```

### 3. Enable Monitoring

```python
import logging

# Enable MongoDB logging
logging.basicConfig()
logging.getLogger("motor").setLevel(logging.INFO)

# Monitor connection pool
from pymongo import monitoring

class CommandLogger(monitoring.CommandListener):
    def started(self, event):
        logging.debug(f"Command {event.command_name} started")

    def succeeded(self, event):
        logging.debug(f"Command {event.command_name} succeeded")

    def failed(self, event):
        logging.error(f"Command {event.command_name} failed: {event.failure}")

monitoring.register(CommandLogger())
```

### 4. Use MongoDB Atlas (Recommended)

```python
# MongoDB Atlas connection (fully managed)
url = "mongodb+srv://user:pass@cluster0.mongodb.net/myapp?retryWrites=true&w=majority"

# Atlas provides:
# - Automatic replica sets
# - Automatic backups
# - Built-in monitoring
# - Global clusters
# - Auto-scaling
```

---

## API Reference

### Core Package

- `MongoRepository(connection, collection, model_cls)` - Generic repository
- `MongoUnitOfWork(connection)` - Transaction manager
- `MongoEventStore(connection)` - Event store
- `MongoOutboxStorage(connection)` - Outbox pattern
- `MongoDBModelMapper(model_cls)` - Entity ↔ Document mapper

### Advanced Package

- `MongoProjectionStore(connection)` - Projection storage
- `MongoSnapshotStore(connection)` - Snapshot store
- `MongoProjectionPositionStore(connection)` - Position tracker

### Query Builder

- `MongoQueryBuilder()` - Specification compiler
- `build_match(spec)` - Build MongoDB filter
- `build_sort(order_by)` - Build sort specification

---

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

**Development Setup:**
```bash
git clone https://github.com/your-org/cqrs-ddd-persistence-mongo
cd cqrs-ddd-persistence-mongo
poetry install
poetry run pytest
```

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---

## Support

- **Documentation:** [Full API docs](docs/)
- **Issues:** [GitHub Issues](https://github.com/your-org/cqrs-ddd-persistence-mongo/issues)
- **Discussions:** [GitHub Discussions](https://github.com/your-org/cqrs-ddd-persistence-mongo/discussions)

---

## Acknowledgments

Built on top of:
- [Motor](https://motor.readthedocs.io/) - Async MongoDB driver
- [PyMongo](https://pymongo.readthedocs.io/) - MongoDB driver
- [cqrs-ddd-core](https://github.com/your-org/cqrs-ddd-core) - Domain primitives
- [cqrs-ddd-specifications](https://github.com/your-org/cqrs-ddd-specifications) - Specification pattern

**Total Package Lines:** ~2500
**Dependencies:** Motor 3.0+, pymongo 4.0+, cqrs-ddd-core, cqrs-ddd-specifications
**Python Version:** 3.11+
**MongoDB Version:** 4.0+ (replica set required for transactions)
