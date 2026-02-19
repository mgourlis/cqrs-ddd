"""Tests for EnvelopeSerializer roundtrip and hydration."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from cqrs_ddd_core.domain.event_registry import EventTypeRegistry
from cqrs_ddd_core.domain.events import DomainEvent
from cqrs_ddd_messaging.envelope import MessageEnvelope
from cqrs_ddd_messaging.exceptions import MessagingSerializationError
from cqrs_ddd_messaging.serialization import EnvelopeSerializer


class OrderCreated(DomainEvent):
    """Test event."""

    order_id: str
    amount: float = 100.0


def test_serialize_deserialize_roundtrip() -> None:
    ser = EnvelopeSerializer()
    e = MessageEnvelope(
        event_type="OrderCreated",
        payload={"order_id": "123", "amount": 99.5},
        correlation_id="corr-1",
    )
    raw = ser.serialize(e)
    assert isinstance(raw, bytes)
    e2 = ser.deserialize(raw)
    assert e2.event_type == e.event_type
    assert e2.payload == e.payload
    assert e2.correlation_id == e.correlation_id


def test_deserialize_invalid_raises() -> None:
    ser = EnvelopeSerializer()
    with pytest.raises(MessagingSerializationError):
        ser.deserialize(b"not json")


def test_serialize_non_json_serializable_payload_raises() -> None:
    """Payload value that model_dump cannot serialize raises MessagingSerializationError with chained cause."""
    ser = EnvelopeSerializer()

    class Bad:
        pass

    envelope = MessageEnvelope(
        event_type="X",
        payload={"key": Bad()},
    )
    with pytest.raises(MessagingSerializationError) as exc_info:
        ser.serialize(envelope)
    assert exc_info.value.__cause__ is not None
    # Pydantic may raise PydanticSerializationError or TypeError from json default
    assert (
        "serializ" in str(exc_info.value).lower()
        or "serializ" in str(exc_info.value.__cause__).lower()
    )


def test_serialize_model_dump_raises_wraps() -> None:
    """If model_dump raises TypeError/ValueError, serialize raises MessagingSerializationError."""
    ser = EnvelopeSerializer()
    envelope = MessageEnvelope(event_type="X", payload={"a": 1})
    with (
        patch.object(MessageEnvelope, "model_dump", side_effect=ValueError("bad")),
        pytest.raises(MessagingSerializationError) as exc_info,
    ):
        ser.serialize(envelope)
    assert "bad" in str(exc_info.value)
    assert exc_info.value.__cause__ is not None


def test_serialize_json_default_raises_type_error() -> None:
    """When json.dumps hits a non-serializable value, _json_serializer raises and we wrap it."""
    from cqrs_ddd_messaging.serialization import _json_serializer

    with pytest.raises(TypeError, match="not JSON serializable"):
        _json_serializer(object())


def test_deserialize_invalid_timestamp_raises() -> None:
    """Valid JSON with non-parseable timestamp raises MessagingSerializationError."""
    ser = EnvelopeSerializer()
    raw = (
        b'{"event_type":"X","payload":{},"timestamp":"not-a-date","correlation_id":""}'
    )
    with pytest.raises(MessagingSerializationError):
        ser.deserialize(raw)


def test_deserialize_invalid_structure_raises() -> None:
    """Valid JSON but invalid for MessageEnvelope (e.g. wrong type for payload) raises."""
    ser = EnvelopeSerializer()
    raw = b'{"event_type":123,"payload":null,"timestamp":"2025-01-01T00:00:00Z","correlation_id":""}'
    with pytest.raises(MessagingSerializationError):
        ser.deserialize(raw)


def test_hydrate_with_registry() -> None:
    registry = EventTypeRegistry()
    registry.register("OrderCreated", OrderCreated)
    ser = EnvelopeSerializer(registry=registry)
    e = MessageEnvelope(
        event_type="OrderCreated",
        payload={"order_id": "o1", "amount": 10.0},
    )
    obj = ser.hydrate(e)
    assert isinstance(obj, OrderCreated)
    assert obj.order_id == "o1"
    assert obj.amount == 10.0


def test_hydrate_without_registry_returns_payload() -> None:
    ser = EnvelopeSerializer()
    e = MessageEnvelope(event_type="X", payload={"a": 1})
    assert ser.hydrate(e) == {"a": 1}


def test_hydrate_unregistered_returns_payload() -> None:
    registry = EventTypeRegistry()
    ser = EnvelopeSerializer(registry=registry)
    e = MessageEnvelope(event_type="Unknown", payload={"a": 1})
    assert ser.hydrate(e) == {"a": 1}
