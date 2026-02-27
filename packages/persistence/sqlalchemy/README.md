# SQLAlchemy Persistence for CQRS/DDD

**Production-ready persistence layer for Domain-Driven Design and CQRS applications using SQLAlchemy 2.0+**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![SQLAlchemy 2.0+](https://img.shields.io/badge/sqlalchemy-2.0+-orange.svg)](https://docs.sqlalchemy.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## Overview

`cqrs-ddd-persistence-sqlalchemy` provides a **complete persistence solution** for CQRS/DDD applications, implementing the repository pattern, event sourcing, sagas, projections, and advanced PostgreSQL features.

**Why This Package?**
- ✅ **Complete CQRS/DDD Stack** - Repository, UoW, Event Store, Outbox, Sagas, Projections
- ✅ **Type-Safe** - Full type hints with Pydantic integration
- ✅ **Async-First** - Built for asyncio with async/await throughout
- ✅ **PostgreSQL Optimized** - FTS, JSONB, Geometry, advanced indexing
- ✅ **Production-Ready** - Battle-tested patterns, optimistic concurrency, error handling
- ✅ **Modular Design** - Use only what you need (core, advanced, specifications)

---

## Quick Start

### Installation

```bash
# Core functionality
pip install cqrs-ddd-persistence-sqlalchemy

# With PostgreSQL support (recommended)
pip install cqrs-ddd-persistence-sqlalchemy[postgres]

# With SQLite support (development)
pip install cqrs-ddd-persistence-sqlalchemy[sqlite]

# With advanced features (sagas, projections, jobs)
pip install cqrs-ddd-persistence-sqlalchemy[advanced]
```

### Basic Usage

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from cqrs_ddd_persistence_sqlalchemy.core import (
    SQLAlchemyRepository,
    SQLAlchemyUnitOfWork,
)
from cqrs_ddd_core.domain.aggregate_root import AggregateRoot

# 1. Define domain model
class Order(AggregateRoot):
    id: str
    customer_id: str
    total: float
    status: str = "pending"

# 2. Define SQLAlchemy model
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Numeric

class OrderModel(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_id: Mapped[str] = mapped_column(String, ForeignKey("customers.id"))
    total: Mapped[float] = mapped_column(Numeric(10, 2))
    status: Mapped[str] = mapped_column(String(50))

# 3. Setup infrastructure
engine = create_async_engine("postgresql+asyncpg://user:pass@localhost/db")
session_factory = async_sessionmaker(engine, expire_on_commit=False)

order_repo = SQLAlchemyRepository(
    entity_cls=Order,
    db_model_cls=OrderModel,
)

# 4. Use in application
async def create_order(order_data: dict):
    async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow:
        order = Order(**order_data)
        await order_repo.add(order, uow=uow)
        await uow.commit()
        return order

async def get_order(order_id: str):
    async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow:
        return await order_repo.get(order_id, uow=uow)
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
│  │     CORE     │  │   ADVANCED   │  │     SPECS    │     │
│  │              │  │              │  │              │     │
│  │  Repository  │  │  Sagas       │  │  Compiler    │     │
│  │  UoW         │  │  Projections │  │  Operators   │     │
│  │  EventStore  │  │  Snapshots   │  │  Hooks       │     │
│  │  Outbox      │  │  Jobs        │  │              │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │    MIXINS    │  │    TYPES     │  │   UTILS      │     │
│  │              │  │              │  │              │     │
│  │  Version     │  │  JSONType    │  │  Helpers     │     │
│  │  Auditable   │  │  SpatiaLite  │  │  Validators  │     │
│  │  Archivable  │  │              │  │              │     │
│  │  Spatial     │  │              │  │              │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    DATABASE LAYER                            │
│                                                              │
│  PostgreSQL (Recommended)  |  SQLite (Development)          │
│  - Full-text search        |  - Basic features              │
│  - JSONB operations        |  - JSON support                │
│  - Geometry (PostGIS)      |  - SpatiaLite support          │
│  - Advanced indexing       |                                │
└─────────────────────────────────────────────────────────────┘
```

---

## Package Structure

### 1. Core Package (`core/`)

**Foundation for all CQRS/DDD applications.**

**Components:**
- `SQLAlchemyRepository` - Generic CRUD with specification support
- `SQLAlchemyUnitOfWork` - Transaction management with auto commit/rollback
- `SQLAlchemyEventStore` - Event sourcing with sequence-based positioning
- `SQLAlchemyOutboxStorage` - Transactional outbox pattern
- `ModelMapper` - Entity ↔ Model conversion

**Use When:**
- Building simple CRUD applications
- Implementing domain-driven design
- Need event sourcing capabilities
- Want reliable event publishing

**[📖 Full Documentation →](src/cqrs_ddd_persistence_sqlalchemy/core/README.md)**

**Example:**
```python
from cqrs_ddd_persistence_sqlalchemy.core import (
    SQLAlchemyRepository,
    SQLAlchemyUnitOfWork,
)

# Repository setup
order_repo = SQLAlchemyRepository(Order, OrderModel)

# Usage
async with SQLAlchemyUnitOfWork(session_factory) as uow:
    order = Order(id="123", customer_id="456", total=99.99)
    await order_repo.add(order, uow=uow)
    await uow.commit()
```

---

### 2. Advanced Package (`advanced/`)

**Advanced patterns for complex CQRS/DDD scenarios.**

**Components:**
- `SQLAlchemySagaRepository` - Saga state machine persistence
- `SQLAlchemyProjectionStore` - Materialized views with version control
- `SQLAlchemySnapshotStore` - Aggregate state snapshots
- `SQLAlchemyBackgroundJobRepository` - Job queue with retry logic
- `SQLAlchemyProjectionPositionStore` - Cursor tracking for projections

**Use When:**
- Implementing long-running processes (sagas)
- Building read models (projections)
- Optimizing aggregate reconstitution (snapshots)
- Processing background jobs

**[📖 Full Documentation →](src/cqrs_ddd_persistence_sqlalchemy/advanced/README.md)**

**Example:**
```python
from cqrs_ddd_persistence_sqlalchemy.advanced import (
    SQLAlchemySagaRepository,
    SQLAlchemyProjectionStore,
)

# Saga
saga_repo = SQLAlchemySagaRepository(OrderFulfillmentSaga)
saga = OrderFulfillmentSaga(order_id="123")
await saga_repo.add(saga, uow=uow)

# Projections
projection_store = SQLAlchemyProjectionStore(session_factory)
await projection_store.upsert(
    collection="order_summaries",
    doc_id="123",
    doc={"order_id": "123", "total": 99.99},
)
```

---

### 3. Specifications Package (`specifications/`)

**Compile domain specifications to SQLAlchemy queries.**

**Components:**
- `build_sqla_filter()` - Specification → SQL compiler
- `SQLAlchemyOperatorRegistry` - Operator strategy registry
- Resolution Hooks - Custom field resolution
- `apply_query_options()` - Query modifiers (order, limit, etc.)

**Use When:**
- Building dynamic queries from UI filters
- Need complex search functionality
- Want to decouple query logic from persistence
- Implementing specification pattern

**[📖 Full Documentation →](src/cqrs_ddd_persistence_sqlalchemy/specifications/README.md)**

**Example:**
```python
from cqrs_ddd_persistence_sqlalchemy.specifications import build_sqla_filter
from cqrs_ddd_specifications import SpecificationBuilder

# Build specification
builder = SpecificationBuilder()
spec = builder.where("status", "eq", "active").and_where("total", "gt", 100).build()

# Compile to SQL
filter_expr = build_sqla_filter(OrderModel, spec.to_dict())
stmt = select(OrderModel).where(filter_expr)

# Execute
result = await session.execute(stmt)
```

---

### 4. Mixins Package (`mixins/`)

**Reusable SQLAlchemy column mixins.**

**Components:**
- `VersionMixin` - Optimistic concurrency control
- `AuditableModelMixin` - Created/updated timestamps
- `ArchivableModelMixin` - Soft delete with partial indexes
- `SpatialModelMixin` - Geometry columns (PostGIS/SpatiaLite)

**Use When:**
- Adding standard columns to models
- Implementing optimistic locking
- Need soft delete functionality
- Working with spatial data

**[📖 Full Documentation →](src/cqrs_ddd_persistence_sqlalchemy/mixins/README.md)**

**Example:**
```python
from cqrs_ddd_persistence_sqlalchemy.mixins import (
    VersionMixin,
    AuditableModelMixin,
)

class OrderModel(VersionMixin, AuditableModelMixin, Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    # ... other fields

    # Automatically adds:
    # - version (for optimistic concurrency)
    # - created_at, updated_at (for auditing)
```

---

### 5. Types Package (`types/`)

**Cross-dialect SQLAlchemy type decorators.**

**Components:**
- `JSONType` - Dialect-agnostic JSON (PostgreSQL JSONB / SQLite JSON)
- `SpatiaLite` helpers - Spatial function setup for SQLite

**Use When:**
- Supporting multiple databases
- Working with JSON data
- Need spatial functionality in SQLite

**Example:**
```python
from cqrs_ddd_persistence_sqlalchemy.types import JSONType

class OrderModel(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    metadata: Mapped[dict] = mapped_column(JSONType())  # Works on both PG and SQLite
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
await repo.add(order, uow=uow)  # Optimistic concurrency check

# Delete
await repo.delete("123", uow=uow)

# Search with specifications
from cqrs_ddd_specifications import SpecificationBuilder

spec = builder.where("status", "eq", "active").build()
orders = await repo.search(spec, options, uow=uow)
```

### 2. Event Sourcing

**Complete event sourcing support with snapshots.**

```python
from cqrs_ddd_persistence_sqlalchemy.core import SQLAlchemyEventStore

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

### 3. Sagas Pattern

**Long-running process management with compensation.**

```python
from cqrs_ddd_advanced_core.sagas.state import SagaState

class OrderFulfillmentSaga(SagaState):
    order_id: str
    payment_id: str | None = None

    @saga_step(compensation="cancel_payment")
    async def process_payment(self, payment_service):
        self.payment_id = await payment_service.charge(self.order_id)

    async def cancel_payment(self, payment_service):
        await payment_service.refund(self.payment_id)

# Execute saga
saga = OrderFulfillmentSaga(order_id="123")
await saga.process_payment(payment_service)
await saga_repo.add(saga, uow=uow)
```

### 4. Projections (Read Models)

**Materialized views for optimized queries.**

```python
# Build projection
async def handle_order_created(event: OrderCreated):
    doc = {
        "order_id": event.order_id,
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

### 5. Optimistic Concurrency

**Automatic version checking for concurrent updates.**

```python
# First transaction
async with SQLAlchemyUnitOfWork(session_factory) as uow:
    order = await repo.get("123", uow=uow)
    order.status = "shipped"
    # version = 1 → 2
    await repo.add(order, uow=uow)
    await uow.commit()

# Concurrent transaction (fails)
async with SQLAlchemyUnitOfWork(session_factory) as uow:
    order = await repo.get("123", uow=uow)  # version = 1 (stale)
    order.status = "delivered"
    try:
        await repo.add(order, uow=uow)  # Raises OptimisticConcurrencyError
    except OptimisticConcurrencyError:
        # Reload and retry
        order = await repo.get("123", uow=uow)  # version = 2
        order.status = "delivered"
        await repo.add(order, uow=uow)  # version = 2 → 3
        await uow.commit()
```

### 6. Transactional Outbox

**Reliable event publishing with outbox pattern.**

```python
async def ship_order(order_id: str):
    async with SQLAlchemyUnitOfWork(session_factory) as uow:
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

### 7. PostgreSQL-Specific Features

**Full-text search, JSONB, Geometry operators.**

```python
# Full-text search
spec = builder.where("description", "fts", "python programming").build()
# WHERE to_tsvector('english', description) @@ to_tsquery('python & programming')

# JSONB containment
spec = builder.where("metadata", "@>", {"tags": ["premium"]}).build()
# WHERE metadata @> '{"tags": ["premium"]}'::jsonb

# Geometry queries
spec = builder.where("location", "st_within", polygon).build()
# WHERE ST_Within(location, ST_GeomFromText('POLYGON(...)'))
```

---

## Integration Examples

### FastAPI Integration

```python
from fastapi import FastAPI, Depends
from sqlalchemy.ext.asyncio import AsyncSession

app = FastAPI()

# Dependency
async def get_uow():
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

@app.get("/orders/{order_id}")
async def get_order(
    order_id: str,
    uow: SQLAlchemyUnitOfWork = Depends(get_uow),
):
    order = await order_repo.get(order_id, uow=uow)
    return order
```

### Dependency Injection Container

```python
from dependency_injector import containers, providers

class Container(containers.DeclarativeContainer):
    config = providers.Configuration()

    # Infrastructure
    engine = providers.Singleton(
        create_async_engine,
        config.database_url,
    )

    session_factory = providers.Singleton(
        async_sessionmaker,
        engine,
        expire_on_commit=False,
    )

    # Unit of Work
    uow = providers.Factory(
        SQLAlchemyUnitOfWork,
        session_factory=session_factory,
    )

    # Repositories
    order_repo = providers.Singleton(
        SQLAlchemyRepository,
        entity_cls=Order,
        db_model_cls=OrderModel,
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

async def test_create_order(uow: SQLAlchemyUnitOfWork):
    """Test order creation."""
    order = Order(id="123", customer_id="456", total=99.99)
    await order_repo.add(order, uow=uow)
    await uow.commit()

    loaded = await order_repo.get("123", uow=uow)
    assert loaded.id == "123"
    assert loaded.total == 99.99
```

---

## Configuration

### Database URLs

```python
# PostgreSQL (recommended)
DATABASE_URL = "postgresql+asyncpg://user:pass@localhost:5432/dbname"

# SQLite (development)
DATABASE_URL = "sqlite+aiosqlite:///./app.db"

# PostgreSQL with PostGIS
DATABASE_URL = "postgresql+asyncpg://user:pass@localhost:5432/dbname"
# Ensure PostGIS extension is installed:
# CREATE EXTENSION IF NOT EXISTS postgis;
```

### Engine Configuration

```python
from sqlalchemy.ext.asyncio import create_async_engine

engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Set True for SQL logging
    pool_size=10,  # Connection pool size
    max_overflow=20,  # Max connections beyond pool_size
    pool_pre_ping=True,  # Check connection health
    pool_recycle=3600,  # Recycle connections after 1 hour
)
```

### Session Configuration

```python
from sqlalchemy.ext.asyncio import async_sessionmaker

session_factory = async_sessionmaker(
    engine,
    expire_on_commit=False,  # Don't expire objects after commit
    autoflush=False,  # Don't auto-flush before queries
    isolation_level="READ COMMITTED",  # Transaction isolation level
)
```

---

## Performance Optimization

### 1. Connection Pooling

```python
# ✅ GOOD: Use connection pool
engine = create_async_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
)

# ❌ BAD: Create new connection per request
async def get_order(order_id: str):
    async with create_async_engine(DATABASE_URL).connect() as conn:
        # ... query
```

### 2. Batch Operations

```python
# ✅ GOOD: Single transaction
async with SQLAlchemyUnitOfWork(session_factory) as uow:
    for order in orders:
        await repo.add(order, uow=uow)
    await uow.commit()  # Single commit

# ❌ BAD: Multiple transactions
for order in orders:
    async with SQLAlchemyUnitOfWork(session_factory) as uow:
        await repo.add(order, uow=uow)
        await uow.commit()
```

### 3. Streaming Large Results

```python
# ✅ GOOD: Stream results
async for order in (await repo.search(spec, options)).stream():
    process(order)

# ❌ BAD: Load all into memory
orders = await (await repo.search(spec, options))
for order in orders:
    process(order)
```

### 4. Index Optimization

```python
# Create indexes for common queries
class OrderModel(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_id: Mapped[str] = mapped_column(String, ForeignKey("customers.id"))
    status: Mapped[str] = mapped_column(String(50), index=True)  # Index for filtering
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)  # Index for ordering

    __table_args__ = (
        Index("ix_orders_customer_status", "customer_id", "status"),  # Composite index
    )
```

---

## Migration to Production

### 1. Use Migrations (Alembic)

```bash
# Install Alembic
pip install alembic

# Initialize
alembic init migrations

# Create migration
alembic revision --autogenerate -m "Initial schema"

# Apply migration
alembic upgrade head
```

### 2. Disable Auto-DDL

```python
# ❌ DEVELOPMENT ONLY: Auto-create tables
await projection_store.ensure_collection("order_summaries", schema=schema)

# ✅ PRODUCTION: Use migrations
# Disable auto-DDL
projection_store = SQLAlchemyProjectionStore(
    session_factory=session_factory,
    allow_auto_ddl=False,  # Raises error if collection doesn't exist
)
```

### 3. Connection Pooling

```python
# Production engine configuration
engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True,
    pool_recycle=3600,
)
```

### 4. Monitoring

```python
import logging

# Enable SQL logging
logging.basicConfig()
logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)

# Monitor connection pool
from sqlalchemy import event

@event.listens_for(engine.sync_engine, "checkout")
def receive_checkout(dbapi_connection, connection_record, connection_proxy):
    logger.debug("Connection checked out from pool")
```

---

## API Reference

### Core Package

- `SQLAlchemyRepository(entity_cls, db_model_cls)` - Generic repository
- `SQLAlchemyUnitOfWork(session, session_factory)` - Transaction manager
- `SQLAlchemyEventStore(session)` - Event store
- `SQLAlchemyOutboxStorage(session)` - Outbox pattern

### Advanced Package

- `SQLAlchemySagaRepository(saga_cls)` - Saga persistence
- `SQLAlchemyProjectionStore(session_factory)` - Projection storage
- `SQLAlchemySnapshotStore(uow_factory)` - Snapshot store
- `SQLAlchemyBackgroundJobRepository(job_cls)` - Job queue

### Specifications Package

- `build_sqla_filter(model, spec_dict, hooks)` - Specification compiler
- `apply_query_options(stmt, model, options)` - Query modifier
- `SQLAlchemyOperatorRegistry()` - Operator registry

---

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

**Development Setup:**
```bash
git clone https://github.com/your-org/cqrs-ddd-persistence-sqlalchemy
cd cqrs-ddd-persistence-sqlalchemy
poetry install
poetry run pytest
```

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---

## Support

- **Documentation:** [Full API docs](docs/)
- **Issues:** [GitHub Issues](https://github.com/your-org/cqrs-ddd-persistence-sqlalchemy/issues)
- **Discussions:** [GitHub Discussions](https://github.com/your-org/cqrs-ddd-persistence-sqlalchemy/discussions)

---

## Acknowledgments

Built on top of:
- [SQLAlchemy 2.0](https://docs.sqlalchemy.org/) - The best Python ORM
- [cqrs-ddd-core](https://github.com/your-org/cqrs-ddd-core) - Domain primitives
- [cqrs-ddd-specifications](https://github.com/your-org/cqrs-ddd-specifications) - Specification pattern

**Total Package Lines:** ~4000
**Dependencies:** SQLAlchemy 2.0+, cqrs-ddd-core, cqrs-ddd-specifications
**Python Version:** 3.11+
