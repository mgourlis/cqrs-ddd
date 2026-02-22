# Primitives Layer - Core Utilities

**Package:** `cqrs_ddd_core.primitives`  
**Purpose:** Core utility classes and exception hierarchy

---

## Overview

The primitives layer provides **fundamental building blocks** used throughout the framework.

### Components

| Component | Purpose | File |
|-----------|---------|------|
| **Exception Hierarchy** | Structured error handling | `exceptions.py` |
| **IIDGenerator** | ID generation protocol | `id_generator.py` |
| **ResourceIdentifier** | Lock resource specification | `locking.py` |

---

## Exception Hierarchy

### Implementation

```python
from cqrs_ddd_core.primitives.exceptions import (
    # Root
    CQRSDDDError,
    
    # Domain errors
    DomainError,
    NotFoundError,
    EntityNotFoundError,
    InvariantViolationError,
    
    # Concurrency errors
    ConcurrencyError,
    OptimisticConcurrencyError,
    DomainConcurrencyError,
    OptimisticLockingError,
    LockAcquisitionError,
    LockRollbackError,
    
    # Validation errors
    ValidationError,
    
    # Infrastructure errors
    InfrastructureError,
    PersistenceError,
    EventStoreError,
    OutboxError,
    
    # Handler errors
    HandlerError,
    HandlerRegistrationError,
    PublisherNotFoundError,
)

# Root exception
class CQRSDDDError(Exception):
    """Root exception for the entire cqrs-ddd toolkit."""

# Domain errors
class DomainError(CQRSDDDError):
    """Base class for all domain-related errors."""

class NotFoundError(DomainError):
    """Raised when an aggregate or resource is not found."""

class EntityNotFoundError(NotFoundError):
    """Raised when a specific entity cannot be found by ID."""
    
    def __init__(self, entity_type: str, entity_id: object) -> None:
        self.entity_type = entity_type
        self.entity_id = entity_id
        super().__init__(f"{entity_type} with id={entity_id!r} not found")

class InvariantViolationError(DomainError):
    """Raised when a domain invariant is violated."""

# Concurrency errors
class ConcurrencyError(CQRSDDDError):
    """Base class for all concurrency-related conflicts (both semantic and technical)."""

class OptimisticConcurrencyError(ConcurrencyError):
    """Raised when concurrent modification is detected via version mismatch.
    
    This is a technical concurrency error (version mismatch in database).
    Both SQLAlchemy and MongoDB implementations raise this exception.
    """

class DomainConcurrencyError(ConcurrencyError, DomainError):
    """Raised when domain logic detects a semantic conflict.
    
    Use in Aggregate Roots or Domain Services when business rules
    indicate that the user's intent is based on stale data.
    """

class OptimisticLockingError(ConcurrencyError, PersistenceError):
    """Raised when persistence layer detects technical version mismatch."""

class LockAcquisitionError(ConcurrencyError):
    """Failed to acquire lock with detailed context.
    
    Provides diagnostic information about which resource failed
    and under what conditions.
    """
    
    def __init__(
        self,
        resource: ResourceIdentifier,
        timeout: float,
        reason: str | None = None,
    ) -> None:
        self.resource = resource
        self.timeout = timeout
        self.reason = reason
        ...

class LockRollbackError(ConcurrencyError):
    """Failed to rollback locks after partial acquisition failure.
    
    Contains information about how many locks were successfully
    released and which ones failed.
    """

# Validation errors
class ValidationError(CQRSDDDError):
    """Raised when command validation fails.
    
    Carries structured errors: ``{field: [messages]}``.
    """
    
    def __init__(self, errors: dict[str, list[str]] | str | None = None) -> None:
        if isinstance(errors, str):
            self.errors: dict[str, list[str]] = {"__root__": [errors]}
        elif errors is None:
            self.errors = {}
        else:
            self.errors = errors
        super().__init__(str(self.errors))

# Infrastructure errors
class InfrastructureError(CQRSDDDError):
    """Base class for all infrastructure-related errors."""

class PersistenceError(InfrastructureError):
    """Base class for all persistence-related errors."""

class EventStoreError(CQRSDDDError):
    """Raised when event-store operations fail."""

class OutboxError(CQRSDDDError):
    """Raised when outbox operations fail."""

# Handler errors
class HandlerError(CQRSDDDError):
    """Base class for all handler related errors (registration, lookup, execution)."""

class HandlerRegistrationError(HandlerError):
    """Raised when a handler registration conflict is detected.
    
    HandlerRegistry raises this when trying to register multiple
    handlers for a command or query type.
    """

class PublisherNotFoundError(HandlerError):
    """Raised when a publisher cannot be resolved for a specific topic/event.
    
    TopicRoutingPublisher raises this when no specific route
    exists and no default publisher is configured.
    """
```

### Usage Examples

#### Domain Errors

```python
from cqrs_ddd_core.primitives.exceptions import (
    DomainError,
    InvariantViolationError,
)

class OrderNotFoundError(DomainError):
    """Order not found in repository."""

class InvalidOrderStateError(DomainError):
    """Order in invalid state for operation."""

# Usage in aggregate
class Order(AggregateRoot[UUID]):
    def confirm(self) -> None:
        if self.status != "pending":
            raise InvalidOrderStateError("Can only confirm pending orders")
        
        object.__setattr__(self, "status", "confirmed")

# Usage in repository
async def get_order(order_id: str) -> Order:
    order = await repo.get(order_id)
    if not order:
        raise OrderNotFoundError(f"Order {order_id} not found")
    return order
```

#### Optimistic Concurrency

```python
from cqrs_ddd_core.primitives.exceptions import OptimisticConcurrencyError

# Repository raises on version conflict
try:
    await repo.add(order)  # Version check
except OptimisticConcurrencyError as e:
    # Handle conflict
    logger.warning(f"Concurrent modification: {e}")
    # Retry or fail
```

#### Validation Errors

```python
from cqrs_ddd_core.primitives.exceptions import ValidationError

class CreateOrderCommand(Command[str]):
    customer_id: str
    items: list[OrderItem]
    
    @field_validator("items")
    @classmethod
    def validate_items(cls, v: list[OrderItem]) -> list[OrderItem]:
        if not v:
            raise ValidationError("Order must have at least one item")
        return v
```

---

## ID Generation

### Protocol Definition

```python
from cqrs_ddd_core.primitives.id_generator import IIDGenerator

@runtime_checkable
class IIDGenerator(Protocol):
    """Protocol for ID generation strategies."""
    
    def next_id(self) -> str:
        """Generate next ID."""
        ...
```

### Implementations

#### UUID4Generator

```python
from cqrs_ddd_core.primitives.id_generator import UUID4Generator

generator = UUID4Generator()

# Generate IDs
id1 = generator.next_id()  # "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
id2 = generator.next_id()  # "f0e1d2c3-b4a5-6789-0abc-def123456789"
```

#### Custom Generator

```python
from cqrs_ddd_core.primitives.id_generator import IIDGenerator

class SnowflakeGenerator(IIDGenerator):
    """Snowflake ID generator for distributed systems."""
    
    def __init__(self, worker_id: int, datacenter_id: int):
        self.worker_id = worker_id
        self.datacenter_id = datacenter_id
        self.sequence = 0
        self.last_timestamp = 0
    
    def next_id(self) -> str:
        """Generate next snowflake ID."""
        # Snowflake algorithm implementation
        timestamp = int(time.time() * 1000)
        
        if timestamp == self.last_timestamp:
            self.sequence += 1
        else:
            self.sequence = 0
            self.last_timestamp = timestamp
        
        snowflake_id = (
            ((timestamp - CUSTOM_EPOCH) << 22) |
            (self.datacenter_id << 17) |
            (self.worker_id << 12) |
            self.sequence
        )
        
        return str(snowflake_id)

# Usage
generator = SnowflakeGenerator(worker_id=1, datacenter_id=1)
order_id = generator.next_id()
```

#### UUIDv7 Generator (Time-sorted)

```python
from cqrs_ddd_core.primitives.id_generator import IIDGenerator
import uuid
import time

class UUID7Generator(IIDGenerator):
    """UUIDv7 generator for time-sorted IDs."""
    
    def next_id(self) -> str:
        """Generate UUIDv7 (time-sorted)."""
        # Unix timestamp in milliseconds
        timestamp = int(time.time() * 1000)
        
        # Create UUIDv7 structure
        uuid_bytes = uuid.uuid4().bytes
        
        # Replace first 6 bytes with timestamp
        uuid_bytes = (
            timestamp.to_bytes(6, 'big') +
            uuid_bytes[6:]
        )
        
        # Set version (7) and variant
        uuid_bytes = bytearray(uuid_bytes)
        uuid_bytes[6] = (uuid_bytes[6] & 0x0F) | 0x70
        uuid_bytes[8] = (uuid_bytes[8] & 0x3F) | 0x80
        
        return str(uuid.UUID(bytes=bytes(uuid_bytes)))
```

### Usage with Aggregates

```python
from cqrs_ddd_core.primitives.id_generator import UUID4Generator, IIDGenerator

class Order(AggregateRoot[str]):
    customer_id: str
    
    @classmethod
    def create(cls, customer_id: str, id_generator: IIDGenerator) -> "Order":
        return cls(
            id=id_generator.next_id(),
            customer_id=customer_id,
        )

# Usage in production
generator = UUID4Generator()
order = Order.create(customer_id="cust-123", id_generator=generator)
print(order.id)  # Auto-generated UUID

# Usage in tests with fixed IDs
class FixedIDGenerator(IIDGenerator):
    def __init__(self, fixed_id: str):
        self.fixed_id = fixed_id
    
    def next_id(self) -> str:
        return self.fixed_id

order = Order.create(
    customer_id="cust-123",
    id_generator=FixedIDGenerator("test-order-id")
)
assert order.id == "test-order-id"
```

---

## Resource Locking

### ResourceIdentifier

```python
from cqrs_ddd_core.primitives.locking import ResourceIdentifier

@dataclass(frozen=True)
class ResourceIdentifier:
    """
    Identifies a resource for pessimistic locking.
    
    Attributes:
        resource_type: Type of resource (e.g., "Account", "Order")
        resource_id: Unique identifier of resource
        lock_mode: Lock mode ("read" or "write", default: "write")
    """
    
    resource_type: str
    resource_id: str
    lock_mode: str = "write"
    
    def __str__(self) -> str:
        return f"{self.resource_type}:{self.resource_id}:{self.lock_mode}"
```

### Usage Examples

#### Write Locks

```python
from cqrs_ddd_core.primitives.locking import ResourceIdentifier

class TransferFundsCommand(Command[None]):
    from_account: str
    to_account: str
    amount: float
    
    def get_critical_resources(self) -> list[ResourceIdentifier]:
        """Lock both accounts with write locks."""
        return [
            ResourceIdentifier("Account", self.from_account),
            ResourceIdentifier("Account", self.to_account),
        ]

# Middleware locks both accounts (sorted to prevent deadlocks)
# No concurrent transfers on same accounts
```

#### Mixed Read/Write Locks

```python
class UpdateUserSettingsCommand(Command[None]):
    user_id: str
    org_id: str
    settings: dict
    
    def get_critical_resources(self) -> list[ResourceIdentifier]:
        """Write lock user, read lock organization."""
        return [
            ResourceIdentifier("User", self.user_id, lock_mode="write"),
            ResourceIdentifier("Organization", self.org_id, lock_mode="read"),
        ]

# User can be modified
# Organization cannot be modified concurrently
# Other operations can read organization
```

---

## Best Practices

### ✅ DO: Use Package Exceptions

```python
from cqrs_ddd_core.primitives.exceptions import DomainError

class OrderNotFoundError(DomainError):
    """Order not found."""

# Use instead of bare ValueError/ RuntimeError
```

### ❌ DON'T: Use Generic Exceptions

```python
# BAD: Generic exception
if not order:
    raise ValueError("Order not found")  # Too generic

# GOOD: Specific exception
if not order:
    raise OrderNotFoundError("Order not found")
```

### ✅ DO: Create Specific Exception Types

```python
# Specific exceptions for different scenarios
class OrderNotFoundError(DomainError):
    """Order not found."""

class InvalidOrderStateError(DomainError):
    """Order in invalid state."""

class InsufficientFundsError(DomainError):
    """Insufficient account balance."""
```

### ❌ DON'T: Overly Generic Exceptions

```python
# BAD: Too generic
class OrderError(DomainError):
    """Any order-related error."""

# Loses information about what went wrong
```

### ✅ DO: Use Pluggable ID Generators

```python
# Inject generator for testability
class Order(AggregateRoot[str]):
    @classmethod
    def create(cls, customer_id: str, id_generator: IIDGenerator) -> "Order":
        return cls(id=id_generator.next_id(), customer_id=customer_id)

# Production: UUID generator
order = Order.create(customer_id="cust-123", id_generator=UUIDGenerator())

# Testing: Fixed ID generator
class FixedIDGenerator(IIDGenerator):
    def __init__(self, fixed_id: str):
        self.fixed_id = fixed_id
    
    def next_id(self) -> str:
        return self.fixed_id

order = Order.create(customer_id="cust-123", id_generator=FixedIDGenerator("test-id"))
```

---

## Summary

**Key Features:**
- Structured exception hierarchy
- Protocol-based ID generation
- Resource locking primitives

**Components:**
- `CQRSDDDError` - Base exception
- `DomainError` - Domain errors
- `HandlerError` - Handler errors
- `ValidationError` - Validation errors
- `PersistenceError` - Persistence errors
- `OptimisticConcurrencyError` - Version conflicts
- `IIDGenerator` - ID generation protocol
- `ResourceIdentifier` - Lock resource spec

---

**Last Updated:** February 22, 2026  
**Package:** `cqrs_ddd_core.primitives`
