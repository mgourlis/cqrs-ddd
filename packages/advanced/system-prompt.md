# Module Architecture Guide: `cqrs-ddd-advanced-core`

**Role:** The Complex Logic Layer.
**Dependency Policy:**
* **Mandatory:** `cqrs-ddd-core`.
* **Recommended:** `pydantic` (for Saga State serialization).
* **Optional:** `tenacity` (for retry logic in workers).
* **Strictly Forbidden:** Infrastructure drivers (SQLAlchemy, Redis, Kafka, Boto3).
* **Purpose:** Provide pure-logic implementations of Sagas, Outbox, Persistence Dispatcher, Background Jobs, Event Publishing/Consuming, and Undo/Redo patterns.

---

## **1. Directory Structure**

```text
├── ports/                       # Public interfaces and Protocols (Ports)
├── adapters/                    # Concrete implementations (Adapters)
│   └── memory/                  # In-memory implementations for testing
│       ├── background_jobs.py   # InMemoryBackgroundJobRepository
│       └── sagas.py             # InMemorySagaRepository
├── sagas/                       # Saga / Process Manager (State Machine)
│   ├── orchestration.py         # Saga[S] base class (handle, TCC, compensate)
│   ├── state.py                 # SagaState (Pydantic, 20+ fields)
│   ├── manager.py               # SagaManager (handle, start_saga)
│   ├── registry.py              # SagaRegistry (event_type → saga_type mapping)
│   ├── bootstrap.py             # bootstrap_sagas()
│   └── worker.py                # SagaRecoveryWorker (crash recovery, timeout handling)
├── outbox/                      # Outbox Pattern (transactional side-effects)
│   ├── message.py               # OutboxMessage (dataclass)
│   ├── service.py               # OutboxService (batch operations, retry logic)
│   ├── publisher.py             # OutboxPublisher (adapter to IMessagePublisher)
│   ├── worker.py                # OutboxWorker (asyncio polling loop)
│   └── testing.py               # InMemoryOutboxStorage
├── persistence/                 # Persistence Dispatcher logic
│   └── dispatcher.py            # PersistenceDispatcher (routes to ports/persistence.py)
├── background_jobs/             # Background Job Management
│   ├── entity.py                # BaseBackgroundJob (entity with status lifecycle)
│   ├── events.py                # Job lifecycle events (6 types)
│   ├── service.py               # BackgroundJobService
│   ├── worker.py                # JobSweeperWorker
│   ├── handler.py               # BackgroundJobEventHandler
│   └── testing.py               # InMemoryBackgroundJobPersistence
├── publishers/                  # Event Publishing & Routing
├── consumers/                   # Event Consumption
├── undo/                        # Undo/Redo Pattern
├── upcasting/                   # Event Schema Evolution logic
│   └── registry.py              # UpcasterChain (v1→v2→v3 pipeline)
├── snapshots/                   # Event Sourcing Optimization logic
│   └── strategy.py              # EveryNEventsStrategy
├── scheduling/                  # Command Scheduling logic
│   └── ...                      # (Concrete implementation logic)
└── conflict/                    # Conflict Resolution logic
    └── resolution.py            # Merge strategy implementations
```

## **2. Implementation Rules**

### **A. Sagas & Process Managers (`sagas/`)**

**Design Decision:** We use an **explicit state machine** approach, NOT decorator-based (`@saga_step`). All event handling goes through a single `_handle_event(event)` method with `match`/`case` or `if`/`elif` dispatch.

**`SagaState` (Pydantic Model, 20+ fields)**
* `id: str` — Unique saga instance ID
* `saga_type: str` — Class name for registry lookup
* `status: SagaStatus` — `PENDING | RUNNING | SUSPENDED | COMPLETED | FAILED | COMPENSATING`
* `current_step: str` — Current step name
* `step_history: List[StepRecord]` — Ordered list of step transitions with timestamps
* `processed_event_ids: List[str]` — Idempotency tracking
* `pending_commands: List[dict]` — Queued commands awaiting dispatch
* `compensation_stack: List[CompensationRecord]` — LIFO stack of compensating actions
* `suspended_at: Optional[datetime]` — When suspension started
* `suspension_reason: Optional[str]` — Why the saga was suspended
* `timeout_at: Optional[datetime]` — When the saga should time out
* `retry_count: int` — Number of retries after failure
* `max_retries: int` — Configurable max retries
* `created_at: datetime` — Saga creation timestamp
* `updated_at: datetime` — Last state change
* `metadata: dict` — Arbitrary context data
* `correlation_id: Optional[str]` — For distributed tracing
* `version: int` — Optimistic concurrency

**`Saga[S]` Base Class**
* `handle(event)` — Async. Public entry: idempotency check → `_handle_event()` → collect commands.
* `_handle_event(event)` — **Abstract.** User implements with match/case on event type.
* `dispatch(command)` — Queues a command for later execution by SagaManager.
* `complete()` — Marks saga as COMPLETED.
* `fail(reason)` — Marks saga as FAILED, triggers compensation.
* `suspend(reason, timeout)` — Marks saga as SUSPENDED with optional timeout.
* `resume()` — Resumes a SUSPENDED saga.
* `add_compensation(action)` — Pushes a compensating action onto the stack.
* `execute_compensations()` — Pops and executes compensating actions in LIFO order.

**`SagaManager`**
* **Lifecycle:** Load saga from repository → Call `handle(event)` → Save state → Dispatch pending commands.
* **API:** `handle(event)` — Event-driven choreography; `start_saga(saga_class, initial_event, correlation_id)` — Explicit orchestration.
* **Crash Recovery:** `recover_pending_sagas()` — Queries ISagaRepository for stale sagas.

**`SagaRegistry`**
* Maps `event_type → List[Type[Saga]]` (multiple sagas can react to the same event).
* `register_saga(saga_class)` uses `listened_events()` (from `listens_to` or override); manual `register(event_type, saga_class)` also supported.

**`SagaRecoveryWorker`**
* Background worker that polls for stale/timed-out sagas.
* Processes: (1) expired suspended sagas, (2) stalled sagas with pending commands (deduplicates by `dispatched` flag), (3) TCC TIME_BASED step timeouts.
* Depends on `ISagaRepository` for persistence.

### **B. Outbox Pattern (`outbox/`)**

**`OutboxMessage` (Dataclass/Pydantic)**
* `id`, `event_id`, `event_type`, `aggregate_id`, `payload`, `status`, `created_at`, `retry_count`, `last_error`.
* Status: `PENDING | PUBLISHED | FAILED`.

**`OutboxService`**
* `save_messages(messages)` — Delegates to `IOutboxStorage` port.
* `process_batch(batch_size)` — Gets pending → publishes via `IMessagePublisher` → marks published.
* `retry_failed(max_retries)` — Retries failed messages.

**`OutboxPublisher`**
* Adapter that reads from `IOutboxStorage` and publishes via `IMessagePublisher`.
* Serializes `OutboxMessage.payload` to broker-specific format.

**`OutboxWorker`**
* Asyncio polling loop. Configurable interval and batch size.
* Implements `IBackgroundWorker` (defined in this package).

### **C. Persistence Dispatcher (`persistence/`)**

**`PersistenceRegistry`** — Centralized registry for all persistence handlers. Maps types to `PersistenceHandlerEntry` which includes `handler_cls`, `source` (polyglot routing), and `priority`.
**`IOperationPersistence[T_Entity, ID_contra]`** — Write operations. Priority-ordered list in registry.
**`IRetrievalPersistence[T_Entity, ID_contra]`** — Aggregate retrieval (Command-side reads). 1:1 mapping.
**`IQueryPersistence[T_Result, ID_contra]`** — ID-based read model fetching (highly cacheable). 1:1 mapping.
**`IQuerySpecificationPersistence[T_Result]`** — Specification-based read model filtering. 1:1 mapping.
**`PersistenceDispatcher`** — Unified API: routes `apply(modification)`, `fetch_domain(entity_type, ids)`, and `fetch(result_type, criteria)` to correct backend via polyglot `uow_factories`.

### **D. Background Jobs (`background_jobs/`)**

* `BaseBackgroundJob` — Entity with status lifecycle (`PENDING → RUNNING → COMPLETED/FAILED`).
* 6 lifecycle events: `JobCreated`, `JobStarted`, `JobCompleted`, `JobFailed`, `JobRetried`, `JobCancelled`.
* `BackgroundJobService` — Schedule, cancel, retry, query status.
* `JobSweeperWorker` — Periodically cleans up stale/orphaned jobs.

### **E. Event Publishing & Routing (`publishers/`)**

* `PublishingEventHandler` — Bridges `DomainEvent` dispatch to `IMessagePublisher`.
* `TopicRoutingPublisher` — Routes events to different topics/exchanges based on event type.
* `@route_to(destination)` — Decorator that marks an event class for a specific routing destination.

### **F. Event Consumer (`consumers/`)**

* `BaseEventConsumer` — Deserializes broker messages → hydrates `DomainEvent` via `EventTypeRegistry` → dispatches to `EventDispatcher`.

### **G. Undo/Redo (`undo/`)**

* `UndoExecutor` — Protocol for reversing a specific action type.
* `UndoExecutorRegistry` — Maps action types to their undo executors.
* `UndoService` — Orchestrates undo by looking up the executor and executing reversal.

### **H. Event Upcasting (`upcasting/`)** ✅ Implemented
* `IEventUpcaster` — Transforms `dict` → `dict` (version N → N+1).
* `UpcasterChain` — Applies sequence of upcasters based on event version.

* `ISnapshotStore` — Protocol in `ports/snapshots.py`.
* `ISnapshotStrategy` / `EveryNEventsStrategy` — Protocol in `ports/snapshots.py`, impl in `snapshots/strategy.py`.

---

## **3. Code Prototypes**

#### **1. The Base Saga (State Machine Approach)**
```python
from __future__ import annotations
from typing import Generic, TypeVar, List, Any
from pydantic import BaseModel, Field
from cqrs_ddd_core.domain.events import DomainEvent
from cqrs_ddd_core.cqrs.command import Command

S = TypeVar("S", bound=BaseModel)

class SagaStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUSPENDED = "SUSPENDED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    COMPENSATING = "COMPENSATING"

class SagaState(BaseModel):
    id: str
    saga_type: str = ""
    status: SagaStatus = SagaStatus.PENDING
    current_step: str = ""
    step_history: List[dict] = Field(default_factory=list)
    processed_event_ids: List[str] = Field(default_factory=list)
    pending_commands: List[dict] = Field(default_factory=list)
    compensation_stack: List[dict] = Field(default_factory=list)
    suspended_at: Optional[datetime] = None
    suspension_reason: Optional[str] = None
    timeout_at: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 3
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = Field(default_factory=dict)
    correlation_id: Optional[str] = None
    version: int = 0

class Saga(Generic[S]):
    def __init__(self, state: S):
        self.state = state
        self._commands_to_dispatch: List[Command] = []

    def handle(self, event: DomainEvent) -> None:
        if str(event.event_id) in self.state.processed_event_ids:
            return  # Idempotency guard
        self._handle_event(event)
        self.state.processed_event_ids.append(str(event.event_id))
        self.state.updated_at = datetime.now(timezone.utc)
        self.state.version += 1

    def _handle_event(self, event: DomainEvent) -> None:
        raise NotImplementedError("Subclass must implement _handle_event with match/case")

    def dispatch(self, command: Command) -> None:
        self._commands_to_dispatch.append(command)

    def suspend(self, reason: str, timeout: Optional[timedelta] = None) -> None:
        self.state.status = SagaStatus.SUSPENDED
        self.state.suspended_at = datetime.now(timezone.utc)
        self.state.suspension_reason = reason
        if timeout:
            self.state.timeout_at = self.state.suspended_at + timeout

    def resume(self) -> None:
        self.state.status = SagaStatus.RUNNING
        self.state.suspended_at = None
        self.state.suspension_reason = None
        self.state.timeout_at = None

    def complete(self) -> None:
        self.state.status = SagaStatus.COMPLETED

    def fail(self, reason: str) -> None:
        self.state.status = SagaStatus.FAILED
        self.state.metadata["failure_reason"] = reason

    def add_compensation(self, action: dict) -> None:
        self.state.compensation_stack.append(action)

    async def execute_compensations(self) -> None:
        self.state.status = SagaStatus.COMPENSATING
        while self.state.compensation_stack:
            action = self.state.compensation_stack.pop()
            self.dispatch(action["command"])

    def collect_commands(self) -> List[Command]:
        cmds = self._commands_to_dispatch[:]
        self._commands_to_dispatch.clear()
        return cmds
```

#### **2. The Saga Manager**
```python
class SagaManager:
    def __init__(self, repository: ISagaRepository, registry: SagaRegistry, mediator: IMediator):
        self._repository = repository
        self._registry = registry
        self._mediator = mediator

    async def handle_event(self, event: DomainEvent) -> None:
        saga_types = self._registry.get_sagas_for_event(type(event).__name__)
        for saga_type in saga_types:
            state = await self._repository.load(saga_type, event)
            saga = saga_type(state)
            saga.handle(event)
            await self._repository.save(saga.state)
            for command in saga.collect_commands():
                await self._mediator.send(command)
```

#### **3. The Outbox Worker**
```python
class OutboxWorker:
    def __init__(self, storage: IOutboxStorage, publisher: IMessagePublisher,
                 interval: float = 1.0, batch_size: int = 100):
        self._storage = storage
        self._publisher = publisher
        self._interval = interval
        self._batch_size = batch_size
        self._running = False

    async def start(self) -> None:
        self._running = True
        while self._running:
            messages = await self._storage.get_pending(self._batch_size)
            for msg in messages:
                try:
                    await self._publisher.publish(msg.event_type, msg.payload)
                    await self._storage.mark_published(msg.id)
                except Exception as e:
                    await self._storage.mark_failed(msg.id, str(e))
            await asyncio.sleep(self._interval)

    async def stop(self) -> None:
        self._running = False

#### **4. The Persistence Dispatcher (Refined Polyglot Routing)**
```python
class PersistenceDispatcher:
    def __init__(
        self,
        uow_factories: Dict[str, Callable[[], IUnitOfWork]],
        registry: PersistenceRegistry,
        handler_factory: Optional[Callable[[Type], Any]] = None,
    ):
        self._uow_factories = uow_factories
        self._registry = registry
        self._handler_factory = handler_factory or (lambda cls: cls())

    async def apply(self, modification: Modification[ID_contra]) -> ID_contra:
        entry = self._registry.get_operation_entries(type(modification.entity))[0]
        handler = self._handler_factory(entry.handler_cls)
        async with self._uow_factories[entry.source]() as uow:
            return await handler.persist(modification, uow)

    async def fetch(self, result_type: Type[T_Result], criteria: Union[Sequence[ID], ISpecification]) -> List[T_Result]:
        if isinstance(criteria, ISpecification):
            entry = self._registry.get_query_spec_entry(result_type)
            # ... resolve and dispatch to QuerySpecificationPersistence
        else:
            entry = self._registry.get_query_entry(result_type)
            # ... resolve and dispatch to QueryPersistence (ID-based)
```
```

---

## **4. System Prompt for Agent Implementation**

> **Instruction:**
> Implement the `cqrs-ddd-advanced-core` package.
>
> **Goal:** Create the complete machinery for complex business workflows (Sagas), reliable event delivery (Outbox), multi-backend persistence routing (PersistenceDispatcher), background job management, event publishing/consuming, and schema evolution (Upcasting).
>
> **Constraints:**
> 1.  **Pure Python:** NO database code. NO infrastructure drivers. Only `cqrs-ddd-core` + optional `pydantic`/`tenacity`.
> 2.  **Saga Pattern (State Machine):**
>     * Implement `Saga[S]` with explicit `_handle_event()` method (NOT decorator-based).
>     * `SagaState` must have 20+ fields (history, compensations, suspension, timeouts).
>     * Implement `SagaManager` with both `handle()` (event-driven) and `start_saga()` (orchestration).
>     * Implement `SagaRecoveryWorker` for crash recovery.
>     * Implement `SagaRegistry` for event-to-saga routing.
>     * Implement `InMemorySagaRepository` for testing.
> 3.  **Outbox Pattern:**
>     * Implement `OutboxMessage`, `OutboxService`, `OutboxPublisher`, `OutboxWorker`.
>     * Implement `InMemoryOutboxStorage` for testing.
> 4.  **Persistence Dispatcher:**
>     * Implement `PersistenceRegistry` with `PersistenceHandlerEntry` (source/priority metadata).
>     * Implement `OperationPersistence`, `RetrievalPersistence`.
>     * Split Query: `QueryPersistence` (ID-based) and `QuerySpecificationPersistence` (Spec-based).
>     * Implement `PersistenceDispatcher` with polyglot `uow_factories` routing.
> 5.  **Background Jobs:**
>     * Implement `BaseBackgroundJob`, 6 lifecycle events, `BackgroundJobService`, `JobSweeperWorker`.
> 6.  **Publishers/Consumer:**
>     * Implement `PublishingEventHandler`, `TopicRoutingPublisher`, `@route_to()`, `BaseEventConsumer`.
> 7.  **Undo:**
>     * Implement `UndoService`, `UndoExecutor`, `UndoExecutorRegistry`.
> 8.  **Upcasting:** Already implemented — keep as-is.
> 9.  **Snapshotting:** Add `ISnapshotStore` protocol.
>
> **Output (priority order):**
> 1.  `sagas/` — state.py, orchestration.py, manager.py, registry.py, worker.py, bootstrap.py; `adapters/memory/sagas.py` — InMemorySagaRepository
> 2.  `outbox/` — message.py, service.py, publisher.py, worker.py, testing.py
> 3.  `persistence/dispatcher.py`
> 4.  `background_jobs/` — entity.py, events.py, service.py, worker.py, handler.py, testing.py
> 5.  `publishers/` — handler.py, routing.py, decorators.py
> 6.  `consumers/base.py`
> 7.  `undo/service.py`
> 8.  `snapshots/store.py` (ISnapshotStore protocol)

---

## **5. Analysis & Validation Guidelines**

When reviewing or generating code in `cqrs-ddd-advanced-core`, systematically apply these checks.

### **5.1 Import Isolation (Blocker)**

This package is pure logic — zero infrastructure drivers allowed:
- `grep -r "import sqlalchemy" src/` → MUST return zero results
- `grep -r "import redis" src/` → MUST return zero results
- `grep -r "import motor" src/` → MUST return zero results
- `grep -r "import aio_pika" src/` → MUST return zero results
- `grep -r "import boto" src/` → MUST return zero results
- Only allowed external imports: `cqrs_ddd_core`, `pydantic` (optional), `tenacity` (optional)

### **5.2 Protocol Ownership**

This package OWNS these protocols (they are NOT in core):
- `ISagaRepository` — saga state persistence contract
- `IBackgroundWorker` — background worker lifecycle contract
- `ISnapshotStore` — snapshot persistence contract
- `ISnapshotStrategy` — snapshotting decision contract
- `ICommandScheduler` — deferred command execution contract
- `IEventUpcaster` — event translation contract
- `IOperationPersistence`, `IRetrievalPersistence`, `IQueryPersistence`, `IQuerySpecificationPersistence` — persistence contracts
- `IMergeStrategy` — conflict resolution contract

Verify: none of these protocols appear in `cqrs-ddd-core/ports/`.

### **5.3 Saga State Machine Integrity**

**Status Transition Validation:**
```
Valid transitions:
  PENDING → RUNNING (on first event)
  RUNNING → COMPLETED (on success)
  RUNNING → FAILED (on unrecoverable error)
  RUNNING → SUSPENDED (on explicit suspension or external wait)
  RUNNING → COMPENSATING (on failure requiring rollback)
  SUSPENDED → RUNNING (on resume or timeout)
  FAILED → COMPENSATING (on compensation trigger)
  COMPENSATING → FAILED (compensation itself failed)
  COMPENSATING → COMPLETED (all compensations executed)

Invalid transitions (must raise SagaTransitionError):
  COMPLETED → anything
  anything → PENDING (PENDING is initial state only)
```

Checklist:
- [ ] `SagaState` has 20+ fields (verify completeness against spec)
- [ ] `processed_event_ids` guard prevents duplicate event processing (idempotency)
- [ ] `compensation_stack` pops in LIFO order during `execute_compensations()`
- [ ] `timeout_at` is checked by `SagaRecoveryWorker` — expired sagas get resumed or compensated
- [ ] `version` increments on every state mutation (optimistic concurrency)
- [ ] `step_history` records every transition with timestamp and event reference
- [ ] `pending_commands` are drained by `SagaManager` after `handle()`, then cleared

### **5.4 Outbox Reliability**

- [ ] `OutboxMessage` has `retry_count` and `max_retries` fields
- [ ] `OutboxWorker` handles exceptions per-message (one failure does NOT kill the batch)
- [ ] `mark_failed()` increments `retry_count` and records `last_error`
- [ ] Messages exceeding `max_retries` are dead-lettered (not retried indefinitely)
- [ ] `OutboxService.process_batch()` is idempotent — marking published is atomic
- [ ] `InMemoryOutboxStorage` mimics the same contract for testing

### **5.5 Background Job Lifecycle**

- [ ] Status transitions: `PENDING → RUNNING → COMPLETED/FAILED`, `FAILED → RETRIED → RUNNING`
- [ ] All 6 lifecycle events (`JobCreated`, `JobStarted`, `JobCompleted`, `JobFailed`, `JobRetried`, `JobCancelled`) are emitted at each transition
- [ ] `JobSweeperWorker` detects stale jobs (stuck in `RUNNING` past configurable timeout)
- [ ] `InMemoryBackgroundJobPersistence` provided for testing

### **5.6 Event Publishing Chain**

- [ ] `PublishingEventHandler` bridges domain events to `IMessagePublisher` (from `cqrs-ddd-messaging`)
- [ ] `TopicRoutingPublisher` routes events based on event type via `@route_to` decorator or registry
- [ ] `BaseEventConsumer` hydrates events via `EventTypeRegistry` before dispatching
- [ ] Serialization roundtrip is lossless: `event → .model_dump() → JSON string → parse → hydrate() → equivalent event`

### **5.7 Undo/Redo Pattern**

- [ ] `UndoExecutor` is a protocol (not concrete class) — each action type provides its own executor
- [ ] `UndoExecutorRegistry` maps action types to executor instances
- [ ] `UndoService` orchestrates: look up executor → execute reversal → emit undo event
- [ ] Undo actions are themselves auditable (produce events)

### **5.8 Anti-Pattern Detection**

| Pattern | Detection | Fix |
|:---|:---|:---|
| Decorator-based saga | `@saga_step`, `@step` decorators | Use explicit `_handle_event(event)` with match/case |
| Missing idempotency | `handle(event)` without `processed_event_ids` check | Add guard at top of `handle()` |
| Sync compensation | `execute_compensations()` not async | Must be `async def` — compensations may dispatch commands |
| Direct DB access | Any `sqlalchemy` / `redis` / file / network import | Use `IOutboxStorage`, `ISagaRepository` protocols |
| Missing correlation | Saga dispatches commands without `correlation_id` | Copy saga's `correlation_id` to all dispatched commands |
| Infinite retry | `OutboxWorker` retries without checking `max_retries` | Check `retry_count < max_retries` before retrying |
| Lost commands | `Saga.collect_commands()` not called after `handle()` | `SagaManager` must drain commands after every handle call |

### **5.9 Completeness Verification**

Before marking advanced-core as "Phase 2 Complete", verify:

```
sagas/
  ✅ state.py          — SagaState (20+ fields), SagaStatus enum, StepRecord, CompensationRecord
  ✅ orchestration.py  — Saga[S] base class with handle/suspend/resume/compensate/complete/fail
  ✅ manager.py        — SagaManager
  ✅ registry.py       — SagaRegistry (event_type → saga_type mapping)
  ✅ worker.py         — SagaRecoveryWorker (stale/timeout recovery)
  ✅ testing.py        — InMemorySagaRepository

outbox/
  ✅ message.py        — OutboxMessage dataclass
  ✅ service.py        — OutboxService (batch + retry)
  ✅ publisher.py      — OutboxPublisher (adapter to IMessagePublisher)
  ✅ worker.py         — OutboxWorker (async polling loop)
  ✅ testing.py        — InMemoryOutboxStorage

persistence/
  ✅ dispatcher.py     — OperationPersistence, RetrievalPersistence, QueryPersistence, PersistenceDispatcher

background_jobs/
  ✅ entity.py         — BaseBackgroundJob
  ✅ events.py         — 6 lifecycle events
  ✅ service.py        — BackgroundJobService
  ✅ worker.py         — JobSweeperWorker
  ✅ handler.py        — BackgroundJobEventHandler
  ✅ testing.py        — InMemoryBackgroundJobPersistence

publishers/
  ✅ handler.py        — PublishingEventHandler
  ✅ routing.py        — TopicRoutingPublisher
  ✅ decorators.py     — @route_to(destination)

consumers/
  ✅ base.py           — BaseEventConsumer

undo/
  ✅ service.py        — UndoService, UndoExecutor, UndoExecutorRegistry

upcasting/
  ✅ registry.py       — UpcasterChain

snapshots/
  ✅ strategy.py       — EveryNEventsStrategy

scheduling/
  ✅ (impl-specific files)

conflict/
  ✅ resolution.py     — ConflictResolutionPolicy, ConflictResolver, etc.

ports/
  ✅ persistence.py    — IOperationPersistence, IRetrievalPersistence, IQueryPersistence, IQuerySpecificationPersistence
  ✅ scheduling.py     — ICommandScheduler
  ✅ upcasting.py      — IEventUpcaster
  ✅ snapshots.py      — ISnapshotStore, ISnapshotStrategy
  ✅ conflict.py       — IMergeStrategy
```
