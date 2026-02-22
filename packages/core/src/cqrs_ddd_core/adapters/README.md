# Adapters Layer - In-Memory Implementations

**Package:** `cqrs_ddd_core.adapters`  
**Purpose:** In-memory implementations for testing

---

## Overview

The adapters layer provides **in-memory implementations** of all ports for fast unit testing without infrastructure dependencies.

### Design Philosophy

- **Test-First** - No database required for 90% of tests
- **Fast** - In-memory operations
- **Complete** - Implements all port methods
- **Production-like** - Same behavior as real adapters

### Components

| Adapter | Purpose | Location |
|---------|---------|----------|
| **InMemoryRepository** | Repository implementation | `memory/repository.py` |
| **InMemoryUnitOfWork** | UoW implementation | `memory/unit_of_work.py` |
| **InMemoryEventStore** | Event store implementation | `memory/event_store.py` |
| **InMemoryOutboxStorage** | Outbox implementation | `memory/outbox.py` |
| **InMemoryLockStrategy** | Lock implementation | `memory/locking.py` |
| **CachingRepository** | Caching decorator | `decorators/caching_repository.py` |

---

## InMemoryRepository

### Implementation

```python
from cqrs_ddd_core.adapters.memory.repository import InMemoryRepository

class InMemoryRepository(Generic[T, ID]):
    """
    In-memory repository for testing.
    
    Features:
    - Thread-safe storage
    - Optimistic concurrency support
    - Specification-based search
    """
    
    def __init__(self, model_cls: type[T] | None = None):
        self._storage: dict[ID, T] = {}
        self._model_cls = model_cls
```

### Usage Example

```python
from cqrs_ddd_core.adapters.memory.repository import InMemoryRepository

# Create repository
repo = InMemoryRepository[Order, str](model_cls=Order)

# Add aggregate
order = Order(id="order-123", customer_id="cust-456")
await repo.add(order)

# Get aggregate
saved = await repo.get("order-123")
assert saved == order

# Search with specification
spec = OrderStatusSpecification("pending")
result = await repo.search(spec)
items = await result

# Delete aggregate
await repo.delete("order-123")
```

---

## InMemoryUnitOfWork

### Implementation

```python
from cqrs_ddd_core.adapters.memory.unit_of_work import InMemoryUnitOfWork

class InMemoryUnitOfWork(UnitOfWork):
    """
    In-memory UoW for testing.
    
    Features:
    - Transaction simulation
    - Commit hooks
    - Context manager support
    """
```

### Usage Example

```python
from cqrs_ddd_core.adapters.memory.unit_of_work import InMemoryUnitOfWork

# Setup
uow = InMemoryUnitOfWork()
uow.orders = InMemoryRepository[Order, str]()

# Use with context manager
async with uow:
    order = Order.create(...)
    await uow.orders.add(order)
    
    # Register commit hook
    uow.on_commit(lambda: print("Order created!"))
    
    await uow.commit()  # Hooks trigger after commit

# Verify
saved = await uow.orders.get(order.id)
assert saved == order
```

---

## InMemoryEventStore

### Implementation

```python
from cqrs_ddd_core.adapters.memory.event_store import InMemoryEventStore

class InMemoryEventStore(IEventStore):
    """
    In-memory event store for testing.
    
    Features:
    - Event persistence
    - Version-based retrieval
    - Position tracking
    """
```

### Usage Example

```python
from cqrs_ddd_core.adapters.memory.event_store import InMemoryEventStore

# Create event store
event_store = InMemoryEventStore()

# Append event
event = StoredEvent(
    event_id="evt-123",
    event_type="OrderCreated",
    aggregate_id="order-456",
    version=1,
    payload={"customer_id": "cust-789"},
)
await event_store.append(event)

# Get events
events = await event_store.get_events("order-456")
print(len(events))  # 1

# Stream events
async for event in event_store.stream_all():
    process(event)
```

---

## InMemoryOutboxStorage

### Implementation

```python
from cqrs_ddd_core.adapters.memory.outbox import InMemoryOutboxStorage

class InMemoryOutboxStorage(IOutboxStorage):
    """
    In-memory outbox for testing.
    
    Features:
    - Message persistence
    - Pending retrieval
    - Status tracking
    """
```

### Usage Example

```python
from cqrs_ddd_core.adapters.memory.outbox import InMemoryOutboxStorage

# Create outbox
outbox = InMemoryOutboxStorage()

# Save message
message = OutboxMessage(
    message_id="msg-123",
    event_type="OrderCreated",
    payload={"order_id": "order-456"},
)
await outbox.save_messages([message])

# Get pending
pending = await outbox.get_pending()
print(len(pending))  # 1

# Mark as published
await outbox.mark_published(["msg-123"])
```

---

## InMemoryLockStrategy

### Implementation

```python
from cqrs_ddd_core.adapters.memory.locking import InMemoryLockStrategy

class InMemoryLockStrategy(ILockStrategy):
    """
    In-memory lock for testing.
    
    Features:
    - Lock acquisition
    - Lock release
    - TTL support
    """
```

### Usage Example

```python
from cqrs_ddd_core.adapters.memory.locking import InMemoryLockStrategy

# Create lock
lock = InMemoryLockStrategy()

# Acquire lock
acquired = await lock.acquire("resource-123", timeout=10.0, ttl=30.0)
print(acquired)  # True

# Try to acquire again (should fail)
acquired2 = await lock.acquire("resource-123", timeout=1.0)
print(acquired2)  # False

# Release lock
await lock.release("resource-123")

# Now can acquire again
acquired3 = await lock.acquire("resource-123")
print(acquired3)  # True
```

---

## CachingRepository Decorator

### Implementation

```python
from cqrs_ddd_core.adapters.decorators.caching_repository import CachingRepository

class CachingRepository(Generic[T, ID]):
    """
    Repository decorator that adds caching.
    
    Features:
    - Transparent caching
    - TTL support
    - Cache invalidation
    """
    
    def __init__(
        self,
        inner: IRepository[T, ID],
        cache: ICacheService,
        ttl_seconds: float | None = None,
    ):
        self._inner = inner
        self._cache = cache
        self._ttl = ttl_seconds
```

### Usage Example

```python
from cqrs_ddd_core.adapters.decorators.caching_repository import CachingRepository
from cqrs_ddd_core.adapters.memory.repository import InMemoryRepository

# Create base repository
base_repo = InMemoryRepository[Order, str]()

# Add caching
cached_repo = CachingRepository(
    inner=base_repo,
    cache=InMemoryCache(),
    ttl_seconds=300,
)

# First call hits database
order1 = await cached_repo.get("order-123")

# Second call hits cache
order2 = await cached_repo.get("order-123")  # Faster!

# Cache is transparent
assert order1 == order2
```

---

## Best Practices

### ✅ DO: Use In-Memory Adapters in Tests

```python
async def test_create_order():
    # Use in-memory adapters - fast!
    uow = InMemoryUnitOfWork()
    uow.orders = InMemoryRepository[Order, str]()
    
    handler = CreateOrderHandler()
    command = CreateOrderCommand(customer_id="cust-123")
    
    response = await handler.handle(command)
    
    assert response.success
    # No database needed!
```

### ❌ DON'T: Use Real Databases in Unit Tests

```python
async def test_create_order():
    # BAD: Slow, requires setup
    db = await create_postgres_connection()
    repo = SQLAlchemyOrderRepository(db)
    
    handler = CreateOrderHandler(repo)
    # ... test code ...
    
    # Slow, hard to maintain
```

### ✅ DO: Test with Multiple Adapters

```python
# Test with in-memory
uow = InMemoryUnitOfWork()
await test_order_creation(uow)

# Test with real database (integration test)
uow = SQLAlchemyUnitOfWork(session)
await test_order_creation(uow)

# Same test logic, different adapters
```

---

## Summary

**Key Features:**
- Fast in-memory operations
- No infrastructure required
- Complete implementation
- Production-like behavior

**Components:**
- `InMemoryRepository[T, ID]` - Repository
- `InMemoryUnitOfWork` - UoW
- `InMemoryEventStore` - Event store
- `InMemoryOutboxStorage` - Outbox
- `InMemoryLockStrategy` - Locking
- `CachingRepository` - Caching decorator

---

**Last Updated:** February 22, 2026  
**Package:** `cqrs_ddd_core.adapters`
