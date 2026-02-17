"""Tests for SagaBuilder — fluent API for saga creation."""

from __future__ import annotations

from datetime import timedelta
from typing import ClassVar

import pytest

from cqrs_ddd_advanced_core.exceptions import SagaConfigurationError
from cqrs_ddd_advanced_core.sagas.builder import SagaBuilder
from cqrs_ddd_advanced_core.sagas.orchestration import Saga, TCCStep
from cqrs_ddd_advanced_core.sagas.state import SagaState, SagaStatus
from cqrs_ddd_core.cqrs.command import Command
from cqrs_ddd_core.domain.events import DomainEvent


# Test fixtures
class EventA(DomainEvent):
    value: str = ""


class EventB(DomainEvent):
    value: str = ""


class EventC(DomainEvent):
    value: str = ""


class CommandX(Command[None]):
    value: str = ""


class CommandY(Command[None]):
    value: str = ""


class CommandZ(Command[None]):
    value: str = ""


class CustomSagaState(SagaState):
    custom_field: str = "default"


class TestSagaBuilderBasics:
    """Test basic builder functionality."""

    def test_build_creates_saga_subclass(self) -> None:
        """build() returns a Saga subclass with correct name."""
        MySaga = SagaBuilder("MySaga").on(EventA, complete=True).build()

        assert issubclass(MySaga, Saga)
        assert MySaga.__name__ == "MySaga"

    def test_build_sets_listens_to(self) -> None:
        """build() sets listens_to from registered events."""
        MySaga = (
            SagaBuilder("MySaga")
            .on(EventA, complete=True)
            .on(EventB, complete=True)
            .build()
        )

        assert hasattr(MySaga, "listens_to")
        assert EventA in MySaga.listens_to
        assert EventB in MySaga.listens_to
        assert len(MySaga.listens_to) == 2

    def test_with_state_class(self) -> None:
        """with_state_class() sets custom state class."""
        MySaga = (
            SagaBuilder("MySaga")
            .with_state_class(CustomSagaState)
            .on(EventA, complete=True)
            .build()
        )

        assert MySaga.state_class == CustomSagaState

    def test_with_max_retries(self) -> None:
        """with_max_retries() is applied to saga instances."""
        MySaga = (
            SagaBuilder("MySaga")
            .with_max_retries(10)
            .on(EventA, complete=True)
            .build()
        )

        state = SagaState(id="saga-1")
        saga = MySaga(state)
        assert saga.state.max_retries == 10

    def test_empty_builder_builds_successfully(self) -> None:
        """build() without any event registrations is allowed (empty listens_to)."""
        MySaga = SagaBuilder("EmptySaga").on(EventA, complete=True).build()
        assert MySaga.listens_to == [EventA]


class TestSagaBuilderActions:
    """Test different action types in .on() method."""

    @pytest.mark.asyncio
    async def test_send_action(self) -> None:
        """on() with send dispatches a command."""
        dispatched = []

        MySaga = (
            SagaBuilder("MySaga")
            .on(EventA, send=lambda e: CommandX(value=e.value))
            .build()
        )

        state = SagaState(id="saga-1")
        saga = MySaga(state)
        saga.dispatch = lambda cmd: dispatched.append(cmd)  # type: ignore
        await saga.handle(EventA(value="test"))

        assert len(dispatched) == 1
        assert isinstance(dispatched[0], CommandX)
        assert dispatched[0].value == "test"

    @pytest.mark.asyncio
    async def test_send_all_action(self) -> None:
        """on() with send_all dispatches multiple commands."""
        dispatched = []

        MySaga = (
            SagaBuilder("MySaga")
            .on(
                EventA,
                send_all=lambda e: [CommandX(value=e.value), CommandY(value=e.value)],
            )
            .build()
        )

        state = SagaState(id="saga-1")
        saga = MySaga(state)
        saga.dispatch = lambda cmd: dispatched.append(cmd)  # type: ignore
        await saga.handle(EventA(value="multi"))

        assert len(dispatched) == 2
        assert isinstance(dispatched[0], CommandX)
        assert isinstance(dispatched[1], CommandY)

    @pytest.mark.asyncio
    async def test_complete_action(self) -> None:
        """on() with complete=True marks saga as completed."""
        MySaga = SagaBuilder("MySaga").on(EventA, complete=True).build()

        state = SagaState(id="saga-1")
        saga = MySaga(state)
        await saga.handle(EventA())

        assert saga.state.status == SagaStatus.COMPLETED
        assert saga.state.completed_at is not None

    @pytest.mark.asyncio
    async def test_fail_action(self) -> None:
        """on() with fail marks saga as failed."""
        MySaga = SagaBuilder("MySaga").on(EventA, fail="Test failure").build()

        state = SagaState(id="saga-1")
        saga = MySaga(state)
        await saga.handle(EventA())

        assert saga.state.status == SagaStatus.FAILED
        assert saga.state.error == "Test failure"
        assert saga.state.failed_at is not None

    @pytest.mark.asyncio
    async def test_suspend_action(self) -> None:
        """on() with suspend pauses the saga."""
        MySaga = (
            SagaBuilder("MySaga")
            .on(EventA, suspend="Needs review", suspend_timeout=timedelta(hours=1))
            .build()
        )

        state = SagaState(id="saga-1")
        saga = MySaga(state)
        await saga.handle(EventA())

        assert saga.state.status == SagaStatus.SUSPENDED
        assert saga.state.suspension_reason == "Needs review"
        assert saga.state.timeout_at is not None

    @pytest.mark.asyncio
    async def test_resume_action(self) -> None:
        """on() with resume=True resumes a suspended saga."""
        MySaga = (
            SagaBuilder("MySaga")
            .on(EventA, suspend="Paused")
            .on(EventB, resume=True, complete=True)
            .build()
        )

        state = SagaState(id="saga-1")
        saga = MySaga(state)
        await saga.handle(EventA())
        assert saga.state.status == SagaStatus.SUSPENDED

        await saga.handle(EventB())
        assert saga.state.status == SagaStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_step_action(self) -> None:
        """on() with step sets current_step."""
        MySaga = (
            SagaBuilder("MySaga")
            .on(EventA, step="step1", send=lambda e: CommandX())
            .on(EventB, step="step2", complete=True)
            .build()
        )

        state = SagaState(id="saga-1")
        saga = MySaga(state)
        saga.dispatch = lambda cmd: None  # type: ignore

        await saga.handle(EventA())
        assert saga.state.current_step == "step1"

        await saga.handle(EventB())
        assert saga.state.current_step == "step2"

    @pytest.mark.asyncio
    async def test_compensate_action(self) -> None:
        """on() with compensate adds compensation to stack."""
        MySaga = (
            SagaBuilder("MySaga")
            .on(
                EventA,
                send=lambda e: CommandX(),
                compensate=lambda e: CommandY(),
                compensate_description="Undo action",
            )
            .build()
        )

        state = SagaState(id="saga-1")
        saga = MySaga(state)
        saga.dispatch = lambda cmd: None  # type: ignore

        await saga.handle(EventA())

        assert len(saga.state.compensation_stack) == 1
        assert saga.state.compensation_stack[0].description == "Undo action"

    @pytest.mark.asyncio
    async def test_custom_handler_action(self) -> None:
        """on() with handler executes custom logic."""
        called = []

        async def custom_handler(event: DomainEvent) -> None:
            called.append(event)

        MySaga = SagaBuilder("MySaga").on(EventA, handler=custom_handler).build()

        state = SagaState(id="saga-1")
        saga = MySaga(state)
        await saga.handle(EventA(value="custom"))

        assert len(called) == 1
        assert called[0].value == "custom"


class TestSagaBuilderTCC:
    """Test TCC (Try-Confirm-Cancel) pattern support."""

    def test_with_tcc_step(self) -> None:
        """with_tcc_step() registers TCC steps."""
        step1 = TCCStep(
            name="payment",
            try_command=CommandX(),
            confirm_command=CommandY(),
            cancel_command=CommandZ(),
        )

        MySaga = (
            SagaBuilder("MySaga")
            .with_tcc_step(step1)
            .on_tcc_begin(EventA)
            .on_tcc_tried("payment", EventB)
            .on_tcc_confirmed("payment", EventC)
            .build()
        )

        # Verify TCC begin event is in listens_to
        assert EventA in MySaga.listens_to

    @pytest.mark.asyncio
    async def test_on_tcc_begin_triggers_try_commands(self) -> None:
        """on_tcc_begin() triggers begin_tcc() which dispatches try commands."""
        dispatched = []

        step1 = TCCStep(
            name="inventory",
            try_command=CommandX(value="try"),
            confirm_command=CommandY(value="confirm"),
            cancel_command=CommandZ(value="cancel"),
        )

        MySaga = (
            SagaBuilder("MySaga")
            .with_tcc_step(step1)
            .on_tcc_begin(EventA)
            .on_tcc_tried("inventory", EventB)
            .on_tcc_confirmed("inventory", EventC)
            .build()
        )

        state = SagaState(id="saga-1")
        saga = MySaga(state)
        saga.dispatch = lambda cmd: dispatched.append(cmd)  # type: ignore

        await saga.handle(EventA())

        # begin_tcc() should dispatch try commands
        assert len(dispatched) == 1
        assert isinstance(dispatched[0], CommandX)
        assert dispatched[0].value == "try"

    def test_tcc_without_begin_raises_error(self) -> None:
        """TCC steps without on_tcc_begin() raises configuration error."""
        step1 = TCCStep(
            name="payment",
            try_command=CommandX(),
            confirm_command=CommandY(),
            cancel_command=CommandZ(),
        )

        with pytest.raises(SagaConfigurationError, match="on_tcc_begin.*not called"):
            SagaBuilder("MySaga").with_tcc_step(step1).build()

    def test_tcc_begin_without_steps_raises_error(self) -> None:
        """on_tcc_begin() without TCC steps raises configuration error."""
        with pytest.raises(
            SagaConfigurationError, match="no TCC steps are registered"
        ):
            SagaBuilder("MySaga").on_tcc_begin(EventA).build()

    def test_tcc_tried_unknown_step_raises_error(self) -> None:
        """on_tcc_tried() with unknown step name raises configuration error."""
        step1 = TCCStep(
            name="payment",
            try_command=CommandX(),
            confirm_command=CommandY(),
            cancel_command=CommandZ(),
        )

        with pytest.raises(SagaConfigurationError, match="unknown.*step"):
            (
                SagaBuilder("MySaga")
                .with_tcc_step(step1)
                .on_tcc_begin(EventA)
                .on_tcc_tried("inventory", EventB)  # Wrong name
                .build()
            )


class TestSagaBuilderValidation:
    """Test validation rules."""

    def test_handler_mutually_exclusive_with_actions(self) -> None:
        """handler is mutually exclusive with other action parameters."""
        async def handler(e: DomainEvent) -> None:
            pass

        with pytest.raises(SagaConfigurationError, match="mutually exclusive"):
            SagaBuilder("MySaga").on(EventA, handler=handler, complete=True).build()

    def test_send_and_send_all_mutually_exclusive(self) -> None:
        """send and send_all are mutually exclusive."""
        with pytest.raises(SagaConfigurationError, match="mutually exclusive"):
            (
                SagaBuilder("MySaga")
                .on(EventA, send=lambda e: CommandX(), send_all=lambda e: [CommandY()])
                .build()
            )

    def test_suspend_mutually_exclusive_with_dispatch(self) -> None:
        """suspend is mutually exclusive with send/send_all/complete/fail."""
        with pytest.raises(SagaConfigurationError, match="mutually exclusive"):
            (
                SagaBuilder("MySaga")
                .on(EventA, suspend="Paused", send=lambda e: CommandX())
                .build()
            )

    def test_fail_mutually_exclusive_with_dispatch(self) -> None:
        """fail is mutually exclusive with send/send_all/complete/suspend."""
        with pytest.raises(SagaConfigurationError, match="mutually exclusive"):
            (
                SagaBuilder("MySaga")
                .on(EventA, fail="Failed", send=lambda e: CommandX())
                .build()
            )

    def test_suspend_timeout_requires_suspend(self) -> None:
        """suspend_timeout requires suspend parameter."""
        with pytest.raises(SagaConfigurationError, match="requires 'suspend'"):
            (
                SagaBuilder("MySaga")
                .on(EventA, suspend_timeout=timedelta(hours=1), complete=True)
                .build()
            )

    def test_at_least_one_action_required(self) -> None:
        """At least one action parameter is required."""
        with pytest.raises(SagaConfigurationError, match="At least one action"):
            SagaBuilder("MySaga").on(EventA).build()

    def test_duplicate_event_registration_raises_error(self) -> None:
        """Duplicate event registration raises configuration error."""
        with pytest.raises(SagaConfigurationError, match="Duplicate event"):
            (
                SagaBuilder("MySaga")
                .on(EventA, step="step1", send=lambda e: CommandX())
                .on(EventA, step="step2", complete=True)  # Duplicate!
                .build()
            )

    def test_duplicate_tcc_begin_raises_error(self) -> None:
        """Calling on_tcc_begin() twice raises configuration error."""
        step1 = TCCStep(
            name="payment",
            try_command=CommandX(),
            confirm_command=CommandY(),
            cancel_command=CommandZ(),
        )

        with pytest.raises(SagaConfigurationError, match="only be called once"):
            (
                SagaBuilder("MySaga")
                .with_tcc_step(step1)
                .on_tcc_begin(EventA)
                .on_tcc_begin(EventB)  # Duplicate!
            )


class TestSagaBuilderIntegration:
    """Integration tests with multiple events and actions."""

    @pytest.mark.asyncio
    async def test_multi_event_saga_flow(self) -> None:
        """Complex saga with multiple events and actions."""
        dispatched = []

        MySaga = (
            SagaBuilder("OrderSaga")
            .with_max_retries(5)
            .on(
                EventA,  # Order created
                step="reserving",
                send=lambda e: CommandX(value="reserve"),
                compensate=lambda e: CommandY(value="cancel"),
            )
            .on(
                EventB,  # Payment received
                step="shipping",
                send=lambda e: CommandX(value="ship"),
            )
            .on(
                EventC,  # Order shipped
                step="completed",
                complete=True,
            )
            .build()
        )

        state = SagaState(id="saga-1")
        saga = MySaga(state)
        saga.dispatch = lambda cmd: dispatched.append(cmd)  # type: ignore

        # Step 1: Order created
        await saga.handle(EventA(value="order1"))
        assert saga.state.current_step == "reserving"
        assert len(dispatched) == 1
        assert dispatched[0].value == "reserve"
        assert len(saga.state.compensation_stack) == 1

        # Step 2: Payment received
        await saga.handle(EventB(value="payment1"))
        assert saga.state.current_step == "shipping"
        assert len(dispatched) == 2
        assert dispatched[1].value == "ship"

        # Step 3: Order shipped
        await saga.handle(EventC())
        assert saga.state.status == SagaStatus.COMPLETED
        assert saga.state.current_step == "completed"

    @pytest.mark.asyncio
    async def test_saga_with_suspend_and_resume(self) -> None:
        """Saga that suspends and resumes."""
        MySaga = (
            SagaBuilder("ApprovalSaga")
            .on(EventA, step="awaiting_approval", suspend="Manual review required")
            .on(EventB, resume=True, step="approved", send=lambda e: CommandX())
            .on(EventC, step="completed", complete=True)
            .build()
        )

        state = SagaState(id="saga-1")
        saga = MySaga(state)
        saga.dispatch = lambda cmd: None  # type: ignore

        # Suspend
        await saga.handle(EventA())
        assert saga.state.status == SagaStatus.SUSPENDED
        assert saga.state.current_step == "awaiting_approval"

        # Resume
        await saga.handle(EventB())
        assert saga.state.status == SagaStatus.RUNNING

        # Complete
        await saga.handle(EventC())
        assert saga.state.status == SagaStatus.COMPLETED

    def test_listens_to_contains_all_registered_events(self) -> None:
        """listens_to includes all events from on() and TCC methods."""
        step1 = TCCStep(
            name="step1",
            try_command=CommandX(),
            confirm_command=CommandY(),
            cancel_command=CommandZ(),
        )

        class Event1(DomainEvent):
            pass

        class Event2(DomainEvent):
            pass

        class Event3(DomainEvent):
            pass

        class Event4(DomainEvent):
            pass

        MySaga = (
            SagaBuilder("MySaga")
            .with_tcc_step(step1)
            .on(Event1, send=lambda e: CommandX())
            .on_tcc_begin(Event2)
            .on_tcc_tried("step1", Event3)
            .on_tcc_confirmed("step1", Event4)
            .build()
        )

        assert Event1 in MySaga.listens_to
        assert Event2 in MySaga.listens_to
        assert Event3 in MySaga.listens_to
        assert Event4 in MySaga.listens_to
        assert len(MySaga.listens_to) == 4
