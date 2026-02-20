# cqrs-ddd-projections

**Write-to-read synchronisation engine** for the CQRS-DDD Toolkit.

Consumes domain events — from an **event store** (poll-based worker) or from **message brokers** (RabbitMQ, Kafka, SQS via `IMessageConsumer`) — applies projection handlers to build read models, and checkpoints progress so processing can resume after crashes.

```
pip install cqrs-ddd-projections
```

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Core Concepts](#core-concepts)
  - [Projection Handlers](#projection-handlers)
  - [Projection Registry](#projection-registry)
  - [Checkpoint Store](#checkpoint-store)
  - [Error Policy](#error-policy)
- [Event Sources](#event-sources)
  - [Poll-Based Worker (ProjectionWorker)](#poll-based-worker-projectionworker)
  - [Broker-Based Sink (EventSinkRunner)](#broker-based-sink-eventsinkrunner)
- [Replay Engine](#replay-engine)
- [Partitioned Processing](#partitioned-processing)
- [Integration with the Toolkit](#integration-with-the-toolkit)
  - [Relationship to IRepository](#relationship-to-irepository)
  - [Relationship to PersistenceDispatcher](#relationship-to-persistencedispatcher)
  - [Multiple Sources Flow (PersistenceHandlerEntry)](#multiple-sources-flow-persistencehandlerentry)
  - [End-to-End Data Flow](#end-to-end-data-flow)
- [Configuration Reference](#configuration-reference)
- [Exception Hierarchy](#exception-hierarchy)
- [Public API](#public-api)

---

## Architecture Overview

In a CQRS architecture the **write side** persists aggregates and emits domain events; the **read side** maintains denormalised views (projections) optimised for queries. This package is the bridge between the two sides.

```
┌─────────────────── Write Side ────────────────────┐
│                                                    │
│  AggregateRoot ──► IRepository.add()               │
│       │                 │                          │
│       │   events        ▼                          │
│       └────────► IEventStore.append()              │
│                         │                          │
│                         ▼                          │
│              Outbox / Message Broker                │
└──────────────────────┬─────────────────────────────┘
                       │
            ┌──────────┴──────────┐
            │                     │
            ▼                     ▼
   ProjectionWorker        EventSinkRunner
   (polls IEventStore)    (IMessageConsumer)
            │                     │
            └──────────┬──────────┘
                       │
                       ▼
              ProjectionRegistry
              ┌────────┴────────┐
              │   get_handlers  │
              └───┬────┬────┬───┘
                  │    │    │
                  ▼    ▼    ▼
              Handler  Handler  Handler
              (update read models / DTOs)
                       │
                       ▼
              ICheckpointStore
              (save last position)
```

Both `ProjectionWorker` and `EventSinkRunner` implement `IBackgroundWorker` from core, giving a uniform `start()` / `stop()` lifecycle. The same `ProjectionRegistry`, handlers, and `ICheckpointStore` are shared regardless of which event source is used.

---

## Core Concepts

### Projection Handlers

A projection handler receives a single `DomainEvent` and updates one or more read models. The base `ProjectionHandler` keeps an internal mapping of `type[DomainEvent] -> async handler`, so complexity stays flat as event types grow.

**Protocol:**

```python
@runtime_checkable
class IProjectionHandler(Protocol):
    handles: set[type[DomainEvent]]

    async def handle(self, event: DomainEvent) -> None: ...
```

**Base class (convenience with event map):**

```python
from cqrs_ddd_projections import ProjectionHandler

class OrderSummaryProjection(ProjectionHandler):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.add_handler(OrderCreated, self._on_order_created)
        self.add_handler(OrderShipped, self._on_order_shipped)

    async def _on_order_created(self, event: OrderCreated) -> None:
        await self.db.insert({
            "order_id": event.aggregate_id,
            "status": "created",
            "total": event.total,
        })

    async def _on_order_shipped(self, event: OrderShipped) -> None:
        await self.db.update(
            {"order_id": event.aggregate_id},
            {"status": "shipped"},
        )
```

A single event type may be handled by **multiple** handlers — for example `OrderCreated` might update both an `OrderSummaryProjection` and a `RevenueReportProjection`.

### Projection Registry

`ProjectionRegistry` maps event type names (strings) to the list of handlers that should process them. Registration uses each handler instance's `handles` set (derived from its internal event map):

```python
from cqrs_ddd_projections import ProjectionRegistry

registry = ProjectionRegistry()
registry.register(OrderSummaryProjection())
registry.register(RevenueReportProjection())

# At runtime, for a stored event with event_type="OrderCreated":
handlers = registry.get_handlers("OrderCreated")
# → [OrderSummaryProjection, RevenueReportProjection]
```

Key behaviours:
- Multiple handlers per event type are supported (fan-out).
- `get_handlers()` returns an empty list for unrecognised event types (no error).
- Handlers are resolved by the **class name** of the event type in `handles`.

### Checkpoint Store

Checkpoints track the last-processed position per named projection, enabling crash recovery and idempotent restarts.

**Protocol:**

```python
@runtime_checkable
class ICheckpointStore(Protocol):
    async def get_position(self, projection_name: str) -> int | None: ...
    async def save_position(self, projection_name: str, position: int) -> None: ...
```

**Built-in implementation — `InMemoryCheckpointStore` (testing):**

```python
from cqrs_ddd_projections import InMemoryCheckpointStore

checkpoint = InMemoryCheckpointStore()

await checkpoint.save_position("order_summary", 42)
pos = await checkpoint.get_position("order_summary")  # → 42
pos = await checkpoint.get_position("unknown")         # → None

checkpoint.clear()  # reset all positions
```

For production, implement `ICheckpointStore` backed by Redis, SQLAlchemy, or MongoDB. Persist the position durably so workers resume from the correct offset after restarts.

### Error Policy

`ProjectionErrorPolicy` defines how handler failures are treated on a per-event basis. Four strategies are available by default:

| Strategy | Behaviour |
|---|---|
| `"skip"` (default) | Log the error and continue processing the next event. |
| `"retry"` | Re-raise to trigger the worker's retry loop (up to `max_retries` attempts). |
| `"dead_letter"` | Invoke a callback with the failed event and error, then re-raise. |
| `"retry_then_dead_letter"` | Retry while `attempt < max_retries`; once exhausted, invoke dead-letter callback (if provided) and re-raise. |

`ProjectionErrorPolicy` follows the **Open/Closed Principle**: built-in policies are registered as strategies, and you can add new policies through `register_policy()` without modifying `handle_failure()` or changing existing policy branches.

```python
from cqrs_ddd_projections import ProjectionErrorPolicy

# Skip failures silently (non-critical projections)
policy = ProjectionErrorPolicy(policy="skip")

# Retry up to 5 times before giving up
policy = ProjectionErrorPolicy(policy="retry", max_retries=5)

# Dead-letter: persist the failure for manual investigation
async def on_dead_letter(event, error):
    await dead_letter_store.save(event, error)

policy = ProjectionErrorPolicy(
    policy="dead_letter",
    dead_letter_callback=on_dead_letter,
)

# Retry first, then dead-letter on final failure
policy = ProjectionErrorPolicy(
    policy="retry_then_dead_letter",
    max_retries=5,
    dead_letter_callback=on_dead_letter,
)

# Add a custom policy without editing core policy logic
async def on_notify_and_skip(policy, event, error, attempt):
    await alerting.notify(event=event, error=error, attempt=attempt)
    # no raise -> worker continues

policy = ProjectionErrorPolicy(policy="notify_and_skip")
policy.register_policy("notify_and_skip", on_notify_and_skip)
```

When a handler raises an exception:

1. **skip** — `handle_failure()` returns immediately; the worker moves on.
2. **retry** — `handle_failure()` raises `ProjectionHandlerError` if `attempt < max_retries`, causing the worker's retry loop to re-attempt the event.
3. **dead_letter** — the callback is invoked (sync or async), then `ProjectionHandlerError` is raised.
4. **retry_then_dead_letter** — retry behavior applies first; after retries are exhausted, dead-letter callback is invoked (if configured), then `ProjectionHandlerError` is raised.

---

## Event Sources

### Poll-Based Worker (`ProjectionWorker`)

`ProjectionWorker` implements `IBackgroundWorker` and continuously polls `IEventStore` for new events after the last checkpoint. This is the simplest deployment model — no message broker required.

**Lifecycle:**

```
start()
  → load checkpoint (last processed position)
  → loop:
      → IEventStore.get_events_after(position, batch_size)
      → for each event: hydrate → dispatch to registry → error policy
      → save checkpoint (position + batch length)
      → sleep(poll_interval)
  → stop() → cancel task, exit
```

**Full example:**

```python
import asyncio
from cqrs_ddd_core.domain.events import DomainEvent
from cqrs_ddd_core.domain.event_registry import EventTypeRegistry
from cqrs_ddd_projections import (
    InMemoryCheckpointStore,
    ProjectionErrorPolicy,
    ProjectionHandler,
    ProjectionRegistry,
    ProjectionWorker,
)

# 1. Define domain events
class OrderCreated(DomainEvent):
    order_id: str = ""
    total: float = 0.0

class OrderShipped(DomainEvent):
    order_id: str = ""

# 2. Register event types for hydration
event_registry = EventTypeRegistry()
event_registry.register("OrderCreated", OrderCreated)
event_registry.register("OrderShipped", OrderShipped)

# 3. Define projection handler
class OrderSummaryProjection(ProjectionHandler):
    def __init__(self, read_db):
        super().__init__()
        self.read_db = read_db
        self.add_handler(OrderCreated, self._on_order_created)
        self.add_handler(OrderShipped, self._on_order_shipped)

    async def _on_order_created(self, event: OrderCreated) -> None:
        self.read_db[event.order_id] = {
            "status": "created",
            "total": event.total,
        }

    async def _on_order_shipped(self, event: OrderShipped) -> None:
        if event.order_id in self.read_db:
            self.read_db[event.order_id]["status"] = "shipped"

# 4. Wire up
read_db: dict = {}
projection_registry = ProjectionRegistry()
projection_registry.register(OrderSummaryProjection(read_db))

checkpoint_store = InMemoryCheckpointStore()

worker = ProjectionWorker(
    event_store=my_event_store,           # any IEventStore implementation
    projection_registry=projection_registry,
    checkpoint_store=checkpoint_store,
    projection_name="order_summary",
    event_registry=event_registry,
    batch_size=100,
    poll_interval_seconds=0.5,
    error_policy=ProjectionErrorPolicy(policy="retry", max_retries=3),
)

# 5. Run
await worker.start()
# ... application runs ...
await worker.stop()
```

**Key parameters:**

| Parameter | Default | Description |
|---|---|---|
| `projection_name` | `"default"` | Identifier used for checkpoint storage. Each distinct projection should have its own name. |
| `event_registry` | `None` | `EventTypeRegistry` instance for hydrating `StoredEvent` → `DomainEvent`. **Required** for handlers to receive typed events. |
| `batch_size` | `100` | Number of events fetched per poll cycle via `IEventStore.get_events_after()`. |
| `poll_interval_seconds` | `1.0` | Sleep duration between poll cycles when no new events are found. |
| `error_policy` | `skip` | `ProjectionErrorPolicy` instance controlling failure behaviour. |

### Broker-Based Sink (`EventSinkRunner`)

`EventSinkRunner` implements `IBackgroundWorker` and subscribes to a message broker topic via `IMessageConsumer`. This is the recommended production pattern for multi-service deployments where events are published to RabbitMQ, Kafka, or SQS through the outbox.

**Lifecycle:**

```
start()
  → restore offset from checkpoint
  → IMessageConsumer.subscribe(topic, on_message)
  → on each message:
      → extract event_type from payload or kwargs
      → hydrate via EventTypeRegistry
      → dispatch to ProjectionRegistry → handlers → error policy
      → increment offset → save checkpoint
  → stop() → save final checkpoint
```

**Full example:**

```python
from cqrs_ddd_projections import (
    EventSinkRunner,
    InMemoryCheckpointStore,
    ProjectionErrorPolicy,
    ProjectionRegistry,
)

projection_registry = ProjectionRegistry()
projection_registry.register(OrderSummaryProjection(read_db))

checkpoint_store = InMemoryCheckpointStore()

sink = EventSinkRunner(
    consumer=my_rabbitmq_consumer,        # any IMessageConsumer implementation
    projection_registry=projection_registry,
    checkpoint_store=checkpoint_store,
    projection_name="order_summary_sink",
    topic="domain.events",
    queue_name="projections.order_summary",
    event_registry=event_registry,
    error_policy=ProjectionErrorPolicy(policy="dead_letter", dead_letter_callback=on_dead_letter),
)

await sink.start()
# ... application runs, messages flow in from the broker ...
await sink.stop()
```

**Key parameters:**

| Parameter | Default | Description |
|---|---|---|
| `projection_name` | `"sink"` | Checkpoint identifier for this sink. |
| `topic` | `"events"` | Broker topic/exchange to subscribe to. |
| `queue_name` | `None` | Optional queue name (for RabbitMQ-style consumers). |
| `event_registry` | `None` | `EventTypeRegistry` for event hydration. |
| `error_policy` | `skip` | Failure strategy. |

**When to use which event source:**

| Source | Transport | Use case |
|---|---|---|
| `ProjectionWorker` | Polls `IEventStore` directly | Single-service deployments, no broker, testing, catch-up after outage |
| `EventSinkRunner` | Subscribes to `IMessageConsumer` | Multi-service, real-time, production with RabbitMQ/Kafka/SQS |

Both share the same `ProjectionRegistry`, handlers, and `ICheckpointStore`. You can run a `ProjectionWorker` alongside an `EventSinkRunner` to catch up on missed broker messages by reading directly from the event store.

---

## Replay Engine

`ReplayEngine` rebuilds a projection from the full event history. This is necessary when:

- A projection handler's logic changes and existing read models must be recomputed.
- A new projection is added and needs to process all historical events.
- Data corruption requires a clean rebuild.

**Lifecycle:**

```
replay("order_summary")
  → on_drop() — clear the read model (e.g. drop collection, truncate table)
  → reset checkpoint to from_position (default 0)
  → IEventStore.get_all_streaming(batch_size) — iterate all events in batches
  → for each event: hydrate → dispatch to handlers → error policy
  → save checkpoint after each batch
  → report progress via callback
```

**Full example:**

```python
from cqrs_ddd_projections import ReplayEngine, ProjectionErrorPolicy

replay = ReplayEngine(
    event_store=my_event_store,
    projection_registry=projection_registry,
    checkpoint_store=checkpoint_store,
    event_registry=event_registry,
    batch_size=500,
    error_policy=ProjectionErrorPolicy(policy="skip"),
)

# Drop existing read model and rebuild
async def drop_order_summary():
    await read_model_db.drop_collection("order_summary")

async def on_progress(processed: int, total: int, pct: float):
    print(f"Replayed {processed} events...")

await replay.replay(
    "order_summary",
    from_position=0,
    on_drop=drop_order_summary,
    progress_callback=on_progress,
)
```

**Key behaviours:**

- `on_drop` is called before replay begins. It can be sync or async. Use it to clear the target read model.
- `progress_callback(processed, total, pct)` is invoked after each event. Since total count is not known in advance during streaming, `total` is `-1`.
- Replay is **idempotent** — running it twice produces the same result (assuming handlers are idempotent).
- Uses `IEventStore.get_all_streaming()` for memory-efficient batch iteration.
- Checkpoints are saved after each batch, so a crashed replay can be resumed from the last completed batch.

---

## Partitioned Processing

`PartitionedProjectionWorker` enables horizontal scaling by distributing events across multiple worker instances. Each worker claims a partition via `ILockStrategy` and processes only events whose `aggregate_id` hashes to that partition.

```
                    Events from IEventStore
                            │
               ┌────────────┼────────────┐
               ▼            ▼            ▼
         Partition 0   Partition 1   Partition 2
         (Worker A)    (Worker B)    (Worker C)
               │            │            │
               ▼            ▼            ▼
         Handlers      Handlers      Handlers
```

**Partitioning algorithm:** `SHA-256(aggregate_id) % partition_count`. This ensures all events for a given aggregate are always processed by the same worker, preserving ordering guarantees.

**Example — 3 partitioned workers:**

```python
from cqrs_ddd_projections import PartitionedProjectionWorker

workers = []
for i in range(3):
    w = PartitionedProjectionWorker(
        event_store=my_event_store,
        projection_registry=projection_registry,
        checkpoint_store=checkpoint_store,
        lock_strategy=my_redis_lock,        # ILockStrategy (e.g. Redis-backed)
        partition_index=i,
        partition_count=3,
        projection_name="order_summary",
        event_registry=event_registry,
        batch_size=100,
        poll_interval_seconds=0.5,
    )
    workers.append(w)

# Start all workers
for w in workers:
    await w.start()

# On shutdown
for w in workers:
    await w.stop()
```

**Key behaviours:**

- Each worker acquires a distributed lock for its partition via `ILockStrategy.acquire()`.
- The internal `ProjectionWorker` is configured with a partition filter that skips events not belonging to the assigned partition.
- Each partition gets its own checkpoint name (`{projection_name}_p{partition_index}`).
- On worker failure, the lock expires and the partition can be claimed by another instance.

---

## Integration with the Toolkit

### Relationship to `IRepository`

`IRepository` (from `cqrs_ddd_core.ports.repository`) is the **write-side** interface for managing state-stored aggregates:

```python
@runtime_checkable
class IRepository(Protocol[T, ID]):
    async def add(self, entity: T, uow: UnitOfWork | None = None) -> ID: ...
    async def get(self, entity_id: ID, uow: UnitOfWork | None = None) -> T | None: ...
    async def delete(self, entity_id: ID, uow: UnitOfWork | None = None) -> ID: ...
    async def list_all(self, entity_ids: list[ID] | None = None, uow: UnitOfWork | None = None) -> list[T]: ...
    async def search(self, criteria: ISpecification[T] | Any, uow: UnitOfWork | None = None) -> SearchResult[T]: ...
```

The write-side flow is:

1. Application code calls `repo.add(order, uow)` to persist an aggregate.
2. The repository implementation stores the aggregate state **and** appends domain events to the event store (via `IEventStore`) within the same unit of work.
3. Events flow to the projection engine (via polling or broker).

**The projection engine sits on the opposite side of this boundary.** It reads from `IEventStore` (or a message broker that received events from the outbox) and updates **read models** — which are a completely different data shape from the aggregates managed by `IRepository`. A repository manages `AggregateRoot` entities; projections produce DTOs, summary tables, materialised views, or search indices.

```
Write Side                           Read Side
──────────                           ─────────
IRepository.add(Order)               ProjectionHandler.handle(OrderCreated)
  → IEventStore.append(OrderCreated)   → read_db.upsert(OrderSummaryDTO)
                                     ProjectionHandler.handle(OrderShipped)
                                       → read_db.update(OrderSummaryDTO)
```

### Relationship to `PersistenceDispatcher`

`PersistenceDispatcher` (from `cqrs_ddd_advanced_core.persistence.dispatcher`) is the **unified entry point** for both write and query operations in the advanced package. It routes:

- **Writes** via `dispatcher.apply(entity, uow, events)` → resolves an `IOperationPersistence` handler from the `PersistenceRegistry`.
- **Domain reads** via `dispatcher.fetch_domain(entity_type, ids)` → resolves an `IRetrievalPersistence` handler.
- **Query reads** via `dispatcher.fetch(result_type, criteria)` → resolves an `IQueryPersistence` or `IQuerySpecificationPersistence` handler. Returns a `SearchResult` that supports both `await` (for list) and `.stream()` (for async iteration).

The projection engine **feeds the read models** that `PersistenceDispatcher.fetch()` queries:

```
                ┌───────────────────────────────────────────┐
                │          PersistenceDispatcher             │
                │                                           │
                │  .apply(order)    .fetch(OrderDTO, spec)  │
                │       │                    │              │
                │       ▼                    ▼              │
                │  IOperationPersistence  IQueryPersistence  │
                │  (persist aggregate)   (query read model)  │
                └───────┬───────────────────┬───────────────┘
                        │                   ▲
                        ▼                   │ read models kept
                   IEventStore              │ in sync by projections
                        │                   │
                        ▼                   │
                ProjectionWorker ──► ProjectionHandler
                or EventSinkRunner    (updates read model)
```

### Multiple Sources Flow (`PersistenceHandlerEntry`)

`PersistenceRegistry` stores handlers as `PersistenceHandlerEntry(handler_cls, source, priority)`. This enables a complete multi-source routing model:

- `source` selects which `UnitOfWork` factory is used (`dispatcher._get_uow_factory(entry.source)`).
- `priority` decides which operation handler is selected when multiple write handlers are registered for the same aggregate type.
- query/retrieval handlers are source-aware as well, so read and write paths can target different backends intentionally.

**Example: SQL primary writes + Mongo read projections**

```python
registry = PersistenceRegistry()

# Writes for Order aggregate:
# - SQLAlchemy as primary write backend (higher priority)
# - fallback write backend (lower priority)
registry.register_operation(
    Order,
    SqlOrderOperationPersistence,
    source="sql_primary",
    priority=100,
)
registry.register_operation(
    Order,
    LegacyOrderOperationPersistence,
    source="legacy_sql",
    priority=10,
)

# Domain retrieval from SQL primary
registry.register_retrieval(
    Order,
    SqlOrderRetrievalPersistence,
    source="sql_primary",
)

# Query-side DTO reads from Mongo projection store
registry.register_query(
    OrderSummaryDTO,
    MongoOrderSummaryQueryPersistence,
    source="mongo_read",
)

dispatcher = PersistenceDispatcher(
    uow_factories={
        "sql_primary": build_sql_uow,
        "legacy_sql": build_legacy_sql_uow,
        "mongo_read": build_mongo_uow,
    },
    registry=registry,
)
```

**Flow with this setup:**

1. `dispatcher.apply(order)` resolves operation entries for `Order`, sorts by `priority`, picks `SqlOrderOperationPersistence` (`source="sql_primary"`).
2. SQL write persists aggregate + events; events go to event store/outbox.
3. `ProjectionWorker` or `EventSinkRunner` consumes events and updates Mongo read models (`OrderSummaryDTO` projection documents).
4. `dispatcher.fetch(OrderSummaryDTO, criteria)` resolves `MongoOrderSummaryQueryPersistence` (`source="mongo_read"`) and queries the projection store.

This pattern lets one dispatcher coordinate **polyglot persistence** cleanly:
- write-model consistency in one source (e.g. SQL),
- projection/read-model performance in another (e.g. Mongo),
- explicit and testable source boundaries via `PersistenceHandlerEntry`.

**Concrete end-to-end scenario:**

```python
# --- Write Side (command handler) ---
async def handle_create_order(cmd: CreateOrderCommand, dispatcher: IPersistenceDispatcher):
    order = Order.create(cmd.customer_id, cmd.items)
    # apply() persists the aggregate and its events via IOperationPersistence
    order_id = await dispatcher.apply(order, events=order.collect_events())
    return order_id

# --- Projection Handler (background) ---
class OrderSummaryProjection(ProjectionHandler):
    def __init__(self, mongo_collection):
        super().__init__()
        self.collection = mongo_collection
        self.add_handler(OrderCreated, self._on_created)
        self.add_handler(OrderShipped, self._on_shipped)
        self.add_handler(OrderCancelled, self._on_cancelled)

    async def _on_created(self, event: OrderCreated) -> None:
        await self.collection.insert_one({
            "_id": event.aggregate_id,
            "customer_id": event.customer_id,
            "status": "created",
            "total": event.total,
            "created_at": event.occurred_at.isoformat(),
        })

    async def _on_shipped(self, event: OrderShipped) -> None:
        await self.collection.update_one(
            {"_id": event.aggregate_id},
            {"$set": {"status": "shipped"}},
        )

    async def _on_cancelled(self, event: OrderCancelled) -> None:
        await self.collection.update_one(
            {"_id": event.aggregate_id},
            {"$set": {"status": "cancelled"}},
        )

# --- Read Side (query handler) ---
async def handle_get_order_summary(query: GetOrderSummary, dispatcher: IPersistenceDispatcher):
    # fetch() queries the read model built by the projection handler
    result = await dispatcher.fetch(OrderSummaryDTO, [query.order_id])
    items = await result  # SearchResult → list[OrderSummaryDTO]
    return items[0] if items else None
```

### End-to-End Data Flow

Putting it all together, here is the complete event flow from command to query:

```
1. Client sends CreateOrderCommand
       │
       ▼
2. Command Handler
   └─► Order.create() → emits OrderCreated event
       │
       ▼
3. PersistenceDispatcher.apply(order, events=[OrderCreated])
   └─► IOperationPersistence.persist()
       ├─► SQLAlchemy: INSERT aggregate row
       ├─► IEventStore.append(StoredEvent)
       └─► Outbox: enqueue event for broker
       │
       ▼
4a. ProjectionWorker (polls IEventStore)
    └─► get_events_after(last_checkpoint)
        └─► [StoredEvent(event_type="OrderCreated", ...)]
       │
  OR
       │
4b. EventSinkRunner (broker pushes message)
    └─► IMessageConsumer delivers message
        └─► {"event_type": "OrderCreated", ...}
       │
       ▼
5. EventTypeRegistry.hydrate("OrderCreated", payload)
   └─► OrderCreated(order_id="abc", total=99.95, ...)
       │
       ▼
6. ProjectionRegistry.get_handlers("OrderCreated")
   └─► [OrderSummaryProjection, RevenueReportProjection]
       │
       ▼
7. handler.handle(OrderCreated)
   └─► MongoDB: db.order_summary.insert_one({...})
       │
       ▼
8. ICheckpointStore.save_position("order_summary", new_position)
       │
       ▼
9. Client sends GetOrderSummary query
       │
       ▼
10. PersistenceDispatcher.fetch(OrderSummaryDTO, [order_id])
    └─► IQueryPersistence reads from MongoDB
        └─► OrderSummaryDTO(order_id="abc", status="created", total=99.95)
```

---

## Configuration Reference

### `ProjectionWorker`

```python
ProjectionWorker(
    event_store: IEventStore,
    projection_registry: IProjectionRegistry,
    checkpoint_store: ICheckpointStore,
    *,
    projection_name: str = "default",
    event_registry: EventTypeRegistry | None = None,
    batch_size: int = 100,
    poll_interval_seconds: float = 1.0,
    error_policy: ProjectionErrorPolicy | None = None,
)
```

### `EventSinkRunner`

```python
EventSinkRunner(
    consumer: IMessageConsumer,
    projection_registry: IProjectionRegistry,
    checkpoint_store: ICheckpointStore,
    *,
    projection_name: str = "sink",
    topic: str = "events",
    queue_name: str | None = None,
    event_registry: EventTypeRegistry | None = None,
    error_policy: ProjectionErrorPolicy | None = None,
)
```

### `ReplayEngine`

```python
ReplayEngine(
    event_store: IEventStore,
    projection_registry: IProjectionRegistry,
    checkpoint_store: ICheckpointStore,
    *,
    event_registry: EventTypeRegistry | None = None,
    batch_size: int = 500,
    error_policy: ProjectionErrorPolicy | None = None,
)
```

### `PartitionedProjectionWorker`

```python
PartitionedProjectionWorker(
    event_store: IEventStore,
    projection_registry: IProjectionRegistry,
    checkpoint_store: ICheckpointStore,
    lock_strategy: ILockStrategy,
    *,
    partition_index: int = 0,
    partition_count: int = 1,
    projection_name: str = "partitioned",
    event_registry: EventTypeRegistry | None = None,
    batch_size: int = 100,
    poll_interval_seconds: float = 1.0,
    error_policy: ProjectionErrorPolicy | None = None,
)
```

### `ProjectionErrorPolicy`

```python
ProjectionErrorPolicy(
    policy: str = "skip",            # "skip" | "retry" | "dead_letter" | "retry_then_dead_letter"
    *,
    max_retries: int = 3,
    dead_letter_callback: Callable[[DomainEvent, Exception], Any] | None = None,
)
```

---

## Exception Hierarchy

All exceptions inherit from the core toolkit hierarchy:

```
CQRSDDDError (cqrs_ddd_core)
├── HandlerError
│   └── ProjectionError
│       └── ProjectionHandlerError
└── PersistenceError
    └── CheckpointError
```

| Exception | Raised when |
|---|---|
| `ProjectionError` | Base for all projection-related errors. |
| `ProjectionHandlerError` | A projection handler fails after exhausting retries, or error policy escalates. |
| `CheckpointError` | Checkpoint read/write operations fail. |

---

## Public API

Everything exported from `cqrs_ddd_projections`:

| Symbol | Kind | Description |
|---|---|---|
| `IProjectionHandler` | Protocol | Contract for projection handlers. |
| `ICheckpointStore` | Protocol | Contract for checkpoint persistence. |
| `IProjectionRegistry` | Protocol | Contract for event-type → handler mapping. |
| `ProjectionHandler` | Base class | Convenience base with async event-type map (`add_handler`) and dispatching `handle()`. |
| `ProjectionRegistry` | Implementation | In-memory registry mapping event types to handler lists. |
| `InMemoryCheckpointStore` | Implementation | Dict-backed checkpoint store for testing. |
| `ProjectionWorker` | Worker | Polls `IEventStore`, dispatches events, checkpoints. |
| `EventSinkRunner` | Worker | Subscribes to `IMessageConsumer`, dispatches events, checkpoints. |
| `ReplayEngine` | Engine | Rebuilds projections from full event history. |
| `PartitionedProjectionWorker` | Worker | Hash-partitioned worker with `ILockStrategy` for horizontal scaling. |
| `ProjectionErrorPolicy` | Policy | Configurable skip / retry / dead-letter / retry-then-dead-letter handling. |
| `ProjectionError` | Exception | Base projection error. |
| `ProjectionHandlerError` | Exception | Handler failure after retries. |
| `CheckpointError` | Exception | Checkpoint I/O failure. |

---

## Optional Dependencies

Install extras for production checkpoint stores and event sources:

```
pip install cqrs-ddd-projections[redis]        # Redis checkpoint store
pip install cqrs-ddd-projections[sqlalchemy]    # SQLAlchemy checkpoint store
pip install cqrs-ddd-projections[mongo]         # MongoDB projection store
pip install cqrs-ddd-projections[messaging]     # IMessageConsumer for EventSinkRunner
pip install cqrs-ddd-projections[advanced]      # PersistenceDispatcher integration
```

---

## Recommended Setup

For most teams, this setup gives a strong default balance between reliability, operability, and simplicity:

- **Write side**: use SQLAlchemy persistence for aggregates and event store (`cqrs-ddd-persistence-sqlalchemy`).
- **Event delivery**: publish through outbox to a broker and run `EventSinkRunner` as the primary projection path.
- **Read side (default)**: use SQLAlchemy projections; for geometry/GIS workloads prefer PostgreSQL + PostGIS via SQLAlchemy for mature spatial indexing and query capabilities.
- **Read side (optional)**: use MongoDB projections (`cqrs-ddd-persistence-mongo`) for document-centric, denormalized query DTOs where advanced spatial semantics are not required.
- **Checkpointing**: use Redis or SQL-backed `ICheckpointStore` in production (avoid in-memory checkpoints outside tests).
- **Error policy**: start with `retry_then_dead_letter` for critical projections, and reserve `skip` for non-critical or analytics-only projections.
- **Replay strategy**: keep `ReplayEngine` available as an operational tool for schema/view rebuilds and recovery drills.

### Minimal production profile

```python
ProjectionWorker/EventSinkRunner:
  batch_size: 100-500
  poll_interval_seconds: 0.5-2.0   # poll mode only
  error_policy: retry_then_dead_letter(max_retries=3..5)
  checkpoint_store: durable (redis/sql)
```

### Local development profile

```python
ProjectionWorker:
  checkpoint_store: InMemoryCheckpointStore
  error_policy: skip or retry(max_retries=1)
  batch_size: 50-100
  poll_interval_seconds: 0.2-1.0
```
