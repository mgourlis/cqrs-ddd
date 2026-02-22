# Advanced CQRS Handlers — Resilient Command Processing

Production-ready command handlers with **automatic retry**, **conflict resolution**, and **pipeline behavior** for building robust CQRS systems.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Pipeline Pattern](#pipeline-pattern)
4. [Retry Behavior](#retry-behavior)
5. [Conflict Resolution](#conflict-resolution)
6. [Handler Types](#handler-types)
7. [Usage Examples](#usage-examples)
8. [Best Practices](#best-practices)

---

## Overview

The advanced CQRS handlers extend the core `CommandHandler` with:

- **Pipeline Architecture**: Customize handler behavior with middleware-like behaviors
- **Automatic Retry**: Retry failed commands with configurable policies
- **Conflict Resolution**: Automatically resolve optimistic concurrency conflicts
- **Composable Mixins**: Mix and match behaviors as needed

```
┌────────────────────────────────────────────────────────────────┐
│          RESILIENT COMMAND HANDLER PIPELINE                    │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Command: UpdateOrder                                          │
│     ↓                                                          │
│  ┌──────────────────────────────────────┐                      │
│  │  Pipeline Behavior 1: Retry          │                      │
│  │  - Catches exceptions                │                      │
│  │  - Retries with exponential backoff  │                      │
│  └──────────────────┬───────────────────┘                      │
│                     ↓                                          │
│  ┌──────────────────────────────────────┐                      │
│  │  Pipeline Behavior 2: Conflict Res   │                      │
│  │  - Catches ConcurrencyError          │                      │
│  │  - Fetches latest state              │                      │
│  │  - Merges changes                    │                      │
│  │  - Retries with merged command       │                      │
│  └──────────────────┬───────────────────┘                      │
│                     ↓                                          │
│  ┌──────────────────────────────────────┐                      │
│  │  Core Handler: process()             │                      │
│  │  - Business logic                    │                      │
│  │  - Load aggregate                    │                      │
│  │  - Execute command                   │                      │
│  │  - Persist changes                   │                      │
│  └──────────────────┬───────────────────┘                      │
│                     ↓                                          │
│  CommandResponse: Success/Failure                              │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## Architecture

### Base Class Hierarchy

```
CommandHandler (core)
    ↓
PipelinedCommandHandler
    ├── RetryableCommandHandler (with retry)
    ├── ConflictCommandHandler (with conflict resolution)
    └── ResilientCommandHandler (with both)
```

### Key Components

| Component | Purpose | Use Case |
|-----------|---------|----------|
| `PipelinedCommandHandler` | Base class with pipeline support | Custom behaviors |
| `RetryBehaviorMixin` | Automatic retry on failure | Transient errors |
| `ConflictResolutionMixin` | Automatic conflict resolution | Optimistic concurrency |
| `RetryPolicy` | Retry delay strategies | Configurable backoff |
| `ConflictConfig` | Conflict resolution strategies | Merge, last-wins, etc. |

---

## Pipeline Pattern

### How It Works

The pipeline pattern allows you to wrap the core `process()` method with custom behaviors (middleware).

```python
from cqrs_ddd_advanced_core.cqrs.handlers import PipelinedCommandHandler

class MyHandler(PipelinedCommandHandler[str]):
    async def process(self, command: MyCommand) -> CommandResponse[str]:
        # Core business logic
        return CommandResponse(result="success")
    
    def get_pipeline(self):
        # Build pipeline with behaviors
        pipeline = self.process
        for behavior in reversed(self._behaviors):
            pipeline = behavior(pipeline)
        return pipeline
```

### Adding Custom Behaviors

```python
from collections.abc import Callable, Awaitable

# Define a behavior (wrapper function)
def logging_behavior(
    next_fn: Callable[[Command], Awaitable[CommandResponse]]
) -> Callable[[Command], Awaitable[CommandResponse]]:
    async def wrapped(command: Command) -> CommandResponse:
        logger.info(f"Processing {type(command).__name__}")
        result = await next_fn(command)
        logger.info(f"Completed {type(command).__name__}")
        return result
    return wrapped

# Add to handler
handler = MyHandler(dispatcher)
handler.add_behavior(logging_behavior)
```

**Behavior Execution Order**:
- Behaviors are applied in **LIFO order** (last added = outermost)
- Example: `retry → conflict_resolution → process`

---

## Retry Behavior

### Retry Policies

#### 1. FixedRetryPolicy

Retries with a fixed delay between attempts.

```python
from cqrs_ddd_advanced_core.cqrs.mixins import FixedRetryPolicy

policy = FixedRetryPolicy(
    max_retries=3,
    delay_ms=1000,  # 1 second between retries
    jitter=True,  # Add random jitter
)
```

**Use Case**: Simple, predictable retry delays.

#### 2. ExponentialBackoffPolicy (Recommended)

Retries with exponentially increasing delay.

```python
from cqrs_ddd_advanced_core.cqrs.mixins import ExponentialBackoffPolicy

policy = ExponentialBackoffPolicy(
    max_retries=5,
    initial_delay_ms=100,  # Start with 100ms
    multiplier=2.0,  # Double each time
    max_delay_ms=5000,  # Cap at 5 seconds
    jitter=True,
)
```

**Delay Pattern**:
```
Attempt 1: 100ms
Attempt 2: 200ms
Attempt 3: 400ms
Attempt 4: 800ms
Attempt 5: 1600ms
...
```

**Use Case**: Network failures, database timeouts, rate limiting.

### Using Retry with Commands

```python
from cqrs_ddd_advanced_core.cqrs.mixins import Retryable, ExponentialBackoffPolicy
from cqrs_ddd_core.cqrs.command import Command

class UpdateOrderCommand(Command[str], Retryable):
    """Command with automatic retry on failure."""
    order_id: str
    status: str
    
    # Inherited from Retryable:
    # retry_policy: RetryPolicy = Field(default_factory=ExponentialBackoffPolicy)
```

**Handler**:

```python
from cqrs_ddd_advanced_core.cqrs.handlers import RetryableCommandHandler

class UpdateOrderHandler(RetryableCommandHandler[str]):
    async def process(self, command: UpdateOrderCommand) -> CommandResponse[str]:
        # If this fails, it will be automatically retried
        order = await self.dispatcher.retrieve([command.order_id], uow)
        order.update_status(command.status)
        await self.dispatcher.persist(order, uow)
        return CommandResponse(result=order.id)
```

**What Gets Retried**:
- ✅ Network timeouts
- ✅ Database connection errors
- ✅ Transient failures
- ❌ Validation errors (immediate failure)
- ❌ Business rule violations (immediate failure)

---

## Conflict Resolution

### The Problem: Optimistic Concurrency

When multiple users update the same aggregate simultaneously:

```
User A: Load Order (v1) → Modify → Save (v2) ✓
User B: Load Order (v1) → Modify → Save (v2) ✗ CONFLICT!
```

### Solution: Automatic Conflict Resolution

```
┌────────────────────────────────────────────────────────────────┐
│         CONFLICT RESOLUTION FLOW                               │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  1. User B: UpdateOrder(status="shipped")                     │
│     ↓                                                          │
│  2. Handler attempts save                                      │
│     - Throws ConcurrencyError (v1 != current v2)              │
│     ↓                                                          │
│  3. Conflict Resolution Behavior:                             │
│     a. Fetch latest state (v2)                                │
│     b. Get incoming state from command                        │
│     c. Apply merge strategy:                                  │
│        - Deep merge                                           │
│        - Field-level merge                                    │
│        - Timestamp last-wins                                  │
│     d. Create new command with merged state                   │
│     ↓                                                          │
│  4. Retry with merged command                                  │
│     - Save succeeds (v3)                                      │
│     ↓                                                          │
│  5. Return success                                             │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### Conflict Resolution Policies

#### 1. FIRST_WINS (Default)

First update wins, subsequent updates fail immediately.

```python
from cqrs_ddd_advanced_core.cqrs.mixins import ConflictConfig
from cqrs_ddd_advanced_core.conflict.resolution import ConflictResolutionPolicy

config = ConflictConfig(policy=ConflictResolutionPolicy.FIRST_WINS)
```

**Use Case**: Critical data where conflicts should be explicit.

#### 2. LAST_WINS

Last update wins (overwrites previous).

```python
config = ConflictConfig(policy=ConflictResolutionPolicy.LAST_WINS)
```

**Use Case**: Non-critical data, user preferences.

#### 3. MERGE

Automatically merge conflicting changes.

```python
config = ConflictConfig(
    policy=ConflictResolutionPolicy.MERGE,
    strategy_name="deep",  # Use deep merge strategy
    append_lists=True,  # Append list items instead of replace
)
```

**Use Case**: Complex aggregates with multiple fields.

### Merge Strategies

#### DeepMergeStrategy

Recursively merges nested objects and lists.

```python
from cqrs_ddd_advanced_core.conflict.resolution import DeepMergeStrategy

strategy = DeepMergeStrategy(
    append_lists=True,
    list_identity_key="id",  # Match list items by "id" field
)

# Example:
current = {
    "items": [{"id": 1, "qty": 2}],
    "status": "pending",
}
incoming = {
    "items": [{"id": 1, "qty": 3}],  # Update qty
    "notes": "Updated",  # New field
}

merged = strategy.merge(current, incoming)
# Result:
# {
#     "items": [{"id": 1, "qty": 3}],  # Merged by id
#     "status": "pending",  # Kept from current
#     "notes": "Updated",  # Added from incoming
# }
```

#### FieldLevelMergeStrategy

Merges specific fields with fine-grained control.

```python
from cqrs_ddd_advanced_core.conflict.resolution import FieldLevelMergeStrategy

strategy = FieldLevelMergeStrategy(
    include_fields={"status", "notes"},  # Only merge these fields
    exclude_fields={"created_at"},  # Never overwrite these
)

# Example:
current = {"status": "pending", "notes": "Old", "created_at": "2024-01-01"}
incoming = {"status": "shipped", "notes": "New", "created_at": "2024-01-02"}

merged = strategy.merge(current, incoming)
# Result:
# {
#     "status": "shipped",  # Merged (in include_fields)
#     "notes": "New",  # Merged (in include_fields)
#     "created_at": "2024-01-01",  # NOT merged (in exclude_fields)
# }
```

#### TimestampLastWinsStrategy

Uses timestamp field to determine which version wins.

```python
from cqrs_ddd_advanced_core.conflict.resolution import TimestampLastWinsStrategy

strategy = TimestampLastWinsStrategy(
    timestamp_field="modified_at",  # Field to compare
    fallback_to_incoming=True,  # Use incoming if timestamps equal
)

# Example:
current = {"status": "pending", "modified_at": "2024-01-01T10:00:00Z"}
incoming = {"status": "shipped", "modified_at": "2024-01-01T11:00:00Z"}

merged = strategy.merge(current, incoming)
# Result: incoming (later timestamp)
# {"status": "shipped", "modified_at": "2024-01-01T11:00:00Z"}
```

### Using Conflict Resolution with Commands

```python
from cqrs_ddd_advanced_core.cqrs.mixins import ConflictResilient, ConflictConfig
from cqrs_ddd_advanced_core.conflict.resolution import ConflictResolutionPolicy

class UpdateOrderCommand(Command[str], ConflictResilient):
    """Command with automatic conflict resolution."""
    order_id: str
    updates: dict
    
    # Configure conflict resolution
    conflict_config: ConflictConfig = Field(
        default_factory=lambda: ConflictConfig(
            policy=ConflictResolutionPolicy.MERGE,
            strategy_name="deep",
            append_lists=True,
        )
    )
```

**Handler** (must implement abstract methods):

```python
from cqrs_ddd_advanced_core.cqrs.handlers import ConflictCommandHandler

class UpdateOrderHandler(ConflictCommandHandler[str]):
    async def process(self, command: UpdateOrderCommand) -> CommandResponse[str]:
        order = await self.dispatcher.retrieve([command.order_id], uow)
        # Apply updates
        await self.dispatcher.persist(order, uow)
        return CommandResponse(result=order.id)
    
    async def fetch_latest_state(self, command: UpdateOrderCommand) -> dict:
        """Fetch current order state from database."""
        order = await self.dispatcher.retrieve([command.order_id], None)
        return order.model_dump() if order else None
    
    def get_incoming_state(self, command: UpdateOrderCommand) -> dict:
        """Extract incoming state from command."""
        return command.updates
    
    def update_command(
        self, command: UpdateOrderCommand, merged_state: dict
    ) -> UpdateOrderCommand:
        """Create new command with merged state."""
        return UpdateOrderCommand(
            order_id=command.order_id,
            updates=merged_state,
            # Preserve retry/conflict config
            conflict_config=command.conflict_config,
        )
```

---

## Handler Types

### 1. PipelinedCommandHandler

Base class with pipeline support (no built-in behaviors).

```python
from cqrs_ddd_advanced_core.cqrs.handlers import PipelinedCommandHandler

class MyHandler(PipelinedCommandHandler[str]):
    async def process(self, command: MyCommand) -> CommandResponse[str]:
        # Your business logic
        return CommandResponse(result="success")
```

**Use Case**: Custom behaviors, lightweight handlers.

---

### 2. RetryableCommandHandler

Adds automatic retry behavior.

```python
from cqrs_ddd_advanced_core.cqrs.handlers import RetryableCommandHandler

class UpdateOrderHandler(RetryableCommandHandler[str]):
    async def process(self, command: UpdateOrderCommand) -> CommandResponse[str]:
        # Will be retried on failure
        return CommandResponse(result="success")
```

**Requires**: Command must extend `Retryable` mixin.

**Use Case**: Network operations, external APIs, database operations.

---

### 3. ConflictCommandHandler

Adds automatic conflict resolution.

```python
from cqrs_ddd_advanced_core.cqrs.handlers import ConflictCommandHandler

class UpdateOrderHandler(ConflictCommandHandler[str]):
    async def process(self, command: UpdateOrderCommand) -> CommandResponse[str]:
        # Conflicts will be automatically resolved
        return CommandResponse(result="success")
    
    # Must implement abstract methods (see above)
    async def fetch_latest_state(self, command): ...
    def get_incoming_state(self, command): ...
    def update_command(self, command, merged_state): ...
```

**Requires**: Command must extend `ConflictResilient` mixin.

**Use Case**: Concurrent updates, collaborative editing, optimistic concurrency.

---

### 4. ResilientCommandHandler (Recommended)

Adds **both** retry and conflict resolution.

```python
from cqrs_ddd_advanced_core.cqrs.handlers import ResilientCommandHandler

class UpdateOrderHandler(ResilientCommandHandler[str]):
    async def process(self, command: UpdateOrderCommand) -> CommandResponse[str]:
        # Will be retried on failure AND conflicts will be resolved
        return CommandResponse(result="success")
    
    # Must implement conflict resolution methods
    async def fetch_latest_state(self, command): ...
    def get_incoming_state(self, command): ...
    def update_command(self, command, merged_state): ...
```

**Requires**: Command must extend **both** `Retryable` and `ConflictResilient` mixins.

**Use Case**: Production-grade handlers with full resilience.

---

## Usage Examples

### Example 1: Simple Retry

```python
from cqrs_ddd_core.cqrs.command import Command
from cqrs_ddd_advanced_core.cqrs.mixins import Retryable, ExponentialBackoffPolicy
from cqrs_ddd_advanced_core.cqrs.handlers import RetryableCommandHandler

# Command with retry
class SendEmailCommand(Command[str], Retryable):
    to: str
    subject: str
    body: str
    
    retry_policy: ExponentialBackoffPolicy = Field(
        default_factory=lambda: ExponentialBackoffPolicy(
            max_retries=3,
            initial_delay_ms=500,
        )
    )

# Handler
class SendEmailHandler(RetryableCommandHandler[str]):
    async def process(self, command: SendEmailCommand) -> CommandResponse[str]:
        # This might fail due to network issues
        await email_service.send(command.to, command.subject, command.body)
        return CommandResponse(result="sent")

# Usage
handler = SendEmailHandler(dispatcher)
result = await handler.handle(SendEmailCommand(...))
```

---

### Example 2: Conflict Resolution

```python
from cqrs_ddd_core.cqrs.command import Command
from cqrs_ddd_advanced_core.cqrs.mixins import ConflictResilient, ConflictConfig
from cqrs_ddd_advanced_core.conflict.resolution import ConflictResolutionPolicy
from cqrs_ddd_advanced_core.cqrs.handlers import ConflictCommandHandler

# Command with conflict resolution
class UpdateProfileCommand(Command[str], ConflictResilient):
    user_id: str
    updates: dict
    
    conflict_config: ConflictConfig = Field(
        default_factory=lambda: ConflictConfig(
            policy=ConflictResolutionPolicy.MERGE,
            strategy_name="field",
            include_fields={"name", "email", "preferences"},
        )
    )

# Handler
class UpdateProfileHandler(ConflictCommandHandler[str]):
    async def process(self, command: UpdateProfileCommand) -> CommandResponse[str]:
        user = await self.dispatcher.retrieve([command.user_id], uow)
        for key, value in command.updates.items():
            setattr(user, key, value)
        await self.dispatcher.persist(user, uow)
        return CommandResponse(result=user.id)
    
    async def fetch_latest_state(self, command: UpdateProfileCommand):
        user = await self.dispatcher.retrieve([command.user_id], None)
        return user.model_dump() if user else None
    
    def get_incoming_state(self, command: UpdateProfileCommand):
        return command.updates
    
    def update_command(self, command: UpdateProfileCommand, merged_state: dict):
        return UpdateProfileCommand(
            user_id=command.user_id,
            updates=merged_state,
            conflict_config=command.conflict_config,
        )

# Usage
handler = UpdateProfileHandler(dispatcher)
result = await handler.handle(UpdateProfileCommand(...))
```

---

### Example 3: Full Resilience (Recommended)

```python
from cqrs_ddd_core.cqrs.command import Command
from cqrs_ddd_advanced_core.cqrs.mixins import (
    Retryable,
    ConflictResilient,
    ConflictConfig,
    ExponentialBackoffPolicy,
)
from cqrs_ddd_advanced_core.conflict.resolution import ConflictResolutionPolicy
from cqrs_ddd_advanced_core.cqrs.handlers import ResilientCommandHandler

# Command with both retry and conflict resolution
class UpdateOrderCommand(
    Command[str],
    Retryable,
    ConflictResilient,
):
    order_id: str
    updates: dict
    
    # Retry configuration
    retry_policy: ExponentialBackoffPolicy = Field(
        default_factory=lambda: ExponentialBackoffPolicy(
            max_retries=3,
            initial_delay_ms=100,
        )
    )
    
    # Conflict resolution configuration
    conflict_config: ConflictConfig = Field(
        default_factory=lambda: ConflictConfig(
            policy=ConflictResolutionPolicy.MERGE,
            strategy_name="deep",
            append_lists=True,
            list_identity_key="product_id",
        )
    )

# Handler
class UpdateOrderHandler(ResilientCommandHandler[str]):
    async def process(self, command: UpdateOrderCommand) -> CommandResponse[str]:
        # 1. Load order
        orders = await self.dispatcher.retrieve([command.order_id], uow)
        if not orders:
            raise ValueError(f"Order {command.order_id} not found")
        
        order = orders[0]
        
        # 2. Apply updates
        for key, value in command.updates.items():
            if hasattr(order, key):
                setattr(order, key, value)
        
        # 3. Persist (may throw ConcurrencyError)
        await self.dispatcher.persist(order, uow)
        
        return CommandResponse(
            result=order.id,
            events=order.collect_events(),
        )
    
    async def fetch_latest_state(self, command: UpdateOrderCommand):
        """Fetch current order state from database."""
        orders = await self.dispatcher.retrieve([command.order_id], None)
        return orders[0].model_dump() if orders else None
    
    def get_incoming_state(self, command: UpdateOrderCommand):
        """Extract incoming state from command."""
        return command.updates
    
    def update_command(
        self, command: UpdateOrderCommand, merged_state: dict
    ) -> UpdateOrderCommand:
        """Create new command with merged state."""
        return UpdateOrderCommand(
            order_id=command.order_id,
            updates=merged_state,
            retry_policy=command.retry_policy,
            conflict_config=command.conflict_config,
        )

# Usage
handler = UpdateOrderHandler(dispatcher)
result = await handler.handle(UpdateOrderCommand(
    order_id="order_123",
    updates={"status": "shipped", "notes": "Express delivery"},
))
# ✓ Automatically retries on transient failures
# ✓ Automatically resolves conflicts
```

---

### Example 4: Custom Merge Strategy

```python
from cqrs_ddd_advanced_core.conflict.resolution import IMergeStrategy

class CustomOrderMergeStrategy(IMergeStrategy):
    """Custom merge logic for orders."""
    
    def merge(self, current: dict, incoming: dict) -> dict:
        # Custom business logic
        merged = current.copy()
        
        # Always preserve created_at
        merged["created_at"] = current.get("created_at")
        
        # Merge items by product_id
        current_items = {item["product_id"]: item for item in current.get("items", [])}
        for item in incoming.get("items", []):
            current_items[item["product_id"]] = item
        merged["items"] = list(current_items.values())
        
        # Take latest status
        merged["status"] = incoming.get("status", current.get("status"))
        
        return merged

# Register strategy
from cqrs_ddd_advanced_core.conflict.resolution import MergeStrategyRegistry

registry = MergeStrategyRegistry()
registry.register("custom_order", CustomOrderMergeStrategy)

# Use in command
class UpdateOrderCommand(Command[str], ConflictResilient):
    conflict_config: ConflictConfig = Field(
        default_factory=lambda: ConflictConfig(
            policy=ConflictResolutionPolicy.MERGE,
            strategy_name="custom_order",
        )
    )

# Inject registry in handler
handler = UpdateOrderHandler(dispatcher, strategy_registry=registry)
```

---

## Best Practices

### 1. Choose the Right Handler

| Scenario | Handler | Reasoning |
|----------|---------|-----------|
| Simple operations | `PipelinedCommandHandler` | No resilience needed |
| Network operations | `RetryableCommandHandler` | Handles transient failures |
| Concurrent updates | `ConflictCommandHandler` | Handles optimistic concurrency |
| **Production systems** | `ResilientCommandHandler` | Full resilience (recommended) |

### 2. Configure Retry Appropriately

```python
# ✅ GOOD: Exponential backoff with jitter
retry_policy = ExponentialBackoffPolicy(
    max_retries=3,
    initial_delay_ms=100,
    multiplier=2.0,
    jitter=True,  # Prevents thundering herd
)

# ❌ BAD: Too many retries
retry_policy = FixedRetryPolicy(
    max_retries=10,  # Too many!
    delay_ms=100,
)
```

### 3. Choose the Right Conflict Policy

```python
# ✅ GOOD: Merge for collaborative editing
conflict_config = ConflictConfig(
    policy=ConflictResolutionPolicy.MERGE,
    strategy_name="deep",
    append_lists=True,
)

# ❌ BAD: Last-wins for critical data
conflict_config = ConflictConfig(
    policy=ConflictResolutionPolicy.LAST_WINS,  # Data loss!
)
```

### 4. Test Conflict Resolution

```python
import pytest

@pytest.mark.asyncio
async def test_conflict_resolution():
    # 1. Create order
    order = Order(id="order_123", status="pending")
    await repository.persist(order, uow)
    
    # 2. Simulate concurrent update
    order2 = await repository.retrieve(["order_123"], uow)
    order2.status = "processing"
    await repository.persist(order2, uow)
    
    # 3. Try to update stale order (should auto-resolve)
    command = UpdateOrderCommand(
        order_id="order_123",
        updates={"notes": "Customer request"},
        conflict_config=ConflictConfig(
            policy=ConflictResolutionPolicy.MERGE,
        ),
    )
    
    result = await handler.handle(command)
    assert result.result == "order_123"
    
    # 4. Verify merge
    final = await repository.retrieve(["order_123"], uow)
    assert final.status == "processing"  # Kept from concurrent update
    assert final.notes == "Customer request"  # Added from command
```

### 5. Log and Monitor

```python
# Use hooks for observability
from cqrs_ddd_core.instrumentation import get_hook_registry

registry = get_hook_registry()

@registry.hook("handler.retry.*")
async def log_retry(context: dict):
    logger.warning(
        f"Retrying {context['handler.type']}: "
        f"attempt {context['attempt']}/{context['max_retries']}"
    )

@registry.hook("handler.conflict.*")
async def log_conflict(context: dict):
    logger.info(
        f"Conflict resolved for {context['command.type']}: "
        f"strategy={context.get('strategy')}"
    )
```

### 6. Don't Retry Everything

```python
# ✅ GOOD: Retry network errors only
async def process(self, command):
    try:
        await external_api.call()
    except NetworkError:
        raise  # Will be retried
    except ValidationError:
        raise  # Won't be retried (immediate failure)

# ❌ BAD: Retrying business errors
async def process(self, command):
    if order.status == "cancelled":
        raise BusinessError("Cannot update cancelled order")
    # This will be retried 3 times! (wasteful)
```

---

## Summary

| Feature | Handler | When to Use |
|---------|---------|-------------|
| **Pipeline** | `PipelinedCommandHandler` | Custom behaviors |
| **Retry** | `RetryableCommandHandler` | Transient failures |
| **Conflict Resolution** | `ConflictCommandHandler` | Optimistic concurrency |
| **Full Resilience** | `ResilientCommandHandler` | **Production (recommended)** |

**Key Takeaways**:
- ✅ Use `ResilientCommandHandler` for production systems
- ✅ Configure exponential backoff with jitter
- ✅ Choose appropriate merge strategy for your domain
- ✅ Test conflict resolution scenarios
- ✅ Monitor retries and conflicts with hooks
- ✅ Don't retry business validation errors

The advanced CQRS handlers provide enterprise-grade resilience for command processing, handling transient failures and concurrency conflicts automatically.
