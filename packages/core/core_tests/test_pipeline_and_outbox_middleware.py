"""Tests for middleware pipeline building and OutboxMiddleware."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from cqrs_ddd_core.cqrs.response import CommandResponse
from cqrs_ddd_core.domain.events import DomainEvent
from cqrs_ddd_core.middleware.outbox import OutboxMiddleware
from cqrs_ddd_core.middleware.pipeline import build_pipeline
from cqrs_ddd_core.ports.middleware import IMiddleware


# Test fixtures
class OrderCreated(DomainEvent):
    """Test event."""

    order_id: str = ""


class PaymentProcessed(DomainEvent):
    """Another test event."""

    transaction_id: str = ""


class TrackingMiddleware(IMiddleware):
    """Test middleware that tracks calls."""

    def __init__(self, name: str):
        self.name = name
        self.calls: list[str] = []

    async def __call__(self, message, next_handler):
        self.calls.append(f"{self.name}_before")
        result = await next_handler(message)
        self.calls.append(f"{self.name}_after")
        return result


@pytest.mark.asyncio
class TestBuildPipeline:
    """Test middleware pipeline construction."""

    async def test_build_pipeline_with_no_middleware(self) -> None:
        """Pipeline with empty middleware list calls handler directly."""
        handler_called = False

        async def handler(msg):
            nonlocal handler_called
            handler_called = True
            return "result"

        pipeline = build_pipeline([], handler)

        result = await pipeline("test_message")

        assert handler_called
        assert result == "result"

    async def test_build_pipeline_with_single_middleware(self) -> None:
        """Pipeline with single middleware wraps handler."""
        mw = TrackingMiddleware("mw1")

        async def handler(msg):
            return f"handled: {msg}"

        pipeline = build_pipeline([mw], handler)

        result = await pipeline("test")

        assert result == "handled: test"
        assert mw.calls == ["mw1_before", "mw1_after"]

    async def test_build_pipeline_execution_order_lifo(self) -> None:
        """Middleware executes in LIFO order (first in list is outermost)."""
        execution_order = []

        class OrderTracker(IMiddleware):
            def __init__(self, name: str):
                self.name = name

            async def __call__(self, message, next_handler):
                execution_order.append(f"{self.name}_before")
                result = await next_handler(message)
                execution_order.append(f"{self.name}_after")
                return result

        mw1 = OrderTracker("mw1")
        mw2 = OrderTracker("mw2")
        mw3 = OrderTracker("mw3")

        async def handler(msg):
            execution_order.append("handler")
            return "result"

        pipeline = build_pipeline([mw1, mw2, mw3], handler)

        await pipeline("test")

        # Expected order: mw1_before, mw2_before, mw3_before, handler, mw3_after, mw2_after, mw1_after
        assert execution_order == [
            "mw1_before",
            "mw2_before",
            "mw3_before",
            "handler",
            "mw3_after",
            "mw2_after",
            "mw1_after",
        ]

    async def test_build_pipeline_middleware_can_modify_message(self) -> None:
        """Middleware can modify message before passing to next handler."""

        class ModifyingMiddleware(IMiddleware):
            async def __call__(self, message, next_handler):
                modified_msg = f"modified_{message}"
                return await next_handler(modified_msg)

        mw = ModifyingMiddleware()

        async def handler(msg):
            return msg

        pipeline = build_pipeline([mw], handler)

        result = await pipeline("original")

        assert result == "modified_original"

    async def test_build_pipeline_middleware_can_modify_result(self) -> None:
        """Middleware can modify result from handler."""

        class ModifyingMiddleware(IMiddleware):
            async def __call__(self, message, next_handler):
                result = await next_handler(message)
                return f"wrapped_{result}"

        mw = ModifyingMiddleware()

        async def handler(msg):
            return "result"

        pipeline = build_pipeline([mw], handler)

        result = await pipeline("test")

        assert result == "wrapped_result"

    async def test_build_pipeline_with_multiple_middleware_layers(self) -> None:
        """Each middleware wraps the next in chain."""
        execution_order = []

        class OrderTrackingMiddleware(IMiddleware):
            def __init__(self, name: str):
                self.name = name

            async def __call__(self, message, next_handler):
                execution_order.append(f"{self.name}_start")
                result = await next_handler(message)
                execution_order.append(f"{self.name}_end")
                return result

        mw1 = OrderTrackingMiddleware("outer")
        mw2 = OrderTrackingMiddleware("middle")
        mw3 = OrderTrackingMiddleware("inner")

        async def handler(msg):
            execution_order.append("handler")
            return "result"

        pipeline = build_pipeline([mw1, mw2, mw3], handler)

        await pipeline("test")

        # Verify LIFO execution order
        assert execution_order == [
            "outer_start",
            "middle_start",
            "inner_start",
            "handler",
            "inner_end",
            "middle_end",
            "outer_end",
        ]


@pytest.mark.asyncio
class TestOutboxMiddleware:
    """Test OutboxMiddleware event publishing."""

    @pytest.fixture
    def mock_outbox(self):
        """Mock outbox publisher."""
        return AsyncMock()

    @pytest.fixture
    def outbox_middleware(self, mock_outbox):
        """Create OutboxMiddleware with mock outbox."""
        return OutboxMiddleware(outbox=mock_outbox)

    async def test_publishes_events_from_command_response(
        self, outbox_middleware, mock_outbox
    ) -> None:
        """OutboxMiddleware publishes events from CommandResponse."""
        event1 = OrderCreated(aggregate_id="order-123", order_id="order-123")
        event2 = PaymentProcessed(aggregate_id="order-123", transaction_id="tx-456")

        response = CommandResponse(result="order-123", events=[event1, event2])

        async def handler(msg):
            return response

        await outbox_middleware("test_message", handler)

        # Verify both events were published
        assert mock_outbox.publish.call_count == 2
        # Check first event
        call1 = mock_outbox.publish.call_args_list[0]
        assert call1[0][0] == "OrderCreated"  # topic
        assert call1[0][1] == event1  # event
        # Check second event
        call2 = mock_outbox.publish.call_args_list[1]
        assert call2[0][0] == "PaymentProcessed"  # topic
        assert call2[0][1] == event2  # event

    async def test_uses_event_type_name_as_topic(
        self, outbox_middleware, mock_outbox
    ) -> None:
        """OutboxMiddleware uses event class name as topic."""
        event = OrderCreated(aggregate_id="order-123", order_id="order-123")
        response = CommandResponse(result="order-123", events=[event])

        async def handler(msg):
            return response

        await outbox_middleware("test_message", handler)

        # Verify topic is event class name
        call = mock_outbox.publish.call_args_list[0]
        assert call[0][0] == "OrderCreated"

    async def test_passthrough_for_non_command_response(
        self, outbox_middleware, mock_outbox
    ) -> None:
        """OutboxMiddleware passes through non-CommandResponse results."""

        async def handler(msg):
            return "simple_result"

        result = await outbox_middleware("test_message", handler)

        assert result == "simple_result"
        mock_outbox.publish.assert_not_called()

    async def test_returns_original_command_response(
        self, outbox_middleware, mock_outbox
    ) -> None:
        """OutboxMiddleware returns original CommandResponse after publishing."""
        event = OrderCreated(aggregate_id="order-123", order_id="order-123")
        response = CommandResponse(result="order-123", events=[event])

        async def handler(msg):
            return response

        result = await outbox_middleware("test_message", handler)

        assert result == response
        assert result.result == "order-123"
        assert result.events == [event]

    async def test_handles_empty_events_list(
        self, outbox_middleware, mock_outbox
    ) -> None:
        """OutboxMiddleware handles CommandResponse with no events."""
        response = CommandResponse(result="order-123", events=[])

        async def handler(msg):
            return response

        result = await outbox_middleware("test_message", handler)

        assert result == response
        mock_outbox.publish.assert_not_called()

    async def test_publishes_each_event_separately(
        self, outbox_middleware, mock_outbox
    ) -> None:
        """OutboxMiddleware publishes events one by one."""
        events = [
            OrderCreated(aggregate_id="order-1", order_id="order-1"),
            OrderCreated(aggregate_id="order-2", order_id="order-2"),
            OrderCreated(aggregate_id="order-3", order_id="order-3"),
        ]
        response = CommandResponse(result="success", events=events)

        async def handler(msg):
            return response

        await outbox_middleware("test_message", handler)

        # Verify each event was published separately
        assert mock_outbox.publish.call_count == 3
        for i, call in enumerate(mock_outbox.publish.call_args_list):
            assert call[0][0] == "OrderCreated"
            assert call[0][1] == events[i]

    async def test_middleware_in_pipeline_integration(self, mock_outbox) -> None:
        """OutboxMiddleware works correctly in full pipeline."""
        outbox_mw = OutboxMiddleware(outbox=mock_outbox)

        event = OrderCreated(aggregate_id="order-123", order_id="order-123")
        response = CommandResponse(result="order-123", events=[event])

        async def handler(msg):
            return response

        # Build pipeline with outbox middleware
        pipeline = build_pipeline([outbox_mw], handler)

        result = await pipeline("test_message")

        # Verify result and outbox publishing
        assert isinstance(result, CommandResponse)
        assert mock_outbox.publish.call_count == 1
