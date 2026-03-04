"""Tests for EventToRowMapper."""

from __future__ import annotations

from cqrs_ddd_analytics.mapper import EventToRowMapper

from .conftest import OrderCancelled, OrderCreated, UnmappedEvent


class TestEventToRowMapper:
    """Tests for EventToRowMapper."""

    def test_register_and_map_decorator(self) -> None:
        mapper = EventToRowMapper()

        @mapper.register(OrderCreated)
        def map_order(event: OrderCreated) -> dict[str, object]:
            return {"order_id": event.order_id, "total": event.total_amount}

        event = OrderCreated(order_id="o1", total_amount=50.0, aggregate_id="o1")
        result = mapper.map(event)
        assert result == {"order_id": "o1", "total": 50.0}

    def test_register_direct_call(self) -> None:
        mapper = EventToRowMapper()

        def map_order(event: OrderCreated) -> dict[str, object]:
            return {"id": event.order_id}

        mapper.register(OrderCreated, map_order)
        event = OrderCreated(order_id="o2", aggregate_id="o2")
        result = mapper.map(event)
        assert result == {"id": "o2"}

    def test_unmapped_event_returns_none(self) -> None:
        mapper = EventToRowMapper()
        event = UnmappedEvent(data="hello")
        assert mapper.map(event) is None

    def test_mapper_returns_list(self) -> None:
        mapper = EventToRowMapper()

        @mapper.register(OrderCreated)
        def map_order(event: OrderCreated) -> list[dict[str, object]]:
            return [
                {"field": "order_id", "value": event.order_id},
                {"field": "total", "value": event.total_amount},
            ]

        event = OrderCreated(order_id="o3", total_amount=10.0, aggregate_id="o3")
        result = mapper.map(event)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_registered_types(self) -> None:
        mapper = EventToRowMapper()
        mapper.register(OrderCreated, lambda e: {"id": e.order_id})
        mapper.register(OrderCancelled, lambda e: {"id": e.order_id})
        assert mapper.registered_types == frozenset({OrderCreated, OrderCancelled})

    def test_mapper_returning_none_skips(self) -> None:
        mapper = EventToRowMapper()

        @mapper.register(OrderCreated)
        def maybe_map(event: OrderCreated) -> dict[str, object] | None:
            if event.total_amount <= 0:
                return None
            return {"id": event.order_id}

        assert mapper.map(OrderCreated(order_id="o4", total_amount=0.0)) is None
        result = mapper.map(OrderCreated(order_id="o5", total_amount=10.0))
        assert result == {"id": "o5"}

    def test_decorator_returns_original_function(self) -> None:
        mapper = EventToRowMapper()

        @mapper.register(OrderCreated)
        def map_order(event: OrderCreated) -> dict[str, object]:
            return {"id": event.order_id}

        # Decorator should return the original function
        assert callable(map_order)
        result = map_order(OrderCreated(order_id="test"))
        assert result == {"id": "test"}
