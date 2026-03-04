"""Tests for MetricsMiddleware."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cqrs_ddd_core.cqrs.command import Command
from cqrs_ddd_core.cqrs.query import Query
from cqrs_ddd_observability.metrics import MetricsMiddleware


class TestDetectKind:
    """Tests for _detect_kind function."""

    def test_detect_kind_command(self):
        """Test detecting command type."""
        from cqrs_ddd_observability.metrics import _detect_kind

        class TestCommand(Command):
            pass

        assert _detect_kind(TestCommand()) == "command"

    def test_detect_kind_query(self):
        """Test detecting query type."""
        from cqrs_ddd_observability.metrics import _detect_kind

        class TestQuery(Query):
            pass

        assert _detect_kind(TestQuery()) == "query"

    def test_detect_kind_message(self):
        """Test detecting generic message type."""
        from cqrs_ddd_observability.metrics import _detect_kind

        class TestMessage:
            pass

        assert _detect_kind(TestMessage()) == "message"


class TestMetricsMiddleware:
    """Tests for MetricsMiddleware."""

    @pytest.mark.asyncio
    async def test_metrics_without_prometheus(self):
        """Test middleware works without prometheus_client installed."""
        import builtins

        real_import = builtins.__import__

        def raise_for_prometheus(name, *args, **kwargs):
            if name == "prometheus_client":
                raise ImportError("No module named 'prometheus_client'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=raise_for_prometheus):
            mw = MetricsMiddleware()
        next_handler = AsyncMock(return_value="ok")
        message = type("TestMessage", (), {"__name__": "TestMessage"})()

        result = await mw(message, next_handler)
        assert result == "ok"
        next_handler.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_metrics_records_success(self):
        """Test middleware records successful operation."""
        mock_histogram = MagicMock()
        mock_counter = MagicMock()

        with (
            patch("prometheus_client.Counter", return_value=mock_counter),
            patch("prometheus_client.Histogram", return_value=mock_histogram),
        ):
            mw = MetricsMiddleware()
            next_handler = AsyncMock(return_value="ok")
            message = type("TestMessage", (), {"__name__": "TestMessage"})()

            result = await mw(message, next_handler)

            assert result == "ok"
            mock_histogram.labels.assert_called_once()
            mock_counter.labels.assert_called_once()
            mock_histogram.labels.return_value.observe.assert_called_once()
            mock_counter.labels.return_value.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_metrics_records_error(self):
        """Test middleware records failed operation."""
        mock_histogram = MagicMock()
        mock_counter = MagicMock()

        with (
            patch("prometheus_client.Counter", return_value=mock_counter),
            patch("prometheus_client.Histogram", return_value=mock_histogram),
        ):
            mw = MetricsMiddleware()
            next_handler = AsyncMock(side_effect=ValueError("Test error"))
            message = type("TestMessage", (), {"__name__": "TestMessage"})()

            with pytest.raises(ValueError, match="Test error"):
                await mw(message, next_handler)

            # Should still record metrics even on error
            mock_histogram.labels.assert_called_once()
            mock_counter.labels.assert_called_once()
            mock_histogram.labels.return_value.observe.assert_called_once()
            mock_counter.labels.return_value.inc.assert_called_once()

            # Check outcome label
            histogram_labels = mock_histogram.labels.call_args.kwargs
            counter_labels = mock_counter.labels.call_args.kwargs
            assert histogram_labels["outcome"] == "error"
            assert counter_labels["outcome"] == "error"

    @pytest.mark.asyncio
    async def test_metrics_detects_command_kind(self):
        """Test middleware classifies commands correctly."""
        mock_histogram = MagicMock()
        mock_counter = MagicMock()

        with (
            patch("prometheus_client.Counter", return_value=mock_counter),
            patch("prometheus_client.Histogram", return_value=mock_histogram),
        ):
            mw = MetricsMiddleware()

            class TestCommand(Command):
                pass

            next_handler = AsyncMock(return_value="ok")
            message = TestCommand()

            await mw(message, next_handler)

            histogram_labels = mock_histogram.labels.call_args.kwargs
            counter_labels = mock_counter.labels.call_args.kwargs
            assert histogram_labels["kind"] == "command"
            assert counter_labels["kind"] == "command"

    @pytest.mark.asyncio
    async def test_metrics_detects_query_kind(self):
        """Test middleware classifies queries correctly."""
        mock_histogram = MagicMock()
        mock_counter = MagicMock()

        with (
            patch("prometheus_client.Counter", return_value=mock_counter),
            patch("prometheus_client.Histogram", return_value=mock_histogram),
        ):
            mw = MetricsMiddleware()

            class TestQuery(Query):
                pass

            next_handler = AsyncMock(return_value="ok")
            message = TestQuery()

            await mw(message, next_handler)

            histogram_labels = mock_histogram.labels.call_args.kwargs
            counter_labels = mock_counter.labels.call_args.kwargs
            assert histogram_labels["kind"] == "query"
            assert counter_labels["kind"] == "query"

    @pytest.mark.asyncio
    async def test_metrics_records_message_type(self):
        """Test middleware records message type in labels."""
        mock_histogram = MagicMock()
        mock_counter = MagicMock()

        with (
            patch("prometheus_client.Counter", return_value=mock_counter),
            patch("prometheus_client.Histogram", return_value=mock_histogram),
        ):
            mw = MetricsMiddleware()
            next_handler = AsyncMock(return_value="ok")

            class CustomMessage:
                pass

            message = CustomMessage()
            await mw(message, next_handler)

            histogram_labels = mock_histogram.labels.call_args.kwargs
            counter_labels = mock_counter.labels.call_args.kwargs
            assert histogram_labels["message_type"] == "CustomMessage"
            assert counter_labels["message_type"] == "CustomMessage"

    @pytest.mark.asyncio
    async def test_metrics_handles_emit_failure(self):
        """Test middleware handles prometheus emit failures gracefully."""
        mock_histogram = MagicMock()
        mock_counter = MagicMock()

        # Make histogram.observe() raise an exception
        mock_histogram.labels.return_value.observe.side_effect = RuntimeError(
            "Prometheus failed"
        )

        with (
            patch("prometheus_client.Counter", return_value=mock_counter),
            patch("prometheus_client.Histogram", return_value=mock_histogram),
            patch("cqrs_ddd_observability.metrics._logger") as mock_logger,
        ):
            mw = MetricsMiddleware()
            next_handler = AsyncMock(return_value="ok")
            message = type("TestMessage", (), {"__name__": "TestMessage"})()

            # Should not raise exception, should log debug message
            result = await mw(message, next_handler)
            assert result == "ok"

            # Verify debug logging
            assert mock_logger.debug.called
