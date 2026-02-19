"""Tests for DeadLetterHandler."""

from __future__ import annotations

import pytest

from cqrs_ddd_messaging.dead_letter import DeadLetterHandler
from cqrs_ddd_messaging.envelope import MessageEnvelope
from cqrs_ddd_messaging.exceptions import DeadLetterError


@pytest.mark.asyncio
async def test_route_raises_dead_letter_error() -> None:
    h = DeadLetterHandler()
    e = MessageEnvelope(event_type="X", payload={}, message_id="mid-1")
    with pytest.raises(DeadLetterError) as exc_info:
        await h.route(e, "failed")
    assert exc_info.value.message_id == "mid-1"


@pytest.mark.asyncio
async def test_route_calls_callback_then_raises() -> None:
    seen: list[tuple[MessageEnvelope, str, BaseException | None]] = []

    async def on_dlq(
        envelope: MessageEnvelope, reason: str, exc: BaseException | None
    ) -> None:
        seen.append((envelope, reason, exc))

    h = DeadLetterHandler(on_dead_letter=on_dlq)
    e = MessageEnvelope(event_type="X", payload={})
    with pytest.raises(DeadLetterError):
        await h.route(e, "max retries", exception=ValueError("err"))
    assert len(seen) == 1
    assert seen[0][0] == e
    assert seen[0][1] == "max retries"
    assert isinstance(seen[0][2], ValueError)
