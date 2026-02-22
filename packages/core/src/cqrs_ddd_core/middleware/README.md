# Middleware Layer - Pipeline Components

**Package:** `cqrs_ddd_core.middleware`  
**Purpose:** Pluggable middleware pipeline for command/query processing

---

## Overview

The middleware layer provides a **pipeline architecture** for processing commands and queries with cross-cutting concerns.

### Design Philosophy

- **Pluggable** - Add/remove middleware dynamically
- **Ordered** - Control execution order
- **Transparent** - Transparent to handlers
- **Composable** - Chain multiple middleware

### Components

| Component | Purpose | File |
|-----------|---------|------|
| **MiddlewareRegistry** | Manage middleware | `registry.py` |
| **build_pipeline** | Build execution pipeline | `pipeline.py` |
| **LoggingMiddleware** | Request/response logging | `logging.py` |
| **ValidatorMiddleware** | Command/query validation | `validation.py` |
| **OutboxMiddleware** | Save events to outbox | `outbox.py` |
| **ConcurrencyGuardMiddleware** | Pessimistic locking | `concurrency.py` |
| **PersistenceMiddleware** | Auto-persist aggregates | `persistence.py` |

---

## MiddlewareRegistry

### Implementation

```python
from cqrs_ddd_core.middleware.registry import MiddlewareRegistry

class MiddlewareRegistry:
    """
    Registry for managing middleware.
    
    Features:
    - Ordered registration
    - Priority support
    - Enable/disable
    """
    
    def register(
        self,
        middleware: IMiddleware,
        *,
        priority: int = 0,
        enabled: bool = True,
    ) -> None:
        """Register middleware."""
        ...
    
    def get_ordered_middlewares(self) -> list[IMiddleware]:
        """Get middlewares sorted by priority."""
        ...
```

### Usage Example

```python
from cqrs_ddd_core.middleware.registry import MiddlewareRegistry
from cqrs_ddd_core.middleware.logging import LoggingMiddleware
from cqrs_ddd_core.middleware.validation import ValidatorMiddleware

# Create registry
registry = MiddlewareRegistry()

# Register middlewares
registry.register(LoggingMiddleware(), priority=0)
registry.register(ValidatorMiddleware(), priority=10)
registry.register(OutboxMiddleware(outbox), priority=20)

# Use with Mediator
mediator = Mediator(
    registry=handler_registry,
    uow_factory=uow_factory,
    middleware_registry=registry,
)
```

---

## Pipeline Execution

### How It Works

```python
from cqrs_ddd_core.middleware.pipeline import build_pipeline

# Middleware executes in order:
# 1. LoggingMiddleware (before)
# 2. ValidatorMiddleware (before)
# 3. Handler execution
# 4. ValidatorMiddleware (after)
# 5. LoggingMiddleware (after)

# Priority determines order:
# Lower priority = outer wrapper (runs first)
# Higher priority = inner wrapper (runs last before handler)

middlewares = [
    LoggingMiddleware(),      # priority=0 (outermost)
    ValidatorMiddleware(),     # priority=10
    OutboxMiddleware(outbox), # priority=20 (innermost)
]

pipeline = build_pipeline(middlewares, handler)
result = await pipeline(command)
```

---

## LoggingMiddleware

### Implementation

```python
from cqrs_ddd_core.middleware.logging import LoggingMiddleware

class LoggingMiddleware(IMiddleware):
    """
    Logs command/query execution.
    
    Features:
    - Request logging
    - Response logging
    - Error logging
    - Duration tracking
    """
    
    async def __call__(
        self,
        message: Any,
        next_handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        logger.info(f"Processing: {type(message).__name__}")
        
        start = time.time()
        try:
            result = await next_handler(message)
            duration = time.time() - start
            logger.info(f"Completed in {duration:.2f}s")
            return result
        except Exception as e:
            logger.error(f"Failed: {e}")
            raise
```

### Usage Example

```python
from cqrs_ddd_core.middleware.logging import LoggingMiddleware

registry.register(LoggingMiddleware(), priority=0)

# Logs:
# INFO: Processing: CreateOrderCommand
# INFO: Completed in 0.15s
```

---

## ValidatorMiddleware

### Implementation

```python
from cqrs_ddd_core.middleware.validation import ValidatorMiddleware

class ValidatorMiddleware(IMiddleware):
    """
    Validates commands/queries before execution.
    
    Features:
    - Pydantic validation
    - Custom validators
    - Early rejection
    """
    
    async def __call__(
        self,
        message: Any,
        next_handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        # Validate message
        result = await self.validator.validate(message)
        
        if not result.is_valid:
            raise ValidationError(result.errors)
        
        return await next_handler(message)
```

### Usage Example

```python
from cqrs_ddd_core.middleware.validation import ValidatorMiddleware

registry.register(ValidatorMiddleware(), priority=10)

# Validates using Pydantic models
# Raises ValidationError if invalid
```

---

## OutboxMiddleware

### Implementation

```python
from cqrs_ddd_core.middleware.outbox import OutboxMiddleware

class OutboxMiddleware(IMiddleware):
    """
    Saves CommandResponse.events to outbox after commit.
    
    Features:
    - Transactional outbox
    - Automatic event persistence
    - Same transaction as aggregate
    """
    
    def __init__(self, outbox: BufferedOutbox):
        self.outbox = outbox
    
    async def __call__(
        self,
        message: Any,
        next_handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        result = await next_handler(message)
        
        # Save events from CommandResponse
        if hasattr(result, 'events'):
            for event in result.events:
                await self.outbox.publish(event)
        
        return result
```

### Usage Example

```python
from cqrs_ddd_core.middleware.outbox import OutboxMiddleware

registry.register(OutboxMiddleware(outbox), priority=20)

# Automatically saves events from CommandResponse
# Events persisted in same transaction as aggregate
```

---

## ConcurrencyGuardMiddleware

### Implementation

```python
from cqrs_ddd_core.middleware.concurrency import ConcurrencyGuardMiddleware

class ConcurrencyGuardMiddleware(IMiddleware):
    """
    Implements pessimistic locking.
    
    Features:
    - Locks resources from command.get_critical_resources()
    - Prevents deadlocks by sorting
    - Configurable timeout
    """
    
    def __init__(
        self,
        lock_strategy: ILockStrategy,
        timeout_seconds: float = 30.0,
    ):
        self.lock = lock_strategy
        self.timeout = timeout_seconds
    
    async def __call__(
        self,
        message: Any,
        next_handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        # Get resources to lock
        resources = message.get_critical_resources() if hasattr(message, 'get_critical_resources') else []
        
        if not resources:
            return await next_handler(message)
        
        # Sort to prevent deadlocks
        sorted_resources = sorted(resources, key=lambda r: (r.resource_type, r.resource_id))
        
        # Acquire locks
        for resource in sorted_resources:
            acquired = await self.lock.acquire(
                f"{resource.resource_type}:{resource.resource_id}",
                timeout=self.timeout,
            )
            if not acquired:
                raise LockAcquisitionError(f"Failed to acquire lock: {resource}")
        
        try:
            return await next_handler(message)
        finally:
            # Release all locks
            for resource in sorted_resources:
                await self.lock.release(f"{resource.resource_type}:{resource.resource_id}")
```

### Usage Example

```python
from cqrs_ddd_core.middleware.concurrency import ConcurrencyGuardMiddleware

registry.register(
    ConcurrencyGuardMiddleware(lock_strategy, timeout_seconds=30.0),
    priority=15,
)

# Command with locking
class TransferFundsCommand(Command[None]):
    from_account: str
    to_account: str
    
    def get_critical_resources(self) -> list[ResourceIdentifier]:
        return [
            ResourceIdentifier("Account", self.from_account),
            ResourceIdentifier("Account", self.to_account),
        ]

# Middleware automatically locks accounts
# Prevents concurrent transfers
```

---

## PersistenceMiddleware

### Implementation

```python
from cqrs_ddd_core.middleware.persistence import EventStorePersistenceMiddleware

class EventStorePersistenceMiddleware(IMiddleware):
    """
    Auto-persists events from CommandResponse to IEventStore.
    
    Features:
    - Runs after handler returns
    - Converts domain events to StoredEvent
    - Batch persistence
    - Automatic version management
    """
```

### Usage Example

```python
from cqrs_ddd_core.middleware.persistence import EventStorePersistenceMiddleware
from cqrs_ddd_core.ports.event_store import IEventStore

# Create middleware with event store
middleware = EventStorePersistenceMiddleware(event_store=event_store)

# Register
registry.register(middleware, priority=25)

# Events automatically persisted after handler execution
```

---

## MiddlewareDefinition

### Implementation

```python
from cqrs_ddd_core.middleware.definition import MiddlewareDefinition

@dataclass
class MiddlewareDefinition:
    """
    Descriptor for a middleware in the pipeline.
    
    Supports **deferred instantiation**: supply *middleware_cls* and
    optional *factory* for lazy construction.
    
    Attributes:
        middleware_cls: Middleware class type
        priority: Execution priority (lower = outer wrapper)
        factory: Optional factory function for custom instantiation
        kwargs: Constructor arguments for middleware_cls
    """
    
    middleware_cls: type[IMiddleware]
    priority: int = 0
    factory: Callable[..., IMiddleware] | None = None
    kwargs: dict[str, object] = field(default_factory=dict)
    
    def build(self) -> IMiddleware:
        """Construct the middleware instance."""
        ...
```

### Usage Examples

#### Basic Usage

```python
from cqrs_ddd_core.middleware.definition import MiddlewareDefinition
from cqrs_ddd_core.middleware.logging import LoggingMiddleware

# Create definition
definition = MiddlewareDefinition(
    middleware_cls=LoggingMiddleware,
    priority=0,
)

# Build instance
middleware = definition.build()
```

#### With Factory (Dependency Injection)

```python
from cqrs_ddd_core.middleware.definition import MiddlewareDefinition
from cqrs_ddd_core.middleware.outbox import OutboxMiddleware

# Factory with dependencies
def create_outbox_middleware() -> OutboxMiddleware:
    outbox = get_outbox_from_container()
    return OutboxMiddleware(outbox)

# Definition with factory
definition = MiddlewareDefinition(
    middleware_cls=OutboxMiddleware,
    priority=20,
    factory=create_outbox_middleware,
)

# Build with custom factory
middleware = definition.build()  # Calls factory()
```

#### With Constructor Arguments

```python
from cqrs_ddd_core.middleware.definition import MiddlewareDefinition
from cqrs_ddd_core.middleware.concurrency import ConcurrencyGuardMiddleware

# Definition with kwargs
definition = MiddlewareDefinition(
    middleware_cls=ConcurrencyGuardMiddleware,
    priority=15,
    kwargs={
        "lock_strategy": redis_lock,
        "timeout_seconds": 30.0,
    },
)

# Build with args
middleware = definition.build()
```

---

## Best Practices

### ✅ DO: Use Middleware for Cross-Cutting Concerns

```python
# Logging, validation, outbox - all cross-cutting
registry.register(LoggingMiddleware(), priority=0)
registry.register(ValidatorMiddleware(), priority=10)
registry.register(OutboxMiddleware(outbox), priority=20)
```

### ❌ DON'T: Put Business Logic in Middleware

```python
# BAD: Business logic in middleware
class OrderValidationMiddleware(IMiddleware):
    async def __call__(self, message, next_handler):
        if message.customer_id == "blocked":
            raise ValueError("Blocked customer")  # Business rule!
        return await next_handler(message)

# Business logic belongs in aggregates or handlers
```

### ✅ DO: Order Middleware Correctly

```python
# Lower priority = outer (runs first)
# Higher priority = inner (runs last)

# Logging (outermost)
registry.register(LoggingMiddleware(), priority=0)

# Validation (early rejection)
registry.register(ValidatorMiddleware(), priority=10)

# Locking (before handler)
registry.register(ConcurrencyGuardMiddleware(lock), priority=15)

# Outbox (after handler)
registry.register(OutboxMiddleware(outbox), priority=20)
```

### ❌ DON'T: Hard-Code Middleware in Handlers

```python
# BAD: Middleware logic in handler
class CreateOrderHandler(CommandHandler[str]):
    async def handle(self, command: CreateOrderCommand) -> CommandResponse[str]:
        # Don't do validation here - use middleware
        if not command.items:
            raise ValueError("No items")
        
        # Don't do logging here - use middleware
        logger.info("Creating order")
        
        # Business logic only
        order = Order.create(...)
        return CommandResponse(result=order.id)
```

---

## Summary

**Key Features:**
- Pluggable pipeline
- Ordered execution
- Cross-cutting concerns
- Transparent to handlers

**Components:**
- `MiddlewareRegistry` - Manage middleware
- `LoggingMiddleware` - Request/response logging
- `ValidatorMiddleware` - Command/query validation
- `OutboxMiddleware` - Event outbox
- `ConcurrencyGuardMiddleware` - Pessimistic locking
- `PersistenceMiddleware` - Auto-persistence

---

**Last Updated:** February 22, 2026  
**Package:** `cqrs_ddd_core.middleware`
