# Module Architecture Guide: `cqrs-ddd-persistence-sqlalchemy`

**Role:** The Write Side Engine.
**Dependency Policy:**
* **Mandatory:** `sqlalchemy[asyncio]>=2.0.0`, `asyncpg`, `cqrs-ddd-core`.
* **Optional:** `cqrs-ddd-advanced-core` (for Outbox, Saga, Background Job persistence impls).
* **Purpose:** Provide ACID-compliant implementations of `IUnitOfWork`, `IRepository`, `IOutboxStorage`, `IEventStore`, `ISagaRepository`, and Background Job persistence using the State + Outbox pattern.

---

## **1. Directory Structure**

```text
cqrs_ddd_persistence_sqlalchemy/
├── outbox/
│   ├── models.py            # OutboxMessage (SQLAlchemy Model, BigInteger PK)
│   └── storage.py           # SQLAlchemyOutboxStorage (implements IOutboxStorage)
├── repository/
│   ├── base.py              # SQLAlchemyRepository[T] (Generic Implementation, State + Outbox)
│   └── mixins.py            # MultitenantMixin, AuditMixin (repository-level cross-cutting)
├── event_store/
│   └── sqlalchemy_store.py  # SQLAlchemyEventStoreMixin (implements IEventStore)
├── sagas/
│   └── sqlalchemy_repo.py   # SQLAlchemySagaRepository (implements ISagaRepository)
├── background_jobs/
│   └── sqlalchemy_persistence.py  # SQLAlchemyBackgroundJobPersistence
├── types/
│   └── json.py              # Dialect-agnostic JSON type (Postgres JSONB vs SQLite JSON)
└── unit_of_work.py          # SQLAlchemyUnitOfWork (Session Management)
```

## **2. Implementation Rules**

### **A. Tech Stack: SQLAlchemy 2.0+ (Async)**
* **Async Only:** All DB interactions must happen via `AsyncSession`.
* **Declarative Mapping:** Use `DeclarativeBase` for internal models.
* **Dialect Agnostic:** Code must target **Postgres** (Production) but support **SQLite** (Testing).
* **JSON Handling:** **CRITICAL.** Do not use `JSONB` directly. Use a custom `TypeDecorator` to switch between `JSONB` (PG) and `JSON` (SQLite).

### **B. The Outbox Schema**
The "Write Side" uses the Outbox Pattern to capture side effects reliably.

**`OutboxModel` (Table: `outbox`)**
* `id` (BigInteger, PK, Auto-increment) → **BigInt** is strictly better than UUID for ordering/indexing log tables.
* `event_id` (String) → The Domain Event's ID.
* `event_type` (String) → The Class Name (e.g., "OrderCreated").
* `aggregate_id` (String) → **MUST be String** to support both UUID and Int IDs from Domain.
* `payload` (JSON) → The serialized Domain Event (`.model_dump()`).
* `status` (Enum) → `PENDING`, `PUBLISHED`, `FAILED`.
* `created_at` (DateTime) → Timestamp.
* `retry_count` (Integer) → For retry logic.
* `last_error` (String, nullable) → Last failure message.

**Compound Index:** `ix_outbox_pending_id` on `(status, id)` for efficient polling of oldest pending messages.

### **C. The Generic Repository (`SQLAlchemyRepository[T]`)**
* **Strategy:** **State + Outbox.**
* **Role:** Saves the **Current State** (Aggregate Table) and **Events** (Outbox Table) in a single atomic transaction.
* **Mechanism:**
    1.  `add(entity)` adds the entity to the session.
    2.  It calls `entity.collect_events()`.
    3.  It creates `OutboxMessage` records for each event.
    4.  It strictly casts `aggregate_id=str(entity.id)` for polymorphic ID support.
* **Optimistic Locking:** The Repository should map the `_version` field and include `WHERE version = :expected` on updates.

### **D. The Unit of Work (`SQLAlchemyUnitOfWork`)**
* **Context Manager:** `async with uow:`.
* **Session Management:** Wraps an `AsyncSession`.
* **Auto-rollback:** On exception in `__aexit__`.
* **Explicit commit:** `await uow.commit()`.

### **E. Outbox Storage (`SQLAlchemyOutboxStorage`)**
* Implements `IOutboxStorage` from `cqrs-ddd-core/ports/outbox.py`.
* **`save_messages(messages)`** — Bulk insert `OutboxMessage` rows.
* **`get_pending(batch_size)`** — Query `WHERE status = PENDING ORDER BY id LIMIT :batch_size`.
* **`mark_published(message_id)`** — Update status to `PUBLISHED`.
* **`mark_failed(message_id, error)`** — Update status to `FAILED`, increment `retry_count`, set `last_error`.

### **F. Event Store (`SQLAlchemyEventStoreMixin`)**
* Implements `IEventStore` from `cqrs-ddd-core/ports/event_store.py`.
* Stores `StoredEvent` records with aggregate_id, event_type, version, payload.
* Supports append, get_events, get_by_aggregate operations.

### **G. Saga Repository (`SQLAlchemySagaRepository`)**
* Implements `ISagaRepository` from `cqrs-ddd-advanced-core` (NOT from core — saga protocols are owned by advanced-core).
* Stores serialized `SagaState` as JSON (using `JSONType` for dialect compatibility).
* Supports `save`, `load`, `list_pending` operations.
* Uses optimistic locking via `SagaState.version`.

### **H. Background Job Persistence (`SQLAlchemyBackgroundJobPersistence`)**
* Persists `BaseBackgroundJob` entities.
* Includes a `BackgroundJobMixin` for SQLAlchemy model definition.
* Supports status lifecycle queries (pending, running, failed, stale).

### **I. Repository Mixins**
* **`MultitenantMixin`** — Automatically appends `WHERE tenant_id = :ctx` using ContextVar.
* **`AuditMixin`** — Auto-populates `created_by`, `updated_by` from ContextVar user.

---

## **3. Code Prototypes**

#### **1. The JSON Type Decorator (`types/json.py`)**

```python
from sqlalchemy.types import TypeDecorator, JSON
from sqlalchemy.dialects.postgresql import JSONB

class JSONType(TypeDecorator):
    """
    Switches between JSONB (Postgres) and JSON (SQLite/Others)
    automatically based on the dialect.
    """
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())
```

#### **2. The Outbox Model (`outbox/models.py`)**

```python
from datetime import datetime, timezone
from enum import Enum as PyEnum
from sqlalchemy import String, Integer, BigInteger, DateTime, Enum, Index
from sqlalchemy.orm import Mapped, mapped_column, DeclarativeBase
from ..types.json import JSONType

class Base(DeclarativeBase):
    pass

class OutboxStatus(str, PyEnum):
    PENDING = "PENDING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"

class OutboxMessage(Base):
    __tablename__ = "outbox"

    # Use BigInteger for indefinite scaling of event logs
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String, index=True)
    aggregate_id: Mapped[str] = mapped_column(String, index=True)  # Polymorphic ID
    payload: Mapped[dict] = mapped_column(JSONType)
    status: Mapped[OutboxStatus] = mapped_column(Enum(OutboxStatus), default=OutboxStatus.PENDING, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True, default=None)

    # Compound index for polling performance (Find oldest pending)
    __table_args__ = (
        Index('ix_outbox_pending_id', 'status', 'id'),
    )
```

#### **3. The Generic Repository (`repository/base.py`)**

```python
from typing import TypeVar, Any
from sqlalchemy.ext.asyncio import AsyncSession
from cqrs_ddd_core.ports.repository import IRepository
from cqrs_ddd_core.domain.aggregate import AggregateRoot
from ..outbox.models import OutboxMessage

T = TypeVar("T", bound=AggregateRoot)

class SQLAlchemyRepository(IRepository[T]):
    def __init__(self, session: AsyncSession, model_cls: type[T]):
        self.session = session
        self.model_cls = model_cls

    async def add(self, entity: T) -> None:
        # 1. Add the Entity State
        self.session.add(entity)

        # 2. Harvest Events -> Outbox
        events = entity.collect_events()
        for event in events:
            msg = OutboxMessage(
                event_id=str(event.event_id),
                event_type=event.__class__.__name__,
                aggregate_id=str(entity.id),  # Cast Generic ID to String
                payload=event.model_dump(),    # Pydantic Serialization
                created_at=event.occurred_at
            )
            self.session.add(msg)

    async def get(self, id: Any) -> T | None:
        return await self.session.get(self.model_cls, id)

    async def delete(self, id: Any) -> None:
        entity = await self.get(id)
        if entity:
            await self.session.delete(entity)
```

#### **4. The Unit of Work (`unit_of_work.py`)**

```python
from sqlalchemy.ext.asyncio import AsyncSession
from cqrs_ddd_core.ports.uow import IUnitOfWork

class SQLAlchemyUnitOfWork(IUnitOfWork):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def __aenter__(self) -> "SQLAlchemyUnitOfWork":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type:
            await self.rollback()
```

#### **5. The Outbox Storage (`outbox/storage.py`)**

```python
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from cqrs_ddd_core.ports.outbox import IOutboxStorage
from .models import OutboxMessage, OutboxStatus

class SQLAlchemyOutboxStorage(IOutboxStorage):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_pending(self, batch_size: int = 100) -> list[OutboxMessage]:
        stmt = (
            select(OutboxMessage)
            .where(OutboxMessage.status == OutboxStatus.PENDING)
            .order_by(OutboxMessage.id)
            .limit(batch_size)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def mark_published(self, message_id: int) -> None:
        stmt = (
            update(OutboxMessage)
            .where(OutboxMessage.id == message_id)
            .values(status=OutboxStatus.PUBLISHED)
        )
        await self.session.execute(stmt)

    async def mark_failed(self, message_id: int, error: str) -> None:
        stmt = (
            update(OutboxMessage)
            .where(OutboxMessage.id == message_id)
            .values(
                status=OutboxStatus.FAILED,
                retry_count=OutboxMessage.retry_count + 1,
                last_error=error,
            )
        )
        await self.session.execute(stmt)
```

---

## **4. System Prompt for Agent Implementation**

> **Instruction:**
> Implement the `cqrs-ddd-persistence-sqlalchemy` package.
>
> **Goal:** Create the complete persistence layer using SQLAlchemy + Asyncpg, including Outbox storage, Event Store, Saga Repository, and Background Job persistence.
>
> **Constraints:**
> 1.  **Strict Async:** Use `sqlalchemy.ext.asyncio`.
> 2.  **State + Outbox:** The `add()` method in the Repository MUST harvest events from the aggregate and save them to the `OutboxMessage` table in the same transaction.
> 3.  **Polymorphism:** The `OutboxMessage.aggregate_id` column must be `String` to handle both UUID and Int IDs.
> 4.  **BigInteger PK:** The `OutboxMessage.id` MUST be `BigInteger` (NOT UUID).
> 5.  **JSON Compatibility:** Implement the `JSONType` decorator to handle Postgres `JSONB` vs SQLite `JSON`.
> 6.  **Clean Architecture:** Implement `SQLAlchemyRepository[T]`, `SQLAlchemyUnitOfWork`, `SQLAlchemyOutboxStorage`, `SQLAlchemyEventStoreMixin`, `SQLAlchemySagaRepository`, `SQLAlchemyBackgroundJobPersistence`.
> 7.  **Repository Mixins:** Implement `MultitenantMixin` (ContextVar tenant_id) and `AuditMixin` (ContextVar user_id).
> 8.  **Optimistic Locking:** Repository should check `_version` on updates.
>
> **Output (priority order):**
> 1.  `types/json.py`
> 2.  `outbox/models.py`, `outbox/storage.py`
> 3.  `repository/base.py`, `repository/mixins.py`
> 4.  `unit_of_work.py`
> 5.  `event_store/sqlalchemy_store.py`
> 6.  `sagas/sqlalchemy_repo.py`
> 7.  `background_jobs/sqlalchemy_persistence.py`

---

## **5. Analysis & Validation Guidelines**

When reviewing or generating code in `cqrs-ddd-persistence-sqlalchemy`, systematically apply these checks.

### **5.1 Async Enforcement (Blocker)**

- ALL database operations use `AsyncSession` from `sqlalchemy.ext.asyncio`
- No synchronous `Session` usage anywhere in the package
- No `session.commit()` outside `UnitOfWork.commit()` — session management is the UoW's responsibility
- No blocking calls (`time.sleep`, sync HTTP) inside async methods
- All public methods that touch the DB are `async def`

### **5.2 Dialect Compatibility**

- `JSONType` TypeDecorator is used for ALL JSON columns — never raw `JSONB`
- Tests run against both SQLite (in-memory, fast) AND Postgres (via testcontainers)
- No Postgres-specific SQL syntax outside the `JSONType` dialect switch and index definitions
- `BigInteger` PK works on both Postgres (native BIGSERIAL) and SQLite (INTEGER with autoincrement)
- String-based aggregate IDs (`str(entity.id)`) handle both UUID and integer PKs

### **5.3 Outbox Atomicity (Critical)**

This is the most important invariant in the package:
- [ ] `Repository.add(entity)` inserts the entity AND outbox messages in the SAME session
- [ ] Outbox messages are created BEFORE `session.commit()` — they are part of the atomic transaction
- [ ] `aggregate_id` is ALWAYS cast via `str(entity.id)` — never a raw UUID object or int
- [ ] `OutboxMessage.id` is `BigInteger` AUTO-INCREMENT (not UUID) — ordering correctness depends on this
- [ ] Compound index `(status, id)` exists on the outbox table for efficient polling
- [ ] Each event from `entity.collect_events()` maps to exactly one `OutboxMessage` row

### **5.4 Optimistic Locking**

- [ ] `Repository.update()` includes `WHERE version = :expected` in the UPDATE clause
- [ ] On zero rows affected (version mismatch), raises `ConcurrencyError` from `cqrs-ddd-core`
- [ ] Version is incremented atomically: `SET version = version + 1`
- [ ] Version check is performed BEFORE flushing events to outbox (prevent orphan outbox entries)

### **5.5 Mixin Integrity**

- [ ] `MultitenantMixin` reads `tenant_id` from `ContextVar` — never from method parameters
- [ ] `MultitenantMixin` raises `TenantContextMissingError` if `TenantContext` is empty (prevents data leakage)
- [ ] `AuditMixin` reads `user_id` from `ContextVar` for `created_by` / `updated_by` fields
- [ ] Mixins compose correctly via MRO: `class OrderRepo(MultitenantMixin, AuditMixin, SQLAlchemyRepository): ...`
- [ ] Mixin filters apply to ALL query methods (get, list, search, count) — not just `get()`

### **5.6 Protocol Implementation Correctness**

| Implementation | Implements | Package Source |
|:---|:---|:---|
| `SQLAlchemyRepository[T]` | `IRepository[T]` | `cqrs-ddd-core` |
| `SQLAlchemyUnitOfWork` | `IUnitOfWork` | `cqrs-ddd-core` |
| `SQLAlchemyOutboxStorage` | `IOutboxStorage` | `cqrs-ddd-core` |
| `SQLAlchemyEventStoreMixin` | `IEventStore` | `cqrs-ddd-core` |
| `SQLAlchemySagaRepository` | `ISagaRepository` | `cqrs-ddd-advanced-core` |
| `SQLAlchemyBackgroundJobPersistence` | (internal contract) | `cqrs-ddd-advanced-core` |

Verify: each implementation's method signatures match the protocol exactly (names, types, async).

### **5.7 Anti-Pattern Detection**

| Pattern | Detection | Fix |
|:---|:---|:---|
| Raw JSONB usage | `from sqlalchemy.dialects.postgresql import JSONB` used directly on columns | Use `JSONType` TypeDecorator |
| UUID outbox PK | `OutboxMessage.id` typed as `UUID` or `String` | Change to `BigInteger` auto-increment |
| Sync session | `from sqlalchemy.orm import Session` | Use `from sqlalchemy.ext.asyncio import AsyncSession` |
| Missing tenant filter | Query executes without tenant context when mixin is applied | Mixin must auto-inject `WHERE tenant_id = :ctx` |
| Commit outside UoW | `session.commit()` called inside repository methods | Only `UnitOfWork.commit()` should call commit |
| Implicit autocommit | Session created with `autocommit=True` | Use explicit UoW transaction boundaries |
| Raw SQL strings | `session.execute(text("SELECT ..."))` with string interpolation | Use parameterized queries or ORM constructs |
| Missing outbox on update | `Repository.update()` doesn't harvest events to outbox | `update()` must call `collect_events()` and create outbox rows |

### **5.8 Completeness Verification**

Before marking the persistence package as "Phase 2 Complete", verify:

```
outbox/
  ✅ models.py           — OutboxMessage (BigInt PK, compound index, JSONType payload)
  ✅ storage.py          — SQLAlchemyOutboxStorage (save, get_pending, mark_published, mark_failed)

repository/
  ✅ base.py             — SQLAlchemyRepository[T] (add with outbox, get, delete, optimistic locking)
  ✅ mixins.py           — MultitenantMixin, AuditMixin

event_store/
  ✅ sqlalchemy_store.py — SQLAlchemyEventStoreMixin (append, get_events, get_by_aggregate)

sagas/
  ✅ sqlalchemy_repo.py  — SQLAlchemySagaRepository (save, load, list_pending, optimistic locking)

background_jobs/
  ✅ sqlalchemy_persistence.py — SQLAlchemyBackgroundJobPersistence (CRUD + lifecycle queries)

types/
  ✅ json.py             — JSONType TypeDecorator (PG JSONB ↔ SQLite JSON)

  ✅ unit_of_work.py     — SQLAlchemyUnitOfWork (async context manager, auto-rollback)
```
