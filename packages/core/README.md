# CQRS-DDD Core - Complete Implementation Guide

**Package:** `cqrs-ddd-core`
**Version:** 0.1.0
**Purpose:** Pure Python foundation for Domain-Driven Design and CQRS

The pure-Python foundation of the CQRS-DDD Toolkit. **Zero infrastructure dependencies** — only `pydantic` and `typing-extensions`.

This package provides:
- **Domain primitives** - AggregateRoot, DomainEvent, ValueObject, Mixins, Specification
- **CQRS dispatch pipeline** - Mediator, Commands, Queries, Handlers, EventDispatcher
- **Protocol-based ports** - IRepository, IEventStore, IOutboxStorage, UnitOfWork
- **In-memory adapters** - Full test suite without databases
- **Middleware pipeline** - Pluggable command/query processing
- **Instrumentation hooks** - Observable without specific observability stack
- **Correlation context** - Automatic distributed tracing

## Installation

```bash
pip install cqrs-ddd-core
```

Optional extras:

```bash
pip install cqrs-ddd-core[geometry]       # SpatialMixin / GeoJSON support
pip install cqrs-ddd-core[observability]  # OpenTelemetry hook adapter
pip install cqrs-ddd-core[health]         # Health check registry
```

---

## Package Structure

```
cqrs_ddd_core/
├── domain/             # AggregateRoot, DomainEvent, ValueObject, EventTypeRegistry, mixins
├── cqrs/               # Command, Query, Mediator, EventDispatcher, HandlerRegistry
│   ├── outbox/         # OutboxService, BufferedOutbox
│   ├── consumers/      # BaseEventConsumer
│   └── publishers/     # TopicRoutingPublisher, decorators
├── ports/              # Protocol definitions (IRepository, IEventStore, ILockStrategy, …)
├── adapters/memory/    # In-memory implementations for all ports (testing)
├── middleware/          # OutboxMiddleware, LoggingMiddleware, ValidatorMiddleware, pipeline
├── primitives/         # Exception hierarchy, ResourceIdentifier, IIDGenerator
├── validation/         # PydanticValidator, CompositeValidator, ValidationResult
├── correlation.py      # ContextVar-based correlation / causation ID propagation
└── instrumentation.py  # HookRegistry, InstrumentationHook protocol, fire_and_forget_hook
```

## Detailed Documentation

Each folder has its own detailed README with implementation details and usage examples:

| Folder | Description | README |
|--------|-------------|--------|
| **domain/** | Aggregate roots, domain events, value objects, mixins, specifications | [domain/README.md](src/cqrs_ddd_core/domain/README.md) |
| **cqrs/** | Mediator, commands, queries, handlers, event dispatcher, registry | [cqrs/README.md](src/cqrs_ddd_core/cqrs/README.md) |
| **ports/** | Protocol definitions for all infrastructure abstractions | [ports/README.md](src/cqrs_ddd_core/ports/README.md) |
| **adapters/** | In-memory implementations for testing (repositories, UoW, event store, etc.) | [adapters/README.md](src/cqrs_ddd_core/adapters/README.md) |
| **middleware/** | Pluggable middleware pipeline (logging, validation, outbox, locking) | [middleware/README.md](src/cqrs_ddd_core/middleware/README.md) |
| **primitives/** | Exception hierarchy, ID generators, resource locking primitives | [primitives/README.md](src/cqrs_ddd_core/primitives/README.md) |
| **validation/** | Pydantic validators, composite validators, validation results | [validation/README.md](src/cqrs_ddd_core/validation/README.md) |

---

## Correlation Context

### Problem

In distributed and async systems, a single user request fans out into commands, events, sagas, outbox messages, and background jobs. Without an explicit thread of identity, logs and traces from different components cannot be stitched together.

### Design

Correlation context is built on Python's `contextvars.ContextVar`, which propagates automatically across `async`/`await` boundaries and is copied into child `asyncio.Task`s:

```
HTTP request arrives
  │
  ├─ set_correlation_id("req-abc-123")     ← entry point sets context
  │
  ├─ mediator.send(CreateOrderCommand())   ← Command auto-inherits "req-abc-123"
  │    │
  │    ├─ EventDispatcher dispatches OrderCreated
  │    │    └─ hook attributes include correlation_id="req-abc-123"
  │    │
  │    └─ OutboxMiddleware publishes to outbox
  │         └─ outbox message metadata includes correlation_id="req-abc-123"
  │
  └─ all logs, spans, and hook attributes carry the same ID
```

### Two Context Variables

| Variable | Purpose | Lifecycle |
|:---------|:--------|:----------|
| `correlation_id` | Groups all operations belonging to the same logical request | Set once at the entry point; inherited by everything downstream |
| `causation_id` | Links an operation to the specific event that triggered it | Set by `CorrelationIdPropagator` when an event's `event_id` is detected |

### API

```python
from cqrs_ddd_core import (
    set_correlation_id,
    get_correlation_id,
    generate_correlation_id,
    set_causation_id,
    get_causation_id,
    get_context_vars,
    set_context_vars,
    CorrelationIdPropagator,
)

# ── At the request entry point ────────────────────────────
set_correlation_id(generate_correlation_id())

# ── Read anywhere downstream ──────────────────────────────
cid = get_correlation_id()   # same UUID set above

# ── Propagate to background tasks ─────────────────────────
ctx = get_context_vars()     # {"correlation_id": "...", "causation_id": "..."}
async def background():
    set_context_vars(**ctx)  # restore in the new task
    ...
asyncio.create_task(background())
```

### Automatic Inheritance by Commands and Queries

`Command` and `Query` base classes use `get_correlation_id` as their default factory:

```python
class Command(BaseModel, Generic[TResult]):
    correlation_id: str | None = Field(default_factory=get_correlation_id)
```

This means:

1. If a correlation ID is active in the context, the command inherits it **at creation time** — no middleware required.
2. If no context is set, `correlation_id` defaults to `None`.
3. The `Mediator` detects `None` and generates a fresh ID, setting it on both the command and the context so all downstream operations are covered.

The `CorrelationIdPropagator` middleware provides additional propagation: it injects the context ID into outgoing messages, extracts IDs from incoming messages, and sets the `causation_id` from event IDs.

---

## Instrumentation Hooks

### Problem

Every component in the framework (event dispatchers, outbox, sagas, lock managers, persistence orchestrators, etc.) needs to support observability, auditing, rate limiting, and similar cross-cutting concerns. Hard-wiring any specific technology (OpenTelemetry, Prometheus, Sentry) into the core would violate the zero-dependency principle.

### Design: Protocol + Registry + Pipeline

The instrumentation system has three concepts:

```
┌─────────────────────────────────────────────────────────────────┐
│  InstrumentationHook (Protocol)                                 │
│  Any callable matching the protocol can be a hook:              │
│  (operation, attributes, next_handler) → result                 │
└────────────────────────────────┬────────────────────────────────┘
                                 │ implements
┌────────────────────────────────▼────────────────────────────────┐
│  HookRegistration                                               │
│  Wraps a hook with filtering: operations, message_types,        │
│  predicate, priority, enabled flag, match cache                 │
└────────────────────────────────┬────────────────────────────────┘
                                 │ 0..*
┌────────────────────────────────▼────────────────────────────────┐
│  HookRegistry                                                   │
│  Manages registrations, builds pipelines, executes hooks.       │
│  Stored in a ContextVar — no module-level mutable global.       │
└─────────────────────────────────────────────────────────────────┘
```

### Why ContextVar, Not a Module Global

The registry is stored in a `ContextVar[HookRegistry | None]` rather than a module-level global:

- **Test isolation** — each test gets a fresh, empty registry automatically. No save/restore boilerplate, no leaked state between tests.
- **No mutable module state** — importing the module has no side effects. The registry is created lazily on first access within each context.
- **Context-safe** — `asyncio.create_task()` copies the current context, so child tasks inherit the application's configured registry.

```python
from cqrs_ddd_core import get_hook_registry, set_hook_registry, HookRegistry

# Application startup — configure once
registry = get_hook_registry()          # lazily created
registry.register(my_tracing_hook)
registry.register(my_metrics_hook)

# Test — automatic isolation
async def test_something():
    reg = get_hook_registry()           # fresh HookRegistry (ContextVar default)
    assert len(reg._registrations) == 0 # no leakage from other tests
```

### The InstrumentationHook Protocol

```python
@runtime_checkable
class InstrumentationHook(Protocol):
    async def __call__(
        self,
        operation: str,                          # dot-separated name
        attributes: dict[str, Any],              # contextual metadata
        next_handler: Callable[[], Awaitable[Any]],  # continue pipeline
    ) -> Any: ...
```

A hook wraps an operation. It receives the operation name (e.g., `"event.dispatch.OrderCreated"`), a dict of contextual attributes, and a `next_handler` to call the next hook or the actual operation. This is the **middleware pattern applied to infrastructure**.

### Pipeline Execution

When a framework component calls `registry.execute_all(operation, attributes, actual_work)`:

1. Matching registrations are filtered (by operation pattern, predicate, message type, enabled flag).
2. Matching hooks are composed into a pipeline ordered by priority (lower priority = outer wrapper).
3. The pipeline is awaited. Each hook calls `next_handler()` to continue.
4. If no hooks match, `actual_work()` is called directly with zero overhead.

```
priority=-10         priority=0           priority=10
┌──────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ TracingHk │ →  │ MetricsHook │ →  │  AuditHook   │ →  │ actual_work  │
│ (outer)   │    │             │    │  (inner)     │    │              │
└──────────┘    └──────────────┘    └──────────────┘    └──────────────┘
     ↑               result              result              result
     └───────────────────────────────────────────────────────────┘
```

### Registration Options

```python
registry = get_hook_registry()

# Match all operations
registry.register(my_hook, operations=["*"])

# Match by wildcard (fnmatch syntax)
registry.register(my_hook, operations=["event.*"])
registry.register(my_hook, operations=["saga.*", "job.*"])

# Match by message type (structural, checked at runtime)
registry.register(my_hook, message_types=[OrderCreated, OrderShipped])

# Match by runtime predicate
registry.register(my_hook, predicate=lambda op, attrs: "saga" in op)

# Control execution order (lower = outermost)
registry.register(tracing_hook, priority=-100)  # runs first, sees total duration
registry.register(audit_hook, priority=100)      # runs last, closest to actual work

# Disable/enable at runtime
reg = registry.register(my_hook, operations=["*"])
reg.enabled = False  # temporarily disabled
```

### Instrumented Components in Core

Every major component in the core package is instrumented. When no hooks are registered, the overhead is a single empty-list check and a direct call to the actual operation.

| Component | Operation | When |
|:----------|:---------|:-----|
| `EventDispatcher` | `event.dispatch.{EventType}` | Dispatching to all handlers for an event |
| `EventDispatcher` | `event.handler.{EventType}.{Handler}` | Invoking each individual handler |
| `TopicRoutingPublisher` | `publisher.publish.{topic}` | Publishing to a routed topic |
| `BaseEventConsumer` | `consumer.consume.{EventType}` | Consumer processing an incoming message |
| `OutboxService` | `outbox.process_batch` | Processing a batch of outbox messages |
| `OutboxService` | `outbox.retry_failed` | Retrying failed outbox messages |
| `BufferedOutbox` | `outbox.buffered.publish` | Saving a message to the outbox |
| `OutboxMiddleware` | `outbox.save_events` | Publishing events from a CommandResponse |
| `UnitOfWork` | `uow.commit` / `uow.rollback` | Committing or rolling back a transaction |
| `CriticalSection` | `lock.acquire.{resource_type}` | Acquiring a distributed lock |
| `InMemoryEventStore` | `event_store.append.{aggregate_type}` | Appending events to the store |
| `MessageRegistry` | `message_registry.register` | Registering a command or query type |
| `enrich_event_metadata` | `event.enrich_metadata` | Enriching an event with correlation IDs |

### Fire-and-Forget Hooks

Some components are synchronous (e.g., `MessageRegistry.register_command()`, `ConflictResolver.merge()`) but still need to emit hook notifications. The `fire_and_forget_hook` helper safely schedules a no-op hook execution on the running event loop with proper error logging:

```python
from cqrs_ddd_core import fire_and_forget_hook, get_hook_registry

# Safe from synchronous code — does nothing if no loop is running
fire_and_forget_hook(
    get_hook_registry(),
    "my.operation",
    {"key": "value"},
)
```

Key safety properties:
- Short-circuits immediately if no hooks are registered (zero overhead).
- Does nothing if there is no running event loop (safe in sync-only contexts).
- Attaches a `done_callback` that logs exceptions instead of silently swallowing them.

### Writing a Custom Hook

```python
from cqrs_ddd_core import get_hook_registry

class TimingHook:
    """Logs operations that exceed a duration threshold."""

    def __init__(self, threshold_ms: float = 200):
        self._threshold = threshold_ms

    async def __call__(self, operation, attributes, next_handler):
        import time
        start = time.monotonic()
        try:
            return await next_handler()
        finally:
            elapsed_ms = (time.monotonic() - start) * 1000
            if elapsed_ms > self._threshold:
                print(f"SLOW: {operation} took {elapsed_ms:.1f}ms")

# Register at application startup
get_hook_registry().register(
    TimingHook(threshold_ms=100),
    operations=["*"],
    priority=-50,
)
```

### Integrating with Observability Packages

The `cqrs-ddd-observability` package provides a ready-made `ObservabilityInstrumentationHook` that creates OpenTelemetry spans for every instrumented operation. A single call at startup connects everything:

```python
from cqrs_ddd_observability import install_framework_hooks

install_framework_hooks()  # registers OTel hook into the core HookRegistry
```

See the [observability package README](../infrastructure/observability/README.md) for full details on tracing, metrics, structured logging, and Sentry integration.

---

## CQRS Dispatch

### Command → Mediator → Handler → Response → Events

```python
from cqrs_ddd_core import (
    Command, CommandHandler, CommandResponse,
    Mediator, HandlerRegistry,
    set_correlation_id, generate_correlation_id,
)

class CreateOrder(Command[str]):
    customer_id: str
    items: list[str]

class CreateOrderHandler(CommandHandler[str]):
    async def handle(self, command: CreateOrder) -> CommandResponse[str]:
        order_id = "order-123"
        return CommandResponse(
            result=order_id,
            events=[OrderCreated(order_id=order_id)],
        )

# Wire up
registry = HandlerRegistry()
registry.register_command(CreateOrder, CreateOrderHandler)

mediator = Mediator(
    handler_registry=registry,
    uow_factory=lambda: InMemoryUnitOfWork(),
)

# Dispatch
set_correlation_id(generate_correlation_id())
response = await mediator.send(CreateOrder(customer_id="cust-1", items=["A", "B"]))
```

### Query → Mediator → Handler → Response

```python
from cqrs_ddd_core import Query, QueryHandler, QueryResponse

class GetOrder(Query[dict]):
    order_id: str

class GetOrderHandler(QueryHandler[dict]):
    async def handle(self, query: GetOrder) -> QueryResponse[dict]:
        return QueryResponse(result={"id": query.order_id, "status": "pending"})

registry.register_query(GetOrder, GetOrderHandler)
response = await mediator.query(GetOrder(order_id="order-123"))
```

---

## Domain Primitives

### AggregateRoot

```python
from cqrs_ddd_core import AggregateRoot, DomainEvent

class OrderCreated(DomainEvent):
    order_id: str
    aggregate_type: str | None = "Order"

class Order(AggregateRoot[str]):
    customer_id: str = ""
    items: list[str] = []

    def create(self, customer_id: str, items: list[str]) -> None:
        self.customer_id = customer_id
        self.items = items
        self._record_event(OrderCreated(
            order_id=str(self.id),
            aggregate_id=str(self.id),
        ))
```

### DomainEvent

Immutable, carries full tracing context. Aggregate metadata (`aggregate_id`, `aggregate_type`) enables event sourcing and undo/redo.

```python
class OrderShipped(DomainEvent):
    order_id: str
    tracking_number: str
    aggregate_type: str | None = "Order"
```

Events automatically pick up `correlation_id` and `causation_id` when enriched via `enrich_event_metadata()`.

---

## Ports (Protocols)

All infrastructure concerns are defined as `@runtime_checkable` protocols:

| Port | Module | Methods |
|:-----|:-------|:--------|
| `IRepository` | `ports.repository` | `get`, `save`, `delete`, `search` |
| `IEventStore` | `ports.event_store` | `append`, `get_events`, `get_by_aggregate` |
| `IOutboxStorage` | `ports.outbox` | `save_messages`, `get_pending`, `mark_published`, `mark_failed` |
| `IMessagePublisher` | `ports.messaging` | `publish` |
| `IMessageConsumer` | `ports.messaging` | `subscribe`, `start`, `stop` |
| `ILockStrategy` | `ports.locking` | `acquire`, `release` |
| `ICacheService` | `ports.cache` | `get`, `set`, `delete`, `exists` |
| `IMiddleware` | `ports.middleware` | `__call__(message, next_handler)` |
| `IBackgroundWorker` | `ports.background_worker` | `start`, `stop` |
| `IValidator` | `ports.validation` | `validate` |

---

## In-Memory Adapters

Every port has an in-memory implementation in `adapters/memory/` for unit testing:

```python
from cqrs_ddd_core import (
    InMemoryRepository,
    InMemoryEventStore,
    InMemoryOutboxStorage,
    InMemoryLockStrategy,
    InMemoryUnitOfWork,
)
```

These explicitly implement their corresponding protocols and are the recommended test doubles.

---

## Middleware Pipeline

Middleware wraps command dispatch in a composable pipeline:

```python
from cqrs_ddd_core import (
    Mediator,
    CorrelationIdPropagator,
    LoggingMiddleware,
    ValidatorMiddleware,
    OutboxMiddleware,
)

mediator = Mediator(
    handler_registry=registry,
    uow_factory=uow_factory,
    middlewares=[
        CorrelationIdPropagator(),   # propagate correlation IDs
        LoggingMiddleware(),          # log command/query dispatch
        ValidatorMiddleware(validator), # validate commands
        OutboxMiddleware(outbox),     # publish events to outbox
    ],
)
```

Middleware execution follows the same pattern as instrumentation hooks — each middleware calls `next_handler(message)` to continue the pipeline.

---

## Exception Hierarchy

```
CQRSDDDError
├── DomainError
│   ├── InvariantViolationError
│   ├── EntityNotFoundError
│   └── NotFoundError
├── ConcurrencyError
│   ├── OptimisticLockingError
│   ├── DomainConcurrencyError
│   └── LockAcquisitionError
├── HandlerError
│   ├── HandlerRegistrationError
│   └── PublisherNotFoundError
├── ValidationError
├── PersistenceError
│   └── EventStoreError
├── OutboxError
└── InfrastructureError
```

Prefer package-specific exceptions over bare `ValueError` / `RuntimeError`.

---

## API Reference

### Correlation

| Symbol | Description |
|:-------|:------------|
| `get_correlation_id()` | Read the current correlation ID from `ContextVar` |
| `set_correlation_id(id)` | Set the correlation ID in the current context |
| `generate_correlation_id()` | Generate a new UUID4 string |
| `get_causation_id()` | Read the current causation ID |
| `set_causation_id(id)` | Set the causation ID |
| `get_context_vars()` | Snapshot both vars for background-task spawning |
| `set_context_vars(**kw)` | Restore both vars in a new task |
| `CorrelationIdPropagator` | Middleware: inject/extract correlation IDs on messages |

### Instrumentation

| Symbol | Description |
|:-------|:------------|
| `InstrumentationHook` | Protocol that hooks must satisfy |
| `HookRegistration` | Registration handle with filtering, priority, enable/disable |
| `HookRegistry` | Registry: `register()`, `execute_all()`, `clear()` |
| `get_hook_registry()` | Get the `ContextVar`-backed registry for the current context |
| `set_hook_registry(r)` | Replace the registry in the current context |
| `fire_and_forget_hook(r, op, attrs)` | Safe fire-and-forget hook from sync code |
| `set_instrumentation_hook(h)` | Backward-compat: register a single hook |
| `get_instrumentation_hook()` | Backward-compat: get the first registered hook |

---

## Domain Layer - Implementation Details

### AggregateRoot

Base class for all aggregates with event collection and versioning:

```python
from uuid import UUID
from cqrs_ddd_core.domain.aggregate import AggregateRoot

class Order(AggregateRoot[UUID]):
    """Order aggregate with business logic."""

    customer_id: str
    status: str = "pending"
    total: float = 0.0

    def add_item(self, item: OrderItem) -> None:
        """Business logic in domain method."""
        if self.status != "pending":
            raise ValueError("Cannot modify confirmed order")

        # Update state (Pydantic frozen workaround)
        items = self._items.copy()
        items.append(item)
        object.__setattr__(self, "_items", items)

        # Recalculate total
        new_total = sum(i.price * i.quantity for i in items)
        object.__setattr__(self, "total", new_total)

        # Record event
        event = ItemAdded(aggregate_id=str(self.id), item_id=item.id)
        self._domain_events.append(event)
```

**Key Features:**
- Event collection via `_domain_events` private attribute
- Versioning via `_version` for optimistic concurrency
- Generic ID type support (str, int, UUID)
- ID auto-generation via `IIDGenerator` protocol

### DomainEvent

Immutable fact with full tracing context:

```python
from cqrs_ddd_core.domain.events import DomainEvent

class OrderCreated(DomainEvent):
    aggregate_id: str  # Required for event sourcing
    aggregate_type: str = "Order"
    customer_id: str
    total: float

# Enrich with correlation
enriched = enrich_event_metadata(event, correlation_id="req-123")
```

### ValueObject

Immutable value with structural equality:

```python
from cqrs_ddd_core.domain.value_object import ValueObject

class Money(ValueObject):
    amount: float
    currency: str

price1 = Money(amount=100.0, currency="USD")
price2 = Money(amount=100.0, currency="USD")
print(price1 == price2)  # True
```

---

## CQRS Layer - Implementation Details

### Mediator

Central dispatch with UoW scope management:

```python
from cqrs_ddd_core.cqrs.mediator import Mediator, get_current_uow

mediator = Mediator(registry=registry, uow_factory=uow_factory)
response = await mediator.send(command)

# Nested commands share UoW
uow = get_current_uow()  # Inherited from parent
```

### Commands & Queries

```python
from cqrs_ddd_core.cqrs.command import Command
from cqrs_ddd_core.cqrs.query import Query

class CreateOrderCommand(Command[str]):
    customer_id: str

class GetOrderQuery(Query[OrderDTO]):
    order_id: str
```

---

## Ports & Adapters

### In-Memory Testing

```python
from cqrs_ddd_core.adapters.memory import InMemoryRepository, InMemoryUnitOfWork

uow = InMemoryUnitOfWork()
uow.orders = InMemoryRepository[Order, str]()

# Fast unit tests without database
async with uow:
    await uow.orders.add(order)
    await uow.commit()
```

---

## Best Practices

### ✅ DO: Domain Logic in Aggregates

```python
class Order(AggregateRoot[UUID]):
    def confirm(self) -> None:
        if self.status != "pending":
            raise InvalidOrderStateError(...)
        object.__setattr__(self, "status", "confirmed")
        self._domain_events.append(OrderConfirmed(...))
```

### ❌ DON'T: Anemic Domain Model

```python
# Business logic in services - BAD!
class OrderService:
    def confirm(self, order: Order) -> None:
        order.status = "confirmed"
```

---

## Summary

**Key Features:**
- ✅ Zero infrastructure dependencies
- ✅ Type-safe with full generic support
- ✅ Event sourcing ready
- ✅ Protocol-based ports
- ✅ In-memory adapters for testing
- ✅ Automatic correlation context
- ✅ Pluggable instrumentation hooks

**Package Ecosystem:**
- `cqrs-ddd-core` - Pure Python foundation (this package)
- `cqrs-ddd-advanced` - Sagas, TCC, background jobs
- `cqrs-ddd-persistence-sqlalchemy` - SQL persistence
- `cqrs-ddd-persistence-mongo` - MongoDB persistence
- `cqrs-ddd-infrastructure-redis` - Redis adapters

---

**Last Updated:** February 22, 2026
**Package Version:** 0.1.0
**Maintained by:** CQRS-DDD Toolkit Team
