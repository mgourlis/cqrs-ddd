"""Integration tests — end-to-end event → mapper → buffer → sink pipeline."""

from __future__ import annotations

import pytest

from cqrs_ddd_analytics.buffer import AnalyticsBuffer
from cqrs_ddd_analytics.handler import AnalyticsEventHandler
from cqrs_ddd_analytics.mapper import EventToRowMapper
from cqrs_ddd_analytics.memory import InMemorySink
from cqrs_ddd_analytics.schema import AnalyticsSchema, ColumnDef, ColumnType

from .conftest import OrderCancelled, OrderCreated, UnmappedEvent


@pytest.fixture
def full_pipeline() -> tuple[
    EventToRowMapper, AnalyticsBuffer, InMemorySink, AnalyticsEventHandler
]:
    """Create a complete pipeline: mapper → buffer → sink → handler."""
    sink = InMemorySink()
    mapper = EventToRowMapper()

    @mapper.register(OrderCreated)
    def map_created(event: OrderCreated) -> dict[str, object]:
        return {
            "event_type": "OrderCreated",
            "event_id": event.event_id,
            "occurred_at": event.occurred_at.isoformat(),
            "order_id": event.order_id,
            "total_amount": event.total_amount,
        }

    @mapper.register(OrderCancelled)
    def map_cancelled(event: OrderCancelled) -> dict[str, object]:
        return {
            "event_type": "OrderCancelled",
            "event_id": event.event_id,
            "occurred_at": event.occurred_at.isoformat(),
            "order_id": event.order_id,
            "reason": event.reason,
        }

    buffer = AnalyticsBuffer(sink, batch_size=10, flush_interval=300.0)
    handler = AnalyticsEventHandler(mapper, buffer, table="order_events")

    return mapper, buffer, sink, handler


class TestEndToEnd:
    """End-to-end integration tests."""

    @pytest.mark.asyncio
    async def test_full_pipeline(
        self,
        full_pipeline: tuple[
            EventToRowMapper, AnalyticsBuffer, InMemorySink, AnalyticsEventHandler
        ],
    ) -> None:
        _, buffer, sink, handler = full_pipeline

        schema = AnalyticsSchema(
            table_name="order_events",
            columns=[
                ColumnDef(name="event_type", type=ColumnType.STRING),
                ColumnDef(name="event_id", type=ColumnType.STRING),
                ColumnDef(name="occurred_at", type=ColumnType.STRING),
                ColumnDef(name="order_id", type=ColumnType.STRING),
                ColumnDef(name="total_amount", type=ColumnType.FLOAT, nullable=True),
                ColumnDef(name="reason", type=ColumnType.STRING, nullable=True),
            ],
        )
        await sink.initialize_dataset(schema)

        # Process events
        await handler.handle(
            OrderCreated(order_id="o1", total_amount=99.99, aggregate_id="o1")
        )
        await handler.handle(
            OrderCancelled(order_id="o2", reason="Out of stock", aggregate_id="o2")
        )
        # Unmapped events are silently skipped
        await handler.handle(UnmappedEvent(data="ignored"))

        await buffer.flush_all()

        rows = sink.get_rows("order_events")
        assert len(rows) == 2
        assert rows[0]["event_type"] == "OrderCreated"
        assert rows[0]["total_amount"] == 99.99
        assert rows[1]["event_type"] == "OrderCancelled"
        assert rows[1]["reason"] == "Out of stock"

    @pytest.mark.asyncio
    async def test_batch_size_auto_flush(
        self,
        full_pipeline: tuple[
            EventToRowMapper, AnalyticsBuffer, InMemorySink, AnalyticsEventHandler
        ],
    ) -> None:
        _, buffer, sink, handler = full_pipeline

        # batch_size is 10, so after 10 events the buffer flushes
        for i in range(10):
            await handler.handle(
                OrderCreated(
                    order_id=f"o{i}",
                    total_amount=float(i),
                    aggregate_id=f"o{i}",
                )
            )

        # Should have auto-flushed
        assert sink.row_count("order_events") == 10

    @pytest.mark.asyncio
    async def test_backfill_simulation(self) -> None:
        """Simulate backfill: batch-map historical events and push to sink."""
        sink = InMemorySink()
        mapper = EventToRowMapper()

        @mapper.register(OrderCreated)
        def map_order(event: OrderCreated) -> dict[str, object]:
            return {
                "event_date": event.occurred_at.strftime("%Y-%m-%d"),
                "order_id": event.order_id,
                "total_amount": event.total_amount,
            }

        # Simulate reading from event store
        historical_events = [
            OrderCreated(
                order_id=f"hist-{i}",
                total_amount=float(i * 5),
                aggregate_id=f"hist-{i}",
            )
            for i in range(50)
        ]

        # Map events and push in batches
        batch: list[dict[str, object]] = []
        for event in historical_events:
            result = mapper.map(event)
            if result is None:
                continue
            if isinstance(result, dict):
                batch.append(result)
            else:
                batch.extend(result)

        await sink.push_batch("orders", batch)
        assert sink.row_count("orders") == 50
