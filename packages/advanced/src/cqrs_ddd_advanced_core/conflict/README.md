# Conflict Resolution — Merge Strategies for Concurrent Edits

**Smart conflict resolution** for optimistic concurrency scenarios.

---

## Overview

When multiple users or services edit the same aggregate concurrently, **optimistic concurrency** detects conflicts. This module provides **merge strategies** to automatically resolve conflicts instead of rejecting the later update.

```
┌────────────────────────────────────────────────────────────────┐
│            OPTIMISTIC CONCURRENCY WITH MERGE                   │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  User A loads Order (v1)                                       │
│  ┌──────────────────────────────────────────┐                  │
│  │ Order {status: "pending", items: [...]} │                  │
│  └──────────────────────────────────────────┘                  │
│                                                                │
│  User B loads Order (v1)                                       │
│  ┌──────────────────────────────────────────┐                  │
│  │ Order {status: "pending", items: [...]} │                  │
│  └──────────────────────────────────────────┘                  │
│                                                                │
│  User A updates status → "confirmed" (v2)                      │
│  User B updates items → [...] (v2) ← CONFLICT!                 │
│                                                                │
│  Without Merge: ❌ Reject User B's update                      │
│                                                                │
│  With Merge: ✅ Combine changes                                │
│  ┌──────────────────────────────────────────┐                  │
│  │ Order {status: "confirmed", items: [...]}│                  │
│  │ Merged from both updates                 │                  │
│  └──────────────────────────────────────────┘                  │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## Key Benefits

| Benefit | Description |
|---------|-------------|
| **Automatic Resolution** | Merge concurrent changes without user intervention |
| **Data Preservation** | Keep both sets of changes when possible |
| **Flexibility** | Choose strategy per aggregate or field |
| **Composability** | Stack strategies for complex scenarios |
| **Pluggable** | Implement custom merge logic |

---

## Merge Strategies

### 1. LastWinsStrategy

**Simplest strategy** — incoming change always wins.

```python
from cqrs_ddd_advanced_core.conflict import LastWinsStrategy

strategy = LastWinsStrategy()

# Existing state
existing = {"status": "pending", "items": ["A"]}

# Incoming change
incoming = {"status": "confirmed"}

# Merge
merged = strategy.merge(existing, incoming)
# Result: {"status": "confirmed"} ← incoming completely replaces existing
```

**Use When**:
- ✅ Recent updates are always correct
- ✅ No need to preserve previous state
- ✅ Simple overwrite semantics

---

### 2. FieldLevelMergeStrategy

**Top-level field merge** — merge dict fields, resolve conflicts per field.

```python
from cqrs_ddd_advanced_core.conflict import FieldLevelMergeStrategy

# Default: incoming overwrites conflicting fields
strategy = FieldLevelMergeStrategy()

existing = {"status": "pending", "items": ["A"], "total": 100}
incoming = {"status": "confirmed", "discount": 10}

merged = strategy.merge(existing, incoming)
# Result: {"status": "confirmed", "items": ["A"], "total": 100, "discount": 10}
#         ↑ overwritten        ↑ preserved    ↑ preserved      ↑ added
```

**Configuration Options**:

```python
# Ignore conflicts — existing wins for conflicting fields
strategy = FieldLevelMergeStrategy(ignore_conflicts=True)

existing = {"status": "pending", "items": ["A"]}
incoming = {"status": "confirmed", "discount": 10}

merged = strategy.merge(existing, incoming)
# Result: {"status": "pending", "items": ["A"], "discount": 10}
#         ↑ existing wins                        ↑ added

# Include only specific fields
strategy = FieldLevelMergeStrategy(include_fields={"status", "items"})

# Exclude specific fields
strategy = FieldLevelMergeStrategy(exclude_fields={"internal_id"})
```

**Use When**:
- ✅ Merge top-level dict fields
- ✅ Preserve non-conflicting fields
- ✅ Control which fields to merge

---

### 3. DeepMergeStrategy

**Recursive merge** — deeply merge nested dicts and lists.

```python
from cqrs_ddd_advanced_core.conflict import DeepMergeStrategy

strategy = DeepMergeStrategy()

existing = {
    "customer": {"name": "John", "email": "john@example.com"},
    "items": [{"id": 1, "qty": 2}],
}

incoming = {
    "customer": {"email": "new@example.com"},  # Update email
    "items": [{"id": 2, "qty": 1}],  # Replace items (default)
}

merged = strategy.merge(existing, incoming)
# Result:
# {
#     "customer": {"name": "John", "email": "new@example.com"},
#     "items": [{"id": 2, "qty": 1}]  ← replaced (not appended)
# }
```

**List Merging**:

```python
# Append lists instead of replacing
strategy = DeepMergeStrategy(append_lists=True)

existing = {"items": [{"id": 1, "qty": 2}]}
incoming = {"items": [{"id": 2, "qty": 1}]}

merged = strategy.merge(existing, incoming)
# Result: {"items": [{"id": 1, "qty": 2}, {"id": 2, "qty": 1}]}
#         ↑ appended, not replaced

# Merge lists by identity key
strategy = DeepMergeStrategy(
    append_lists=False,
    list_identity_key="id",  # Merge items with same ID
)

existing = {"items": [{"id": 1, "qty": 2, "price": 100}]}
incoming = {"items": [{"id": 1, "qty": 3}]}  # Same ID, update qty

merged = strategy.merge(existing, incoming)
# Result: {"items": [{"id": 1, "qty": 3, "price": 100}]}
#         ↑ merged by ID: qty updated, price preserved
```

**Use When**:
- ✅ Deep merge nested structures
- ✅ Merge lists by identity
- ✅ Preserve nested state

---

### 4. TimestampLastWinsStrategy

**Time-based merge** — most recent update wins.

```python
from cqrs_ddd_advanced_core.conflict import TimestampLastWinsStrategy
from datetime import datetime, timezone

strategy = TimestampLastWinsStrategy(timestamp_field="modified_at")

existing = {
    "status": "pending",
    "modified_at": datetime(2026, 2, 20, 10, 0, tzinfo=timezone.utc),
}

incoming = {
    "status": "confirmed",
    "modified_at": datetime(2026, 2, 21, 15, 0, tzinfo=timezone.utc),
}

merged = strategy.merge(existing, incoming)
# Result: incoming wins (later timestamp)
# {"status": "confirmed", "modified_at": ...}
```

**Configuration Options**:

```python
# Custom timestamp extractor
def get_timestamp(obj: Any) -> datetime | None:
    return obj.updated_at if hasattr(obj, "updated_at") else None

strategy = TimestampLastWinsStrategy(timestamp_field=get_timestamp)

# Fallback to incoming if no timestamp
strategy = TimestampLastWinsStrategy(
    timestamp_field="modified_at",
    fallback_to_incoming=True,
)
```

**Use When**:
- ✅ Entities have timestamp fields
- ✅ Most recent update is correct
- ✅ Natural temporal ordering

---

### 5. UnionListMergeStrategy

**List union** — merge lists by deduplicating items.

```python
from cqrs_ddd_advanced_core.conflict import UnionListMergeStrategy

# Deduplicate by identity key
strategy = UnionListMergeStrategy(identity_key="id")

existing = {"items": [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]}
incoming = {"items": [{"id": 2, "name": "B Updated"}, {"id": 3, "name": "C"}]}

merged = strategy.merge(existing, incoming)
# Result: {"items": [
#     {"id": 1, "name": "A"},
#     {"id": 2, "name": "B Updated"},  ← incoming wins for same ID
#     {"id": 3, "name": "C"},
# ]}
```

**Without Identity Key**:

```python
# Strict set union for hashable items
strategy = UnionListMergeStrategy(identity_key=None)

existing = {"tags": ["urgent", "customer"]}
incoming = {"tags": ["customer", "vip"]}

merged = strategy.merge(existing, incoming)
# Result: {"tags": ["urgent", "customer", "vip"]}
#         ↑ deduplicated (customer appears once)
```

**Use When**:
- ✅ Merge lists without duplicates
- ✅ Combine additions from both sides
- ✅ Incoming wins for duplicates

---

## Conflict Resolution Policy

**Enum** defining resolution policies:

```python
from cqrs_ddd_advanced_core.conflict import ConflictResolutionPolicy

class ConflictResolutionPolicy(str, Enum):
    FIRST_WINS = "FIRST_WINS"  # Reject concurrent updates
    LAST_WINS = "LAST_WINS"    # Most recent update wins
    MERGE = "MERGE"            # Use merge strategy
    CUSTOM = "CUSTOM"          # User-supplied callback
```

---

## ConflictResolver

**Wrapper** that applies a merge strategy.

```python
from cqrs_ddd_advanced_core.conflict import ConflictResolver, DeepMergeStrategy

resolver = ConflictResolver(strategy=DeepMergeStrategy())

existing = {"customer": {"name": "John"}}
incoming = {"customer": {"email": "john@example.com"}}

merged = resolver.merge(existing, incoming)
# Result: {"customer": {"name": "John", "email": "john@example.com"}}
```

**Hooks**: Fires observability hooks on merge:
- `conflict.resolve.<StrategyName>`
- `merge_strategy.apply.<StrategyName>`

---

## Merge Strategy Registry

**Registry** for looking up strategies by name.

```python
from cqrs_ddd_advanced_core.conflict import MergeStrategyRegistry

# Get stock registry with all standard strategies
registry = MergeStrategyRegistry.get_stock_registry()

# Look up strategy by name
strategy_cls = registry.get("deep")  # DeepMergeStrategy

# Create instance with config
strategy = registry.create("field", ignore_conflicts=True)

# Register custom strategy
class CustomMergeStrategy(IMergeStrategy):
    def merge(self, existing: Any, incoming: Any) -> Any:
        # Custom logic
        return incoming

registry.register("custom", CustomMergeStrategy)
```

**Stock Strategies**:

| Name | Strategy Class |
|------|----------------|
| `"last_wins"` | `LastWinsStrategy` |
| `"field"` | `FieldLevelMergeStrategy` |
| `"deep"` | `DeepMergeStrategy` |
| `"timestamp"` | `TimestampLastWinsStrategy` |
| `"union"` | `UnionListMergeStrategy` |

---

## Integration with Command Handlers

Conflict resolution is used by `ConflictCommandHandler` (see `cqrs/README.md`):

```python
from cqrs_ddd_advanced_core.cqrs import ConflictCommandHandler
from cqrs_ddd_advanced_core.conflict import DeepMergeStrategy

class UpdateOrderHandler(ConflictCommandHandler[UpdateOrder]):
    conflict_strategy = DeepMergeStrategy(append_lists=True)
    
    async def _handle_internal(self, command: UpdateOrder):
        order = await self.repo.get(command.order_id)
        order.update(command.changes)
        await self.repo.save(order)
    
    def resolve_conflict(
        self,
        existing: Order,
        incoming: dict,
    ) -> Order:
        # Merge using strategy
        merged_data = self.conflict_strategy.merge(
            existing.model_dump(),
            incoming,
        )
        return Order(**merged_data)
```

---

## Custom Merge Strategies

Implement `IMergeStrategy` interface:

```python
from cqrs_ddd_advanced_core.ports.conflict import IMergeStrategy

class PriorityBasedMergeStrategy(IMergeStrategy):
    """Merge based on field priority levels."""
    
    def __init__(self, priority_fields: dict[str, int]):
        self.priority_fields = priority_fields
    
    def merge(
        self,
        existing: dict[str, Any],
        incoming: dict[str, Any],
    ) -> dict[str, Any]:
        merged = dict(existing)
        
        for key, incoming_value in incoming.items():
            # Higher priority wins
            existing_priority = self.priority_fields.get(key, 0)
            incoming_priority = self.priority_fields.get(key, 0)
            
            if incoming_priority >= existing_priority:
                merged[key] = incoming_value
        
        return merged

# Usage
strategy = PriorityBasedMergeStrategy(
    priority_fields={"status": 10, "total": 5, "notes": 1},
)

existing = {"status": "pending", "notes": "old"}
incoming = {"status": "confirmed", "notes": "new"}

merged = strategy.merge(existing, incoming)
# Result: {"status": "confirmed", "notes": "new"}
# Both incoming fields win (higher priority for incoming)
```

---

## Best Practices

### 1. Choose Strategy Based on Data Semantics

```python
# ✅ GOOD: Timestamp for temporal data
TimestampLastWinsStrategy(timestamp_field="modified_at")

# ✅ GOOD: Deep merge for nested structures
DeepMergeStrategy(list_identity_key="id")

# ✅ GOOD: Field merge for flat objects
FieldLevelMergeStrategy(ignore_conflicts=True)

# ❌ BAD: LastWins for important data (data loss)
LastWinsStrategy()  # Overwrites everything
```

### 2. Test Merge Strategies

```python
import pytest

def test_deep_merge_strategy():
    strategy = DeepMergeStrategy(list_identity_key="id")
    
    existing = {"items": [{"id": 1, "qty": 2}]}
    incoming = {"items": [{"id": 1, "qty": 3}]}
    
    merged = strategy.merge(existing, incoming)
    
    assert merged["items"][0]["qty"] == 3  # Updated
    assert len(merged["items"]) == 1  # Not duplicated
```

### 3. Use Identity Keys for Lists

```python
# ✅ GOOD: Merge lists by identity
DeepMergeStrategy(list_identity_key="id")

# ❌ BAD: Append lists blindly (duplicates)
DeepMergeStrategy(append_lists=True)
```

### 4. Fallback for Missing Timestamps

```python
# ✅ GOOD: Handle missing timestamps
TimestampLastWinsStrategy(
    timestamp_field="modified_at",
    fallback_to_incoming=True,
)

# ❌ BAD: Crash on missing timestamp
TimestampLastWinsStrategy(timestamp_field="modified_at")
```

### 5. Document Merge Behavior

```python
class UpdateOrderHandler(ConflictCommandHandler[UpdateOrder]):
    """Update order with automatic conflict resolution.
    
    Conflict Resolution:
    - Deep merge nested structures
    - Merge lists by item ID
    - Preserve non-conflicting fields
    """
    conflict_strategy = DeepMergeStrategy(list_identity_key="id")
```

---

## Summary

| Strategy | Best For | Complexity |
|----------|----------|------------|
| `LastWinsStrategy` | Simple overwrites | Low |
| `FieldLevelMergeStrategy` | Flat dicts with field control | Low |
| `DeepMergeStrategy` | Nested structures, lists | Medium |
| `TimestampLastWinsStrategy` | Temporal data | Low |
| `UnionListMergeStrategy` | List deduplication | Low |

**Key Takeaways**:
- ✅ Use merge strategies to **automatically resolve** optimistic concurrency conflicts
- ✅ Choose strategy based on **data semantics** (temporal, nested, flat)
- ✅ Use **identity keys** for list merging to avoid duplicates
- ✅ **Test merge behavior** to ensure correctness
- ✅ Implement **custom strategies** for domain-specific merge logic
- ✅ **Document merge behavior** for team clarity

Conflict resolution **preserves data** while maintaining concurrency control.
