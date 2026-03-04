"""Tests for TracingMiddleware."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from cqrs_ddd_observability.tracing import TracingMiddleware


class _FakeSpan:
    """Fake span for testing."""

    def __init__(self):
        self.attributes = {}
        self.exceptions = []

    def set_attribute(self, key: str, value: str | int) -> None:
        self.attributes[key] = value

    def record_exception(self, exc: Exception) -> None:
        self.exceptions.append(exc)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


class _FakeTracer:
    """Fake tracer for testing."""

    def __init__(self, span: _FakeSpan):
        self._span = span

    def start_as_current_span(self, name: str):
        return self._span


@pytest.mark.asyncio
async def test_tracing_with_opentelemetry():
    """Test middleware creates span with opentelemetry."""
    fake_span = _FakeSpan()
    fake_tracer = _FakeTracer(fake_span)

    mw = TracingMiddleware()
    mw._tracer = fake_tracer
    next_handler = AsyncMock(return_value="ok")
    message = type("TestMessage", (), {"__name__": "TestMessage"})()

    result = await mw(message, next_handler)

    assert result == "ok"
    assert "cqrs.command_type" in fake_span.attributes
    assert fake_span.attributes["cqrs.command_type"] == "TestMessage"
    assert fake_span.attributes["cqrs.outcome"] == "success"


@pytest.mark.asyncio
async def test_tracing_records_correlation_id():
    """Test middleware records correlation_id from context."""
    fake_span = _FakeSpan()
    fake_tracer = _FakeTracer(fake_span)

    with patch(
        "cqrs_ddd_observability.tracing.get_correlation_id",
        return_value="test-correlation-123",
    ):
        mw = TracingMiddleware()
        mw._tracer = fake_tracer
        next_handler = AsyncMock(return_value="ok")
        message = type("TestMessage", (), {"__name__": "TestMessage"})()

        await mw(message, next_handler)

        assert fake_span.attributes["cqrs.correlation_id"] == "test-correlation-123"


@pytest.mark.asyncio
async def test_tracing_records_message_correlation_id():
    """Test middleware records correlation_id from message when context is None."""
    fake_span = _FakeSpan()
    fake_tracer = _FakeTracer(fake_span)

    with patch("cqrs_ddd_observability.tracing.get_correlation_id", return_value=None):
        mw = TracingMiddleware()
        mw._tracer = fake_tracer
        next_handler = AsyncMock(return_value="ok")
        message = type(
            "TestMessage",
            (),
            {"__name__": "TestMessage", "correlation_id": "msg-correlation-456"},
        )()

        await mw(message, next_handler)

        assert fake_span.attributes["cqrs.correlation_id"] == "msg-correlation-456"


@pytest.mark.asyncio
async def test_tracing_records_exception():
    """Test middleware records exception in span."""
    fake_span = _FakeSpan()
    fake_tracer = _FakeTracer(fake_span)

    test_exception = ValueError("Test error")

    mw = TracingMiddleware()
    mw._tracer = fake_tracer
    next_handler = AsyncMock(side_effect=test_exception)
    message = type("TestMessage", (), {"__name__": "TestMessage"})()

    with pytest.raises(ValueError, match="Test error"):
        await mw(message, next_handler)

    assert fake_span.attributes["cqrs.outcome"] == "error"
    assert len(fake_span.exceptions) == 1
    assert fake_span.exceptions[0] is test_exception


@pytest.mark.asyncio
async def test_tracing_exception_suppression():
    """Test middleware suppresses span.record_exception errors."""

    class FakeSpanWithBadRecord(_FakeSpan):
        def record_exception(self, exc):
            raise RuntimeError("Span record failed")

    fake_span = FakeSpanWithBadRecord()
    fake_tracer = _FakeTracer(fake_span)
    test_exception = ValueError("Test error")

    mw = TracingMiddleware()
    mw._tracer = fake_tracer
    next_handler = AsyncMock(side_effect=test_exception)
    message = type("TestMessage", (), {"__name__": "TestMessage"})()

    # Should not raise RuntimeError from span.record_exception
    with pytest.raises(ValueError, match="Test error"):
        await mw(message, next_handler)

    assert fake_span.attributes["cqrs.outcome"] == "error"
