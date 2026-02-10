# Module Architecture Guide: `cqrs-ddd-core`

**Role:** The Foundation.
**Dependency Policy:** **Zero Infrastructure Dependencies.**
* **Pydantic:** **Recommended Default.** The core classes are designed to inherit from `pydantic.BaseModel` if available, offering runtime validation and schema generation.
* **Fallback:** If Pydantic is missing, classes gracefully degrade to standard Python objects or `dataclasses`.
* **Standard Lib:** `typing`, `abc`, `uuid`, `datetime`, `contextvars`.

---

## **1. Directory Structure**

```text
cqrs_ddd_core/
├── domain/                  # DDD Primitives
│   ├── aggregate.py         # AggregateRoot (Pydantic-enabled)
│   ├── events.py            # DomainEvent (Pydantic-enabled)
│   ├── value_object.py      # ValueObject (Immutable Pydantic Model)
│   └── mixins.py            # Serialization/Validation Mixins
├── cqrs/                    # CQRS Primitives
│   ├── command.py           # Command (Immutable Pydantic Model)
│   ├── query.py             # Query (Immutable Pydantic Model)
│   └── bus.py               # ICommandBus & IQueryBus Protocols
├── ports/                   # Infrastructure Interfaces (Ports)
│   ├── repository.py        # IRepository[T] Protocol
│   ├── uow.py               # IUnitOfWork Protocol
│   ├── event_store.py       # IEventStore Protocol
│   └── blob_storage.py      # IBlobStorage Protocol
├── primitives/              # Utilities
│   ├── exceptions.py        # DomainError, ConcurrencyError
│   └── result.py            # Result[T, E] Monad
└── testing/                 # Fakes for Unit Testing
    ├── memory_repo.py
    └── memory_uow.py
```

## **2. Implementation Rules**

### **A. The Hybrid Base Classes (`domain/`)**

**Strategy:** The Core must detect if `pydantic` is installed.
* **If Installed:** `AggregateRoot` and `DomainEvent` inherit from `pydantic.BaseModel`.
* **If Missing:** They fall back to standard `@dataclass` or plain objects.

**`DomainEvent`**
* **Fields:** `event_id` (UUID), `occurred_at` (UTC), `version` (int), `metadata` (dict).
* **Serialization:** Must implement a `.model_dump()` method that works regardless of the backing library.
* **Immutability:** Events should be immutable (`frozen=True` in Pydantic configuration).

**`AggregateRoot`**
* **Fields:** `id` (Generic), `_events` (Private list).
* **Validation:** Use Pydantic validators to enforce domain invariants (e.g., `price > 0`).
* **Methods:** `add_event()`, `collect_events()`, `clear_events()`.
* **Safety:** The `_events` list must be excluded from serialization (`exclude=True` or `PrivateAttr`).

### **B. CQRS Primitives (`cqrs/`)**

**`Command` & `Query`**
* **Recommendation:** These should be **Pydantic Models**.
* **Why:** They represent **external input** (API Requests). Pydantic validates this input *before* it reaches the Domain Logic.
* **Structure:**
    ```python
    class Command(BaseModel):
        model_config = ConfigDict(frozen=True)  # Commands are immutable intents
    ```

### **C. Ports / Interfaces (`ports/`)**

**`IRepository[T]`**
* **Generic:** `T` is bound to `AggregateRoot`.
* **Async:** All IO methods must be `async`.
* **Methods:** `add(entity)`, `get(id)`, `delete(id)`.

**`IUnitOfWork`**
* **Context Manager:** Must support `async with uow:`.
* **Commit/Rollback:** Must be explicit.

---

## **3. Code Prototypes (Pydantic First)**

Use these snippets to guide the agent implementation.

#### **1. The Hybrid Domain Event**
```python
# cqrs_ddd_core/domain/events.py
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

try:
    from pydantic import BaseModel, Field, ConfigDict
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False
    BaseModel = object
    Field = lambda **kwargs: None
    ConfigDict = lambda **kwargs: None

class DomainEvent(BaseModel if HAS_PYDANTIC else object):
    """
    Base class for all Domain Events.
    Recommended: Use Pydantic for automatic JSON serialization.
    """
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1
    metadata: Dict[str, Any] = Field(default_factory=dict)

    if HAS_PYDANTIC:
        model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
```

#### **2. The Aggregate Root**
```python
# cqrs_ddd_core/domain/aggregate.py
from typing import List, Any
try:
    from pydantic import BaseModel, PrivateAttr
except ImportError:
    BaseModel = object
    PrivateAttr = lambda **kwargs: None

class AggregateRoot(BaseModel):
    id: Any
    # Private attributes are not serialized by Pydantic
    _version: int = PrivateAttr(default=0)
    _domain_events: List[Any] = PrivateAttr(default_factory=list)

    def add_event(self, event: Any) -> None:
        """
        Stages an event for emission.
        Increments internal version to ensure optimistic locking.
        """
        self._domain_events.append(event)

    def collect_events(self) -> List[Any]:
        """Returns and clears staged events."""
        events = list(self._domain_events)
        self._domain_events.clear()
        return events
```

## **4. System Prompt for Agent Implementation**

> **Instruction:**
> Implement the `cqrs-ddd-core` package.
> 
> **Goal:** Create the Domain and CQRS primitives, prioritizing **Pydantic** for schema definition and validation.
> 
> **Constraints:**
> 1.  **Pydantic Support:** All base classes (`AggregateRoot`, `DomainEvent`, `Command`) must inherit from `pydantic.BaseModel` if the library is available.
> 2.  **Immutability:** Events and Commands must be immutable (`frozen=True`).
> 3.  **Interfaces:** Use `typing.Protocol` for `IRepository`, `IUnitOfWork`, `IEventStore`.
> 4.  **No Drivers:** Do not import `sqlalchemy` or `motor`.
> 5.  **Generics:** Repositories must be Generic over the Aggregate Type.
> 
> **Output:**
> 1.  `domain/events.py` (The Pydantic-enabled base class)
> 2.  `domain/aggregate.py` (The Pydantic-enabled base class with private event list)
> 3.  `cqrs/command.py` (Immutable Base Model)
> 4.  `ports/repository.py` (Protocol)
