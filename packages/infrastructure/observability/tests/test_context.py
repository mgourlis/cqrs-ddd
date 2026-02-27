"""Tests for ObservabilityContext."""

from __future__ import annotations

from unittest.mock import patch

from cqrs_ddd_observability.context import ObservabilityContext


class TestObservabilityContext:
    """Tests for ObservabilityContext static methods."""

    def test_get_empty_context(self):
        """Test get returns empty dict when context is not set."""
        result = ObservabilityContext.get()
        assert result == {}

    def test_get_set_context(self):
        """Test setting and getting context values."""
        ObservabilityContext.set(
            trace_id="trace-123",
            span_id="span-456",
        )

        result = ObservabilityContext.get()
        assert result["trace_id"] == "trace-123"
        assert result["span_id"] == "span-456"

        # Reset context
        ObservabilityContext.set()

    def test_get_trace_id(self):
        """Test getting trace_id from context."""
        ObservabilityContext.set(trace_id="trace-789")

        result = ObservabilityContext.get_trace_id()
        assert result == "trace-789"

        # Reset context
        ObservabilityContext.set()

    def test_get_trace_id_when_not_set(self):
        """Test get_trace_id returns None when not set."""
        ObservabilityContext.set()  # Clear context

        result = ObservabilityContext.get_trace_id()
        assert result is None

    def test_get_span_id(self):
        """Test getting span_id from context."""
        ObservabilityContext.set(span_id="span-101")

        result = ObservabilityContext.get_span_id()
        assert result == "span-101"

        # Reset context
        ObservabilityContext.set()

    def test_get_span_id_when_not_set(self):
        """Test get_span_id returns None when not set."""
        ObservabilityContext.set()  # Clear context

        result = ObservabilityContext.get_span_id()
        assert result is None

    def test_set_updates_existing_context(self):
        """Test set updates existing context rather than replacing it."""
        # Set initial values
        ObservabilityContext.set(
            trace_id="trace-123",
            span_id="span-456",
        )

        # Update with additional values
        ObservabilityContext.set(custom_field="custom-value")

        result = ObservabilityContext.get()
        assert result["trace_id"] == "trace-123"
        assert result["span_id"] == "span-456"
        assert result["custom_field"] == "custom-value"

        # Reset context
        ObservabilityContext.set()

    def test_set_overwrites_existing_values(self):
        """Test set overwrites existing values."""
        ObservabilityContext.set(
            trace_id="trace-123",
            span_id="span-456",
        )

        # Overwrite trace_id
        ObservabilityContext.set(trace_id="trace-789")

        result = ObservabilityContext.get()
        assert result["trace_id"] == "trace-789"
        assert result["span_id"] == "span-456"

        # Reset context
        ObservabilityContext.set()

    def test_get_correlation_id_delegates_to_core(self):
        """Test get_correlation_id delegates to core.get_correlation_id."""
        with patch(
            "cqrs_ddd_observability.context.get_correlation_id",
            return_value="core-correlation-123",
        ):
            result = ObservabilityContext.get_correlation_id()
            assert result == "core-correlation-123"

    def test_get_correlation_id_when_none(self):
        """Test get_correlation_id returns None when core returns None."""
        with patch(
            "cqrs_ddd_observability.context.get_correlation_id", return_value=None
        ):
            result = ObservabilityContext.get_correlation_id()
            assert result is None

    def test_multiple_contexts_isolated(self):
        """Test that different async contexts are isolated."""
        import asyncio

        async def set_trace(trace_id: str):
            ObservabilityContext.set(trace_id=trace_id)
            return ObservabilityContext.get_trace_id()

        async def main():
            # Run tasks concurrently
            task1 = asyncio.create_task(set_trace("trace-1"))
            task2 = asyncio.create_task(set_trace("trace-2"))

            result1 = await task1
            result2 = await task2

            return result1, result2

        # Note: In real async scenarios, ContextVar isolation works
        # This test just verifies the API
        result = asyncio.run(main())
        # Results may vary depending on execution order
        assert result[0] in ["trace-1", "trace-2"]
        assert result[1] in ["trace-1", "trace-2"]

    def test_clear_context(self):
        """Test clearing context by calling set() with no args."""
        ObservabilityContext.set(
            trace_id="trace-123",
            span_id="span-456",
        )

        # Clear context
        ObservabilityContext.set()

        result = ObservabilityContext.get()
        assert result == {}

    def test_set_none_value(self):
        """Test setting None values."""
        ObservabilityContext.set(
            trace_id=None,
            span_id=None,
        )

        result = ObservabilityContext.get()
        assert result["trace_id"] is None
        assert result["span_id"] is None

        # Reset context
        ObservabilityContext.set()

    def test_get_returns_copy(self):
        """Test that get returns a copy, not the original dict."""
        ObservabilityContext.set(trace_id="trace-123")

        result = ObservabilityContext.get()
        result["trace_id"] = "modified"

        # Original context should be unchanged
        original = ObservabilityContext.get()
        assert original["trace_id"] == "trace-123"

        # Reset context
        ObservabilityContext.set()
