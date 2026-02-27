# CQRS-DDD Toolkit

<div align="center">

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

**Enterprise-grade Python framework for Domain-Driven Design and CQRS applications**

[Quick Start](#-quick-start) • [Features](#-features) • [Packages](#-packages) • [Documentation](#-documentation) • [Examples](#-examples)

</div>

---

## 📖 Overview

A **composable**, **production-ready** toolkit for building scalable, maintainable domain-driven applications with CQRS architecture.

### Why CQRS-DDD Toolkit?

- ✅ **Zero Infrastructure Lock-in** — Core package has no infrastructure dependencies
- ✅ **Protocol-Based Design** — Clean separation between domain and infrastructure
- ✅ **Production-Ready** — Battle-tested patterns: Event Sourcing, Sagas, Outbox, Projections
- ✅ **Observable by Default** — Built-in instrumentation hooks, correlation IDs, tracing
- ✅ **Test-Friendly** — In-memory adapters for all ports enable fast unit tests
- ✅ **Polyglot Persistence** — Write side (PostgreSQL) separate from read side (MongoDB)

---

## 🚀 Quick Start

### Installation

```bash
# Core package (required)
pip install cqrs-ddd-core

# Advanced features (sagas, event sourcing, jobs, etc.)
pip install cqrs-ddd-advanced-core

# Specification pattern (type-safe queries)
pip install cqrs-ddd-specifications

# Persistence (choose one or both)
pip install cqrs-ddd-persistence-sqlalchemy  # PostgreSQL/SQLite
pip install cqrs-ddd-persistence-mongo       # MongoDB

# Infrastructure adapters
pip install cqrs-ddd-redis        # Distributed locking, caching
pip install cqrs-ddd-messaging    # RabbitMQ, Kafka, SQS

# Observability
pip install cqrs-ddd-observability  # OpenTelemetry, Prometheus, Sentry
pip install cqrs-ddd-health         # Health checks
```

### Minimal Example

```python
from cqrs_ddd_core import (
    Command, CommandHandler, CommandResponse,
    Mediator, HandlerRegistry, get_current_uow,
)
from cqrs_ddd_core.domain import AggregateRoot, DomainEvent

# 1. Define Domain
class OrderCreated(DomainEvent):
    order_id: str
    customer_id: str

class Order(AggregateRoot[str]):
    customer_id: str
    status: str = "pending"

    @classmethod
    def create(cls, order_id: str, customer_id: str) -> "Order":
        order = cls(id=order_id, customer_id=customer_id)
        order.add_event(OrderCreated(
            aggregate_id=order_id,
            order_id=order_id,
            customer_id=customer_id,
        ))
        return order

# 2. Define Command
class CreateOrderCommand(Command[str]):
    order_id: str
    customer_id: str

# 3. Define Handler
class CreateOrderHandler(CommandHandler[str]):
    async def handle(self, cmd: CreateOrderCommand) -> CommandResponse[str]:
        uow = get_current_uow()

        # Create order
        order = Order.create(cmd.order_id, cmd.customer_id)
        await uow.orders.add(order)

        # Return with events
        return CommandResponse(
            result=order.id,
            events=order.clear_events(),
        )

# 4. Wire Everything
registry = HandlerRegistry()
registry.register_command_handler(CreateOrderCommand, CreateOrderHandler())

mediator = Mediator(
    registry=registry,
    uow_factory=lambda: InMemoryUnitOfWork(),
)

# 5. Execute
response = await mediator.send(CreateOrderCommand(
    order_id="order-123",
    customer_id="cust-456",
))

print(f"Created order: {response.result}")
print(f"Events emitted: {len(response.events)}")
```

---

## ✨ Features

### Core Features
- 🏗️ **Domain Primitives** — `AggregateRoot`, `DomainEvent`, `ValueObject`, Mixins, Specifications
- 📤 **CQRS Pipeline** — `Mediator`, `Command`, `Query`, `EventDispatcher`, `HandlerRegistry`
- 🔌 **Protocol Ports** — `IRepository`, `IEventStore`, `IOutboxStorage`, `ILockStrategy`, `ICacheService`
- 🧪 **In-Memory Adapters** — Full test suite without databases
- 🔄 **Middleware Pipeline** — Logging, validation, outbox, locking, persistence
- 📊 **Instrumentation Hooks** — Observable without specific observability stack
- 🔗 **Correlation Context** — Automatic distributed tracing via ContextVar

### Advanced Features
- 🎭 **Event Sourcing** — Automatic persistence, snapshots, upcasting, replay
- 🔄 **Sagas** — TCC pattern, automatic compensation, state machine
- 📊 **Projections** — Build read models from event streams
- 🔀 **Conflict Resolution** — 5 merge strategies (deep merge, last wins, etc.)
- ⏰ **Command Scheduling** — Delayed execution with background workers
- ↩️ **Undo/Redo** — Reversible command execution with tokens
- 🗄️ **Background Jobs** — State machine, sweeper, admin service

### Infrastructure
- 🐘 **SQLAlchemy Persistence** — PostgreSQL/SQLite with FTS, JSONB, Geometry
- 🍃 **MongoDB Persistence** — Motor async, change streams, ACID transactions
- 🔴 **Redis** — Redlock distributed locking, FIFO locks, caching
- 📨 **Messaging** — RabbitMQ, Kafka, SQS with retry policies
- 📈 **Observability** — OpenTelemetry, Prometheus, Sentry, structured logging
- 🏥 **Health Checks** — Database, cache, worker probes

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    cqrs-ddd-core                            │
│  Domain • CQRS • Ports • Middleware • Validation • Fakes   │
│           (Zero Infrastructure Dependencies)                │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐
│  advanced    │  │specifications│  │ persistence          │
│  Sagas • ES  │  │  Query AST   │  │ sqlalchemy • mongo   │
└──────────────┘  └──────────────┘  └──────────────────────┘
        │                   │                   │
        └───────────────────┼───────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐
│    redis     │  │  messaging   │  │   observability      │
│ Lock • Cache │  │Rabbit • Kafka│  │OTel • Prometheus •   │
└──────────────┘  └──────────────┘  │      Sentry          │
                                      └──────────────────────┘
```

### Design Principles

1. **Strict Isolation** — Core package has zero infrastructure dependencies
2. **Protocol-Based Ports** — All infrastructure defined as `@runtime_checkable` protocols
3. **Composition over Inheritance** — Repositories use mixins for cross-cutting concerns
4. **Context Propagation** — Tenant/user context via `ContextVar`, not method parameters
5. **One-Way Data Flow** — Read models updated from events, never write back
6. **Interface Segregation** — Domain depends on `IBlobStorage` protocol, not AWS S3 SDK

---

## 📦 Packages

### Core Layer

| Package | Purpose | PyPI | README |
|:--------|:--------|:-----|:-------|
| **cqrs-ddd-core** | Domain primitives, CQRS pipeline, ports, middleware, validation, in-memory fakes | `pip install cqrs-ddd-core` | [README](packages/core/README.md) |

<details>
<summary><b>Core Package Structure</b></summary>

```
cqrs_ddd_core/
├── domain/             # AggregateRoot, DomainEvent, ValueObject, EventTypeRegistry
│   └── README.md       → Detailed domain layer docs
├── cqrs/               # Mediator, Command, Query, Handler, EventDispatcher
│   ├── outbox/         # BufferedOutbox, OutboxService
│   ├── publishers/     # TopicRoutingPublisher
│   └── README.md       → CQRS layer docs
├── ports/              # IRepository, IEventStore, ILockStrategy, ICacheService
│   └── README.md       → Port definitions
├── adapters/memory/    # In-memory implementations for testing
│   └── README.md       → Adapter implementations
├── middleware/         # Logging, Validation, Outbox, Locking middleware
│   └── README.md       → Middleware pipeline
├── primitives/         # Exception hierarchy, ResourceIdentifier, IIDGenerator
│   └── README.md       → Core utilities
└── validation/         # PydanticValidator, CompositeValidator, ValidationResult
    └── README.md       → Validation layer
```
</details>

### Advanced Layer

| Package | Purpose | PyPI | README |
|:--------|:--------|:-----|:-------|
| **cqrs-ddd-advanced-core** | Event sourcing, sagas, projections, conflict resolution, scheduling, undo/redo | `pip install cqrs-ddd-advanced-core` | [README](packages/advanced/README.md) |

<details>
<summary><b>Key Components</b></summary>

- **Event Sourcing** — `EventSourcedMediator`, `EventSourcedRepository`, snapshots, upcasting
- **Sagas** — `SagaBuilder`, `SagaManager`, TCC pattern with automatic compensation
- **Projections** — `ProjectionWorker`, `ProjectionRegistry`, checkpoint tracking
- **Conflict Resolution** — `DeepMergeStrategy`, `LastWinsStrategy`, 5 built-in strategies
- **Background Jobs** — `BackgroundJobService`, `JobSweeperWorker`, state machine
- **Command Scheduling** — `CommandSchedulerService`, delayed execution
- **Undo/Redo** — `UndoService`, `UndoToken`, reversible commands

</details>

### Specifications

| Package | Purpose | PyPI | README |
|:--------|:--------|:-----|:-------|
| **cqrs-ddd-specifications** | Specification pattern with fluent builder, composite operators, query options | `pip install cqrs-ddd-specifications` | [README](packages/specifications/README.md) |

### Persistence

| Package | Purpose | PyPI | README |
|:--------|:--------|:-----|:-------|
| **cqrs-ddd-persistence-sqlalchemy** | PostgreSQL/SQLite persistence with event store, outbox, sagas, projections | `pip install cqrs-ddd-persistence-sqlalchemy` | [README](packages/persistence/sqlalchemy/README.md) |
| **cqrs-ddd-persistence-mongo** | MongoDB persistence with Motor async, change streams, ACID transactions | `pip install cqrs-ddd-persistence-mongo` | [README](packages/persistence/mongo/README.md) |

### Infrastructure

| Package | Purpose | PyPI | README |
|:--------|:--------|:-----|:-------|
| **cqrs-ddd-redis** | Distributed locking (Redlock, FIFO), caching | `pip install cqrs-ddd-redis` | [README](packages/infrastructure/redis/README.md) |
| **cqrs-ddd-messaging** | RabbitMQ, Kafka, SQS adapters with retry policies | `pip install cqrs-ddd-messaging` | [README](packages/infrastructure/messaging/README.md) |
| **cqrs-ddd-observability** | OpenTelemetry, Prometheus, Sentry integration | `pip install cqrs-ddd-observability` | [README](packages/infrastructure/observability/README.md) |
| **cqrs-ddd-health** | Health check registry with database, cache, worker probes | `pip install cqrs-ddd-health` | [README](packages/infrastructure/health/README.md) |

### Features

| Package | Purpose | PyPI | README |
|:--------|:--------|:-----|:-------|
| **cqrs-ddd-filtering** | HTTP query parameter parsing with 24 operators | `pip install cqrs-ddd-filtering` | [README](packages/features/filtering/README.md) |

### Engines

| Package | Purpose | PyPI | README |
|:--------|:--------|:-----|:-------|
| **cqrs-ddd-projections** | Write-to-read synchronization engine | `pip install cqrs-ddd-projections` | [README](packages/engines/projections/README.md) |

---

## 📚 Documentation

### Package Documentation

Each package has detailed README with implementation details and usage examples:

| Package | Description | Link |
|:--------|:------------|:-----|
| Core | Domain, CQRS, Ports, Middleware, Validation | [packages/core/README.md](packages/core/README.md) |
| Advanced | Event Sourcing, Sagas, Projections, Jobs | [packages/advanced/README.md](packages/advanced/README.md) |
| Specifications | Query AST, Operators, Evaluators | [packages/specifications/README.md](packages/specifications/README.md) |
| SQLAlchemy Persistence | PostgreSQL/SQLite implementation | [packages/persistence/sqlalchemy/README.md](packages/persistence/sqlalchemy/README.md) |
| MongoDB Persistence | Motor async implementation | [packages/persistence/mongo/README.md](packages/persistence/mongo/README.md) |

### Subfolder Documentation

Core package has detailed README for each subfolder:

- [Domain Layer](packages/core/src/cqrs_ddd_core/domain/README.md) — Aggregates, events, value objects
- [CQRS Layer](packages/core/src/cqrs_ddd_core/cqrs/README.md) — Mediator, commands, queries
- [Ports](packages/core/src/cqrs_ddd_core/ports/README.md) — Protocol definitions
- [Adapters](packages/core/src/cqrs_ddd_core/adapters/README.md) — In-memory implementations
- [Middleware](packages/core/src/cqrs_ddd_core/middleware/README.md) — Pipeline components
- [Primitives](packages/core/src/cqrs_ddd_core/primitives/README.md) — Exceptions, ID generators
- [Validation](packages/core/src/cqrs_ddd_core/validation/README.md) — Validators

### Architecture Documentation

- [Package Organization](docs/package-organization.md) — Full package ecosystem
- [Architecture Decisions](docs/architecture_persistence_layers.md) — Persistence layer design
- [Projection Writer](docs/projection_writer.md) — Read model synchronization
- [Mongo vs SQLAlchemy](MONGO_VS_SQLALCHEMY_COMPARISON.md) — Comparison guide

---

## 💡 Examples

### Core CQRS Pattern

#### 1. Define Your Domain Model

```python
from cqrs_ddd_core.domain import AggregateRoot, DomainEvent, ValueObject
from datetime import datetime

# Value Object for money
class Money(ValueObject):
    amount: float
    currency: str = "USD"

# Domain Events
class OrderCreated(DomainEvent):
    order_id: str
    customer_id: str
    total: Money

class OrderItemAdded(DomainEvent):
    order_id: str
    product_id: str
    quantity: int
    price: Money

class OrderConfirmed(DomainEvent):
    order_id: str
    confirmed_at: datetime

# Aggregate Root
class Order(AggregateRoot[str]):
    customer_id: str
    items: list[dict] = []
    total: Money = Money(amount=0.0)
    status: str = "pending"

    @classmethod
    def create(cls, order_id: str, customer_id: str) -> "Order":
        """Factory method to create order."""
        order = cls(id=order_id, customer_id=customer_id)
        order.add_event(OrderCreated(
            aggregate_id=order_id,
            order_id=order_id,
            customer_id=customer_id,
            total=Money(amount=0.0),
        ))
        return order

    def add_item(self, product_id: str, quantity: int, price: Money) -> None:
        """Add item to order with business rules."""
        if self.status != "pending":
            raise ValueError("Can only add items to pending orders")

        if quantity <= 0:
            raise ValueError("Quantity must be positive")

        # Update state
        self.items.append({
            "product_id": product_id,
            "quantity": quantity,
            "price": price,
        })

        # Recalculate total
        total_amount = sum(
            item["price"].amount * item["quantity"]
            for item in self.items
        )
        self.total = Money(amount=total_amount)

        # Emit event
        self.add_event(OrderItemAdded(
            aggregate_id=self.id,
            order_id=self.id,
            product_id=product_id,
            quantity=quantity,
            price=price,
        ))

    def confirm(self) -> None:
        """Confirm the order."""
        if not self.items:
            raise ValueError("Cannot confirm empty order")

        if self.status != "pending":
            raise ValueError("Order already processed")

        self.status = "confirmed"
        self.add_event(OrderConfirmed(
            aggregate_id=self.id,
            order_id=self.id,
            confirmed_at=datetime.utcnow(),
        ))
```

#### 2. Define Commands and Handlers

```python
from cqrs_ddd_core.cqrs import Command, CommandHandler, CommandResponse, get_current_uow

# Commands
class CreateOrderCommand(Command[str]):
    order_id: str
    customer_id: str

class AddOrderItemCommand(Command[None]):
    order_id: str
    product_id: str
    quantity: int
    price_amount: float

class ConfirmOrderCommand(Command[None]):
    order_id: str

# Handlers
class CreateOrderHandler(CommandHandler[str]):
    async def handle(self, cmd: CreateOrderCommand) -> CommandResponse[str]:
        uow = get_current_uow()

        # Check if order exists
        existing = await uow.orders.get(cmd.order_id)
        if existing:
            raise ValueError(f"Order {cmd.order_id} already exists")

        # Create order
        order = Order.create(cmd.order_id, cmd.customer_id)
        await uow.orders.add(order)

        return CommandResponse(
            result=order.id,
            events=order.clear_events(),
        )

class AddOrderItemHandler(CommandHandler[None]):
    async def handle(self, cmd: AddOrderItemCommand) -> CommandResponse[None]:
        uow = get_current_uow()

        # Load order
        order = await uow.orders.get(cmd.order_id)
        if not order:
            raise ValueError(f"Order {cmd.order_id} not found")

        # Add item
        order.add_item(
            product_id=cmd.product_id,
            quantity=cmd.quantity,
            price=Money(amount=cmd.price_amount),
        )

        # Persist
        await uow.orders.add(order)

        return CommandResponse(
            result=None,
            events=order.clear_events(),
        )

class ConfirmOrderHandler(CommandHandler[None]):
    async def handle(self, cmd: ConfirmOrderCommand) -> CommandResponse[None]:
        uow = get_current_uow()

        order = await uow.orders.get(cmd.order_id)
        if not order:
            raise ValueError(f"Order {cmd.order_id} not found")

        order.confirm()
        await uow.orders.add(order)

        return CommandResponse(
            result=None,
            events=order.clear_events(),
        )
```

#### 3. Define Queries and Handlers

```python
from cqrs_ddd_core.cqrs import Query, QueryHandler, QueryResponse
from dataclasses import dataclass

# DTOs for read models
@dataclass
class OrderDTO:
    order_id: str
    customer_id: str
    total: float
    status: str
    item_count: int

# Queries
class GetOrderQuery(Query[OrderDTO]):
    order_id: str

class ListOrdersQuery(Query[list[OrderDTO]]):
    customer_id: str | None = None
    status: str | None = None
    limit: int = 100

# Handlers
class GetOrderHandler(QueryHandler[OrderDTO]):
    async def handle(self, query: GetOrderQuery) -> QueryResponse[OrderDTO]:
        uow = get_current_uow()

        # For queries, we could use a separate read model
        # Here we're using the aggregate for simplicity
        order = await uow.orders.get(query.order_id)
        if not order:
            return QueryResponse(result=None)

        dto = OrderDTO(
            order_id=order.id,
            customer_id=order.customer_id,
            total=order.total.amount,
            status=order.status,
            item_count=len(order.items),
        )

        return QueryResponse(result=dto)

class ListOrdersHandler(QueryHandler[list[OrderDTO]]):
    async def handle(self, query: ListOrdersQuery) -> QueryResponse[list[OrderDTO]]:
        uow = get_current_uow()

        # Build specification
        from cqrs_ddd_specifications import SpecificationBuilder
        spec_builder = SpecificationBuilder()

        if query.customer_id:
            spec_builder = spec_builder.where("customer_id", "==", query.customer_id)

        if query.status:
            spec_builder = spec_builder.where("status", "==", query.status)

        spec = spec_builder.build()

        # Search
        from cqrs_ddd_core.ports import QueryOptions
        options = QueryOptions().with_specification(spec).with_limit(query.limit)

        result = await uow.orders.search(options)
        orders = await result  # Await SearchResult

        # Convert to DTOs
        dtos = [
            OrderDTO(
                order_id=o.id,
                customer_id=o.customer_id,
                total=o.total.amount,
                status=o.status,
                item_count=len(o.items),
            )
            for o in orders
        ]

        return QueryResponse(result=dtos)
```

#### 4. Event Handlers (Side Effects)

```python
from cqrs_ddd_core.cqrs import EventHandler

class SendOrderConfirmationEmailHandler(EventHandler[OrderConfirmed]):
    def __init__(self, email_service: EmailService):
        self.email_service = email_service

    async def handle(self, event: OrderConfirmed) -> None:
        # Send email when order is confirmed
        await self.email_service.send(
            to=event.customer_id,  # Assuming customer_id is email
            subject="Order Confirmed",
            body=f"Your order {event.order_id} has been confirmed!",
        )

class UpdateInventoryHandler(EventHandler[OrderItemAdded]):
    def __init__(self, inventory_service: InventoryService):
        self.inventory_service = inventory_service

    async def handle(self, event: OrderItemAdded) -> None:
        # Update inventory
        await self.inventory_service.reserve(
            product_id=event.product_id,
            quantity=event.quantity,
        )
```

#### 5. Wire Everything Together

```python
from cqrs_ddd_core import Mediator, HandlerRegistry
from cqrs_ddd_core.middleware import LoggingMiddleware, ValidatorMiddleware

# Create registry
registry = HandlerRegistry()

# Register command handlers
registry.register_command_handler(CreateOrderCommand, CreateOrderHandler())
registry.register_command_handler(AddOrderItemCommand, AddOrderItemHandler())
registry.register_command_handler(ConfirmOrderCommand, ConfirmOrderHandler())

# Register query handlers
registry.register_query_handler(GetOrderQuery, GetOrderHandler())
registry.register_query_handler(ListOrdersQuery, ListOrdersHandler())

# Register event handlers
registry.register_event_handler(OrderConfirmed, SendOrderConfirmationEmailHandler(email_service))
registry.register_event_handler(OrderItemAdded, UpdateInventoryHandler(inventory_service))

# Create mediator with middleware
mediator = Mediator(
    registry=registry,
    uow_factory=lambda: SQLAlchemyUnitOfWork(session_factory),
    middleware_registry=MiddlewareRegistry([
        LoggingMiddleware(),
        ValidatorMiddleware(),
    ]),
)

# Execute commands
async def create_and_confirm_order():
    # Create order
    order_id = await mediator.send(CreateOrderCommand(
        order_id="order-123",
        customer_id="cust-456",
    ))

    # Add items
    await mediator.send(AddOrderItemCommand(
        order_id="order-123",
        product_id="prod-789",
        quantity=2,
        price_amount=29.99,
    ))

    # Confirm
    await mediator.send(ConfirmOrderCommand(
        order_id="order-123",
    ))

    # Query
    order = await mediator.send(GetOrderQuery(order_id="order-123"))
    print(f"Order: {order}")
```

### Event Sourcing with Snapshots

```python
from cqrs_ddd_advanced_core.event_sourcing import EventSourcedMediator, EventSourcedRepository
from cqrs_ddd_advanced_core.snapshots import EveryNEventsStrategy, JSONSnapshotSerializer

# Configure event-sourced repository
order_repo = EventSourcedRepository(
    event_store=event_store,
    snapshot_store=snapshot_store,
    aggregate_cls=Order,
)

# Snapshot every 100 events for performance
mediator = EventSourcedMediator(
    registry=registry,
    event_store=event_store,
    snapshot_store=snapshot_store,
    snapshot_strategy=EveryNEventsStrategy(every_n=100),
    snapshot_serializer=JSONSnapshotSerializer(),
)

# Load aggregate (from snapshot + recent events)
order = await mediator.load("order-123")

# Or replay entire history
order = await mediator.load("order-123", from_version=0)

# Save with automatic snapshotting
await mediator.save(order)
```

#### Event Upcasting (Schema Evolution)

```python
from cqrs_ddd_advanced_core.upcasting import UpcasterRegistry, EventUpcaster

# Upcast OrderCreated v1 to v2
class OrderCreatedV1ToV2Upcaster(EventUpcaster):
    supported_type = "OrderCreated"
    from_version = 1
    to_version = 2

    def upcast(self, payload: dict) -> dict:
        # Add new field with default
        payload["shipping_method"] = payload.get("shipping_method", "standard")
        # Rename field
        if "cust_id" in payload:
            payload["customer_id"] = payload.pop("cust_id")
        return payload

# Register upcasters
upcaster_registry = UpcasterRegistry()
upcaster_registry.register(OrderCreatedV1ToV2Upcaster())

# Event store uses upcasters automatically
event_store = SQLAlchemyEventStore(
    session_factory=session_factory,
    upcaster_registry=upcaster_registry,
)
```

### Saga with TCC Pattern

```python
from cqrs_ddd_advanced_core.sagas import SagaBuilder, bootstrap_sagas, SagaManager

# Define saga with compensation
OrderFulfillmentSaga = (
    SagaBuilder("OrderFulfillment")
    # Step 1: Reserve items
    .on(OrderCreated,
        send=lambda e: ReserveItems(order_id=e.order_id, items=e.items),
        step="reserving",
        compensate=lambda e: CancelReservation(order_id=e.order_id))
    # Step 2: Charge payment
    .on(ItemsReserved,
        send=lambda e: ChargePayment(
            order_id=e.order_id,
            amount=e.total,
            payment_method_id=e.payment_method_id,
        ),
        step="charging",
        compensate=lambda e: RefundPayment(
            order_id=e.order_id,
            amount=e.total,
        ))
    # Step 3: Confirm order (final step)
    .on(PaymentCharged,
        send=lambda e: ConfirmOrder(order_id=e.order_id),
        step="confirming",
        complete=True)
    .build()
)

# Bootstrap saga manager
manager = await bootstrap_sagas(
    sagas=[OrderFulfillmentSaga, PaymentProcessingSaga, ShippingSaga],
    repository=SQLAlchemySagaRepository(session_factory),
    command_bus=mediator,
    lock_strategy=redis_lock,
)

# Saga executes automatically when OrderCreated event is dispatched
# If any step fails, compensating actions execute in reverse order
```

#### Manual Saga Control

```python
# Get saga state
saga_state = await manager.get_saga_state(saga_id="saga-123")

# Retry failed step
await manager.retry_step(saga_id="saga-123", step_name="charging")

# Force compensation (manual rollback)
await manager.compensate(saga_id="saga-123")

# List active sagas
active_sagas = await manager.list_active()
```

### Specification Pattern with Advanced Queries

```python
from cqrs_ddd_specifications import SpecificationBuilder, QueryOptions
from cqrs_ddd_core.ports import SearchResult

# Complex specification with multiple operators
spec = (
    SpecificationBuilder()
    # Standard operators
    .where("status", "==", "active")
    .where("total", ">", 100)
    .where("customer_id", "in", ["cust-1", "cust-2"])
    # String operators
    .where("name", "contains", "Order")
    .where("description", "starts_with", "Premium")
    # Null checks
    .where("deleted_at", "is_null")
    # Range operators
    .where("created_at", "between", ["2024-01-01", "2024-12-31"])
    # JSON path queries
    .where("metadata.priority", ">", 5)
    # Composite operators
    .where("tags", "contains_any", ["urgent", "priority"])
    .build()
)

# With pagination, ordering, and field projection
options = (
    QueryOptions()
    .with_specification(spec)
    .with_pagination(limit=20, offset=40)
    .with_ordering("-created_at", "name")  # DESC created_at, ASC name
    .with_fields(["id", "name", "status", "total"])  # Project only needed fields
    .with_grouping("customer_id")  # Group by customer
    .with_aggregation("total", "sum")  # Calculate sum
)

# Execute on repository
result: SearchResult = await repository.search(options)

# Access results
orders = await result  # Get all items
async for batch in result.stream(batch_size=100):  # Stream in batches
    for order in batch:
        process(order)

# Get total count
total = await result.total_count()

# Get aggregations
aggregations = await result.aggregations()
print(f"Total revenue: {aggregations['total_sum']}")
```

#### Specification Reuse

```python
# Create reusable specifications
ActiveOrdersSpec = (
    SpecificationBuilder()
    .where("status", "in", ["pending", "processing"])
    .where("deleted_at", "is_null")
    .build()
)

HighValueOrdersSpec = (
    SpecificationBuilder()
    .where("total", ">", 1000)
    .build()
)

# Compose specifications
from cqrs_ddd_specifications import AndSpecification

PremiumActiveOrdersSpec = AndSpecification(ActiveOrdersSpec, HighValueOrdersSpec)

# Use composed spec
options = QueryOptions().with_specification(PremiumActiveOrdersSpec)
result = await repository.search(options)
```

### Distributed Locking with Redis

```python
from cqrs_ddd_redis import RedlockLockStrategy, FifoRedisLockStrategy
from cqrs_ddd_core.cqrs.concurrency import CriticalSection
from cqrs_ddd_core.primitives.locking import ResourceIdentifier

# Redlock for high availability (3-node quorum)
redlock = RedlockLockStrategy([
    "redis://redis-1:6379",
    "redis://redis-2:6379",
    "redis://redis-3:6379",
], retry_count=3, retry_delay=0.2)

# FIFO lock for strict ordering
fifo_lock = FifoRedisLockStrategy(
    redis_url="redis://localhost:6379",
    timeout=30.0,
)

# Lock single resource
async with CriticalSection(
    resources=[ResourceIdentifier("Order", "order-123")],
    lock_strategy=redlock,
    timeout=10.0,
    ttl=60.0,
) as section:
    order = await order_repo.get("order-123")
    order.process()
    await order_repo.add(order)

# Lock multiple resources (deadlock-free)
resources = [
    ResourceIdentifier("Account", "acc-123"),
    ResourceIdentifier("Account", "acc-456"),
]

async with CriticalSection(resources, fifo_lock, timeout=15.0):
    # Both accounts locked atomically
    await transfer_funds(from_acc="acc-123", to_acc="acc-456", amount=100)

# Reentrant locking with session_id
session_id = "user-session-abc"

async def outer_operation():
    async with CriticalSection(
        [ResourceIdentifier("Order", "order-123")],
        lock_strategy=redlock,
        session_id=session_id,
    ):
        await inner_operation()

async def inner_operation():
    async with CriticalSection(
        [ResourceIdentifier("Order", "order-123")],
        lock_strategy=redlock,
        session_id=session_id,  # Same session = reentrant
    ):
        # Lock acquired again (same session)
        await process_order("order-123")
```

### Transactional Outbox Pattern

```python
from cqrs_ddd_core.cqrs.outbox import BufferedOutbox, OutboxService
from cqrs_ddd_core.middleware import OutboxMiddleware

# Setup outbox
outbox = BufferedOutbox(
    storage=SQLAlchemyOutboxStorage(session_factory),
    broker=KafkaPublisher(kafka_config),
    lock_strategy=redis_lock,
    batch_size=100,
    max_retries=5,
)

# Start background worker
await outbox.start()

# Register middleware
middleware_registry = MiddlewareRegistry()
middleware_registry.register(OutboxMiddleware(outbox), priority=20)

# Mediator automatically saves events to outbox
mediator = Mediator(
    registry=handler_registry,
    uow_factory=lambda: SQLAlchemyUnitOfWork(session_factory),
    middleware_registry=middleware_registry,
)

# Send command - events automatically go to outbox
response = await mediator.send(CreateOrderCommand(...))

# Events are:
# 1. Saved to outbox table in same transaction as order
# 2. Published to Kafka by background worker
# 3. Retried on failure with exponential backoff
```

### Background Jobs

```python
from cqrs_ddd_advanced_core.background_jobs import (
    BackgroundJobService,
    BackgroundJobAdminService,
    JobSweeperWorker,
)

# Create job service
job_service = BackgroundJobService(
    repository=SQLAlchemyBackgroundJobRepository(session_factory),
    lock_strategy=redis_lock,
)

# Schedule job
job_id = await job_service.schedule(
    job_type="ProcessLargeFile",
    payload={"file_id": "file-123", "size": 1024000},
    scheduled_at=datetime.utcnow() + timedelta(hours=1),  # Delayed execution
    max_retries=5,
    timeout_seconds=300,
)

# Process job in worker
async def process_file_worker():
    pending = await job_service.get_pending_jobs(limit=10)

    for job in pending:
        try:
            # Mark as running
            await job_service.mark_running(job.job_id)

            # Process
            await process_large_file(job.payload["file_id"])

            # Mark complete
            await job_service.mark_completed(job.job_id)
        except Exception as e:
            # Mark failed (will be retried)
            await job_service.mark_failed(job.job_id, error=str(e))

# Admin operations
admin = BackgroundJobAdminService(job_service)

# Retry failed job
await admin.retry_job("job-123")

# Cancel scheduled job
await admin.cancel_job("job-456")

# Get job statistics
stats = await admin.get_statistics()
print(f"Pending: {stats.pending}, Running: {stats.running}, Failed: {stats.failed}")
```

### Undo/Redo Service

```python
from cqrs_ddd_advanced_core.undo import UndoService, UndoExecutor

# Setup undo service
undo_service = UndoService(
    event_store=event_store,
    repository=undo_token_repository,
)

# Execute command with undo support
async def create_order_with_undo():
    # Execute command
    response = await mediator.send(CreateOrderCommand(
        order_id="order-123",
        customer_id="cust-456",
    ))

    # Generate undo token
    undo_token = await undo_service.create_token(
        aggregate_id="order-123",
        aggregate_type="Order",
        events=response.events,
    )

    return {
        "order_id": response.result,
        "undo_token": undo_token.token_id,
    }

# Undo operation
async def undo_order(undo_token_id: str):
    # Execute undo
    executor = UndoExecutor(mediator, event_store)
    await executor.undo(undo_token_id)

    # Order is now reverted to previous state

# Redo operation
async def redo_order(undo_token_id: str):
    executor = UndoExecutor(mediator, event_store)
    await executor.redo(undo_token_id)

    # Order is back to the state it was before undo
```

### Observability and Monitoring

```python
from cqrs_ddd_observability import (
    install_framework_hooks,
    TracingMiddleware,
    MetricsMiddleware,
    SentryMiddleware,
)

# One call to enable tracing across entire framework
install_framework_hooks()

# Add middleware for per-command observability
mediator = Mediator(
    registry=handler_registry,
    uow_factory=uow_factory,
    middleware_registry=MiddlewareRegistry([
        TracingMiddleware(),  # OpenTelemetry spans
        MetricsMiddleware(),  # Prometheus metrics
        SentryMiddleware(),   # Error tracking
        LoggingMiddleware(),  # Structured logging
    ]),
)

# All operations now emit:
# - OpenTelemetry spans
# - Prometheus counters/histograms
# - Sentry error events
# - Structured JSON logs
```

### Health Checks

```python
from cqrs_ddd_health import HealthRegistry, DatabaseHealthCheck, RedisHealthCheck

# Get singleton registry
health = HealthRegistry.get_instance()

# Register health checks
health.register("database", DatabaseHealthCheck(session_factory))
health.register("redis", RedisHealthCheck(redis_client))
health.register("kafka", MessageBrokerHealthCheck(kafka_consumer))

# Kubernetes liveness probe
@app.get("/health/live")
async def liveness():
    report = await health.status()
    return {"status": report.status}

# Kubernetes readiness probe
@app.get("/health/ready")
async def readiness():
    report = await health.status()
    if report.status == "healthy":
        return {"status": "ready"}
    raise HTTPException(503, detail=report.to_dict())
```

---

## 🧪 Testing

All packages have in-memory adapters for fast unit tests:

```python
from cqrs_ddd_core import InMemoryRepository, InMemoryUnitOfWork

# No database needed!
repo = InMemoryRepository[Order, str]()
uow = InMemoryUnitOfWork()

# Test handler
handler = CreateOrderHandler(repo)
result = await handler.handle(CreateOrderCommand(...))

assert await repo.get("order-123") is not None
```

---

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details.

### Development Setup

```bash
# Clone repo
git clone https://github.com/mgourlis/cqrs-ddd.git
cd cqrs-ddd

# Install dependencies
uv sync

# Run tests
python3 -m pytest packages/core/tests/ -v

# Run linting
ruff check packages/
pyright packages/
```

---

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

Built with inspiration from:
- Domain-Driven Design by Eric Evans
- CQRS by Greg Young
- Event Sourcing patterns by Martin Fowler
- Saga pattern by Hector Garcia-Molina

---

<div align="center">

**[⬆ Back to Top](#cqrs-ddd-toolkit)**

Made with ❤️ by the CQRS-DDD Team

</div>
