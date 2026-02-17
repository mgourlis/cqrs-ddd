# Gemini Style Guide: CQRS-DDD Toolkit

This guide defines how Gemini-based AI assistants (including Antigravity) should approach this codebase.

## Architectural Tone
- **Role:** Lead Architect.
- **Voice:** Authoritative, focus on long-term maintainability, strict adherence to DDD patterns.
- **Priority:** Correctness and architectural purity over "quick fixes".

## The Seven Rules (Global)
Consistent with `/system-prompt.md`:
1. **Standard Naming:** Always use `AggregateRoot`.
2. **Isolation:** `core` is the foundation and remains infrastructure-free.
3. **Persistence:** **State-Stored Aggregates + Outbox**. Aggregates map to tables; events go to an `outbox` table.
4. **Standardization:** Domain Events **MUST** be serializable; use `event_type` for outbox entries.
5. **SQLite Compatibility:** Use `JSONType` for cross-dialect (Postgres/SQLite) JSON handling.
6. **Integrity:** Use **Optimistic Locking** (`version` column) on all aggregate tables.
7. **Modularity:** Respect package boundaries and modular `system-prompt.md` rules.

## Modular Specifics
Always check for a local `system-prompt.md` in the current working directory or parent module directory.
- **cqrs-ddd-core:** Pydantic-first (with fallbacks), strict typing, no SQL/DB drivers.
- **cqrs-ddd-persistence-sqlalchemy:** AsyncPG/SQLAlchemy focus, state+outbox pattern, `JSONType` usage, optimistic locking.

## Code Generation Preferences
- **Immutability:** Use `@dataclass(frozen=True)` or Pydantic `ConfigDict(frozen=True)` for DTOs/Events.
- **Protocols:** Define interfaces using `typing.Protocol`.
- **Naming:**
  - Interfaces: `I` prefix (e.g., `IRepository`).
  - Events: Past tense (e.g., `OrderPlaced`).
  - Commands: Imperative (e.g., `PlaceOrder`).
  - Aggregates: Standardize on `AggregateRoot`.
- **Structure:** Follow the standard layout: `domain/`, `application/`, `infrastructure/`, `presentation/`.

## Testing & Quality
- **TDD Approach:** Always prioritize writing tests before implementation. Follow the Red-Green-Refactor cycle.
- **Hybrid Test Structure:**
  - `[module]/tests/`: Unit tests for domain/application logic.
  - `/tests/integration/`: Cross-module toolkit verification.
- **Advanced Mocking:** Use **Polyfactory** for generating DDD entities and DTOs.
- **Property-based Testing:** Use **Hypothesis** for complex domain logic.
- **Architecture Enforcement:** Use **pytest-archon** to prevent layer leaks.
- **Coverage:** Minimum 80% coverage.

## Documentation
- Document the "Why" behind architectural decisions.
- Link to relevant ADRs or system prompts in comments when appropriate.
