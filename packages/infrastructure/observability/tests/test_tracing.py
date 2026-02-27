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
async def test_tracing_without_opentelemetry():
    """Test middleware works without opentelemetry installed."""
    with patch.object(TracingMiddleware, "__init__", lambda self: None):
        mw = TracingMiddleware()
        mw._tracer = None
    next_handler = AsyncMock(return_value="ok")
    message = type("TestMessage", (), {"__name__": "TestMessage"})()
    result = await mw(message, next_handler)
    assert result == "ok"
    next_handler.assert_called_once_with(message)


@pytest.mark.asyncio
async def test_tracing_with_opentelemetry():
    """Test middleware creates span with opentelemetry."""
    fake_span = _FakeSpan()
    fake_tracer = _FakeTracer(fake_span)
    with patch.object(TracingMiddleware, "__init__", lambda self: None):
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
    with patch.object(TracingMiddleware, "__init__", lambda self: None):
        mw = TracingMiddleware()
        mw._tracer = fake_tracer
    with patch(
        "cqrs_ddd_observability.tracing.get_correlation_id",
        return_value="test-correlation-123",
    ):
        next_handler = AsyncMock(return_value="ok")
        message = type("TestMessage", (), {"__name__": "TestMessage"})()
        await mw(message, next_handler)
    assert fake_span.attributes.get("cqrs.correlation_id") == "test-correlation-123"


@pytest.mark.asyncio
async def test_tracing_records_message_correlation_id():
    """Test middleware records correlation_id from message when context is None."""
    fake_span = _FakeSpan()
    fake_tracer = _FakeTracer(fake_span)
    with patch.object(TracingMiddleware, "__init__", lambda self: None):
        mw = TracingMiddleware()
        mw._tracer = fake_tracer
    with patch("cqrs_ddd_observability.tracing.get_correlation_id", return_value=None):
        next_handler = AsyncMock(return_value="ok")
        message = type(
            "TestMessage",
            (),
            {"__name__": "TestMessage", "correlation_id": "msg-correlation"},
        )()
        await mw(message, next_handler)
    assert fake_span.attributes.get("cqrs.correlation_id") == "msg-correlation"


@pytest.mark.asyncio
async def test_tracing_records_exception():
    """Test middleware records exception in span."""
    fake_span = _FakeSpan()
    fake_tracer = _FakeTracer(fake_span)
    test_exception = ValueError("Test error")
    with patch.object(TracingMiddleware, "__init__", lambda self: None):
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
    """Test that record_exception failure does not mask the original exception."""

    class _FakeSpanBadRecord(_FakeSpan):
        def record_exception(self, exc: Exception) -> None:
            raise RuntimeError("record_exception failed")

    fake_span = _FakeSpanBadRecord()
    fake_tracer = _FakeTracer(fake_span)
    test_exception = ValueError("Test error")
    with patch.object(TracingMiddleware, "__init__", lambda self: None):
        mw = TracingMiddleware()
        mw._tracer = fake_tracer
    next_handler = AsyncMock(side_effect=test_exception)
    message = type("TestMessage", (), {"__name__": "TestMessage"})()

    with pytest.raises(ValueError, match="Test error"):
        await mw(message, next_handler)

    assert fake_span.attributes["cqrs.outcome"] == "error"
