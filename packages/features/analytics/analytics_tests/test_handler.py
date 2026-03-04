"""Tests for AnalyticsEventHandler."""

from __future__ import annotations

import pytest

from cqrs_ddd_analytics.buffer import AnalyticsBuffer
from cqrs_ddd_analytics.handler import AnalyticsEventHandler
from cqrs_ddd_analytics.mapper import EventToRowMapper
from cqrs_ddd_analytics.memory import InMemorySink

from .conftest import OrderCreated, UnmappedEvent


@pytest.fixture
def mapper() -> EventToRowMapper:
    m = EventToRowMapper()

    @m.register(OrderCreated)
    def map_order(event: OrderCreated) -> dict[str, object]:
        return {
            "event_type": "OrderCreated",
            "order_id": event.order_id,
            "total": event.total_amount,
        }

    return m


@pytest.fixture
def sink() -> InMemorySink:
    return InMemorySink()


@pytest.fixture
def buffer(sink: InMemorySink) -> AnalyticsBuffer:
    return AnalyticsBuffer(sink, batch_size=100, flush_interval=300.0)


class TestAnalyticsEventHandler:
    """Tests for AnalyticsEventHandler."""

    @pytest.mark.asyncio
    async def test_handles_mapped_event(
        self,
        mapper: EventToRowMapper,
        buffer: AnalyticsBuffer,
        sink: InMemorySink,
    ) -> None:
        handler = AnalyticsEventHandler(mapper, buffer, table="orders")
        event = OrderCreated(order_id="o1", total_amount=99.99, aggregate_id="o1")
        await handler.handle(event)
        await buffer.flush_all()
        rows = sink.get_rows("orders")
        assert len(rows) == 1
        assert rows[0]["order_id"] == "o1"
        assert rows[0]["total"] == 99.99

    @pytest.mark.asyncio
    async def test_skips_unmapped_event(
        self,
        mapper: EventToRowMapper,
        buffer: AnalyticsBuffer,
        sink: InMemorySink,
    ) -> None:
        handler = AnalyticsEventHandler(mapper, buffer, table="orders")
        event = UnmappedEvent(data="nope")
        await handler.handle(event)
        await buffer.flush_all()
        assert sink.row_count("orders") == 0

    @pytest.mark.asyncio
    async def test_handles_list_result(
        self,
        buffer: AnalyticsBuffer,
        sink: InMemorySink,
    ) -> None:
        multi_mapper = EventToRowMapper()

        @multi_mapper.register(OrderCreated)
        def map_multi(event: OrderCreated) -> list[dict[str, object]]:
            return [
                {"field": "order_id", "value": event.order_id},
                {"field": "total", "value": event.total_amount},
            ]

        handler = AnalyticsEventHandler(multi_mapper, buffer, table="metrics")
        event = OrderCreated(order_id="o2", total_amount=50.0, aggregate_id="o2")
        await handler.handle(event)
        await buffer.flush_all()
        assert sink.row_count("metrics") == 2

    @pytest.mark.asyncio
    async def test_multiple_events_accumulate(
        self,
        mapper: EventToRowMapper,
        buffer: AnalyticsBuffer,
        sink: InMemorySink,
    ) -> None:
        handler = AnalyticsEventHandler(mapper, buffer, table="orders")
        for i in range(5):
            event = OrderCreated(
                order_id=f"o{i}",
                total_amount=float(i * 10),
                aggregate_id=f"o{i}",
            )
            await handler.handle(event)
        await buffer.flush_all()
        assert sink.row_count("orders") == 5
