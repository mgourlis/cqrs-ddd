# CQRS-DDD Toolkit

A composable, enterprise-grade Python framework for **Domain-Driven Design (DDD)** and **CQRS** applications. This document describes the **implemented** architecture—what exists today and how to use it.

---

## Implemented Architecture

The toolkit is built as a monorepo of five **implemented** packages. Dependencies flow inward: infrastructure and persistence depend on core; advanced and specifications extend core without introducing infrastructure.

```
                    ┌─────────────────────────────────────────────────────────┐
                    │                     cqrs-ddd-core                        │
                    │  Domain • CQRS • Ports • Middleware • Validation • Fakes │
                    └─────────────────────────────────────────────────────────┘
                                              │
           ┌──────────────────────────────────┼──────────────────────────────────┐
           │                                  │                                  │
           ▼                                  ▼                                  ▼
┌──────────────────────┐          ┌──────────────────────┐          ┌──────────────────────┐
│ cqrs-ddd-advanced-   │          │ cqrs-ddd-            │          │ cqrs-ddd-persistence- │
│ core                 │          │ specifications        │          │ sqlalchemy           │
│ Sagas • Event        │          │ Specification pattern  │          │ Write-side: Repo,    │
│ Sourcing • Jobs •    │          │ AST • Operators •      │          │ UoW, Outbox, Event   │
│ Scheduling • Undo    │          │ In-memory evaluator   │          │ Store • Spec compiler│
└──────────────────────┘          └──────────────────────┘          └──────────────────────┘
           │                                  │                                  │
           │                                  └──────────────┬───────────────────┘
           │                                                 │
           ▼                                                 ▼
┌──────────────────────┐                          SQLAlchemy compiles
│ cqrs-ddd-persistence-│                          specifications to
│ sqlalchemy [advanced]│                          WHERE clauses
│ Saga • Jobs •        │
│ Snapshots • Scheduler│
└──────────────────────┘

┌──────────────────────┐
│ cqrs-ddd-redis       │  ← Implements ILockStrategy, ICacheService from core
│ Cache • Redlock •    │    Used by outbox workers, sagas, CachingRepository
│ Fifo locking         │
└──────────────────────┘
```

### Implemented Packages (5)

| Package | PyPI name | Role |
|:--------|:----------|:-----|
| **core** | `cqrs-ddd-core` | Domain primitives (`AggregateRoot`, `DomainEvent`, `ValueObject`), CQRS (`Command`, `Query`, `Mediator`, `EventDispatcher`), ports (`IRepository`, `IUnitOfWork`, `IEventStore`, `IOutboxStorage`, `IMessagePublisher`, `IMessageConsumer`, `ILockStrategy`, `ICacheService`), middleware pipeline, validation, in-memory fakes. **Zero infrastructure dependencies.** |
| **advanced** | `cqrs-ddd-advanced-core` | Sagas, event sourcing, background jobs, scheduling, conflict resolution, snapshots, upcasting, undo/redo. Depends only on core. |
| **specifications** | `cqrs-ddd-specifications` | Specification pattern: composable query AST, operators, in-memory evaluator, hooks. Used by persistence for type-safe filtering. |
| **persistence/sqlalchemy** | `cqrs-ddd-persistence-sqlalchemy` | Write-side persistence: `SQLAlchemyRepository`, `SQLAlchemyUnitOfWork`, `SQLAlchemyOutboxStorage`, `SQLAlchemyEventStore`, specification-to-SQL compiler. Optional: saga/job/snapshot/scheduler persistence. |
| **infrastructure/redis** | `cqrs-ddd-redis` | `RedisCacheService` (ICacheService), `RedlockLockStrategy`, `FifoRedisLockStrategy` (ILockStrategy). Used for distributed locking and caching. |

Detailed module-by-module breakdown: [docs/package-organization.md](docs/package-organization.md).

---

## Technology Stack

- **Python**: 3.10, 3.11, 3.12
- **Domain**: Pydantic v2
- **Write-side persistence**: SQLAlchemy 2.0 (async) / PostgreSQL (SQLite for tests)
- **Caching / locking**: Redis (optional; in-memory fakes in core for tests)

---

## Core Philosophy

1. **Strict isolation** — `cqrs-ddd-core` has no infrastructure dependencies. It defines protocols; adapters live in other packages.
2. **Intent-based packaging** — No generic "utils"; each package has a clear role (messaging, caching, persistence, etc.).
3. **Polyglot persistence** — Write side (Postgres/SQLAlchemy) is separate from read side (Mongo, planned). Sync via projection workers (planned).

---

## Implementation Rules

- **Composition over inheritance** — Repositories use mixins: e.g. `class OrderRepo(MultitenantMixin, CachingMixin, SQLAlchemyRepository)`.
- **Context propagation** — Use `ContextVar` for tenant/user; domain methods stay signature-pure (no `tenant_id` in parameters).
- **One-way data flow** — Read models are updated from events; they never write back to the event store.
- **Interface segregation** — Domain depends on `IBlobStorage` (core), not on concrete storage SDKs.

---

## Install and Use

From the repo root (monorepo):

```bash
uv sync
# or
pip install -e "packages/core" -e "packages/advanced" -e "packages/specifications" \
  -e "packages/persistence/sqlalchemy" -e "packages/infrastructure/redis"
```

Optional extras:

```bash
# GeoPackage / SpatiaLite (spatial queries)
pip install cqrs-ddd-persistence-sqlalchemy[geometry]
pip install cqrs-ddd-core[geometry]

# Advanced persistence (sagas, jobs, snapshots, scheduler)
pip install cqrs-ddd-persistence-sqlalchemy[advanced]
```

At startup, for spatial support:

```python
from cqrs_ddd_persistence_sqlalchemy import init_geopackage
init_geopackage(engine)
```

- **Safe** (after mapping registration): ST_Intersects, ST_Within, ST_Contains, ST_Overlaps, ST_Crosses, ST_Touches, ST_Disjoint, ST_Equals, ST_Distance.
- **SpatiaLite-specific**: ST_Transform, ST_Length, ST_Buffer, etc. use `register_spatialite_mappings()`.
- **Missing in SpatiaLite**: ST_DWithin, ST_MakeEnvelope — package provides `@compiles` overrides to ST_Distance and BuildMbr.

---

## Roadmap (Planned Packages)

The following are specified in the architecture but **not yet implemented** (placeholder directories or documented only):

- **Persistence**: `cqrs-ddd-persistence-mongo` (read-side), `cassandra` (future).
- **Engines**: `cqrs-ddd-projections` (write→read sync).
- **Features**: identity, access-control, multitenancy, observability, audit, analytics, filtering, feature-flags.
- **Infrastructure**: messaging (RabbitMQ/Kafka/SQS adapters), file-storage, notifications.
- **Bridges**: FastAPI, Django, GraphQL.
- **Tooling**: CLI, container (DI / composition root).

See [system-prompt.md](system-prompt.md) and [docs/package-organization.md](docs/package-organization.md) for full planned ecosystem and package roles.
