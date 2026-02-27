# SQLAlchemy Advanced Persistence

**Production-ready implementations for sagas, projections, snapshots, and background jobs.**

---

## Overview

The `advanced` package provides **specialized persistence patterns** for complex CQRS/DDD scenarios, building on top of the core repository and event store implementations.

**Key Features:**
- ✅ **Saga Persistence** - State machine storage with step history and timeout handling
- ✅ **Projection Store** - Materialized views with version control and idempotency
- ✅ **Snapshot Store** - Aggregate state optimization for long event histories
- ✅ **Background Jobs** - Reliable job queue with retry logic and progress tracking
- ✅ **Position Tracking** - Cursor-based projection position management

**Dependencies:**
- `cqrs-ddd-advanced-core` - Saga, projection, and background job primitives
- `cqrs-ddd-persistence-sqlalchemy[core]` - Base repository and UoW implementations

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    APPLICATION LAYER                         │
│                                                              │
│  Saga Orchestrator / Projection Builder / Job Scheduler      │
│       ↓                                                      │
│  async with uow:                                             │
│      await saga_repo.save(saga_state, uow=uow)             │
│      await projection_store.upsert(doc, uow=uow)            │
│      await job_repo.add(job, uow=uow)                       │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                  ADVANCED PERSISTENCE                        │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  SQLAlchemySagaRepository                             │  │
│  │  - State machine persistence                          │  │
│  │  - Correlation ID lookup                              │  │
│  │  - Stalled/suspended saga detection                   │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  SQLAlchemyProjectionStore                            │  │
│  │  - Materialized view storage                          │  │
│  │  - Version-based concurrency                          │  │
│  │  - Idempotent event processing                        │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  SQLAlchemySnapshotStore                              │  │
│  │  - Aggregate state snapshots                          │  │
│  │  - Performance optimization                           │  │
│  │  - Automatic versioning                               │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  SQLAlchemyBackgroundJobRepository                    │  │
│  │  - Job queue persistence                              │  │
│  │  - Stale job detection                                │  │
│  │  - Progress tracking                                  │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  SQLAlchemyProjectionPositionStore                    │  │
│  │  - Cursor-based positioning                           │  │
│  │  - Multi-projection support                           │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    DATABASE (PostgreSQL/SQLite)              │
│                                                              │
│  Tables: sagas, projections*, snapshots, jobs, positions    │
└─────────────────────────────────────────────────────────────┘
```

---

## Components

### 1. `SQLAlchemySagaRepository` - Saga State Persistence

**Purpose:** Persists saga state machines with step history and timeout tracking.

**Key Features:**
- State machine status (RUNNING, SUSPENDED, COMPLETED, CANCELLED)
- Step history stored as JSON events
- Correlation ID lookup for saga instances
- Stalled and suspended saga detection
- Automatic timeout handling

**Usage:**

```python
from cqrs_ddd_persistence_sqlalchemy.advanced import SQLAlchemySagaRepository
from cqrs_ddd_advanced_core.sagas.state import SagaState, SagaStatus
from cqrs_ddd_advanced_core.sagas.decorators import saga_step

# Domain saga definition
class OrderFulfillmentSaga(SagaState):
    order_id: str
    payment_id: str | None = None
    shipment_id: str | None = None
    status: SagaStatus = SagaStatus.RUNNING

    @saga_step(compensation="cancel_payment")
    async def process_payment(self, payment_service):
        self.payment_id = await payment_service.charge(self.order_id)

    @saga_step(compensation="cancel_shipment")
    async def create_shipment(self, shipment_service):
        self.shipment_id = await shipment_service.ship(self.order_id)

    async def cancel_payment(self, payment_service):
        await payment_service.refund(self.payment_id)

    async def cancel_shipment(self, shipment_service):
        await shipment_service.cancel(self.shipment_id)

# Repository setup
saga_repo = SQLAlchemySagaRepository(
    saga_cls=OrderFulfillmentSaga,
    uow_factory=lambda: uow,
)

# Start new saga
async with SQLAlchemyUnitOfWork(session_factory) as uow:
    saga = OrderFulfillmentSaga(
        id="saga-123",
        order_id="order-456",
        correlation_id="order-456",
    )
    await saga_repo.add(saga, uow=uow)
    await uow.commit()

# Find saga by correlation ID
saga = await saga_repo.find_by_correlation_id(
    correlation_id="order-456",
    saga_type="OrderFulfillmentSaga",
)

# Detect stalled sagas (not updated in 5 minutes)
stalled = await saga_repo.find_stalled_sagas(limit=10)
for saga in stalled:
    logger.warning(f"Saga {saga.id} has stalled")

# Find suspended sagas waiting for external events
suspended = await saga_repo.find_suspended_sagas(limit=10)
for saga in suspended:
    # Check if external event arrived
    if await check_external_event(saga.correlation_id):
        saga.resume()
        await saga_repo.add(saga, uow=uow)
        await uow.commit()

# Find expired suspended sagas
expired = await saga_repo.find_expired_suspended_sagas(limit=10)
for saga in expired:
    # Compensate all completed steps
    await saga.compensate_all()
    saga.mark_as_cancelled("Timeout exceeded")
    await saga_repo.add(saga, uow=uow)
    await uow.commit()
```

**Custom Model Mapping:**

```python
class SQLAlchemySagaRepository(SQLAlchemyRepository[SagaState, str], ISagaRepository):
    def to_model(self, entity: SagaState) -> SagaStateModel:
        """Custom mapping with step history."""
        model = super().to_model(entity)

        # Map step_history to events JSON column
        model.events = [s.model_dump(mode="json") for s in entity.step_history]

        # Store full state (excluding history) in state JSON column
        model.state = entity.model_dump(mode="json", exclude={"step_history"})

        return model

    def from_model(self, model: SagaStateModel) -> SagaState:
        """Reconstruct saga with history."""
        data = model.state.copy() if model.state else {}

        # Override with column values
        data["id"] = model.id
        data["correlation_id"] = model.correlation_id
        data["status"] = DomainSagaStatus(model.status.value)
        data["step_history"] = model.events  # Restore history

        return self._saga_domain_cls(**data)
```

---

### 2. `SQLAlchemyProjectionStore` - Materialized Views

**Purpose:** Stores projection documents with version-based concurrency control.

**Key Features:**
- SQL injection protection via identifier validation
- Version-based optimistic locking
- Idempotent event processing via `_last_event_id`
- Composite primary key support
- Efficient batch upserts
- Auto-DDL for development (disabled in production)

**Usage:**

```python
from cqrs_ddd_persistence_sqlalchemy.advanced import SQLAlchemyProjectionStore
from cqrs_ddd_advanced_core.projections.schema import ProjectionSchema

# Define projection schema
order_summary_schema = ProjectionSchema(
    collection="order_summaries",
    fields=[
        ("order_id", "VARCHAR(50) PRIMARY KEY"),
        ("customer_name", "VARCHAR(200)"),
        ("total_amount", "DECIMAL(10, 2)"),
        ("item_count", "INTEGER"),
        ("status", "VARCHAR(50)"),
        ("created_at", "TIMESTAMP"),
        ("_version", "INTEGER DEFAULT 1"),
        ("_last_event_id", "VARCHAR(100)"),
    ],
)

# Setup projection store
projection_store = SQLAlchemyProjectionStore(
    session_factory=session_factory,
    allow_auto_ddl=False,  # Use migrations in production
    default_id_column="order_id",
)

# Create collection (dev only, use migrations in prod)
await projection_store.ensure_collection(
    "order_summaries",
    schema=order_summary_schema,
)

# Upsert projection
projection_store = SQLAlchemyProjectionStore(session_factory=session_factory)

async with SQLAlchemyUnitOfWork(session_factory) as uow:
    doc = {
        "order_id": "order-123",
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

# Batch upsert (efficient)
async with SQLAlchemyUnitOfWork(session_factory) as uow:
    docs = [
        {"order_id": f"order-{i}", "customer_name": f"Customer {i}", ...}
        for i in range(100)
    ]
    await projection_store.bulk_upsert(
        collection="order_summaries",
        docs=docs,
        doc_id_field="order_id",
        uow=uow,
    )
    await uow.commit()

# Idempotent event processing
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
        "order_id": event.order_id,
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

**SQL Injection Protection:**

```python
# ✅ SAFE: Validated identifiers
await projection_store.find_one(
    collection="order_summaries",  # Validated
    doc_id="order-123",
)

# ❌ BLOCKED: SQL injection attempt
await projection_store.find_one(
    collection="order_summaries; DROP TABLE users; --",  # Raises ValueError
    doc_id="order-123",
)
# ValueError: Invalid SQL table name: 'order_summaries; DROP TABLE users; --'
```

**Version-Based Concurrency:**

```python
async def update_projection(order_id: str, new_status: str):
    """Update with optimistic locking."""
    async with SQLAlchemyUnitOfWork(session_factory) as uow:
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

---

### 3. `SQLAlchemySnapshotStore` - Aggregate Snapshots

**Purpose:** Optimizes aggregate reconstitution by storing periodic snapshots.

**Key Features:**
- Reduces event replay overhead
- Automatic versioning
- Snapshot deletion and cleanup
- Type-safe snapshot data

**Usage:**

```python
from cqrs_ddd_persistence_sqlalchemy.advanced import SQLAlchemySnapshotStore

snapshot_store = SQLAlchemySnapshotStore(uow_factory=lambda: uow)

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
    aggregates = await repo.find_not_updated_since(
        threshold=datetime.now(timezone.utc) - timedelta(hours=24)
    )

    for aggregate in aggregates:
        await snapshot_store.save_snapshot(
            aggregate_type=type(aggregate).__name__,
            aggregate_id=aggregate.id,
            snapshot_data=aggregate.model_dump(),
            version=aggregate.version,
        )
```

---

### 4. `SQLAlchemyBackgroundJobRepository` - Job Queue

**Purpose:** Persists background jobs with status tracking and retry logic.

**Key Features:**
- Job status tracking (PENDING, RUNNING, COMPLETED, CANCELLED, FAILED)
- Progress tracking (processed_items / total_items)
- Stale job detection (timeout handling)
- Automatic retry with max_retries
- Correlation ID for tracing

**Usage:**

```python
from cqrs_ddd_persistence_sqlalchemy.advanced import SQLAlchemyBackgroundJobRepository
from cqrs_ddd_advanced_core.background_jobs.entity import BaseBackgroundJob

# Domain job definition
class EmailBatchJob(BaseBackgroundJob):
    email_ids: list[str]
    template_id: str

    async def execute(self, email_service):
        """Send batch emails."""
        for i, email_id in enumerate(self.email_ids):
            await email_service.send(email_id, self.template_id)
            self.processed_items = i + 1  # Update progress

# Repository setup
job_repo = SQLAlchemyBackgroundJobRepository(
    job_cls=EmailBatchJob,
    stale_job_timeout_seconds=3600,  # 1 hour
)

# Create job
async with SQLAlchemyUnitOfWork(session_factory) as uow:
    job = EmailBatchJob(
        id="job-123",
        email_ids=["email-1", "email-2", "email-3"],
        template_id="welcome-email",
        total_items=3,
    )
    await job_repo.add(job, uow=uow)
    await uow.commit()

# Job worker
async def job_worker():
    """Background worker processing jobs."""
    while True:
        async with SQLAlchemyUnitOfWork(session_factory) as uow:
            # Get pending jobs
            jobs = await job_repo.find_by_status(
                status=JobStatus.PENDING,
                limit=10,
                uow=uow,
            )

            for job in jobs:
                try:
                    job.mark_as_running()
                    await job_repo.add(job, uow=uow)
                    await uow.commit()

                    # Execute job
                    await job.execute(email_service)

                    # Mark as completed
                    job.mark_as_completed()
                    await job_repo.add(job, uow=uow)
                    await uow.commit()

                except Exception as e:
                    # Handle failure
                    if job.retry_count < job.max_retries:
                        job.mark_for_retry()
                    else:
                        job.mark_as_failed(str(e))

                    await job_repo.add(job, uow=uow)
                    await uow.commit()

        await asyncio.sleep(1)

# Detect stale jobs
stale_jobs = await job_repo.get_stale_jobs(timeout_seconds=3600, uow=uow)
for job in stale_jobs:
    logger.warning(f"Job {job.id} has stalled, marking as failed")
    job.mark_as_failed("Job stalled")
    await job_repo.add(job, uow=uow)
    await uow.commit()
```

**Progress Tracking:**

```python
# Query job progress
job = await job_repo.get("job-123", uow=uow)
progress_percent = (job.processed_items / job.total_items) * 100
print(f"Job progress: {progress_percent:.1f}%")
```

---

### 5. `SQLAlchemyProjectionPositionStore` - Cursor Tracking

**Purpose:** Tracks the position of projections in the event stream.

**Key Features:**
- Cursor-based positioning for projections
- Multi-projection support
- Atomic position updates
- Simple key-value store

**Usage:**

```python
from cqrs_ddd_persistence_sqlalchemy.advanced import SQLAlchemyProjectionPositionStore

position_store = SQLAlchemyProjectionPositionStore(
    session_factory=session_factory,
    table_name="projection_positions",
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

---

## Integration Patterns

### Pattern 1: Saga with Compensation

```python
async def fulfill_order(order_id: str):
    """Saga with automatic compensation on failure."""
    async with SQLAlchemyUnitOfWork(session_factory) as uow:
        # Load or create saga
        saga = await saga_repo.find_by_correlation_id(
            correlation_id=order_id,
            saga_type="OrderFulfillmentSaga",
        )

        if not saga:
            saga = OrderFulfillmentSaga(
                id=str(uuid4()),
                order_id=order_id,
                correlation_id=order_id,
            )

        try:
            # Execute steps
            if not saga.payment_id:
                await saga.process_payment(payment_service)

            if not saga.shipment_id:
                await saga.create_shipment(shipment_service)

            # Mark as completed
            saga.mark_as_completed()

        except Exception as e:
            # Compensate on failure
            await saga.compensate_all()
            saga.mark_as_cancelled(str(e))

        await saga_repo.add(saga, uow=uow)
        await uow.commit()
```

### Pattern 2: Projection Builder with Idempotency

```python
async def build_order_summary_projection(event: OrderCreated):
    """Event handler building projection with idempotency."""
    async with SQLAlchemyUnitOfWork(session_factory) as uow:
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
            "order_id": event.order_id,
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

### Pattern 3: Background Job with Progress

```python
async def process_large_file(file_id: str):
    """Background job with progress tracking."""
    # Create job
    job = FileProcessingJob(
        id=str(uuid4()),
        file_id=file_id,
        total_items=await count_lines(file_id),
    )

    async with SQLAlchemyUnitOfWork(session_factory) as uow:
        await job_repo.add(job, uow=uow)
        await uow.commit()

    # Process file (separate transaction per chunk)
    async for chunk in read_file_chunks(file_id, chunk_size=100):
        async with SQLAlchemyUnitOfWork(session_factory) as uow:
            # Reload job
            job = await job_repo.get(job.id, uow=uow)

            # Process chunk
            for line in chunk:
                await process_line(line)
                job.processed_items += 1

            # Update progress
            await job_repo.add(job, uow=uow)
            await uow.commit()

    # Mark as completed
    async with SQLAlchemyUnitOfWork(session_factory) as uow:
        job = await job_repo.get(job.id, uow=uow)
        job.mark_as_completed()
        await job_repo.add(job, uow=uow)
        await uow.commit()
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

# ✅ FAST: Batch upsert
await projection_store.bulk_upsert(collection, docs, "order_id", uow=uow)
```

### 3. Position Tracking

```python
# ❌ SLOW: Update position per event
for event in events:
    await update_projection(event)
    await position_store.save_position(...)

# ✅ FAST: Batch position update
for event in events:
    await update_projection(event)

await position_store.save_position(
    projection_name="OrderSummary",
    position=events[-1].position,
)
```

---

## Error Handling

### Saga Timeout

```python
from cqrs_ddd_persistence_sqlalchemy.exceptions import OptimisticConcurrencyError

async def handle_saga_timeout():
    """Handle expired suspended sagas."""
    expired = await saga_repo.find_expired_suspended_sagas(limit=10)

    for saga in expired:
        async with SQLAlchemyUnitOfWork(session_factory) as uow:
            try:
                # Compensate all completed steps
                await saga.compensate_all()
                saga.mark_as_cancelled("Timeout exceeded")

                await saga_repo.add(saga, uow=uow)
                await uow.commit()

            except OptimisticConcurrencyError:
                # Saga was updated by another process
                logger.info(f"Saga {saga.id} already handled")
```

### Projection Version Conflict

```python
async def update_with_retry(order_id: str, new_status: str, max_retries: int = 3):
    """Retry on version conflict."""
    for attempt in range(max_retries):
        async with SQLAlchemyUnitOfWork(session_factory) as uow:
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

            except OptimisticConcurrencyError:
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(0.1 * (2 ** attempt))  # Exponential backoff
```

---

## Summary

| Component | Purpose | Key Features |
|-----------|---------|--------------|
| `SQLAlchemySagaRepository` | Saga state persistence | Step history, timeout detection, correlation IDs |
| `SQLAlchemyProjectionStore` | Materialized views | Version control, idempotency, SQL injection protection |
| `SQLAlchemySnapshotStore` | Aggregate snapshots | Performance optimization, automatic versioning |
| `SQLAlchemyBackgroundJobRepository` | Job queue | Progress tracking, retry logic, stale detection |
| `SQLAlchemyProjectionPositionStore` | Cursor tracking | Multi-projection support, atomic updates |

**Total Lines:** ~1200
**Dependencies:** SQLAlchemy 2.0+, cqrs-ddd-advanced-core, cqrs-ddd-persistence-sqlalchemy[core]
**Python Version:** 3.11+
