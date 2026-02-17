"""SagaBuilder — fluent API for defining sagas without subclassing."""

from __future__ import annotations

from inspect import isawaitable
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from datetime import timedelta

from cqrs_ddd_advanced_core.exceptions import SagaConfigurationError

from .orchestration import Saga, TCCStep
from .state import SagaState

if TYPE_CHECKING:
    from cqrs_ddd_core.cqrs.command import Command
    from cqrs_ddd_core.domain.events import DomainEvent

S = TypeVar("S", bound=SagaState)

if TYPE_CHECKING:
    HandlerAction = Callable[[DomainEvent], Awaitable[None]] | None
else:
    HandlerAction = Any


# ── Handler generation helper ──────────────────────────────────────────


def _create_resume_action(saga: Saga[Any]) -> HandlerAction:
    """Create resume action if needed."""

    async def _action(_event: DomainEvent) -> None:
        saga.resume()

    return _action


def _create_step_action(saga: Saga[Any], step: str) -> HandlerAction:
    """Create step action if needed."""

    async def _action(_event: DomainEvent) -> None:
        saga.state.current_step = step

    return _action


def _create_send_action(
    saga: Saga[Any], send_fn: Callable[[DomainEvent], Command[Any]]
) -> HandlerAction:
    """Create send action if needed."""

    async def _action(event: DomainEvent) -> None:
        saga.dispatch(send_fn(event))

    return _action


def _create_send_all_action(
    saga: Saga[Any], send_all_fn: Callable[[DomainEvent], list[Command[Any]]]
) -> HandlerAction:
    """Create send_all action if needed."""

    async def _action(event: DomainEvent) -> None:
        for cmd in send_all_fn(event):
            saga.dispatch(cmd)

    return _action


def _create_compensate_action(
    saga: Saga[Any],
    compensate_fn: Callable[[DomainEvent], Command[Any]],
    desc: str,
) -> HandlerAction:
    """Create compensate action if needed."""

    async def _action(event: DomainEvent) -> None:
        saga.add_compensation(compensate_fn(event), desc)

    return _action


def _create_suspend_action(
    saga: Saga[Any], reason: str, timeout: timedelta | None
) -> HandlerAction:
    """Create suspend action if needed."""

    async def _action(_event: DomainEvent) -> None:
        saga.suspend(reason, timeout=timeout)

    return _action


def _create_fail_action(saga: Saga[Any], reason: str) -> HandlerAction:
    """Create fail action if needed."""

    async def _action(_event: DomainEvent) -> None:
        await saga.fail(reason)

    return _action


def _create_complete_action(saga: Saga[Any]) -> HandlerAction:
    """Create complete action if needed."""

    async def _action(_event: DomainEvent) -> None:
        saga.complete()

    return _action


def _build_handler_actions(  # noqa: C901
    saga: Saga[Any], config: dict[str, Any]
) -> list[Callable[[DomainEvent], Awaitable[None]]]:
    """Build list of handler actions from config."""
    actions: list[Callable[[DomainEvent], Awaitable[None]]] = []

    _maybe_add_action(
        actions, config.get("resume", False), lambda: _create_resume_action(saga)
    )
    _maybe_add_action(
        actions, "step" in config, lambda: _create_step_action(saga, config["step"])
    )
    _maybe_add_action(
        actions, "send" in config, lambda: _create_send_action(saga, config["send"])
    )
    _maybe_add_action(
        actions,
        "send_all" in config,
        lambda: _create_send_all_action(saga, config["send_all"]),
    )
    _maybe_add_action(
        actions,
        "compensate" in config,
        lambda: _create_compensate_action(
            saga, config["compensate"], config.get("compensate_description", "")
        ),
    )
    _maybe_add_action(
        actions,
        "suspend" in config,
        lambda: _create_suspend_action(
            saga, config["suspend"], config.get("suspend_timeout")
        ),
    )
    _maybe_add_action(
        actions, "fail" in config, lambda: _create_fail_action(saga, config["fail"])
    )
    _maybe_add_action(
        actions, config.get("complete", False), lambda: _create_complete_action(saga)
    )

    return actions


def _maybe_add_action(
    actions: list[Callable[[DomainEvent], Awaitable[None]]],
    condition: bool,
    factory: Callable[[], Callable[[DomainEvent], Awaitable[None]] | None],
) -> None:
    """Add an action if condition is met and factory returns a value."""
    if condition:
        action = factory()
        if action is not None:
            actions.append(action)


def _create_mapped_handler(
    saga: Saga[Any],
    config: dict[str, Any],
) -> Callable[[DomainEvent], Awaitable[None]]:
    """Create a handler function from config dict."""
    actions = _build_handler_actions(saga, config)

    async def _mapped_handler(event: DomainEvent) -> None:
        for action in actions:
            await action(event)

    return _mapped_handler


def _register_on_mapping(
    saga: Saga[Any],
    event_type: type[DomainEvent],
    config: dict[str, Any],
) -> None:
    """Register a single ``.on()`` event mapping from a builder config dict."""
    handler = config.get("handler")
    if handler is not None:
        saga.on(event_type, handler=handler)
        return

    mapped_handler = _create_mapped_handler(saga, config)
    saga.on(event_type, handler=mapped_handler)


# ── Builder ────────────────────────────────────────────────────────────


def _wire_tcc_begin_handler(saga: Saga[Any], event_type: type[DomainEvent]) -> None:
    """Wire TCC begin handler."""

    def _begin(_event: Any) -> None:
        saga.begin_tcc()

    saga.on(event_type, handler=_begin)


def _wire_tcc_tried_handlers(
    saga: Saga[Any], tcc_tried: list[tuple[str, type[DomainEvent]]]
) -> None:
    """Wire TCC tried handlers."""
    for step_name, event_type in tcc_tried:

        def _tried(_event: Any, _sn: str = step_name) -> None:
            saga.mark_step_tried(_sn)

        saga.on(event_type, handler=_tried)


def _wire_tcc_confirmed_handlers(
    saga: Saga[Any], tcc_confirmed: list[tuple[str, type[DomainEvent]]]
) -> None:
    """Wire TCC confirmed handlers."""
    for step_name, event_type in tcc_confirmed:

        def _confirmed(_event: Any, _sn: str = step_name) -> None:
            saga.mark_step_confirmed(_sn)

        saga.on(event_type, handler=_confirmed)


def _wire_tcc_failed_handlers(
    saga: Saga[Any], tcc_failed: list[tuple[str, type[DomainEvent]]]
) -> None:
    """Wire TCC failed handlers."""
    for step_name, event_type in tcc_failed:

        def _failed(event: Any, _sn: str = step_name) -> None:
            reason = getattr(event, "reason", "") or getattr(event, "error", "")
            saga.mark_step_failed(_sn, reason=reason)

        saga.on(event_type, handler=_failed)


def _wire_tcc_cancelled_handlers(
    saga: Saga[Any], tcc_cancelled: list[tuple[str, type[DomainEvent]]]
) -> None:
    """Wire TCC cancelled handlers."""
    for step_name, event_type in tcc_cancelled:

        def _cancelled(_event: Any, _sn: str = step_name) -> None:
            saga.mark_step_cancelled(_sn)

        saga.on(event_type, handler=_cancelled)


def _create_init_function(
    on_regs: list[tuple[type[DomainEvent], dict[str, Any]]],
    tcc_steps: list[TCCStep],
    max_retries: int | None,
    tcc_begin_evt: type[DomainEvent] | None,
    tcc_tried: list[tuple[str, type[DomainEvent]]],
    tcc_confirmed: list[tuple[str, type[DomainEvent]]],
    tcc_failed: list[tuple[str, type[DomainEvent]]],
    tcc_cancelled: list[tuple[str, type[DomainEvent]]],
) -> Callable[[Saga[Any], Any, Any], None]:
    """Create the __init__ function for the generated saga class."""

    def _init(
        self_saga: Saga[Any],
        state: Any,
        message_registry: Any = None,
    ) -> None:
        Saga.__init__(self_saga, state, message_registry)

        if max_retries is not None:
            self_saga.state.max_retries = max_retries

        # Replay .on() registrations
        for evt_type, config in on_regs:
            _register_on_mapping(self_saga, evt_type, config)

        # Register TCC steps
        for step in tcc_steps:
            self_saga.add_tcc_step(step)

        # TCC event wiring
        if tcc_begin_evt is not None:
            _wire_tcc_begin_handler(self_saga, tcc_begin_evt)

        _wire_tcc_tried_handlers(self_saga, tcc_tried)
        _wire_tcc_confirmed_handlers(self_saga, tcc_confirmed)
        _wire_tcc_failed_handlers(self_saga, tcc_failed)
        _wire_tcc_cancelled_handlers(self_saga, tcc_cancelled)

    return _init


def _create_timeout_override(
    timeout_fn: Callable[[Saga[Any]], None]
    | Callable[[Saga[Any]], Awaitable[None]]
    | None,
) -> Callable[[Saga[Any]], Awaitable[None]] | None:
    """Create timeout override method if provided."""
    if timeout_fn is None:
        return None

    _fn = timeout_fn

    async def _on_timeout(self_saga: Saga[Any]) -> None:
        result = _fn(self_saga)
        if isawaitable(result):
            await result

    return _on_timeout


class SagaBuilder:
    """
    Fluent builder that produces a :class:`Saga` subclass from declarative
    event mappings, TCC steps, and lifecycle configuration.

    Covers all saga features without requiring a hand-written subclass:
    command dispatch, multi-command dispatch, compensation, suspend/resume,
    fail, TCC event wiring, custom timeout handling, and max retries.

    The built class has :attr:`listens_to` set automatically from all
    registered events and works with :class:`SagaRegistry`,
    :class:`SagaManager`, and :func:`bootstrap_sagas`.

    Example — basic saga::

        OrderSaga = (
            SagaBuilder("OrderFulfillment")
            .with_state_class(OrderSagaState)
            .with_max_retries(5)
            .on(OrderCreated,
                send=lambda e: ReserveItems(order_id=e.order_id),
                step="reserving",
                compensate=lambda e: CancelReservation(order_id=e.order_id))
            .on(PaymentCharged,
                send=lambda e: ConfirmOrder(order_id=e.order_id),
                step="confirming",
                complete=True)
            .build()
        )

    Example — TCC saga (OrderCreated is the trigger event that starts TCC;
    it is added to ``listens_to`` automatically)::

        TCCSaga = (
            SagaBuilder("OrderTCC")
            .with_tcc_step(TCCStep(
                name="inventory",
                try_command=ReserveInventory(...),
                confirm_command=ConfirmInventory(...),
                cancel_command=ReleaseInventory(...),
            ))
            .on_tcc_begin(OrderCreated)   # When OrderCreated arrives -> begin_tcc()
            .on_tcc_tried("inventory", InventoryReserved)
            .on_tcc_confirmed("inventory", InventoryConfirmed)
            .on_tcc_failed("inventory", InventoryFailed)
            .on_tcc_cancelled("inventory", InventoryReleased)
            .build()
        )
    """

    def __init__(self, name: str) -> None:
        self._name = name
        self._on_registrations: list[tuple[type[DomainEvent], dict[str, Any]]] = []
        self._tcc_steps: list[TCCStep] = []
        self._state_class: type[SagaState] = SagaState
        self._max_retries: int | None = None
        self._on_timeout_fn: (
            Callable[[Saga[Any]], None] | Callable[[Saga[Any]], Awaitable[None]] | None
        ) = None
        self._tcc_begin_event: type[DomainEvent] | None = None
        self._tcc_tried: list[tuple[str, type[DomainEvent]]] = []
        self._tcc_confirmed: list[tuple[str, type[DomainEvent]]] = []
        self._tcc_failed: list[tuple[str, type[DomainEvent]]] = []
        self._tcc_cancelled: list[tuple[str, type[DomainEvent]]] = []

    # ══════════════════════════════════════════════════════════════════
    # Event → action mapping
    # ══════════════════════════════════════════════════════════════════

    def on(  # noqa: PLR0913
        self,
        event_type: type[DomainEvent],
        handler: (
            Callable[[DomainEvent], None]
            | Callable[[DomainEvent], Awaitable[None]]
            | None
        ) = None,
        *,
        send: Callable[[DomainEvent], Command[Any]] | None = None,
        send_all: Callable[[DomainEvent], list[Command[Any]]] | None = None,
        step: str | None = None,
        compensate: Callable[[DomainEvent], Command[Any]] | None = None,
        compensate_description: str = "",
        complete: bool = False,
        suspend: str | None = None,
        suspend_timeout: timedelta | None = None,
        resume: bool = False,
        fail: str | None = None,
    ) -> SagaBuilder:
        """Register an event mapping — command dispatch, lifecycle action, or handler.

        **Command mapper** (preferred)::

            .on(OrderCreated,
                send=lambda e: ReserveItems(order_id=e.order_id),
                step="reserving")

        **Multi-command dispatch**::

            .on(PaymentReceived,
                send_all=lambda e: [NotifyWarehouse(...), UpdateLedger(...)],
                step="processing")

        **Suspend** (human-in-the-loop)::

            .on(NeedsReview,
                suspend="Needs manual review",
                suspend_timeout=timedelta(hours=24))

        **Resume and dispatch**::

            .on(ReviewApproved,
                send=lambda e: ContinueOrder(...),
                resume=True)

        **Fail**::

            .on(PaymentDeclined, fail="Payment permanently declined")

        **Custom handler** (complex branching)::

            .on(OrderCreated, handler=my_handler_fn)

        Args:
            event_type: The domain event class to handle.
            handler: Custom handler callable.  Mutually exclusive with all
                other action parameters.
            send: Command factory — receives the event, returns one command.
                Mutually exclusive with *send_all*.
            send_all: Command list factory — receives the event, returns a
                list of commands.  Mutually exclusive with *send*.
            step: Set ``current_step`` on the saga state.
            compensate: Compensation command factory.
            compensate_description: Description for the compensation record.
            complete: Mark the saga as COMPLETED after processing.
            suspend: Suspend the saga with this reason.  Mutually exclusive
                with *send*, *send_all*, *complete*, and *fail*.
            suspend_timeout: Timeout for auto-expiry (requires *suspend*).
            resume: If True, call ``resume()`` before dispatching.  Can
                combine with *send* or *send_all*.
            fail: Fail the saga with this reason.  Mutually exclusive with
                *send*, *send_all*, *complete*, and *suspend*.
        """
        self._validate_on(
            handler=handler,
            send=send,
            send_all=send_all,
            complete=complete,
            suspend=suspend,
            suspend_timeout=suspend_timeout,
            resume=resume,
            fail=fail,
        )
        config: dict[str, Any] = {
            "handler": handler,
            "send": send,
            "send_all": send_all,
            "step": step,
            "compensate": compensate,
            "compensate_description": compensate_description,
            "complete": complete,
            "suspend": suspend,
            "suspend_timeout": suspend_timeout,
            "resume": resume,
            "fail": fail,
        }
        self._on_registrations.append((event_type, config))
        return self

    def with_handler(
        self,
        event_type: type[DomainEvent],
        handler: (
            Callable[[DomainEvent], None] | Callable[[DomainEvent], Awaitable[None]]
        ),
    ) -> SagaBuilder:
        """Convenience for ``on(event_type, handler=fn)``."""
        return self.on(event_type, handler=handler)

    # ══════════════════════════════════════════════════════════════════
    # TCC step registration
    # ══════════════════════════════════════════════════════════════════

    def with_tcc_step(self, step: TCCStep) -> SagaBuilder:
        """Register a TCC step (Try/Confirm/Cancel)."""
        self._tcc_steps.append(step)
        return self

    # ══════════════════════════════════════════════════════════════════
    # TCC event wiring
    # ══════════════════════════════════════════════════════════════════

    def on_tcc_begin(self, event_type: type[DomainEvent]) -> SagaBuilder:
        """Wire an event to ``begin_tcc()`` — dispatches all Try commands.

        Must be called exactly once when TCC steps are registered.
        The event is automatically added to ``listens_to``.
        """
        if self._tcc_begin_event is not None:
            raise SagaConfigurationError("on_tcc_begin() can only be called once.")
        self._tcc_begin_event = event_type
        return self

    def on_tcc_tried(
        self, step_name: str, event_type: type[DomainEvent]
    ) -> SagaBuilder:
        """Wire an event to ``mark_step_tried(step_name)``.

        When all steps are TRIED, confirm commands are auto-dispatched.
        """
        self._tcc_tried.append((step_name, event_type))
        return self

    def on_tcc_confirmed(
        self, step_name: str, event_type: type[DomainEvent]
    ) -> SagaBuilder:
        """Wire an event to ``mark_step_confirmed(step_name)``.

        When all steps are CONFIRMED, the saga completes.
        """
        self._tcc_confirmed.append((step_name, event_type))
        return self

    def on_tcc_failed(
        self, step_name: str, event_type: type[DomainEvent]
    ) -> SagaBuilder:
        """Wire an event to ``mark_step_failed(step_name)``.

        Extracts a reason from the event's ``reason`` or ``error``
        attribute if present.  Triggers Cancel for in-progress steps.
        """
        self._tcc_failed.append((step_name, event_type))
        return self

    def on_tcc_cancelled(
        self, step_name: str, event_type: type[DomainEvent]
    ) -> SagaBuilder:
        """Wire an event to ``mark_step_cancelled(step_name)``."""
        self._tcc_cancelled.append((step_name, event_type))
        return self

    # ══════════════════════════════════════════════════════════════════
    # Configuration
    # ══════════════════════════════════════════════════════════════════

    def with_state_class(self, state_class: type[SagaState]) -> SagaBuilder:
        """Set the saga state class (default: :class:`SagaState`)."""
        self._state_class = state_class
        return self

    def with_max_retries(self, n: int) -> SagaBuilder:
        """Set ``max_retries`` on the saga state at construction time."""
        self._max_retries = n
        return self

    def on_timeout(
        self,
        fn: Callable[[Saga[Any]], None] | Callable[[Saga[Any]], Awaitable[None]],
    ) -> SagaBuilder:
        """Override the ``on_timeout()`` method on the generated class.

        *fn* receives the saga instance so you can call lifecycle methods::

            .on_timeout(lambda saga: saga.fail("Order expired"))
        """
        self._on_timeout_fn = fn
        return self

    # ══════════════════════════════════════════════════════════════════
    # Build
    # ══════════════════════════════════════════════════════════════════

    def build(self) -> type[Saga[Any]]:
        """Build and return a :class:`Saga` subclass.

        Raises :class:`SagaConfigurationError` on configuration errors:

        * TCC steps registered without ``on_tcc_begin()`` (or vice versa).
        * TCC step name in wiring methods doesn't match a registered step.
        * Duplicate event type across ``on()``, ``on_tcc_begin()``, etc.
        """
        self._validate_build()

        listened_to = self._collect_listened_events()

        # Snapshot builder state into locals for the generated __init__ closure.
        on_regs = list(self._on_registrations)
        tcc_steps = list(self._tcc_steps)
        state_cls = self._state_class
        max_retries = self._max_retries
        tcc_begin_evt = self._tcc_begin_event
        tcc_tried = list(self._tcc_tried)
        tcc_confirmed = list(self._tcc_confirmed)
        tcc_failed = list(self._tcc_failed)
        tcc_cancelled = list(self._tcc_cancelled)
        timeout_fn = self._on_timeout_fn

        _init = _create_init_function(
            on_regs,
            tcc_steps,
            max_retries,
            tcc_begin_evt,
            tcc_tried,
            tcc_confirmed,
            tcc_failed,
            tcc_cancelled,
        )

        # Build class dict
        cls_dict: dict[str, Any] = {
            "listens_to": listened_to,
            "state_class": state_cls,
            "__init__": _init,
        }

        # Override on_timeout if provided
        timeout_override = _create_timeout_override(timeout_fn)
        if timeout_override is not None:
            cls_dict["on_timeout"] = timeout_override

        return type(self._name, (Saga,), cls_dict)

    # ══════════════════════════════════════════════════════════════════
    # Internal validation
    # ══════════════════════════════════════════════════════════════════

    @staticmethod
    def _validate_on(  # noqa: PLR0913
        *,
        handler: Any,
        send: Any,
        send_all: Any,
        complete: bool,
        suspend: Any,
        suspend_timeout: Any,
        resume: bool,
        fail: Any,
    ) -> None:
        """Validate mutual-exclusivity rules for a single ``.on()`` call."""
        if handler is not None:
            if any([send, send_all, complete, suspend, fail, resume]):
                raise SagaConfigurationError(
                    "'handler' is mutually exclusive with all other action parameters."
                )
            return

        if send is not None and send_all is not None:
            raise SagaConfigurationError(
                "'send' and 'send_all' are mutually exclusive."
            )

        if suspend is not None and any([send, send_all, complete, fail]):
            raise SagaConfigurationError(
                "'suspend' is mutually exclusive with 'send', 'send_all', "
                "'complete', and 'fail'."
            )

        if fail is not None and any([send, send_all, complete, suspend]):
            raise SagaConfigurationError(
                "'fail' is mutually exclusive with 'send', 'send_all', "
                "'complete', and 'suspend'."
            )

        if suspend_timeout is not None and suspend is None:
            raise SagaConfigurationError("'suspend_timeout' requires 'suspend'.")

        if not any([handler, send, send_all, complete, suspend, fail, resume]):
            raise SagaConfigurationError(
                "At least one action is required: handler, send, send_all, "
                "complete, suspend, fail, or resume."
            )

    def _validate_tcc_consistency(self, _tcc_step_names: set[str]) -> None:
        """Validate TCC steps and on_tcc_begin consistency."""
        if self._tcc_steps and self._tcc_begin_event is None:
            raise SagaConfigurationError(
                "TCC steps are registered but on_tcc_begin() was not called. "
                "Specify which event triggers begin_tcc()."
            )
        if self._tcc_begin_event is not None and not self._tcc_steps:
            raise SagaConfigurationError(
                "on_tcc_begin() was called but no TCC steps are registered. "
                "Add steps with with_tcc_step()."
            )

    def _validate_tcc_step_names(self, tcc_step_names: set[str]) -> None:
        """Validate TCC step name references."""
        for label, entries in [
            ("on_tcc_tried", self._tcc_tried),
            ("on_tcc_confirmed", self._tcc_confirmed),
            ("on_tcc_failed", self._tcc_failed),
            ("on_tcc_cancelled", self._tcc_cancelled),
        ]:
            for step_name, _ in entries:
                if step_name not in tcc_step_names:
                    raise SagaConfigurationError(
                        f"{label}('{step_name}', ...) references unknown "
                        f"TCC step. Known steps: {sorted(tcc_step_names)}"
                    )

    def _collect_all_events(self) -> list[type]:
        """Collect all registered event types."""
        all_events: list[type] = []
        for evt_type, _ in self._on_registrations:
            all_events.append(evt_type)
        if self._tcc_begin_event is not None:
            all_events.append(self._tcc_begin_event)
        for _, evt in self._tcc_tried:
            all_events.append(evt)
        for _, evt in self._tcc_confirmed:
            all_events.append(evt)
        for _, evt in self._tcc_failed:
            all_events.append(evt)
        for _, evt in self._tcc_cancelled:
            all_events.append(evt)
        return all_events

    def _validate_no_duplicate_events(self, all_events: list[type]) -> None:
        """Validate no duplicate event registrations."""
        seen: set[type] = set()
        for evt in all_events:
            if evt in seen:
                raise SagaConfigurationError(
                    f"Duplicate event registration for {evt.__name__}. "
                    f"Each event can only appear once across on(), "
                    f"on_tcc_begin(), on_tcc_tried(), on_tcc_confirmed(), "
                    f"on_tcc_failed(), and on_tcc_cancelled()."
                )
            seen.add(evt)

    def _validate_build(self) -> None:
        """Build-time validation of the complete builder configuration."""
        tcc_step_names = {s.name for s in self._tcc_steps}
        self._validate_tcc_consistency(tcc_step_names)
        self._validate_tcc_step_names(tcc_step_names)
        all_events = self._collect_all_events()
        self._validate_no_duplicate_events(all_events)

    def _collect_listened_events(self) -> list[type[DomainEvent]]:
        """Collect unique event types in registration order."""
        events: list[type[DomainEvent]] = []
        seen: set[type[DomainEvent]] = set()

        def _add(evt: type[DomainEvent]) -> None:
            if evt not in seen:
                seen.add(evt)
                events.append(evt)

        for evt_type, _ in self._on_registrations:
            _add(evt_type)
        if self._tcc_begin_event is not None:
            _add(self._tcc_begin_event)
        for _, evt in self._tcc_tried:
            _add(evt)
        for _, evt in self._tcc_confirmed:
            _add(evt)
        for _, evt in self._tcc_failed:
            _add(evt)
        for _, evt in self._tcc_cancelled:
            _add(evt)
        return events
