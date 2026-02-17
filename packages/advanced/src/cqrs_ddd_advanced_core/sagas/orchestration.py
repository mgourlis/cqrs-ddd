"""Saga base class — explicit state machine with integrated TCC support."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from inspect import isawaitable
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeVar

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

from cqrs_ddd_advanced_core.exceptions import (
    HandlerNotRegisteredError,
    SagaConfigurationError,
    SagaHandlerNotFoundError,
    SagaStateError,
)

from .state import (
    CompensationRecord,
    ReservationType,
    SagaState,
    SagaStatus,
    TCCPhase,
    TCCStepRecord,
)

if TYPE_CHECKING:
    from cqrs_ddd_core.cqrs.command import Command
    from cqrs_ddd_core.cqrs.message_registry import MessageRegistry
    from cqrs_ddd_core.domain.events import DomainEvent

S = TypeVar("S", bound=SagaState)

logger = logging.getLogger("cqrs_ddd.sagas")


# ── TCC Step builder ────────────────────────────────────────────────


class TCCStep:
    """Builder for a TCC step — provides Try/Confirm/Cancel commands.

    Pass this to :meth:`Saga.add_tcc_step` during ``__init__()`` or
    from a ``configure_steps`` hook.

    Attributes:
        name: Unique identifier for this step.
        try_command: Command dispatched during the Try phase.
        confirm_command: Command dispatched when all steps are TRIED.
        cancel_command: Command dispatched on failure / timeout.
        reservation_type: ``RESOURCE`` (held indefinitely) or
            ``TIME_BASED`` (auto-expires after *timeout*).
        timeout: For ``TIME_BASED`` reservations — the TTL after which
            the step is considered expired.

    Example::

        TCCStep(
            name="reserve_inventory",
            try_command=ReserveInventoryCommand(...),
            confirm_command=ConfirmInventoryCommand(...),
            cancel_command=ReleaseInventoryCommand(...),
        )

        # Time-based:
        TCCStep(
            name="hold_payment",
            try_command=HoldPaymentCommand(...),
            confirm_command=CapturePaymentCommand(...),
            cancel_command=VoidPaymentCommand(...),
            reservation_type=ReservationType.TIME_BASED,
            timeout=timedelta(minutes=15),
        )
    """

    def __init__(
        self,
        name: str,
        try_command: Command[Any],
        confirm_command: Command[Any],
        cancel_command: Command[Any],
        reservation_type: ReservationType = ReservationType.RESOURCE,
        timeout: timedelta | None = None,
    ) -> None:
        self.name = name
        self.try_command = try_command
        self.confirm_command = confirm_command
        self.cancel_command = cancel_command
        self.reservation_type = reservation_type
        self.timeout = timeout

        if reservation_type == ReservationType.TIME_BASED and timeout is None:
            raise SagaConfigurationError(
                f"TCCStep '{name}': TIME_BASED reservation requires a timeout."
            )


# ── Saga base class ────────────────────────────────────────────────


class Saga(Generic[S]):
    """
    Base class for Sagas / Process Managers with integrated TCC support.

    **Two styles for event handling:**

    *Command mapper* — maps an event directly to a command dispatch
    (the primary saga pattern)::

        self.on(OrderCreated,
                send=lambda e: ReserveItems(order_id=e.order_id),
                step="reserving",
                compensate=lambda e: CancelReservation(order_id=e.order_id))

    *Handler* — for complex logic requiring conditional dispatch::

        self.on(OrderCreated, handler=self.handle_order_created)

    **TCC (Try-Confirm/Cancel):**

    TCC steps are a native feature.  Register them with
    :meth:`add_tcc_step`, start with :meth:`begin_tcc`, and react to
    events via ``mark_step_tried`` / ``mark_step_failed``.

    Two reservation types:

    * ``ReservationType.RESOURCE`` — held indefinitely until explicit
      confirm/cancel (inventory holds, seat reservations).
    * ``ReservationType.TIME_BASED`` — auto-expires after a TTL
      (payment holds, temporary blocks).

    Lifecycle
    ---------
    * ``handle(event)`` — public entry point: idempotency →
      ``_handle_event()`` → collect commands.
    * ``on(event_type, ...)`` — register event→command mapping.
    * ``dispatch(command)`` — queue a command for later execution.
    * ``complete()`` — mark as *COMPLETED*.
    * ``fail(reason)`` — mark as *FAILED*, trigger compensation.
    * ``suspend(reason, timeout)`` — mark as *SUSPENDED*.
    * ``resume()`` — resume a *SUSPENDED* saga.
    * ``add_compensation(command, description)`` — push to compensation stack.
    * ``execute_compensations()`` — pop & execute in LIFO order.
    * ``add_tcc_step(step)`` — register a TCC step.
    * ``begin_tcc()`` — dispatch Try commands for all TCC steps.

    **Event registration (hand-written sagas):**

    Hand-written saga subclasses **must** set the class-level :attr:`listens_to`
    to the list of event types they handle. There is no auto-discovery from
    ``on()`` registrations. If :attr:`listens_to` is empty, the saga will not
    receive any events from the registry::

        class OrderSaga(Saga[OrderSagaState]):
            listens_to = [OrderCreated, PaymentReceived]

            def __init__(self, state, message_registry=None):
                super().__init__(state, message_registry)
                self.on(OrderCreated, send=lambda e: ReserveItems(...))
                self.on(PaymentReceived, handler=self.handle_payment)

    For declarative sagas without subclassing, use :class:`SagaBuilder`; it
    sets :attr:`listens_to` automatically from the events passed to ``.on()``.
    """

    state_class: ClassVar[type[SagaState]] = SagaState
    listens_to: ClassVar[list[type[DomainEvent]]] = []

    def __init__(
        self, state: S, message_registry: MessageRegistry | None = None
    ) -> None:
        self.state: S = state
        self.message_registry = message_registry
        self._commands_to_dispatch: list[Command[Any]] = []
        self._event_handlers: dict[
            type[DomainEvent],
            Callable[[DomainEvent], None] | Callable[[DomainEvent], Awaitable[None]],
        ] = {}
        # TCC
        self._tcc_steps: list[TCCStep] = []
        self._tcc_step_index: dict[str, int] = {}
        self._tcc_records_cache: list[TCCStepRecord] | None = None

    # ══════════════════════════════════════════════════════════════════
    # Class-level event declaration
    # ══════════════════════════════════════════════════════════════════

    @classmethod
    def listened_events(cls) -> list[type[DomainEvent]]:
        """Return event types this saga handles.

        **Hand-written sagas must set** the class-level :attr:`listens_to`
        to the list of event types they handle. This method returns that list.
        There is no auto-discovery from ``on()``; if :attr:`listens_to` is
        empty, the saga will not be registered for any events. Use
        :class:`SagaBuilder` for declarative sagas — it sets :attr:`listens_to`
        when building the class.

        Returns:
            List of event types this saga handles (from :attr:`listens_to`).
        """
        if cls is Saga:
            return []
        if cls.listens_to:
            return list(cls.listens_to)
        return []

    # ══════════════════════════════════════════════════════════════════
    # Public entry point
    # ══════════════════════════════════════════════════════════════════

    async def handle(self, event: DomainEvent) -> None:
        """
        Idempotent entry point — skips already-processed events, then
        delegates to ``_handle_event`` and records the event id.
        """
        self._tcc_records_cache = None  # Invalidate TCC cache for fresh load
        if self.state.is_terminal:
            logger.debug(
                "Saga %s is in terminal state %s — ignoring event %s",
                self.state.id,
                self.state.status,
                type(event).__name__,
            )
            return

        if self.state.is_event_processed(event.event_id):
            return

        # Transition to RUNNING on first handled event.
        if self.state.status == SagaStatus.PENDING:
            self.state.status = SagaStatus.RUNNING

        result = self._handle_event(event)
        if isawaitable(result):
            await result

        self.state.mark_event_processed(event.event_id)
        self.state.record_step(
            step_name=self.state.current_step,
            event_type=type(event).__name__,
        )

    async def _handle_event(self, event: DomainEvent) -> None:
        """
        Dispatch to registered handlers (from :meth:`on`) or raise.

        **Override in subclasses** with ``match``/``case`` or
        ``if``/``elif`` for imperative dispatch.  Registered handlers
        from :meth:`on` take precedence.
        """
        handler = self._event_handlers.get(type(event))
        if handler is not None:
            result = handler(event)
            if isawaitable(result):
                await result
        else:
            raise SagaHandlerNotFoundError(
                f"No handler registered for {type(event).__name__}. "
                f"Either override _handle_event() or register handlers with on()."
            )

    # ══════════════════════════════════════════════════════════════════
    # Event → Command mapping  (declarative)
    # ══════════════════════════════════════════════════════════════════

    def on(
        self,
        event_type: type[DomainEvent],
        handler: Callable[[DomainEvent], None]
        | Callable[[DomainEvent], Awaitable[None]]
        | None = None,
        *,
        send: Callable[[DomainEvent], Command[Any]] | None = None,
        step: str | None = None,
        compensate: Callable[[DomainEvent], Command[Any]] | None = None,
        compensate_description: str = "",
        complete: bool = False,
    ) -> None:
        """Register an event mapping — either a handler or a command dispatch.

        **Command mapper** (preferred for sagas) — the event is mapped to
        a command which is dispatched through the mediator / command bus::

            self.on(OrderCreated,
                    send=lambda e: ReserveItems(order_id=e.order_id),
                    step="reserving",
                    compensate=lambda e: CancelReservation(order_id=e.order_id))

        **Handler** (backward-compatible, for complex logic)::

            self.on(OrderCreated, handler=self.handle_order_created)

        Args:
            event_type: The domain event class to handle.
            handler: Custom handler callable. Mutually exclusive with *send*.
            send: Command factory — receives the event, returns a
                :class:`Command` to dispatch through the mediator.
            step: Set ``current_step`` on the saga state when this event
                is received.
            compensate: Compensation command factory — if provided, a
                compensating command is pushed onto the stack.
            compensate_description: Description for the compensation record.
            complete: If *True*, mark the saga as *COMPLETED* after
                processing this event.
        """
        if handler is not None and send is not None:
            raise SagaConfigurationError(
                "Cannot provide both 'handler' and 'send' — pick one."
            )
        if handler is None and send is None:
            raise SagaConfigurationError("Must provide either 'handler' or 'send'.")

        if handler is not None:
            self._event_handlers[event_type] = handler
        else:
            # Build a handler from the command-mapper parameters.
            # Capture values in a closure — safe since these are local params.
            _send = send
            _step = step
            _compensate = compensate
            _comp_desc = compensate_description
            _complete = complete

            async def _mapped_handler(event: DomainEvent) -> None:
                if _step is not None:
                    self.state.current_step = _step
                assert _send is not None  # guaranteed by validation above
                command = _send(event)
                self.dispatch(command)
                if _compensate is not None:
                    comp_cmd = _compensate(event)
                    self.add_compensation(comp_cmd, _comp_desc)
                if _complete:
                    self.complete()

            self._event_handlers[event_type] = _mapped_handler

    # ══════════════════════════════════════════════════════════════════
    # Command dispatch
    # ══════════════════════════════════════════════════════════════════

    def dispatch(self, command: Command[Any]) -> None:
        """Queue a command for dispatch by the :class:`SagaManager`."""
        self._commands_to_dispatch.append(command)

    def collect_commands(self) -> list[Command[Any]]:
        """Return all queued commands and clear the internal list."""
        cmds = list(self._commands_to_dispatch)
        self._commands_to_dispatch.clear()
        return cmds

    # ══════════════════════════════════════════════════════════════════
    # Lifecycle transitions
    # ══════════════════════════════════════════════════════════════════

    def complete(self) -> None:
        """Mark the saga as successfully completed."""
        self.state.status = SagaStatus.COMPLETED
        self.state.completed_at = datetime.now(timezone.utc)
        self.state.touch()

    async def fail(self, reason: str, *, compensate: bool = True) -> None:
        """Mark the saga as failed and optionally trigger compensation.

        Args:
            reason: Human-readable failure description.
            compensate: If *True* (default) and there are compensating
                commands on the stack, ``execute_compensations()`` is
                called before the saga transitions to its terminal state.
        """
        self.state.error = reason
        self.state.failed_at = datetime.now(timezone.utc)

        if compensate and self.state.compensation_stack:
            await self.execute_compensations()
        else:
            self.state.status = SagaStatus.FAILED
            self.state.touch()

    def suspend(
        self,
        reason: str,
        timeout: timedelta | None = None,
    ) -> None:
        """Suspend the saga, optionally with a timeout for auto-expiry."""
        self.state.status = SagaStatus.SUSPENDED
        self.state.suspended_at = datetime.now(timezone.utc)
        self.state.suspension_reason = reason
        if timeout is not None:
            self.state.timeout_at = datetime.now(timezone.utc) + timeout
        else:
            self.state.timeout_at = None
        self.state.touch()

    def resume(self) -> None:
        """Resume a previously suspended saga."""
        if self.state.status != SagaStatus.SUSPENDED:
            logger.warning(
                "Attempted to resume saga %s which is %s, not SUSPENDED",
                self.state.id,
                self.state.status,
            )
            return
        self.state.status = SagaStatus.RUNNING
        self.state.suspended_at = None
        self.state.suspension_reason = None
        self.state.timeout_at = None
        self.state.touch()

    async def on_timeout(self) -> None:
        """
        Called when a suspended saga's timeout expires.

        Default behaviour marks the saga as failed and triggers
        compensation.  Subclasses may override to implement custom
        recovery logic.
        """
        reason = "Saga timed out while suspended"
        if self.state.suspension_reason:
            reason += f" for: {self.state.suspension_reason}"
        await self.fail(reason)

    # ══════════════════════════════════════════════════════════════════
    # Compensation
    # ══════════════════════════════════════════════════════════════════

    def add_compensation(
        self,
        command: Command[Any],
        description: str = "",
    ) -> None:
        """Push a compensating command onto the LIFO stack."""
        record = CompensationRecord(
            command_type=type(command).__name__,
            module_name=type(command).__module__,
            data=self._serialize_command_data(command),
            description=description,
        )
        self.state.compensation_stack.append(record)

    def _require_message_registry(self) -> MessageRegistry:
        """Return the message_registry or raise with a helpful message."""
        if self.message_registry is None:
            raise SagaStateError(
                "message_registry is required for this operation. "
                "When using Saga with a SagaManager, it is injected automatically. "
                "For standalone use, pass message_registry to the constructor."
            )
        return self.message_registry

    async def execute_compensations(self) -> None:
        """
        Pop and execute compensating commands in LIFO order.

        Failed compensations are recorded in ``state.failed_compensations``
        so they can be inspected / retried manually.

        On completion the saga moves to ``COMPENSATED`` if all
        compensations succeeded, or ``FAILED`` if any failed.
        """
        registry = self._require_message_registry()

        self.state.status = SagaStatus.COMPENSATING
        self.state.touch()

        has_failures = False
        while self.state.compensation_stack:
            record = self.state.compensation_stack.pop()
            try:
                # Deserialize using MessageRegistry
                command = registry.hydrate_command(
                    record.command_type,
                    record.data,
                )
                if command is None:
                    raise HandlerNotRegisteredError(
                        f"Compensating command type '{record.command_type}' "
                        f"not registered. Ensure it's registered in MessageRegistry."
                    )
                self.dispatch(command)
            except Exception as exc:  # noqa: BLE001
                has_failures = True
                logger.error(
                    "Failed to execute compensation %s for saga %s: %s",
                    record.command_type,
                    self.state.id,
                    exc,
                )
                self.state.failed_compensations.append(
                    {
                        "command_type": record.command_type,
                        "error": str(exc),
                        "failed_at": datetime.now(timezone.utc).isoformat(),
                    }
                )

        # Transition to terminal state.
        if has_failures:
            self.state.status = SagaStatus.FAILED
        else:
            self.state.status = SagaStatus.COMPENSATED
        self.state.touch()

    # ══════════════════════════════════════════════════════════════════
    # TCC — Step registration
    # ══════════════════════════════════════════════════════════════════

    def add_tcc_step(self, step: TCCStep) -> None:
        """Register a TCC step.

        Call during ``__init__()`` (after ``super().__init__()``) to set
        up Try-Confirm/Cancel steps as a native part of the saga.

        Args:
            step: A :class:`TCCStep` builder with Try/Confirm/Cancel commands.

        Example::

            # Resource-based (held until explicit confirm/cancel):
            self.add_tcc_step(TCCStep(
                name="reserve_inventory",
                try_command=ReserveInventory(order_id=order_id),
                confirm_command=ConfirmInventory(order_id=order_id),
                cancel_command=ReleaseInventory(order_id=order_id),
            ))

            # Time-based (auto-expires after timeout):
            self.add_tcc_step(TCCStep(
                name="hold_payment",
                try_command=HoldPayment(order_id=order_id),
                confirm_command=CapturePayment(order_id=order_id),
                cancel_command=VoidPayment(order_id=order_id),
                reservation_type=ReservationType.TIME_BASED,
                timeout=timedelta(minutes=15),
            ))
        """
        if step.name in self._tcc_step_index:
            raise SagaConfigurationError(f"TCC step '{step.name}' already registered.")
        self._tcc_step_index[step.name] = len(self._tcc_steps)
        self._tcc_steps.append(step)

    # ══════════════════════════════════════════════════════════════════
    # TCC — Lifecycle
    # ══════════════════════════════════════════════════════════════════

    def begin_tcc(self) -> None:
        """Dispatch **Try** commands for all registered TCC steps.

        Call this once — typically from the first event handler or
        when the saga is started by the manager.

        For ``TIME_BASED`` steps a ``timeout_at`` deadline is recorded
        in the step record.
        """
        if not self._tcc_steps:
            raise SagaStateError("No TCC steps registered — call add_tcc_step() first.")

        if self.state.tcc_steps:
            raise SagaStateError("TCC already started for this saga.")

        records: list[TCCStepRecord] = []
        now = datetime.now(timezone.utc)
        for step in self._tcc_steps:
            timeout_at: datetime | None = None
            if step.reservation_type == ReservationType.TIME_BASED and step.timeout:
                timeout_at = now + step.timeout

            record = TCCStepRecord(
                name=step.name,
                phase=TCCPhase.TRYING,
                reservation_type=step.reservation_type,
                try_command_type=type(step.try_command).__name__,
                try_command_module=type(step.try_command).__module__,
                try_command_data=self._serialize_command_data(step.try_command),
                confirm_command_type=type(step.confirm_command).__name__,
                confirm_command_module=type(step.confirm_command).__module__,
                confirm_command_data=self._serialize_command_data(step.confirm_command),
                cancel_command_type=type(step.cancel_command).__name__,
                cancel_command_module=type(step.cancel_command).__module__,
                cancel_command_data=self._serialize_command_data(step.cancel_command),
                timeout_at=timeout_at,
            )
            records.append(record)
            self.dispatch(step.try_command)

        self.state.tcc_steps = records
        self.state.status = SagaStatus.RUNNING
        self.state.current_step = "trying"
        self.state.touch()

        logger.info(
            "TCC saga %s began with %d steps",
            self.state.id,
            len(self._tcc_steps),
        )

    # ── TCC step transition helpers ─────────────────────────────────

    def mark_step_tried(self, step_name: str) -> None:
        """Mark a step's Try phase as successful.

        If all steps are now TRIED, confirm commands are auto-dispatched.
        """
        self._set_tcc_phase(
            step_name, TCCPhase.TRIED, tried_at=datetime.now(timezone.utc)
        )

        if self._all_tcc_steps_in_phase(TCCPhase.TRIED):
            self._dispatch_confirms()

    def mark_step_confirmed(self, step_name: str) -> None:
        """Mark a step's Confirm phase as successful.

        If all steps are CONFIRMED the saga completes.
        """
        self._set_tcc_phase(
            step_name, TCCPhase.CONFIRMED, confirmed_at=datetime.now(timezone.utc)
        )

        if self._all_tcc_steps_in_phase(TCCPhase.CONFIRMED):
            self.complete()

    def mark_step_failed(self, step_name: str, reason: str = "") -> None:
        """Mark a step as failed and trigger Cancel for in-progress steps.

        Cancels are dispatched *before* the step is marked FAILED so
        that ``_dispatch_cancels`` can still see its current phase and
        issue a cancel command if the reservation was already made
        (TRIED / CONFIRMING).
        """
        # Dispatch cancels while the step is still in its current phase.
        self._dispatch_cancels(reason)
        # Now mark the originating step as FAILED (overwrites CANCELLING).
        self._set_tcc_phase(step_name, TCCPhase.FAILED, error=reason)

    def mark_step_cancelled(self, step_name: str) -> None:
        """Confirm that a step's Cancel command has been processed."""
        self._set_tcc_phase(
            step_name, TCCPhase.CANCELLED, cancelled_at=datetime.now(timezone.utc)
        )

        # Check if all non-PENDING steps are cancelled (or failed).
        records = self._load_tcc_records()
        terminal = {TCCPhase.CANCELLED, TCCPhase.FAILED, TCCPhase.PENDING}
        if all(r.phase in terminal for r in records):
            self.state.status = SagaStatus.COMPENSATED
            self.state.touch()

    # ── TCC timeout management ──────────────────────────────────────

    def check_tcc_timeouts(self) -> list[str]:
        """Check for expired TIME_BASED TCC steps.

        Returns the names of steps that timed out.  For each expired
        step a Cancel command is dispatched automatically.

        Typically called by the :class:`SagaManager` during periodic
        sweeps, not by user code.
        """
        records = self._load_tcc_records()
        now = datetime.now(timezone.utc)
        expired_names: list[str] = []

        for rec in records:
            if (
                rec.reservation_type == ReservationType.TIME_BASED
                and rec.timeout_at is not None
                and rec.timeout_at <= now
                and rec.phase in (TCCPhase.TRYING, TCCPhase.TRIED)
            ):
                expired_names.append(rec.name)

        for name in expired_names:
            logger.warning(
                "TCC step '%s' in saga %s has timed out — cancelling.",
                name,
                self.state.id,
            )
            self.mark_step_failed(
                name, reason=f"TIME_BASED reservation expired for step '{name}'"
            )

        return expired_names

    # ── TCC query helpers ───────────────────────────────────────────

    def get_tcc_step_phase(self, step_name: str) -> TCCPhase | None:
        """Return the current phase of a named TCC step, or ``None``."""
        for rec in self._load_tcc_records():
            if rec.name == step_name:
                return rec.phase
        return None

    def get_tcc_step_records(self) -> list[TCCStepRecord]:
        """Return a snapshot of all TCC step records."""
        return self._load_tcc_records()

    # ══════════════════════════════════════════════════════════════════
    # TCC — Internal mechanics
    # ══════════════════════════════════════════════════════════════════

    def _load_tcc_records(self) -> list[TCCStepRecord]:
        if self._tcc_records_cache is not None:
            return self._tcc_records_cache
        records = list(self.state.tcc_steps)
        self._tcc_records_cache = records
        return records

    def _save_tcc_records(self, records: list[TCCStepRecord]) -> None:
        self._tcc_records_cache = records
        self.state.tcc_steps = records

    def _set_tcc_phase(
        self,
        step_name: str,
        phase: TCCPhase,
        *,
        error: str | None = None,
        tried_at: datetime | None = None,
        confirmed_at: datetime | None = None,
        cancelled_at: datetime | None = None,
    ) -> None:
        records = self._load_tcc_records()
        updated: list[TCCStepRecord] = []
        for rec in records:
            if rec.name == step_name:
                updates: dict[str, Any] = {"phase": phase}
                if error is not None:
                    updates["error"] = error
                if tried_at is not None:
                    updates["tried_at"] = tried_at
                if confirmed_at is not None:
                    updates["confirmed_at"] = confirmed_at
                if cancelled_at is not None:
                    updates["cancelled_at"] = cancelled_at
                rec = rec.model_copy(update=updates)
            updated.append(rec)
        self._save_tcc_records(updated)
        self.state.touch()

    def _all_tcc_steps_in_phase(self, phase: TCCPhase) -> bool:
        """Return *True* if every TCC step has reached *phase*."""
        records = self._load_tcc_records()
        return all(r.phase == phase for r in records)

    def _dispatch_confirms(self) -> None:
        """Dispatch Confirm commands for all TRIED steps."""
        registry = self._require_message_registry()
        records = self._load_tcc_records()
        updated: list[TCCStepRecord] = []
        for rec in records:
            if rec.phase == TCCPhase.TRIED:
                command = registry.hydrate_command(
                    rec.confirm_command_type, rec.confirm_command_data
                )
                if command is not None:
                    self.dispatch(command)
                    rec = rec.model_copy(update={"phase": TCCPhase.CONFIRMING})
                else:
                    logger.error(
                        "Cannot hydrate confirm command %s for step %s",
                        rec.confirm_command_type,
                        rec.name,
                    )
            updated.append(rec)

        self._save_tcc_records(updated)
        self.state.current_step = "confirming"
        self.state.touch()

        logger.info("TCC saga %s: all steps tried — confirming", self.state.id)

    def _dispatch_cancels(self, reason: str) -> None:
        """Dispatch Cancel commands for all TRIED steps in LIFO order."""
        registry = self._require_message_registry()
        records = self._load_tcc_records()

        # Process in reverse (LIFO) for proper rollback ordering.
        cancellable_indices: list[int] = []
        for idx, rec in enumerate(records):
            if rec.phase in (TCCPhase.TRIED, TCCPhase.TRYING, TCCPhase.CONFIRMING):
                cancellable_indices.append(idx)

        for idx in reversed(cancellable_indices):
            rec = records[idx]
            command = registry.hydrate_command(
                rec.cancel_command_type, rec.cancel_command_data
            )
            if command is not None:
                self.dispatch(command)
                records[idx] = rec.model_copy(update={"phase": TCCPhase.CANCELLING})
            else:
                logger.error(
                    "Cannot hydrate cancel command %s for step %s",
                    rec.cancel_command_type,
                    rec.name,
                )

        self._save_tcc_records(records)
        self.state.status = SagaStatus.COMPENSATING
        self.state.current_step = "cancelling"
        self.state.error = reason
        self.state.touch()

        logger.info(
            "TCC saga %s: step failure — cancelling %d steps",
            self.state.id,
            len(cancellable_indices),
        )

    # ══════════════════════════════════════════════════════════════════
    # Serialisation helpers (delegate to module-level)
    # ══════════════════════════════════════════════════════════════════

    @staticmethod
    def _serialize_command_data(command: Command[Any]) -> dict[str, Any]:
        """Extract a JSON-safe dict from a command (Pydantic or dataclass)."""
        return serialize_command_data(command)


# ── Shared serialization (used by Saga and SagaManager) ───────────────


def serialize_command_data(command: Command[Any]) -> dict[str, Any]:
    """Extract a JSON-safe dict from a command (Pydantic or dataclass)."""
    if hasattr(command, "model_dump"):
        return command.model_dump()  # Pydantic v2
    if hasattr(command, "__dict__"):
        return dict(command.__dict__)
    return {}  # pragma: no cover


def serialize_command_full(command: Command[Any]) -> dict[str, Any]:
    """Serialize command to full format: type_name, module_name, data."""
    return {
        "type_name": type(command).__name__,
        "module_name": type(command).__module__,
        "data": serialize_command_data(command),
    }


def serialize_command_for_pending(command: Command[Any]) -> dict[str, Any]:
    """Serialize command for pending_commands with dispatched: False."""
    return {**serialize_command_full(command), "dispatched": False}


def is_command_dispatched(cmd_data: dict[str, Any]) -> bool:
    """Return True if command was already successfully dispatched.

    Backward compat: missing = False.
    """
    return cmd_data.get("dispatched", False) is True
