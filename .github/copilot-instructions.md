# GitHub Copilot Instructions: CQRS-DDD Toolkit

Follow these rules when suggesting code. These align with `.cursorrules` and the project's README.

## 1. Project layout and packages

- **Monorepo:** Code lives under `packages/`. Do not assume legacy top-level packages (e.g. `cqrs-ddd-core/`).
- **Five implemented packages:**
  - `packages/core` — Domain primitives, CQRS, ports, in-memory adapters. **Zero infrastructure dependencies.**
  - `packages/advanced` — Sagas, TCC, background jobs, scheduling, conflict resolution, snapshots, upcasting, undo.
  - `packages/specifications` — Specification pattern and query building.
  - `packages/persistence/sqlalchemy` — Write-side persistence (event store, outbox, repositories).
  - `packages/infrastructure/redis` — Redis-backed adapters (cache, locks, etc.).
- **Planned packages** under `packages/persistence/`, `packages/infrastructure/`, `packages/features/`, etc. Each may have a `.prompt.md`. Global rules and architecture: `/README.md`.

## 2. Core philosophy and terminology

- **Layers:** Domain (entities, `AggregateRoot`, events, value objects) → Application (commands, queries, handlers, DTOs) → Infrastructure (repositories, adapters) → Presentation (FastAPI, CLI). Do not import infrastructure into domain or application.
- **Naming:** Use `AggregateRoot` (not "Aggregate"). Use `Saga` / `SagaState` / `SagaManager` as in the advanced package.
- **Strict isolation:** `packages/core` must remain pure Python (no SQLAlchemy, Redis, etc.). Only stdlib and optional Pydantic.
- **Persistence:** State-stored aggregates with outbox by default. Events and side effects go through the outbox in the same transaction.
- **Serialization:** Domain events must be JSON/BSON-serializable; implement `.model_dump()` consistently.
- **Mixins:** Use mixins for cross-cutting concerns (e.g. `AuditableMixin`, `ArchivableMixin`). Avoid deep inheritance. Prefer composition over inheritance.

## 3. Protocols and implementations

- **Ports = Protocols:** All ports are `typing.Protocol` with `@runtime_checkable`. Defined under each package's `ports/`.
- **Explicit protocol extension:** Adapters and middleware must **declare** the protocol they implement (e.g. `class InMemoryOutboxStorage(IOutboxStorage):`). Relying only on structural typing is not enough.
- **Repository search:** `IRepository.search()` returns `SearchResult[T]`, not `list[T]`. Use the protocol's `SearchResult` (await for list, or `.stream()` for iteration).
- **Workers:** Background workers implement `IBackgroundWorker` and use a **reactive** pattern: `trigger()` plus polling fallback.

## 4. Implementation standards

- **Python:** Target Python 3.12+. Optimize for 3.14+ features where possible.
- **Pydantic:** Use Pydantic for `AggregateRoot`, `DomainEvent`, `Command` where applicable. Use `ConfigDict(frozen=True)` for immutability where needed.
- **JSON in persistence:** In SQLAlchemy packages, use the project's `JSONType` (or equivalent) for Postgres/SQLite compatibility in tests.
- **Optimistic locking:** Aggregate persistence must support a `version` field and enforce it on updates.
- **Immutability:** Domain events and commands should be immutable (e.g. `frozen=True`).
- **Async:** All repository, UoW, event store, outbox, and worker lifecycle methods are `async`.
- **Typing:** Use strict type hints and `Generic[T]` for repositories/aggregates. Use `from __future__ import annotations` in modules.
- **Context:** Use `ContextVar` for tenant and user context; keep domain method signatures free of `tenant_id`/user parameters.

## 5. File and structure conventions

- **Ports:** Protocol definitions live in `ports/` (e.g. `ports/repository.py`, `ports/outbox.py`).
- **Adapters:** In-memory or test doubles live under `adapters/memory/` (or package-specific `adapters/`). They must explicitly implement the corresponding port.
- **Sagas (advanced):** Hand-written sagas must set class-level `listens_to`. For declarative sagas without subclassing, use `SagaBuilder`.

## 6. Tooling and quality

- **Lint/format:** Use `ruff`. **Types:** Use `pyright`. **Tasks:** Use `nox` where configured.
- **Tests:** Unit tests under `[package]/tests/` or `[package]/[package]_tests/`; integration/architecture tests under `tests/` at repo root. Use pytest. Enforce layer boundaries via architecture tests (e.g. **pytest-archon**). Prefer **Polyfactory** for test data and **Hypothesis** for property-based tests where useful.
- **Coverage:** Aim for high coverage (>80% where practical) on domain and application code; exclude trivial boilerplate.

## 7. Testing practices

- **TDD:** Prefer writing tests before or alongside domain/application logic when adding behavior.
- **In-memory first:** Prefer in-memory adapters from core/advanced for unit tests; avoid real DBs unless integration tests require it.
- **Isolation:** Do not let core depend on persistence or messaging packages. Respect dependency direction (e.g. advanced → core, persistence → core).

## 8. Exceptions

- **Prefer package exceptions** over bare `ValueError` / `RuntimeError`. Use `cqrs_ddd_core.primitives.exceptions` and package-specific modules (e.g. `cqrs_ddd_advanced_core.exceptions`).
- **Hierarchy:** Core defines `CQRSDDDError` and categories (`DomainError`, `HandlerError`, `ValidationError`, `PersistenceError`). Packages add concrete types that inherit from these.
- **When to use what:** **DomainError** / **JobStateError** — invalid domain state or state-machine transitions. **HandlerError** / **HandlerNotRegisteredError** — no handler or handler failure. **ValidationError** / **SagaConfigurationError** — invalid configuration or build-time validation. **SagaStateError** — invalid saga runtime state. **PersistenceError** — repository, event store, or UoW failures.
- Use `ValueError` only for truly generic argument validation when no package exception fits.

## Example: Repository protocol

```python
from __future__ import annotations
from typing import Protocol, TypeVar
from .domain.aggregate import Order, AggregateRoot

T = TypeVar("T", bound=AggregateRoot)

class IOrderRepository(Protocol[T]):
    async def add(self, entity: T) -> None: ...
    async def get(self, id: str) -> T | None: ...
```

Refer to `/README.md` for full architecture and package ecosystem. The project uses a Python virtual environment in `.venv`.
