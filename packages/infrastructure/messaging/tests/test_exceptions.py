"""Tests for messaging exceptions."""

from __future__ import annotations

from cqrs_ddd_core.primitives.exceptions import InfrastructureError
from cqrs_ddd_messaging.exceptions import (
    DeadLetterError,
    MessagingError,
)


def test_messaging_error_is_infrastructure() -> None:
    assert issubclass(MessagingError, InfrastructureError)


def test_dead_letter_error_has_message_id() -> None:
    e = DeadLetterError("failed", message_id="mid-1")
    assert e.message_id == "mid-1"
    assert "failed" in str(e)
