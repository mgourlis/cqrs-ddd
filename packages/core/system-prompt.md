# Module Architecture Guide: `cqrs-ddd-core`

**Role:** The Foundation.
**Dependency Policy:** **Zero Infrastructure Dependencies.**
* **Pydantic:** **Required.** `pydantic>=2.5.0` is the single non-stdlib dependency. All base classes inherit from `pydantic.BaseModel` directly.
* **Standard Lib:** `typing`, `abc`, `uuid`, `datetime`, `contextvars`, `enum`, `logging`.

---

## **1. Directory Structure**

```text
cqrs_ddd_core/
├── domain/                      # DDD Primitives
│   ├── aggregate.py             # AggregateRoot[ID] (Pydantic-enabled)
│   ├── events.py                # DomainEvent (Pydantic-enabled), enrich_event_metadata()
│   ├── value_object.py          # ValueObject (Immutable Pydantic Model)
│   ├── event_registry.py        # EventTypeRegistry (type→class mapping, hydration)
│   └── mixins.py                # AuditableMixin (Timestamps only)
├── cqrs/                        # CQRS Primitives
│   ├── command.py               # Command (Immutable Pydantic Model)
│   ├── query.py                 # Query (Immutable Pydantic Model)
│   ├── handler.py               # ICommandHandler, IQueryHandler, IEventHandler protocols
│   ├── response.py              # CommandResponse, QueryResponse wrappers
│   ├── mediator.py              # Mediator (ContextVar UoW, nested command scope)
│   ├── registry.py              # Handler Registry (__init_subclass__ auto-discovery)
│   ├── event_dispatcher.py      # EventDispatcher (priority + background dual-queue)
│   └── bus.py                   # ICommandBus, IQueryBus protocols
├── ports/                       # Infrastructure Interfaces (Ports)
│   ├── repository.py            # IRepository[T] Protocol
│   ├── uow.py                   # IUnitOfWork Protocol
│   ├── event_store.py           # IEventStore Protocol + StoredEvent dataclass
│   ├── outbox.py                # IOutboxStorage Protocol
│   ├── event_dispatcher.py      # IEventDispatcher Protocol
│   ├── middleware.py            # IMiddleware Protocol
│   └── validation.py            # IValidator Protocol
├── middleware/                   # Middleware Pipeline (pure logic)
│   ├── base.py                  # Middleware protocol, MiddlewareDefinition, pipeline builder
│   ├── registry.py              # MiddlewareRegistry (declarative registration)
│   └── builtin.py               # LoggingMiddleware, ValidatorMiddleware, AuthorizationMiddleware,
│                                #   AttributeInjectionMiddleware, EventStorePersistenceMiddleware
├── validation/                   # Validation System (pure logic)
│   ├── result.py                # ValidationResult (errors dict + factory methods)
│   ├── composite.py             # CompositeValidator (chains validators)
│   └── pydantic.py              # PydanticValidator (async context + field discovery)
├── primitives/                   # Utilities
│   ├── exceptions.py            # DomainError, ConcurrencyError, ValidationError, EntityNotFoundError,
│   │                            #   AuthorizationError, CQRSDDDError, EventStoreError, OutboxError
│   ├── result.py                # Result[T, E] Monad
│   ├── id_generator.py          # ID generation utilities
│   └── scanning.py              # scan_packages() auto-discovery utility
└── testing/                      # In-Memory Fakes for Unit Testing
    ├── memory_repo.py           # InMemoryRepository
    ├── memory_uow.py            # InMemoryUnitOfWork
    ├── memory_event_store.py    # InMemoryEventStore
    └── memory_outbox.py         # InMemoryOutboxStorage
```

## **2. Implementation Rules**

### **A. The Hybrid Base Classes (`domain/`)**

**Strategy:** All base classes inherit directly from `pydantic.BaseModel`. Pydantic is a required dependency.

**`DomainEvent`**
* **Fields:** `event_id` (UUID), `occurred_at` (UTC), `version` (int), `metadata` (dict), `correlation_id` (optional), `causation_id` (optional).
* **Serialization:** Pydantic `.model_dump()` is used directly.
* **Immutability:** Events use `model_config = ConfigDict(frozen=True)`.
* **Auto-Registration:** `__init_subclass__` must register each event type in the `EventTypeRegistry` for hydration from stored events.

**`EventTypeRegistry`**
* **Role:** Maps `event_type_name: str` → `Type[DomainEvent]` for hydration from the event store.
* **Auto-Registration:** Via `DomainEvent.__init_subclass__`.
* **Manual Registration:** `register(name, cls)` for cross-module events.
* **Hydration:** `hydrate(event_type: str, data: dict) -> DomainEvent`.

**`AggregateRoot[ID]`**
* **Generics:** Must be Generic over `ID` to support `UUID`, `int`, or `str`.
* **Fields:** `id: ID`, `_events` (Private list), `_version` (Private int).
* **Mixins:** Inherits `AuditableMixin` (created_at, updated_at).
* **Lifecycle:** **No Soft Delete Mixins.** Use explicit Status Enums (e.g., `status: OrderStatus.CANCELLED`) instead of `is_deleted` flags.
* **Safety:** The `_events` list and `_version` must be excluded from serialization (`exclude=True` or `PrivateAttr`).

**`Modification`**
* **Role:** DTO bundling an entity with its collected domain events. Returned by command handlers.
* **Fields:** `entity: T`, `events: List[DomainEvent]`.

### **B. CQRS Primitives (`cqrs/`)**

**`Command` & `Query`**
* **Base:** Inherit from `pydantic.BaseModel` directly.
* **Immutability:** Use `model_config = ConfigDict(frozen=True)`.
* **Metadata:** Commands carry `command_id`, `correlation_id` for tracing.

**`CommandHandler[C, R]` / `QueryHandler[Q, R]` / `EventHandler[E]`**
* **Protocols:** Abstract base classes with a single `handle()` method.
* **Auto-Discovery:** Use `__init_subclass__` to register in the global Handler Registry.
* **Type Safety:** Generic over `C` (command type) and `R` (response type).

**`CommandResponse` / `QueryResponse`**
* **Role:** Wrapper types for handler return values. `CommandResponse` includes events and success status.

**`Mediator`**
* **Role:** The central dispatch point.
* **UoW Scope:** Uses `ContextVars` to detect if it is running inside an existing UnitOfWork (Nested Commands) or needs to start a new one (Root Commands).
* **Pipeline:** Routes through middleware chain before reaching handler.
* **Event Dispatch:** After command execution, dispatches collected events via `EventDispatcher`.

**`Handler Registry`**
* **Auto-Registration:** `__init_subclass__` on handler base classes introspects `handle()` signature to extract command/query type.
* **Lookup:** `get_handler(command_type) -> Type[Handler]`.
* **Conflict Detection:** Raises error if two handlers register for the same command type.

**`EventDispatcher`**
* **Dual-Queue:** Separates priority (in-transaction, sync) and background (post-commit, async) dispatch.
* **Priority Dispatch:** For events that must be handled before the transaction commits.
* **Background Dispatch:** For events that can be handled asynchronously after commit.
* **Ordering:** Handlers execute in registration order within each queue.

### **C. Ports / Interfaces (`ports/`)**

Core defines ONLY the fundamental infrastructure protocols needed by CQRS building blocks. Domain-specific protocols live in their respective packages per the multi-module architecture (see root `system-prompt.md`).

All ports are `typing.Protocol` classes. All IO methods are `async`.

| Protocol | Key Methods | Notes |
|:---|:---|:---|
| `IRepository[T]` | `add`, `get`, `delete` | `T` bound to `AggregateRoot` |
| `IUnitOfWork` | `commit`, `rollback`, `__aenter__`, `__aexit__` | Async context manager |
| `IEventStore` | `append`, `get_events`, `get_by_aggregate` | Includes `StoredEvent` dataclass |
| `IOutboxStorage` | `save_messages`, `get_pending`, `mark_published`, `mark_failed` | Batch operations |
| `IEventDispatcher` | `dispatch_priority`, `dispatch_background` | Dual-queue |
| `IMiddleware` | `apply(command, next)` | LIFO chain |
| `IValidator` | `validate(command) -> ValidationResult` | Composable |

**Protocols defined in other packages (per multi-module architecture):**

| Protocol | Package | Reason |
|:---|:---|:---|
| `ICacheService`, `IDistributedLock` | `cqrs-ddd-caching` | Caching is an optional infrastructure concern |
| `IMessageBroker`, `IMessagePublisher`, `IMessageConsumer` | `cqrs-ddd-messaging` | Messaging is an optional infrastructure concern |
| `ISagaRepository`, `IBackgroundWorker` | `cqrs-ddd-advanced-core` | Advanced patterns own their own contracts |

### **D. Middleware Pipeline (`middleware/`)**

* **LIFO Chain:** Outer middleware executes first, inner middleware executes last.
* **MiddlewareDefinition:** Supports deferred instantiation (lazy loading).
* **MiddlewareRegistry:** Declarative registration with ordering.
* **Builtin Middlewares (5):**
  - `LoggingMiddleware` — Duration, correlation_id, structured logging.
  - `ValidatorMiddleware` — Runs `IValidator.validate()` before handler.
  - `AuthorizationMiddleware` — RBAC/ABAC check using ContextVar user.
  - `AttributeInjectionMiddleware` — Injects ContextVar values (tenant_id, user_id) into commands.
  - `EventStorePersistenceMiddleware` — Auto-persists events from CommandResponse to IEventStore.
* **Note:** `ThreadSafetyMiddleware` lives in `cqrs-ddd-caching` (requires `IDistributedLock`).

### **E. Validation System (`validation/`)**

* **`ValidationResult`:** Structured errors dict with `is_valid`, `errors`, factory methods (`success()`, `failure()`).
* **`CompositeValidator`:** Chains multiple validators; collects all errors (not fail-fast).
* **`PydanticValidator`:** Leverages Pydantic model validation with async context and field discovery.

### **F. Testing Infrastructure (`testing/`)**

In-memory implementations of core ports for unit testing:
* **`InMemoryRepository`:** Dict-backed, supports add/get/delete.
* **`InMemoryUnitOfWork`:** Tracks commit/rollback calls.
* **`InMemoryEventStore`:** List-backed, supports append/query.
* **`InMemoryOutboxStorage`:** List-backed, supports save/get_pending/mark_published.

**Note:** `MemoryCacheService` and `InMemoryLockStrategy` live in `cqrs-ddd-caching`. `InMemorySagaRepository` lives in `cqrs-ddd-advanced-core`. `cached()` / `cache_invalidate()` decorators live in `cqrs-ddd-caching`.

---

## **3. Code Prototypes (Pydantic First)**

Use these snippets to guide the agent implementation.

#### **1. The Mixins (`domain/mixins.py`)**

```python
from datetime import datetime, timezone
from pydantic import BaseModel, Field

class AuditableMixin(BaseModel):
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

#### **2. The Aggregate Root (`domain/aggregate.py`)**

```python
from typing import List, Any, TypeVar, Generic
from .mixins import AuditableMixin
from pydantic import PrivateAttr, ConfigDict

ID = TypeVar("ID")

class AggregateRoot(AuditableMixin, Generic[ID]):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: ID
    _version: int = PrivateAttr(default=0)
    _domain_events: List[Any] = PrivateAttr(default_factory=list)

    def __init__(self, **data: Any):
        super().__init__(**data)
        object.__setattr__(self, "_domain_events", [])
        if not hasattr(self, '_version'):
            object.__setattr__(self, "_version", 0)

    def add_event(self, event: Any) -> None:
        self._domain_events.append(event)
        self._version += 1

    def collect_events(self) -> List[Any]:
        events = list(self._domain_events)
        self._domain_events.clear()
        return events
```

#### **3. Handler Auto-Discovery (`cqrs/handler.py`)**

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TypeVar, Generic, get_type_hints

C = TypeVar("C")  # Command type
R = TypeVar("R")  # Response type

class CommandHandler(ABC, Generic[C, R]):
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Introspect handle() to extract C type, register in global registry
        hints = get_type_hints(cls.handle)
        if 'command' in hints:
            from .registry import handler_registry
            handler_registry.register(hints['command'], cls)

    @abstractmethod
    async def handle(self, command: C) -> R: ...
```

#### **4. Mediator with ContextVar UoW (`cqrs/mediator.py`)**

```python
from __future__ import annotations
from contextvars import ContextVar
from typing import Optional, Any

_current_uow: ContextVar[Optional[Any]] = ContextVar("current_uow", default=None)

class Mediator:
    def __init__(self, registry, uow_factory, middleware_registry=None, event_dispatcher=None):
        self._registry = registry
        self._uow_factory = uow_factory
        self._middleware_registry = middleware_registry
        self._event_dispatcher = event_dispatcher

    async def send(self, command) -> Any:
        existing_uow = _current_uow.get()
        if existing_uow:
            return await self._dispatch(command)  # Nested: reuse parent UoW
        else:
            async with self._uow_factory() as uow:
                token = _current_uow.set(uow)
                try:
                    result = await self._dispatch(command)
                    await uow.commit()
                    return result
                except Exception:
                    await uow.rollback()
                    raise
                finally:
                    _current_uow.reset(token)
```

---

## **4. Best Practices: ID Generation**

**Recommendation: Use UUIDv7 (Time-Ordered UUIDs)**

While `uuid4` is the Python default, we strongly recommend using **UUIDv7** for your Aggregate IDs.

* **Performance:** UUIDv7 is time-ordered, which prevents index fragmentation in databases.
* **Sorting:** You can sort aggregates by ID to see creation order.

```python
from pydantic import Field
from uuid6 import uuid7
from cqrs_ddd_core.domain.aggregate import AggregateRoot

class Order(AggregateRoot[str]):
    id: str = Field(default_factory=lambda: str(uuid7()))
```

---

## **5. System Prompt for Agent Implementation**

> **Instruction:**
> Implement the `cqrs-ddd-core` package.
>
> **Goal:** Create the complete Domain, CQRS, Middleware, Validation, and Testing foundation, prioritizing **Pydantic** for schema definition and validation.
>
> **Constraints:**
> 1.  **Pydantic Required:** `pydantic>=2.5.0` is a hard dependency. All base classes inherit `pydantic.BaseModel` directly. No fallback code.
> 2.  **Zero Infrastructure Dependencies:** No database drivers, no Redis, no message brokers.
> 3.  **Immutability:** Events and Commands must be immutable (`frozen=True`).
> 4.  **Interfaces:** Use `typing.Protocol` for core ports only (7 protocols: Repository, UoW, EventStore, Outbox, EventDispatcher, Middleware, Validator). Other protocols live in their respective packages per the multi-module architecture.
> 5.  **Generics:** `AggregateRoot` must be `Generic[ID]` to support Int/UUID.
> 6.  **Mixins:** Implement `AuditableMixin` for `created_at`/`updated_at`. **DO NOT** implement Soft Delete.
> 7.  **Mediator:** Must use ContextVar for UoW scope detection (nested vs root commands).
> 8.  **Handler Registry:** Auto-discovery via `__init_subclass__`.
> 9.  **EventDispatcher:** Dual-queue (priority + background).
> 10. **EventTypeRegistry:** Auto-registration of DomainEvent subclasses.
> 11. **Middleware Pipeline:** LIFO chain with 5 builtin middlewares (`ThreadSafetyMiddleware` lives in `cqrs-ddd-caching`).
> 12. **Validation:** `ValidationResult` + `CompositeValidator` + `PydanticValidator`.
> 13. **Testing Fakes:** In-memory implementations of core ports (4 fakes: Repo, UoW, EventStore, Outbox). Cache/Lock fakes live in `cqrs-ddd-caching`.
> 14. **`__init__.py` Exports:** All public APIs must be re-exported from package root.
>
> **Output (priority order):**
> 1.  `domain/aggregate.py`, `domain/events.py`, `domain/event_registry.py`, `domain/mixins.py`, `domain/value_object.py`
> 2.  `cqrs/handler.py`, `cqrs/response.py`, `cqrs/mediator.py`, `cqrs/registry.py`, `cqrs/event_dispatcher.py`
> 3.  `ports/` — all 7 protocol files
> 4.  `middleware/base.py`, `middleware/registry.py`, `middleware/builtin.py`
> 5.  `validation/result.py`, `validation/composite.py`, `validation/pydantic.py`
> 6.  `primitives/exceptions.py`, `primitives/scanning.py`
> 7.  `testing/` — all 4 in-memory implementations

---

## **6. Analysis & Validation Guidelines**

When reviewing or generating code in `cqrs-ddd-core`, systematically apply these checks.

### **6.1 Import Isolation (Blocker)**

Run these checks on every PR or code generation:
- `grep -r "import sqlalchemy" src/` → MUST return zero results
- `grep -r "import redis" src/` → MUST return zero results
- `grep -r "import motor" src/` → MUST return zero results
- `grep -r "import aio_pika" src/` → MUST return zero results
- `grep -r "import boto" src/` → MUST return zero results
- Only allowed non-stdlib imports: `pydantic` (optional, with fallback guard)

### **6.2 Pydantic Verification**

- All base classes inherit from `pydantic.BaseModel` directly (no `HAS_PYDANTIC` guards)
- `model_config = ConfigDict(frozen=True)` used for Events and Commands
- `.model_dump()` and `.model_copy()` are used directly
- No fallback code paths exist in the codebase

### **6.3 Protocol Completeness**

- All 7 port protocols define complete method signatures with full type hints
- All IO-bound methods are `async def` (repository, UoW, event store, outbox)
- Protocols use `typing.Protocol` (not `abc.ABC`) — consumers can implement without inheriting
- `IRepository[T]` is properly generic with `T` bound to `AggregateRoot`
- No protocol in `ports/` belongs to another package (no `ICacheService`, `ISagaRepository`, `IMessageBroker`)

### **6.4 Domain Integrity**

- `DomainEvent` is immutable (`frozen=True` in Pydantic, `__setattr__` override in fallback)
- `Command` is immutable (`frozen=True`)
- `AggregateRoot` is `Generic[ID]` — supports `UUID`, `int`, `str` without code changes
- `_events` and `_version` are excluded from serialization (`PrivateAttr` or `exclude=True`)
- No `is_deleted`, `SoftDeleteMixin`, or `deleted_at` anywhere in the codebase
- `EventTypeRegistry` auto-registers via `DomainEvent.__init_subclass__`
- `collect_events()` clears the event list after returning (one-time collection)

### **6.5 Mediator Correctness**

- Uses `ContextVar` for UoW scope detection (nested vs root commands)
- Nested commands reuse the parent UoW (no double-commit)
- Root commands create a new UoW, commit on success, rollback on failure
- After command execution, collects events from `CommandResponse` and dispatches via `EventDispatcher`
- Middleware pipeline executes in correct LIFO order before handler

### **6.6 Middleware Pipeline**

- LIFO ordering: first registered = outermost wrapper
- Exactly 5 builtin middlewares (NO `ThreadSafetyMiddleware` — that's in `cqrs-ddd-caching`)
- Each middleware calls `await next(command)` to pass control to the next in chain
- Middleware can short-circuit (e.g., `AuthorizationMiddleware` rejects unauthorized commands)
- `MiddlewareRegistry` supports declarative registration with ordering/priority

### **6.7 Test Quality**

- All 4 in-memory fakes exist and implement their respective `I*` protocols
- Tests achieve >80% code coverage
- At least one test per protocol method per fake (e.g., `test_memory_repo_add`, `test_memory_repo_get`, `test_memory_repo_delete`)
- No test depends on infrastructure (no DB connections, no Redis, no file system)

### **6.8 Anti-Pattern Detection**

| Pattern | Detection | Fix |
|:---|:---|:---|
| Cache/Lock protocols in core | `ICacheService` or `IDistributedLock` in `ports/` | Move to `cqrs-ddd-caching` |
| Saga protocols in core | `ISagaRepository` or `IBackgroundWorker` in `ports/` | Move to `cqrs-ddd-advanced-core` |
| Messaging protocols in core | `IMessagePublisher` or `IMessageConsumer` in `ports/` | Move to `cqrs-ddd-messaging` |
| Infrastructure import | `from sqlalchemy` / `import redis` anywhere | Remove — use Protocol instead |
| Mutable Event | `DomainEvent` without `frozen=True` | Add `model_config = ConfigDict(frozen=True)` |
| Missing correlation_id | Handler doesn't propagate `correlation_id` to events | Copy from command to each event in handler |
| Mutable Command | `Command` subclass without `frozen=True` | Enforce immutability via model config |
| Sync IO in ports | Protocol method without `async def` for IO operations | All IO ports must be async |

### **6.9 Completeness Verification**

Before marking the core package as "Phase 1 Complete", verify:

```
domain/
  ✅ aggregate.py      — AggregateRoot[ID] with Generic, PrivateAttr events/version
  ✅ events.py         — DomainEvent (frozen), enrich_event_metadata(), .model_dump()
  ✅ event_registry.py — EventTypeRegistry with __init_subclass__ auto-registration
  ✅ mixins.py         — AuditableMixin (created_at, updated_at)
  ✅ value_object.py   — Immutable ValueObject base

cqrs/
  ✅ command.py         — Command (frozen, command_id, correlation_id)
  ✅ query.py           — Query (frozen, query_id, correlation_id)
  ✅ handler.py         — CommandHandler[C,R], QueryHandler[Q,R], EventHandler[E]
  ✅ response.py        — CommandResponse, QueryResponse
  ✅ mediator.py        — Mediator with ContextVar UoW + middleware pipeline
  ✅ registry.py        — HandlerRegistry with __init_subclass__ discovery
  ✅ event_dispatcher.py — EventDispatcher (priority + background queues)
  ✅ bus.py             — ICommandBus, IQueryBus protocols

ports/
  ✅ repository.py      — IRepository[T]
  ✅ uow.py             — IUnitOfWork
  ✅ event_store.py     — IEventStore + StoredEvent
  ✅ outbox.py          — IOutboxStorage
  ✅ event_dispatcher.py — IEventDispatcher
  ✅ middleware.py       — IMiddleware
  ✅ validation.py      — IValidator

middleware/
  ✅ base.py            — Middleware protocol, MiddlewareDefinition, pipeline builder
  ✅ registry.py        — MiddlewareRegistry
  ✅ builtin.py         — 5 builtin middlewares

validation/
  ✅ result.py          — ValidationResult
  ✅ composite.py       — CompositeValidator
  ✅ pydantic.py        — PydanticValidator

primitives/
  ✅ exceptions.py      — All domain exceptions
  ✅ result.py          — Result[T, E] monad
  ✅ id_generator.py    — ID generation utilities
  ✅ scanning.py        — scan_packages() utility

testing/
  ✅ memory_repo.py     — InMemoryRepository
  ✅ memory_uow.py      — InMemoryUnitOfWork
  ✅ memory_event_store.py — InMemoryEventStore
  ✅ memory_outbox.py   — InMemoryOutboxStorage
```
