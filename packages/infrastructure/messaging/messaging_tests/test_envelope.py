"""Tests for MessageEnvelope."""

from __future__ import annotations

from datetime import timezone

import pytest
from pydantic import ValidationError

from cqrs_ddd_messaging.envelope import MessageEnvelope


def test_envelope_defaults() -> None:
    e = MessageEnvelope(event_type="OrderCreated", payload={"order_id": "1"})
    assert e.event_type == "OrderCreated"
    assert e.payload == {"order_id": "1"}
    assert e.attempt == 1
    assert e.message_id
    assert e.timestamp.tzinfo == timezone.utc
    assert e.correlation_id is None
    assert e.causation_id is None
    assert e.headers == {}


def test_envelope_frozen() -> None:
    e = MessageEnvelope(event_type="X", payload={})
    with pytest.raises((ValueError, ValidationError), match=r".+"):
        e.event_type = "Y"  # type: ignore[misc]


def test_envelope_attempt_ge_1() -> None:
    MessageEnvelope(event_type="X", payload={}, attempt=1)
    with pytest.raises(ValidationError, match=r"attempt|ge|greater"):
        MessageEnvelope(event_type="X", payload={}, attempt=0)
