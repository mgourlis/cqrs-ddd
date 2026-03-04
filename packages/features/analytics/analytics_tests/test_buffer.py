"""Tests for AnalyticsBuffer."""

from __future__ import annotations

import asyncio

import pytest

from cqrs_ddd_analytics.buffer import AnalyticsBuffer
from cqrs_ddd_analytics.exceptions import BufferFlushError
from cqrs_ddd_analytics.memory import InMemorySink


@pytest.fixture
def sink() -> InMemorySink:
    return InMemorySink()


@pytest.fixture
def buffer(sink: InMemorySink) -> AnalyticsBuffer:
    return AnalyticsBuffer(sink, batch_size=3, flush_interval=60.0)


class TestAnalyticsBuffer:
    """Tests for AnalyticsBuffer."""

    @pytest.mark.asyncio
    async def test_add_below_batch_size_does_not_flush(
        self, buffer: AnalyticsBuffer, sink: InMemorySink
    ) -> None:
        await buffer.add("orders", {"id": "1"})
        await buffer.add("orders", {"id": "2"})
        assert sink.row_count("orders") == 0
        assert buffer.pending_count == 2

    @pytest.mark.asyncio
    async def test_auto_flush_at_batch_size(
        self, buffer: AnalyticsBuffer, sink: InMemorySink
    ) -> None:
        await buffer.add("orders", {"id": "1"})
        await buffer.add("orders", {"id": "2"})
        await buffer.add("orders", {"id": "3"})  # triggers flush at batch_size=3
        assert sink.row_count("orders") == 3
        assert buffer.pending_count == 0

    @pytest.mark.asyncio
    async def test_flush_all(self, buffer: AnalyticsBuffer, sink: InMemorySink) -> None:
        await buffer.add("orders", {"id": "1"})
        await buffer.add("metrics", {"val": 42})
        await buffer.flush_all()
        assert sink.row_count("orders") == 1
        assert sink.row_count("metrics") == 1
        assert buffer.pending_count == 0

    @pytest.mark.asyncio
    async def test_multiple_tables(
        self, buffer: AnalyticsBuffer, sink: InMemorySink
    ) -> None:
        for i in range(3):
            await buffer.add("t1", {"i": i})
        for i in range(2):
            await buffer.add("t2", {"i": i})
        assert sink.row_count("t1") == 3
        assert sink.row_count("t2") == 0
        await buffer.flush_all()
        assert sink.row_count("t2") == 2

    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(self, sink: InMemorySink) -> None:
        buf = AnalyticsBuffer(sink, batch_size=100, flush_interval=0.05)
        await buf.add("orders", {"id": "1"})
        await buf.start()
        # Wait enough for one flush cycle
        await asyncio.sleep(0.15)
        assert sink.row_count("orders") == 1
        await buf.stop()

    @pytest.mark.asyncio
    async def test_stop_flushes_remaining(
        self, buffer: AnalyticsBuffer, sink: InMemorySink
    ) -> None:
        await buffer.add("orders", {"id": "1"})
        await buffer.start()
        await buffer.stop()
        assert sink.row_count("orders") == 1

    @pytest.mark.asyncio
    async def test_flush_error_preserves_rows(self, sink: InMemorySink) -> None:
        class FailingSink(InMemorySink):
            async def push_batch(
                self, table: str, rows: list[dict[str, object]]
            ) -> int:
                raise RuntimeError("disk full")

        failing_sink = FailingSink()
        buf = AnalyticsBuffer(failing_sink, batch_size=100)
        await buf.add("orders", {"id": "1"})

        with pytest.raises(BufferFlushError, match="disk full"):
            await buf.flush_all()

        # Rows should be preserved in buffer
        assert buf.pending_count == 1

    @pytest.mark.asyncio
    async def test_start_idempotent(self, buffer: AnalyticsBuffer) -> None:
        await buffer.start()
        await buffer.start()  # Should not create duplicate tasks
        await buffer.stop()
