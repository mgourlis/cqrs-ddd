# Domain Layer - Implementation Details & Usage

**Package:** `cqrs_ddd_core.domain`
**Purpose:** Domain modeling primitives for DDD (Domain-Driven Design)

---

## Overview

The domain layer provides foundational building blocks for implementing Domain-Driven Design patterns. All components are **infrastructure-agnostic** and depend only on Pydantic.

### Components

| Component | Purpose | File |
|-----------|---------|------|
| **AggregateRoot** | Consistency boundary with event collection | `aggregate.py` |
| **DomainEvent** | Immutable fact about domain state change | `events.py` |
| **ValueObject** | Identity-less immutable value | `value_object.py` |
| **Mixins** | Reusable cross-cutting behaviors | `mixins.py` |
| **Specification** | Encapsulated business rules | `specification.py` |
| **EventRegistry** | Event type name mapping | `event_registry.py` |

---

## AggregateRoot

### Implementation

```python
from uuid import UUID
from cqrs_ddd_core.domain.aggregate import AggregateRoot

class AggregateRoot(AggregateRootMixin, BaseModel, Generic[ID]):
    """
    Base class for all aggregate roots.

    Features:
    - Generic ID type (str, int, UUID)
    - Event collection (_domain_events)
    - Version tracking (_version)
    - ID auto-generation support
    - Event sourcing reconstitution
    """

    id: ID
    _id_generator: IIDGenerator | None = PrivateAttr(default=None)
    _domain_events: list[DomainEvent] = PrivateAttr(default_factory=list)
    _version: int = PrivateAttr(default=0)
```

### Usage Examples

#### Basic Aggregate

```python
from uuid import UUID
from cqrs_ddd_core.domain.aggregate import AggregateRoot

class Order(AggregateRoot[UUID]):
    customer_id: str
    status: str = "pending"
    total: float = 0.0

    def confirm(self) -> None:
        """Business logic with event collection."""
        if self.status != "pending":
            raise ValueError("Can only confirm pending orders")

        object.__setattr__(self, "status", "confirmed")

        event = OrderConfirmed(
            aggregate_id=str(self.id),
            aggregate_type="Order",
        )
        self._domain_events.append(event)

# Create with explicit ID
order = Order(
    id=UUID("12345678-1234-5678-1234-567812345678"),
    customer_id="cust-123",
)

# Create with auto-generated ID
from cqrs_ddd_core.primitives.id_generator import UUIDGenerator

generator = UUIDGenerator()
order = Order(id_generator=generator, customer_id="cust-123")
```

#### Event Collection

```python
# Execute business logic
order.confirm()

# Retrieve and clear events
events = order.clear_events()
print(f"Events raised: {len(events)}")  # 1
```

#### Event Sourcing Reconstitution

```python
# Reconstitute from event stream (used by event store)
order = Order.reconstitute(
    aggregate_id=UUID("12345678-1234-5678-1234-567812345678"),
    customer_id="cust-123",
    status="pending",
)

# Apply events to rebuild state
for event in event_stream:
    order.apply_event(event)
```

---

## DomainEvent

### Implementation

```python
from cqrs_ddd_core.domain.events import DomainEvent, enrich_event_metadata

class DomainEvent(BaseModel):
    """
    Base class for all domain events.

    Features:
    - Immutable (frozen=True)
    - Auto-generated event_id (UUID)
    - Auto-generated occurred_at (UTC)
    - Schema versioning
    - Tracing context
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1
    aggregate_id: str | None = None
    aggregate_type: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    correlation_id: str | None = None
    causation_id: str | None = None
```

### Usage Examples

#### Basic Event

```python
from cqrs_ddd_core.domain.events import DomainEvent

class OrderCreated(DomainEvent):
    """Event: Order was created."""

    # Required for event sourcing
    aggregate_id: str
    aggregate_type: str = "Order"

    # Event-specific fields
    customer_id: str
    total: float

# Create event
event = OrderCreated(
    aggregate_id="order-123",
    customer_id="cust-456",
    total=150.00,
)

print(event.event_id)  # Auto-generated UUID
print(event.occurred_at)  # UTC timestamp
print(event.version)  # 1 (default)
```

#### Event with Metadata

```python
event = OrderCreated(
    aggregate_id="order-123",
    customer_id="cust-456",
    total=150.00,
    metadata={
        "source": "mobile_app",
        "ip_address": "192.168.1.1",
    }
)
```

#### Enriching with Correlation

```python
from cqrs_ddd_core.domain.events import enrich_event_metadata

# Enrich with correlation context
enriched = enrich_event_metadata(
    event,
    correlation_id="req-abc-123",
    causation_id="cmd-xyz-789",
)

print(enriched.correlation_id)  # req-abc-123
print(enriched.causation_id)  # cmd-xyz-789
# Original event unchanged (frozen!)
```

---

## ValueObject

### Implementation

```python
from cqrs_ddd_core.domain.value_object import ValueObject

class ValueObject(BaseModel):
    """
    Base class for value objects.

    Features:
    - Immutable (frozen=True)
    - Structural equality
    - Hashable
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, self.__class__):
            return False
        return self.model_dump() == other.model_dump()

    def __hash__(self) -> int:
        return hash(tuple(sorted(self.model_dump().items())))
```

### Usage Examples

#### Basic Value Object

```python
from cqrs_ddd_core.domain.value_object import ValueObject

class Money(ValueObject):
    amount: float
    currency: str

    def add(self, other: "Money") -> "Money":
        """Add two money values (same currency)."""
        if self.currency != other.currency:
            raise ValueError("Cannot add different currencies")
        return Money(amount=self.amount + other.amount, currency=self.currency)

# Structural equality
price1 = Money(amount=100.00, currency="USD")
price2 = Money(amount=100.00, currency="USD")
print(price1 == price2)  # True

# Hashable
prices = {price1, price2}
print(len(prices))  # 1 (equal objects)

# Operations return new instances
total = price1.add(Money(amount=50.00, currency="USD"))
print(total)  # Money(amount=150.0, currency='USD')
```

#### Embedding in Aggregates

```python
class Order(AggregateRoot[UUID]):
    customer_id: str
    total: Money  # Embedded value object
```

---

## Mixins

### Available Mixins

| Mixin | Purpose | Fields |
|-------|---------|--------|
| `AuditableMixin` | Creation/update timestamps | `created_at`, `updated_at` |
| `ArchivableMixin` | Soft archival | `archived_at`, `archived_by` |
| `SpatialMixin` | Geographic location | `geom` (GeoJSON) |

### Usage Examples

#### AuditableMixin

```python
from cqrs_ddd_core.domain.mixins import AuditableMixin

class Document(AuditableMixin, AggregateRoot[str]):
    title: str
    content: str

doc = Document(id="doc-123", title="Report", content="...")
print(doc.created_at)  # Auto-set
print(doc.updated_at)  # Auto-set

doc.touch()  # Update timestamp
```

#### ArchivableMixin

```python
from cqrs_ddd_core.domain.mixins import ArchivableMixin

class Document(ArchivableMixin, AggregateRoot[str]):
    title: str

doc = Document(id="doc-123", title="Report")
doc.archive(by="user-456")

print(doc.is_archived)  # True
print(doc.archived_by)  # user-456

doc.restore()
print(doc.is_archived)  # False
```

#### SpatialMixin (requires `cqrs-ddd-core[geometry]`)

```python
from cqrs_ddd_core.domain.mixins import SpatialMixin
from geojson_pydantic.geometries import Point

class Store(SpatialMixin, AggregateRoot[str]):
    name: str

store = Store(
    id="store-123",
    name="Downtown",
    geom=Point(type="Point", coordinates=[-73.985428, 40.748817]),
)
```

---

## Specification

### Implementation

```python
from cqrs_ddd_core.domain.specification import ISpecification

@runtime_checkable
class ISpecification(Protocol, Generic[T]):
    """Protocol for the Specification pattern."""

    def is_satisfied_by(self, candidate: T) -> bool:
        """Check if candidate satisfies specification."""
        ...

    def to_dict(self) -> dict[str, Any]:
        """Convert to query dict."""
        ...
```

### Usage Examples

#### Simple Specification

```python
from cqrs_ddd_core.domain.specification import ISpecification

class OrderStatusSpecification(ISpecification[Order]):
    """Specification: Order has specific status."""

    def __init__(self, status: str):
        self.status = status

    def is_satisfied_by(self, candidate: Order) -> bool:
        """In-memory filtering."""
        return candidate.status == self.status

    def to_dict(self) -> dict[str, Any]:
        """Query building."""
        return {"status": self.status}

# Usage
spec = OrderStatusSpecification("confirmed")

# In-memory check
order = Order(status="confirmed")
print(spec.is_satisfied_by(order))  # True

# Query building
query = spec.to_dict()  # {"status": "confirmed"}
results = await repo.search(query)
```

#### Composite Specification

```python
class AndSpecification(ISpecification[Order]):
    """Combine specifications with AND."""

    def __init__(self, spec1: ISpecification[Order], spec2: ISpecification[Order]):
        self.spec1 = spec1
        self.spec2 = spec2

    def is_satisfied_by(self, candidate: Order) -> bool:
        return self.spec1.is_satisfied_by(candidate) and self.spec2.is_satisfied_by(candidate)

    def to_dict(self) -> dict[str, Any]:
        return {"$and": [self.spec1.to_dict(), self.spec2.to_dict()]}

# Usage
status_spec = OrderStatusSpecification("confirmed")
price_spec = PriceRangeSpecification(100.0, 500.0)
combined = AndSpecification(status_spec, price_spec)

results = await repo.search(combined)
```

---

## Event Registry

### Implementation

```python
from cqrs_ddd_core.domain.event_registry import EventTypeRegistry

registry = EventTypeRegistry()

# Register event types
registry.register("OrderCreated", OrderCreated)
registry.register("OrderConfirmed", OrderConfirmed)

# Lookup by name
event_cls = registry.get("OrderCreated")

# Get name from instance
event = OrderCreated(...)
event_name = registry.get_name(event)  # "OrderCreated"
```

---

## Best Practices

### ✅ DO: Business Logic in Aggregates

```python
class Order(AggregateRoot[UUID]):
    status: str = "pending"

    def confirm(self) -> None:
        if self.status != "pending":
            raise InvalidOrderStateError("...")

        object.__setattr__(self, "status", "confirmed")
        self._domain_events.append(OrderConfirmed(...))
```

### ❌ DON'T: Anemic Domain Model

```python
# Business logic in services - BAD!
class OrderService:
    def confirm(self, order: Order) -> None:
        order.status = "confirmed"
```

### ✅ DO: Include aggregate_id in Events

```python
class OrderConfirmed(DomainEvent):
    aggregate_id: str  # Always include
    aggregate_type: str = "Order"  # Always include
```

### ❌ DON'T: Missing Event Metadata

```python
class OrderConfirmed(DomainEvent):
    # Missing aggregate_id - breaks event sourcing!
    confirmed_by: str
```

---

## Summary

**Key Features:**
- Zero infrastructure dependencies
- Event sourcing ready
- Type-safe with generics
- Immutability by default
- Protocol-based design

**Components:**
- `AggregateRoot[ID]` - Consistency boundary
- `DomainEvent` - Immutable fact
- `ValueObject` - Identity-less value
- `Mixins` - Reusable behaviors
- `ISpecification[T]` - Business rules

---

**Last Updated:** February 22, 2026
**Package:** `cqrs_ddd_core.domain`
