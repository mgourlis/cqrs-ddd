"""Tests for the Sagas package — state, orchestration, registry, manager, worker, testing."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import ClassVar
from unittest.mock import AsyncMock

import pytest

from cqrs_ddd_advanced_core.adapters.memory import InMemorySagaRepository
from cqrs_ddd_advanced_core.exceptions import SagaConfigurationError, SagaStateError
from cqrs_ddd_advanced_core.sagas.bootstrap import SagaBootstrapResult, bootstrap_sagas
from cqrs_ddd_advanced_core.sagas.manager import SagaManager
from cqrs_ddd_advanced_core.sagas.orchestration import Saga, TCCStep
from cqrs_ddd_advanced_core.sagas.registry import SagaRegistry
from cqrs_ddd_advanced_core.sagas.state import (
    ReservationType,
    SagaState,
    SagaStatus,
    TCCPhase,
    TCCStepRecord,
)
from cqrs_ddd_advanced_core.sagas.worker import SagaRecoveryWorker
from cqrs_ddd_core.cqrs.command import Command
from cqrs_ddd_core.cqrs.event_dispatcher import EventDispatcher
from cqrs_ddd_core.cqrs.message_registry import MessageRegistry
from cqrs_ddd_core.domain.events import DomainEvent

# ═══════════════════════════════════════════════════════════════════════
# Fixtures / helpers
# ═══════════════════════════════════════════════════════════════════════


class OrderCreated(DomainEvent):
    order_id: str = ""


class PaymentReceived(DomainEvent):
    order_id: str = ""


class ShipOrder(Command[None]):
    order_id: str = ""


class CancelOrder(Command[None]):
    order_id: str = ""


class OrderSagaState(SagaState):
    """Custom saga state with an extra domain field."""

    items_reserved: bool = False


class OrderSaga(Saga[OrderSagaState]):
    """Concrete saga using explicit match/case dispatch."""

    state_class = OrderSagaState

    async def _handle_event(self, event: DomainEvent) -> None:
        match event:
            case OrderCreated():
                self.state.current_step = "awaiting_payment"
                self.dispatch(ShipOrder(order_id=event.order_id))
                self.add_compensation(
                    CancelOrder(order_id=event.order_id),
                    description="Cancel order on failure",
                )
            case PaymentReceived():
                self.state.current_step = "completed"
                self.state.items_reserved = True
                self.complete()


# ═══════════════════════════════════════════════════════════════════════
# SagaState tests
# ═══════════════════════════════════════════════════════════════════════


class TestSagaState:
    def test_default_fields(self) -> None:
        state = SagaState(id="s1")
        assert state.status == SagaStatus.PENDING
        assert state.version == 0
        assert state.current_step == "init"
        assert state.processed_event_ids == []
        assert state.compensation_stack == []
        assert state.metadata == {}
        assert state.correlation_id is None
        assert state.error is None
        assert state.retry_count == 0
        assert state.max_retries == 3
        assert state.suspended_at is None
        assert state.timeout_at is None
        assert state.completed_at is None
        assert state.failed_at is None
        assert not state.is_terminal

    def test_has_20_plus_fields(self) -> None:
        field_count = len(SagaState.model_fields)
        assert field_count >= 20, f"SagaState has {field_count} fields, needs ≥20"

    def test_idempotency(self) -> None:
        state = SagaState(id="s1")
        assert not state.is_event_processed("ev-1")
        state.mark_event_processed("ev-1")
        assert state.is_event_processed("ev-1")
        # Duplicate is no-op
        state.mark_event_processed("ev-1")
        assert state.processed_event_ids.count("ev-1") == 1

    def test_record_step(self) -> None:
        state = SagaState(id="s1")
        state.record_step("step_a", "SomeEvent", metadata={"key": "val"})
        assert state.current_step == "step_a"
        assert len(state.step_history) == 1
        assert state.step_history[0].step_name == "step_a"
        assert state.step_history[0].metadata == {"key": "val"}

    def test_is_terminal(self) -> None:
        state = SagaState(id="s1", status=SagaStatus.COMPLETED)
        assert state.is_terminal
        state2 = SagaState(id="s2", status=SagaStatus.FAILED)
        assert state2.is_terminal
        state3 = SagaState(id="s3", status=SagaStatus.RUNNING)
        assert not state3.is_terminal

    def test_touch_updates_timestamp(self) -> None:
        state = SagaState(id="s1")
        before = state.updated_at
        state.touch()
        assert state.updated_at >= before

    def test_serialization_roundtrip(self) -> None:
        state = SagaState(
            id="s1",
            saga_type="OrderSaga",
            status=SagaStatus.RUNNING,
            current_step="awaiting_payment",
            correlation_id="corr-1",
            metadata={"key": "value"},
        )
        data = state.model_dump()
        restored = SagaState.model_validate(data)
        assert restored.id == "s1"
        assert restored.saga_type == "OrderSaga"
        assert restored.status == SagaStatus.RUNNING
        assert restored.correlation_id == "corr-1"


# ═══════════════════════════════════════════════════════════════════════
# Saga orchestration tests
# ═══════════════════════════════════════════════════════════════════════


class TestSaga:
    @pytest.mark.asyncio()
    async def test_handle_event_dispatches_commands(self) -> None:
        state = OrderSagaState(id="saga-1")
        registry = MessageRegistry()
        saga = OrderSaga(state, registry)
        event = OrderCreated(order_id="ord-1")

        await saga.handle(event)

        cmds = saga.collect_commands()
        assert len(cmds) == 1
        assert isinstance(cmds[0], ShipOrder)
        assert state.current_step == "awaiting_payment"
        assert state.status == SagaStatus.RUNNING

    @pytest.mark.asyncio()
    async def test_idempotent_event_handling(self) -> None:
        state = OrderSagaState(id="saga-1")
        registry = MessageRegistry()
        saga = OrderSaga(state, registry)
        event = OrderCreated(order_id="ord-1")

        await saga.handle(event)
        saga.collect_commands()  # drain

        await saga.handle(event)  # duplicate
        assert len(saga.collect_commands()) == 0

    @pytest.mark.asyncio()
    async def test_complete_lifecycle(self) -> None:
        state = OrderSagaState(id="saga-1")
        registry = MessageRegistry()
        saga = OrderSaga(state, registry)

        await saga.handle(OrderCreated(order_id="ord-1"))
        saga.collect_commands()

        await saga.handle(PaymentReceived(order_id="ord-1"))
        assert state.status == SagaStatus.COMPLETED
        assert state.completed_at is not None
        assert state.items_reserved is True

    @pytest.mark.asyncio()
    async def test_terminal_state_ignores_events(self) -> None:
        state = OrderSagaState(id="saga-1", status=SagaStatus.COMPLETED)
        registry = MessageRegistry()
        saga = OrderSaga(state, registry)
        await saga.handle(OrderCreated(order_id="ord-1"))
        assert len(saga.collect_commands()) == 0

    @pytest.mark.asyncio()
    async def test_fail(self) -> None:
        state = OrderSagaState(id="saga-1")
        registry = MessageRegistry()
        saga = OrderSaga(state, registry)
        await saga.fail("something broke", compensate=False)
        assert state.status == SagaStatus.FAILED
        assert state.error == "something broke"
        assert state.failed_at is not None

    def test_suspend_and_resume(self) -> None:
        state = OrderSagaState(id="saga-1", status=SagaStatus.RUNNING)
        registry = MessageRegistry()
        saga = OrderSaga(state, registry)

        saga.suspend("waiting for approval", timeout=timedelta(hours=1))
        assert state.status == SagaStatus.SUSPENDED
        assert state.suspension_reason == "waiting for approval"
        assert state.timeout_at is not None

        saga.resume()
        assert state.status == SagaStatus.RUNNING
        assert state.suspension_reason is None
        assert state.timeout_at is None

    def test_resume_non_suspended_is_noop(self) -> None:
        state = OrderSagaState(id="saga-1", status=SagaStatus.RUNNING)
        registry = MessageRegistry()
        saga = OrderSaga(state, registry)
        saga.resume()  # should not crash
        assert state.status == SagaStatus.RUNNING

    @pytest.mark.asyncio()
    async def test_add_compensation(self) -> None:
        state = OrderSagaState(id="saga-1")
        registry = MessageRegistry()
        saga = OrderSaga(state, registry)
        await saga.handle(OrderCreated(order_id="ord-1"))
        assert len(state.compensation_stack) == 1
        assert state.compensation_stack[0].command_type == "CancelOrder"
        assert state.compensation_stack[0].description == "Cancel order on failure"

    @pytest.mark.asyncio()
    async def test_execute_compensations(self) -> None:
        state = OrderSagaState(id="saga-1")
        registry = MessageRegistry()
        # Register the command so hydration works
        registry.register_command("CancelOrder", CancelOrder)
        saga = OrderSaga(state, registry)
        await saga.handle(OrderCreated(order_id="ord-1"))
        saga.collect_commands()  # drain the ShipOrder

        await saga.execute_compensations()

        assert state.status == SagaStatus.COMPENSATED
        compensating_cmds = saga.collect_commands()
        assert len(compensating_cmds) == 1
        assert isinstance(compensating_cmds[0], CancelOrder)
        assert state.compensation_stack == []

    @pytest.mark.asyncio()
    async def test_on_timeout_default_fails_saga(self) -> None:
        state = OrderSagaState(
            id="saga-1",
            status=SagaStatus.SUSPENDED,
            suspension_reason="manual approval",
        )
        registry = MessageRegistry()
        saga = OrderSaga(state, registry)
        await saga.on_timeout()
        assert state.status == SagaStatus.FAILED
        assert "timed out" in state.error


# ═══════════════════════════════════════════════════════════════════════
# SagaRegistry tests
# ═══════════════════════════════════════════════════════════════════════


class TestSagaRegistry:
    def test_register_and_query(self) -> None:
        registry = SagaRegistry()
        registry.register(OrderCreated, OrderSaga)

        sagas = registry.get_sagas_for_event(OrderCreated)
        assert OrderSaga in sagas
        assert registry.get_saga_type("OrderSaga") is OrderSaga

    def test_multiple_sagas_for_same_event(self) -> None:
        class AnotherSaga(Saga[SagaState]):
            def _handle_event(self, event: DomainEvent) -> None:
                pass

        registry = SagaRegistry()
        registry.register(OrderCreated, OrderSaga)
        registry.register(OrderCreated, AnotherSaga)

        sagas = registry.get_sagas_for_event(OrderCreated)
        assert len(sagas) == 2

    def test_no_duplicate_registration(self) -> None:
        registry = SagaRegistry()
        registry.register(OrderCreated, OrderSaga)
        registry.register(OrderCreated, OrderSaga)  # duplicate

        sagas = registry.get_sagas_for_event(OrderCreated)
        assert len(sagas) == 1

    def test_unknown_event_returns_empty(self) -> None:
        registry = SagaRegistry()
        assert registry.get_sagas_for_event(PaymentReceived) == []

    def test_unknown_type_returns_none(self) -> None:
        registry = SagaRegistry()
        assert registry.get_saga_type("NonExistent") is None

    def test_clear(self) -> None:
        registry = SagaRegistry()
        registry.register(OrderCreated, OrderSaga)
        registry.clear()
        assert registry.get_sagas_for_event(OrderCreated) == []
        assert registry.get_saga_type("OrderSaga") is None


# ═══════════════════════════════════════════════════════════════════════
# InMemorySagaRepository tests
# ═══════════════════════════════════════════════════════════════════════


class TestInMemorySagaRepository:
    @pytest.mark.asyncio()
    async def test_save_and_load(self) -> None:
        repo = InMemorySagaRepository()
        state = SagaState(id="s1", saga_type="OrderSaga")
        await repo.add(state)

        loaded = await repo.get("s1")
        assert loaded is not None
        assert loaded.id == "s1"
        assert loaded.version == 1  # incremented on save

    @pytest.mark.asyncio()
    async def test_find_by_correlation_id(self) -> None:
        repo = InMemorySagaRepository()
        state = SagaState(id="s1", saga_type="OrderSaga", correlation_id="corr-1")
        await repo.add(state)

        found = await repo.find_by_correlation_id("corr-1", "OrderSaga")
        assert found is not None
        assert found.id == "s1"

        # Wrong saga type returns None
        not_found = await repo.find_by_correlation_id("corr-1", "OtherSaga")
        assert not_found is None

    @pytest.mark.asyncio()
    async def test_find_stalled_sagas(self) -> None:
        repo = InMemorySagaRepository()
        stalled = SagaState(
            id="s1",
            status=SagaStatus.RUNNING,
            pending_commands=[{"type_name": "Foo", "module_name": "bar", "data": {}}],
        )
        normal = SagaState(id="s2", status=SagaStatus.RUNNING)
        await repo.add(stalled)
        await repo.add(normal)

        result = await repo.find_stalled_sagas()
        assert len(result) == 1
        assert result[0].id == "s1"

    @pytest.mark.asyncio()
    async def test_find_expired_suspended_sagas(self) -> None:
        repo = InMemorySagaRepository()
        expired = SagaState(
            id="s1",
            status=SagaStatus.SUSPENDED,
            timeout_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        not_expired = SagaState(
            id="s2",
            status=SagaStatus.SUSPENDED,
            timeout_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        no_timeout = SagaState(id="s3", status=SagaStatus.SUSPENDED)
        await repo.add(expired)
        await repo.add(not_expired)
        await repo.add(no_timeout)

        result = await repo.find_expired_suspended_sagas()
        assert len(result) == 1
        assert result[0].id == "s1"

    @pytest.mark.asyncio()
    async def test_find_suspended_sagas(self) -> None:
        repo = InMemorySagaRepository()
        suspended = SagaState(id="s1", status=SagaStatus.SUSPENDED)
        running = SagaState(id="s2", status=SagaStatus.RUNNING)
        await repo.add(suspended)
        await repo.add(running)

        result = await repo.find_suspended_sagas()
        assert len(result) == 1
        assert result[0].id == "s1"

    @pytest.mark.asyncio()
    async def test_find_running_sagas_with_tcc_steps(self) -> None:
        repo = InMemorySagaRepository()
        with_tcc = SagaState(
            id="s1",
            status=SagaStatus.RUNNING,
            saga_type="OrderTCCSaga",
            metadata={"tcc_steps": [{"name": "hold", "phase": "TRYING"}]},
        )
        running_no_tcc = SagaState(id="s2", status=SagaStatus.RUNNING)
        await repo.add(with_tcc)
        await repo.add(running_no_tcc)

        result = await repo.find_running_sagas_with_tcc_steps()
        assert len(result) == 1
        assert result[0].id == "s1"


# ═══════════════════════════════════════════════════════════════════════
# SagaManager tests
# ═══════════════════════════════════════════════════════════════════════


class TestSagaManager:
    def _make_manager(
        self,
    ) -> tuple[SagaManager, InMemorySagaRepository, AsyncMock]:
        repo = InMemorySagaRepository()
        registry = SagaRegistry()
        registry.register(OrderCreated, OrderSaga)
        registry.register(PaymentReceived, OrderSaga)
        command_bus = AsyncMock()
        command_bus.send = AsyncMock()
        msg_registry = MessageRegistry()
        manager = SagaManager(
            repository=repo,
            registry=registry,
            command_bus=command_bus,
            message_registry=msg_registry,
        )
        return manager, repo, command_bus

    @pytest.mark.asyncio()
    async def test_handle_creates_saga(self) -> None:
        manager, repo, command_bus = self._make_manager()

        event = OrderCreated(order_id="ord-1", correlation_id="corr-1")
        await manager.handle(event)

        sagas = repo.all_sagas()
        assert len(sagas) == 1
        assert sagas[0].saga_type == "OrderSaga"
        assert sagas[0].correlation_id == "corr-1"
        command_bus.send.assert_called_once()

    @pytest.mark.asyncio()
    async def test_handle_continues_existing_saga(self) -> None:
        manager, repo, command_bus = self._make_manager()

        await manager.handle(OrderCreated(order_id="ord-1", correlation_id="corr-1"))
        await manager.handle(PaymentReceived(order_id="ord-1", correlation_id="corr-1"))

        saga_state = await repo.find_by_correlation_id("corr-1", "OrderSaga")
        assert saga_state is not None
        assert saga_state.status == SagaStatus.COMPLETED

    @pytest.mark.asyncio()
    async def test_handle_no_correlation_id_warns(self) -> None:
        manager, repo, _ = self._make_manager()
        event = OrderCreated(order_id="ord-1")  # no correlation_id
        await manager.handle(event)
        # Should not create any saga.
        assert len(repo.all_sagas()) == 0

    @pytest.mark.asyncio()
    async def test_handle_unregistered_event_is_noop(self) -> None:
        manager, repo, _ = self._make_manager()

        class UnknownEvent(DomainEvent):
            pass

        await manager.handle(UnknownEvent(correlation_id="corr-1"))
        assert len(repo.all_sagas()) == 0


# ═══════════════════════════════════════════════════════════════════════
# SagaManager start_saga tests
# ═══════════════════════════════════════════════════════════════════════


class TestSagaManagerStartSaga:
    @pytest.mark.asyncio()
    async def test_start_saga(self) -> None:
        repo = InMemorySagaRepository()
        registry = SagaRegistry()
        registry.register_type(OrderSaga)
        command_bus = AsyncMock()
        command_bus.send = AsyncMock()
        msg_registry = MessageRegistry()
        manager = SagaManager(
            repository=repo,
            registry=registry,
            command_bus=command_bus,
            message_registry=msg_registry,
        )

        event = OrderCreated(order_id="ord-1", correlation_id="corr-1")
        saga_id = await manager.start_saga(OrderSaga, event, "corr-1")

        assert saga_id is not None
        state = await repo.get(saga_id)
        assert state is not None
        assert state.saga_type == "OrderSaga"
        command_bus.send.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════
# SagaManager recovery / timeout tests
# ═══════════════════════════════════════════════════════════════════════


class TestSagaManagerRecovery:
    def _make_manager(
        self,
    ) -> tuple[SagaManager, InMemorySagaRepository, AsyncMock]:
        repo = InMemorySagaRepository()
        registry = SagaRegistry()
        registry.register(OrderCreated, OrderSaga)
        registry.register_type(OrderSaga)
        command_bus = AsyncMock()
        command_bus.send = AsyncMock()
        msg_registry = MessageRegistry()
        manager = SagaManager(
            repository=repo,
            registry=registry,
            command_bus=command_bus,
            message_registry=msg_registry,
        )
        return manager, repo, command_bus

    @pytest.mark.asyncio()
    async def test_recover_pending_sagas(self) -> None:
        manager, repo, command_bus = self._make_manager()

        # Simulate a stalled saga with a pending command.
        state = SagaState(
            id="s1",
            saga_type="OrderSaga",
            status=SagaStatus.RUNNING,
            pending_commands=[
                {
                    "type_name": "ShipOrder",
                    "module_name": __name__,
                    "data": {"order_id": "ord-1"},
                }
            ],
        )
        await repo.add(state)

        await manager.recover_pending_sagas()

        command_bus.send.assert_called_once()
        loaded = await repo.get("s1")
        assert loaded is not None
        assert loaded.pending_commands == []

    @pytest.mark.asyncio()
    async def test_recover_skips_already_dispatched_commands(self) -> None:
        """Recovery re-dispatches only commands with dispatched=False (or missing)."""
        manager, repo, command_bus = self._make_manager()

        # Stalled saga: first command already dispatched, second not.
        state = SagaState(
            id="s2",
            saga_type="OrderSaga",
            status=SagaStatus.RUNNING,
            pending_commands=[
                {
                    "type_name": "ShipOrder",
                    "module_name": __name__,
                    "data": {"order_id": "ord-a"},
                    "dispatched": True,  # already sent
                },
                {
                    "type_name": "ShipOrder",
                    "module_name": __name__,
                    "data": {"order_id": "ord-b"},
                    "dispatched": False,  # needs dispatch
                },
            ],
        )
        await repo.add(state)

        await manager.recover_pending_sagas()

        # Only the undispatched command should be sent.
        command_bus.send.assert_called_once()
        cmd = command_bus.send.call_args[0][0]
        assert cmd.order_id == "ord-b"

        loaded = await repo.get("s2")
        assert loaded is not None
        assert loaded.pending_commands == []

    @pytest.mark.asyncio()
    async def test_recover_backward_compat_missing_dispatched_key(self) -> None:
        """Legacy pending_commands without 'dispatched' are treated as undispatched."""
        manager, repo, command_bus = self._make_manager()

        state = SagaState(
            id="s3",
            saga_type="OrderSaga",
            status=SagaStatus.RUNNING,
            pending_commands=[
                {
                    "type_name": "ShipOrder",
                    "module_name": __name__,
                    "data": {"order_id": "ord-legacy"},
                    # no "dispatched" key - backward compat
                }
            ],
        )
        await repo.add(state)

        await manager.recover_pending_sagas()

        command_bus.send.assert_called_once()
        cmd = command_bus.send.call_args[0][0]
        assert cmd.order_id == "ord-legacy"
        loaded = await repo.get("s3")
        assert loaded is not None
        assert loaded.pending_commands == []

    @pytest.mark.asyncio()
    async def test_recover_respects_max_retries(self) -> None:
        """When retry_count >= max_retries, saga is failed and recovery is not attempted."""
        manager, repo, command_bus = self._make_manager()

        # Stalled saga with max_retries=2; we will fail recovery twice then hit limit
        state = SagaState(
            id="s-max-retries",
            saga_type="OrderSaga",
            status=SagaStatus.RUNNING,
            retry_count=0,
            max_retries=2,
            pending_commands=[
                {
                    "type_name": "ShipOrder",
                    "module_name": __name__,
                    "data": {"order_id": "ord-1"},
                    "dispatched": False,
                }
            ],
        )
        await repo.add(state)

        # First attempt: retry_count becomes 1, then recovery fails (send raises)
        command_bus.send.side_effect = RuntimeError("Bus unavailable")
        await manager.recover_pending_sagas()

        loaded = await repo.get("s-max-retries")
        assert loaded is not None
        assert loaded.retry_count == 1
        assert loaded.status == SagaStatus.RUNNING
        assert len(loaded.pending_commands) == 1

        # Second attempt: retry_count becomes 2, recovery fails again
        await manager.recover_pending_sagas()

        loaded = await repo.get("s-max-retries")
        assert loaded is not None
        assert loaded.retry_count == 2
        assert loaded.status == SagaStatus.RUNNING

        # Third attempt: retry_count (2) >= max_retries (2) -> saga is failed, no dispatch
        command_bus.send.reset_mock()
        command_bus.send.side_effect = None  # would succeed now
        await manager.recover_pending_sagas()

        loaded = await repo.get("s-max-retries")
        assert loaded is not None
        assert loaded.status == SagaStatus.FAILED
        assert "max_retries" in (loaded.error or "")
        # No dispatch was attempted (saga was failed instead)
        command_bus.send.assert_not_called()

    @pytest.mark.asyncio()
    async def test_recover_resets_retry_count_on_success(self) -> None:
        """On successful recovery, retry_count is reset to 0."""
        manager, repo, command_bus = self._make_manager()

        state = SagaState(
            id="s-reset",
            saga_type="OrderSaga",
            status=SagaStatus.RUNNING,
            retry_count=2,
            max_retries=5,
            pending_commands=[
                {
                    "type_name": "ShipOrder",
                    "module_name": __name__,
                    "data": {"order_id": "ord-1"},
                    "dispatched": False,
                }
            ],
        )
        await repo.add(state)

        await manager.recover_pending_sagas()

        loaded = await repo.get("s-reset")
        assert loaded is not None
        assert loaded.retry_count == 0
        assert loaded.pending_commands == []

    @pytest.mark.asyncio()
    async def test_process_timeouts(self) -> None:
        manager, repo, command_bus = self._make_manager()

        state = SagaState(
            id="s1",
            saga_type="OrderSaga",
            status=SagaStatus.SUSPENDED,
            suspension_reason="manual approval",
            timeout_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        await repo.add(state)

        await manager.process_timeouts()

        loaded = await repo.get("s1")
        assert loaded is not None
        assert loaded.status == SagaStatus.FAILED
        assert "timed out" in (loaded.error or "")

    @pytest.mark.asyncio()
    async def test_process_tcc_timeouts(self) -> None:
        """process_tcc_timeouts cancels expired TIME_BASED TCC steps."""
        repo = InMemorySagaRepository()
        registry = SagaRegistry()
        registry.register_type(OrderTCCSaga)
        msg_registry = MessageRegistry()
        msg_registry.register_command("VoidPayment", VoidPayment)
        msg_registry.register_command("ReleaseInventory", ReleaseInventory)
        command_bus = AsyncMock()
        command_bus.send = AsyncMock()
        manager = SagaManager(
            repository=repo,
            registry=registry,
            command_bus=command_bus,
            message_registry=msg_registry,
        )

        # Create RUNNING saga with expired TIME_BASED TCC step
        expired_record = TCCStepRecord(
            name="hold_payment",
            phase=TCCPhase.TRIED,
            reservation_type=ReservationType.TIME_BASED,
            timeout_at=datetime.now(timezone.utc) - timedelta(minutes=5),
            cancel_command_type="VoidPayment",
            cancel_command_module=__name__,
            cancel_command_data={"order_id": "ord-1"},
        )
        state = SagaState(
            id="s1",
            saga_type="OrderTCCSaga",
            status=SagaStatus.RUNNING,
            metadata={"tcc_steps": [expired_record.model_dump()]},
        )
        await repo.add(state)

        await manager.process_tcc_timeouts()

        command_bus.send.assert_called_once()
        loaded = await repo.get("s1")
        assert loaded is not None
        assert loaded.status == SagaStatus.COMPENSATING


# ═══════════════════════════════════════════════════════════════════════
# SagaRecoveryWorker tests
# ═══════════════════════════════════════════════════════════════════════


class TestSagaRecoveryWorker:
    @pytest.mark.asyncio()
    async def test_run_once(self) -> None:
        repo = InMemorySagaRepository()
        registry = SagaRegistry()
        registry.register_type(OrderSaga)
        command_bus = AsyncMock()
        command_bus.send = AsyncMock()
        msg_registry = MessageRegistry()
        manager = SagaManager(
            repository=repo,
            registry=registry,
            command_bus=command_bus,
            message_registry=msg_registry,
        )

        # Place a stalled saga
        state = SagaState(
            id="s1",
            saga_type="OrderSaga",
            status=SagaStatus.RUNNING,
            pending_commands=[
                {
                    "type_name": "ShipOrder",
                    "module_name": __name__,
                    "data": {"order_id": "ord-1"},
                }
            ],
        )
        await repo.add(state)

        worker = SagaRecoveryWorker(manager, poll_interval=1.0)
        await worker.run_once()

        loaded = await repo.get("s1")
        assert loaded is not None
        assert loaded.pending_commands == []

    @pytest.mark.asyncio()
    async def test_start_and_stop(self) -> None:
        manager = AsyncMock()
        manager.process_timeouts = AsyncMock()
        manager.process_tcc_timeouts = AsyncMock()
        manager.recover_pending_sagas = AsyncMock()
        worker = SagaRecoveryWorker(manager, poll_interval=0.01)

        await worker.start()
        await asyncio.sleep(0.05)  # let one cycle run
        await worker.stop()

        manager.process_timeouts.assert_called()
        manager.process_tcc_timeouts.assert_called()
        manager.recover_pending_sagas.assert_called()


# ═══════════════════════════════════════════════════════════════════════
# on() — command mapper tests
# ═══════════════════════════════════════════════════════════════════════


class ConfirmPayment(Command[None]):
    order_id: str = ""


class CancelReservation(Command[None]):
    order_id: str = ""


class DeclarativeSaga(Saga[SagaState]):
    """Saga using the command-mapper style of on()."""

    listens_to: ClassVar[list[type[DomainEvent]]] = [OrderCreated, PaymentReceived]

    def __init__(self, state: SagaState, registry: MessageRegistry) -> None:
        super().__init__(state, registry)
        self.on(
            OrderCreated,
            send=lambda e: ShipOrder(order_id=e.order_id),
            step="shipping",
            compensate=lambda e: CancelOrder(order_id=e.order_id),
            compensate_description="Cancel order on failure",
        )
        self.on(
            PaymentReceived,
            send=lambda e: ConfirmPayment(order_id=e.order_id),
            step="completed",
            complete=True,
        )


class TestOnCommandMapper:
    @pytest.mark.asyncio()
    async def test_send_dispatches_command(self) -> None:
        state = SagaState(id="saga-1")
        saga = DeclarativeSaga(state, MessageRegistry())
        await saga.handle(OrderCreated(order_id="ord-1"))

        cmds = saga.collect_commands()
        assert len(cmds) == 1
        assert isinstance(cmds[0], ShipOrder)
        assert cmds[0].order_id == "ord-1"

    @pytest.mark.asyncio()
    async def test_step_sets_current_step(self) -> None:
        state = SagaState(id="saga-1")
        saga = DeclarativeSaga(state, MessageRegistry())
        await saga.handle(OrderCreated(order_id="ord-1"))
        assert state.current_step == "shipping"

    @pytest.mark.asyncio()
    async def test_compensate_adds_to_stack(self) -> None:
        state = SagaState(id="saga-1")
        saga = DeclarativeSaga(state, MessageRegistry())
        await saga.handle(OrderCreated(order_id="ord-1"))
        assert len(state.compensation_stack) == 1
        assert state.compensation_stack[0].command_type == "CancelOrder"
        assert state.compensation_stack[0].description == "Cancel order on failure"

    @pytest.mark.asyncio()
    async def test_complete_flag_completes_saga(self) -> None:
        state = SagaState(id="saga-1")
        saga = DeclarativeSaga(state, MessageRegistry())
        await saga.handle(OrderCreated(order_id="ord-1"))
        saga.collect_commands()
        await saga.handle(PaymentReceived(order_id="ord-1"))
        assert state.status == SagaStatus.COMPLETED

    @pytest.mark.asyncio()
    async def test_handler_style_backward_compat(self) -> None:
        """on(EventType, handler=fn) still works."""

        class HandlerSaga(Saga[SagaState]):
            listens_to: ClassVar[list[type[DomainEvent]]] = [OrderCreated]

            def __init__(self, s: SagaState, r: MessageRegistry) -> None:
                super().__init__(s, r)
                self.on(OrderCreated, handler=self._on_order)

            def _on_order(self, event: DomainEvent) -> None:
                self.state.current_step = "handled"
                self.dispatch(ShipOrder(order_id="x"))

        state = SagaState(id="saga-1")
        saga = HandlerSaga(state, MessageRegistry())
        await saga.handle(OrderCreated(order_id="ord-1"))
        assert state.current_step == "handled"
        assert len(saga.collect_commands()) == 1

    def test_send_and_handler_raises(self) -> None:
        state = SagaState(id="saga-1")
        saga = Saga(state, MessageRegistry())
        with pytest.raises(SagaConfigurationError, match="Cannot provide both"):
            saga.on(OrderCreated, handler=lambda e: None, send=lambda e: ShipOrder())

    def test_neither_send_nor_handler_raises(self) -> None:
        state = SagaState(id="saga-1")
        saga = Saga(state, MessageRegistry())
        with pytest.raises(SagaConfigurationError, match="Must provide either"):
            saga.on(OrderCreated)


# ═══════════════════════════════════════════════════════════════════════
# TCC integrated into base Saga tests
# ═══════════════════════════════════════════════════════════════════════


class ReserveInventory(Command[None]):
    order_id: str = ""


class ConfirmInventory(Command[None]):
    order_id: str = ""


class ReleaseInventory(Command[None]):
    order_id: str = ""


class HoldPayment(Command[None]):
    order_id: str = ""


class CapturePayment(Command[None]):
    order_id: str = ""


class VoidPayment(Command[None]):
    order_id: str = ""


class InventoryReserved(DomainEvent):
    order_id: str = ""


class PaymentHeld(DomainEvent):
    order_id: str = ""


class InventoryConfirmed(DomainEvent):
    order_id: str = ""


class PaymentCaptured(DomainEvent):
    order_id: str = ""


class InventoryFailed(DomainEvent):
    order_id: str = ""
    reason: str = ""


class PaymentFailed(DomainEvent):
    order_id: str = ""
    reason: str = ""


class OrderTCCSaga(Saga[SagaState]):
    """TCC saga using the integrated add_tcc_step API."""

    listens_to: ClassVar[list[type[DomainEvent]]] = [
        InventoryReserved,
        PaymentHeld,
        InventoryConfirmed,
        PaymentCaptured,
        InventoryFailed,
        PaymentFailed,
    ]

    def __init__(self, state: SagaState, registry: MessageRegistry) -> None:
        super().__init__(state, registry)
        self.add_tcc_step(
            TCCStep(
                name="reserve_inventory",
                try_command=ReserveInventory(order_id="ord-1"),
                confirm_command=ConfirmInventory(order_id="ord-1"),
                cancel_command=ReleaseInventory(order_id="ord-1"),
            )
        )
        self.add_tcc_step(
            TCCStep(
                name="hold_payment",
                try_command=HoldPayment(order_id="ord-1"),
                confirm_command=CapturePayment(order_id="ord-1"),
                cancel_command=VoidPayment(order_id="ord-1"),
            )
        )
        # Register event handlers using on()
        self.on(
            InventoryReserved,
            handler=lambda e: self.mark_step_tried("reserve_inventory"),
        )
        self.on(PaymentHeld, handler=lambda e: self.mark_step_tried("hold_payment"))
        self.on(
            InventoryConfirmed,
            handler=lambda e: self.mark_step_confirmed("reserve_inventory"),
        )
        self.on(
            PaymentCaptured, handler=lambda e: self.mark_step_confirmed("hold_payment")
        )
        self.on(
            InventoryFailed,
            handler=lambda e: self.mark_step_failed("reserve_inventory", e.reason),
        )
        self.on(
            PaymentFailed,
            handler=lambda e: self.mark_step_failed("hold_payment", e.reason),
        )

    def start(self) -> None:
        self.begin_tcc()


class TestTCCIntegrated:
    def _make_saga(self) -> tuple[OrderTCCSaga, SagaState, MessageRegistry]:
        state = SagaState(id="tcc-1")
        registry = MessageRegistry()
        registry.register_command("ConfirmInventory", ConfirmInventory)
        registry.register_command("CapturePayment", CapturePayment)
        registry.register_command("ReleaseInventory", ReleaseInventory)
        registry.register_command("VoidPayment", VoidPayment)
        saga = OrderTCCSaga(state, registry)
        return saga, state, registry

    def test_begin_tcc_dispatches_try_commands(self) -> None:
        saga, state, _ = self._make_saga()
        saga.start()

        cmds = saga.collect_commands()
        assert len(cmds) == 2
        assert isinstance(cmds[0], ReserveInventory)
        assert isinstance(cmds[1], HoldPayment)
        assert state.status == SagaStatus.RUNNING
        assert state.current_step == "trying"

    def test_begin_tcc_no_steps_raises(self) -> None:
        state = SagaState(id="tcc-1")
        saga = Saga(state, MessageRegistry())
        with pytest.raises(SagaStateError, match="No TCC steps"):
            saga.begin_tcc()

    def test_begin_tcc_already_started_raises(self) -> None:
        """Calling begin_tcc() twice raises."""
        saga, state, _ = self._make_saga()
        saga.start()
        with pytest.raises(SagaStateError, match="TCC already started"):
            saga.begin_tcc()

    @pytest.mark.asyncio()
    async def test_mark_step_tried_partial(self) -> None:
        saga, state, _ = self._make_saga()
        saga.start()
        saga.collect_commands()

        await saga.handle(InventoryReserved(order_id="ord-1"))
        # Only one step tried — no confirm yet
        assert saga.get_tcc_step_phase("reserve_inventory") == TCCPhase.TRIED
        assert saga.get_tcc_step_phase("hold_payment") == TCCPhase.TRYING
        assert state.status == SagaStatus.RUNNING

    @pytest.mark.asyncio()
    async def test_all_tried_dispatches_confirms(self) -> None:
        saga, state, _ = self._make_saga()
        saga.start()
        saga.collect_commands()

        await saga.handle(InventoryReserved(order_id="ord-1"))
        saga.collect_commands()
        await saga.handle(PaymentHeld(order_id="ord-1"))

        cmds = saga.collect_commands()
        assert len(cmds) == 2
        assert isinstance(cmds[0], ConfirmInventory)
        assert isinstance(cmds[1], CapturePayment)
        assert state.current_step == "confirming"

    @pytest.mark.asyncio()
    async def test_all_confirmed_completes_saga(self) -> None:
        saga, state, _ = self._make_saga()
        saga.start()
        saga.collect_commands()

        await saga.handle(InventoryReserved(order_id="ord-1"))
        saga.collect_commands()
        await saga.handle(PaymentHeld(order_id="ord-1"))
        saga.collect_commands()
        await saga.handle(InventoryConfirmed(order_id="ord-1"))
        saga.collect_commands()
        await saga.handle(PaymentCaptured(order_id="ord-1"))

        assert state.status == SagaStatus.COMPLETED
        assert all(
            rec.phase == TCCPhase.CONFIRMED for rec in saga.get_tcc_step_records()
        )

    @pytest.mark.asyncio()
    async def test_step_failure_dispatches_cancels(self) -> None:
        saga, state, _ = self._make_saga()
        saga.start()
        saga.collect_commands()

        # Inventory reserved OK
        await saga.handle(InventoryReserved(order_id="ord-1"))
        saga.collect_commands()

        # Payment fails — should cancel the TRIED inventory step
        await saga.handle(PaymentFailed(order_id="ord-1", reason="insufficient funds"))

        assert state.status == SagaStatus.COMPENSATING
        cmds = saga.collect_commands()
        cancel_types = [type(c).__name__ for c in cmds]
        # Inventory was TRIED -> gets ReleaseInventory cancel
        assert "ReleaseInventory" in cancel_types

    @pytest.mark.asyncio()
    async def test_mark_step_cancelled_terminal_state(self) -> None:
        saga, state, _ = self._make_saga()
        saga.start()
        saga.collect_commands()

        await saga.handle(InventoryFailed(order_id="ord-1", reason="fail"))
        saga.collect_commands()

        saga.mark_step_cancelled("reserve_inventory")
        saga.mark_step_cancelled("hold_payment")

        records = saga.get_tcc_step_records()
        for rec in records:
            assert rec.phase in (TCCPhase.CANCELLED, TCCPhase.FAILED)
        assert state.status == SagaStatus.COMPENSATED

    def test_duplicate_step_name_raises(self) -> None:
        state = SagaState(id="tcc-1")
        saga = Saga(state, MessageRegistry())
        saga.add_tcc_step(
            TCCStep(
                name="step_a",
                try_command=ShipOrder(order_id="x"),
                confirm_command=ShipOrder(order_id="x"),
                cancel_command=CancelOrder(order_id="x"),
            )
        )
        with pytest.raises(SagaConfigurationError, match="already registered"):
            saga.add_tcc_step(
                TCCStep(
                    name="step_a",
                    try_command=ShipOrder(order_id="x"),
                    confirm_command=ShipOrder(order_id="x"),
                    cancel_command=CancelOrder(order_id="x"),
                )
            )


# ═══════════════════════════════════════════════════════════════════════
# TCC — ReservationType tests
# ═══════════════════════════════════════════════════════════════════════


class TestTCCReservationTypes:
    def test_resource_based_no_timeout(self) -> None:
        """RESOURCE steps have no timeout_at in their records."""
        state = SagaState(id="tcc-1")
        registry = MessageRegistry()
        saga = Saga(state, registry)
        saga.add_tcc_step(
            TCCStep(
                name="reserve",
                try_command=ReserveInventory(order_id="ord-1"),
                confirm_command=ConfirmInventory(order_id="ord-1"),
                cancel_command=ReleaseInventory(order_id="ord-1"),
                reservation_type=ReservationType.RESOURCE,
            )
        )
        saga.begin_tcc()
        records = saga.get_tcc_step_records()
        assert records[0].reservation_type == ReservationType.RESOURCE
        assert records[0].timeout_at is None

    def test_time_based_records_timeout(self) -> None:
        """TIME_BASED steps get a timeout_at in their records."""
        state = SagaState(id="tcc-1")
        registry = MessageRegistry()
        saga = Saga(state, registry)
        saga.add_tcc_step(
            TCCStep(
                name="hold",
                try_command=HoldPayment(order_id="ord-1"),
                confirm_command=CapturePayment(order_id="ord-1"),
                cancel_command=VoidPayment(order_id="ord-1"),
                reservation_type=ReservationType.TIME_BASED,
                timeout=timedelta(minutes=15),
            )
        )
        before = datetime.now(timezone.utc)
        saga.begin_tcc()
        records = saga.get_tcc_step_records()
        assert records[0].reservation_type == ReservationType.TIME_BASED
        assert records[0].timeout_at is not None
        assert records[0].timeout_at >= before + timedelta(minutes=14)

    def test_time_based_requires_timeout(self) -> None:
        """TIME_BASED without timeout raises SagaConfigurationError."""
        with pytest.raises(SagaConfigurationError, match="requires a timeout"):
            TCCStep(
                name="bad",
                try_command=HoldPayment(order_id="x"),
                confirm_command=CapturePayment(order_id="x"),
                cancel_command=VoidPayment(order_id="x"),
                reservation_type=ReservationType.TIME_BASED,
            )

    def test_check_tcc_timeouts_cancels_expired(self) -> None:
        """check_tcc_timeouts auto-cancels expired TIME_BASED steps."""
        state = SagaState(id="tcc-1")
        registry = MessageRegistry()
        registry.register_command("VoidPayment", VoidPayment)
        saga = Saga(state, registry)
        saga.add_tcc_step(
            TCCStep(
                name="hold",
                try_command=HoldPayment(order_id="ord-1"),
                confirm_command=CapturePayment(order_id="ord-1"),
                cancel_command=VoidPayment(order_id="ord-1"),
                reservation_type=ReservationType.TIME_BASED,
                timeout=timedelta(minutes=15),
            )
        )
        saga.begin_tcc()
        saga.collect_commands()

        # Set TRIED phase and backdate timeout_at into the past
        records = saga._load_tcc_records()
        updated = records[0].model_copy(
            update={
                "phase": TCCPhase.TRIED,
                "timeout_at": datetime.now(timezone.utc) - timedelta(seconds=10),
            }
        )
        saga._save_tcc_records([updated])

        expired = saga.check_tcc_timeouts()
        assert expired == ["hold"]
        assert state.status == SagaStatus.COMPENSATING
        cmds = saga.collect_commands()
        cancel_types = [type(c).__name__ for c in cmds]
        assert "VoidPayment" in cancel_types

    def test_check_tcc_timeouts_ignores_resource(self) -> None:
        """RESOURCE steps are never auto-cancelled by timeout."""
        state = SagaState(id="tcc-1")
        registry = MessageRegistry()
        saga = Saga(state, registry)
        saga.add_tcc_step(
            TCCStep(
                name="reserve",
                try_command=ReserveInventory(order_id="ord-1"),
                confirm_command=ConfirmInventory(order_id="ord-1"),
                cancel_command=ReleaseInventory(order_id="ord-1"),
                reservation_type=ReservationType.RESOURCE,
            )
        )
        saga.begin_tcc()
        saga.collect_commands()

        expired = saga.check_tcc_timeouts()
        assert expired == []

    def test_mixed_step_types(self) -> None:
        """RESOURCE + TIME_BASED steps in same saga."""
        state = SagaState(id="tcc-1")
        registry = MessageRegistry()
        saga = Saga(state, registry)
        saga.add_tcc_step(
            TCCStep(
                name="reserve",
                try_command=ReserveInventory(order_id="ord-1"),
                confirm_command=ConfirmInventory(order_id="ord-1"),
                cancel_command=ReleaseInventory(order_id="ord-1"),
                reservation_type=ReservationType.RESOURCE,
            )
        )
        saga.add_tcc_step(
            TCCStep(
                name="hold",
                try_command=HoldPayment(order_id="ord-1"),
                confirm_command=CapturePayment(order_id="ord-1"),
                cancel_command=VoidPayment(order_id="ord-1"),
                reservation_type=ReservationType.TIME_BASED,
                timeout=timedelta(minutes=10),
            )
        )
        saga.begin_tcc()
        records = saga.get_tcc_step_records()
        assert len(records) == 2
        assert records[0].reservation_type == ReservationType.RESOURCE
        assert records[0].timeout_at is None
        assert records[1].reservation_type == ReservationType.TIME_BASED
        assert records[1].timeout_at is not None


# ═══════════════════════════════════════════════════════════════════════
# Listened Events (auto-discovery) tests
# ═══════════════════════════════════════════════════════════════════════


class ShipmentConfirmed(DomainEvent):
    order_id: str = ""


class DeclarativeOrderSaga(Saga[OrderSagaState]):
    """Saga using on() mapping — events declared via listens_to."""

    state_class = OrderSagaState
    listens_to: ClassVar[list[type[DomainEvent]]] = [
        OrderCreated,
        PaymentReceived,
        ShipmentConfirmed,
    ]

    def __init__(
        self, state: OrderSagaState, message_registry: MessageRegistry | None = None
    ) -> None:
        super().__init__(state, message_registry)
        self.on(
            OrderCreated,
            send=lambda e: ShipOrder(order_id=e.order_id),
            step="awaiting_payment",
        )
        self.on(
            PaymentReceived,
            handler=lambda e: (
                setattr(self.state, "items_reserved", True)
                or self.state.__setattr__("current_step", "awaiting_shipment")
            ),
        )
        self.on(ShipmentConfirmed, handler=lambda e: self.complete())


class TestListenedEvents:
    def test_base_saga_returns_empty_list(self) -> None:
        """Base Saga.listened_events() returns [] by default."""
        assert Saga.listened_events() == []

    def test_auto_discovers_from_on_registrations(self) -> None:
        """listened_events() returns events from listens_to declaration."""
        events = DeclarativeOrderSaga.listened_events()
        assert OrderCreated in events
        assert PaymentReceived in events
        assert ShipmentConfirmed in events
        assert len(events) == 3

    def test_imperative_saga_returns_empty(self) -> None:
        """Imperative saga (no on() calls) auto-discovers empty list."""
        events = OrderSaga.listened_events()
        assert events == []

    def test_manual_override_still_works(self) -> None:
        """Subclass can still override listened_events() manually."""

        class ManualSaga(Saga[SagaState]):
            state_class = SagaState

            @classmethod
            def listened_events(cls) -> list[type[DomainEvent]]:
                return [OrderCreated]

        assert ManualSaga.listened_events() == [OrderCreated]

    @pytest.mark.asyncio()
    async def test_saga_works_without_message_registry(self) -> None:
        """Saga can be constructed without message_registry (optional)."""
        state = OrderSagaState(id="s-1")
        saga = DeclarativeOrderSaga(state)
        event = OrderCreated(order_id="ord-1", event_id="e-1")
        await saga.handle(event)
        assert saga.state.current_step == "awaiting_payment"

    def test_message_registry_required_for_compensation(self) -> None:
        """Operations needing message_registry raise SagaStateError if None."""
        state = SagaState(id="s-1")
        saga = Saga(state)
        with pytest.raises(SagaStateError, match="message_registry is required"):
            saga._require_message_registry()


# ═══════════════════════════════════════════════════════════════════════
# register_saga() bulk registration tests
# ═══════════════════════════════════════════════════════════════════════


class TestRegisterSaga:
    def test_register_saga_bulk(self) -> None:
        """register_saga() registers for all listened_events at once."""
        registry = SagaRegistry()
        registry.register_saga(DeclarativeOrderSaga)

        assert DeclarativeOrderSaga in registry.get_sagas_for_event(OrderCreated)
        assert DeclarativeOrderSaga in registry.get_sagas_for_event(PaymentReceived)
        assert DeclarativeOrderSaga in registry.get_sagas_for_event(ShipmentConfirmed)
        assert registry.get_saga_type("DeclarativeOrderSaga") is DeclarativeOrderSaga

    def test_register_saga_no_events_warns(self) -> None:
        """register_saga() with imperative saga registers by name only."""
        registry = SagaRegistry()
        registry.register_saga(OrderSaga)  # OrderSaga uses _handle_event override
        assert registry.get_saga_type("OrderSaga") is OrderSaga
        # No on() calls → auto-discovery returns empty.
        assert registry.get_sagas_for_event(OrderCreated) == []

    def test_registered_event_types_property(self) -> None:
        """registered_event_types returns all event types with sagas."""
        registry = SagaRegistry()
        registry.register_saga(DeclarativeOrderSaga)
        event_types = registry.registered_event_types
        assert set(event_types) == {OrderCreated, PaymentReceived, ShipmentConfirmed}

    def test_register_saga_idempotent(self) -> None:
        """Calling register_saga twice doesn't create duplicates."""
        registry = SagaRegistry()
        registry.register_saga(DeclarativeOrderSaga)
        registry.register_saga(DeclarativeOrderSaga)
        # Should have exactly 1 entry per event, not 2.
        assert len(registry.get_sagas_for_event(OrderCreated)) == 1


# ═══════════════════════════════════════════════════════════════════════
# bind_to() EventDispatcher integration tests
# ═══════════════════════════════════════════════════════════════════════


class TestBindTo:
    def _make_setup(
        self,
    ) -> tuple[SagaManager, EventDispatcher, InMemorySagaRepository, AsyncMock]:
        repo = InMemorySagaRepository()
        registry = SagaRegistry()
        registry.register_saga(DeclarativeOrderSaga)
        command_bus = AsyncMock()
        command_bus.send = AsyncMock()
        msg_registry = MessageRegistry()
        dispatcher = EventDispatcher()
        manager = SagaManager(
            repository=repo,
            registry=registry,
            command_bus=command_bus,
            message_registry=msg_registry,
        )
        return manager, dispatcher, repo, command_bus

    def test_bind_to_registers_all_events(self) -> None:
        """bind_to() registers the manager as handler for all saga events."""
        manager, dispatcher, _, _ = self._make_setup()
        manager.bind_to(dispatcher)

        handlers = dispatcher.get_registered_handlers()
        assert OrderCreated in handlers
        assert PaymentReceived in handlers
        assert ShipmentConfirmed in handlers

    @pytest.mark.asyncio()
    async def test_bind_to_events_route_to_saga(self) -> None:
        """Events dispatched through EventDispatcher reach the saga."""
        manager, dispatcher, repo, command_bus = self._make_setup()
        manager.bind_to(dispatcher)

        event = OrderCreated(order_id="ord-1", correlation_id="corr-1")
        await dispatcher.dispatch([event])

        sagas = repo.all_sagas()
        assert len(sagas) == 1
        assert sagas[0].saga_type == "DeclarativeOrderSaga"
        command_bus.send.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════
# SagaManager handle routes via registry tests
# ═══════════════════════════════════════════════════════════════════════


class TestSagaManagerHandleRouting:
    @pytest.mark.asyncio()
    async def test_handle_routes_via_registry(self) -> None:
        """handle() routes events via SagaRegistry."""
        repo = InMemorySagaRepository()
        registry = SagaRegistry()
        registry.register_saga(DeclarativeOrderSaga)
        command_bus = AsyncMock()
        command_bus.send = AsyncMock()
        msg_registry = MessageRegistry()
        manager = SagaManager(
            repository=repo,
            registry=registry,
            command_bus=command_bus,
            message_registry=msg_registry,
        )

        event = OrderCreated(order_id="ord-1", correlation_id="corr-1")
        await manager.handle(event)

        sagas = repo.all_sagas()
        assert len(sagas) == 1
        assert sagas[0].saga_type == "DeclarativeOrderSaga"

    @pytest.mark.asyncio()
    async def test_handle_unregistered_event_is_noop(self) -> None:
        """handle() ignores events with no registered saga."""
        repo = InMemorySagaRepository()
        registry = SagaRegistry()
        command_bus = AsyncMock()
        msg_registry = MessageRegistry()
        manager = SagaManager(
            repository=repo,
            registry=registry,
            command_bus=command_bus,
            message_registry=msg_registry,
        )

        event = OrderCreated(order_id="ord-1", correlation_id="corr-1")
        await manager.handle(event)
        assert len(repo.all_sagas()) == 0

    @pytest.mark.asyncio()
    async def test_bind_to_event_dispatcher(self) -> None:
        """Manager can bind_to EventDispatcher."""
        repo = InMemorySagaRepository()
        registry = SagaRegistry()
        registry.register_saga(DeclarativeOrderSaga)
        command_bus = AsyncMock()
        command_bus.send = AsyncMock()
        msg_registry = MessageRegistry()
        dispatcher = EventDispatcher()
        manager = SagaManager(
            repository=repo,
            registry=registry,
            command_bus=command_bus,
            message_registry=msg_registry,
        )
        manager.bind_to(dispatcher)

        event = OrderCreated(order_id="ord-1", correlation_id="corr-1")
        await dispatcher.dispatch([event])

        sagas = repo.all_sagas()
        assert len(sagas) == 1


# ═══════════════════════════════════════════════════════════════════════
# bootstrap_sagas() tests
# ═══════════════════════════════════════════════════════════════════════


class TestBootstrapSagas:
    def test_bootstrap_creates_manager(self) -> None:
        """bootstrap_sagas() creates SagaManager."""
        repo = InMemorySagaRepository()
        command_bus = AsyncMock()
        msg_registry = MessageRegistry()

        result = bootstrap_sagas(
            sagas=[DeclarativeOrderSaga],
            repository=repo,
            command_bus=command_bus,
            message_registry=msg_registry,
        )

        assert isinstance(result, SagaBootstrapResult)
        assert isinstance(result.manager, SagaManager)
        assert result.worker is None
        # Registry has the saga registered.
        assert DeclarativeOrderSaga in result.registry.get_sagas_for_event(OrderCreated)

    def test_bootstrap_with_dispatcher(self) -> None:
        """bootstrap_sagas() binds manager to event dispatcher."""
        repo = InMemorySagaRepository()
        command_bus = AsyncMock()
        msg_registry = MessageRegistry()
        dispatcher = EventDispatcher()

        bootstrap_sagas(
            sagas=[DeclarativeOrderSaga],
            repository=repo,
            command_bus=command_bus,
            message_registry=msg_registry,
            event_dispatcher=dispatcher,
        )

        handlers = dispatcher.get_registered_handlers()
        assert OrderCreated in handlers
        assert PaymentReceived in handlers
        assert ShipmentConfirmed in handlers

    def test_bootstrap_with_recovery_worker(self) -> None:
        """bootstrap_sagas() creates recovery worker when interval specified."""
        repo = InMemorySagaRepository()
        command_bus = AsyncMock()
        msg_registry = MessageRegistry()

        result = bootstrap_sagas(
            sagas=[DeclarativeOrderSaga],
            repository=repo,
            command_bus=command_bus,
            message_registry=msg_registry,
            recovery_interval=30,
        )

        assert result.worker is not None
        assert isinstance(result.worker, SagaRecoveryWorker)
        assert result.worker._poll_interval == 30.0

    def test_bootstrap_with_existing_registry(self) -> None:
        """bootstrap_sagas() can use a pre-existing registry."""
        repo = InMemorySagaRepository()
        command_bus = AsyncMock()
        msg_registry = MessageRegistry()
        existing_registry = SagaRegistry()

        result = bootstrap_sagas(
            sagas=[DeclarativeOrderSaga],
            repository=repo,
            command_bus=command_bus,
            message_registry=msg_registry,
            registry=existing_registry,
        )

        assert result.registry is existing_registry
        assert DeclarativeOrderSaga in existing_registry.get_sagas_for_event(
            OrderCreated
        )

    @pytest.mark.asyncio()
    async def test_bootstrap_end_to_end(self) -> None:
        """Full bootstrap → dispatch event → saga processes it."""
        repo = InMemorySagaRepository()
        command_bus = AsyncMock()
        command_bus.send = AsyncMock()
        msg_registry = MessageRegistry()
        dispatcher = EventDispatcher()

        bootstrap_sagas(
            sagas=[DeclarativeOrderSaga],
            repository=repo,
            command_bus=command_bus,
            message_registry=msg_registry,
            event_dispatcher=dispatcher,
        )

        # Dispatch event through the event dispatcher.
        event = OrderCreated(order_id="ord-1", correlation_id="corr-1")
        await dispatcher.dispatch([event])

        sagas = repo.all_sagas()
        assert len(sagas) == 1
        assert sagas[0].saga_type == "DeclarativeOrderSaga"
        assert sagas[0].status == SagaStatus.RUNNING
        command_bus.send.assert_called_once()
