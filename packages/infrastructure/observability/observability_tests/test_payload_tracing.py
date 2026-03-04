"""Tests for PayloadTracingMiddleware."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from cqrs_ddd_observability.payload_tracing import PayloadTracingMiddleware


class _FakeSpan:
    def __init__(self) -> None:
        self.attributes: dict[str, object] = {}
        self.events: list[tuple[str, dict[str, object]]] = []

    def set_attribute(self, key: str, value: object) -> None:
        self.attributes[key] = value

    def add_event(self, name: str, attributes: dict[str, object]) -> None:
        self.events.append((name, attributes))


@pytest.mark.asyncio
async def test_payload_tracing_redacts_and_hashes_fields() -> None:
    span = _FakeSpan()
    mw = PayloadTracingMiddleware(
        redact_fields={"email"},
        hash_fields={"token"},
    )
    mw._get_active_span = lambda: span  # type: ignore[method-assign]  # noqa: SLF001

    message = {
        "order_id": "o-1",
        "email": "user@example.com",
        "token": "secret-token",
    }
    next_handler = AsyncMock(return_value="ok")

    result = await mw(message, next_handler)
    assert result == "ok"

    payload_event = [evt for evt in span.events if evt[0] == "cqrs.command_payload"]
    assert payload_event
    payload_text = str(payload_event[0][1]["payload"])
    assert '"order_id": "o-1"' in payload_text
    assert '"email": "***"' in payload_text
    assert '"token": "sha256:' in payload_text
    assert "secret-token" not in payload_text


@pytest.mark.asyncio
async def test_payload_tracing_uses_allowlist_and_truncation() -> None:
    span = _FakeSpan()
    mw = PayloadTracingMiddleware(
        include_fields={"order_id"},
        max_payload_chars=20,
    )
    mw._get_active_span = lambda: span  # type: ignore[method-assign]  # noqa: SLF001

    message = {
        "order_id": "very-very-long-order-id",
        "email": "user@example.com",
    }
    next_handler = AsyncMock(return_value="ok")

    await mw(message, next_handler)

    payload_event = [evt for evt in span.events if evt[0] == "cqrs.command_payload"]
    assert payload_event
    payload_text = str(payload_event[0][1]["payload"])
    assert "order_id" in payload_text
    assert "email" not in payload_text
    assert "...<truncated>" in payload_text
    assert span.attributes["cqrs.payload_truncated"] is True


@pytest.mark.asyncio
async def test_payload_tracing_no_active_span_is_noop() -> None:
    mw = PayloadTracingMiddleware()
    mw._get_active_span = lambda: None  # type: ignore[method-assign]  # noqa: SLF001

    next_handler = AsyncMock(return_value="ok")
    result = await mw({"order_id": "o-1"}, next_handler)
    assert result == "ok"
    next_handler.assert_awaited_once()
