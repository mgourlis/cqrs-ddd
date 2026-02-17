"""Tests for the Undo/Redo package."""

from __future__ import annotations

from typing import Any

import pytest

from cqrs_ddd_advanced_core.ports.undo import IUndoExecutor
from cqrs_ddd_advanced_core.undo import UndoExecutorRegistry, UndoService
from cqrs_ddd_core.domain.events import DomainEvent

# ============================================================================
# Test Events
# ============================================================================


class OrderCreated(DomainEvent):
    """Test event."""

    order_id: str
    amount: float = 100.0


class OrderCancelled(DomainEvent):
    """Compensating event."""

    order_id: str


# ============================================================================
# Mock Executors
# ============================================================================


class OrderCreatedUndoExecutor(IUndoExecutor[OrderCreated]):
    """Mock executor for undoing OrderCreated."""

    @property
    def event_type(self) -> str:
        return "OrderCreated"

    async def can_undo(self, event: OrderCreated) -> bool:
        # Simple rule: can undo if amount < 1000
        return event.amount < 1000.0

    async def undo(self, event: OrderCreated) -> list[DomainEvent]:
        return [
            OrderCancelled(
                order_id=event.order_id,
                correlation_id=event.correlation_id,
            )
        ]

    async def redo(
        self, event: OrderCreated, undo_event: Any = None
    ) -> list[DomainEvent]:
        return [event]


class FailingUndoExecutor(IUndoExecutor[DomainEvent]):
    """Mock executor that always fails."""

    @property
    def event_type(self) -> str:
        return "FailingEvent"

    async def can_undo(self, event: DomainEvent) -> bool:
        return True

    async def undo(self, event: DomainEvent) -> list[DomainEvent]:
        raise RuntimeError("Intentional failure")

    async def redo(
        self, event: DomainEvent, undo_event: Any = None
    ) -> list[DomainEvent]:
        raise RuntimeError("Intentional failure")


# ============================================================================
# Tests: UndoExecutorRegistry
# ============================================================================


class TestUndoExecutorRegistry:
    """Test the UndoExecutorRegistry."""

    def test_register_executor(self) -> None:
        """Executor should be registered and retrievable."""
        registry = UndoExecutorRegistry()
        executor = OrderCreatedUndoExecutor()

        registry.register(executor)

        found = registry.get("OrderCreated")
        assert found is executor

    def test_has_executor_true(self) -> None:
        """has_executor should return True for registered executor."""
        registry = UndoExecutorRegistry()
        executor = OrderCreatedUndoExecutor()
        registry.register(executor)

        assert registry.has_executor("OrderCreated")

    def test_has_executor_false(self) -> None:
        """has_executor should return False for unregistered executor."""
        registry = UndoExecutorRegistry()

        assert not registry.has_executor("UnknownEvent")

    def test_get_unregistered_returns_none(self) -> None:
        """get() should return None for unregistered event type."""
        registry = UndoExecutorRegistry()

        result = registry.get("UnknownEvent")

        assert result is None

    def test_list_executors(self) -> None:
        """list_executors should return all registered executors."""
        registry = UndoExecutorRegistry()
        executor1 = OrderCreatedUndoExecutor()
        executor2 = OrderCreatedUndoExecutor()

        registry.register(executor1)
        registry.register(executor2)

        executors = registry.list_executors()

        assert len(executors) == 1
        assert executors["OrderCreated"] is executor2  # Last one wins

    def test_clear_removes_all(self) -> None:
        """clear() should remove all registered executors."""
        registry = UndoExecutorRegistry()
        executor = OrderCreatedUndoExecutor()
        registry.register(executor)

        registry.clear()

        assert not registry.has_executor("OrderCreated")


# ============================================================================
# Tests: UndoService
# ============================================================================


class TestUndoService:
    """Test the UndoService."""

    @pytest.mark.asyncio()
    async def test_undo_event_with_executor(self) -> None:
        """Service should undo event when executor is registered."""
        registry = UndoExecutorRegistry()
        executor = OrderCreatedUndoExecutor()
        registry.register(executor)
        service = UndoService(registry)

        event = OrderCreated(order_id="ord-123", amount=500.0)

        undo_events = await service.undo(event)

        assert len(undo_events) == 1
        assert isinstance(undo_events[0], OrderCancelled)
        assert undo_events[0].order_id == "ord-123"

    @pytest.mark.asyncio()
    async def test_undo_respects_business_rules(self) -> None:
        """Service should respect can_undo() check."""
        registry = UndoExecutorRegistry()
        executor = OrderCreatedUndoExecutor()
        registry.register(executor)
        service = UndoService(registry)

        # High amount => can_undo returns False
        event = OrderCreated(order_id="ord-456", amount=2000.0)

        undo_events = await service.undo(event)

        assert undo_events == []

    @pytest.mark.asyncio()
    async def test_undo_unregistered_event_raises(self) -> None:
        """Service should raise if executor not registered."""
        registry = UndoExecutorRegistry()
        service = UndoService(registry)

        event = OrderCreated(order_id="ord-789", amount=100.0)

        with pytest.raises(ValueError, match="No UndoExecutor"):
            await service.undo(event)

    @pytest.mark.asyncio()
    async def test_undo_executor_failure_raises(self) -> None:
        """Service should re-raise executor exceptions."""
        registry = UndoExecutorRegistry()
        executor = FailingUndoExecutor()
        registry.register(executor)
        service = UndoService(registry)

        from cqrs_ddd_core.domain.events import DomainEvent

        class FailingEvent(DomainEvent):
            pass

        event = FailingEvent()

        with pytest.raises(RuntimeError, match="Intentional failure"):
            await service.undo(event)

    @pytest.mark.asyncio()
    async def test_redo_event_with_executor(self) -> None:
        """Service should redo event when executor is registered."""
        registry = UndoExecutorRegistry()
        executor = OrderCreatedUndoExecutor()
        registry.register(executor)
        service = UndoService(registry)

        event = OrderCreated(order_id="ord-123", amount=500.0)
        undo_event = OrderCancelled(order_id="ord-123")

        redo_events = await service.redo(event, undo_event)

        assert len(redo_events) == 1
        assert redo_events[0] is event

    @pytest.mark.asyncio()
    async def test_redo_unregistered_event_raises(self) -> None:
        """Service should raise if executor not registered for redo."""
        registry = UndoExecutorRegistry()
        service = UndoService(registry)

        event = OrderCreated(order_id="ord-789", amount=100.0)
        undo_event = OrderCancelled(order_id="ord-789")

        with pytest.raises(ValueError, match="No UndoExecutor"):
            await service.redo(event, undo_event)

    @pytest.mark.asyncio()
    async def test_redo_executor_failure_raises(self) -> None:
        """Service should re-raise executor exceptions during redo."""
        registry = UndoExecutorRegistry()
        executor = FailingUndoExecutor()
        registry.register(executor)
        service = UndoService(registry)

        from cqrs_ddd_core.domain.events import DomainEvent

        class FailingEvent(DomainEvent):
            pass

        event = FailingEvent()
        undo_event = FailingEvent()

        with pytest.raises(RuntimeError, match="Intentional failure"):
            await service.redo(event, undo_event)
