# Projections System

A comprehensive guide to the CQRS-DDD Projections System for building scalable, eventually consistent read models.

---

## Table of Contents

1. [Overview](#overview)
2. [Write Models vs Read Models](#write-models-vs-read-models)
3. [Architecture](#architecture)
4. [Core Components](#core-components)
   - [IProjectionWriter & IProjectionReader](#iprojectionwriter--iprojectionreader)
   - [ProjectionSchema](#projectionschema)
   - [ProjectionWorker](#projectionworker)
   - [ProjectionManager](#projectionmanager)
   - [ProjectionBackedPersistence](#projectionbackedpersistence)
5. [Event Processing](#event-processing)
6. [Specification Compilation](#specification-compilation)
7. [Usage Examples](#usage-examples)
8. [Best Practices](#best-practices)
9. [Infrastructure Implementations](#infrastructure-implementations)

---

## Overview

**Projections** are denormalized, optimized read models built from domain events. They represent the "Q" (Query) side of CQRS, providing efficient data structures for queries while keeping the domain model focused on business logic.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          CQRS Architecture                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│    ┌──────────────┐         ┌──────────────┐                           │
│    │    WRITE     │         │    READ      │                           │
│    │    MODEL     │         │    MODEL     │                           │
│    ├──────────────┤         ├──────────────┤                           │
│    │              │  Events │              │                           │
│    │  Aggregate   │────────▶│  Projection  │                           │
│    │  Root        │         │  (Denorm.)   │                           │
│    │              │         │              │                           │
│    │  - Commands  │         │  - Queries   │                           │
│    │  - Business  │         │  - DTOs      │                           │
│    │    Rules     │         │  - Optimized │                           │
│    │  - Events    │         │    for Read  │                           │
│    └──────────────┘         └──────────────┘                           │
│           │                        │                                    │
│           ▼                        ▼                                    │
│    ┌──────────────┐         ┌──────────────┐                           │
│    │  Event Store │         │  Projection  │                           │
│    │  (Append     │         │  Store       │                           │
│    │   Only)      │         │  (Mongo/SQL) │                           │
│    └──────────────┘         └──────────────┘                           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Key Benefits

| Benefit | Description |
|---------|-------------|
| **Separation of Concerns** | Domain logic stays in aggregates; queries use optimized projections |
| **Performance** | Pre-computed joins, denormalized data, indexed for specific queries |
| **Scalability** | Read replicas can serve projections independently |
| **Flexibility** | Multiple projections from same events for different use cases |
| **Event Sourcing** | Replay events to rebuild projections at any point |

---

## Write Models vs Read Models

### Write Model (Domain Layer)

```python
# The source of truth - captures business intent and enforces invariants
class Order(AggregateRoot):
    def __init__(self, order_id: str, customer_id: str):
        super().__init__()
        self.id = order_id
        self.customer_id = customer_id
        self.items: list[OrderItem] = []
        self.status = OrderStatus.PENDING
        self.total = Decimal("0.00")
    
    def add_item(self, product_id: str, quantity: int, price: Decimal):
        # Business rules enforced here
        if self.status != OrderStatus.PENDING:
            raise CannotModifyCompletedOrder()
        
        item = OrderItem(product_id, quantity, price)
        self.items.append(item)
        self.total += item.subtotal
        
        # Emits domain event
        self.add_event(OrderItemAdded(
            order_id=self.id,
            product_id=product_id,
            quantity=quantity,
            price=str(price),
            new_total=str(self.total)
        ))
```

### Read Model (Projection)

```python
# Optimized for queries - denormalized, pre-computed, indexed
@dataclass
class OrderSummaryDTO:
    """Projection optimized for order list views."""
    id: str
    customer_name: str        # Denormalized from Customer
    customer_email: str       # Denormalized from Customer
    item_count: int           # Pre-computed count
    total: Decimal            # Pre-computed sum
    status: str
    created_at: datetime
    last_updated: datetime
    
@dataclass  
class CustomerOrderHistoryDTO:
    """Projection optimized for customer order history."""
    customer_id: str
    customer_name: str
    total_orders: int         # Pre-computed
    total_spent: Decimal      # Pre-computed
    last_order_date: datetime
    favorite_products: list[str]  # Pre-computed
```

### Comparison Table

| Aspect | Write Model | Read Model (Projection) |
|--------|-------------|------------------------|
| **Purpose** | Business logic, validation | Fast queries, display |
| **Normalization** | Normalized (3NF) | Denormalized |
| **Mutability** | Mutable via commands | Immutable (replaced) |
| **Source** | User commands | Domain events |
| **Storage** | Event Store | Projection Store |
| **Consistency** | Strong (transactional) | Eventual |
| **Schema** | Domain-driven | Query-driven |
| **Indexes** | For aggregate retrieval | For specific queries |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         PROJECTION PIPELINE                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────────┐     │
│  │ Event Store │───▶│ Projection  │───▶│ Projection Store        │     │
│  │             │    │ Worker      │    │ (SQLAlchemy / MongoDB)  │     │
│  │ - Ordered   │    │             │    │                         │     │
│  │ - Durable   │    │ - Position  │    │ - customer_summaries    │     │
│  │             │    │   Tracking  │    │ - order_summaries       │     │
│  │             │    │             │    │ - product_search        │     │
│  │             │    │ - Handler   │    │                         │     │
│  │             │    │   Dispatch  │    │                         │     │
│  └─────────────┘    └─────────────┘    └─────────────────────────┘     │
│         │                  │                        │                   │
│         │                  ▼                        ▼                   │
│         │           ┌─────────────┐         ┌─────────────────┐        │
│         │           │ Position    │         │ Backed          │        │
│         │           │ Store       │         │ Persistence     │        │
│         │           │             │         │                 │        │
│         │           │ - Resume    │         │ - Typed DTOs    │        │
│         │           │   Point     │         │ - Specs         │        │
│         │           │ - Replay    │         │ - Dispatcher    │        │
│         │           │   Support   │         │   Integration   │        │
│         └──────────▶└─────────────┘         └─────────────────┘        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Core Components

### IProjectionWriter & IProjectionReader

Low-level interfaces for projection storage operations.

```python
from cqrs_ddd_advanced_core.ports.projection import (
    IProjectionWriter,
    IProjectionReader,
    DocId,
)

# Writer - for event handlers updating projections
class IProjectionWriter(Protocol):
    async def ensure_collection(
        self, collection: str, *, schema: ProjectionSchema | None = None
    ) -> None:
        """Create table/collection with optional schema."""
        ...
    
    async def upsert(
        self,
        collection: str,
        doc_id: DocId,
        data: dict[str, Any],
        *,
        event_position: int | None = None,  # For concurrency control
        event_id: str | None = None,         # For idempotency
        uow: UnitOfWork | None = None,
    ) -> bool:
        """Upsert with version control. Returns False if stale/duplicate."""
        ...
    
    async def upsert_batch(
        self, collection: str, docs: list[dict], *, id_field: str = "id"
    ) -> None:
        """Bulk upsert for efficiency."""
        ...
    
    async def delete(
        self, collection: str, doc_id: DocId, *, uow: UnitOfWork | None = None
    ) -> None:
        """Delete a projection document."""
        ...

# Reader - for queries and read-modify-write patterns
class IProjectionReader(Protocol):
    async def get(
        self, collection: str, doc_id: DocId, *, uow: UnitOfWork | None = None
    ) -> dict[str, Any] | None:
        """Fetch single document by ID."""
        ...
    
    async def get_batch(
        self, collection: str, doc_ids: list[DocId], *, uow: UnitOfWork | None = None
    ) -> list[dict[str, Any] | None]:
        """Fetch multiple documents preserving order."""
        ...
    
    async def find(
        self,
        collection: str,
        filter: dict[str, Any],
        *,
        limit: int = 100,
        offset: int = 0,
        uow: UnitOfWork | None = None,
    ) -> list[dict[str, Any]]:
        """Query documents by filter dict."""
        ...
```

#### Version Control & Idempotency

Every projection upsert can include version metadata for:

1. **Optimistic Concurrency**: Skip if existing `_version` >= `event_position`
2. **Idempotency**: Skip if `_last_event_id` matches (already processed)

```python
# Event handler with version control
async def handle_order_created(self, event: OrderCreated, uow: UnitOfWork):
    await self.writer.upsert(
        "order_summaries",
        event.order_id,
        {
            "id": event.order_id,
            "customer_id": event.customer_id,
            "status": "pending",
            "total": "0.00",
        },
        event_position=event.position,  # Concurrency control
        event_id=event.id,               # Idempotency
        uow=uow,
    )
```

---

### ProjectionSchema

Declarative schema definitions for SQL-based projections.

```python
from cqrs_ddd_advanced_core.projections.schema import (
    ProjectionSchema,
    ProjectionSchemaRegistry,
    ProjectionRelationship,
    RelationshipType,
    GeometryType,
)
from sqlalchemy import Column, String, Integer, Numeric, DateTime
from sqlalchemy import func

# Define projection schema
customer_summary_schema = ProjectionSchema(
    name="customer_summaries",
    columns=[
        Column("id", String(36), primary_key=True),
        Column("customer_name", String(255), nullable=False),
        Column("customer_email", String(255), nullable=False),
        Column("total_orders", Integer, default=0),
        Column("total_spent", Numeric(12, 2), default=0),
        Column("last_order_date", DateTime(timezone=True)),
        Column("created_at", DateTime(timezone=True), server_default=func.now()),
        # Version columns added automatically
    ],
    indexes=[
        {"columns": ["customer_email"], "unique": True},
        {"columns": ["last_order_date"]},
    ],
)

# Register schemas
registry = ProjectionSchemaRegistry()
registry.register(customer_summary_schema)
registry.register(order_summary_schema)

# Generate DDL
ddl = customer_summary_schema.create_ddl()
# CREATE TABLE customer_summaries (
#     id VARCHAR(36) PRIMARY KEY,
#     customer_name VARCHAR(255) NOT NULL,
#     ...
#     _version INTEGER DEFAULT 0,
#     _last_event_id VARCHAR(36),
#     _last_event_position INTEGER
# )
```

#### Schema with Relationships

```python
order_summary_schema = ProjectionSchema(
    name="order_summaries",
    columns=[
        Column("id", String(36), primary_key=True),
        Column("customer_id", String(36), nullable=False),
        Column("customer_name", String(255)),  # Denormalized
        Column("status", String(50)),
        Column("total", Numeric(12, 2)),
    ],
    relationships=[
        ProjectionRelationship(
            name="customer",
            type=RelationshipType.MANY_TO_ONE,
            target_schema="customer_summaries",
            foreign_key="customer_id",
        )
    ],
)
```

---

### ProjectionWorker

Processes events from the event store and updates projections.

```python
from cqrs_ddd_advanced_core.projections.worker import (
    ProjectionWorker,
    ProjectionEventHandler,
)

# Define handlers for each event type
class OrderSummaryHandler:
    def __init__(self, writer: IProjectionWriter):
        self.writer = writer
    
    async def handle(self, event: StoredEvent, *, uow: UnitOfWork) -> None:
        if event.event_type == "OrderCreated":
            data = json.loads(event.payload)
            await self.writer.upsert(
                "order_summaries",
                data["order_id"],
                {
                    "id": data["order_id"],
                    "customer_id": data["customer_id"],
                    "status": "pending",
                    "total": "0.00",
                },
                event_position=event.position,
                event_id=event.id,
                uow=uow,
            )
        
        elif event.event_type == "OrderItemAdded":
            data = json.loads(event.payload)
            # Update existing projection
            existing = await self.writer.get("order_summaries", data["order_id"])
            if existing:
                await self.writer.upsert(
                    "order_summaries",
                    data["order_id"],
                    {**existing, "total": data["new_total"]},
                    event_position=event.position,
                    event_id=event.id,
                    uow=uow,
                )

# Create worker
handler_map = {
    "OrderCreated": OrderSummaryHandler(writer),
    "OrderItemAdded": OrderSummaryHandler(writer),
}

worker = ProjectionWorker(
    event_store=event_store,
    position_store=position_store,
    writer=writer,
    handler_map=handler_map,
    uow_factory=uow_factory,
    catch_up=False,  # Set True to skip historical replay
)

# Run projection
await worker.run("order_summaries")
```

#### Catch-Up Mode

When `catch_up=True` and no position exists, the worker:
1. Gets the latest event position from event store
2. Saves that position (skipping historical events)
3. Starts streaming only new events

Useful for projections that only need current state going forward.

---

### ProjectionManager

Distributed initialization with locking for multi-pod deployments.

```python
from cqrs_ddd_advanced_core.projections.manager import ProjectionManager
from cqrs_ddd_core.ports.locking import ILockStrategy

# Setup with Redis locking
manager = ProjectionManager(
    writer=writer,
    registry=schema_registry,
    lock_strategy=redis_lock_strategy,
)

# Initialize single projection (with distributed lock)
await manager.initialize_once("customer_summaries")

# Initialize all projections in dependency order
await manager.initialize_all()
```

This ensures only one process runs DDL when multiple instances start simultaneously.

---

### ProjectionBackedPersistence

Adapts low-level projection stores to typed query interfaces for dispatcher integration.

```python
from cqrs_ddd_advanced_core.projections.backed_persistence import (
    ProjectionBackedQueryPersistence,
    ProjectionBackedSpecPersistence,
    ProjectionBackedDualPersistence,
)
from pydantic import BaseModel

# Define DTO
class CustomerSummaryDTO(BaseModel):
    id: str
    customer_name: str
    customer_email: str
    total_orders: int
    total_spent: Decimal
    last_order_date: datetime | None

# Option 1: ID-based queries only
class CustomerSummaryQueryPersistence(
    ProjectionBackedQueryPersistence[CustomerSummaryDTO, str]
):
    collection = "customer_summaries"
    
    def __init__(self, store: IProjectionReader):
        self._store = store
    
    def to_dto(self, doc: dict) -> CustomerSummaryDTO:
        return CustomerSummaryDTO(
            id=doc["id"],
            customer_name=doc["customer_name"],
            customer_email=doc["customer_email"],
            total_orders=doc.get("total_orders", 0),
            total_spent=Decimal(doc.get("total_spent", "0")),
            last_order_date=doc.get("last_order_date"),
        )
    
    def get_reader(self) -> IProjectionReader:
        return self._store

# Option 2: Specification-based queries
class CustomerSummarySpecPersistence(
    ProjectionBackedSpecPersistence[CustomerSummaryDTO]
):
    collection = "customer_summaries"
    # ... same as above ...
    
    def build_filter(self, spec: ISpecification) -> dict[str, Any]:
        # Convert specification to filter dict
        if hasattr(spec, "customer_email"):
            return {"customer_email": spec.customer_email}
        if hasattr(spec, "min_orders"):
            return {"total_orders": {"$gte": spec.min_orders}}  # MongoDB
        return {}

# Option 3: Full-featured dual persistence
class CustomerSummaryDualPersistence(
    ProjectionBackedDualPersistence[CustomerSummaryDTO, str]
):
    collection = "customer_summaries"
    # ... to_dto, get_reader, get_writer, build_filter ...
    
    # Plus convenience method for projection handlers:
    async def refresh_from_event(
        self, customer_id: str, event: CustomerUpdated
    ) -> bool:
        return await self.refresh(
            customer_id,
            {
                "id": customer_id,
                "customer_name": event.new_name,
                "customer_email": event.new_email,
            },
            event_position=event.position,
            event_id=event.id,
        )
```

#### Register with Dispatcher

```python
from cqrs_ddd_advanced_core.persistence.dispatcher import (
    PersistenceRegistry,
    PersistenceDispatcher,
)

registry = PersistenceRegistry()

# Register projection-backed queries
registry.register_query(
    CustomerSummaryDTO,
    CustomerSummaryQueryPersistence,
)

registry.register_query_spec(
    CustomerSummaryDTO,
    CustomerSummarySpecPersistence,
)

# Create dispatcher
dispatcher = PersistenceDispatcher(
    uow_factories={"default": uow_factory},
    registry=registry,
)

# Use in query handlers
class GetCustomerSummaryQueryHandler:
    async def handle(self, query: GetCustomerSummary, uow: UnitOfWork):
        results = await dispatcher.fetch(
            CustomerSummaryDTO,
            [query.customer_id],
            uow=uow,
        )
        return results[0] if results else None
```

---

## Event Processing

### Event Flow

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Command    │────▶│   Aggregate  │────▶│ Domain Event │────▶│ Event Store  │
│   Handler    │     │   (Write)    │     │              │     │              │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
                                                                        │
                           ┌────────────────────────────────────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │  Projection  │
                    │   Worker     │
                    └──────────────┘
                           │
           ┌───────────────┼───────────────┐
           │               │               │
           ▼               ▼               ▼
    ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
    │  Projection  │ │  Projection  │ │  Projection  │
    │   Store      │ │   Store      │ │   Store      │
    │              │ │              │ │              │
    │  - orders    │ │  - customers │ │  - products  │
    └──────────────┘ └──────────────┘ └──────────────┘
```

### Position Tracking

The `IProjectionPositionStore` tracks the last processed event position for each projection:

```python
class IProjectionPositionStore(Protocol):
    async def get_position(
        self, projection_name: str, *, uow: UnitOfWork | None = None
    ) -> int | None:
        """Get last processed position. None = never processed."""
        ...
    
    async def save_position(
        self, projection_name: str, position: int, *, uow: UnitOfWork | None = None
    ) -> None:
        """Update position after successful processing. MUST be in same UoW as projection writes."""
        ...
    
    async def reset_position(
        self, projection_name: str, *, uow: UnitOfWork | None = None
    ) -> None:
        """Reset for full replay."""
        ...
```

### Replay Scenarios

```python
# Scenario 1: New projection from historical events
async def rebuild_customer_stats(position_store, writer, event_store):
    # Reset position to replay from beginning
    await position_store.reset_position("customer_stats")
    
    # Clear existing data
    await writer.truncate_collection("customer_stats")
    
    # Run worker to rebuild
    worker = ProjectionWorker(
        event_store=event_store,
        position_store=position_store,
        writer=writer,
        handler_map=handler_map,
        uow_factory=uow_factory,
    )
    await worker.run("customer_stats")

# Scenario 2: Fix corrupted projection
async def repair_orders_after(position_store, writer, event_store, from_position: int):
    # Reset to specific position
    await position_store.save_position("order_summaries", from_position)
    
    # Worker will reprocess from that point
    await worker.run("order_summaries")
```

---

## Usage Examples

### Complete Example: E-Commerce Order System

```python
# ============================================================
# 1. DOMAIN EVENTS (Write Side)
# ============================================================

@dataclass
class OrderCreated(DomainEvent):
    order_id: str
    customer_id: str
    created_at: datetime

@dataclass  
class OrderItemAdded(DomainEvent):
    order_id: str
    product_id: str
    product_name: str
    quantity: int
    unit_price: str
    new_total: str

@dataclass
class OrderSubmitted(DomainEvent):
    order_id: str
    submitted_at: datetime

# ============================================================
# 2. PROJECTION DEFINITIONS (Read Side)
# ============================================================

from pydantic import BaseModel
from decimal import Decimal
from datetime import datetime

class OrderSummaryDTO(BaseModel):
    """Projection for order list views."""
    id: str
    customer_id: str
    customer_name: str        # Denormalized
    status: str
    total: Decimal
    item_count: int
    created_at: datetime
    submitted_at: datetime | None

class CustomerStatsDTO(BaseModel):
    """Projection for customer statistics."""
    id: str
    customer_name: str
    email: str
    total_orders: int
    total_spent: Decimal
    last_order_date: datetime | None
    favorite_product_id: str | None

class ProductSalesDTO(BaseModel):
    """Projection for product analytics."""
    id: str  # product_id
    product_name: str
    total_sold: int
    revenue: Decimal
    last_sold_at: datetime | None

# ============================================================
# 3. PROJECTION HANDLERS
# ============================================================

class OrderSummaryHandler:
    """Updates order_summaries projection."""
    
    def __init__(self, writer: IProjectionWriter, reader: IProjectionReader):
        self.writer = writer
        self.reader = reader
    
    async def handle_order_created(self, event: OrderCreated, uow: UnitOfWork):
        # Get customer info for denormalization
        customer = await self.reader.get("customer_stats", event.customer_id)
        customer_name = customer.get("customer_name", "Unknown") if customer else "Unknown"
        
        await self.writer.upsert(
            "order_summaries",
            event.order_id,
            {
                "id": event.order_id,
                "customer_id": event.customer_id,
                "customer_name": customer_name,
                "status": "pending",
                "total": "0.00",
                "item_count": 0,
                "created_at": event.created_at.isoformat(),
                "submitted_at": None,
            },
            event_position=event.position,
            event_id=event.id,
            uow=uow,
        )
    
    async def handle_order_item_added(self, event: OrderItemAdded, uow: UnitOfWork):
        existing = await self.reader.get("order_summaries", event.order_id)
        if not existing:
            return  # Order doesn't exist, skip
        
        await self.writer.upsert(
            "order_summaries",
            event.order_id,
            {
                **existing,
                "total": event.new_total,
                "item_count": existing.get("item_count", 0) + event.quantity,
            },
            event_position=event.position,
            event_id=event.id,
            uow=uow,
        )
    
    async def handle_order_submitted(self, event: OrderSubmitted, uow: UnitOfWork):
        existing = await self.reader.get("order_summaries", event.order_id)
        if not existing:
            return
        
        await self.writer.upsert(
            "order_summaries",
            event.order_id,
            {
                **existing,
                "status": "submitted",
                "submitted_at": event.submitted_at.isoformat(),
            },
            event_position=event.position,
            event_id=event.id,
            uow=uow,
        )

class CustomerStatsHandler:
    """Updates customer_stats projection."""
    
    def __init__(self, writer: IProjectionWriter):
        self.writer = writer
    
    async def handle_order_submitted(self, event: OrderSubmitted, uow: UnitOfWork):
        # Get order to find customer
        order = await self.writer.get("order_summaries", event.order_id)
        if not order:
            return
        
        customer_id = order["customer_id"]
        existing = await self.writer.get("customer_stats", customer_id)
        
        if existing:
            # Update existing stats
            new_total_orders = existing.get("total_orders", 0) + 1
            new_total_spent = Decimal(existing.get("total_spent", "0")) + Decimal(order["total"])
            
            await self.writer.upsert(
                "customer_stats",
                customer_id,
                {
                    **existing,
                    "total_orders": new_total_orders,
                    "total_spent": str(new_total_spent),
                    "last_order_date": event.submitted_at.isoformat(),
                },
                event_position=event.position,
                event_id=event.id,
                uow=uow,
            )

# ============================================================
# 4. QUERY PERSISTENCE (Dispatcher Integration)
# ============================================================

class OrderSummaryQueryPersistence(
    ProjectionBackedDualPersistence[OrderSummaryDTO, str]
):
    """Full-featured query persistence for orders."""
    
    collection = "order_summaries"
    
    def __init__(self, store: SQLAlchemyProjectionStore):
        self._store = store
    
    def to_dto(self, doc: dict) -> OrderSummaryDTO:
        return OrderSummaryDTO(
            id=doc["id"],
            customer_id=doc["customer_id"],
            customer_name=doc["customer_name"],
            status=doc["status"],
            total=Decimal(doc["total"]),
            item_count=doc.get("item_count", 0),
            created_at=datetime.fromisoformat(doc["created_at"]),
            submitted_at=datetime.fromisoformat(doc["submitted_at"]) if doc.get("submitted_at") else None,
        )
    
    def get_reader(self) -> IProjectionReader:
        return self._store
    
    def get_writer(self) -> IProjectionWriter:
        return self._store
    
    def build_filter(self, spec: ISpecification) -> dict[str, Any]:
        """Convert specification to filter dict for IProjectionReader.find()."""
        filters = {}
        
        if hasattr(spec, "customer_id"):
            filters["customer_id"] = spec.customer_id
        
        if hasattr(spec, "status"):
            filters["status"] = spec.status
        
        # Note: For complex queries (ranges, OR conditions), use 
        # the specification compilation system instead of build_filter()
        # See "Specification Compilation" section below
        
        return filters

# ============================================================
# 5. REGISTRATION & BOOTSTRAP
# ============================================================

from cqrs_ddd_advanced_core.persistence.dispatcher import (
    PersistenceRegistry,
    PersistenceDispatcher,
)

# Setup
registry = PersistenceRegistry()

# Register query handlers
registry.register_query(OrderSummaryDTO, OrderSummaryQueryPersistence)
registry.register_query_spec(OrderSummaryDTO, OrderSummaryQueryPersistence)

dispatcher = PersistenceDispatcher(
    uow_factories={"default": lambda: SQLAlchemyUnitOfWork(session_factory)},
    registry=registry,
)

# ============================================================
# 6. QUERY HANDLERS (Application Layer)
# ============================================================

class GetOrderSummaryHandler:
    """Query handler for single order."""
    
    async def handle(self, query: GetOrderSummary, uow: UnitOfWork) -> OrderSummaryDTO | None:
        results = await dispatcher.fetch(OrderSummaryDTO, [query.order_id], uow=uow)
        return results[0] if results else None

class ListCustomerOrdersHandler:
    """Query handler for customer's orders."""
    
    async def handle(
        self, query: ListCustomerOrders, uow: UnitOfWork
    ) -> list[OrderSummaryDTO]:
        from cqrs_ddd_specifications import SpecificationBuilder, QueryOptions
        
        # Build specification
        builder = SpecificationBuilder().where("customer_id", "=", query.customer_id)
        
        if query.status:
            builder = builder.where("status", "=", query.status)
        
        spec = builder.build()
        
        # Create query options
        options = QueryOptions().with_specification(spec)
        
        results = await dispatcher.fetch(OrderSummaryDTO, options, uow=uow)
        return await results  # SearchResult -> list
```

---

## Best Practices

### 1. Projection Design

| Practice | Description |
|----------|-------------|
| **Denormalize for queries** | Include all data needed for display; avoid joins |
| **Pre-compute aggregates** | Store counts, sums, averages in the projection |
| **One projection per view** | Different views = different projections |
| **Version your projections** | Use `_version` for optimistic concurrency |
| **Include timestamps** | `created_at`, `updated_at` for debugging and sync |

### 2. Event Handling

```python
# ✅ GOOD: Idempotent handlers
async def handle(self, event: StoredEvent, uow: UnitOfWork):
    # Version/idempotency check is automatic via upsert()
    await self.writer.upsert(
        "my_projection",
        doc_id,
        data,
        event_position=event.position,
        event_id=event.id,
        uow=uow,
    )

# ❌ BAD: Non-idempotent operations
async def handle(self, event: StoredEvent, uow: UnitOfWork):
    # This will duplicate on replay!
    existing = await self.reader.get("my_projection", doc_id)
    await self.writer.upsert(
        "my_projection",
        doc_id,
        {"count": existing["count"] + 1},  # WRONG: increments on replay
    )

# ✅ GOOD: Use event data for idempotency
async def handle(self, event: StoredEvent, uow: UnitOfWork):
    data = json.loads(event.payload)
    await self.writer.upsert(
        "my_projection",
        doc_id,
        {"count": data["new_count"]},  # RIGHT: deterministic from event
    )
```

### 3. Concurrency

```python
# Always use UnitOfWork for atomic updates
async def handle_batch(self, events: list[StoredEvent]):
    async with self.uow_factory() as uow:
        for event in events:
            await self.handle(event, uow=uow)
        # All updates commit together
```

### 4. Error Handling

```python
# ProjectionWorker logs and continues on handler errors
# For critical projections, add custom error handling:

class RobustHandler:
    async def handle(self, event: StoredEvent, *, uow: UnitOfWork):
        try:
            await self._process(event, uow=uow)
        except ProjectionConsistencyError as e:
            # Log and skip - don't block the stream
            logger.error(f"Consistency error for {event.id}: {e}")
        except Exception as e:
            # Re-raise to stop worker - requires manual intervention
            logger.critical(f"Fatal error processing {event.id}: {e}")
            raise
```

---

## Infrastructure Implementations

### SQLAlchemy (PostgreSQL/SQLite)

```python
from cqrs_ddd_persistence_sqlalchemy.advanced import (
    SQLAlchemyProjectionStore,
    SQLAlchemyProjectionPositionStore,
    SQLAlchemyProjectionDualPersistence,
)

# Setup
store = SQLAlchemyProjectionStore(
    session_factory=async_session_factory,
    allow_auto_ddl=False,  # Use migrations in production
    default_id_column="id",
)

position_store = SQLAlchemyProjectionPositionStore(session_factory)

# Query persistence
class MyQueryPersistence(SQLAlchemyProjectionDualPersistence[MyDTO, str]):
    def build_filter(self, spec) -> dict:
        """
        Simple filter for equality queries.
        
        For complex queries (ranges, OR, computed fields), see the
        "Specification Compilation" section for using build_sqla_filter()
        with hooks.
        """
        if hasattr(spec, "status"):
            return {"status": spec.status}
        return {}
```

### MongoDB

```python
from cqrs_ddd_persistence_mongo.advanced import (
    MongoProjectionStore,
    MongoProjectionPositionStore,
    MongoProjectionDualPersistence,
)

# Setup
store = MongoProjectionStore(
    client=mongo_client,
    database="projections",
    id_field="id",
)

position_store = MongoProjectionPositionStore(
    client=mongo_client,
    database="projections",
)

# Query persistence
class MyQueryPersistence(MongoProjectionDualPersistence[MyDTO, str]):
    """
    MongoDB query persistence with automatic specification compilation.
    
    Note: No build_filter() needed! MongoQueryBuilder automatically
    compiles specifications to MongoDB queries. See "Specification Compilation"
    section for details.
    """
    pass
```

### MongoDB Transaction Support

**Important:** MongoDB transactions require a replica set (not available on standalone instances).

```python
# ✅ GOOD: Transactional updates (requires replica set)
async def handle_order_created(self, event: OrderCreated, uow: UnitOfWork):
    # Both position and projection update in same transaction
    await self.position_store.save_position(
        "order_summaries",
        event.position,
        uow=uow,  # Reuses MongoDB session from UnitOfWork
    )
    
    await self.writer.upsert(
        "order_summaries",
        event.order_id,
        {
            "id": event.order_id,
            "customer_id": event.customer_id,
            "status": "pending",
            "total": "0.00",
        },
        event_position=event.position,
        event_id=event.id,
        uow=uow,  # Same session - atomic with position update
    )

# ⚠️ DEVELOPMENT: mongomock compatibility
# mongomock doesn't support sessions/transactions
# The implementation automatically falls back to non-transactional mode
```

**Setting up MongoDB Replica Set for Development:**

```bash
# Using Docker
docker run -d --name mongo-replica \
  -p 27017:27017 \
  mongo:7.0 --replSet rs0

# Initialize replica set
docker exec -it mongo-replica mongosh --eval "rs.initiate()"
```

**Transaction Requirements:**

| Feature | Standalone | Replica Set | Sharded Cluster |
|---------|-----------|-------------|-----------------|
| Transactions | ❌ No | ✅ Yes | ✅ Yes (on mongos) |
| Sessions | ❌ No | ✅ Yes | ✅ Yes |
| Multi-document ACID | ❌ No | ✅ Yes | ✅ Yes |

**Fallback Behavior:**

When using `mongomock` in tests or standalone MongoDB, the projection stores
automatically handle the lack of session support:

```python
# In MongoProjectionStore._get_session()
def _get_session(self, uow: UnitOfWork | None) -> Any:
    if uow is None:
        return None
    return getattr(uow, "session", None)

# In upsert() and other operations
session = self._get_session(uow)
try:
    await coll.find_one(filter_doc, session=session)
except (NotImplementedError, TypeError):
    # mongomock fallback - ignore session parameter
    await coll.find_one(filter_doc)
```

---

## Specification Compilation

The projection system integrates with the `cqrs_ddd_specifications` package to provide
backend-specific query compilation.

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    SPECIFICATION COMPILATION FLOW                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────────┐                                                   │
│  │  Specification   │  SpecificationBuilder instance                    │
│  │  (Python DSL)    │  .where("customer_id", "=", "123")                │
│  │                  │  .where("status", "=", "active")                  │
│  └────────┬─────────┘                                                   │
│           │                                                             │
│           │ spec.to_dict()                                              │
│           ▼                                                             │
│  ┌──────────────────┐                                                   │
│  │   AST (Dict)     │  {"op": "and", "conditions": [...]}               │
│  │                  │  {"op": "eq", "attr": "status", "val": "active"}  │
│  └────────┬─────────┘                                                   │
│           │                                                             │
│           ├──────────────────────┬─────────────────────┐                │
│           │                      │                     │                │
│           ▼                      ▼                     ▼                │
│  ┌────────────────┐    ┌─────────────────┐   ┌──────────────────┐     │
│  │  SQLAlchemy    │    │     MongoDB      │   │   Memory         │     │
│  │  Compiler      │    │   Query Builder  │   │   Evaluator      │     │
│  │                │    │                  │   │                  │     │
│  │ build_sqla_    │    │ MongoQueryBuilder│   │ MemoryEvaluator  │     │
│  │ filter()       │    │ .build_match()   │   │ .evaluate()      │     │
│  └────────┬───────┘    └────────┬─────────┘   └────────┬─────────┘     │
│           │                     │                      │               │
│           ▼                     ▼                      ▼               │
│  ┌────────────────┐    ┌─────────────────┐   ┌──────────────────┐     │
│  │ ColumnElement  │    │  MongoDB Filter │   │   Python bool    │     │
│  │ [bool] (SQL)   │    │  Dict (Query)   │   │   (in-memory)    │     │
│  └────────────────┘    └─────────────────┘   └──────────────────┘     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Using with cqrs_ddd_specifications

The projection system integrates with the `cqrs_ddd_specifications` package to provide
type-safe query building with backend-specific compilation.

```python
from cqrs_ddd_specifications import SpecificationBuilder, QueryOptions
from cqrs_ddd_advanced_core.persistence.dispatcher import PersistenceDispatcher

# Build specification using fluent builder
spec = (
    SpecificationBuilder()
    .where("customer_id", "=", "cust_123")
    .where("status", "=", "submitted")
    .where("total", ">=", Decimal("100.00"))
    .build()
)

# Create query options with specification, ordering, and pagination
options = (
    QueryOptions()
    .with_specification(spec)
    .with_ordering("-created_at")
    .with_pagination(limit=10)
)

# Fetch via dispatcher (automatically compiles to backend query)
result = await dispatcher.fetch(OrderSummaryDTO, options, uow=uow)
orders = await result  # SearchResult -> list
```

**API Components:**

| Component | Purpose | Example |
|-----------|---------|---------|
| `SpecificationBuilder` | Builds filter conditions | `.where("field", "op", value)` |
| `QueryOptions` | Result shaping (order, limit, etc.) | `.with_ordering("-date").with_pagination(limit=10)` |
| `SpecificationOperator` | Valid operators | `"="`, `">="`, `"in"`, `"contains"`, etc. |

**Common Operators:**

```python
from cqrs_ddd_specifications import SpecificationBuilder, SpecificationOperator

builder = SpecificationBuilder()

# Equality
builder.where("status", "=", "active")

# Comparison
builder.where("age", ">=", 18)
builder.where("price", "<", 100)

# Set membership
builder.where("status", "in", ["active", "pending"])

# String matching
builder.where("name", "contains", "smith")
builder.where("email", "starts_with", "admin")

# Null checks
builder.where("deleted_at", "is_null", True)

# Range
builder.where("age", "between", [18, 65])
```

**Advanced: Logical Grouping**

```python
# OR conditions
spec = (
    SpecificationBuilder()
    .or_group()
        .where("role", "=", "admin")
        .where("role", "=", "superuser")
    .end_group()
    .where("active", "=", True)
    .build()
)

# Complex nested conditions
spec = (
    SpecificationBuilder()
    .where("customer_id", "=", "123")
    .or_group()
        .where("status", "=", "submitted")
        .and_group()
            .where("status", "=", "draft")
            .where("created_by", "=", "user_456")
        .end_group()
    .end_group()
    .build()
)
```

### Backend-Specific Compilation

#### MongoDB (Automatic)

MongoDB projections use `MongoQuerySpecificationPersistence` which automatically
compiles specifications using `MongoQueryBuilder`:

```python
from cqrs_ddd_persistence_mongo.advanced import MongoProjectionDualPersistence
from cqrs_ddd_persistence_mongo.query_builder import MongoQueryBuilder

class OrderSummaryQueryPersistence(MongoProjectionDualPersistence[OrderSummaryDTO, str]):
    collection = "order_summaries"
    
    def __init__(self, store: MongoProjectionStore):
        self._store = store
    
    def to_dto(self, doc: dict) -> OrderSummaryDTO:
        return OrderSummaryDTO(**doc)
    
    # No build_filter() needed! MongoQueryBuilder handles it automatically
```

**MongoDB Query Builder Features:**

```python
from cqrs_ddd_persistence_mongo.query_builder import MongoQueryBuilder
from cqrs_ddd_specifications import SpecificationBuilder

# Build specification
spec = (
    SpecificationBuilder()
    .where("status", "=", "active")
    .where("age", ">=", 18)
    .build()
)

# Compile specification to MongoDB filter
builder = MongoQueryBuilder()
filter_query = builder.build_match(spec)
# Result: {"$and": [{"status": "active"}, {"age": {"$gte": 18}}]}

# Build sort stage
sort = builder.build_sort([("-created_at", "desc"), ("name", "asc")])
# Result: [("created_at", -1), ("name", 1)]

# Build projection stage
project = builder.build_project(["id", "name", "email"])
# Result: {"id": 1, "name": 1, "email": 1}
```

#### SQLAlchemy (Manual or Hooks)

SQLAlchemy projections can use one of two approaches:

**Option 1: Simple `build_filter()` for equality queries**

```python
from cqrs_ddd_persistence_sqlalchemy.advanced import SQLAlchemyProjectionDualPersistence

class OrderSummaryQueryPersistence(
    SQLAlchemyProjectionDualPersistence[OrderSummaryDTO, str]
):
    collection = "order_summaries"
    
    def build_filter(self, spec: ISpecification) -> dict[str, Any]:
        """Simple filter dict for equality queries."""
        filters = {}
        
        if hasattr(spec, "customer_id"):
            filters["customer_id"] = spec.customer_id
        
        if hasattr(spec, "status"):
            filters["status"] = spec.status
        
        return filters
```

**Option 2: Full specification compiler for complex queries**

```python
from cqrs_ddd_persistence_sqlalchemy.specifications import build_sqla_filter
from cqrs_ddd_persistence_sqlalchemy.advanced import SQLAlchemyProjectionStore

# For complex queries, use the specification compiler directly
class OrderSummaryQueryPersistence(
    SQLAlchemyProjectionDualPersistence[OrderSummaryDTO, str]
):
    async def find_by_spec(
        self, 
        spec: ISpecification, 
        *, 
        limit: int = 100,
        offset: int = 0,
        uow: UnitOfWork | None = None,
    ) -> list[OrderSummaryDTO]:
        """Execute specification-based query using compiler."""
        from sqlalchemy import select
        
        # Compile specification to SQLAlchemy expression
        filter_expr = build_sqla_filter(
            OrderSummaryModel,
            spec.to_dict(),
            hooks=self._get_hooks(),
        )
        
        # Build query
        stmt = select(OrderSummaryModel).where(filter_expr)
        
        if offset:
            stmt = stmt.offset(offset)
        if limit:
            stmt = stmt.limit(limit)
        
        # Execute
        session = self._get_session(uow)
        result = await session.execute(stmt)
        rows = result.scalars().all()
        
        return [self.to_dto(self._row_to_dict(row)) for row in rows]
```

### Supported Specification Operators

| Operator | SQLAlchemy | MongoDB | Memory | Example |
|----------|-----------|---------|--------|---------|
| **Equality** |
| `eq` / `=` | ✅ | ✅ | ✅ | `.where("status", "=", "active")` |
| `ne` / `!=` | ✅ | ✅ | ✅ | `.where("status", "!=", "deleted")` |
| **Comparison** |
| `gt` / `>` | ✅ | ✅ | ✅ | `.where("age", ">", 18)` |
| `gte` / `>=` | ✅ | ✅ | ✅ | `.where("age", ">=", 18)` |
| `lt` / `<` | ✅ | ✅ | ✅ | `.where("price", "<", 100)` |
| `lte` / `<=` | ✅ | ✅ | ✅ | `.where("price", "<=", 100)` |
| **Range** |
| `between` | ✅ | ✅ | ✅ | `.where("age", "between", [18, 65])` |
| `not_between` | ✅ | ✅ | ✅ | `.where("price", "not_between", [10, 20])` |
| **Set Membership** |
| `in` | ✅ | ✅ | ✅ | `.where("status", "in", ["active", "pending"])` |
| `not_in` | ✅ | ✅ | ✅ | `.where("status", "not_in", ["deleted"])` |
| **String Matching** |
| `like` | ✅ | ✅* | ✅ | `.where("name", "like", "%john%")` |
| `ilike` | ✅ | ✅* | ✅ | `.where("name", "ilike", "%JOHN%")` |
| `starts_with` | ✅ | ✅ | ✅ | `.where("email", "starts_with", "admin")` |
| `ends_with` | ✅ | ✅ | ✅ | `.where("email", "ends_with", "@example.com")` |
| `contains` | ✅ | ✅ | ✅ | `.where("name", "contains", "smith")` |
| **Null Handling** |
| `is_null` | ✅ | ✅ | ✅ | `.where("deleted_at", "is_null", True)` |
| `is_not_null` | ✅ | ✅ | ✅ | `.where("email", "is_not_null", True)` |
| **JSON/JSONB** |
| `json_contains` | ✅ | ✅ | ✅ | `.where("tags", "json_contains", "python")` |
| `json_has_key` | ✅ | ✅ | ✅ | `.where("metadata", "json_has_key", "verified")` |
| **Array/Set** |
| `array_contains` | ✅ | ✅ | ✅ | `.where("tags", "array_contains", ["python"])` |
| **Geography/Geometry** |
| `geo_within` | ✅** | ✅ | ❌ | `.where("location", "geo_within", polygon)` |
| `geo_intersects` | ✅** | ✅ | ❌ | `.where("area", "geo_intersects", point)` |
| `near` | ✅** | ✅ | ❌ | `.where("location", "near", point)` |
| **Full-Text Search** |
| `fts_match` | ✅*** | ✅ | ❌ | `.where("content", "fts_match", "python async")` |

\* MongoDB uses `$regex` for pattern matching  
\** Requires PostGIS extension for SQLAlchemy  
\*** Requires PostgreSQL full-text search configuration

### SQLAlchemy Resolution Hooks

For complex field resolution (computed columns, JSON paths, relationship joins):

```python
from cqrs_ddd_persistence_sqlalchemy.specifications.hooks import (
    SQLAlchemyResolutionContext,
    SQLAlchemyHookResult,
    ResolutionHook,
)
from cqrs_ddd_persistence_sqlalchemy.specifications import build_sqla_filter

def json_field_hook(ctx: SQLAlchemyResolutionContext) -> SQLAlchemyHookResult:
    """Resolve JSON/JSONB field queries."""
    if ctx.field_path.startswith("metadata."):
        # Extract nested JSON field
        json_path = ctx.field_path.split(".", 1)[1]
        return SQLAlchemyHookResult(
            handled=True,
            value=Model.data[json_path].astext == ctx.value,
        )
    return SQLAlchemyHookResult(handled=False)

def computed_field_hook(ctx: SQLAlchemyResolutionContext) -> SQLAlchemyHookResult:
    """Handle computed/virtual fields."""
    if ctx.field_path == "full_name":
        return SQLAlchemyHookResult(
            handled=True,
            value=(Model.first_name + " " + Model.last_name).ilike(f"%{ctx.value}%"),
        )
    return SQLAlchemyHookResult(handled=False)

def relationship_hook(ctx: SQLAlchemyResolutionContext) -> SQLAlchemyHookResult:
    """Handle relationship field queries."""
    if "." in ctx.field_path:
        parts = ctx.field_path.split(".", 1)
        if parts[0] == "customer":
            # customer.email -> access relationship
            return SQLAlchemyHookResult(
                handled=True,
                value=getattr(Model.customer, parts[1]) == ctx.value,
            )
    return SQLAlchemyHookResult(handled=False)

# Use hooks in filter compilation
hooks: list[ResolutionHook] = [
    json_field_hook,
    computed_field_hook,
    relationship_hook,
]

filter_expr = build_sqla_filter(
    OrderSummaryModel,
    spec.to_dict(),
    hooks=hooks,
)
```

### MongoDB Query Operators

MongoDB's query builder supports all MongoDB operators directly:

```python
# Comparison operators
{"field": {"$eq": value}}      # Equal
{"field": {"$ne": value}}      # Not equal
{"field": {"$gt": value}}      # Greater than
{"field": {"$gte": value}}     # Greater than or equal
{"field": {"$lt": value}}      # Less than
{"field": {"$lte": value}}     # Less than or equal
{"field": {"$in": [values]}}   # In array
{"field": {"$nin": [values]}}  # Not in array

# Logical operators
{"$and": [expr1, expr2]}       # AND
{"$or": [expr1, expr2]}        # OR
{"$nor": [expr1, expr2]}       # NOR
{"$not": {expr}}               # NOT

# Element operators
{"field": {"$exists": True}}   # Field exists
{"field": {"$type": "string"}} # Type check

# Array operators
{"field": {"$all": [val1, val2]}}    # Contains all
{"field": {"$elemMatch": {...}}}     # Element match
{"field": {"$size": 3}}              # Array size

# Geospatial operators
{"field": {"$near": {"$geometry": point, "$maxDistance": 1000}}}
{"field": {"$geoWithin": {"$geometry": polygon}}}
{"field": {"$geoIntersects": {"$geometry": geometry}}}

# Text search
{"$text": {"$search": "query", "$language": "en"}}
```

### Custom Operator Implementation

You can extend the compilation system with custom operators:

#### SQLAlchemy Custom Operator

```python
from cqrs_ddd_persistence_sqlalchemy.specifications.strategy import (
    SQLAlchemyOperatorRegistry,
    SQLAlchemyOperatorStrategy,
)
from cqrs_ddd_specifications.operators import SpecificationOperator
from sqlalchemy import ColumnElement

class MyCustomOperatorStrategy(SQLAlchemyOperatorStrategy):
    """Custom operator implementation."""
    
    def apply(
        self, 
        column: ColumnElement[Any], 
        value: Any
    ) -> ColumnElement[bool]:
        # Implement custom logic
        return column.op("@@")(value  # PostgreSQL text search vector

# Register custom operator
registry = SQLAlchemyOperatorRegistry()
registry.register(SpecificationOperator("fts_match"), MyCustomOperatorStrategy())

# Use in compilation
filter_expr = build_sqla_filter(
    Model, 
    spec.to_dict(), 
    registry=registry
)
```

#### MongoDB Custom Operator

```python
from typing import Any

def compile_custom_operator(
    field: str, 
    op: str, 
    val: Any
) -> dict[str, Any] | None:
    """Custom MongoDB operator compiler."""
    if op == "my_custom_op":
        # Return MongoDB query fragment
        return {field: {"$expr": {...}}}
    return None

# Add to compilers list in query_builder.py
from cqrs_ddd_persistence_mongo import query_builder
query_builder._COMPILERS.append(compile_custom_operator)
```

### Performance Considerations

| Backend | Compilation Overhead | Index Usage | Optimization Tips |
|---------|---------------------|-------------|-------------------|
| **SQLAlchemy** | Medium (SQL generation) | Full index support | Use hooks for computed fields; avoid N+1 queries |
| **MongoDB** | Low (dict construction) | Full index support | Use covered queries; prefer `$eq` over `$regex` |
| **Memory** | Very low | N/A (full scan) | Only for small datasets; use for testing |

**Best Practices:**

1. **Use indexes**: Ensure fields used in specifications have proper indexes
2. **Limit results**: Always use `.limit()` for pagination
3. **Select fields**: Use `.only()` or projection to reduce data transfer
4. **Avoid complex OR**: Complex OR conditions can skip indexes
5. **Test with production data volume**: Ensure queries scale appropriately
---

## Summary

The CQRS-DDD Projections System provides a complete solution for building scalable, eventually consistent read models optimized for query performance.

### Key Takeaways

| Concept | Description |
|---------|-------------|
| **Separation of Concerns** | Domain logic in aggregates, query optimization in projections |
| **Eventual Consistency** | Projections updated asynchronously from domain events |
| **Performance** | Pre-computed joins, denormalized data, indexed for specific queries |
| **Flexibility** | Multiple projections from same events for different use cases |
| **Replayability** | Rebuild projections at any time by replaying events |

### Component Summary

| Component | Purpose | Key Features |
|-----------|---------|--------------|
| **IProjectionWriter** | Write projections | Upsert, batch operations, version control, idempotency |
| **IProjectionReader** | Read projections | Get, get_batch, find with pagination |
| **ProjectionSchema** | Define SQL schemas | Columns, indexes, relationships, DDL generation |
| **ProjectionWorker** | Process events | Position tracking, handler dispatch, catch-up mode |
| **ProjectionManager** | Initialize schemas | Distributed locking, dependency ordering |
| **ProjectionBackedPersistence** | Dispatcher integration | Typed DTOs, specifications, query patterns |
| **Specification Compiler** | Query compilation | Backend-specific query generation (SQL/MongoDB/Memory) |

### Backend Comparison

| Feature | SQLAlchemy | MongoDB | Memory |
|---------|-----------|---------|--------|
| **Use Case** | Relational DBs | Document DBs | Testing/Prototyping |
| **Transaction Support** | Full ACID | Replica Set Required | N/A |
| **Schema Management** | DDL + Migrations | Schema-less | N/A |
| **Specification Compilation** | Manual or Hooks | Automatic | Automatic |
| **Performance** | High (SQL) | Very High (Native) | Low (Full scan) |
| **Scalability** | Vertical + Read Replicas | Horizontal Sharding | N/A |

### Architecture Principles

1. **Denormalize for Read Performance**
   - Include all data needed for display in projections
   - Avoid joins in read queries
   - Pre-compute aggregations and counts

2. **Event Sourcing Compatibility**
   - Projections can be rebuilt from event history
   - Version control prevents duplicate processing
   - Idempotent handlers handle replay gracefully

3. **Specification-Driven Queries**
   - Use `cqrs_ddd_specifications` for type-safe queries
   - Backend compilers translate to optimal queries
   - Hooks enable custom field resolution

4. **Operational Resilience**
   - Position tracking enables resume after failures
   - Distributed locking prevents duplicate initialization
   - Catch-up mode for new projections

### Quick Reference

```python
# 1. Define projection DTO
@dataclass
class OrderSummaryDTO:
    id: str
    customer_name: str
    total: Decimal
    status: str

# 2. Create event handler
class OrderHandler:
    def __init__(self, writer: IProjectionWriter):
        self.writer = writer
    
    async def handle(self, event: StoredEvent, uow: UnitOfWork):
        await self.writer.upsert(
            "order_summaries",
            event.order_id,
            {...},
            event_position=event.position,
            event_id=event.id,
            uow=uow,
        )

# 3. Create query persistence
class OrderQuery(SQLAlchemyProjectionDualPersistence[OrderSummaryDTO, str]):
    collection = "order_summaries"
    
    def to_dto(self, doc: dict) -> OrderSummaryDTO:
        return OrderSummaryDTO(**doc)

# 4. Register with dispatcher
registry.register_query(OrderSummaryDTO, OrderQuery)
registry.register_query_spec(OrderSummaryDTO, OrderQuery)

# 5. Use in query handlers
from cqrs_ddd_specifications import SpecificationBuilder, QueryOptions

spec = (
    SpecificationBuilder()
    .where("customer_id", "=", "123")
    .where("status", "=", "active")
    .build()
)
options = QueryOptions().with_specification(spec)
result = await dispatcher.fetch(OrderSummaryDTO, options, uow=uow)
orders = await result
```

### Next Steps

- **For SQLAlchemy Users**: Review SQLAlchemy hooks for complex field resolution
- **For MongoDB Users**: Ensure replica set is configured for transactions
- **For Testing**: Use in-memory projections with MemoryEvaluator
- **For Production**: Set up distributed locking and monitoring
- **For Advanced Queries**: Explore custom operators and specification extensions

### Further Reading

- **Event Sourcing**: See `packages/advanced/src/cqrs_ddd_advanced_core/event_sourcing/README.md`
- **Specifications**: See `packages/specifications/README.md`
- **Persistence**: See `packages/persistence/sqlalchemy/README.md` and `packages/persistence/mongo/README.md`
- **Dispatcher**: See `packages/advanced/src/cqrs_ddd_advanced_core/persistence/README.md`

---

**Version**: 1.0.0  
**Last Updated**: February 2026  
**Maintainers**: CQRS-DDD Toolkit Team
