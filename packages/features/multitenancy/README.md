# CQRS-DDD Multitenancy Module

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests: 562](https://img.shields.io/badge/tests-562%20passing-brightgreen.svg)]()
[![Coverage: 93%](https://img.shields.io/badge/coverage-93%25-brightgreen.svg)]()

Production-ready multitenancy module for CQRS-DDD applications. Provides tenant isolation at every layer — domain, persistence, messaging, caching, and presentation — with three isolation strategies and zero-intrusion MRO mixin composition.

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Architecture Overview](#architecture-overview)
- [Quick Start](#quick-start)
- [Context Management](#context-management)
- [Tenant Resolution](#tenant-resolution)
- [Isolation Strategies](#isolation-strategies)
- [Domain Layer](#domain-layer)
- [Persistence Mixins](#persistence-mixins)
- [CQRS Middleware](#cqrs-middleware)
- [FastAPI Integration](#fastapi-integration)
- [Projections Engine](#projections-engine)
- [Background Jobs & Workers](#background-jobs--workers)
- [Infrastructure](#infrastructure)
- [Tenant Administration](#tenant-administration)
- [Observability](#observability)
- [Testing](#testing)
- [API Reference](#api-reference)

---

## Features

### Core Infrastructure
- **Context Management** — `ContextVar`-based tenant resolution with token-based reset, async-safe propagation, and nested context support
- **Three Isolation Strategies** — Discriminator column, schema-per-tenant (PostgreSQL), and database-per-tenant with LRU-cached connection pools
- **Eight Resolver Strategies** — Header, JWT Claim, Subdomain, Path, Static, Composite, Callable
- **Specification-Based Filtering** — All persistence operations use `AttributeSpecification` for SQL/MongoDB-level tenant filtering
- **System Tenant** — `__system__` sentinel for admin operations that bypass tenant isolation

### Persistence Layer (17 Mixins)
- **Repository** — `MultitenantRepositoryMixin` + `StrictMultitenantRepositoryMixin` for `IRepository`
- **Event Store** — `MultitenantEventStoreMixin` for `IEventStore` (10 methods)
- **Outbox** — `MultitenantOutboxMixin` + `StrictMultitenantOutboxMixin` for `IOutboxStorage`
- **Dispatcher** — `MultitenantDispatcherMixin` for `IPersistenceDispatcher`
- **Persistence Interfaces** — 4 mixins for `IOperationPersistence`, `IRetrievalPersistence`, `IQueryPersistence`, `IQuerySpecificationPersistence`
- **Projections** — `MultitenantProjectionMixin` + `MultitenantProjectionPositionMixin` with document ID namespacing
- **Sagas** — `MultitenantSagaMixin` for `ISagaRepository` (11 methods)
- **Snapshots** — `MultitenantSnapshotMixin` for `ISnapshotStore`
- **Scheduling** — `MultitenantCommandSchedulerMixin` for `ICommandScheduler`
- **Upcasting** — `MultitenantUpcasterMixin` preserving tenant context through event migrations
- **Background Jobs** — `MultitenantBackgroundJobMixin` for `IBackgroundJobRepository` (11 methods)

### Presentation & Middleware
- **CQRS Middleware** — `TenantMiddleware` implementing `IMiddleware` for command/query pipelines
- **FastAPI Integration** — ASGI middleware, dependency injection (`get_current_tenant_dep`, `require_tenant_dep`), public path exclusion

### Infrastructure Adapters
- **Redis Cache** — `MultitenantRedisCacheMixin` with automatic key namespacing (`{tenant_id}:{key}`)
- **Redis Locks** — `MultitenantRedisLockMixin` with tenant-isolated distributed locks
- **Health Checks** — `TenantHealthChecker` + `CompositeTenantHealthChecker` with latency tracking
- **Message Propagation** — `TenantMessagePropagator` for broker context injection/extraction
- **Worker Context** — `TenantAwareJobWorker` for automatic tenant context in background workers

### Projections Engine
- **Handler Wrapping** — `MultitenantProjectionHandler` extracts tenant from events and sets context
- **Replay** — `MultitenantReplayMixin` sets tenant context per event during replay
- **Worker** — `MultitenantWorkerMixin` sets tenant context per event during polling
- **Registry** — `TenantAwareProjectionRegistry` auto-wraps handlers

### Administration
- **Tenant Registry** — Abstract `TenantRegistry` protocol with `InMemoryTenantRegistry` for testing
- **Admin Operations** — Provisioning, deactivation, reactivation, metadata updates, deletion via `TenantAdmin`
- **Schema Router** — PostgreSQL schema-per-tenant with `SET search_path`
- **Database Router** — Database-per-tenant with LRU-cached connection pools and configurable `engine_factory`

### Observability
- **Prometheus Metrics** — Resolution timing, schema switch counts, context error tracking
- **OpenTelemetry Tracing** — Spans for resolution, schema switches, database switches
- Both gracefully no-op when dependencies are not installed

---

## Installation

```bash
pip install cqrs-ddd-multitenancy
```

### Optional Dependencies

```bash
# SQLAlchemy persistence
pip install cqrs-ddd-multitenancy[sqlalchemy]

# FastAPI integration
pip install cqrs-ddd-multitenancy[fastapi]

# Advanced persistence (sagas, snapshots, scheduling, etc.)
pip install cqrs-ddd-multitenancy[advanced]

# Redis adapters (cache, locks)
pip install cqrs-ddd-multitenancy[redis]

# MongoDB adapters
pip install cqrs-ddd-multitenancy[mongo]

# Observability (Prometheus + OpenTelemetry)
pip install cqrs-ddd-multitenancy[observability]

# Everything
pip install cqrs-ddd-multitenancy[all]
```

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│                    Presentation Layer                      │
│  FastAPI TenantMiddleware, get_current_tenant_dep          │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐   │
│  │ HeaderResolver│  │ JwtResolver  │  │SubdomainResolver│  │
│  └──────┬───────┘  └──────┬───────┘  └───────┬───────┘   │
│         └──────────────────┼──────────────────┘           │
│                            ▼                              │
│                   set_tenant(tenant_id) → Token            │
└─────────────────────────────┬────────────────────────────┘
                              │ ContextVar
┌─────────────────────────────▼────────────────────────────┐
│                    Application Layer                      │
│  CQRS TenantMiddleware (IMiddleware)                      │
│  Command/Query pipelines automatically scoped             │
└─────────────────────────────┬────────────────────────────┘
                              │
┌─────────────────────────────▼────────────────────────────┐
│                    Persistence Layer                      │
│  ┌────────────────────────────────────────────┐          │
│  │  MRO Mixin Composition                     │          │
│  │   MultitenantRepositoryMixin               │          │
│  │   + SQLAlchemyRepository / MongoRepository  │          │
│  │   → AttributeSpecification("tenant_id",EQ) │          │
│  └────────────────────────────────────────────┘          │
│  Event Store, Outbox, Sagas, Snapshots, Jobs, etc.       │
└─────────────────────────────┬────────────────────────────┘
                              │
┌─────────────────────────────▼────────────────────────────┐
│                 Infrastructure Layer                      │
│  Redis Cache/Locks (key namespacing)                      │
│  Health Checks, Message Propagation                       │
│  Schema Router (PostgreSQL), Database Router (LRU pool)   │
└──────────────────────────────────────────────────────────┘
```

The tenant ID flows through `ContextVar` from the presentation layer down to every persistence and infrastructure operation. The system tenant (`__system__`) bypasses all filtering.

---

## Quick Start

### 1. Add Multitenancy to Domain Entities

```python
from cqrs_ddd_core import AggregateRoot
from cqrs_ddd_multitenancy.domain import MultitenantMixin

class Order(MultitenantMixin, AggregateRoot[str]):
    """Order aggregate with tenant isolation."""
    customer_id: str
    status: str = "pending"
    total: float = 0.0

# The tenant_id field is required, validated (1-128 chars, alphanumeric/hyphens/underscores)
order = Order(id="order-1", tenant_id="acme-corp", customer_id="cust-42")
order.validate_tenant("acme-corp")  # OK
order.validate_tenant("other")     # raises ValueError
```

### 2. Set Up Tenant Context

```python
from cqrs_ddd_multitenancy import set_tenant, get_current_tenant, reset_tenant

# Token-based context management (safe for nesting)
token = set_tenant("tenant-123")
try:
    tenant_id = get_current_tenant()  # "tenant-123"
    # ... all operations are scoped to this tenant
finally:
    reset_tenant(token)  # restores previous context
```

### 3. Create Tenant-Aware Repository

```python
from cqrs_ddd_multitenancy import MultitenantRepositoryMixin
from cqrs_ddd_persistence_sqlalchemy import SQLAlchemyRepository

class OrderRepository(MultitenantRepositoryMixin, SQLAlchemyRepository[Order, str]):
    """Repository with automatic tenant filtering."""
    pass

# Mixin intercepts every operation:
await repo.add(order)           # tenant_id auto-injected from context
entity = await repo.get("o-1")  # returns None if wrong tenant (silent denial)
orders = await repo.search(spec) # WHERE tenant_id = 'tenant-123' AND (user criteria)
await repo.delete("o-1")        # scoped to current tenant
```

### 4. Configure CQRS Middleware

```python
from cqrs_ddd_multitenancy import CQRSTenantMiddleware
from cqrs_ddd_multitenancy.resolver import HeaderResolver

middleware = CQRSTenantMiddleware(resolver=HeaderResolver("X-Tenant-ID"))
mediator.add_middleware(middleware)

# All commands/queries now resolve tenant before handler execution
```

### 5. FastAPI Integration

```python
from fastapi import FastAPI, Depends
from cqrs_ddd_multitenancy.contrib.fastapi import (
    TenantMiddleware,
    get_current_tenant_dep,
    require_tenant_dep,
)
from cqrs_ddd_multitenancy.resolver import HeaderResolver

app = FastAPI()
app.add_middleware(
    TenantMiddleware,
    resolver=HeaderResolver("X-Tenant-ID"),
    public_paths=["/health", "/docs", "/openapi.json"],
)

@app.get("/orders")
async def list_orders(tenant_id: str = Depends(require_tenant_dep)):
    """tenant_id is guaranteed to be set; returns 400 if missing."""
    return {"tenant_id": tenant_id}
```

---

## Context Management

The context module provides `ContextVar`-based tenant storage that propagates correctly through `async`/`await` call chains. All state is stored in a single `ContextVar[str | None]` initialized with `default=None`.

### Tenant ID Validation

`set_tenant()` validates the tenant ID before storing it:

- **Allowed characters:** alphanumeric, hyphens (`-`), underscores (`_`)
- **Length:** 1–128 characters
- **Regex:** `^[a-zA-Z0-9_-]+$`
- **Reserved:** `__system__` is the system tenant sentinel constant (`SYSTEM_TENANT`)

Invalid IDs raise `ValueError` with a descriptive message:

```python
set_tenant("")              # ValueError: Tenant ID must be between 1 and 128 characters
set_tenant("a" * 200)       # ValueError: Tenant ID must be between 1 and 128 characters
set_tenant("invalid tenant") # ValueError: Tenant ID contains invalid characters
```

### Token-Based Reset

Every `set_tenant()` call returns a `contextvars.Token` that can restore the previous state. This is critical for nested contexts and middleware chains:

```python
from cqrs_ddd_multitenancy import set_tenant, reset_tenant, get_current_tenant

# Outer context
outer_token = set_tenant("tenant-a")

# Inner context (nesting is safe)
inner_token = set_tenant("tenant-b")
assert get_current_tenant() == "tenant-b"

reset_tenant(inner_token)  # uses _tenant_context.reset(token)
assert get_current_tenant() == "tenant-a"

reset_tenant(outer_token)
```

> **`reset_tenant(token)` vs `clear_tenant()`:** `reset_tenant()` restores the *previous* value from the token, which may be a different tenant (not `None`). `clear_tenant()` unconditionally sets the context to `None`. Always prefer token-based reset in middleware and nested contexts.

### Async Context Manager

`with_tenant_context()` returns a `_TenantContextManager` that calls `set_tenant()` on `__aenter__` and `reset_tenant(token)` on `__aexit__`, ensuring correct restore even on exceptions:

```python
from cqrs_ddd_multitenancy import with_tenant_context, get_current_tenant

async with with_tenant_context("tenant-123"):
    assert get_current_tenant() == "tenant-123"
    # Nested:
    async with with_tenant_context("tenant-456"):
        assert get_current_tenant() == "tenant-456"
    assert get_current_tenant() == "tenant-123"
# Context fully restored here
```

### Accessor Functions

| Function | Behavior |
|---|---|
| `get_current_tenant()` | Returns tenant ID or raises `TenantContextMissingError` |
| `get_current_tenant_or_none()` | Returns tenant ID or `None` — never raises |
| `require_tenant()` | Alias for `get_current_tenant()` |
| `is_tenant_context_set()` | Returns `True` if context is not `None` |
| `is_system_tenant()` | Returns `True` if context is `__system__` |

### System Operations

The `@system_operation` decorator wraps an `async` function to run with `__system__` context. Every persistence mixin checks `is_system_tenant()` first and bypasses all tenant filtering when `True`. Use it only for admin functions behind proper authorization:

```python
from cqrs_ddd_multitenancy import system_operation

@system_operation
async def migrate_all_tenants():
    """This can query across all tenants — no tenant filter applied."""
    all_orders = await repo.list_all()  # returns ALL tenants' orders
    return all_orders
```

The decorator internally calls `set_tenant(SYSTEM_TENANT)` before the function and `reset_tenant(token)` in a `finally` block after it completes.

### Background Task Propagation

When spawning background tasks, capture and propagate the tenant context:

```python
from cqrs_ddd_multitenancy import get_tenant_context_vars, propagate_tenant_context

# Capture current context
ctx = get_tenant_context_vars()  # {"tenant_id": "tenant-123"} or {"tenant_id": None}

# Option 1: Wrap an async function to carry the context
# If tenant_id is None, captures the current tenant at wrap time
wrapped = propagate_tenant_context(my_async_handler, tenant_id=ctx["tenant_id"])
await wrapped()

# Option 2: Synchronous context (uses contextvars.copy_context() for thread safety)
from cqrs_ddd_multitenancy.context import run_in_tenant_context
result = run_in_tenant_context("tenant-123", sync_function, arg1, arg2)
```

`run_in_tenant_context()` creates a copy of the current `contextvars.Context` via `copy_context()`, sets the tenant inside the copy, and runs the function there. This is safe for thread pool executors and sync callbacks.

---

## Tenant Resolution

Resolvers extract the tenant ID from incoming requests or messages. All implement `ITenantResolver` (a `@runtime_checkable` Protocol):

```python
class ITenantResolver(Protocol):
    async def resolve(self, message: Any) -> str | None: ...
    def can_resolve(self, message: Any) -> bool: ...
```

> The default `can_resolve()` implementation always returns `True`. Override it if your resolver only works with specific message types.

### Available Resolvers

| Resolver | Source | Example |
|---|---|---|
| `HeaderResolver` | HTTP header | `X-Tenant-ID: tenant-123` |
| `JwtClaimResolver` | JWT claim / Principal object | `{"tenant_id": "tenant-123"}` |
| `SubdomainResolver` | URL subdomain | `tenant-123.app.example.com` |
| `PathResolver` | URL path segment | `/tenants/tenant-123/orders` |
| `StaticResolver` | Fixed value | Always returns configured tenant |
| `CallableResolver` | Custom function | Wraps sync/async callable |
| `CompositeResolver` | Multiple resolvers | Priority-based fallback chain |

### HeaderResolver

Extracts tenant from an HTTP header. The header name match is **case-insensitive**. Supports multiple message formats:

- **Starlette/FastAPI `Request`**: reads `request.headers[name]`
- **Dict-based messages**: reads `message["headers"][name]` or `message[name]`
- **Objects with `.metadata`**: reads `message.metadata.headers[name]`

```python
from cqrs_ddd_multitenancy.resolver import HeaderResolver

# required=False (default): returns None if header is missing
resolver = HeaderResolver("X-Tenant-ID")

# required=True: raises TenantContextMissingError if header is missing
resolver = HeaderResolver("X-Tenant-ID", required=True)
```

### JwtClaimResolver

Extracts tenant from JWT claims or `Principal` objects (compatible with `cqrs-ddd-auth`). Resolution order:

1. **Direct attribute**: `message.principal.claims[claim_name]` or `message.claims[claim_name]`
2. **Principal protocol**: `message.principal` → extract claims from it
3. **Dict-based**: `message["claims"][claim_name]` or searches known keys (`claims`, `token_claims`, `jwt_claims`, `decoded_token`)
4. **Nested claims**: supports dot-notation paths (e.g., `"org.tenant_id"` → `claims["org"]["tenant_id"]`)

```python
from cqrs_ddd_multitenancy.resolver import JwtClaimResolver

# From JWT payload dict
resolver = JwtClaimResolver(claim_name="tenant_id")
tenant = await resolver.resolve({"tenant_id": "acme-corp", "sub": "user-1"})
# "acme-corp"

# From nested claims (dot notation)
resolver = JwtClaimResolver(claim_name="org.id")
tenant = await resolver.resolve({"org": {"id": "acme-corp"}})
# "acme-corp"

# From Principal object (cqrs-ddd-auth)
resolver = JwtClaimResolver(claim_name="tenant_id")
tenant = await resolver.resolve(request_with_principal)
# Reads principal.claims["tenant_id"]
```

### SubdomainResolver

Extracts tenant from the first subdomain of the URL, using regex `^([a-zA-Z0-9][-a-zA-Z0-9]*)\.`. **Automatically skips** common non-tenant subdomains: `www`, `api`, `app`, `admin`, `mail`, `ftp`.

```python
from cqrs_ddd_multitenancy.resolver import SubdomainResolver

resolver = SubdomainResolver(base_domain="app.example.com")
tenant = await resolver.resolve(request)
# "acme-corp" from https://acme-corp.app.example.com/orders

# Skipped subdomains return None:
# www.app.example.com → None
# api.app.example.com → None
```

Extracts the hostname from `url.hostname`, `.host` attribute, or `headers["Host"]` dict key.

### PathResolver

Extracts tenant from a URL path segment, using a configurable prefix (default: `/tenants/`). Builds a regex from the prefix to capture the segment:

```python
from cqrs_ddd_multitenancy.resolver import PathResolver

resolver = PathResolver(prefix="/tenants/")
tenant = await resolver.resolve(request)
# "acme-corp" from /tenants/acme-corp/orders

# Custom prefix
resolver = PathResolver(prefix="/api/v1/orgs/")
tenant = await resolver.resolve(request)
# "acme-corp" from /api/v1/orgs/acme-corp/resources
```

### Composite Resolver (Priority Fallback)

Tries resolvers in order and returns the first non-`None` result. **Swallows exceptions** from individual resolvers so a failing resolver doesn't block the chain. `add_resolver()` returns a new `CompositeResolver` instance (immutable pattern):

```python
from cqrs_ddd_multitenancy.resolver import (
    HeaderResolver,
    JwtClaimResolver,
    SubdomainResolver,
    CompositeResolver,
)

# Try header first, then JWT claim, then subdomain
resolver = CompositeResolver([
    HeaderResolver("X-Tenant-ID"),
    JwtClaimResolver(claim_name="tenant_id"),
    SubdomainResolver(base_domain="app.example.com"),
])

# Add another resolver (returns new instance)
resolver = resolver.add_resolver(PathResolver(prefix="/tenants/"))
```

### CallableResolver and StaticResolver

```python
from cqrs_ddd_multitenancy.resolver import CallableResolver, StaticResolver

# Wraps any sync or async callable
# Detects async via inspect or __await__ check
async def custom_resolve(message):
    return message.get("org_id")

resolver = CallableResolver(custom_resolve)

# Fixed tenant — useful for testing or single-tenant deployments
# Validates that tenant_id is non-empty at construction time
resolver = StaticResolver("default-tenant")
```

---

## Isolation Strategies

Three isolation strategies are supported, defined in `TenantIsolationStrategy` (a `str, Enum`):

| Strategy | Value | PostgreSQL Required | Connection Routing |
|---|---|---|---|
| `DISCRIMINATOR_COLUMN` | `"discriminator_column"` | No | No |
| `SCHEMA_PER_TENANT` | `"schema_per_tenant"` | Yes | No |
| `DATABASE_PER_TENANT` | `"database_per_tenant"` | No | Yes |

### IsolationConfig

A frozen dataclass that defines the isolation strategy and its parameters:

```python
from cqrs_ddd_multitenancy import IsolationConfig, TenantIsolationStrategy

config = IsolationConfig(
    strategy=TenantIsolationStrategy.SCHEMA_PER_TENANT,
    tenant_column="tenant_id",           # column name for discriminator filtering
    schema_prefix="tenant_",             # prefix for PostgreSQL schemas
    database_prefix="app_",              # prefix for per-database names
    default_schema="public",             # fallback schema for system tenant
    allow_cross_tenant=False,            # whether cross-tenant access is permitted
)

# Derived helpers
config.get_schema_name("acme-corp")    # "tenant_acme_corp" (hyphens → underscores)
config.get_database_name("acme-corp")  # "app_acme_corp"
config.get_search_path("acme-corp")    # "tenant_acme_corp,public"

# Validation — raises ValueError if strategy requirements are not met
config.validate_for_strategy()
```

### TenantRoutingInfo

A frozen dataclass that bundles tenant + isolation details for use by routers. Create it from config:

```python
from cqrs_ddd_multitenancy import TenantRoutingInfo

info = TenantRoutingInfo.from_config("acme-corp", config)
# info.tenant_id    → "acme-corp"
# info.strategy     → TenantIsolationStrategy.SCHEMA_PER_TENANT
# info.schema_name  → "tenant_acme_corp"
# info.database_name → None (only set for DATABASE_PER_TENANT)
# info.search_path  → "tenant_acme_corp,public"
```

### Discriminator Column (Default)

All tenants share the same schema. A `tenant_id` column on each table provides filtering. The repository mixin automatically injects `WHERE tenant_id = ?` into every query via `AttributeSpecification`.

```python
config = IsolationConfig(
    strategy=TenantIsolationStrategy.DISCRIMINATOR_COLUMN,
    tenant_column="tenant_id",
)

class OrderRepository(MultitenantRepositoryMixin, SQLAlchemyRepository[Order, str]):
    pass

# Under tenant-123 context:
await repo.add(order)
# SQL: INSERT INTO orders (id, tenant_id, ...) VALUES ('o-1', 'tenant-123', ...)

orders = await repo.search(some_spec)
# SQL: SELECT * FROM orders WHERE tenant_id = 'tenant-123' AND (some_spec conditions)
```

### Schema per Tenant (PostgreSQL)

Each tenant gets their own PostgreSQL schema. The `SchemaRouter` manages `SET search_path` and provides schema lifecycle management.

**SQL injection prevention:** Schema names are validated against `^[a-zA-Z0-9_]+$` before being used in SQL statements. Hyphens in tenant IDs are converted to underscores.

```python
from cqrs_ddd_multitenancy.schema_routing import SchemaRouter

router = SchemaRouter(config)
# Constructor validates that strategy is SCHEMA_PER_TENANT

# Create a tenant schema (run during provisioning)
await router.create_tenant_schema(session, "acme-corp")
# 1. Checks existence via information_schema.schemata
# 2. SQL: CREATE SCHEMA IF NOT EXISTS tenant_acme_corp
# 3. Commits the transaction
# Raises TenantProvisioningError on failure

# Query in tenant context
async with router.with_schema(session, "acme-corp"):
    # 1. Resolves tenant from context or parameter
    # 2. System tenant (__system__) uses default_schema ("public")
    # 3. SET search_path TO tenant_acme_corp
    # 4. Records previous search_path for restore
    results = await session.execute(select(Order))
    # On exit: SET search_path TO <previous_path>

# Schema management
exists = await router.schema_exists(session, "acme-corp")
await router.drop_tenant_schema(session, "old-tenant", cascade=True)
# SQL: DROP SCHEMA IF EXISTS tenant_old_tenant CASCADE

# Convenience functions (module-level)
from cqrs_ddd_multitenancy.schema_routing import with_tenant_schema
async with with_tenant_schema(session, router, "acme-corp"):
    ...
```

The `set_search_path()` method saves the current path via `SHOW search_path` before switching, and `reset_search_path()` restores it. Observability spans are emitted for each switch when OpenTelemetry is available.

### Database per Tenant

Each tenant gets their own database. The `DatabaseRouter` manages a `TenantConnectionPool` with **LRU eviction** of SQLAlchemy engines.

```python
from cqrs_ddd_multitenancy.database_routing import (
    DatabaseRouter,
    TenantConnectionPool,
    TenantDatabaseConfig,
)

# Configure pool settings
pool_config = TenantDatabaseConfig(
    pool_size=5,           # per-engine pool size
    max_overflow=10,       # per-engine max overflow
    pool_timeout=30,       # connection wait timeout
    echo=False,            # SQLAlchemy echo flag
)

# The pool manages engine lifecycle with LRU eviction
pool = TenantConnectionPool(
    get_database_url=lambda tid: f"postgresql+asyncpg://user:pass@localhost:5432/app_{tid}",
    max_pools=50,          # evicts least-recently-used engine when exceeded
    config=pool_config,
)

# LRU internals: uses OrderedDict with move_to_end() on access
# Lock: lazily created asyncio.Lock() for thread-safe pool operations
engine = await pool.get_engine("acme-corp")               # creates or returns cached engine
session_factory = await pool.get_session_factory("acme-corp")  # async_sessionmaker wrapper

# DatabaseRouter wraps the pool with context-aware sessions
router = DatabaseRouter(
    config=config,
    base_url="postgresql+asyncpg://user:pass@localhost:5432",
)

# Get a session for a specific tenant
async with router.session_for_tenant("acme-corp") as session:
    # Connects to: postgresql+asyncpg://user:pass@localhost:5432/app_acme_corp
    results = await session.execute(select(Order))

# Or use current context automatically
async with router.session_for_current_tenant() as session:
    # Uses get_current_tenant() to determine the database
    results = await session.execute(select(Order))

# Custom engine factory (useful for testing with SQLite)
pool = TenantConnectionPool(
    get_database_url=lambda tid: f"sqlite+aiosqlite:///{tid}.db",
    engine_factory=lambda tid, config: create_async_engine(f"sqlite+aiosqlite:///{tid}.db"),
)

# Cleanup
await pool.close_engine("old-tenant")  # disposes a single engine
await pool.close_all()                 # disposes all cached engines
await pool.health_check("acme-corp")   # tests connectivity
```

---

## Domain Layer

### MultitenantMixin

A Pydantic `BaseModel` mixin that adds a validated `tenant_id` field to aggregates and entities. The field uses Pydantic `Field` with validation constraints:

```python
from pydantic import BaseModel, Field

class MultitenantMixin(BaseModel):
    tenant_id: str = Field(
        ...,                             # required (no default)
        min_length=1,
        max_length=128,
        examples=["acme-corp", "tenant_42", "org-123"],
    )
```

Use it with `AggregateRoot` via MRO composition:

```python
from cqrs_ddd_core import AggregateRoot
from cqrs_ddd_multitenancy.domain import MultitenantMixin

class Invoice(MultitenantMixin, AggregateRoot[str]):
    """Invoice aggregate with tenant isolation."""
    amount: float
    currency: str = "USD"
    paid: bool = False

# tenant_id is required and validated at construction time
inv = Invoice(id="inv-1", tenant_id="acme-corp", amount=99.99)
```

### Tenant Validation

The `validate_tenant()` method checks that an entity belongs to an expected tenant:

```python
inv.validate_tenant("acme-corp")  # OK — returns None
inv.validate_tenant("wrong")     # raises ValueError:
# "Entity Invoice[inv-1] belongs to tenant 'acme-corp', not 'wrong'"
```

This is a domain-level safety check. The persistence mixins enforce isolation at the query level automatically, so `validate_tenant()` is primarily useful for explicit domain logic assertions.

### How It Works with Persistence

The `tenant_id` field is persisted as a regular database column (not JSONB metadata). This enables:

- **B-tree index** for efficient `WHERE tenant_id = ?` filtering
- **Row-Level Security (RLS)** support in PostgreSQL
- **Foreign key constraints** across tenant-scoped tables
- **Table partitioning** by `tenant_id` for horizontal scaling

The persistence mixins use `_set_tenant_id_on_entity()` which tries `setattr` first, then falls back to `model_copy(update={"tenant_id": ...})` for frozen Pydantic models.

---

## Persistence Mixins

All 17 persistence mixins follow the same **MRO composition** pattern — place the mixin **before** the base class so it intercepts method calls:

```python
class TenantRepo(MultitenantRepositoryMixin, SQLAlchemyRepository[Order, str]):
    pass  # No extra code needed
```

### How Specification-Based Filtering Works

Every mixin method follows the same pattern internally:

1. **Check system tenant**: `if is_system_tenant(): return await super().method(...)` — bypasses all filtering
2. **Get current tenant**: `_require_tenant_context()` → raises `TenantContextMissingError` if not set
3. **Build specification**: `_build_tenant_specification(tenant_id)` → creates `AttributeSpecification("tenant_id", EQ, tenant_id)`
4. **Compose with user spec**: `_compose_specs(tenant_spec, user_spec)` — uses `__and__` operator (`tenant_spec & user_spec`)
5. **Delegate to base**: passes the composed specification via `super().method(..., specification=combined)`

The `_build_tenant_specification()` method uses `cqrs-ddd-specifications` when available:

```python
# When cqrs-ddd-specifications is installed:
AttributeSpecification(attr="tenant_id", op=SpecificationOperator.EQ, val=tenant_id, registry=build_default_registry())

# Fallback (when not installed):
{"attr": "tenant_id", "op": "eq", "value": tenant_id}
```

### Repository Mixin

```python
from cqrs_ddd_multitenancy import MultitenantRepositoryMixin, StrictMultitenantRepositoryMixin

# Standard: cross-tenant get() returns None (silent denial — prevents information leakage)
class OrderRepo(MultitenantRepositoryMixin, SQLAlchemyRepository[Order, str]):
    pass

# Strict: cross-tenant access raises CrossTenantAccessError
# Overrides get() to fetch first, then compare entity.tenant_id vs current_tenant
class StrictOrderRepo(StrictMultitenantRepositoryMixin, SQLAlchemyRepository[Order, str]):
    pass
```

**Method behaviors:**

| Method | Standard Mixin | Strict Mixin |
|---|---|---|
| `add()` | Injects `tenant_id` from context; rejects if entity has a different `tenant_id` | Same |
| `get()` | Passes `specification=tenant_spec` to base; returns `None` for wrong tenant | Fetches via base, then raises `CrossTenantAccessError` if tenant mismatch |
| `delete()` | Composes tenant spec with ID filter; `_allow_cross_tenant_delete=False` by default | Same, with `_allow_cross_tenant_delete=True` |
| `list_all()` | Composes tenant spec with `specification` parameter | Same |
| `search()` | `_compose_tenant_filter()` which tries `__and__`, dict composition, or `SpecificationFactory` | Same |

The `_set_tenant_id_on_entity()` method handles both mutable and immutable models:
1. Tries `setattr(entity, "tenant_id", tenant_id)`
2. Falls back to `entity.model_copy(update={"tenant_id": tenant_id})` for frozen Pydantic models

### Event Store Mixin

Overrides 10 methods (`append`, `append_batch`, `get_events`, `get_by_aggregate`, `get_all`, `get_events_after`, `stream_all`, `get_events_from_position`, `get_all_streaming`, `get_latest_position`):

```python
from cqrs_ddd_multitenancy import MultitenantEventStoreMixin

class TenantEventStore(MultitenantEventStoreMixin, SQLEventStore):
    pass
```

**Key implementation detail:** Events are injected with `tenant_id` using `dataclasses.replace()` for frozen `StoredEvent` dataclasses. The `_inject_tenant_into_event()` method tries `dataclasses.replace()` first, then falls back to constructing a new instance with all fields.

The `tenant_id` is stored in a **dedicated column** (not JSONB metadata) to enable B-tree indexes and Row-Level Security.

```python
# tenant_id injected into StoredEvent on append
await store.append(stored_event)
# Internally: dataclasses.replace(stored_event, tenant_id=current_tenant)

# All reads filtered by current tenant — specification passed to base
events = await store.get_events(aggregate_id="agg-1")
all_events = await store.get_all()
position = await store.get_latest_position()

# Streaming also filtered
async for event in store.stream_all():
    process(event)
```

### Outbox Mixin

Injects `tenant_id` into both the dedicated `OutboxMessage.tenant_id` field AND the metadata dict (for backward-compatible consumers):

```python
from cqrs_ddd_multitenancy import MultitenantOutboxMixin, StrictMultitenantOutboxMixin

class TenantOutbox(MultitenantOutboxMixin, SQLOutboxStorage):
    pass

# tenant_id injected into OutboxMessage (dedicated field + metadata)
await outbox.save_messages([msg1, msg2])

# Only returns messages for current tenant (specification passed to base)
pending = await outbox.get_pending(limit=100)

# Strict variant validates ownership before mark_published
# Fetches messages and checks tenant_id before allowing modification
class StrictTenantOutbox(StrictMultitenantOutboxMixin, SQLOutboxStorage):
    pass
```

Tenant extraction follows resolution order: (1) `message.tenant_id` attribute → (2) `message.metadata["tenant_id"]`.

### Saga Mixin

Overrides 11 methods for complete saga lifecycle management with tenant isolation:

```python
from cqrs_ddd_multitenancy import MultitenantSagaMixin

class TenantSagaRepo(MultitenantSagaMixin, SagaRepository):
    pass

# All saga operations scoped to current tenant
await repo.add(saga_state)             # injects tenant_id into state + metadata
saga = await repo.get("saga-1")        # None if wrong tenant (silent denial)
saga = await repo.find_by_correlation_id("corr-123", "OrderSaga")  # cross-tenant → None

# Spec-based filtering for bulk queries
stalled = await repo.find_stalled_sagas(limit=10)
suspended = await repo.find_suspended_sagas(limit=10)
expired = await repo.find_expired_suspended_sagas(limit=10)
tcc = await repo.find_running_sagas_with_tcc_steps(limit=10)
```

The `_inject_tenant_to_saga()` method sets tenant_id using `object.__setattr__()` to bypass Pydantic's frozen model restriction, and raises `CrossTenantAccessError` if the saga already belongs to a different tenant.

### Advanced Mixins

**Snapshot Store** — `MultitenantSnapshotMixin`: Injects `tenant_id` into snapshot data on save, composes tenant spec on retrieval and deletion.

**Command Scheduler** — `MultitenantCommandSchedulerMixin`: Injects `tenant_id` into command via `object.__setattr__()` (dedicated attribute + `_metadata` dict). System tenant sees ALL due commands (for background workers).

**Event Upcaster** — `MultitenantUpcasterMixin`: Extracts `tenant_id` before the upcasting transformation, reinjects it after. Logs a **warning** if the upcaster modifies or removes `tenant_id`, and always restores the original value.

**Background Job** — `MultitenantBackgroundJobMixin`: 11 methods overridden. Silent denial on `get()` (returns `None` for wrong tenant), spec-based filtering for `find_by_status()`, `count_by_status()`, `get_stale_jobs()`, `purge_completed()`.

**Dispatcher** — `MultitenantDispatcherMixin`: Validates entity has `tenant_id` field (raises `ValueError` if not), injects into entity via `model_copy()` or `setattr()`, injects into event metadata.

**Persistence Interfaces** — 4 mixins (`MultitenantOperationPersistenceMixin`, `MultitenantRetrievalPersistenceMixin`, `MultitenantQueryPersistenceMixin`, `MultitenantQuerySpecificationPersistenceMixin`): Follow the same spec-based pattern for the advanced persistence layer's `IOperationPersistence`, `IRetrievalPersistence`, `IQueryPersistence`, and `IQuerySpecificationPersistence` protocols.

**Projection Store** — `MultitenantProjectionMixin` + `MultitenantProjectionPositionMixin`: Document IDs are namespaced with `{tenant_id}:{doc_id}`. For composite/int IDs, injects `tenant_id` into the dict key. `find()` adds `tenant_id` to the filter dict. Position tracking uses `{tenant_id}:{projection_name}` as the key.

### Complete Mixin List

```python
from cqrs_ddd_multitenancy import (
    # Core persistence
    MultitenantRepositoryMixin,
    StrictMultitenantRepositoryMixin,
    MultitenantEventStoreMixin,
    MultitenantOutboxMixin,
    StrictMultitenantOutboxMixin,
    # CQRS dispatcher & persistence
    MultitenantDispatcherMixin,
    MultitenantOperationPersistenceMixin,
    MultitenantRetrievalPersistenceMixin,
    MultitenantQueryPersistenceMixin,
    MultitenantQuerySpecificationPersistenceMixin,
    # Projections
    MultitenantProjectionMixin,
    MultitenantProjectionPositionMixin,
    # Advanced
    MultitenantSagaMixin,
    MultitenantSnapshotMixin,
    MultitenantCommandSchedulerMixin,
    MultitenantUpcasterMixin,
    MultitenantBackgroundJobMixin,
    # Infrastructure
    MultitenantRedisCacheMixin,
    MultitenantRedisLockMixin,
)
```

### Specification Module

For custom specification-based filtering outside the mixins, the `specification` module provides utility functions:

```python
from cqrs_ddd_multitenancy.specification import (
    TenantSpecification,          # factory class with classmethods
    MetadataTenantSpecification,  # spec that works with both SQL and in-memory
    with_tenant_filter,           # compose any spec with tenant filter
    create_tenant_specification,  # create an AttributeSpecification for tenant_id
    build_tenant_filter_dict,     # raw dict for direct SQLAlchemy builds
)

# Create spec for current tenant
spec = TenantSpecification.for_current_tenant(registry=reg)

# Create for specific tenant
spec = TenantSpecification.for_tenant("acme-corp", registry=reg)

# Compose business logic spec with tenant filter
# System tenant bypasses filtering (returns original spec)
combined = with_tenant_filter(business_spec, registry=reg)

# MetadataTenantSpecification — works with both SQL and in-memory objects
# Resolves tenant from: attribute → metadata dict → _metadata dict
meta_spec = MetadataTenantSpecification("acme-corp")
meta_spec.is_satisfied_by(entity)  # True if entity.tenant_id == "acme-corp"
meta_spec.to_dict()                # {"attr": "tenant_id", "op": "eq", "val": "acme-corp"}
# Supports & | ~ operators for composition with cqrs-ddd-specifications
```

### MongoDB Support

All generic mixins work with MongoDB adapters via MRO — no MongoDB-specific mixin code needed:

```python
from cqrs_ddd_persistence_mongo import MongoRepository, MongoProjectionStore

class TenantMongoRepo(MultitenantRepositoryMixin, MongoRepository[Order, str]):
    pass  # Works identically to SQLAlchemy

class TenantMongoProjections(MultitenantProjectionMixin, MongoProjectionStore):
    pass  # Document queries filtered by tenant_id

class TenantMongoOutbox(MultitenantOutboxMixin, MongoOutboxStorage):
    pass  # Same mixin, different adapter
```

---

## CQRS Middleware

The CQRS `TenantMiddleware` implements `IMiddleware` from `cqrs-ddd-core` and integrates with the mediator pipeline. It uses `__slots__` for performance (`_resolver`, `_allow_anonymous`, `_inject_into_message`).

### Execution Flow

```
Command/Query → TenantMiddleware.__call__(message, next_handler)
  1. resolver.resolve(message) → tenant_id or None
  2. If tenant_id is None and not allow_anonymous → raises TenantContextMissingError
  3. set_tenant(tenant_id) → Token
  4. Optional: inject tenant_id into message (if inject_into_message=True)
  5. await next_handler(message)
  6. finally: reset_tenant(token)
```

```python
from cqrs_ddd_multitenancy import CQRSTenantMiddleware
from cqrs_ddd_multitenancy.resolver import HeaderResolver

# Standard middleware — resolves tenant from the command/query message
middleware = CQRSTenantMiddleware(
    resolver=HeaderResolver("X-Tenant-ID"),
    allow_anonymous=False,          # default: raise if resolver returns None
    inject_into_message=False,      # default: don't modify the message object
)

# Register with mediator
mediator.add_middleware(middleware)
```

### Configuration Options

| Parameter | Type | Default | Description |
|---|---|---|---|
| `resolver` | `ITenantResolver` | required | Resolver to extract tenant from messages |
| `allow_anonymous` | `bool` | `False` | If `True`, allows `None` tenant (no context set) |
| `inject_into_message` | `bool` | `False` | If `True`, injects `tenant_id` into the message object after resolution |

### Message Injection

When `inject_into_message=True`, the `_inject_tenant()` method modifies the message to include the tenant ID:
1. Tries `message.model_copy(update={"tenant_id": tenant_id})` for Pydantic models
2. Falls back to cloning `message.__dict__` and creating a new instance

### Context Injection Middleware

A convenience subclass with `inject_into_message=True` pre-configured:

```python
from cqrs_ddd_multitenancy.middleware import TenantContextInjectionMiddleware

# Equivalent to CQRSTenantMiddleware(resolver=..., inject_into_message=True)
middleware = TenantContextInjectionMiddleware(
    resolver=HeaderResolver("X-Tenant-ID"),
)
```

---

## FastAPI Integration

### ASGI Middleware

The `TenantMiddleware` (extends `BaseHTTPMiddleware`) resolves tenant from every HTTP request and sets the `ContextVar` for the request lifecycle:

```python
from fastapi import FastAPI
from cqrs_ddd_multitenancy.contrib.fastapi import TenantMiddleware
from cqrs_ddd_multitenancy.resolver import HeaderResolver

app = FastAPI()

app.add_middleware(
    TenantMiddleware,
    resolver=HeaderResolver("X-Tenant-ID"),
    public_paths=["/health", "/docs", "/openapi.json"],
)
```

**Request flow:**

1. **Check public paths** — exact match first, then wildcard prefix match for paths ending in `*`
2. **Resolve tenant** from the request using the configured resolver
3. **Return HTTP 400** (JSON body: `{"detail": "..."}`) if resolution fails and path is not public
4. **Set ContextVar** via `set_tenant()` → `Token`
5. **Reset context** via `reset_tenant(token)` in `finally` block (guaranteed cleanup)

**Public path matching:**

```python
# Exact match
public_paths=["/health", "/docs"]
# /health → skipped ✓
# /health/deep → NOT skipped ✗

# Wildcard (paths ending with *)
public_paths=["/api/v1/public/*"]
# /api/v1/public/anything → skipped ✓
# /api/v1/public/nested/deep → skipped ✓
# /api/v1/private → NOT skipped ✗
```

### Dependency Injection

Three FastAPI dependency functions for use with `Depends()`:

```python
from fastapi import Depends
from cqrs_ddd_multitenancy.contrib.fastapi import (
    get_current_tenant_dep,    # Returns str; raises HTTPException(400) if missing
    require_tenant_dep,        # Alias for get_current_tenant_dep
    get_tenant_or_none_dep,    # Returns str | None; never raises
)

@app.get("/orders")
async def list_orders(tenant_id: str = Depends(require_tenant_dep)):
    """Raises HTTPException(400) if tenant not set."""
    return {"tenant_id": tenant_id}

@app.get("/info")
async def get_info(tenant_id: str | None = Depends(get_tenant_or_none_dep)):
    """Returns None if no tenant context (useful for public endpoints)."""
    return {"tenant_id": tenant_id}
```

### TenantContextMiddleware (Simpler Alternative)

A lighter middleware that accepts an `extract_tenant` callable instead of a full resolver. Uses `clear_tenant()` in `finally` (not token-based reset), so it doesn't support nesting:

```python
from cqrs_ddd_multitenancy.contrib.fastapi import TenantContextMiddleware

def extract_from_header(request):
    return request.headers.get("X-Tenant-ID")

app.add_middleware(
    TenantContextMiddleware,
    extract_tenant=extract_from_header,
    # Does not fail on missing tenant — sets None context instead
)
```

> **`TenantMiddleware` vs `TenantContextMiddleware`:** Use `TenantMiddleware` for production (resolver protocol, public paths, token-based reset, proper error responses). Use `TenantContextMiddleware` for simple cases where you just need to extract a value and set context.

---

## Projections Engine

Integrates multitenancy with the projections engine from `cqrs-ddd-advanced` — event handlers, replay, and workers all maintain tenant context per event.

### Tenant Extraction from Events

The `extract_tenant_from_event()` function resolves tenant_id with a two-step fallback:

1. `event.tenant_id` — dedicated attribute (preferred, set by `MultitenantEventStoreMixin`)
2. `event.metadata["tenant_id"]` — metadata dict fallback (backward compatibility)

Returns `None` if neither source provides a tenant ID.

### MultitenantProjectionHandler

Wraps any `IProjectionHandler` to set tenant context before handling. Context flow:

1. Save current tenant context (for restoration)
2. Extract tenant from event via `extract_tenant_from_event()`
3. If `skip_system_events=True` and tenant is `__system__`, skip handling
4. Call `set_tenant(tenant_id)` → `Token`
5. Delegate to `inner.handle(event)`
6. `finally`: restore previous context via `reset_tenant(token)`

```python
from cqrs_ddd_multitenancy.projections import MultitenantProjectionHandler

tenant_handler = MultitenantProjectionHandler(
    inner=my_projection_handler,
    tenant_column="tenant_id",      # attribute name on StoredEvent
    skip_system_events=False,       # whether to skip __system__ events
)

# The handler delegates `.handles` property to the inner handler,
# so it works transparently with projection registries
assert tenant_handler.handles == my_projection_handler.handles
```

### TenantAwareProjectionRegistry

Auto-wraps all handlers returned by a registry. Uses an internal cache (`dict[int, MultitenantProjectionHandler]`) keyed by `id(handler)` to avoid wrapping the same handler multiple times:

```python
from cqrs_ddd_multitenancy.projections import TenantAwareProjectionRegistry

# Wrap an existing registry
tenant_registry = TenantAwareProjectionRegistry(inner=my_registry)

# get_handlers() wraps each result in MultitenantProjectionHandler
handlers = tenant_registry.get_handlers("OrderCreated")
# Each handler automatically sets tenant context before processing

# register() delegates to the inner registry (no wrapping at registration time)
tenant_registry.register(my_handler)
```

### Replay and Worker Mixins

Both mixins override the internal `_dispatch` method to set tenant context per event during bulk processing:

```python
from cqrs_ddd_multitenancy.projections import MultitenantReplayMixin, MultitenantWorkerMixin

class TenantReplayEngine(MultitenantReplayMixin, ReplayEngine):
    pass
    # Overrides _dispatch_to_handlers(stored_event, domain_event)
    # Extracts tenant from stored_event first, then domain_event as fallback

class TenantProjectionWorker(MultitenantWorkerMixin, ProjectionWorker):
    pass
    # Overrides _dispatch(event, stored_event, event_position, retry_count)
    # Sets tenant context before dispatching to handlers
```

Both mixins use `set_tenant()` / `reset_tenant()` token pattern internally, ensuring correct restore after each event is processed.

---

## Background Jobs & Workers

### Job Repository Mixin

`MultitenantBackgroundJobMixin` overrides 11 methods for full lifecycle management. All methods follow the standard mixin pattern: check system tenant → require context → build spec → compose → delegate.

```python
from cqrs_ddd_multitenancy import MultitenantBackgroundJobMixin

class TenantJobRepo(MultitenantBackgroundJobMixin, BackgroundJobRepository):
    pass

# Write operations — inject tenant_id into job.tenant_id + job.metadata["tenant_id"]
await repo.add(job)      # CrossTenantAccessError if job already has a different tenant_id
await repo.update(job)   # validates tenant ownership
await repo.delete(job)   # validates tenant ownership

# Read operations — silent denial or spec-based filtering
job = await repo.get("job-1")                                # None if wrong tenant
jobs = await repo.find_by_status(JobStatus.PENDING)          # spec-based
count = await repo.count_by_status(JobStatus.RUNNING)        # spec-based
stale = await repo.get_stale_jobs(timedelta(hours=1))        # spec-based
await repo.purge_completed(older_than=timedelta(days=30))    # spec-based

# System tenant sees ALL jobs (for admin workers)
```

### Command Scheduler Mixin

`MultitenantCommandSchedulerMixin` provides tenant isolation for scheduled commands:

```python
from cqrs_ddd_multitenancy import MultitenantCommandSchedulerMixin

class TenantScheduler(MultitenantCommandSchedulerMixin, RedisCommandScheduler):
    pass

# schedule() injects tenant_id into command (object.__setattr__ for frozen models)
# Sets BOTH command.tenant_id AND command._metadata["_tenant_id"]
schedule_id = await scheduler.schedule(command, execute_at=future_time)

# get_due_commands() uses spec-based filtering
# System tenant returns ALL due commands (critical for background workers)
due = await scheduler.get_due_commands()
```

### Worker Context Propagation

`TenantAwareJobWorker` wraps a job handler to automatically extract tenant context from job metadata before execution:

```python
from cqrs_ddd_multitenancy import TenantAwareJobWorker, with_tenant_context_from_job

# Option 1: Wrap a worker instance
worker = TenantAwareJobWorker(
    my_handler,
    tenant_metadata_key="tenant_id",  # configurable metadata key (default: "tenant_id")
)
await worker(job)  # extracts job.metadata["tenant_id"], sets context, runs handler

# If no tenant found in metadata, logs a WARNING and proceeds without setting context
```

The `with_tenant_context_from_job` decorator factory creates a `TenantAwareJobWorker` with a customizable metadata key:

```python
# Option 2: Decorator for async job handlers
@with_tenant_context_from_job(tenant_metadata_key="tenant_id")
async def process_job(job):
    tenant_id = get_current_tenant()  # extracted from job.metadata
    await do_work(job)

# Also works without arguments (uses default "tenant_id" key)
@with_tenant_context_from_job
async def process_job(job):
    ...
```

---

## Infrastructure

### Redis Cache (Key Namespacing)

`MultitenantRedisCacheMixin` prefixes all cache keys with `{tenant_id}:` from the current context. All methods (`get`, `set`, `delete`, `exists`, `clear`, `get_many`, `set_many`) are intercepted:

```python
from cqrs_ddd_multitenancy import MultitenantRedisCacheMixin

class TenantCache(MultitenantRedisCacheMixin, RedisCache):
    pass

# Under tenant-123 context:
await cache.set("user:42", data)       # Redis key: "tenant-123:user:42"
await cache.get("user:42")             # Looks up: "tenant-123:user:42"
await cache.delete("user:42")          # Deletes: "tenant-123:user:42"
await cache.exists("user:42")          # Checks: "tenant-123:user:42"
await cache.clear()                    # Clears only tenant-123:* keys (SCAN + DEL)

# Batch operations also namespaced
await cache.get_many(["a", "b"])       # ["tenant-123:a", "tenant-123:b"]
await cache.set_many({"a": 1, "b": 2}) # {"tenant-123:a": 1, "tenant-123:b": 2}
```

### Redis Locks (Tenant-Isolated)

`MultitenantRedisLockMixin` ensures distributed locks are scoped to the current tenant:

```python
from cqrs_ddd_multitenancy import MultitenantRedisLockMixin

class TenantLock(MultitenantRedisLockMixin, RedisLock):
    pass

# Under tenant-123 context:
await lock.acquire("order-processing")    # Redis lock key: "tenant-123:order-processing"
await lock.release("order-processing")
await lock.extend("order-processing", ttl=30)
is_locked = await lock.is_locked("order-processing")
```

### Health Checks

The health check system provides per-tenant infrastructure health monitoring:

**`HealthStatus`** — Enum: `HEALTHY`, `DEGRADED`, `UNHEALTHY`, `UNKNOWN`

**`TenantHealthCheckResult`** — Frozen dataclass with:
- `tenant_id`, `status`, `component`, `message`, `timestamp`, `details` (dict), `latency_ms` (float)
- `to_dict()` — serializes result for API responses

**`TenantHealthChecker`** — Abstract base class:
- `check_health(tenant_id) -> TenantHealthCheckResult` — abstract, implement per component
- `check_current_tenant()` — resolves tenant from context and delegates
- `check_multiple_tenants(tenant_ids)` — runs health checks for multiple tenants

**`CompositeTenantHealthChecker`** — Aggregates multiple checkers:

```python
from cqrs_ddd_multitenancy import (
    TenantHealthChecker,
    CompositeTenantHealthChecker,
    HealthStatus,
    TenantHealthCheckResult,
)

class DatabaseHealthChecker(TenantHealthChecker):
    component = "database"

    async def check_health(self, tenant_id: str) -> TenantHealthCheckResult:
        try:
            start = time.perf_counter()
            await ping_database(tenant_id)
            return TenantHealthCheckResult(
                tenant_id=tenant_id,
                status=HealthStatus.HEALTHY,
                component=self.component,
                latency_ms=(time.perf_counter() - start) * 1000,
            )
        except Exception as e:
            return TenantHealthCheckResult(
                tenant_id=tenant_id,
                status=HealthStatus.UNHEALTHY,
                component=self.component,
                message=str(e),
            )

# Combine multiple checkers
composite = CompositeTenantHealthChecker()
composite.add_checker(DatabaseHealthChecker())
composite.add_checker(CacheHealthChecker())

result = await composite.check_all("tenant-123")
# Returns list of TenantHealthCheckResult from each checker

# Overall status uses priority: UNHEALTHY > DEGRADED > HEALTHY > UNKNOWN
overall = composite.get_overall_status(result)
```

### Message Propagation

Inject and extract tenant context in message broker headers. Uses the header key `x-tenant-id` (constant `TENANT_HEADER`):

```python
from cqrs_ddd_multitenancy import (
    TenantMessagePropagator,
    inject_tenant_to_message,
    extract_tenant_from_message,
    with_tenant_from_message,
)

# Standalone functions (module-level convenience)
headers = inject_tenant_to_message({})
# Gets current tenant from context, returns: {"x-tenant-id": "tenant-123"}

tenant_id = extract_tenant_from_message(headers)
# Reads headers["x-tenant-id"]; logs WARNING if missing

# TenantMessagePropagator — class-based API
propagator = TenantMessagePropagator()
headers = propagator.inject_tenant({})
tenant_id = propagator.extract_tenant(headers)

# Async context manager for message consumers
# Internally creates _TenantMessageContextManager which:
# 1. Extracts tenant from headers
# 2. Calls set_tenant() → Token on __aenter__
# 3. Calls reset_tenant(token) on __aexit__
async with propagator.with_tenant_context(headers):
    tenant_id = get_current_tenant()  # "tenant-123"
    await process_message(message)

# Decorator for message handler functions
@with_tenant_from_message()
async def handle_event(message, headers):
    # tenant context automatically set from headers["x-tenant-id"]
    tenant_id = get_current_tenant()
    await do_work(message)
```

---

## Tenant Administration

### TenantStatus and TenantInfo

```python
from cqrs_ddd_multitenancy.admin import TenantStatus, TenantInfo

# TenantStatus — str Enum with 4 states
TenantStatus.ACTIVE          # normal operation
TenantStatus.DEACTIVATED     # suspended access, data retained
TenantStatus.SUSPENDED       # temporary hold
TenantStatus.PROVISIONING    # schema/database being created
```

`TenantInfo` is a frozen dataclass that represents a tenant's registry entry:

```python
@dataclass(frozen=True)
class TenantInfo:
    tenant_id: str
    name: str
    status: TenantStatus
    isolation_strategy: TenantIsolationStrategy
    created_at: datetime
    updated_at: datetime
    deactivated_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

### TenantRegistry Protocol

`TenantRegistry` is an abstract base class defining the storage interface. Implement it for your data store:

```python
class TenantRegistry(ABC):
    async def get(self, tenant_id: str) -> TenantInfo | None: ...
    async def list_all(self, *, include_deactivated: bool = False) -> list[TenantInfo]: ...
    async def save(self, tenant_info: TenantInfo) -> None: ...
    async def delete(self, tenant_id: str) -> None: ...
```

`InMemoryTenantRegistry` is provided for testing (dict-backed).

### TenantAdmin

All admin operations require `__system__` context — enforced by the `@_require_system_tenant` decorator which checks `is_system_tenant()` and raises `CrossTenantAccessError` if not:

```python
from cqrs_ddd_multitenancy.admin import TenantAdmin, InMemoryTenantRegistry
from cqrs_ddd_multitenancy import IsolationConfig, TenantIsolationStrategy, set_tenant, SYSTEM_TENANT

registry = InMemoryTenantRegistry()
config = IsolationConfig(strategy=TenantIsolationStrategy.DISCRIMINATOR_COLUMN)

admin = TenantAdmin(
    registry=registry,
    config=config,
    on_provision=on_provision,       # async callback(tenant_info, session) — runs after PROVISIONING
    on_deactivate=on_deactivate,     # async callback(tenant_info) — runs after status change
    on_delete=on_delete,             # async callback(tenant_info) — runs before registry removal
)
```

### Provisioning Lifecycle

`provision_tenant()` follows a state machine pattern:

1. Check if tenant already exists → raises `TenantError` if so
2. Create `TenantInfo` with `status=PROVISIONING`
3. Save to registry
4. Call `on_provision(tenant_info, session)` callback (schema creation, migrations, etc.)
5. Update status to `ACTIVE`
6. **On failure:** catches exception, updates status back to `DEACTIVATED`, re-raises as `TenantProvisioningError`

```python
token = set_tenant(SYSTEM_TENANT)
try:
    # Provision with optional metadata
    tenant = await admin.provision_tenant(
        "acme-corp", "Acme Corporation",
        metadata={"plan": "enterprise", "region": "eu-west-1"},
    )
    assert tenant.status == TenantStatus.ACTIVE

    # List tenants
    tenants = await admin.list_tenants()                              # active only
    all_tenants = await admin.list_tenants(include_deactivated=True)  # includes deactivated

    # Get (raises TenantNotFoundError or TenantDeactivatedError)
    info = await admin.get_tenant("acme-corp")

    # Update metadata
    # merge=True (default): merges new keys into existing metadata
    # merge=False: replaces entire metadata dict
    info = await admin.update_tenant_metadata("acme-corp", {"plan": "premium"}, merge=True)

    # Deactivate — records reason in metadata["deactivation_reason"]
    info = await admin.deactivate_tenant("acme-corp", reason="Payment overdue")
    assert info.status == TenantStatus.DEACTIVATED
    assert info.metadata["deactivation_reason"] == "Payment overdue"
    assert info.deactivated_at is not None

    # Reactivate — only from DEACTIVATED status
    info = await admin.reactivate_tenant("acme-corp")
    assert info.status == TenantStatus.ACTIVE

    # Delete permanently — calls on_delete callback first, then removes from registry
    await admin.delete_tenant("acme-corp")
finally:
    reset_tenant(token)
```

### Using `@system_operation`

```python
from cqrs_ddd_multitenancy import system_operation

@system_operation
async def provision_new_tenant(tenant_id: str, name: str):
    """Runs with __system__ context automatically."""
    return await admin.provision_tenant(tenant_id, name)

# No need to manually set/reset system tenant
tenant = await provision_new_tenant("new-corp", "New Corporation")
```

---

## Observability

Both observability modules use **lazy initialization** and gracefully no-op when their dependencies are not installed. Internal `HAS_PROMETHEUS` and `HAS_OTEL` flags (set via `try/except ImportError`) control whether real metrics/traces are emitted or silently skipped.

### Prometheus Metrics

```bash
pip install prometheus-client
```

The `_MetricsRegistry` singleton lazily initializes Prometheus collectors on first use:

| Metric | Type | Labels | Description |
|---|---|---|---|
| `tenant_resolution_duration_seconds` | Histogram | `resolver`, `status` | Time to resolve tenant ID |
| `tenant_resolution_total` | Counter | `resolver`, `status` | Total resolution attempts |
| `tenant_schema_switch_duration_seconds` | Histogram | `tenant_id` | Time for schema switches |
| `tenant_schema_switch_total` | Counter | `tenant_id`, `schema` | Total schema switches |

```python
from cqrs_ddd_multitenancy.observability import TenantMetrics

# Context manager — measures duration and records count
# Uses time.perf_counter() internally for high-resolution timing
with TenantMetrics.operation("resolve", tenant_id="tenant-123"):
    tenant_id = await resolver.resolve(request)
    # On success: records to resolution_duration + resolution_total with status="success"
    # On exception: records with status="error" and re-raises

# Direct recording functions
TenantMetrics.record_resolution("HeaderResolver", "tenant-123", success=True, duration=0.002)
TenantMetrics.record_schema_switch("tenant-123", "tenant_acme_corp", duration=0.001)

# Convenience functions (also available as module-level imports)
from cqrs_ddd_multitenancy.observability.metrics import (
    record_resolution_success,
    record_resolution_failure,
    record_schema_switch,
)
```

When `prometheus-client` is not installed, all operations are silent no-ops — zero overhead.

### OpenTelemetry Tracing

```bash
pip install opentelemetry-api
```

The `_TracerRegistry` singleton lazily initializes an OpenTelemetry tracer named `"cqrs-ddd-multitenancy"` on first use:

```python
from cqrs_ddd_multitenancy.observability import TenantTracing

# Three span types with structured naming convention:

# 1. Resolution spans — name: "tenant.resolve.{resolver_name}"
with TenantTracing.resolve_span("HeaderResolver") as span:
    TenantTracing.set_tenant(span, "tenant-123")
    TenantTracing.set_isolation_strategy(span, "discriminator_column")
    # Span attributes: tenant.id, tenant.isolation_strategy

# 2. Schema switch spans — name: "tenant.schema.switch"
with TenantTracing.schema_switch_span("tenant-123") as span:
    TenantTracing.set_schema(span, "tenant_acme_corp")
    # Span attributes: tenant.id, tenant.schema

# 3. Database switch spans — name: "tenant.database.switch"
with TenantTracing.database_switch_span("tenant-123") as span:
    TenantTracing.set_database(span, "app_acme_corp")
    # Span attributes: tenant.id, tenant.database
```

**Span attribute names:**

| Method | Attribute Key | Example Value |
|---|---|---|
| `set_tenant()` | `tenant.id` | `"tenant-123"` |
| `set_isolation_strategy()` | `tenant.isolation_strategy` | `"schema_per_tenant"` |
| `set_schema()` | `tenant.schema` | `"tenant_acme_corp"` |
| `set_database()` | `tenant.database` | `"app_acme_corp"` |

When `opentelemetry-api` is not installed, all spans are no-op context managers that yield `None` — zero overhead.

### Integration with Routing

The `SchemaRouter` and `DatabaseRouter` automatically emit observability data when available:
- **Schema switches** → `schema_switch_span` + `record_schema_switch`
- **Resolution** → `resolve_span` (used by middleware and resolvers)

---

## Testing

### In-Memory Adapters

Use `InMemoryTenantRegistry` and in-memory persistence adapters from core for unit tests:

```python
import pytest
from cqrs_ddd_multitenancy import set_tenant, reset_tenant, clear_tenant, SYSTEM_TENANT
from cqrs_ddd_multitenancy.admin import TenantAdmin, InMemoryTenantRegistry

@pytest.fixture(autouse=True)
def clear_context():
    """Reset tenant context between tests."""
    clear_tenant()
    yield
    clear_tenant()

@pytest.fixture
def system_context():
    """Set system tenant context."""
    token = set_tenant(SYSTEM_TENANT)
    yield
    reset_tenant(token)

@pytest.fixture
def admin():
    registry = InMemoryTenantRegistry()
    config = IsolationConfig(strategy=TenantIsolationStrategy.DISCRIMINATOR_COLUMN)
    return TenantAdmin(registry=registry, config=config)
```

### MRO Mixin Testing

Test tenant isolation with mock base classes:

```python
async def test_repository_filters_by_tenant():
    token = set_tenant("tenant-a")
    try:
        await repo.add(order_for_tenant_a)
    finally:
        reset_tenant(token)

    token = set_tenant("tenant-b")
    try:
        # Cannot see tenant-a's data
        result = await repo.get(order_for_tenant_a.id)
        assert result is None
    finally:
        reset_tenant(token)
```

### Architecture Tests

The package includes 21 architecture boundary tests using `pytest-archon`:

```python
from pytest_archon import archrule

def test_context_does_not_import_mixins():
    (archrule("context must not import mixins")
        .match("cqrs_ddd_multitenancy.context")
        .should_not_import("cqrs_ddd_multitenancy.mixins")
        .check("cqrs_ddd_multitenancy"))

def test_domain_does_not_import_infrastructure():
    (archrule("domain must not import infrastructure")
        .match("cqrs_ddd_multitenancy.domain")
        .should_not_import("cqrs_ddd_multitenancy.infrastructure")
        .check("cqrs_ddd_multitenancy"))
```

### Test Suite Statistics

| Category | Tests | Files |
|---|---|---|
| Unit tests | 477 | 27 |
| Integration tests | 85 | 4 |
| **Total** | **562** | **31** |
| **Coverage** | **93%** | |

---

## API Reference

### Context Functions

| Function | Description |
|---|---|
| `set_tenant(id) -> Token` | Set tenant context, returns reset token |
| `get_current_tenant() -> str` | Get tenant ID (raises `TenantContextMissingError` if not set) |
| `get_current_tenant_or_none() -> str \| None` | Get tenant ID or None |
| `require_tenant() -> str` | Alias for `get_current_tenant()` |
| `reset_tenant(token)` | Reset to previous context |
| `clear_tenant()` | Clear tenant context (set to None) |
| `is_system_tenant() -> bool` | Check if running as `__system__` |
| `is_tenant_context_set() -> bool` | Check if any tenant is set |
| `@system_operation` | Decorator that runs with `__system__` context |
| `with_tenant_context(id)` | Async context manager |
| `get_tenant_context_vars() -> dict` | Capture context for background task propagation |
| `propagate_tenant_context(fn, id)` | Wrap async function with tenant context |
| `run_in_tenant_context(id, fn, *args)` | Run sync function in tenant context |

### Exceptions

| Exception | Base | When Raised |
|---|---|---|
| `TenantError` | `DomainError` | Base for all tenant errors |
| `TenantContextMissingError` | `TenantError` | No tenant in context |
| `TenantNotFoundError` | `TenantError` | Tenant lookup failed |
| `TenantDeactivatedError` | `TenantError` | Deactivated tenant access |
| `CrossTenantAccessError` | `TenantError` | Cross-tenant access blocked |
| `TenantIsolationError` | `InfrastructureError` | Schema/database routing failure |
| `TenantProvisioningError` | `TenantIsolationError` | Tenant provisioning failure |

### Persistence Mixins

| Mixin | Port/Protocol | Key Methods |
|---|---|---|
| `MultitenantRepositoryMixin` | `IRepository` | `add`, `get`, `delete`, `search`, `list_all` |
| `StrictMultitenantRepositoryMixin` | `IRepository` | Same, but raises `CrossTenantAccessError` |
| `MultitenantEventStoreMixin` | `IEventStore` | `append`, `get_events`, `get_all`, `stream_all` (10 methods) |
| `MultitenantOutboxMixin` | `IOutboxStorage` | `save_messages`, `get_pending`, `mark_published` |
| `StrictMultitenantOutboxMixin` | `IOutboxStorage` | Same, with ownership validation |
| `MultitenantDispatcherMixin` | `IPersistenceDispatcher` | `apply`, `fetch_domain`, `fetch` |
| `MultitenantOperationPersistenceMixin` | `IOperationPersistence` | `persist` |
| `MultitenantRetrievalPersistenceMixin` | `IRetrievalPersistence` | `retrieve` |
| `MultitenantQueryPersistenceMixin` | `IQueryPersistence` | `fetch` |
| `MultitenantQuerySpecificationPersistenceMixin` | `IQuerySpecificationPersistence` | `fetch` |
| `MultitenantProjectionMixin` | `IProjectionWriter/Reader` | `get`, `upsert`, `find`, `delete` (6 methods) |
| `MultitenantProjectionPositionMixin` | `IProjectionPositionStore` | `get_position`, `save_position`, `reset_position` |
| `MultitenantSagaMixin` | `ISagaRepository` | `add`, `get`, `find_by_correlation_id` (11 methods) |
| `MultitenantSnapshotMixin` | `ISnapshotStore` | `save_snapshot`, `get_latest_snapshot`, `delete_snapshot` |
| `MultitenantCommandSchedulerMixin` | `ICommandScheduler` | `schedule`, `get_due_commands`, `cancel` |
| `MultitenantUpcasterMixin` | `IEventUpcaster` | `upcast` (preserves tenant_id) |
| `MultitenantBackgroundJobMixin` | `IBackgroundJobRepository` | `add`, `get`, `find_by_status` (11 methods) |

### Infrastructure Mixins

| Mixin | Port/Protocol | Key Methods |
|---|---|---|
| `MultitenantRedisCacheMixin` | `ICacheService` | `get`, `set`, `delete`, `exists`, `clear` |
| `MultitenantRedisLockMixin` | `ILockStrategy` | `acquire`, `release`, `extend`, `is_locked` |

### Projections Engine

| Class | Description |
|---|---|
| `MultitenantProjectionHandler` | Wraps handler to set tenant context per event |
| `TenantAwareProjectionRegistry` | Auto-wraps registered handlers |
| `MultitenantReplayMixin` | MRO mixin for `ReplayEngine` |
| `MultitenantWorkerMixin` | MRO mixin for `ProjectionWorker` |

---

## License

MIT
