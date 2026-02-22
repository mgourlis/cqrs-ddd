# MongoDB Advanced Persistence

**Production-ready implementations for projections and snapshots with MongoDB.**

---

## Overview

The `advanced` package provides **specialized persistence patterns** for complex CQRS/DDD scenarios using MongoDB's native features.

**Key Features:**
- ✅ **Projection Store** - Materialized views with version control and idempotency
- ✅ **Snapshot Store** - Aggregate state optimization for long event histories
- ✅ **Position Tracking** - Cursor-based projection position management
- ✅ **Flexible ID Mapping** - Support for custom ID fields

**Dependencies:**
- `cqrs-ddd-advanced-core` - Projection and snapshot primitives
- `cqrs-ddd-persistence-mongo[core]` - Base repository and UoW implementations

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    APPLICATION LAYER                         │
│                                                              │
│  Projection Builder / Event Handlers                         │
│       ↓                                                      │
│  async with uow:                                             │
│      await projection_store.upsert(doc, uow=uow)            │
│      await snapshot_store.save_snapshot(agg, uow=uow)       │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                  ADVANCED PERSISTENCE                        │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  MongoProjectionStore                                 │  │
│  │  - Materialized view storage                          │  │
│  │  - Version-based concurrency                          │  │
│  │  - Idempotent event processing                        │  │
│  │  - Efficient bulk upserts                             │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  MongoSnapshotStore                                   │  │
│  │  - Aggregate state snapshots                          │  │
│  │  - Performance optimization                           │  │
│  │  - Automatic versioning                               │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  MongoProjectionPositionStore                         │  │
│  │  - Cursor-based positioning                           │  │
│  │  - Multi-projection support                           │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    MONGODB DATABASE                          │
│                                                              │
│  Collections: projections*, snapshots, positions            │
└─────────────────────────────────────────────────────────────┘
```

---

## Components

### 1. `MongoProjectionStore` - Materialized Views

**Purpose:** Stores projection documents with version-based concurrency control.

**Key Features:**
- Version-based optimistic locking
- Idempotent event processing via `_last_event_id`
- Efficient bulk upserts using `bulk_write`
- Flexible ID field mapping
- Support for composite primary keys

**Usage:**

```python
from cqrs_ddd_persistence_mongo.advanced import MongoProjectionStore
from cqrs_ddd_persistence_mongo.connection import MongoConnectionManager

# Setup projection store
projection_store = MongoProjectionStore(
    connection=connection,
    database="myapp",
    id_field="id",  # Custom ID field (maps to _id in MongoDB)
)

# Upsert projection
async with MongoUnitOfWork(connection=connection) as uow:
    doc = {
        "id": "order-123",
        "customer_name": "John Doe",
        "total_amount": 99.99,
        "item_count": 3,
        "status": "pending",
        "created_at": datetime.now(timezone.utc),
        "_version": 1,
        "_last_event_id": "event-456",
    }
    
    await projection_store.upsert(
        collection="order_summaries",
        doc_id="order-123",
        doc=doc,
        uow=uow,
    )
    await uow.commit()

# Read projection
projection = await projection_store.find_one(
    collection="order_summaries",
    doc_id="order-123",
)
assert projection["customer_name"] == "John Doe"

# Query projections
projections = await projection_store.find(
    collection="order_summaries",
    filter={"status": "pending"},
    sort=[("created_at", -1)],
    limit=10,
)

# Bulk upsert (efficient)
async with MongoUnitOfWork(connection=connection) as uow:
    docs = [
        {"id": f"order-{i}", "customer_name": f"Customer {i}", ...}
        for i in range(100)
    ]
    await projection_store.bulk_upsert(
        collection="order_summaries",
        docs=docs,
        id_field="id",
        uow=uow,
    )
    await uow.commit()

# Delete projection
await projection_store.delete(
    collection="order_summaries",
    doc_id="order-123",
)
```

**Idempotent Event Processing:**

```python
async def handle_order_created(event: OrderCreated):
    """Event handler with idempotency check."""
    # Check if event already processed
    existing = await projection_store.find_one(
        collection="order_summaries",
        doc_id=event.order_id,
    )
    
    if existing and existing.get("_last_event_id") == event.event_id:
        logger.info(f"Event {event.event_id} already processed, skipping")
        return
    
    # Upsert projection
    doc = {
        "id": event.order_id,
        "customer_name": event.customer_name,
        "_version": (existing.get("_version", 0) + 1) if existing else 1,
        "_last_event_id": event.event_id,
    }
    
    await projection_store.upsert(
        collection="order_summaries",
        doc_id=event.order_id,
        doc=doc,
        uow=uow,
    )
```

**Version-Based Concurrency:**

```python
async def update_projection(order_id: str, new_status: str):
    """Update with optimistic locking."""
    async with MongoUnitOfWork(connection=connection) as uow:
        # Load current version
        projection = await projection_store.find_one(
            collection="order_summaries",
            doc_id=order_id,
            uow=uow,
        )
        
        if not projection:
            raise ValueError(f"Order {order_id} not found")
        
        # Update with version check
        updated_doc = {
            **projection,
            "status": new_status,
            "_version": projection["_version"] + 1,
        }
        
        await projection_store.upsert(
            collection="order_summaries",
            doc_id=order_id,
            doc=updated_doc,
            expected_version=projection["_version"],  # Optimistic lock
            uow=uow,
        )
        await uow.commit()
```

**Composite Primary Keys:**

```python
# Projection with composite key
doc = {
    "customer_id": "cust-123",
    "product_id": "prod-456",
    "purchase_date": "2024-01-01",
    "quantity": 5,
    "_version": 1,
}

# Upsert with composite key
await projection_store.upsert(
    collection="customer_purchases",
    doc_id={
        "customer_id": "cust-123",
        "product_id": "prod-456",
    },
    doc=doc,
)
```

**MongoDB Query Support:**

```python
# Complex queries with MongoDB operators
projections = await projection_store.find(
    collection="order_summaries",
    filter={
        "status": {"$in": ["pending", "processing"]},
        "total_amount": {"$gte": 100},
        "created_at": {"$gte": datetime.now(timezone.utc) - timedelta(days=7)},
    },
    sort=[("total_amount", -1), ("created_at", -1)],
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

results = await projection_store.aggregate(
    collection="order_summaries",
    pipeline=pipeline,
)
```

---

### 2. `MongoSnapshotStore` - Aggregate Snapshots

**Purpose:** Optimizes aggregate reconstitution by storing periodic snapshots.

**Key Features:**
- Reduces event replay overhead
- Automatic versioning
- Snapshot deletion and cleanup
- Type-safe snapshot data
- Fast lookups with indexes

**Usage:**

```python
from cqrs_ddd_persistence_mongo.advanced import MongoSnapshotStore

snapshot_store = MongoSnapshotStore(
    connection=connection,
    database="myapp",
)

# Save snapshot after N events
async def reconstitute_order(order_id: str, event_store):
    """Reconstitute order with snapshot optimization."""
    # Try to load latest snapshot
    snapshot = await snapshot_store.get_latest_snapshot(
        aggregate_type="Order",
        aggregate_id=order_id,
    )
    
    if snapshot:
        # Start from snapshot
        order = Order(**snapshot["snapshot_data"])
        version = snapshot["version"]
        logger.info(f"Loaded snapshot at version {version}")
    else:
        # Start from beginning
        order = Order(id=order_id)
        version = 0
        logger.info("No snapshot found, starting from scratch")
    
    # Replay only events after snapshot
    events = await event_store.get_events(order_id, after_version=version)
    
    for event in events:
        order.apply(event)
    
    # Save snapshot every 50 events
    if len(events) >= 50:
        await snapshot_store.save_snapshot(
            aggregate_type="Order",
            aggregate_id=order_id,
            snapshot_data=order.model_dump(),
            version=order.version,
        )
        logger.info(f"Saved snapshot at version {order.version}")
    
    return order

# Delete snapshots (cleanup)
await snapshot_store.delete_snapshot(
    aggregate_type="Order",
    aggregate_id="order-123",
)
```

**Snapshot Strategy:**

```python
# Strategy 1: Event count threshold
SNAPSHOT_THRESHOLD = 50

async def maybe_snapshot(aggregate: AggregateRoot):
    """Save snapshot if threshold exceeded."""
    if aggregate.version % SNAPSHOT_THRESHOLD == 0:
        await snapshot_store.save_snapshot(
            aggregate_type=type(aggregate).__name__,
            aggregate_id=aggregate.id,
            snapshot_data=aggregate.model_dump(),
            version=aggregate.version,
        )

# Strategy 2: Time-based snapshots
async def snapshot_old_aggregates():
    """Snapshot aggregates not updated in 24 hours."""
    threshold = datetime.now(timezone.utc) - timedelta(hours=24)
    
    # Query aggregates not updated recently
    pipeline = [
        {"$match": {
            "updated_at": {"$lt": threshold},
        }},
        {"$group": {
            "_id": "$aggregate_id",
            "latest_version": {"$max": "$version"},
        }},
    ]
    
    # For each aggregate, create snapshot
    async for doc in event_store.aggregate(pipeline):
        # Reconstitute and snapshot
        ...
```

**Snapshot Document Structure:**

```python
{
    "_id": ObjectId("..."),
    "aggregate_id": "order-123",
    "aggregate_type": "Order",
    "version": 50,
    "snapshot_data": {
        "id": "order-123",
        "customer_id": "cust-456",
        "total": 99.99,
        "status": "shipped",
        "items": [...],
    },
    "created_at": ISODate("2024-01-01T00:00:00Z"),
}

// Indexes for fast lookups
{
    "aggregate_id": 1,
    "aggregate_type": 1,
    "version": -1,
}
```

---

### 3. `MongoProjectionPositionStore` - Cursor Tracking

**Purpose:** Tracks the position of projections in the event stream.

**Key Features:**
- Cursor-based positioning for projections
- Multi-projection support
- Atomic position updates with `find_one_and_update`
- Simple key-value store pattern

**Usage:**

```python
from cqrs_ddd_persistence_mongo.advanced import MongoProjectionPositionStore

position_store = MongoProjectionPositionStore(
    connection=connection,
    database="myapp",
)

# Get current position
position = await position_store.get_position(
    projection_name="OrderSummaryProjection",
)
if position is None:
    position = 0

# Process events
events = await event_store.get_events_after(position, limit=1000)
for event in events:
    # Update projection
    await update_projection(event)
    
    # Update position
    await position_store.save_position(
        projection_name="OrderSummaryProjection",
        position=event.position,
        uow=uow,
    )

# Multiple projections
projections = ["OrderSummaryProjection", "CustomerStatsProjection"]
for proj_name in projections:
    position = await position_store.get_position(proj_name)
    # Process events for each projection
```

**Atomic Position Updates:**

```python
async def save_position(
    self,
    projection_name: str,
    position: int,
    *,
    uow: UnitOfWork | None = None,
) -> None:
    """
    Atomically update position using find_one_and_update.
    
    - Upsert: Creates document if not exists
    - Atomic: No race conditions
    - Fast: Single round-trip
    """
    collection = self._db()["projection_positions"]
    
    await collection.find_one_and_update(
        {"projection_name": projection_name},
        {"$set": {"position": position, "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
```

**Position Document Structure:**

```python
{
    "_id": ObjectId("..."),
    "projection_name": "OrderSummaryProjection",
    "position": 5000,
    "updated_at": ISODate("2024-01-01T00:00:00Z"),
}

// Index for fast lookups
{"projection_name": 1}  // Unique index
```

---

## Integration Patterns

### Pattern 1: Projection Builder with Idempotency

```python
async def build_order_summary_projection(event: OrderCreated):
    """Event handler building projection with idempotency."""
    async with MongoUnitOfWork(connection=connection) as uow:
        # Check idempotency
        existing = await projection_store.find_one(
            collection="order_summaries",
            doc_id=event.order_id,
            uow=uow,
        )
        
        if existing and existing.get("_last_event_id") == event.event_id:
            logger.info(f"Event {event.event_id} already processed")
            return
        
        # Build projection
        doc = {
            "id": event.order_id,
            "customer_name": event.customer_name,
            "total_amount": event.total,
            "item_count": len(event.items),
            "status": event.status,
            "created_at": event.occurred_at,
            "_version": (existing["_version"] + 1) if existing else 1,
            "_last_event_id": event.event_id,
        }
        
        await projection_store.upsert(
            collection="order_summaries",
            doc_id=event.order_id,
            doc=doc,
            uow=uow,
        )
        
        await uow.commit()
```

### Pattern 2: Continuous Projection Builder

```python
async def continuous_projection_builder():
    """Background worker building projections continuously."""
    while True:
        try:
            # Get current position
            position = await position_store.get_position("OrderSummaryProjection")
            if position is None:
                position = 0
            
            # Get events after position
            events = await event_store.get_events_after(position, limit=100)
            
            if not events:
                await asyncio.sleep(1)
                continue
            
            # Process each event
            async with MongoUnitOfWork(connection=connection) as uow:
                for event in events:
                    await build_projection(event, uow=uow)
                
                # Update position after processing all events
                await position_store.save_position(
                    projection_name="OrderSummaryProjection",
                    position=events[-1].position,
                    uow=uow,
                )
                
                await uow.commit()
        
        except Exception as e:
            logger.error(f"Projection builder error: {e}")
            await asyncio.sleep(5)
```

### Pattern 3: Snapshot with Projection

```python
async def reconstitute_with_snapshot_and_projection(aggregate_id: str):
    """Reconstitute using both snapshots and projections."""
    # Try snapshot first (write model)
    snapshot = await snapshot_store.get_latest_snapshot(
        aggregate_type="Order",
        aggregate_id=aggregate_id,
    )
    
    if snapshot and snapshot["version"] >= 50:
        # Snapshot is recent enough
        order = Order(**snapshot["snapshot_data"])
        events = await event_store.get_events(
            aggregate_id,
            after_version=snapshot["version"],
        )
        for event in events:
            order.apply(event)
        return order
    
    # Fall back to projection (read model)
    projection = await projection_store.find_one(
        collection="order_summaries",
        doc_id=aggregate_id,
    )
    
    if projection:
        # Rebuild from projection (faster than full replay)
        order = Order(
            id=projection["id"],
            customer_id=projection["customer_id"],
            total=projection["total_amount"],
            status=projection["status"],
        )
        # May need to replay some events if projection is stale
        return order
    
    # Full replay (last resort)
    return await reconstitute_order(aggregate_id, event_store)
```

---

## Performance Considerations

### 1. Snapshot Frequency

```python
# ❌ TOO FREQUENT: Snapshot on every change
if aggregate.version % 1 == 0:
    await snapshot_store.save_snapshot(...)

# ✅ OPTIMAL: Snapshot every 50-100 events
if aggregate.version % 50 == 0:
    await snapshot_store.save_snapshot(...)
```

### 2. Projection Batch Updates

```python
# ❌ SLOW: Individual upserts
for doc in docs:
    await projection_store.upsert(collection, doc_id, doc, uow=uow)

# ✅ FAST: Bulk upsert
await projection_store.bulk_upsert(collection, docs, "id", uow=uow)
```

### 3. Position Tracking

```python
# ❌ SLOW: Update position per event
for event in events:
    await build_projection(event)
    await position_store.save_position(...)

# ✅ FAST: Batch position update
for event in events:
    await build_projection(event)

await position_store.save_position(
    projection_name="OrderSummary",
    position=events[-1].position,
)
```

### 4. Index Optimization

```python
from cqrs_ddd_persistence_mongo.indexes import ensure_indexes

# Create indexes for projections
await ensure_indexes(
    db["order_summaries"],
    [
        ("customer_id", 1),
        ("status", 1),
        ("created_at", -1),
        ("customer_id", 1, "status", 1),  # Compound index
    ],
)

// MongoDB indexes
{
    "customer_id": 1,
    "status": 1,
}
// Query: {"customer_id": "cust-123", "status": "pending"}
// Uses index efficiently
```

---

## Error Handling

### Version Conflict

```python
from pymongo.errors import DuplicateKeyError

async def update_with_retry(order_id: str, new_status: str, max_retries: int = 3):
    """Retry on version conflict."""
    for attempt in range(max_retries):
        async with MongoUnitOfWork(connection=connection) as uow:
            try:
                projection = await projection_store.find_one(
                    collection="order_summaries",
                    doc_id=order_id,
                    uow=uow,
                )
                
                updated_doc = {
                    **projection,
                    "status": new_status,
                    "_version": projection["_version"] + 1,
                }
                
                await projection_store.upsert(
                    collection="order_summaries",
                    doc_id=order_id,
                    doc=updated_doc,
                    expected_version=projection["_version"],
                    uow=uow,
                )
                
                await uow.commit()
                return
                
            except DuplicateKeyError:
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(0.1 * (2 ** attempt))  # Exponential backoff
```

### Projection Builder Errors

```python
async def safe_build_projection(event: StoredEvent):
    """Projection builder with error handling."""
    try:
        await build_order_summary_projection(event)
    except Exception as e:
        logger.error(
            f"Failed to build projection for event {event.event_id}: {e}",
            extra={
                "event_id": event.event_id,
                "event_type": event.event_type,
                "aggregate_id": event.aggregate_id,
            },
        )
        # Don't block other events
        # Could store in dead-letter queue
        raise
```

---

## Summary

| Component | Purpose | Key Features |
|-----------|---------|--------------|
| `MongoProjectionStore` | Materialized views | Version control, idempotency, bulk upserts |
| `MongoSnapshotStore` | Aggregate snapshots | Performance optimization, automatic versioning |
| `MongoProjectionPositionStore` | Cursor tracking | Multi-projection support, atomic updates |

**Total Lines:** ~700  
**Dependencies:** Motor 3.0+, pymongo 4.0+, cqrs-ddd-advanced-core, cqrs-ddd-persistence-mongo[core]  
**Python Version:** 3.11+  
**MongoDB Version:** 4.0+
