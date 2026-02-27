# Snapshot Strategy — Aggregate State Caching

**Optimize aggregate reconstitution** with intelligent snapshot strategies.

---

## Overview

**Snapshots** are point-in-time captures of aggregate state that reduce the number of events needed to reconstruct an aggregate. Instead of replaying thousands of events, snapshots allow the system to:
- ✅ Load aggregate from snapshot
- ✅ Apply only events after snapshot
- ✅ Dramatically improve performance

```
┌────────────────────────────────────────────────────────────────┐
│               SNAPSHOT OPTIMIZATION                            │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  WITHOUT SNAPSHOT (1000 events)                                │
│  ┌──────────────────────────────────────────┐                  │
│  │ Load all 1000 events from event store    │                  │
│  │ Replay all 1000 events                    │                  │
│  │ Time: ~5 seconds                          │                  │
│  └──────────────────────────────────────────┘                  │
│                                                                │
│  WITH SNAPSHOT (snapshot at event 950)                         │
│  ┌──────────────────────────────────────────┐                  │
│  │ Load snapshot at version 950             │                  │
│  │ Load events 951-1000 (50 events)         │                  │
│  │ Replay only 50 events                     │                  │
│  │ Time: ~250ms (20x faster!)               │                  │
│  └──────────────────────────────────────────┘                  │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## Key Benefits

| Benefit | Description |
|---------|-------------|
| **Performance** | Reduce load time by 10-100x |
| **Scalability** | Handle aggregates with millions of events |
| **Resource Efficiency** | Less CPU and memory during reconstitution |
| **Transparent** | Domain code unaware of snapshots |
| **Flexible Strategies** | Configure per aggregate type |

---

## Quick Start

### 1. Define Snapshot Strategy

```python
from cqrs_ddd_advanced_core.snapshots import EveryNEventsStrategy

# Snapshot every 100 events
strategy = EveryNEventsStrategy(frequency=100)
```

### 2. Configure Snapshot Store

```python
from cqrs_ddd_advanced_core.snapshots import SnapshotStore

snapshot_store = SnapshotStore(
    db_session=session,  # SQLAlchemy session
    strategy=strategy,
)
```

### 3. Integrate with EventSourcedLoader

```python
from cqrs_ddd_advanced_core.event_sourcing import EventSourcedLoader

loader = EventSourcedLoader(
    aggregate_type=Order,
    event_store=event_store,
    event_registry=event_registry,
    snapshot_store=snapshot_store,  # Enable snapshots
)

# Load aggregate - uses snapshot if available
order = await loader.load("order_123")
```

---

## Snapshot Strategies

### EveryNEventsStrategy

Snapshot every N events processed.

```python
from cqrs_ddd_advanced_core.snapshots import EveryNEventsStrategy

# Snapshot every 100 events
strategy = EveryNEventsStrategy(frequency=100)

# Snapshot every 50 events for critical aggregates
strategy = EveryNEventsStrategy(frequency=50)
```

**Best For**:
- ✅ Predictable snapshot intervals
- ✅ Simple to understand and configure
- ✅ Consistent performance characteristics

**Example**:

```
Event Stream:
  1, 2, 3, ..., 99, [SNAPSHOT], 101, 102, ..., 199, [SNAPSHOT], ...
                            ↑                              ↑
                      Snapshot at v100               Snapshot at v200
```

### Custom Strategies

Create custom snapshot strategies by implementing the `SnapshotStrategy` protocol.

```python
from typing import Protocol

class SnapshotStrategy(Protocol):
    """Protocol for snapshot strategies."""

    def should_snapshot(
        self,
        aggregate_id: str,
        current_version: int,
        last_snapshot_version: int | None,
    ) -> bool:
        """Determine if a snapshot should be taken."""
        ...

# Example: Time-based strategy
class TimeBasedStrategy:
    """Snapshot based on time since last snapshot."""

    def __init__(self, interval_seconds: int = 3600):
        self.interval_seconds = interval_seconds

    def should_snapshot(
        self,
        aggregate_id: str,
        current_version: int,
        last_snapshot_version: int | None,
        last_snapshot_time: datetime | None = None,
    ) -> bool:
        if last_snapshot_time is None:
            return True

        elapsed = (datetime.now(timezone.utc) - last_snapshot_time).total_seconds()
        return elapsed >= self.interval_seconds
```

### Composite Strategies

Combine multiple strategies for sophisticated snapshot logic.

```python
class CompositeSnapshotStrategy:
    """Combine multiple snapshot strategies."""

    def __init__(
        self,
        strategies: list[SnapshotStrategy],
        mode: str = "any",  # "any" or "all"
    ):
        self.strategies = strategies
        self.mode = mode

    def should_snapshot(
        self,
        aggregate_id: str,
        current_version: int,
        last_snapshot_version: int | None,
    ) -> bool:
        results = [
            strategy.should_snapshot(
                aggregate_id,
                current_version,
                last_snapshot_version,
            )
            for strategy in self.strategies
        ]

        if self.mode == "any":
            return any(results)
        else:  # "all"
            return all(results)

# Example: Snapshot every 100 events OR every hour
strategy = CompositeSnapshotStrategy(
    strategies=[
        EveryNEventsStrategy(frequency=100),
        TimeBasedStrategy(interval_seconds=3600),
    ],
    mode="any",
)
```

---

## Integration

### With EventSourcedRepository

```python
from cqrs_ddd_advanced_core.event_sourcing import (
    EventSourcedRepository,
    EventSourcedLoader,
)
from cqrs_ddd_advanced_core.snapshots import SnapshotStore, EveryNEventsStrategy

# Setup snapshot strategy
strategy = EveryNEventsStrategy(frequency=100)
snapshot_store = SnapshotStore(session, strategy)

# Create loader with snapshots
loader = EventSourcedLoader(
    aggregate_type=Order,
    event_store=event_store,
    event_registry=event_registry,
    snapshot_store=snapshot_store,
)

# Create repository with snapshot support
repo = EventSourcedRepository(
    loader=loader,
    event_store=event_store,
    snapshot_store=snapshot_store,
)

# Load - uses snapshot if available
order = await repo.get("order_123")

# Save - creates snapshot if needed
await repo.save(order)
# Snapshot created at version 100, 200, 300, ...
```

### With Projection Rebuild

```python
from cqrs_ddd_advanced_core.event_sourcing import UpcastingEventReader

# Stream events from snapshot point
async def rebuild_projection_from_snapshot(
    aggregate_id: str,
    snapshot_store: SnapshotStore,
    event_store: EventStore,
):
    # Load snapshot
    snapshot = await snapshot_store.load(aggregate_id)

    if snapshot:
        # Start from snapshot version
        start_position = snapshot.version
        # Apply snapshot state to projection
        await projection.apply_snapshot(snapshot)
    else:
        # No snapshot, start from beginning
        start_position = 0

    # Stream events after snapshot
    async for event in event_store.get_events_from_position(
        aggregate_id=aggregate_id,
        position=start_position,
    ):
        await projection.handle(event)
```

---

## Storage

### Snapshot Schema

Snapshots are stored in a dedicated `snapshots` table:

```sql
CREATE TABLE snapshots (
    aggregate_id VARCHAR PRIMARY KEY,
    aggregate_type VARCHAR NOT NULL,
    version INTEGER NOT NULL,
    state JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL,
    metadata JSONB,
    INDEX idx_aggregate_type (aggregate_type),
    INDEX idx_version (version),
);
```

### SnapshotStore API

```python
from cqrs_ddd_advanced_core.snapshots import SnapshotStore

store = SnapshotStore(session, strategy)

# Save snapshot
await store.save(
    aggregate_id="order_123",
    aggregate_type="Order",
    version=100,
    state={
        "order_id": "order_123",
        "customer_id": "cust_456",
        "items": [...],
        "total": Decimal("500.00"),
    },
    metadata={
        "created_by": "system",
        "reason": "checkpoint",
    },
)

# Load snapshot
snapshot = await store.load("order_123")
if snapshot:
    print(f"Snapshot version: {snapshot.version}")
    print(f"Snapshot state: {snapshot.state}")

# Delete snapshot (e.g., after aggregate deletion)
await store.delete("order_123")

# Get latest snapshot for aggregate type
latest = await store.get_latest_for_type("Order")
```

---

## Usage Patterns

### Pattern 1: High-Frequency Snapshots

For aggregates with complex state or expensive event replay:

```python
# Snapshot every 20 events
strategy = EveryNEventsStrategy(frequency=20)
snapshot_store = SnapshotStore(session, strategy)
```

**Best For**:
- Aggregates with complex event handlers
- Aggregates with expensive state calculations
- Real-time systems requiring fast loads

### Pattern 2: Low-Frequency Snapshots

For aggregates with simple state or cheap event replay:

```python
# Snapshot every 500 events
strategy = EveryNEventsStrategy(frequency=500)
snapshot_store = SnapshotStore(session, strategy)
```

**Best For**:
- Simple aggregates with fast event handlers
- Storage-constrained environments
- Low-frequency access patterns

### Pattern 3: Adaptive Snapshots

Different frequencies for different aggregate types:

```python
# Per-aggregate strategies
strategies = {
    "Order": EveryNEventsStrategy(frequency=50),  # Complex
    "Customer": EveryNEventsStrategy(frequency=200),  # Simple
    "Product": EveryNEventsStrategy(frequency=500),  # Read-heavy
}

class AdaptiveSnapshotStore:
    """Snapshot store with per-type strategies."""

    def __init__(
        self,
        session,
        strategies: dict[str, SnapshotStrategy],
    ):
        self.session = session
        self.strategies = strategies

    def should_snapshot(
        self,
        aggregate_type: str,
        aggregate_id: str,
        current_version: int,
        last_snapshot_version: int | None,
    ) -> bool:
        strategy = self.strategies.get(
            aggregate_type,
            EveryNEventsStrategy(frequency=100),  # Default
        )
        return strategy.should_snapshot(
            aggregate_id,
            current_version,
            last_snapshot_version,
        )
```

---

## Best Practices

### 1. Balance Frequency vs Storage

```python
# ✅ GOOD: Balance performance and storage
strategy = EveryNEventsStrategy(frequency=100)  # Reasonable

# ❌ BAD: Too frequent (excessive storage)
strategy = EveryNEventsStrategy(frequency=5)

# ❌ BAD: Too infrequent (poor performance)
strategy = EveryNEventsStrategy(frequency=10000)
```

**Guidelines**:
- **Complex aggregates**: 50-100 events
- **Simple aggregates**: 200-500 events
- **Read-heavy aggregates**: 20-50 events

### 2. Snapshot After Important Events

```python
class ImportantEventStrategy:
    """Snapshot after critical state changes."""

    def __init__(self, important_events: set[str]):
        self.important_events = important_events

    def should_snapshot(
        self,
        aggregate_id: str,
        current_version: int,
        last_snapshot_version: int | None,
        last_event_type: str | None = None,
    ) -> bool:
        # Always snapshot after important events
        if last_event_type in self.important_events:
            return True

        # Otherwise, use default frequency
        if last_snapshot_version is None:
            return True

        return (current_version - last_snapshot_version) >= 100

# Example: Snapshot after order submission
strategy = ImportantEventStrategy(
    important_events={"OrderSubmitted", "OrderCancelled"},
)
```

### 3. Test Snapshot Performance

```python
import pytest

@pytest.mark.asyncio
async def test_snapshot_performance():
    """Test snapshot improves load time."""
    # Setup aggregate with 1000 events
    order = Order.create("order_123", "cust_456")
    for i in range(1000):
        order.add_item(f"item_{i}", Decimal("10.00"))

    await repo.save(order)

    # Measure load without snapshot
    start = time.time()
    await repo.get("order_123")
    time_without_snapshot = time.time() - start

    # Create snapshot
    await snapshot_store.save(
        aggregate_id="order_123",
        aggregate_type="Order",
        version=order.version,
        state=order.to_dict(),
    )

    # Add more events after snapshot
    order = await repo.get("order_123")
    for i in range(100):
        order.add_item(f"item_{1000+i}", Decimal("10.00"))
    await repo.save(order)

    # Measure load with snapshot
    start = time.time()
    await repo.get("order_123")
    time_with_snapshot = time.time() - start

    # Assert improvement
    assert time_with_snapshot < time_without_snapshot * 0.5
```

### 4. Handle Snapshot Failures Gracefully

```python
class ResilientSnapshotStore:
    """Snapshot store with failure handling."""

    def __init__(self, delegate: SnapshotStore, logger):
        self.delegate = delegate
        self.logger = logger

    async def save(self, *args, **kwargs):
        """Save snapshot with error handling."""
        try:
            await self.delegate.save(*args, **kwargs)
        except Exception as e:
            # Log but don't fail the operation
            self.logger.error(f"Snapshot save failed: {e}")
            # Aggregate can still be loaded from events

    async def load(self, aggregate_id: str):
        """Load snapshot with fallback."""
        try:
            return await self.delegate.load(aggregate_id)
        except Exception as e:
            self.logger.warning(f"Snapshot load failed: {e}")
            # Fall back to event replay
            return None
```

### 5. Clean Up Old Snapshots

```python
class SnapshotMaintenance:
    """Snapshot cleanup and maintenance."""

    def __init__(self, snapshot_store: SnapshotStore):
        self.snapshot_store = snapshot_store

    async def cleanup_old_snapshots(self, keep_last: int = 3):
        """Keep only recent snapshots."""
        async with self.snapshot_store.session.begin():
            # Get all aggregates
            aggregates = await self.snapshot_store.list_aggregates()

            for aggregate_id in aggregates:
                # Get all snapshots for aggregate
                snapshots = await self.snapshot_store.list(aggregate_id)

                # Keep only last N
                if len(snapshots) > keep_last:
                    for snapshot in snapshots[:-keep_last]:
                        await self.snapshot_store.delete(
                            aggregate_id,
                            version=snapshot.version,
                        )
```

---

## Advanced Topics

### Snapshot Versioning

Handle snapshot schema changes with versioning:

```python
class VersionedSnapshotStore:
    """Handle snapshot schema evolution."""

    def __init__(self, session, current_schema_version: int = 1):
        self.session = session
        self.current_schema_version = current_schema_version

    async def load(self, aggregate_id: str):
        """Load snapshot with schema migration."""
        snapshot = await self._load_raw(aggregate_id)

        if not snapshot:
            return None

        # Migrate snapshot to current schema
        if snapshot.schema_version < self.current_schema_version:
            snapshot = await self._migrate_snapshot(snapshot)

        return snapshot

    async def _migrate_snapshot(self, snapshot):
        """Migrate snapshot to current schema version."""
        # Apply migrations
        if snapshot.schema_version == 1:
            snapshot = self._migrate_v1_to_v2(snapshot)
        if snapshot.schema_version == 2:
            snapshot = self._migrate_v2_to_v3(snapshot)

        # Save migrated snapshot
        await self.save(snapshot)
        return snapshot
```

### Snapshot Compression

Compress large snapshots:

```python
import gzip
import json

class CompressedSnapshotStore:
    """Snapshot store with compression."""

    def __init__(self, delegate: SnapshotStore, threshold: int = 1024):
        self.delegate = delegate
        self.threshold = threshold  # Compress if > 1KB

    async def save(self, aggregate_id: str, state: dict, **kwargs):
        """Save with compression."""
        state_bytes = json.dumps(state).encode('utf-8')

        if len(state_bytes) > self.threshold:
            state_bytes = gzip.compress(state_bytes)
            compressed = True
        else:
            compressed = False

        await self.delegate.save(
            aggregate_id,
            state=state_bytes,
            compressed=compressed,
            **kwargs,
        )

    async def load(self, aggregate_id: str):
        """Load with decompression."""
        snapshot = await self.delegate.load(aggregate_id)

        if not snapshot:
            return None

        if snapshot.compressed:
            state_bytes = gzip.decompress(snapshot.state)
        else:
            state_bytes = snapshot.state

        snapshot.state = json.loads(state_bytes.decode('utf-8'))
        return snapshot
```

---

## Summary

| Aspect | With Snapshots | Without Snapshots |
|--------|---------------|-------------------|
| **Load Time** | Fast (10-100x) | Slow (linear with events) |
| **Storage** | Extra snapshot storage | Only events |
| **Complexity** | Moderate | Simple |
| **Use Case** | Long-lived aggregates | Short-lived aggregates |
| **Event Count** | 1000+ events | < 100 events |

**Key Takeaways**:
- ✅ Use snapshots for aggregates with 100+ events
- ✅ Balance snapshot frequency vs storage cost
- ✅ Test snapshot performance gains
- ✅ Handle snapshot failures gracefully
- ✅ Clean up old snapshots periodically
- ✅ Consider custom strategies for specific needs

Snapshots are **essential for scalability** in event-sourced systems with long-lived aggregates.
