# GitHub Copilot Instructions: CQRS-DDD Toolkit

Follow these rules when suggesting code for this project:

## General Principles
- **DDD/CQRS:** Strictly separate read and write models. Use `AggregateRoot` for domain entry points.
- **Modularity:** Respect the package structure. Do NOT import from `infrastructure` into `domain` or `application`.
- **System Prompts:** Always refer to `/system-prompt.md` and any package-specific `system-prompt.md` files (e.g., in `cqrs-ddd-core/`).
- **Persistence:** Favor **State-Stored Aggregates with Outbox**. Aggregates map to their own tables; events go to an `outbox` table in the same transaction.
- **Serialization:** Domain Events **MUST** implement serialization (e.g., `.model_dump()`) for JSON/BSON compatibility.

## Python Standards
- **Type Hints:** Required for all function signatures. Use `from __future__ import annotations`.
- **Async:** Use `async/await` for all repository and external service calls.
- **Pydantic:** Prefer Pydantic v2 for data validation in `core` and `application` layers with standard library fallbacks.
- **JSON Handling:** Use the custom `JSONType` decorator for SQLAlchemy models to ensure cross-dialect (Postgres/SQLite) compatibility.
- **Protocols:** Define interfaces using `typing.Protocol`.

## Layered Architecture
1. **Domain Layer:** Entities, `AggregateRoot`, Domain Events, Value Objects. No external dependencies.
2. **Application Layer:** Commands, Queries, Command/Query Handlers, DTOs.
3. **Infrastructure Layer:** Repository implementations (SQLAlchemy/Mongo), external service adapters.
4. **Presentation Layer:** FastAPI routers, CLI commands.

## Code Style
- Use `frozen=True` for Commands and Events.
- Use Mixins for cross-cutting concerns (Multitenancy, Caching, Timestamps).
- Prefer composition over inheritance.
- Use `ContextVars` for tenant and user context.

## Testing & Quality
- **TDD (Test-Driven Development):** Always suggest writing tests before the implementation code.
- **Hybrid Structure:**
  - `[module]/tests/` for unit tests.
  - `/tests/integration/` for toolkit-wide integration.
- **Tools:** Use **Polyfactory** for mocks, **Hypothesis** for complex logic, and **pytest-archon** for architecture validation.
- **Coverage:** Aim for >80% code coverage.

## Example Pattern (Repository)
```python
from typing import Protocol, TypeVar
from .domain.aggregate import Order, AggregateRoot

T = TypeVar("T", bound=AggregateRoot)

class IOrderRepository(Protocol[T]):
    async def add(self, entity: T) -> None: ...
    async def get(self, id: str) -> T | None: ...
```
