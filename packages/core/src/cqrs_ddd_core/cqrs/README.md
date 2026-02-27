# CQRS Layer - Implementation Details & Usage

**Package:** `cqrs_ddd_core.cqrs`
**Purpose:** Command Query Responsibility Segregation with Mediator pattern

---

## Overview

The CQRS layer implements the Command Query Responsibility Segregation pattern with a central mediator for dispatching commands and queries.

### Components

| Component | Purpose | File |
|-----------|---------|------|
| **Mediator** | Central dispatch point | `mediator.py` |
| **Command** | Write operation intent | `command.py` |
| **Query** | Read operation request | `query.py` |
| **Handler** | Business logic executor | `handler.py` |
| **Response** | Result wrapper | `response.py` |
| **EventDispatcher** | Event distribution | `event_dispatcher.py` |
| **Registry** | Handler registration | `registry.py` |
| **MessageRegistry** | Message deserialization | `message_registry.py` |
| **CriticalSection** | Multi-resource locking | `concurrency.py` |

### Subdirectories

- `outbox/` - Outbox pattern implementation
- `publishers/` - Event publishers
- `consumers/` - Event consumers

---

## Mediator

### Implementation

```python
from cqrs_ddd_core.cqrs.mediator import Mediator, get_current_uow

class Mediator(ICommandBus, IQueryBus):
    """
    Central dispatch with ContextVar UoW scope.

    Features:
    - Root vs nested command detection
    - Automatic correlation ID propagation
    - Middleware pipeline execution
    - Event dispatching from responses
    """

    def __init__(
        self,
        registry: HandlerRegistry,
        uow_factory: Callable[..., UnitOfWork],
        *,
        middleware_registry: MiddlewareRegistry | None = None,
        event_dispatcher: EventDispatcher | None = None,
    ): ...
```

### Usage Examples

#### Basic Setup

```python
from cqrs_ddd_core.cqrs.mediator import Mediator
from cqrs_ddd_core.cqrs.registry import HandlerRegistry
from cqrs_ddd_core.adapters.memory.unit_of_work import InMemoryUnitOfWork

# Create registry
registry = HandlerRegistry()
registry.register_command_handler(CreateOrderCommand, CreateOrderHandler())

# Create mediator
mediator = Mediator(
    registry=registry,
    uow_factory=lambda: InMemoryUnitOfWork(),
)

# Dispatch command
command = CreateOrderCommand(customer_id="cust-123")
response = await mediator.send(command)

print(response.result)  # Order ID
print(len(response.events))  # Domain events
```

#### Nested Commands (Shared UoW)

```python
class ShipOrderHandler(CommandHandler[None]):
    async def handle(self, command: ShipOrderCommand) -> CommandResponse[None]:
        # Get UoW from context (inherited from parent)
        uow = get_current_uow()

        # Nested command reuses same UoW
        await mediator.send(GenerateInvoiceCommand(order_id=command.order_id))

        order = await uow.orders.get(command.order_id)
        order.ship()

        return CommandResponse(result=None, events=order.clear_events())

# Root command creates new UoW, nested commands reuse it
response = await mediator.send(ShipOrderCommand(order_id="order-123"))
# Single commit at root level
```

#### With Middleware

```python
from cqrs_ddd_core.middleware.registry import MiddlewareRegistry
from cqrs_ddd_core.middleware.logging import LoggingMiddleware

middleware_registry = MiddlewareRegistry()
middleware_registry.register(LoggingMiddleware())

mediator = Mediator(
    registry=registry,
    uow_factory=uow_factory,
    middleware_registry=middleware_registry,
)
```

---

## Commands

### Implementation

```python
from cqrs_ddd_core.cqrs.command import Command

class Command(BaseModel, Generic[TResult]):
    """
    Base class for all commands.

    Features:
    - Auto-generated command_id
    - Inherited correlation_id
    - Optional pessimistic locking
    """

    command_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: str | None = Field(default_factory=get_correlation_id)

    def get_critical_resources(self) -> list[ResourceIdentifier]:
        """Override for pessimistic locking."""
        return []
```

### Usage Examples

#### Basic Command

```python
from cqrs_ddd_core.cqrs.command import Command

class CreateOrderCommand(Command[str]):
    """Command to create order."""

    customer_id: str
    items: list[OrderItem]

# Usage
command = CreateOrderCommand(customer_id="cust-123", items=[...])
print(command.command_id)  # Auto-generated UUID
```

#### Command with Locking

```python
from cqrs_ddd_core.primitives.locking import ResourceIdentifier

class TransferFundsCommand(Command[None]):
    """Transfer with pessimistic locking."""

    from_account: str
    to_account: str
    amount: float

    def get_critical_resources(self) -> list[ResourceIdentifier]:
        """Lock both accounts."""
        return [
            ResourceIdentifier("Account", self.from_account),
            ResourceIdentifier("Account", self.to_account),
        ]
```

---

## Queries

### Implementation

```python
from cqrs_ddd_core.cqrs.query import Query

class Query(BaseModel, Generic[TResult]):
    """
    Base class for all queries.

    Features:
    - Auto-generated query_id
    - Inherited correlation_id
    - Read-only (never modifies state)
    """

    query_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: str | None = Field(default_factory=get_correlation_id)
```

### Usage Examples

```python
from cqrs_ddd_core.cqrs.query import Query

class GetOrderQuery(Query[OrderDTO]):
    """Query to get order by ID."""

    order_id: str

class ListOrdersQuery(Query[list[OrderDTO]]):
    """Query to list orders."""

    customer_id: str | None = None
    status: str | None = None
    limit: int = 100

# Usage
query = GetOrderQuery(order_id="order-123")
response = await mediator.send(query)

order_dto: OrderDTO = response.result  # Typed result
```

---

## Handlers

### Implementation

```python
from cqrs_ddd_core.cqrs.handler import CommandHandler, QueryHandler

class CommandHandler(ABC, Generic[TResult]):
    """Base class for command handlers."""

    @abstractmethod
    async def handle(self, command: Command[TResult]) -> CommandResponse[TResult]:
        ...

class QueryHandler(ABC, Generic[TResult]):
    """Base class for query handlers."""

    @abstractmethod
    async def handle(self, query: Query[TResult]) -> QueryResponse[TResult]:
        ...
```

### Usage Examples

#### Command Handler

```python
from cqrs_ddd_core.cqrs.handler import CommandHandler
from cqrs_ddd_core.cqrs.mediator import get_current_uow

class CreateOrderHandler(CommandHandler[str]):
    async def handle(self, command: CreateOrderCommand) -> CommandResponse[str]:
        # Get UoW from context
        uow = get_current_uow()

        # Execute business logic
        order = Order.create(command.customer_id, command.items)
        await uow.orders.add(order)

        # Return with events
        return CommandResponse(
            result=order.id,
            events=order.clear_events(),
        )
```

#### Query Handler

```python
class GetOrderHandler(QueryHandler[OrderDTO]):
    async def handle(self, query: GetOrderQuery) -> QueryResponse[OrderDTO]:
        uow = get_current_uow()
        order = await uow.orders.get(query.order_id)

        # Convert to DTO (no events)
        dto = OrderDTO.from_aggregate(order)
        return QueryResponse(result=dto)
```

---

## Responses

### Implementation

```python
from cqrs_ddd_core.cqrs.response import CommandResponse, QueryResponse

@dataclass(frozen=True)
class CommandResponse(Generic[T]):
    """Wrapper for command results."""

    result: T
    events: list[DomainEvent] = field(default_factory=list)
    success: bool = True
    correlation_id: str | None = None
    causation_id: str | None = None

@dataclass(frozen=True)
class QueryResponse(Generic[T]):
    """Wrapper for query results."""

    result: T
    success: bool = True
    correlation_id: str | None = None
    causation_id: str | None = None
```

### Usage Examples

```python
# Command response with events
return CommandResponse(
    result=order.id,
    events=order.clear_events(),
    success=True,
)

# Query response (no events)
return QueryResponse(
    result=OrderDTO.from_aggregate(order),
)

# Failed response
return CommandResponse(
    result=None,
    events=[],
    success=False,
)
```

---

## EventDispatcher

### Implementation

```python
from cqrs_ddd_core.cqrs.event_dispatcher import EventDispatcher

class EventDispatcher(Generic[E]):
    """
    Event dispatcher with retry and instrumentation.

    Features:
    - Async dispatch
    - Retry on failure
    - Priority-based execution
    - Hook integration
    """
```

### Usage Examples

```python
from cqrs_ddd_core.cqrs.event_dispatcher import EventDispatcher

# Create dispatcher
dispatcher = EventDispatcher[DomainEvent]()

# Register handlers
dispatcher.register(OrderCreated, OrderCreatedHandler())
dispatcher.register(OrderConfirmed, OrderConfirmedHandler())

# Dispatch event
event = OrderCreated(aggregate_id="order-123", customer_id="cust-456")
await dispatcher.dispatch(event)

# All handlers execute asynchronously
```

---

## MessageRegistry

### Implementation

```python
from cqrs_ddd_core.cqrs.message_registry import MessageRegistry

class MessageRegistry:
    """
    Registry for mapping message type names to Command and Query classes.

    Used to reconstruct messages (commands and queries) from stored payloads.
    Explicit registration is required.

    Features:
    - Command registration and hydration
    - Query registration and hydration
    - Type-safe deserialization
    - Instrumentation hooks
    """
```

### Usage Examples

#### Basic Registration

```python
from cqrs_ddd_core.cqrs.message_registry import MessageRegistry

# Create registry
registry = MessageRegistry()

# Register commands and queries
registry.register_command("CreateOrderCommand", CreateOrderCommand)
registry.register_query("GetOrderQuery", GetOrderQuery)

# Check registration
assert registry.has_command("CreateOrderCommand")
assert registry.has_query("GetOrderQuery")
```

#### Hydrating Messages (Deserialization)

```python
from cqrs_ddd_core.cqrs.message_registry import MessageRegistry

registry = MessageRegistry()
registry.register_command("CreateOrderCommand", CreateOrderCommand)

# Reconstruct command from payload (e.g., from message queue)
payload = {
    "customer_id": "cust-123",
    "items": [{"product_id": "prod-456", "quantity": 2}],
}

command = registry.hydrate_command("CreateOrderCommand", payload)

if command:
    # Command is now a fully typed CreateOrderCommand instance
    response = await mediator.send(command)
else:
    print("Unknown command type")
```

#### Query Hydration

```python
registry = MessageRegistry()
registry.register_query("GetOrderQuery", GetOrderQuery)

# Reconstruct query from payload
payload = {"order_id": "order-123"}

query = registry.hydrate_query("GetOrderQuery", payload)

if query:
    response = await mediator.send(query)
```

#### Full Integration Example

```python
from cqrs_ddd_core.cqrs.message_registry import MessageRegistry
from cqrs_ddd_core.cqrs.mediator import Mediator
from cqrs_ddd_core.cqrs.registry import HandlerRegistry

# Setup registries
handler_registry = HandlerRegistry()
message_registry = MessageRegistry()

# Register handlers
handler_registry.register_command_handler(CreateOrderCommand, CreateOrderHandler())
handler_registry.register_query_handler(GetOrderQuery, GetOrderHandler())

# Register message types for deserialization
message_registry.register_command("CreateOrderCommand", CreateOrderCommand)
message_registry.register_query("GetOrderQuery", GetOrderQuery)

# Mediator
mediator = Mediator(registry=handler_registry, uow_factory=lambda: InMemoryUnitOfWork())

# Process incoming message from queue
def process_message(message_type: str, payload: dict):
    # Try command first
    command = message_registry.hydrate_command(message_type, payload)
    if command:
        return await mediator.send(command)

    # Try query
    query = message_registry.hydrate_query(message_type, payload)
    if query:
        return await mediator.send(query)

    raise ValueError(f"Unknown message type: {message_type}")
```

---

## CriticalSection

### Implementation

```python
from cqrs_ddd_core.cqrs.concurrency import CriticalSection

class CriticalSection:
    """
    Async context manager that acquires locks on multiple resources.

    Features:
    - Locks multiple resources atomically
    - Prevents deadlocks via sorted acquisition
    - Supports reentrancy via session_id
    - Auto-releases on exit
    - Rolls back partial locks on failure
    """
```

### Usage Examples

#### Basic Multi-Resource Locking

```python
from cqrs_ddd_core.cqrs.concurrency import CriticalSection
from cqrs_ddd_core.primitives.locking import ResourceIdentifier
from cqrs_ddd_core.adapters.memory.locking import InMemoryLockStrategy

# Define resources to lock
resources = [
    ResourceIdentifier("Account", "123"),
    ResourceIdentifier("Account", "456"),
]

# Acquire locks atomically
async with CriticalSection(resources, lock_strategy) as section:
    # Both accounts are locked here
    await transfer_funds(from_account="123", to_account="456", amount=100)
    # Locks auto-released on exit
```

#### With Custom Timeout and TTL

```python
resources = [
    ResourceIdentifier("Order", "order-123"),
]

async with CriticalSection(
    resources,
    lock_strategy=redis_lock,
    timeout=5.0,     # Wait up to 5s per lock
    ttl=60.0,        # Locks expire after 60s
) as section:
    await process_order("order-123")
```

#### Preventing Deadlocks

```python
# Resources are automatically sorted to prevent deadlocks
resources_a = [
    ResourceIdentifier("Account", "123"),
    ResourceIdentifier("Account", "456"),
]

resources_b = [
    ResourceIdentifier("Account", "456"),  # Different order
    ResourceIdentifier("Account", "123"),
]

# Both will acquire in same order: 123, 456 → no deadlock
async with CriticalSection(resources_a, lock_strategy):
    ...

async with CriticalSection(resources_b, lock_strategy):
    ...
```

#### Reentrant Locking (Same Session)

```python
from cqrs_ddd_core.cqrs.concurrency import CriticalSection

# Same session ID allows reentrant locking
session_id = "user-session-abc"

async def outer_operation():
    resources = [ResourceIdentifier("Order", "order-123")]

    async with CriticalSection(resources, lock_strategy, session_id=session_id):
        # Lock acquired
        await inner_operation()

async def inner_operation():
    resources = [ResourceIdentifier("Order", "order-123")]

    async with CriticalSection(resources, lock_strategy, session_id=session_id):
        # Same session → reentrant lock allowed
        await process_order("order-123")
```

#### Error Handling and Rollback

```python
from cqrs_ddd_core.primitives.exceptions import LockAcquisitionError

resources = [
    ResourceIdentifier("Account", "123"),
    ResourceIdentifier("Account", "456"),
]

try:
    async with CriticalSection(resources, lock_strategy, timeout=10.0):
        # If lock on "456" fails, lock on "123" is auto-released
        await transfer_funds()
except LockAcquisitionError as e:
    print(f"Failed to acquire lock: {e.resource}")
    print(f"Timeout: {e.timeout}s")
    print(f"Reason: {e.reason}")
```

---

## Registry

### Implementation

```python
from cqrs_ddd_core.cqrs.registry import HandlerRegistry

registry = HandlerRegistry()

# Register command handler
registry.register_command_handler(CreateOrderCommand, CreateOrderHandler())

# Register query handler
registry.register_query_handler(GetOrderQuery, GetOrderHandler())

# Register event handler
registry.register_event_handler(OrderCreated, OrderCreatedHandler())

# With factory (dependency injection)
def create_handler() -> CreateOrderHandler:
    email_service = EmailService()
    return CreateOrderHandler(email_service)

registry.register_command_handler(CreateOrderCommand, create_handler)
```

---

## Outbox (`outbox/`)

### Overview

The outbox package implements the **transactional outbox pattern** for reliable event publishing.

**Files:**
- `buffered.py` - Unified publisher and background worker
- `service.py` - Core processing logic with locking

### BufferedOutbox

**Implementation:**

```python
from cqrs_ddd_core.cqrs.outbox.buffered import BufferedOutbox

class BufferedOutbox(IMessagePublisher, IBackgroundWorker):
    """
    Unified Outbox component for both recording and publishing.

    Roles:
    1. Publisher: Saves messages to DB (IMessagePublisher)
    2. Worker: Background loop that publishes to broker (IBackgroundWorker)

    Features:
    - Automatic persistence in same transaction
    - Debounced background publishing
    - Batch processing
    - Retry on failure
    """
```

**Usage Examples:**

#### Basic Setup

```python
from cqrs_ddd_core.cqrs.outbox.buffered import BufferedOutbox
from cqrs_ddd_core.adapters.memory.outbox import InMemoryOutboxStorage
from cqrs_ddd_core.adapters.memory.locking import InMemoryLockStrategy

# Create outbox
outbox = BufferedOutbox(
    storage=InMemoryOutboxStorage(),
    broker=rabbitmq_publisher,  # Your message broker
    lock_strategy=InMemoryLockStrategy(),
    batch_size=50,
    max_retries=5,
)

# Start background worker
await outbox.start()

# Publish event (saved to DB, triggers immediate processing)
await outbox.publish("OrderCreated", event)
```

#### Integration with Mediator

```python
from cqrs_ddd_core.cqrs.mediator import Mediator
from cqrs_ddd_core.middleware.outbox import OutboxMiddleware

# Create outbox
outbox = BufferedOutbox(storage=db_outbox, broker=kafka)

# Register middleware
middleware_registry = MiddlewareRegistry()
middleware_registry.register(OutboxMiddleware(outbox), priority=20)

# Mediator automatically saves events to outbox
mediator = Mediator(
    registry=handler_registry,
    uow_factory=uow_factory,
    middleware_registry=middleware_registry,
)

# Command handler returns events → middleware saves to outbox
response = await mediator.send(CreateOrderCommand(...))
```

#### Configuration Options

```python
outbox = BufferedOutbox(
    storage=storage,
    broker=broker,
    lock_strategy=lock_strategy,
    batch_size=100,          # Messages per batch
    max_retries=10,          # Max retry attempts
    poll_interval=5.0,       # Seconds between polls
    wait_delay=0.1,          # Initial wait delay
    max_delay=2.0,           # Max exponential backoff
)
```

### OutboxService

**Implementation:**

```python
from cqrs_ddd_core.cqrs.outbox.service import OutboxService

class OutboxService:
    """
    Processes pending outbox messages with lock-based claiming.

    Lifecycle:
    1. Fetch pending messages
    2. Claim via locks (prevents duplicates)
    3. Publish to broker
    4. Mark success/record failures

    Two-phase locking prevents race conditions.
    """
```

**Usage Example:**

```python
from cqrs_ddd_core.cqrs.outbox.service import OutboxService

# Create service
service = OutboxService(
    storage=outbox_storage,
    publisher=kafka_publisher,
    lock_strategy=redis_lock,
    max_retries=5,
)

# Process single batch
count = await service.process_batch(batch_size=50)
print(f"Published {count} messages")

# Or run continuously
while True:
    await service.process_batch()
    await asyncio.sleep(10)
```

---

## Publishers (`publishers/`)

### Overview

The publishers package provides **event publishing strategies** with routing and decorator support.

**Files:**
- `routing.py` - TopicRoutingPublisher for flexible routing
- `decorators.py` - `@route_to` decorator
- `handler.py` - PublishingEventHandler bridge

### TopicRoutingPublisher

**Implementation:**

```python
from cqrs_ddd_core.cqrs.publishers.routing import TopicRoutingPublisher

class TopicRoutingPublisher(IMessagePublisher):
    """
    Routes messages to different publishers based on metadata.

    Resolution order:
    1. Check __route_to__ attribute (via @route_to decorator)
    2. Check explicit routes dict
    3. Fall back to default publisher

    Features:
    - Flexible routing
    - Per-event publishers
    - Default fallback
    - Decorator-based routing
    """
```

**Usage Examples:**

#### Basic Routing

```python
from cqrs_ddd_core.cqrs.publishers.routing import TopicRoutingPublisher

# Create router
router = TopicRoutingPublisher(
    routes={
        "OrderCreated": outbox_publisher,
        "UserRegistered": email_publisher,
    },
    default=kafka_publisher,
)

# Publish to specific publisher
await router.publish("OrderCreated", event)  # → outbox_publisher
await router.publish("PaymentProcessed", event)  # → kafka_publisher (default)
```

#### Register Routes Dynamically

```python
router = TopicRoutingPublisher(default=outbox_publisher)

# Register routes
router.register_route("OrderCreated", outbox_publisher)
router.register_route("OrderConfirmed", kafka_publisher)

# Publish
await router.publish("OrderCreated", event)  # → outbox_publisher
```

#### Destinations + Decorators

```python
from cqrs_ddd_core.cqrs.publishers.routing import TopicRoutingPublisher
from cqrs_ddd_core.cqrs.publishers.decorators import route_to

# Define events with routing
@route_to("slow")
class HeavyProcessingEvent(DomainEvent):
    data: dict

@route_to("fast")
class NotificationEvent(DomainEvent):
    message: str

# Create router with destinations
router = TopicRoutingPublisher(
    destinations={
        "slow": background_jobs_publisher,
        "fast": realtime_publisher,
    },
    default=outbox_publisher,
)

# Auto-routes based on decorator
await router.publish("HeavyProcessingEvent", event)  # → background_jobs_publisher
await router.publish("NotificationEvent", event)  # → realtime_publisher
```

### `@route_to` Decorator

**Implementation:**

```python
from cqrs_ddd_core.cqrs.publishers.decorators import route_to

def route_to(destination_key: str) -> Any:
    """
    Decorator to mark event class for specific routing destination.

    Used by TopicRoutingPublisher to resolve publishers.
    """
```

**Usage Example:**

```python
from cqrs_ddd_core.cqrs.publishers.decorators import route_to
from cqrs_ddd_core.domain.events import DomainEvent

@route_to("notifications")
class UserCreated(DomainEvent):
    user_id: str
    email: str

@route_to("analytics")
class OrderPlaced(DomainEvent):
    order_id: str
    total: float

# TopicRoutingPublisher resolves automatically
router = TopicRoutingPublisher(
    destinations={
        "notifications": sns_publisher,
        "analytics": kinesis_publisher,
    }
)
```

### PublishingEventHandler

**Implementation:**

```python
from cqrs_ddd_core.cqrs.publishers.handler import PublishingEventHandler

class PublishingEventHandler(EventHandler[DomainEvent]):
    """
    Generic handler that publishes events to external broker.

    Bridge between domain event dispatcher and IMessagePublisher.
    """
```

**Usage Example:**

```python
from cqrs_ddd_core.cqrs.publishers.handler import PublishingEventHandler
from cqrs_ddd_core.cqrs.event_dispatcher import EventDispatcher

# Create handler
publisher_handler = PublishingEventHandler(publisher=outbox_publisher)

# Register with dispatcher
dispatcher = EventDispatcher()
dispatcher.register(OrderCreated, publisher_handler)
dispatcher.register(OrderConfirmed, publisher_handler)

# Events automatically published
event = OrderCreated(aggregate_id="order-123", ...)
await dispatcher.dispatch(event)  # → outbox_publisher
```

---

## Consumers (`consumers/`)

### Overview

The consumers package provides **event consumer implementations** for subscribing to message brokers.

**Files:**
- `base.py` - BaseEventConsumer with auto-wiring

### BaseEventConsumer

**Implementation:**

```python
from cqrs_ddd_core.cqrs.consumers.base import BaseEventConsumer

class BaseEventConsumer:
    """
    Base implementation of event consumer (message broker subscriber).

    Lifecycle:
    1. Subscribe to topics on message broker
    2. Extract event_type from payload
    3. Hydrate using EventTypeRegistry
    4. Dispatch using IEventDispatcher

    Features:
    - Automatic event hydration
    - Handler auto-wiring
    - Multi-topic subscription
    - Message acknowledgment
    """
```

**Usage Examples:**

#### Basic Consumer

```python
from cqrs_ddd_core.cqrs.consumers.base import BaseEventConsumer
from cqrs_ddd_core.domain.event_registry import EventTypeRegistry

# Register event types for hydration
registry = EventTypeRegistry()
registry.register("OrderCreated", OrderCreated)
registry.register("OrderConfirmed", OrderConfirmed)

# Create consumer
consumer = BaseEventConsumer(
    broker=kafka_consumer,
    topics=["order-events", "user-events"],
    dispatcher=event_dispatcher,
    registry=registry,
)

# Start consuming
await consumer.start()

# Messages automatically:
# 1. Deserialized from broker
# 2. Hydrated to domain events
# 3. Dispatched to handlers
```

#### Auto-Wire Handlers

```python
from cqrs_ddd_core.cqrs.consumers.base import BaseEventConsumer
from cqrs_ddd_core.cqrs.registry import HandlerRegistry

# Register handlers
handler_registry = HandlerRegistry()
handler_registry.register_event_handler(OrderCreated, SendEmailHandler())
handler_registry.register_event_handler(OrderCreated, UpdateProjectionHandler())

# Create consumer with auto-wiring
consumer = BaseEventConsumer(
    broker=rabbitmq_consumer,
    topics=["orders"],
    handler_registry=handler_registry,
    handler_factory=lambda cls: cls(email_service=email_service),
)

# Handlers auto-registered with dispatcher
await consumer.start()
```

#### Full Integration Example

```python
from cqrs_ddd_core.cqrs.consumers.base import BaseEventConsumer
from cqrs_ddd_core.cqrs.event_dispatcher import EventDispatcher
from cqrs_ddd_core.domain.event_registry import EventTypeRegistry

# Setup
registry = EventTypeRegistry()
registry.register("OrderCreated", OrderCreated)

dispatcher = EventDispatcher()
dispatcher.register(OrderCreated, SendEmailHandler())
dispatcher.register(OrderCreated, UpdateProjectionHandler())

# Create consumer
consumer = BaseEventConsumer(
    broker=kafka_consumer,
    topics=["order-events"],
    dispatcher=dispatcher,
    registry=registry,
    queue_name="order-service-queue",
    exchange_name="order-exchange",
)

# Start consuming (blocks)
await consumer.start()

# Or run in background
task = asyncio.create_task(consumer.start())

# Stop gracefully
await consumer.stop()
```

#### With RabbitMQ

```python
from cqrs_ddd_core.cqrs.consumers.base import BaseEventConsumer

consumer = BaseEventConsumer(
    broker=rabbitmq_consumer,
    topics=["orders.created", "orders.confirmed"],
    registry=event_registry,
    dispatcher=event_dispatcher,
    queue_name="order-service-orders",
    exchange_name="orders",
)

await consumer.start()
```

#### With Kafka

```python
consumer = BaseEventConsumer(
    broker=kafka_consumer,
    topics=["order-events", "payment-events"],
    registry=event_registry,
    handler_registry=handler_registry,
)

await consumer.start()
```

---

## Outbox Pattern Flow

### Complete Transaction Flow

```
1. Command arrives → Mediator
2. Handler executes → Creates aggregate
3. Aggregate emits events
4. Handler returns CommandResponse with events
5. OutboxMiddleware saves events to outbox
6. UoW commits (events persisted atomically)
7. Background worker processes outbox
8. Events published to message broker
9. Consumers receive and process events
```

### Example Implementation

```python
from cqrs_ddd_core.cqrs.mediator import Mediator
from cqrs_ddd_core.cqrs.outbox.buffered import BufferedOutbox
from cqrs_ddd_core.middleware.outbox import OutboxMiddleware

# Setup outbox
outbox = BufferedOutbox(
    storage=db_outbox,
    broker=kafka_publisher,
    lock_strategy=redis_lock,
)
await outbox.start()

# Setup mediator with outbox middleware
middleware = MiddlewareRegistry()
middleware.register(OutboxMiddleware(outbox), priority=20)

mediator = Mediator(
    registry=handlers,
    uow_factory=lambda: SqlAlchemyUnitOfWork(session_factory),
    middleware_registry=middleware,
)

# Send command
command = CreateOrderCommand(customer_id="cust-123", items=[...])
response = await mediator.send(command)

# Events automatically:
# 1. Saved to outbox (same transaction as order)
# 2. Published to Kafka by background worker
# 3. Consumed by other services
```

---

## Best Practices

### ✅ DO: Use Handlers for Business Logic

```python
class CreateOrderHandler(CommandHandler[str]):
    async def handle(self, command: CreateOrderCommand) -> CommandResponse[str]:
        uow = get_current_uow()
        order = Order.create(command.customer_id, command.items)
        await uow.orders.add(order)
        return CommandResponse(result=order.id, events=order.clear_events())
```

### ❌ DON'T: Put Business Logic in Commands

```python
# Commands are data structures - no logic!
class CreateOrderCommand(Command[str]):
    # BAD: Business logic in command
    def validate(self) -> bool:
        return len(self.items) > 0
```

### ✅ DO: Return DTOs from Queries

```python
class GetOrderHandler(QueryHandler[OrderDTO]):
    async def handle(self, query: GetOrderQuery) -> QueryResponse[OrderDTO]:
        order = await uow.orders.get(query.order_id)
        return QueryResponse(result=OrderDTO.from_aggregate(order))
```

### ❌ DON'T: Return Aggregates from Queries

```python
# Don't return domain objects from queries
class GetOrderHandler(QueryHandler[Order]):
    async def handle(self, query: GetOrderQuery) -> QueryResponse[Order]:
        order = await uow.orders.get(query.order_id)
        return QueryResponse(result=order)  # BAD: exposes domain model
```

---

## Summary

**Key Features:**
- Central mediator for dispatch
- UoW scope management
- Automatic correlation propagation
- Middleware pipeline
- Event-driven architecture

**Components:**
- `Mediator` - Central dispatch
- `Command[TResult]` - Write operations
- `Query[TResult]` - Read operations
- `Handler` - Business logic
- `Response` - Result wrapper
- `EventDispatcher` - Event distribution

---

**Last Updated:** February 22, 2026
**Package:** `cqrs_ddd_core.cqrs`
