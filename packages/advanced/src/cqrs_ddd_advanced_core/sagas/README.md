# Sagas — Long-Running Business Processes

**Process Manager pattern** with integrated TCC (Try-Confirm/Cancel) support.

---

## Overview

**Sagas** coordinate long-running business transactions that span multiple services, ensuring consistency without distributed locks or two-phase commit. This implementation provides:

- ✅ **Event-driven choreography** — sagas react to domain events automatically
- ✅ **State persistence** — saga state survives crashes and restarts
- ✅ **Idempotency** — duplicate events are safely ignored
- ✅ **Compensation** — failed operations are automatically rolled back
- ✅ **TCC pattern** — native Try-Confirm/Cancel for resource reservations
- ✅ **Recovery** — stalled sagas are automatically retried
- ✅ **Declarative API** — fluent builder for saga definition without subclassing

```
┌────────────────────────────────────────────────────────────────┐
│               SAGA LIFECYCLE                                   │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  1. Event arrives (OrderCreated)                               │
│     ┌──────────────────────────────────────────┐               │
│     │ EventDispatcher                          │               │
│     │ → SagaManager.handle(event)             │               │
│     └───────────┬──────────────────────────────┘               │
│                 │                                              │
│                 ▼                                              │
│  2. Load/Create saga state                                     │
│     ┌──────────────────────────────────────────┐               │
│     │ SagaRepository.find_by_correlation_id() │               │
│     │ → Create if not exists                   │               │
│     └───────────┬──────────────────────────────┘               │
│                 │                                              │
│                 ▼                                              │
│  3. Handle event (idempotent)                                  │
│     ┌──────────────────────────────────────────┐               │
│     │ saga.handle(event)                       │               │
│     │ → Check if event already processed       │               │
│     │ → Execute handler                        │               │
│     │ → Queue commands for dispatch            │               │
│     └───────────┬──────────────────────────────┘               │
│                 │                                              │
│                 ▼                                              │
│  4. Persist state + commands                                   │
│     ┌──────────────────────────────────────────┐               │
│     │ Save state with pending_commands        │               │
│     │ (crash-safety: commands persisted)       │               │
│     └───────────┬──────────────────────────────┘               │
│                 │                                              │
│                 ▼                                              │
│  5. Dispatch commands (transactional)                          │
│     ┌──────────────────────────────────────────┐               │
│     │ For each command:                        │               │
│     │   → Send via command bus                 │               │
│     │   → Mark dispatched = True               │               │
│     │   → Save state                           │               │
│     └───────────┬──────────────────────────────┘               │
│                 │                                              │
│                 ▼                                              │
│  6. Clear dispatched commands                                  │
│     ┌──────────────────────────────────────────┐               │
│     │ Save final state                         │               │
│     │ Saga status: RUNNING / COMPLETED / ...   │               │
│     └──────────────────────────────────────────┘               │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## Key Benefits

| Benefit | Description |
|---------|-------------|
| **Consistency** | Eventually consistent transactions across services |
| **Resilience** | Automatic recovery from crashes, timeouts, and failures |
| **Observability** | Full audit trail of saga lifecycle and steps |
| **Flexibility** | Support for choreography (events) and orchestration (explicit) |
| **Testability** | In-memory repository for unit testing |
| **Zero Boilerplate** | Declarative builder eliminates repetitive code |

---

## Quick Start

### 1. Bootstrap Complete Saga Infrastructure

The **recommended entry point** — sets up all components in one call:

```python
from cqrs_ddd_advanced_core.sagas import bootstrap_sagas
from cqrs_ddd_advanced_core.sagas.builder import SagaBuilder

# Define saga declaratively (no subclassing needed)
OrderSaga = (
    SagaBuilder("OrderFulfillment")
    .on(OrderCreated,
        send=lambda e: ReserveItems(order_id=e.order_id),
        step="reserving",
        compensate=lambda e: CancelReservation(order_id=e.order_id))
    .on(ItemsReserved,
        send=lambda e: ChargePayment(order_id=e.order_id),
        step="charging")
    .on(PaymentCharged,
        send=lambda e: ConfirmOrder(order_id=e.order_id),
        step="confirming",
        complete=True)
    .on(ReservationFailed,
        fail="Inventory unavailable")
    .on(PaymentDeclined,
        fail="Payment declined")
    .build()
)

# Bootstrap everything
result = bootstrap_sagas(
    sagas=[OrderSaga],
    repository=saga_repo,
    command_bus=mediator,
    message_registry=msg_registry,
    event_dispatcher=event_dispatcher,  # Auto-bind events
    recovery_interval=60,  # Recovery worker polls every 60s
)

# Start background recovery worker (handles stalls/timeouts)
await result.worker.start()

# Done! Events auto-route to sagas
```

**What `bootstrap_sagas` sets up**:
1. ✅ Registers sagas in `SagaRegistry` (reads `listened_events()` from each class)
2. ✅ Creates `SagaManager` with repository, registry, command bus
3. ✅ Binds manager to `EventDispatcher` (all saga events auto-routed)
4. ✅ Creates `SagaRecoveryWorker` for background timeout/recovery (if `recovery_interval` set)
5. ✅ Wires recovery trigger to manager (stalled sagas wake worker immediately)

---

## Architecture

### Core Components

```
┌────────────────────────────────────────────────────────────────┐
│                    SAGA ARCHITECTURE                           │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  EventDispatcher (from cqrs_ddd_core)                         │
│       │                                                        │
│       │ (auto-bound)                                          │
│       ▼                                                        │
│  SagaManager                                                   │
│   ├─ SagaRepository (persistence)                             │
│   ├─ SagaRegistry (event → saga mapping)                      │
│   ├─ ICommandBus (dispatch saga commands)                     │
│   └─ MessageRegistry (serialize/deserialize commands)         │
│       │                                                        │
│       │ (load state, instantiate saga)                        │
│       ▼                                                        │
│  Saga (orchestration)                                          │
│   ├─ SagaState (persistent state, 20+ fields)                 │
│   ├─ Event handlers (registered via .on())                    │
│   ├─ Compensation stack (LIFO)                                │
│   └─ TCC steps (optional, Try-Confirm/Cancel)                 │
│                                                                │
│  SagaRecoveryWorker (background)                              │
│   ├─ Poll stalled sagas (pending commands)                    │
│   ├─ Process timeouts (suspended sagas)                       │
│   └─ Process TCC timeouts (TIME_BASED reservations)           │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### SagaState Fields (20+)

The `SagaState` aggregate tracks the complete lifecycle:

```python
class SagaState(AuditableMixin, AggregateRoot[str]):
    # Schema version
    state_version: int = 1
    
    # Identity
    saga_type: str = ""              # Saga class name
    status: SagaStatus = PENDING     # PENDING | RUNNING | SUSPENDED | COMPLETED | FAILED | COMPENSATING | COMPENSATED
    correlation_id: str | None       # Links all events in transaction
    
    # Step tracking
    current_step: str = "init"       # Current step name
    step_history: list[StepRecord]   # Full audit trail
    
    # TCC (first-class field)
    tcc_steps: list[TCCStepRecord]   # Try-Confirm/Cancel steps
    
    # Idempotency
    processed_event_ids: list[str]   # Prevent duplicate processing
    
    # Pending commands
    pending_commands: list[dict]     # Queued commands (crash-safety)
    
    # Compensation
    compensation_stack: list[CompensationRecord]  # LIFO rollback
    failed_compensations: list[dict]              # Failed rollbacks
    
    # Suspension
    suspended_at: datetime | None
    suspension_reason: str | None
    timeout_at: datetime | None      # Auto-expiry for suspended
    
    # Retries
    retry_count: int = 0
    max_retries: int = 3
    
    # Error tracking
    error: str | None
    
    # Timestamps
    completed_at: datetime | None
    failed_at: datetime | None
    created_at / updated_at  # From AuditableMixin
    
    # Metadata
    metadata: dict[str, Any]         # Custom context
```

---

## Saga Definition Styles

### Style 1: Declarative (SagaBuilder) — Recommended

**No subclassing required**. Fluent API for all features.

```python
from cqrs_ddd_advanced_core.sagas.builder import SagaBuilder

OrderSaga = (
    SagaBuilder("OrderFulfillment")
    # Configuration
    .with_state_class(OrderSagaState)
    .with_max_retries(5)
    
    # Event → Command mapping
    .on(OrderCreated,
        send=lambda e: ReserveItems(order_id=e.order_id),
        step="reserving",
        compensate=lambda e: CancelReservation(order_id=e.order_id))
    
    # Multi-command dispatch
    .on(PaymentCharged,
        send_all=lambda e: [
            ConfirmOrder(order_id=e.order_id),
            NotifyCustomer(order_id=e.order_id),
        ],
        step="confirming",
        complete=True)
    
    # Suspend for human-in-the-loop
    .on(NeedsReview,
        suspend="Manual review required",
        suspend_timeout=timedelta(hours=24))
    
    # Resume from suspension
    .on(ReviewApproved,
        send=lambda e: ContinueOrder(order_id=e.order_id),
        resume=True)
    
    # Fail saga
    .on(PaymentDeclined,
        fail="Payment permanently declined")
    
    # Custom handler for complex logic
    .on(OrderCancelled, handler=my_cancel_handler)
    
    .build()
)
```

**Benefits**:
- ✅ Zero boilerplate
- ✅ `listens_to` set automatically from `.on()` calls
- ✅ Works with `bootstrap_sagas()`
- ✅ All features accessible (TCC, compensation, suspend, etc.)

---

### Style 2: Hand-Written Subclass

For complex logic requiring full control.

```python
from cqrs_ddd_advanced_core.sagas import Saga
from cqrs_ddd_advanced_core.sagas.state import SagaState

class OrderSagaState(SagaState):
    """Custom state with additional fields."""
    items_reserved: bool = False
    payment_id: str | None = None

class OrderSaga(Saga[OrderSagaState]):
    # CRITICAL: Must declare listened events explicitly
    listens_to = [OrderCreated, ItemsReserved, PaymentCharged, OrderCancelled]
    
    state_class = OrderSagaState
    
    def __init__(self, state: OrderSagaState, message_registry=None):
        super().__init__(state, message_registry)
        
        # Register event handlers
        self.on(OrderCreated, handler=self.handle_order_created)
        self.on(ItemsReserved, send=self._send_payment, step="charging")
        self.on(PaymentCharged, handler=self.handle_payment_charged)
        self.on(OrderCancelled, handler=self.handle_cancelled)
    
    async def handle_order_created(self, event: OrderCreated):
        """Complex handler with conditional logic."""
        if self.state.items_reserved:
            # Already reserved (idempotency check)
            return
        
        self.dispatch(ReserveItems(order_id=event.order_id))
        self.add_compensation(
            CancelReservation(order_id=event.order_id),
            "Release inventory on failure",
        )
        self.state.current_step = "reserving"
    
    def _send_payment(self, event: ItemsReserved) -> ChargePayment:
        """Command factory."""
        return ChargePayment(
            order_id=event.order_id,
            amount=event.total,
        )
    
    async def handle_payment_charged(self, event: PaymentCharged):
        """Mark completed."""
        self.state.payment_id = event.payment_id
        self.dispatch(ConfirmOrder(order_id=event.order_id))
        self.complete()
    
    async def handle_cancelled(self, event: OrderCancelled):
        """Fail with compensation."""
        await self.fail(f"Order cancelled: {event.reason}", compensate=True)
    
    async def on_timeout(self):
        """Custom timeout handler."""
        # Override default behavior
        await self.fail("Order expired", compensate=True)
```

**Requirements**:
- ⚠️ **MUST** set `listens_to` class attribute (no auto-discovery from `.on()`)
- ✅ Full control over state and logic
- ✅ Works with `bootstrap_sagas()`

---

## TCC (Try-Confirm/Cancel) Pattern

**Native support** for distributed resource reservations with automatic rollback.

### TCC Phases

```
┌────────────────────────────────────────────────────────────────┐
│               TCC LIFECYCLE                                    │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  1. TRY (reserve resources)                                    │
│     ┌──────────────────────────────────────────┐               │
│     │ begin_tcc()                              │               │
│     │ → Dispatch Try commands for all steps    │               │
│     │ → Phase: TRYING                         │               │
│     └───────────┬──────────────────────────────┘               │
│                 │                                              │
│                 ▼                                              │
│  2. TRIED (reservations confirmed)                             │
│     ┌──────────────────────────────────────────┐               │
│     │ mark_step_tried(step_name)              │               │
│     │ → Phase: TRIED                          │               │
│     │ → If all steps TRIED: auto-confirm      │               │
│     └───────────┬──────────────────────────────┘               │
│                 │                                              │
│                 ▼                                              │
│  3a. CONFIRM (finalize reservations)                           │
│      ┌──────────────────────────────────────────┐              │
│      │ _dispatch_confirms() (auto)             │              │
│      │ → Dispatch Confirm commands             │              │
│      │ → Phase: CONFIRMING                     │              │
│      │ → If all CONFIRMED: saga complete       │              │
│      └──────────────────────────────────────────┘              │
│                                                                │
│  OR                                                            │
│                                                                │
│  3b. CANCEL (rollback reservations)                            │
│      ┌──────────────────────────────────────────┐              │
│      │ mark_step_failed(step_name)             │              │
│      │ → Dispatch Cancel commands (LIFO)       │              │
│      │ → Phase: CANCELLING                     │              │
│      │ → If all CANCELLED: saga compensated    │              │
│      └──────────────────────────────────────────┘              │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### Reservation Types

| Type | Behavior | Use Case |
|------|----------|----------|
| `RESOURCE` | Held indefinitely until explicit confirm/cancel | Inventory locks, seat reservations |
| `TIME_BASED` | Auto-expires after `timeout` | Payment holds, temporary blocks |

### Example: Order Fulfillment with TCC

**Using SagaBuilder (declarative)**:

```python
from cqrs_ddd_advanced_core.sagas.builder import SagaBuilder
from cqrs_ddd_advanced_core.sagas.orchestration import TCCStep
from cqrs_ddd_advanced_core.sagas.state import ReservationType
from datetime import timedelta

OrderTCCSaga = (
    SagaBuilder("OrderTCC")
    # Register TCC steps
    .with_tcc_step(TCCStep(
        name="inventory",
        try_command=ReserveInventory(order_id="order_123"),
        confirm_command=ConfirmInventory(order_id="order_123"),
        cancel_command=ReleaseInventory(order_id="order_123"),
        reservation_type=ReservationType.RESOURCE,
    ))
    .with_tcc_step(TCCStep(
        name="payment",
        try_command=HoldPayment(order_id="order_123", amount=100.00),
        confirm_command=CapturePayment(order_id="order_123"),
        cancel_command=VoidPayment(order_id="order_123"),
        reservation_type=ReservationType.TIME_BASED,
        timeout=timedelta(minutes=15),
    ))
    
    # Wire events to TCC lifecycle
    .on_tcc_begin(OrderCreated)               # OrderCreated → begin_tcc()
    .on_tcc_tried("inventory", InventoryReserved)
    .on_tcc_tried("payment", PaymentHeld)
    .on_tcc_confirmed("inventory", InventoryConfirmed)
    .on_tcc_confirmed("payment", PaymentCaptured)
    .on_tcc_failed("inventory", InventoryFailed)
    .on_tcc_failed("payment", PaymentFailed)
    .on_tcc_cancelled("inventory", InventoryReleased)
    .on_tcc_cancelled("payment", PaymentVoided)
    
    .build()
)
```

**What happens**:

1. `OrderCreated` event arrives → `begin_tcc()` dispatched automatically
2. Try commands sent: `ReserveInventory`, `HoldPayment`
3. Events arrive: `InventoryReserved`, `PaymentHeld` → `mark_step_tried()`
4. All steps TRIED → Confirm commands dispatched: `ConfirmInventory`, `CapturePayment`
5. Events arrive: `InventoryConfirmed`, `PaymentCaptured` → `mark_step_confirmed()`
6. All steps CONFIRMED → Saga completes

**On failure**:

1. `InventoryFailed` event → `mark_step_failed("inventory")`
2. Cancel commands dispatched (LIFO): `VoidPayment`, `ReleaseInventory`
3. Events arrive: `PaymentVoided`, `InventoryReleased` → `mark_step_cancelled()`
4. All steps CANCELLED → Saga compensated

**TIME_BASED timeout**:

- `SagaRecoveryWorker` polls running sagas with TCC steps
- Calls `saga.check_tcc_timeouts()`
- If `payment` step's `timeout_at` expired → auto-cancels

---

## Compensation (Rollback)

Failed sagas execute compensating commands in **LIFO order** to undo previous operations.

### Explicit Compensation Stack

```python
# Push compensation when dispatching command
saga.dispatch(ReserveItems(order_id="order_123"))
saga.add_compensation(
    CancelReservation(order_id="order_123"),
    "Release inventory on failure",
)

# Later, on failure
await saga.fail("Payment declined", compensate=True)
# → Executes CancelReservation automatically
```

### LIFO Execution Order

```
Operations:
  1. ReserveItems
  2. ChargePayment
  3. ConfirmShipment

Compensation (on failure):
  3. CancelShipment
  2. RefundPayment
  1. ReleaseItems
```

### Failed Compensations

If a compensation command fails, it's recorded in `state.failed_compensations` for manual inspection:

```python
# After saga.fail()
for failure in saga.state.failed_compensations:
    print(f"Failed compensation: {failure['command_type']}")
    print(f"Error: {failure['error']}")
```

---

## Saga Lifecycle

### Status Transitions

```
PENDING → RUNNING → COMPLETED
         ↓         ↓
      SUSPENDED  FAILED
         ↓         ↓
       RUNNING   COMPENSATING
                   ↓
                COMPENSATED
```

### Lifecycle Methods

```python
# Complete saga
saga.complete()  # → COMPLETED

# Fail with compensation
await saga.fail("Reason", compensate=True)  # → FAILED or COMPENSATED

# Suspend (human-in-the-loop)
saga.suspend("Needs review", timeout=timedelta(hours=24))  # → SUSPENDED

# Resume
saga.resume()  # → RUNNING

# Timeout (called by SagaManager)
await saga.on_timeout()  # Default: fail with compensation
```

---

## Recovery

### Stalled Sagas

Sagas with undispatched commands are automatically recovered by `SagaRecoveryWorker`:

```python
# Recovery flow:
# 1. Find sagas with pending_commands (not all dispatched)
# 2. Check retry_count < max_retries
# 3. Retry dispatching undispatched commands
# 4. Mark dispatched = True after each successful send
# 5. Clear pending_commands on success

# If retry_count >= max_retries:
# → Saga failed (terminal state)
```

### Suspended Timeouts

Sagas suspended with `timeout_at` are automatically failed:

```python
# Timeout flow:
# 1. Find suspended sagas with timeout_at <= now
# 2. Call saga.on_timeout()
# 3. Default: fail with compensation
# 4. Dispatch any queued commands
```

### TCC Timeouts

TIME_BASED TCC steps are automatically cancelled:

```python
# TCC timeout flow:
# 1. Find RUNNING sagas with tcc_steps
# 2. Call saga.check_tcc_timeouts()
# 3. For expired steps: mark_step_failed() → cancels all
# 4. Dispatch cancel commands
```

---

## Integration

### Event Dispatcher Auto-Binding

```python
# Manual binding (tedious)
event_dispatcher.register(OrderCreated, saga_manager)
event_dispatcher.register(PaymentCharged, saga_manager)
event_dispatcher.register(ShipmentConfirmed, saga_manager)
# ... dozens more

# Automatic binding (recommended)
saga_manager.bind_to(event_dispatcher)
# Reads all event types from SagaRegistry and registers
```

### Repository Implementations

Infrastructure packages provide concrete implementations:

- **SQLAlchemy**: `SQLAlchemySagaRepository` (in `cqrs-ddd-persistence-sqlalchemy`)
- **Mongo**: `MongoSagaRepository` (in `cqrs-ddd-persistence-mongo`)
- **In-Memory**: `InMemorySagaRepository` (in `cqrs-ddd-advanced-core/adapters/memory`)

```python
from cqrs_ddd_advanced_core.adapters.memory import InMemorySagaRepository

# Testing
saga_repo = InMemorySagaRepository()

# Production (SQLAlchemy)
from cqrs_ddd_persistence_sqlalchemy import SQLAlchemySagaRepository
saga_repo = SQLAlchemySagaRepository(session, saga_type="OrderSaga")
```

---

## Advanced Topics

### Custom State Classes

Add domain-specific fields to saga state:

```python
class OrderSagaState(SagaState):
    items_reserved: bool = False
    payment_id: str | None = None
    customer_id: str | None = None

# Use in saga
class OrderSaga(Saga[OrderSagaState]):
    state_class = OrderSagaState

# Or in builder
OrderSaga = (
    SagaBuilder("OrderFulfillment")
    .with_state_class(OrderSagaState)
    .on(OrderCreated, handler=lambda e, saga: setattr(saga.state, "customer_id", e.customer_id))
    .build()
)
```

### Correlation ID

All events in a saga **must** have the same `correlation_id`:

```python
# Events must include correlation_id
class OrderCreated(DomainEvent):
    order_id: str
    correlation_id: str  # Required for saga routing

# SagaManager extracts correlation_id:
# 1. event.correlation_id (attribute)
# 2. event.metadata["correlation_id"] (fallback)

# Load saga by correlation_id
state = await repo.find_by_correlation_id(
    correlation_id="tx_123",
    saga_type="OrderSaga",
)
```

### Pending Commands (Crash Safety)

Commands are persisted **before** dispatch for crash recovery:

```python
# SagaManager flow:
# 1. Collect commands from saga
# 2. Serialize and save to state.pending_commands
# 3. Save state (crash-safe: commands persisted)
# 4. Dispatch each command
# 5. Mark dispatched=True after each successful send
# 6. Save state after each dispatch (crash-safe: knows what was sent)
# 7. Clear pending_commands on completion

# On crash during dispatch:
# Recovery finds undispatched commands in state
# Retries only undispatched (dispatched=False)
```

---

## Best Practices

### 1. Use Declarative Sagas (SagaBuilder)

```python
# ✅ GOOD: Declarative, zero boilerplate
OrderSaga = (
    SagaBuilder("OrderFulfillment")
    .on(OrderCreated, send=lambda e: ReserveItems(...))
    .build()
)

# ❌ BAD: Unnecessary subclassing
class OrderSaga(Saga[SagaState]):
    listens_to = [OrderCreated]
    def __init__(self, state, msg_reg):
        super().__init__(state, msg_reg)
        self.on(OrderCreated, send=lambda e: ReserveItems(...))
```

### 2. Always Add Compensation

```python
# ✅ GOOD: Compensate every operation
saga.dispatch(ReserveItems(order_id="order_123"))
saga.add_compensation(CancelReservation(order_id="order_123"))

# ❌ BAD: No rollback on failure
saga.dispatch(ReserveItems(order_id="order_123"))
```

### 3. Use TCC for Resource Reservations

```python
# ✅ GOOD: TCC for distributed transactions
.with_tcc_step(TCCStep(
    name="inventory",
    try_command=ReserveInventory(...),
    confirm_command=ConfirmInventory(...),
    cancel_command=ReleaseInventory(...),
))

# ❌ BAD: Manual compensation is error-prone
.on(InventoryReserved, compensate=lambda e: ReleaseInventory(...))
.on(InventoryFailed, compensate=lambda e: ReleaseInventory(...))
```

### 4. Test with InMemorySagaRepository

```python
import pytest

@pytest.mark.asyncio
async def test_order_saga():
    # Setup in-memory repo
    repo = InMemorySagaRepository()
    manager = SagaManager(repo, registry, command_bus, msg_registry)
    
    # Execute saga
    event = OrderCreated(order_id="order_123", correlation_id="tx_1")
    await manager.handle(event)
    
    # Verify state
    state = await repo.find_by_correlation_id("tx_1", "OrderSaga")
    assert state.status == SagaStatus.COMPLETED
```

### 5. Bootstrap Once at Startup

```python
# ✅ GOOD: Bootstrap during app startup
async def lifespan(app: FastAPI):
    result = bootstrap_sagas(
        sagas=[OrderSaga, PaymentSaga],
        repository=saga_repo,
        command_bus=mediator,
        message_registry=msg_registry,
        event_dispatcher=event_dispatcher,
        recovery_interval=60,
    )
    await result.worker.start()
    yield
    await result.worker.stop()

app = FastAPI(lifespan=lifespan)

# ❌ BAD: Bootstrap on every request
@app.post("/orders")
async def create_order():
    result = bootstrap_sagas(...)  # Wrong!
```

---

## Summary

| Aspect | Sagas | Distributed Transaction |
|--------|-------|------------------------|
| **Consistency** | Eventual | Strong |
| **Locks** | None | Required |
| **Rollback** | Compensation | Automatic |
| **Scalability** | Excellent | Poor |
| **Complexity** | Moderate | High |
| **Use Case** | Microservices | Monolith |

**Key Takeaways**:
- ✅ Use `bootstrap_sagas()` for complete setup in one call
- ✅ Prefer `SagaBuilder` over hand-written subclasses
- ✅ Always add compensation for rollback
- ✅ Use TCC for distributed resource reservations
- ✅ Ensure events have `correlation_id` for routing
- ✅ Test with `InMemorySagaRepository`
- ✅ Let `SagaRecoveryWorker` handle stalls and timeouts

Sagas provide **eventual consistency** for distributed transactions with automatic compensation and recovery.
