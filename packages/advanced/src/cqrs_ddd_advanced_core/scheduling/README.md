# Command Scheduling — Delayed Command Execution

**Schedule commands for future execution** with background worker support.

---

## Overview

The **Command Scheduler** enables scheduling commands to be executed at a future time. This is essential for:

- ✅ **Time-based business rules** — "Cancel unpaid orders after 30 minutes"
- ✅ **Reminder systems** — "Send payment reminder in 24 hours"
- ✅ **Retry with delay** — "Retry failed payment in 5 minutes"
- ✅ **Deferred processing** — "Process order after maintenance window"

```
┌────────────────────────────────────────────────────────────────┐
│            COMMAND SCHEDULING ARCHITECTURE                     │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Application schedules command                                 │
│  ┌──────────────────────────────────────────┐                  │
│  │ await scheduler.schedule(                │                  │
│  │     command=SendReminder(...),           │                  │
│  │     execute_at=datetime.now() + timedelta(hours=24),       │
│  │ )                                         │                  │
│  └───────────┬──────────────────────────────┘                  │
│              │                                                 │
│              ▼                                                 │
│  Command stored in scheduler                                   │
│  ┌──────────────────────────────────────────┐                  │
│  │ scheduled_commands table:                │                  │
│  │ - schedule_id: "sched_123"               │                  │
│  │ - command: SendReminder(...)             │                  │
│  │ - execute_at: 2026-02-22 10:00:00        │                  │
│  │ - status: "pending"                      │                  │
│  └───────────┬──────────────────────────────┘                  │
│              │                                                 │
│              ▼                                                 │
│  Background worker polls (or triggered)                        │
│  ┌──────────────────────────────────────────┐                  │
│  │ CommandSchedulerWorker                    │                  │
│  │ → process_due_commands()                 │                  │
│  │ → Get commands where execute_at <= now   │                  │
│  │ → Dispatch via mediator                  │                  │
│  │ → Delete executed commands               │                  │
│  └───────────┬──────────────────────────────┘                  │
│              │                                                 │
│              ▼                                                 │
│  Command dispatched to handlers                                │
│  ┌──────────────────────────────────────────┐                  │
│  │ Mediator.send(SendReminder(...))         │                  │
│  │ → Handler executes                       │                  │
│  │ → Business logic runs                    │                  │
│  └──────────────────────────────────────────┘                  │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## Key Benefits

| Benefit | Description |
|---------|-------------|
| **Delayed Execution** | Schedule commands for future execution |
| **Reliability** | Commands persisted, survive crashes |
| **Background Processing** | Worker automatically processes due commands |
| **Reactive Triggers** | Wake worker immediately when commands scheduled |
| **Observability** | Hooks for monitoring and metrics |

---

## Components

### 1. ICommandScheduler (Port)

**Port** for scheduling persistence — implemented by infrastructure packages.

```python
from cqrs_ddd_advanced_core.ports.scheduling import ICommandScheduler

class ICommandScheduler(Protocol):
    """Port for command scheduling persistence."""

    async def schedule(
        self,
        command: Command[Any],
        execute_at: datetime,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Schedule a command for future execution.

        Returns:
            Schedule ID for tracking/cancellation.
        """
        ...

    async def get_due_commands(self) -> list[tuple[str, Command[Any]]]:
        """Get all commands ready for execution.

        Returns:
            List of (schedule_id, command) tuples.
        """
        ...

    async def delete_executed(self, schedule_id: str) -> None:
        """Delete an executed command."""
        ...

    async def cancel(self, schedule_id: str) -> bool:
        """Cancel a scheduled command.

        Returns:
            True if cancelled, False if not found or already executed.
        """
        ...
```

**Implementations**:
- **SQLAlchemy**: `SQLAlchemyCommandScheduler` (in `cqrs-ddd-persistence-sqlalchemy`)
- **Mongo**: `MongoCommandScheduler` (in `cqrs-ddd-persistence-mongo`)
- **In-Memory**: `InMemoryCommandScheduler` (in `cqrs-ddd-advanced-core/adapters/memory`)

---

### 2. CommandSchedulerService

**Service** that coordinates scheduling and dispatch.

```python
from cqrs_ddd_advanced_core.scheduling import CommandSchedulerService
from cqrs_ddd_persistence_sqlalchemy import SQLAlchemyCommandScheduler

# Setup scheduler (infrastructure)
scheduler = SQLAlchemyCommandScheduler(session)

# Setup service
service = CommandSchedulerService(
    scheduler=scheduler,
    mediator_send_fn=mediator.send,  # Function to dispatch commands
)

# Schedule command
schedule_id = await scheduler.schedule(
    command=SendPaymentReminder(order_id="order_123"),
    execute_at=datetime.now(timezone.utc) + timedelta(hours=24),
)

# Process due commands (called by worker)
count = await service.process_due_commands()
# Returns number of commands dispatched
```

**API**:

| Method | Description |
|--------|-------------|
| `process_due_commands() → int` | Dispatch all due commands, return count |

**Internal Flow** (called by worker):

1. Get due commands from scheduler
2. For each command:
   - Dispatch via mediator
   - Delete from scheduler
3. Return count of dispatched commands

---

### 3. CommandSchedulerWorker

**Background worker** that automatically processes due commands.

```python
from cqrs_ddd_advanced_core.scheduling import CommandSchedulerWorker

# Setup worker
worker = CommandSchedulerWorker(
    service=service,
    poll_interval=60.0,  # Poll every 60 seconds
)

# Start background processing
await worker.start()

# Trigger immediate processing (e.g., when command scheduled)
worker.trigger()

# Stop worker
await worker.stop()
```

**API**:

| Method | Description |
|--------|-------------|
| `start() → None` | Start background polling |
| `stop() → None` | Stop background polling |
| `trigger() → None` | Wake worker immediately |
| `run_once() → int` | Execute single cycle (for testing) |

**Reactive Pattern**:

The worker uses **trigger + polling fallback** (same as outbox worker):

```python
# Normal flow: Poll every N seconds
await asyncio.wait_for(trigger.wait(), timeout=poll_interval)

# When command scheduled: Immediate wake
worker.trigger()  # Wakes immediately, no need to wait for poll
```

---

## Usage Examples

### Example 1: Schedule Payment Reminder

```python
from datetime import datetime, timedelta, timezone
from cqrs_ddd_advanced_core.scheduling import CommandSchedulerService

async def create_order(command: CreateOrder, scheduler: CommandSchedulerService):
    # Create order
    order = Order.create(command.order_id, command.customer_id)
    await order_repo.save(order)

    # Schedule reminder in 24 hours
    await scheduler._scheduler.schedule(
        command=SendPaymentReminder(order_id=order.id),
        execute_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
```

### Example 2: Auto-Cancel Unpaid Orders

```python
from cqrs_ddd_advanced_core.scheduling import CommandSchedulerService

async def handle_order_created(event: OrderCreated, scheduler: CommandSchedulerService):
    # Schedule auto-cancel in 30 minutes
    schedule_id = await scheduler._scheduler.schedule(
        command=CancelUnpaidOrder(order_id=event.order_id),
        execute_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        metadata={"reason": "auto_cancel_unpaid"},
    )

    # Store schedule_id in case we need to cancel
    order = await order_repo.get(event.order_id)
    order.auto_cancel_schedule_id = schedule_id
    await order_repo.save(order)

async def handle_order_paid(event: OrderPaid, scheduler: ICommandScheduler):
    # Cancel auto-cancel when order is paid
    order = await order_repo.get(event.order_id)

    if order.auto_cancel_schedule_id:
        await scheduler.cancel(order.auto_cancel_schedule_id)
        order.auto_cancel_schedule_id = None
        await order_repo.save(order)
```

### Example 3: Retry Failed Payment

```python
async def handle_payment_failed(event: PaymentFailed, scheduler: ICommandScheduler):
    if event.retry_count < 3:
        # Schedule retry in 5 minutes
        await scheduler.schedule(
            command=RetryPayment(
                order_id=event.order_id,
                retry_count=event.retry_count + 1,
            ),
            execute_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
    else:
        # Max retries exceeded, cancel order
        await mediator.send(CancelOrder(order_id=event.order_id))
```

---

## Integration with FastAPI

### Lifespan Setup

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from cqrs_ddd_advanced_core.scheduling import (
    CommandSchedulerService,
    CommandSchedulerWorker,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup scheduler
    scheduler = SQLAlchemyCommandScheduler(session)
    service = CommandSchedulerService(scheduler, mediator.send)

    # Setup worker
    worker = CommandSchedulerWorker(service, poll_interval=60.0)

    # Start worker
    await worker.start()

    yield

    # Stop worker
    await worker.stop()

app = FastAPI(lifespan=lifespan)
```

### Trigger on Schedule

```python
from fastapi import Depends

async def get_scheduler_worker():
    return app.state.scheduler_worker

@app.post("/orders")
async def create_order(
    command: CreateOrder,
    worker: CommandSchedulerWorker = Depends(get_scheduler_worker),
):
    # Create order and schedule command
    schedule_id = await scheduler.schedule(
        command=SendReminder(order_id=command.order_id),
        execute_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )

    # Wake worker immediately (no need to wait for poll)
    worker.trigger()

    return {"schedule_id": schedule_id}
```

---

## Storage Schema

### SQLAlchemy Schema

```sql
CREATE TABLE scheduled_commands (
    schedule_id VARCHAR PRIMARY KEY,
    command_type VARCHAR NOT NULL,
    command_module VARCHAR NOT NULL,
    command_data JSONB NOT NULL,
    execute_at TIMESTAMP NOT NULL,
    status VARCHAR NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL,
    metadata JSONB,
    INDEX idx_execute_at (execute_at),
    INDEX idx_status (status),
);
```

### Mongo Schema

```javascript
{
    "_id": "sched_123",
    "command_type": "SendPaymentReminder",
    "command_module": "myapp.commands",
    "command_data": {
        "order_id": "order_123",
        // ... command fields
    },
    "execute_at": ISODate("2026-02-22T10:00:00Z"),
    "status": "pending",
    "created_at": ISODate("2026-02-21T10:00:00Z"),
    "metadata": {
        "reason": "auto_reminder"
    }
}
```

---

## Observability Hooks

The scheduler fires hooks for monitoring:

```python
from cqrs_ddd_core.instrumentation import get_hook_registry

registry = get_hook_registry()

# Register hook for scheduler events
@registry.hook
async def monitor_scheduler(operation: str, attrs: dict):
    if operation.startswith("scheduler."):
        print(f"Scheduler: {operation}")
        print(f"  Correlation ID: {attrs.get('correlation_id')}")
        print(f"  Command Type: {attrs.get('command.type')}")
        print(f"  Schedule ID: {attrs.get('schedule.id')}")

# Hook operations:
# - scheduler.dispatch.batch       — Batch processing cycle
# - scheduler.dispatch.<CommandType> — Individual command dispatch
# - scheduler.worker.process        — Worker cycle
```

---

## Best Practices

### 1. Use Timezone-Aware Datetimes

```python
from datetime import datetime, timezone

# ✅ GOOD: Timezone-aware
execute_at = datetime.now(timezone.utc) + timedelta(hours=24)

# ❌ BAD: Naive datetime (timezone issues)
execute_at = datetime.now() + timedelta(hours=24)
```

### 2. Store Schedule ID for Cancellation

```python
# ✅ GOOD: Store ID for later cancellation
schedule_id = await scheduler.schedule(...)
order.reminder_schedule_id = schedule_id

# Later, cancel if needed
await scheduler.cancel(order.reminder_schedule_id)

# ❌ BAD: No way to cancel
await scheduler.schedule(...)
```

### 3. Use Metadata for Context

```python
# ✅ GOOD: Add metadata for tracking
await scheduler.schedule(
    command=CancelOrder(order_id="order_123"),
    execute_at=execute_at,
    metadata={
        "reason": "auto_cancel_unpaid",
        "triggered_by": "order_created",
        "correlation_id": correlation_id,
    },
)
```

### 4. Trigger Worker After Scheduling

```python
# ✅ GOOD: Immediate processing
await scheduler.schedule(...)
worker.trigger()  # Wake worker now

# ❌ BAD: Wait for next poll (up to 60s)
await scheduler.schedule(...)
# Worker will process eventually...
```

### 5. Test with InMemoryCommandScheduler

```python
import pytest
from cqrs_ddd_advanced_core.adapters.memory import InMemoryCommandScheduler

@pytest.mark.asyncio
async def test_scheduled_reminder():
    # Setup in-memory scheduler
    scheduler = InMemoryCommandScheduler()
    service = CommandSchedulerService(scheduler, mock_mediator_send)

    # Schedule command
    schedule_id = await scheduler.schedule(
        command=SendReminder(order_id="order_123"),
        execute_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    # Verify scheduled
    due = await scheduler.get_due_commands()
    assert len(due) == 0  # Not due yet

    # Fast-forward time (mock datetime)
    # ... or use testable implementation
```

---

## Advanced Topics

### Custom Scheduling Policies

Implement custom logic for scheduling decisions:

```python
class SmartScheduler:
    """Scheduler with business hours awareness."""

    def __init__(self, delegate: ICommandScheduler):
        self.delegate = delegate

    async def schedule(
        self,
        command: Command[Any],
        execute_at: datetime,
        **kwargs: Any,
    ) -> str:
        # Skip weekends
        if execute_at.weekday() >= 5:
            # Move to Monday
            days_until_monday = 7 - execute_at.weekday()
            execute_at += timedelta(days=days_until_monday)

        # Skip non-business hours
        if execute_at.hour < 9:
            execute_at = execute_at.replace(hour=9, minute=0, second=0)
        elif execute_at.hour >= 17:
            # Move to next business day
            execute_at += timedelta(days=1)
            execute_at = execute_at.replace(hour=9, minute=0, second=0)

        return await self.delegate.schedule(command, execute_at, **kwargs)
```

### Idempotency

Schedule commands with idempotency keys:

```python
# Use schedule_id as idempotency key
schedule_id = f"reminder:{order_id}:{reminder_type}"

# Check if already scheduled
existing = await scheduler.get(schedule_id)
if existing:
    return existing  # Already scheduled

await scheduler.schedule(
    command=SendReminder(order_id=order_id),
    execute_at=execute_at,
    metadata={"idempotency_key": schedule_id},
)
```

---

## Summary

| Component | Purpose | Required? |
|-----------|---------|-----------|
| `ICommandScheduler` | Persistence port for scheduled commands | Yes (from infrastructure) |
| `CommandSchedulerService` | Coordinate scheduling and dispatch | Yes |
| `CommandSchedulerWorker` | Background processing of due commands | Optional (manual processing possible) |

**Key Takeaways**:
- ✅ Use **scheduler** for time-based business rules
- ✅ **Store schedule IDs** for cancellation capability
- ✅ Use **timezone-aware datetimes** (UTC)
- ✅ **Trigger worker** after scheduling for immediate processing
- ✅ Add **metadata** for tracking and debugging
- ✅ **Test with InMemoryCommandScheduler**
- ✅ **Monitor with hooks** for observability

Command scheduling enables **reliable delayed execution** for business workflows.
