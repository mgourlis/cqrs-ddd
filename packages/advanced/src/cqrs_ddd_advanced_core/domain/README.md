# Domain Utilities — Event Handler Support & Validation

**Helper mixins, decorators, and validators** for event-sourced aggregates.

---

## Overview

This folder provides **optional utilities** to enhance event-sourced aggregates:

- ✅ **EventSourcedAggregateMixin** — Introspection for event handlers
- ✅ **@aggregate_event_handler** — Decorator to mark handlers (metadata)
- ✅ **@aggregate_event_handler_validator** — Configure validation per aggregate
- ✅ **EventValidator** — Validate handler existence before applying events

**These are optional**. Aggregates work without them. They provide:
- Better introspection (what events does this aggregate handle?)
- Validation at startup (catch missing handlers early)
- Documentation via decorators (explicit event handler registration)

---

## Components

### 1. EventSourcedAggregateMixin

**Provides introspection methods** for event-sourced aggregates.

```python
from cqrs_ddd_core.domain.aggregate import AggregateRoot
from cqrs_ddd_advanced_core.domain.aggregate_mixin import EventSourcedAggregateMixin

class Order(AggregateRoot[str], EventSourcedAggregateMixin[str]):
    status: str = "pending"
    
    def apply_OrderCreated(self, event: OrderCreated) -> None:
        self.status = "created"
    
    def apply_OrderPaid(self, event: OrderPaid) -> None:
        self.status = "paid"

# Introspection
order = Order(id="order_123")
order.has_handler_for_event("OrderCreated")  # True
order.has_handler_for_event("OrderShipped")  # False

# Get handler method
handler = order.get_handler_for_event("OrderCreated")  # apply_OrderCreated

# List all supported event types
supported = order._get_supported_event_types()  # {"OrderCreated", "OrderPaid"}
```

**API**:

| Method | Description |
|--------|-------------|
| `has_handler_for_event(event_type: str) → bool` | Check if aggregate can handle event type |
| `get_handler_for_event(event_type: str) → Callable \| None` | Get handler method or None |
| `_get_supported_event_types() → set[str]` | Get all event types this aggregate handles |
| `_apply_event_internal(event: DomainEvent) → None` | Apply event using handler resolution |

**Handler Resolution Order**:

1. Try `apply_<EventType>` (PascalCase)
2. Try `apply_<event_type>` (snake_case for ruff compliance)
3. Try `apply_event` (generic fallback)
4. Raise `MissingEventHandlerError` if none found

**Why Use It**:

```python
# ✅ GOOD: Introspection for dynamic event handling
if aggregate.has_handler_for_event(event_type):
    handler = aggregate.get_handler_for_event(event_type)
    handler(event)

# ✅ GOOD: List supported events for documentation
supported = aggregate._get_supported_event_types()
print(f"Order aggregate handles: {supported}")

# ❌ BAD: Manual hasattr checks
if hasattr(aggregate, f"apply_{event_type}"):
    getattr(aggregate, f"apply_{event_type}")(event)
```

---

### 2. @aggregate_event_handler Decorator

**Marks a method as an event handler** (metadata only, no behavior change).

```python
from cqrs_ddd_advanced_core.domain.event_handlers import aggregate_event_handler

class Order(AggregateRoot[str]):
    status: str = "pending"
    
    # Mark as event handler (optional)
    @aggregate_event_handler()
    def apply_OrderCreated(self, event: OrderCreated) -> None:
        self.status = "created"
    
    # Explicit event type
    @aggregate_event_handler(event_type=OrderCreated)
    def handle_order_created(self, event: OrderCreated) -> None:
        self.status = "created"
```

**What It Does**:

- Adds `_is_aggregate_event_handler = True` metadata
- Optionally stores `_event_type` if explicitly provided
- Stores `_validate_on_load = True` flag

**Why Use It**:

- Documentation: Makes event handlers explicit
- Validation: Can validate all decorated handlers at startup
- IDE support: Better code navigation and documentation

**Note**: This decorator is **purely optional**. The framework finds handlers by naming convention (`apply_<EventType>`) without any decorators.

---

### 3. @aggregate_event_handler_validator Decorator

**Configures validation** for an entire aggregate class.

```python
from cqrs_ddd_advanced_core.domain.event_handlers import aggregate_event_handler_validator

@aggregate_event_handler_validator(enabled=True, strict=True)
class Order(AggregateRoot[str]):
    status: str = "pending"
    
    def apply_OrderCreated(self, event: OrderCreated) -> None:
        self.status = "created"
    
    # This would fail validation in strict mode:
    # def apply_event(self, event: DomainEvent) -> None:
    #     pass
```

**Configuration Options**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enabled` | `bool` | `True` | Enable validation for this aggregate |
| `strict` | `bool` | `False` | Require exact `apply_<EventType>` methods |
| `allow_fallback` | `bool` | `True` | Allow `apply_event` fallback (when `strict=False`) |

**Strict Mode**:

```python
# Strict mode: MUST have exact apply_<EventType> methods
@aggregate_event_handler_validator(strict=True)
class StrictOrder(AggregateRoot[str]):
    # ✅ GOOD: Exact handler
    def apply_OrderCreated(self, event: OrderCreated) -> None:
        pass
    
    # ❌ BAD: Generic fallback not allowed
    # def apply_event(self, event: DomainEvent) -> None:
    #     pass
```

**Lenient Mode** (default):

```python
# Lenient mode: Allows apply_event fallback
@aggregate_event_handler_validator(strict=False, allow_fallback=True)
class LenientOrder(AggregateRoot[str]):
    # ✅ GOOD: Exact handler
    def apply_OrderCreated(self, event: OrderCreated) -> None:
        pass
    
    # ✅ GOOD: Generic fallback allowed
    def apply_event(self, event: DomainEvent) -> None:
        # Handle unknown events
        pass
```

---

### 4. EventValidator

**Validates event handlers** before applying events.

```python
from cqrs_ddd_advanced_core.domain.event_validation import (
    EventValidator,
    EventValidationConfig,
)

# Strict validator - requires exact handlers
strict_validator = EventValidator(EventValidationConfig(
    enabled=True,
    strict_mode=True,
))

# Lenient validator - allows fallback
lenient_validator = EventValidator(EventValidationConfig(
    enabled=True,
    strict_mode=False,
    allow_fallback_handler=True,
))

# Disabled - no validation (performance)
no_validator = EventValidator(EventValidationConfig(
    enabled=False,
))
```

**Usage**:

```python
order = Order(id="order_123")
event = OrderCreated(order_id="order_123")

# Validate before applying
validator.validate_handler_exists(order, event)  # Raises if no handler

# Apply event
order._apply_event_internal(event)
```

**Integration with EventSourcedLoader**:

```python
from cqrs_ddd_advanced_core.event_sourcing import EventSourcedLoader

loader = EventSourcedLoader(
    aggregate_type=Order,
    event_store=event_store,
    event_registry=event_registry,
    validator=strict_validator,  # Optional validation
)

# Load - validates handlers before applying events
order = await loader.load("order_123")
```

---

## Exceptions

### MissingEventHandlerError

Raised when an aggregate has no handler for an event.

```python
from cqrs_ddd_advanced_core.domain.exceptions import MissingEventHandlerError

try:
    order._apply_event_internal(event)
except MissingEventHandlerError as e:
    print(f"No handler for {e.event_type} in {e.aggregate_type}")
    # Expected method: apply_OrderCreated(event) or apply_order_created(event)
```

**Also inherits from `AttributeError`** for backward compatibility.

### StrictValidationViolationError

Raised when strict validation mode is violated.

```python
from cqrs_ddd_advanced_core.domain.exceptions import StrictValidationViolationError

# Raised when:
# - strict_mode=True
# - No exact apply_<EventType> method
# - Only apply_event fallback exists
```

---

## Usage Patterns

### Pattern 1: Minimal (No Utilities)

```python
from cqrs_ddd_core.domain.aggregate import AggregateRoot

class Order(AggregateRoot[str]):
    status: str = "pending"
    
    def apply_OrderCreated(self, event: OrderCreated) -> None:
        self.status = "created"

# Works fine without any utilities
```

### Pattern 2: With Introspection (Mixin)

```python
from cqrs_ddd_core.domain.aggregate import AggregateRoot
from cqrs_ddd_advanced_core.domain.aggregate_mixin import EventSourcedAggregateMixin

class Order(AggregateRoot[str], EventSourcedAggregateMixin[str]):
    status: str = "pending"
    
    def apply_OrderCreated(self, event: OrderCreated) -> None:
        self.status = "created"

# Now has introspection methods
order.has_handler_for_event("OrderCreated")  # True
```

### Pattern 3: With Decorators (Documentation)

```python
from cqrs_ddd_core.domain.aggregate import AggregateRoot
from cqrs_ddd_advanced_core.domain.event_handlers import (
    aggregate_event_handler,
    aggregate_event_handler_validator,
)

@aggregate_event_handler_validator(enabled=True, strict=True)
class Order(AggregateRoot[str]):
    status: str = "pending"
    
    @aggregate_event_handler()
    def apply_OrderCreated(self, event: OrderCreated) -> None:
        self.status = "created"

# Documented and validated
```

### Pattern 4: With Validation (Strict Mode)

```python
from cqrs_ddd_advanced_core.event_sourcing import EventSourcedLoader
from cqrs_ddd_advanced_core.domain.event_validation import (
    EventValidator,
    EventValidationConfig,
)

# Strict validator
validator = EventValidator(EventValidationConfig(
    enabled=True,
    strict_mode=True,
))

# Loader with validation
loader = EventSourcedLoader(
    aggregate_type=Order,
    event_store=event_store,
    event_registry=event_registry,
    validator=validator,  # Validates before applying
)

# Load - catches missing handlers early
order = await loader.load("order_123")
```

---

## Best Practices

### 1. Use Mixin for Introspection

```python
# ✅ GOOD: Introspection for dynamic handling
class Order(AggregateRoot[str], EventSourcedAggregateMixin[str]):
    pass

# ❌ BAD: Manual hasattr checks
if hasattr(aggregate, f"apply_{event_type}"):
    ...
```

### 2. Use Decorators for Documentation

```python
# ✅ GOOD: Explicit event handlers
@aggregate_event_handler()
def apply_OrderCreated(self, event: OrderCreated) -> None:
    pass

# ❌ BAD: No documentation
def apply_OrderCreated(self, event: OrderCreated) -> None:
    pass
```

### 3. Validate in Development, Skip in Production

```python
# Development
validator = EventValidator(EventValidationConfig(enabled=True, strict_mode=True))

# Production (performance)
validator = EventValidator(EventValidationConfig(enabled=False))
```

### 4. Use Strict Mode for Critical Aggregates

```python
@aggregate_event_handler_validator(strict=True)
class Payment(AggregateRoot[str]):
    # MUST have exact handlers - no generic fallback
    def apply_PaymentInitiated(self, event: PaymentInitiated) -> None:
        pass
```

---

## Summary

| Component | Purpose | Optional? |
|-----------|---------|-----------|
| `EventSourcedAggregateMixin` | Introspection for event handlers | Yes |
| `@aggregate_event_handler` | Mark handlers (documentation) | Yes |
| `@aggregate_event_handler_validator` | Configure validation per aggregate | Yes |
| `EventValidator` | Validate handler existence | Yes |

**Key Takeaways**:
- ✅ All utilities are **optional** — aggregates work without them
- ✅ Use **Mixin** for introspection (what events does this aggregate handle?)
- ✅ Use **Decorators** for documentation (explicit event handler registration)
- ✅ Use **Validator** in development to catch missing handlers early
- ✅ Disable validation in production for performance
- ✅ Use strict mode for critical aggregates

These utilities enhance **developer experience** and **safety** without changing core behavior.
