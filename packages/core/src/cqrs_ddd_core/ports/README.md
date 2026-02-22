# Ports Layer - Protocol Definitions

**Package:** `cqrs_ddd_core.ports`  
**Purpose:** Infrastructure contracts using Protocol pattern

---

## Overview

The ports layer defines **infrastructure contracts** using `typing.Protocol`. These are interfaces that infrastructure adapters must implement.

### Design Philosophy

- **Protocol-based** - Structural typing, no inheritance required
- **Infrastructure-agnostic** - No implementation details
- **Type-safe** - Full generic type support
- **Runtime checkable** - `@runtime_checkable` decorator

### Components

| Protocol | Purpose | File |
|----------|---------|------|
| **IRepository** | Aggregate persistence | `repository.py` |
| **UnitOfWork** | Transaction management | `unit_of_work.py` |
| **IEventStore** | Event persistence | `event_store.py` |
| **IOutboxStorage** | Transactional outbox | `outbox.py` |
| **ICommandBus** | Command dispatch | `bus.py` |
| **IQueryBus** | Query dispatch | `bus.py` |
| **ILockStrategy** | Distributed locking | `locking.py` |
| **ICacheService** | Caching | `cache.py` |
| **IValidator** | Validation | `validation.py` |
| **IBackgroundWorker** | Background jobs | `background_worker.py` |
| **IMessagePublisher** | Message publishing | `messaging.py` |
| **IMessageConsumer** | Message subscription | `messaging.py` |
| **IEventDispatcher** | Event dispatching | `event_dispatcher.py` |

---

## IRepository

### Protocol Definition

```python
from cqrs_ddd_core.ports.repository import IRepository

@runtime_checkable
class IRepository(Protocol[T, ID]):
    """
    Generic Repository interface for managing aggregates.
    
    T: Aggregate type (must extend AggregateRoot)
    ID: Primary key type (str, int, UUID)
    """
    
    async def add(self, entity: T, uow: UnitOfWork | None = None) -> ID:
        """Add aggregate to repository."""
        ...
    
    async def get(self, entity_id: ID, uow: UnitOfWork | None = None) -> T | None:
        """Get aggregate by ID."""
        ...
    
    async def delete(self, entity_id: ID, uow: UnitOfWork | None = None) -> ID:
        """Delete aggregate."""
        ...
    
    async def list_all(
        self,
        entity_ids: list[ID] | None = None,
        uow: UnitOfWork | None = None,
    ) -> list[T]:
        """List all aggregates."""
        ...
    
    async def search(
        self,
        criteria: ISpecification[T] | Any,
        uow: UnitOfWork | None = None,
    ) -> SearchResult[T]:
        """Search aggregates using specification."""
        ...
```

### Usage Example

```python
from cqrs_ddd_core.ports.repository import IRepository

class IOrderRepository(IRepository[Order, str]):
    """Order repository contract."""
    pass

# Implementation in infrastructure
class SQLAlchemyOrderRepository(IOrderRepository):
    async def add(self, entity: Order, uow: UnitOfWork | None = None) -> str:
        # SQL implementation
        ...

# Usage in application
async def create_order(command: CreateOrderCommand, repo: IOrderRepository) -> str:
    order = Order.create(command.customer_id)
    return await repo.add(order)
```

---

## UnitOfWork

### Base Class Definition

```python
from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

class UnitOfWork(ABC):
    """
    Abstract base class for Unit of Work.
    
    Features:
    - Transaction management
    - Commit hooks (run after successful commit)
    - Automatic hook triggering
    """
    
    def __init__(self) -> None:
        self._on_commit_hooks: deque[Callable[[], Awaitable[Any]]] = deque()
    
    def on_commit(self, callback: Callable[[], Awaitable[Any]]) -> None:
        """Register async callback to run after commit."""
        self._on_commit_hooks.append(callback)
    
    async def trigger_commit_hooks(self) -> None:
        """Execute all registered hooks."""
        while self._on_commit_hooks:
            callback = self._on_commit_hooks.popleft()
            try:
                await callback()
            except Exception as exc:
                logger.error("Error in on_commit hook: %s", exc)
    
    @abstractmethod
    async def commit(self) -> None:
        """Commit transaction."""
        ...
    
    @abstractmethod
    async def rollback(self) -> None:
        """Rollback transaction."""
        ...
```

### Usage Example

```python
from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

class IOrderUoW(UnitOfWork):
    """Order Unit of Work contract."""
    
    orders: IOrderRepository
    
    async def commit(self) -> None:
        """Commit transaction."""
        ...
    
    async def rollback(self) -> None:
        """Rollback transaction."""
        ...

# Usage with commit hooks
async with uow:
    order = Order.create(...)
    await uow.orders.add(order)
    
    # Register hook to run AFTER commit
    uow.on_commit(lambda: send_email(order.id))
    
    await uow.commit()  # Hooks trigger after successful commit
```

---

## IEventStore

### Protocol Definition

```python
from cqrs_ddd_core.ports.event_store import IEventStore, StoredEvent

@dataclass(frozen=True)
class StoredEvent:
    """Persistent representation of a domain event."""
    
    event_id: str
    event_type: str
    aggregate_id: str
    aggregate_type: str
    version: int  # Aggregate sequence number
    schema_version: int  # Event schema version
    payload: dict[str, object]
    metadata: dict[str, object]
    occurred_at: datetime
    correlation_id: str | None = None
    causation_id: str | None = None
    position: int | None = None  # Cursor position

@runtime_checkable
class IEventStore(Protocol):
    """Protocol for persisting domain events."""
    
    async def append(self, stored_event: StoredEvent) -> None:
        """Append single event."""
        ...
    
    async def append_batch(self, events: list[StoredEvent]) -> None:
        """Append multiple events atomically."""
        ...
    
    async def get_events(
        self,
        aggregate_id: str,
        *,
        after_version: int = 0,
    ) -> list[StoredEvent]:
        """Get events for aggregate."""
        ...
    
    async def get_events_after(
        self,
        position: int,
        limit: int = 1000,
    ) -> list[StoredEvent]:
        """Get events after position (cursor-based)."""
        ...
```

### Usage Example

```python
from cqrs_ddd_core.ports.event_store import IEventStore, StoredEvent

# Append event
event = StoredEvent(
    event_id="evt-123",
    event_type="OrderCreated",
    aggregate_id="order-456",
    aggregate_type="Order",
    version=1,
    payload={"customer_id": "cust-789"},
)
await event_store.append(event)

# Replay events
events = await event_store.get_events("order-456", after_version=0)
for event in events:
    # Rebuild aggregate state
    order.apply_event(event)
```

---

## IOutboxStorage

### Protocol Definition

```python
from cqrs_ddd_core.ports.outbox import IOutboxStorage, OutboxMessage

@dataclass
class OutboxMessage:
    """Message waiting in outbox."""
    
    message_id: str
    event_type: str
    payload: dict[str, object]
    metadata: dict[str, object]
    created_at: datetime
    published_at: datetime | None = None
    error: str | None = None
    retry_count: int = 0
    correlation_id: str = ""
    causation_id: str | None = None

@runtime_checkable
class IOutboxStorage(Protocol):
    """Protocol for transactional outbox."""
    
    async def save_messages(
        self,
        messages: list[OutboxMessage],
        uow: UnitOfWork | None = None,
    ) -> None:
        """Save messages in same transaction as aggregate."""
        ...
    
    async def get_pending(
        self,
        limit: int = 100,
        uow: UnitOfWork | None = None,
    ) -> list[OutboxMessage]:
        """Get unpublished messages."""
        ...
    
    async def mark_published(
        self,
        message_ids: list[str],
        uow: UnitOfWork | None = None,
    ) -> None:
        """Mark messages as published."""
        ...
    
    async def mark_failed(
        self,
        message_id: str,
        error: str,
        uow: UnitOfWork | None = None,
    ) -> None:
        """Mark message as failed."""
        ...
```

### Usage Example

```python
from cqrs_ddd_core.ports.outbox import IOutboxStorage, OutboxMessage

# Save to outbox (same transaction)
message = OutboxMessage(
    message_id="msg-123",
    event_type="OrderCreated",
    payload={"order_id": "order-456"},
    correlation_id="req-abc",
)

await outbox.save_messages([message], uow=uow)
await uow.commit()  # Committed together with aggregate

# Background service publishes messages
pending = await outbox.get_pending(limit=100)
for msg in pending:
    await publisher.publish(msg)
    await outbox.mark_published([msg.message_id])
```

---

## ILockStrategy

### Protocol Definition

```python
from cqrs_ddd_core.ports.locking import ILockStrategy

@runtime_checkable
class ILockStrategy(Protocol):
    """Protocol for distributed locking."""
    
    async def acquire(
        self,
        resource: str,
        *,
        timeout: float = 10.0,
        ttl: float = 30.0,
    ) -> bool:
        """Acquire lock on resource."""
        ...
    
    async def release(self, resource: str) -> None:
        """Release lock."""
        ...
    
    async def extend(self, resource: str, ttl: float) -> bool:
        """Extend lock TTL."""
        ...
```

### Usage Example

```python
from cqrs_ddd_core.ports.locking import ILockStrategy

async def transfer_funds(
    from_account: str,
    to_account: str,
    lock: ILockStrategy,
):
    # Acquire locks in sorted order (prevent deadlocks)
    resources = sorted([from_account, to_account])
    
    for resource in resources:
        acquired = await lock.acquire(resource, timeout=10.0)
        if not acquired:
            raise LockAcquisitionError(f"Failed to lock {resource}")
    
    try:
        # Perform transfer
        ...
    finally:
        # Release all locks
        for resource in resources:
            await lock.release(resource)
```

---

## ICacheStrategy

### Protocol Definition

```python
from cqrs_ddd_core.ports.cache import ICacheStrategy

@runtime_checkable
class ICacheStrategy(Protocol):
    """Protocol for caching."""
    
    async def get(self, key: str) -> Any | None:
        """Get cached value."""
        ...
    
    async def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        """Set cached value."""
        ...
    
    async def delete(self, key: str) -> None:
        """Delete cached value."""
        ...
    
    async def clear(self) -> None:
        """Clear all cached values."""
        ...
```

---

## IValidator

### Protocol Definition

```python
from cqrs_ddd_core.ports.validation import IValidator

@runtime_checkable
class IValidator(Protocol):
    """Protocol for validation."""
    
    async def validate(self, obj: Any) -> ValidationResult:
        """Validate object."""
        ...
```

---

## IBackgroundWorker

### Protocol Definition

```python
from cqrs_ddd_core.ports.background_worker import IBackgroundWorker

@runtime_checkable
class IBackgroundWorker(Protocol):
    """Protocol for background job processing."""
    
    async def start(self) -> None:
        """Start worker."""
        ...
    
    async def stop(self) -> None:
        """Stop worker."""
        ...
    
    async def enqueue(self, job: Any) -> str:
        """Enqueue job."""
        ...
```

---

## SearchResult

### Implementation

```python
from cqrs_ddd_core.ports.search_result import SearchResult

class SearchResult(Generic[T]):
    """
    Result from repository search.
    
    Features:
    - Await for list
    - Stream for async iteration
    """
    
    async def __await__(self) -> list[T]:
        """Get all results as list."""
        ...
    
    async def stream(self, batch_size: int = 100) -> AsyncIterator[T]:
        """Stream results."""
        ...
```

### Usage Example

```python
# Get as list
result = await repo.search(spec)
items = await result  # List[T]

# Stream results
result = await repo.search(spec)
async for item in result.stream(batch_size=100):
    process(item)
```

---

## Best Practices

### ✅ DO: Depend on Protocols

```python
class CreateOrderHandler(CommandHandler[str]):
    def __init__(self, repo: IOrderRepository):
        self.repo = repo  # Depend on protocol
```

### ❌ DON'T: Depend on Implementations

```python
class CreateOrderHandler(CommandHandler[str]):
    def __init__(self, repo: SQLAlchemyOrderRepository):
        self.repo = repo  # BAD: Tight coupling to implementation
```

### ✅ DO: Implement All Protocol Methods

```python
class InMemoryOrderRepository(IOrderRepository):
    async def add(self, entity: Order, uow: UnitOfWork | None = None) -> str:
        ...
    
    async def get(self, entity_id: str, uow: UnitOfWork | None = None) -> Order | None:
        ...
    
    # Implement all methods
```

### ❌ DON'T: Partially Implement Protocols

```python
class IncompleteRepository(IOrderRepository):
    async def add(self, entity: Order, uow: UnitOfWork | None = None) -> str:
        ...
    
    # Missing get(), delete(), search() - BAD!
```

---

## Summary

**Key Features:**
- Protocol-based contracts
- Infrastructure-agnostic
- Type-safe with generics
- Runtime checkable

**Components:**
- `IRepository[T, ID]` - Aggregate persistence
- `UnitOfWork` - Transaction management
- `IEventStore` - Event persistence
- `IOutboxStorage` - Transactional outbox
- `ILockStrategy` - Distributed locking
- `ICacheService` - Caching
- `IValidator` - Validation

---

**Last Updated:** February 22, 2026  
**Package:** `cqrs_ddd_core.ports`
