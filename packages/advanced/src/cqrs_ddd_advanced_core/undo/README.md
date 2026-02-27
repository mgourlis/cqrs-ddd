# Undo/Redo Service — Command Reversal

**Reversible command execution** with full undo/redo support.

---

## Overview

The **Undo Service** provides a robust framework for making commands reversible. It enables:
- ✅ Undo any command that supports reversal
- ✅ Redo previously undone commands
- ✅ Track undo/redo history per aggregate
- ✅ Compose undo executors for complex commands

```
┌────────────────────────────────────────────────────────────────┐
│               UNDO/REDO FLOW                                   │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  User executes command                                         │
│  ┌──────────────────────────────────────────┐                  │
│  │ AddItemToOrder                           │                  │
│  │ - order_id: "order_123"                 │                  │
│  │ - item: "Widget"                        │                  │
│  │ - price: $50.00                         │                  │
│  └───────────┬──────────────────────────────┘                  │
│              │                                                 │
│              ▼                                                 │
│  Command Handler stores undo executor                          │
│  ┌──────────────────────────────────────────┐                  │
│  │ Undo Executor: RemoveItemFromOrder       │                  │
│  │ - order_id: "order_123"                 │                  │
│  │ - item: "Widget"                        │                  │
│  └───────────┬──────────────────────────────┘                  │
│              │                                                 │
│              ▼                                                 │
│  User requests UNDO                                            │
│  ┌──────────────────────────────────────────┐                  │
│  │ UndoService.undo()                       │                  │
│  │ → Executes RemoveItemFromOrder           │                  │
│  └───────────┬──────────────────────────────┘                  │
│              │                                                 │
│              ▼                                                 │
│  Item removed, command stored for REDO                         │
│  ┌──────────────────────────────────────────┐                  │
│  │ Redo Executor: AddItemToOrder            │                  │
│  │ - order_id: "order_123"                 │                  │
│  │ - item: "Widget"                        │                  │
│  │ - price: $50.00                         │                  │
│  └──────────────────────────────────────────┘                  │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## Key Benefits

| Benefit | Description |
|---------|-------------|
| **User-Friendly** | Allow users to reverse mistakes |
| **Safe** | Validate undo/redo operations before execution |
| **Traceable** | Full audit trail of all changes |
| **Composable** | Build complex undo operations from simple executors |
| **Aggregate-Scoped** | Undo/redo history tracked per aggregate |

---

## Quick Start

### 1. Define Undoable Command

```python
from cqrs_ddd_advanced_core.cqrs import Command

class AddItemToOrder(Command):
    """Command to add item to order."""
    order_id: str
    item: str
    price: Decimal
```

### 2. Create Command Handler with Undo Support

```python
from cqrs_ddd_advanced_core.cqrs import CommandHandler
from cqrs_ddd_advanced_core.undo import UndoExecutor

class AddItemToOrderHandler(CommandHandler):
    """Handler with undo support."""

    async def handle(self, command: AddItemToOrder) -> UndoExecutor:
        # Execute command
        order = await self.order_repo.get(command.order_id)
        order.add_item(command.item, command.price)
        await self.order_repo.save(order)

        # Return undo executor
        return RemoveItemFromOrderExecutor(
            order_id=command.order_id,
            item=command.item,
        )
```

### 3. Define Undo Executor

```python
from cqrs_ddd_advanced_core.undo import UndoExecutor

class RemoveItemFromOrderExecutor(UndoExecutor):
    """Executor to remove item from order."""

    order_id: str
    item: str

    async def execute(self) -> Command:
        """Execute undo: remove item."""
        order = await self.order_repo.get(self.order_id)
        order.remove_item(self.item)
        await self.order_repo.save(order)

        # Return redo executor
        return AddItemToOrderExecutor(
            order_id=self.order_id,
            item=self.item,
            price=order.get_item_price(self.item),
        )
```

### 4. Use UndoService

```python
from cqrs_ddd_advanced_core.undo import UndoService

# Setup undo service
undo_service = UndoService(
    command_bus=command_bus,
    executor_registry=executor_registry,
)

# Execute command with undo support
undo_token = await undo_service.execute(
    AddItemToOrder(
        order_id="order_123",
        item="Widget",
        price=Decimal("50.00"),
    ),
)

# Undo command
await undo_service.undo(undo_token)

# Redo command
await undo_service.redo(undo_token)
```

---

## Architecture

### UndoExecutor

Base class for all undo operations. Each executor:
1. Executes the undo operation
2. Returns a redo executor (to reverse the undo)

```python
from cqrs_ddd_advanced_core.undo import UndoExecutor

class UndoExecutor:
    """Base class for undo executors."""

    async def execute(self) -> Command | None:
        """Execute undo and return redo command."""
        raise NotImplementedError

    async def validate(self) -> bool:
        """Validate if undo is possible."""
        return True
```

### UndoToken

Tracks a reversible command and its undo/redo state:

```python
from cqrs_ddd_advanced_core.undo import UndoToken

token = UndoToken(
    token_id="undo_123",
    aggregate_id="order_123",
    command_type="AddItemToOrder",
    executor=RemoveItemFromOrderExecutor(...),
    created_at=datetime.now(timezone.utc),
    status="pending",  # pending, undone, redone
)
```

### ExecutorRegistry

Registry for undo executors with dependency injection:

```python
from cqrs_ddd_advanced_core.undo import ExecutorRegistry

registry = ExecutorRegistry()

# Register executor with dependencies
registry.register(
    executor_type=RemoveItemFromOrderExecutor,
    dependencies={
        "order_repo": order_repository,
        "logger": logger,
    },
)

# Create executor instance
executor = registry.create(
    RemoveItemFromOrderExecutor,
    order_id="order_123",
    item="Widget",
)
```

---

## Usage Patterns

### Pattern 1: Simple Command Undo

```python
# Command
class ShipOrder(Command):
    order_id: str
    tracking_number: str

# Handler
class ShipOrderHandler(CommandHandler):
    async def handle(self, command: ShipOrder) -> UndoExecutor:
        order = await self.order_repo.get(command.order_id)
        previous_status = order.status
        order.ship(command.tracking_number)
        await self.order_repo.save(order)

        # Return undo executor
        return UnshipOrderExecutor(
            order_id=command.order_id,
            previous_status=previous_status,
        )

# Undo Executor
class UnshipOrderExecutor(UndoExecutor):
    order_id: str
    previous_status: str

    async def execute(self) -> Command:
        order = await self.order_repo.get(self.order_id)
        order.unship(self.previous_status)
        await self.order_repo.save(order)

        # Return redo command
        return ShipOrder(
            order_id=self.order_id,
            tracking_number=order.tracking_number,
        )
```

### Pattern 2: Multi-Step Undo

```python
# Complex command with multiple undo steps
class CreateOrderWithItems(Command):
    order_id: str
    customer_id: str
    items: list[dict]

class CreateOrderWithItemsHandler(CommandHandler):
    async def handle(self, command: CreateOrderWithItems):
        # Create order
        order = Order.create(command.order_id, command.customer_id)

        # Add items
        for item in command.items:
            order.add_item(item["name"], item["price"])

        await self.order_repo.save(order)

        # Return composite undo executor
        return CompositeUndoExecutor(
            executors=[
                DeleteOrderExecutor(order_id=command.order_id),
            ]
        )

class CompositeUndoExecutor(UndoExecutor):
    """Execute multiple undo operations in sequence."""

    executors: list[UndoExecutor]

    async def execute(self) -> Command | None:
        redo_executors = []

        # Execute all undo operations
        for executor in reversed(self.executors):
            redo = await executor.execute()
            if redo:
                redo_executors.append(redo)

        # Return composite redo
        return CompositeRedoCommand(executors=redo_executors)
```

### Pattern 3: Conditional Undo

```python
class CancelOrderExecutor(UndoExecutor):
    """Executor to cancel order, but only if not shipped."""

    order_id: str

    async def validate(self) -> bool:
        """Can only cancel if order not shipped."""
        order = await self.order_repo.get(self.order_id)
        return order.status != OrderStatus.SHIPPED

    async def execute(self) -> Command:
        if not await self.validate():
            raise UndoNotPossibleError("Order already shipped")

        order = await self.order_repo.get(self.order_id)
        previous_status = order.status
        order.cancel()
        await self.order_repo.save(order)

        return UncancelOrderExecutor(
            order_id=self.order_id,
            previous_status=previous_status,
        )
```

### Pattern 4: Undo with Compensation

```python
class ChargeCreditCardExecutor(UndoExecutor):
    """Undo credit card charge with refund."""

    order_id: str
    amount: Decimal
    charge_id: str

    async def execute(self) -> Command:
        # Refund the charge
        refund_id = await self.payment_service.refund(
            charge_id=self.charge_id,
            amount=self.amount,
        )

        # Return redo command (recharge)
        return RechargeCreditCardExecutor(
            order_id=self.order_id,
            amount=self.amount,
            refund_id=refund_id,
        )

class RechargeCreditCardExecutor(UndoExecutor):
    """Redo credit card charge after refund."""

    order_id: str
    amount: Decimal
    refund_id: str

    async def execute(self) -> Command:
        # Charge again
        charge_id = await self.payment_service.charge(
            customer_id=self.customer_id,
            amount=self.amount,
        )

        # Return undo command (refund again)
        return ChargeCreditCardExecutor(
            order_id=self.order_id,
            amount=self.amount,
            charge_id=charge_id,
        )
```

---

## Integration

### With Command Bus

```python
from cqrs_ddd_advanced_core.cqrs import CommandBus
from cqrs_ddd_advanced_core.undo import UndoService

# Setup command bus
command_bus = CommandBus()
command_bus.register(AddItemToOrder, AddItemToOrderHandler())

# Setup undo service
undo_service = UndoService(
    command_bus=command_bus,
    executor_registry=executor_registry,
)

# Execute command with undo tracking
undo_token = await undo_service.execute(
    AddItemToOrder(
        order_id="order_123",
        item="Widget",
        price=Decimal("50.00"),
    ),
)

# Later: undo
await undo_service.undo(undo_token)

# Even later: redo
await undo_service.redo(undo_token)
```

### With Aggregate Repository

```python
class UndoAwareRepository:
    """Repository that tracks undo history per aggregate."""

    def __init__(self, undo_service: UndoService):
        self.undo_service = undo_service

    async def save_with_undo(
        self,
        aggregate: AggregateRoot,
        undo_executor: UndoExecutor | None = None,
    ):
        """Save aggregate and register undo executor."""
        await self.delegate.save(aggregate)

        if undo_executor:
            await self.undo_service.register(
                aggregate_id=aggregate.id,
                executor=undo_executor,
            )
```

### With FastAPI

```python
from fastapi import FastAPI, HTTPException

app = FastAPI()

@app.post("/orders/{order_id}/items")
async def add_item(order_id: str, item: ItemDTO):
    """Add item to order with undo support."""
    undo_token = await undo_service.execute(
        AddItemToOrder(
            order_id=order_id,
            item=item.name,
            price=item.price,
        ),
    )

    return {
        "message": "Item added",
        "undo_token": undo_token.token_id,
    }

@app.post("/undo/{token_id}")
async def undo(token_id: str):
    """Undo a command."""
    try:
        await undo_service.undo_by_token_id(token_id)
        return {"message": "Undone"}
    except UndoNotPossibleError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/redo/{token_id}")
async def redo(token_id: str):
    """Redo an undone command."""
    try:
        await undo_service.redo_by_token_id(token_id)
        return {"message": "Redone"}
    except RedoNotPossibleError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

---

## Storage

### Undo History Storage

Undo tokens are persisted in a dedicated `undo_history` table:

```sql
CREATE TABLE undo_history (
    token_id VARCHAR PRIMARY KEY,
    aggregate_id VARCHAR NOT NULL,
    command_type VARCHAR NOT NULL,
    executor_type VARCHAR NOT NULL,
    executor_data JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL,
    undone_at TIMESTAMP,
    redone_at TIMESTAMP,
    status VARCHAR NOT NULL,  -- pending, undone, redone
    INDEX idx_aggregate (aggregate_id),
    INDEX idx_status (status),
);
```

### UndoStorage API

```python
from cqrs_ddd_advanced_core.undo import UndoStorage

storage = UndoStorage(session)

# Save undo token
await storage.save(undo_token)

# Load undo token
token = await storage.load("undo_123")

# Get pending tokens for aggregate
tokens = await storage.get_pending_for_aggregate("order_123")

# Mark as undone
await storage.mark_undone("undo_123")

# Mark as redone
await storage.mark_redone("undo_123")
```

---

## Best Practices

### 1. Always Return Undo Executor

```python
# ✅ GOOD: Command handler returns undo executor
class AddItemHandler(CommandHandler):
    async def handle(self, command: AddItem):
        # ... execute command ...
        return RemoveItemExecutor(...)  # Always return executor

# ❌ BAD: No undo support
class AddItemHandler(CommandHandler):
    async def handle(self, command: AddItem):
        # ... execute command ...
        return None  # Cannot undo!
```

### 2. Validate Undo Possibility

```python
class CancelOrderExecutor(UndoExecutor):
    async def validate(self) -> bool:
        """Can only cancel if not shipped."""
        order = await self.order_repo.get(self.order_id)
        return order.status in [OrderStatus.PENDING, OrderStatus.CONFIRMED]

    async def execute(self) -> Command:
        if not await self.validate():
            raise UndoNotPossibleError("Cannot cancel shipped order")

        # ... execute undo ...
```

### 3. Use Meaningful Error Messages

```python
class UndoNotPossibleError(Exception):
    """Raised when undo cannot be performed."""

    def __init__(self, token_id: str, reason: str):
        self.token_id = token_id
        self.reason = reason
        super().__init__(f"Cannot undo {token_id}: {reason}")

# Usage
raise UndoNotPossibleError(
    token_id="undo_123",
    reason="Order already shipped",
)
```

### 4. Test Undo/Redo Cycles

```python
import pytest

@pytest.mark.asyncio
async def test_add_item_undo_redo_cycle():
    """Test complete undo/redo cycle."""
    # Execute command
    undo_token = await undo_service.execute(
        AddItemToOrder(
            order_id="order_123",
            item="Widget",
            price=Decimal("50.00"),
        ),
    )

    # Verify item added
    order = await order_repo.get("order_123")
    assert len(order.items) == 1
    assert order.items[0].name == "Widget"

    # Undo
    await undo_service.undo(undo_token)

    # Verify item removed
    order = await order_repo.get("order_123")
    assert len(order.items) == 0

    # Redo
    await undo_service.redo(undo_token)

    # Verify item added again
    order = await order_repo.get("order_123")
    assert len(order.items) == 1
    assert order.items[0].name == "Widget"
```

### 5. Limit Undo History

```python
class BoundedUndoService:
    """Undo service with history limit."""

    def __init__(self, delegate: UndoService, max_history: int = 100):
        self.delegate = delegate
        self.max_history = max_history

    async def execute(self, command: Command):
        """Execute command and trim old history."""
        token = await self.delegate.execute(command)

        # Get all tokens for aggregate
        tokens = await self.storage.get_for_aggregate(command.aggregate_id)

        # Remove old tokens beyond limit
        if len(tokens) > self.max_history:
            for old_token in tokens[:-self.max_history]:
                await self.storage.delete(old_token.token_id)

        return token
```

---

## Advanced Topics

### Undo Scope Strategies

```python
class UndoScope:
    """Define scope for undo operations."""

    AGGREGATE = "aggregate"  # Undo affects only one aggregate
    TRANSACTION = "transaction"  # Undo affects entire transaction
    GLOBAL = "global"  # Undo affects multiple aggregates

class ScopedUndoService:
    """Undo service with scope awareness."""

    async def undo(self, token: UndoToken, scope: str = UndoScope.AGGREGATE):
        """Undo with specified scope."""
        if scope == UndoScope.AGGREGATE:
            await self._undo_aggregate(token)
        elif scope == UndoScope.TRANSACTION:
            await self._undo_transaction(token)
        elif scope == UndoScope.GLOBAL:
            await self._undo_global(token)
```

### Undo Policies

```python
class UndoPolicy:
    """Policy for undo behavior."""

    def __init__(
        self,
        max_age_hours: int = 24,
        max_redo_count: int = 3,
        require_validation: bool = True,
    ):
        self.max_age_hours = max_age_hours
        self.max_redo_count = max_redo_count
        self.require_validation = require_validation

    def can_undo(self, token: UndoToken) -> bool:
        """Check if token can be undone."""
        # Check age
        age = (datetime.now(timezone.utc) - token.created_at).total_seconds() / 3600
        if age > self.max_age_hours:
            return False

        # Check redo count
        if token.redo_count > self.max_redo_count:
            return False

        return True

# Usage
policy = UndoPolicy(max_age_hours=48, max_redo_count=5)
undo_service = UndoService(policy=policy)
```

---

## Summary

| Aspect | With Undo Service | Without Undo Service |
|--------|------------------|---------------------|
| **User Experience** | Excellent (reversible) | Limited (permanent) |
| **Complexity** | Moderate | Low |
| **Storage** | Extra history table | None |
| **Use Case** | User-facing operations | System operations |
| **Validation** | Built-in | Manual |

**Key Takeaways**:
- ✅ Return undo executors from command handlers
- ✅ Validate undo operations before execution
- ✅ Test complete undo/redo cycles
- ✅ Limit undo history size
- ✅ Use meaningful error messages
- ✅ Consider undo policies for business rules

The Undo Service provides **essential safety** for user-facing operations, allowing mistakes to be reversed without data loss.
