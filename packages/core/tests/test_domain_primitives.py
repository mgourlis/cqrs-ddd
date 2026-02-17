from datetime import datetime, timezone

import pytest

from cqrs_ddd_core.domain.aggregate import AggregateRoot
from cqrs_ddd_core.domain.events import DomainEvent
from cqrs_ddd_core.domain.value_object import ValueObject

# --- Test Models ---


class SomethingHappened(DomainEvent):
    message: str


class UserAccount(AggregateRoot):
    username: str
    email: str | None = None


class Money(ValueObject):
    amount: float
    currency: str


# --- Tests ---


def test_aggregate_root_event_collection() -> None:
    """Verifies that events are correctly collected and cleared."""
    user = UserAccount(id="user-1", username="alice")
    event = SomethingHappened(message="Created")

    user.add_event(event)
    events = user.collect_events()

    assert len(events) == 1
    assert events[0] == event
    assert len(user.collect_events()) == 0


def test_aggregate_root_versioning() -> None:
    """Verifies that version is incremented correctly."""
    user = UserAccount(id="user-1", username="alice")
    assert user.version == 0

    user.increment_version()
    assert user.version == 1


def test_aggregate_root_init_with_version() -> None:
    """Verifies that AggregateRoot can be initialized with a specific version."""
    user = UserAccount(id="user-1", username="alice", _version=5)
    assert user.version == 5
    assert len(user.collect_events()) == 0


def test_aggregate_root_reconstruction() -> None:
    """Verifies that AggregateRoot can be reconstructed from data."""
    data = {"id": "user-1", "username": "alice", "_version": 10}
    user = UserAccount(**data)
    assert user.id == "user-1"
    assert user.version == 10


def test_aggregate_root_event_persistence() -> None:
    """Verifies that events are not cleared during version increments."""
    user = UserAccount(id="user-1", username="alice")
    user.add_event(SomethingHappened(message="1"))
    user.increment_version()
    user.add_event(SomethingHappened(message="2"))

    events = user.collect_events()
    assert len(events) == 2
    assert user.version == 1


def test_domain_event_serialization_fields() -> None:
    """Verifies all standard fields are present in model_dump output."""
    event = SomethingHappened(message="Hello", metadata={"meta": "data"})
    data = event.model_dump()

    assert data["event_id"]
    assert data["message"] == "Hello"
    assert data["metadata"] == {"meta": "data"}
    assert data["version"] == 1
    assert "occurred_at" in data
    assert data["correlation_id"] is None
    assert data["causation_id"] is None


def test_value_object_hash_consistency() -> None:
    """Verifies ValueObject hashing is consistent and structural."""
    v1 = Money(amount=10.0, currency="USD")
    v2 = Money(amount=10.0, currency="USD")
    v3 = Money(amount=20.0, currency="EUR")
    assert hash(v1) == hash(v2)
    assert hash(v1) != hash(v3)


def test_domain_event_identity() -> None:
    """Verifies that domain events have unique IDs and timestamps."""
    event1 = SomethingHappened(message="First")
    event2 = SomethingHappened(message="Second")

    assert event1.event_id != event2.event_id
    assert isinstance(event1.occurred_at, datetime)
    assert event1.occurred_at.tzinfo == timezone.utc


def test_domain_event_serialization() -> None:
    """Verifies that domain events can be serialized to dictionaries."""
    event = SomethingHappened(message="Hello", metadata={"source": "test"})
    data = event.model_dump()

    assert data["message"] == "Hello"
    assert "event_id" in data
    assert "occurred_at" in data
    assert data["metadata"]["source"] == "test"


def test_value_object_equality() -> None:
    """Verifies that value objects are compared by value, not reference."""
    m1 = Money(amount=10.0, currency="USD")
    m2 = Money(amount=10.0, currency="USD")
    m3 = Money(amount=20.0, currency="USD")

    assert m1 == m2
    assert m1 != m3
    assert hash(m1) == hash(m2)
    assert hash(m1) != hash(m3)


def test_value_object_immutability() -> None:
    """Verifies that value objects are immutable (if Pydantic is used)."""
    m = Money(amount=10.0, currency="USD")
    with pytest.raises(Exception, match="is immutable|cannot set attribute|validation"):
        m.amount = 20.0
