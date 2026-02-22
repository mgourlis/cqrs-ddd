# Event Upcasting — Schema Evolution Without Migrations

**Non-destructive event schema evolution** for event-sourced systems.

---

## Overview

**Upcasting** transforms events written with an older schema into the current schema **at read time**, enabling schema evolution without:
- ❌ Database migrations
- ❌ Data loss
- ❌ Breaking changes
- ❌ Downtime

```
┌────────────────────────────────────────────────────────────────┐
│               UPCASTING FLOW                                   │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Event Store (v1 events)                                       │
│  ┌──────────────────────────────┐                              │
│  │ OrderCreated (v1)            │                              │
│  │ - amount: 100.0 (float)      │                              │
│  │ - customer_id: "cust_123"    │                              │
│  └───────────┬──────────────────┘                              │
│              │                                                 │
│              ▼                                                 │
│  ┌──────────────────────────────┐                              │
│  │  UpcasterChain               │                              │
│  │  - OrderCreatedV1ToV2       │                              │
│  │  - OrderCreatedV2ToV3       │                              │
│  └───────────┬──────────────────┘                              │
│              │                                                 │
│              ▼                                                 │
│  ┌──────────────────────────────┐                              │
│  │ OrderCreated (v3 - current)  │                              │
│  │ - amount: Decimal("100.00")  │                              │
│  │ - customer_id: "cust_123"    │                              │
│  │ - currency: "EUR" (new)      │                              │
│  │ - tax: Decimal("0.00") (new) │                              │
│  └──────────────────────────────┘                              │
│                                                                │
│  Domain code always sees latest schema!                        │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## Key Benefits

| Benefit | Description |
|---------|-------------|
| **Zero Downtime** | No migrations needed, events transformed on read |
| **Non-Destructive** | Original events preserved in event store |
| **Reversible** | Can always replay from original events |
| **Transparent** | Domain code always works with latest schema |
| **Chainable** | Multiple upcasters compose automatically |

---

## Quick Start

### 1. Define Event Versions

```python
# V1 event (old schema)
class OrderCreatedV1(DomainEvent):
    """Original schema with float amount."""
    order_id: str
    customer_id: str
    amount: float  # Old: float

# V2 event (new schema)
class OrderCreatedV2(DomainEvent):
    """Updated schema with Decimal amount and currency."""
    order_id: str
    customer_id: str
    amount: Decimal  # New: Decimal
    currency: str = "EUR"  # New field

# V3 event (latest schema)
class OrderCreatedV3(DomainEvent):
    """Latest schema with tax field."""
    order_id: str
    customer_id: str
    amount: Decimal
    currency: str = "EUR"
    tax: Decimal = Decimal("0.00")  # New field
```

### 2. Create Upcasters

```python
from cqrs_ddd_advanced_core.upcasting import EventUpcaster

class OrderCreatedV1ToV2(EventUpcaster):
    """Upcast OrderCreated from v1 to v2."""
    
    event_type = "OrderCreated"
    source_version = 1
    # target_version auto-computed as 2
    
    def upcast(self, data: dict[str, Any]) -> dict[str, Any]:
        """Transform v1 → v2."""
        return {
            **data,
            "amount": Decimal(str(data["amount"])),  # float → Decimal
            "currency": data.get("currency", "EUR"),  # Add default
        }

class OrderCreatedV2ToV3(EventUpcaster):
    """Upcast OrderCreated from v2 to v3."""
    
    event_type = "OrderCreated"
    source_version = 2
    target_version = 3
    
    def upcast(self, data: dict[str, Any]) -> dict[str, Any]:
        """Transform v2 → v3."""
        return {
            **data,
            "tax": data.get("tax", "0.00"),  # Add tax field
        }
```

### 3. Register Upcasters

```python
from cqrs_ddd_advanced_core.upcasting import UpcasterRegistry

registry = UpcasterRegistry()
registry.register(OrderCreatedV1ToV2())
registry.register(OrderCreatedV2ToV3())
```

### 4. Use with Event Loader

```python
from cqrs_ddd_advanced_core.event_sourcing import EventSourcedLoader

loader = EventSourcedLoader(
    aggregate_type=Order,
    event_store=event_store,
    event_registry=event_registry,
    upcaster_registry=registry,  # Automatic upcasting
)

# Load aggregate - events automatically upcasted
order = await loader.load("order_123")
# OrderCreated events are at v3 schema!
```

---

## Architecture

### UpcasterChain

Chains multiple upcasters together to transform events through multiple versions.

```python
from cqrs_ddd_advanced_core.upcasting import UpcasterChain

# Get chain for event type
chain = registry.chain_for("OrderCreated")

# Upcast from stored version
data, final_version = chain.upcast(
    event_type="OrderCreated",
    event_data=raw_data,
    stored_version=1,
)
# final_version = 3 (latest)
```

**Example Flow**:

```
Stored Event (v1)
  ↓
OrderCreatedV1ToV2.upcast() → v2
  ↓
OrderCreatedV2ToV3.upcast() → v3
  ↓
Final Event (v3 - current)
```

### UpcasterRegistry

Manages upcaster registration and chain building.

```python
registry = UpcasterRegistry()

# Register upcasters
registry.register(OrderCreatedV1ToV2())
registry.register(OrderCreatedV2ToV3())
registry.register(OrderItemAddedV1ToV2())

# Get chain for specific event type
chain = registry.chain_for("OrderCreated")

# Check available upcasters
upcasters = registry.get_upcasters("OrderCreated")
# Returns: [OrderCreatedV1ToV2(), OrderCreatedV2ToV3()]
```

---

## Usage Patterns

### Pattern 1: Add New Field with Default

**Scenario**: Add `currency` field with default value.

```python
# V1: No currency field
data_v1 = {
    "order_id": "order_123",
    "customer_id": "cust_456",
    "amount": "100.00",
}

# Upcaster
class OrderCreatedV1ToV2(EventUpcaster):
    event_type = "OrderCreated"
    source_version = 1
    
    def upcast(self, data: dict[str, Any]) -> dict[str, Any]:
        return {
            **data,
            "currency": data.get("currency", "EUR"),  # Add default
        }

# Result (v2)
data_v2 = {
    "order_id": "order_123",
    "customer_id": "cust_456",
    "amount": "100.00",
    "currency": "EUR",
}
```

### Pattern 2: Type Change

**Scenario**: Change `amount` from `float` to `Decimal`.

```python
# V1: float amount
data_v1 = {
    "order_id": "order_123",
    "amount": 100.50,  # float
}

# Upcaster
class OrderCreatedV1ToV2(EventUpcaster):
    event_type = "OrderCreated"
    source_version = 1
    
    def upcast(self, data: dict[str, Any]) -> dict[str, Any]:
        return {
            **data,
            "amount": Decimal(str(data["amount"])),  # float → Decimal
        }

# Result (v2)
data_v2 = {
    "order_id": "order_123",
    "amount": Decimal("100.50"),  # Decimal
}
```

### Pattern 3: Field Rename

**Scenario**: Rename `cust_id` to `customer_id`.

```python
# V1: Old field name
data_v1 = {
    "order_id": "order_123",
    "cust_id": "cust_456",  # Old name
}

# Upcaster
class OrderCreatedV1ToV2(EventUpcaster):
    event_type = "OrderCreated"
    source_version = 1
    
    def upcast(self, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "order_id": data["order_id"],
            "customer_id": data.pop("cust_id"),  # Rename
        }

# Result (v2)
data_v2 = {
    "order_id": "order_123",
    "customer_id": "cust_456",  # New name
}
```

### Pattern 4: Nested Structure Change

**Scenario**: Flatten nested `customer.id` to `customer_id`.

```python
# V1: Nested structure
data_v1 = {
    "order_id": "order_123",
    "customer": {
        "id": "cust_456",
        "name": "John Doe",
    },
}

# Upcaster
class OrderCreatedV1ToV2(EventUpcaster):
    event_type = "OrderCreated"
    source_version = 1
    
    def upcast(self, data: dict[str, Any]) -> dict[str, Any]:
        customer = data.pop("customer")
        return {
            **data,
            "customer_id": customer["id"],  # Flatten
            "customer_name": customer["name"],
        }

# Result (v2)
data_v2 = {
    "order_id": "order_123",
    "customer_id": "cust_456",
    "customer_name": "John Doe",
}
```

### Pattern 5: Data Migration

**Scenario**: Compute `total` from `items`.

```python
# V1: No total field
data_v1 = {
    "order_id": "order_123",
    "items": [
        {"price": "50.00", "qty": 2},
        {"price": "25.00", "qty": 1},
    ],
}

# Upcaster
class OrderCreatedV1ToV2(EventUpcaster):
    event_type = "OrderCreated"
    source_version = 1
    
    def upcast(self, data: dict[str, Any]) -> dict[str, Any]:
        total = sum(
            Decimal(item["price"]) * item["qty"]
            for item in data["items"]
        )
        return {
            **data,
            "total": str(total),  # Computed field
        }

# Result (v2)
data_v2 = {
    "order_id": "order_123",
    "items": [
        {"price": "50.00", "qty": 2},
        {"price": "25.00", "qty": 1},
    ],
    "total": "125.00",  # Computed
}
```

---

## Integration with Event Sourcing

### EventSourcedLoader Integration

```python
from cqrs_ddd_advanced_core.event_sourcing import EventSourcedLoader
from cqrs_ddd_advanced_core.upcasting import UpcasterRegistry

# Setup upcasters
upcaster_registry = UpcasterRegistry()
upcaster_registry.register(OrderCreatedV1ToV2())
upcaster_registry.register(OrderCreatedV2ToV3())

# Create loader with upcasting
loader = EventSourcedLoader(
    aggregate_type=Order,
    event_store=event_store,
    event_registry=event_registry,
    upcaster_registry=upcaster_registry,
)

# Load aggregate - events automatically upcasted
order = await loader.load("order_123")
```

### UpcastingEventReader Integration

For projections and event replay:

```python
from cqrs_ddd_advanced_core.event_sourcing import UpcastingEventReader

reader = UpcastingEventReader(
    event_store=event_store,
    upcaster_registry=upcaster_registry,
)

# Stream events with upcasting
async for event in reader.get_events_from_position(0):
    # All events at latest schema
    await projection_handler.handle(event)
```

---

## Best Practices

### 1. Keep Upcasters Simple

```python
# ✅ GOOD: Simple transformation
class OrderCreatedV1ToV2(EventUpcaster):
    def upcast(self, data: dict[str, Any]) -> dict[str, Any]:
        return {
            **data,
            "currency": data.get("currency", "EUR"),
        }

# ❌ BAD: Complex business logic
class OrderCreatedV1ToV2(EventUpcaster):
    def upcast(self, data: dict[str, Any]) -> dict[str, Any]:
        # Don't do complex validation or API calls!
        customer = await customer_service.get(data["customer_id"])
        return {
            **data,
            "customer_name": customer.name,
        }
```

### 2. Version All Events

```python
class OrderCreated(DomainEvent):
    """Event with schema version."""
    order_id: str
    customer_id: str
    amount: Decimal
    currency: str = "EUR"
    
    # version field inherited from DomainEvent
    # Defaults to 1, increment when schema changes
```

### 3. Test Upcasters

```python
import pytest

def test_order_created_v1_to_v2():
    upcaster = OrderCreatedV1ToV2()
    
    # V1 data
    v1_data = {
        "order_id": "order_123",
        "customer_id": "cust_456",
        "amount": "100.00",
    }
    
    # Upcast
    v2_data = upcaster.upcast(v1_data)
    
    # Verify
    assert v2_data["currency"] == "EUR"
    assert v2_data["order_id"] == "order_123"
```

### 4. Document Schema Changes

```python
class OrderCreatedV1ToV2(EventUpcaster):
    """Upcast OrderCreated from v1 to v2.
    
    Schema Changes:
    - Added currency field (default: "EUR")
    - Changed amount from float to Decimal
    
    Breaking Changes: None
    Migration Required: No
    """
    
    event_type = "OrderCreated"
    source_version = 1
    
    def upcast(self, data: dict[str, Any]) -> dict[str, Any]:
        return {
            **data,
            "currency": data.get("currency", "EUR"),
            "amount": Decimal(str(data["amount"])),
        }
```

### 5. Chain Upcasters Properly

```python
# ✅ GOOD: Sequential versions
registry.register(OrderCreatedV1ToV2())  # v1 → v2
registry.register(OrderCreatedV2ToV3())  # v2 → v3
registry.register(OrderCreatedV3ToV4())  # v3 → v4

# ❌ BAD: Skip versions
registry.register(OrderCreatedV1ToV2())
registry.register(OrderCreatedV3ToV4())  # Missing v2 → v3!
```

---

## Advanced Topics

### Conditional Upcasting

```python
class OrderCreatedV1ToV2(EventUpcaster):
    """Upcast with conditional logic."""
    
    event_type = "OrderCreated"
    source_version = 1
    
    def upcast(self, data: dict[str, Any]) -> dict[str, Any]:
        # Only apply to specific orders
        if data.get("region") == "US":
            currency = "USD"
        else:
            currency = "EUR"
        
        return {
            **data,
            "currency": currency,
        }
```

### Multiple Event Types

```python
# Register upcasters for multiple event types
registry.register(OrderCreatedV1ToV2())
registry.register(OrderItemAddedV1ToV2())
registry.register(OrderSubmittedV1ToV2())

# Get chains per event type
order_chain = registry.chain_for("OrderCreated")
item_chain = registry.chain_for("OrderItemAdded")
submit_chain = registry.chain_for("OrderSubmitted")
```

### Upcaster Inheritance

```python
class BaseOrderUpcaster(EventUpcaster):
    """Base upcaster with shared logic."""
    
    event_type = "OrderCreated"
    
    def add_metadata(self, data: dict[str, Any]) -> dict[str, Any]:
        """Add common metadata fields."""
        return {
            **data,
            "upcasted_at": datetime.now(timezone.utc).isoformat(),
        }

class OrderCreatedV1ToV2(BaseOrderUpcaster):
    source_version = 1
    
    def upcast(self, data: dict[str, Any]) -> dict[str, Any]:
        data = super().add_metadata(data)
        return {
            **data,
            "currency": "EUR",
        }
```

---

## Summary

| Aspect | Upcasting | Database Migration |
|--------|-----------|-------------------|
| **When Applied** | At read time | At write time |
| **Downtime** | None | Often required |
| **Data Loss** | None | Possible |
| **Reversibility** | Easy | Difficult |
| **Performance** | Slight overhead | No overhead |
| **Complexity** | Low | High |

**Key Takeaways**:
- ✅ Use upcasting for event schema evolution
- ✅ Keep upcasters simple and pure functions
- ✅ Chain upcasters for multi-version upgrades
- ✅ Test upcasters thoroughly
- ✅ Document schema changes
- ✅ Integrate with EventSourcedLoader and UpcastingEventReader

Upcasting enables **zero-downtime schema evolution** for event-sourced systems without data loss or breaking changes.
