"""SagaManager — orchestrates saga lifecycle (load → handle → save → dispatch)."""

from __future__ import annotations

import importlib
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Callable

from cqrs_ddd_advanced_core.exceptions import HandlerNotRegisteredError
from cqrs_ddd_core.correlation import get_correlation_id
from cqrs_ddd_core.instrumentation import get_hook_registry

from .orchestration import (
    Saga,
    is_command_dispatched,
    serialize_command_for_pending,
)
from .state import SagaState, SagaStatus

if TYPE_CHECKING:
    from cqrs_ddd_core.cqrs.command import Command
    from cqrs_ddd_core.cqrs.message_registry import MessageRegistry
    from cqrs_ddd_core.domain.events import DomainEvent
    from cqrs_ddd_core.ports.bus import ICommandBus
    from cqrs_ddd_core.ports.event_dispatcher import IEventDispatcher

    from ..ports.saga_repository import ISagaRepository
    from .registry import SagaRegistry

logger = logging.getLogger("cqrs_ddd.sagas")


def _resolve_state_class(saga_class: type[Saga[Any]]) -> type[SagaState]:
    """Resolve the concrete SagaState class from saga_class.state_class."""
    return getattr(saga_class, "state_class", SagaState)


def _correlation_id_from_event(event: DomainEvent) -> str | None:
    """Extract correlation_id from event (attribute or metadata)."""
    correlation_id = getattr(event, "correlation_id", None)
    if not correlation_id:
        metadata = getattr(event, "metadata", {})
        correlation_id = metadata.get("correlation_id") if metadata else None
    return correlation_id


class SagaManager:
    """
    Abstract base for saga managers.

    Lifecycle per event:
    1. Load/create :class:`SagaState` from repository.
    2. Instantiate :class:`Saga` and call ``handle(event)``.
    3. Save state back to repository.
    4. Dispatch pending commands via :class:`ICommandBus`.

    **TCC Support:**
    TCC steps are integrated into the base :class:`Saga` class.
    The manager doesn't need any special handling — TCC state is
    stored in ``SagaState.metadata`` and persisted automatically.
    For ``TIME_BASED`` TCC steps, periodic timeout checks can be
    triggered via :meth:`process_timeouts`.
    """

    def __init__(
        self,
        repository: ISagaRepository,
        registry: SagaRegistry,
        command_bus: ICommandBus,
        message_registry: MessageRegistry,
        recovery_trigger: Callable[[], None] | None = None,
    ) -> None:
        self.repository = repository
        self.registry = registry
        self.command_bus = command_bus
        self.message_registry = message_registry
        self._recovery_trigger = recovery_trigger

    def set_recovery_trigger(self, callback: Callable[[], None] | None) -> None:
        """Set or clear the callback invoked when a saga stalls.

        E.g. SagaRecoveryWorker.trigger.
        """
        self._recovery_trigger = callback

    # ── Core processing ──────────────────────────────────────────────

    async def _process_saga(
        self,
        saga_class: type[Saga[Any]],
        correlation_id: str,
        event: DomainEvent | None = None,
    ) -> str | None:
        """
        Load or create a saga instance, pass the event, persist state,
        and dispatch queued commands.

        Returns the saga id on success, ``None`` if skipped.
        """
        saga_type_name = saga_class.__name__

        # 1. Load existing or create new state.
        state = await self.repository.find_by_correlation_id(
            correlation_id, saga_type=saga_type_name
        )

        if state is None:
            state_cls = _resolve_state_class(saga_class)
            state = state_cls(
                id=str(uuid.uuid4()),
                saga_type=saga_type_name,
                correlation_id=correlation_id,
            )
            await self.repository.add(state)

        # Skip terminal sagas.
        if state.is_terminal:
            return None

        # 2. Instantiate & handle.
        saga = saga_class(state, self.message_registry)

        if event is not None:
            try:
                await saga.handle(event)
            except Exception:
                # Persist partial state so recovery can pick it up.
                await self.repository.add(state)
                raise

        # 3. Serialise pending commands into state for crash-safety.
        commands = saga.collect_commands()
        for cmd in commands:
            state.pending_commands.append(serialize_command_for_pending(cmd))
        await self.repository.add(state)

        # 4. Dispatch commands, persisting after each so recovery
        # knows what was dispatched.
        try:
            for i, cmd in enumerate(commands):
                await self.command_bus.send(cmd)
                state.pending_commands[i]["dispatched"] = True
                await self.repository.add(state)
        except Exception as dispatch_err:
            logger.error(
                "Saga %s stalled during dispatch: %s",
                state.id,
                dispatch_err,
            )
            if self._recovery_trigger is not None:
                try:
                    self._recovery_trigger()
                except Exception:  # noqa: BLE001
                    logger.debug("Recovery trigger callback failed", exc_info=True)
            raise

        # 5. Clear dispatched commands and persist final state (single write).
        state.pending_commands.clear()
        state.touch()
        await self.repository.add(state)

        return state.id

    # ── Public API ──────────────────────────────────────────────────

    async def handle(self, event: DomainEvent) -> None:
        """Route an event to all registered sagas (event-driven choreography)."""
        registry = get_hook_registry()
        event_type_name = type(event).__name__
        await registry.execute_all(
            f"saga.handle_event.{event_type_name}",
            {
                "event.type": event_type_name,
                "message_type": type(event),
                "correlation_id": get_correlation_id()
                or getattr(event, "correlation_id", None),
            },
            lambda: self._handle_internal(event),
        )

    async def _handle_internal(self, event: DomainEvent) -> None:
        """Route an event to all registered sagas (event-driven choreography)."""
        event_type = type(event)
        saga_classes = self.registry.get_sagas_for_event(event_type)
        if not saga_classes:
            return

        correlation_id = _correlation_id_from_event(event)
        if not correlation_id:
            logger.warning(
                "Event %s has no correlation_id — cannot route to saga",
                event_type.__name__,
            )
            return

        for saga_class in saga_classes:
            await self._process_saga(saga_class, correlation_id, event=event)

    async def start_saga(
        self,
        saga_class: type[Saga[Any]],
        initial_event: DomainEvent,
        correlation_id: str,
    ) -> str | None:
        """Start (or continue) a saga for the given correlation id.

        Explicit orchestration.
        """
        registry = get_hook_registry()
        return cast(
            "str | None",
            await registry.execute_all(
                f"saga.run.{saga_class.__name__}",
                {
                    "saga.type": saga_class.__name__,
                    "saga.correlation_id": correlation_id,
                    "event.type": type(initial_event).__name__,
                    "correlation_id": get_correlation_id()
                    or getattr(initial_event, "correlation_id", None),
                },
                lambda: self._process_saga(
                    saga_class, correlation_id, event=initial_event
                ),
            ),
        )

    # ── Event Dispatcher Integration ────────────────────────────────

    def bind_to(self, event_dispatcher: IEventDispatcher[Any]) -> None:
        """Auto-register this manager as an event handler with the dispatcher.

        Reads all event types from the :class:`SagaRegistry` and registers
        ``self.handle(event)`` for each one.  This eliminates the need for
        manual ``event_dispatcher.register(EventType, manager)`` calls::

            # Before (manual):
            event_dispatcher.register(OrderCreated, manager)
            event_dispatcher.register(PaymentReceived, manager)
            event_dispatcher.register(ShipmentConfirmed, manager)

            # After (automatic):
            manager.bind_to(event_dispatcher)

        """
        handler = self.handle
        for event_type in self.registry.registered_event_types:
            event_dispatcher.register(event_type, handler)
            logger.debug(
                "Bound %s to event type %s via EventDispatcher",
                type(self).__name__,
                event_type.__name__,
            )

    # ── Recovery helpers ─────────────────────────────────────────────

    async def _clear_dispatched_commands(self, state: SagaState) -> None:
        """Clear already-dispatched pending commands."""
        if state.pending_commands:
            state.pending_commands.clear()
            state.touch()
            await self.repository.add(state)
            logger.info(
                "Cleared already-dispatched pending commands for saga %s",
                state.id,
            )

    async def _fail_saga_max_retries(self, state: SagaState) -> None:
        """Fail saga when max retries exceeded."""
        saga_class = self.registry.get_saga_type(state.saga_type)
        if saga_class is not None:
            saga = saga_class(state, self.message_registry)
            await saga.fail(
                f"Saga recovery abandoned: max_retries ({state.max_retries}) exceeded",
                compensate=True,
            )
            await self.repository.add(state)
            logger.warning(
                "Saga %s failed: max_retries (%d) exceeded",
                state.id,
                state.max_retries,
            )
        else:
            logger.error(
                "Cannot fail saga %s (unknown type %s); skipping recovery",
                state.id,
                state.saga_type,
            )

    async def _dispatch_undispatched_commands(
        self, state: SagaState, undispatched: list[tuple[int, dict[str, Any]]]
    ) -> None:
        """Dispatch undispatched commands and mark recovery success."""
        for i, cmd_data in undispatched:
            command = self._deserialize_command(cmd_data)
            await self.command_bus.send(command)
            state.pending_commands[i]["dispatched"] = True
            await self.repository.add(state)

        state.pending_commands.clear()
        state.retry_count = 0  # Reset so a future stall gets a fresh count
        state.touch()
        await self.repository.add(state)
        logger.info("Successfully recovered saga %s", state.id)

    async def recover_pending_sagas(self, limit: int = 10) -> None:
        """Re-dispatch only undispatched pending commands for stalled sagas.

        Respects :attr:`SagaState.max_retries`: if ``retry_count >= max_retries``,
        the saga is failed (terminal state) and no further recovery is attempted.
        On each recovery attempt, ``retry_count`` is incremented; on success it
        is reset to 0 so a future stall gets a fresh count.
        """
        registry = get_hook_registry()
        await registry.execute_all(
            "saga.recovery.pending",
            {"saga.limit": limit, "correlation_id": get_correlation_id()},
            lambda: self._recover_pending_sagas_internal(limit),
        )

    async def _recover_pending_sagas_internal(self, limit: int = 10) -> None:
        stalled = await self.repository.find_stalled_sagas(limit)

        for state in stalled:
            undispatched = [
                (i, cmd_data)
                for i, cmd_data in enumerate(state.pending_commands)
                if not is_command_dispatched(cmd_data)
            ]

            if not undispatched:
                await self._clear_dispatched_commands(state)
                continue

            if state.retry_count >= state.max_retries:
                await self._fail_saga_max_retries(state)
                continue

            state.retry_count += 1
            state.touch()
            await self.repository.add(state)

            logger.info(
                "Recovering stalled saga %s (attempt %d/%d) "
                "with %d undispatched commands.",
                state.id,
                state.retry_count,
                state.max_retries,
                len(undispatched),
            )

            try:
                await self._dispatch_undispatched_commands(state, undispatched)
            except Exception as exc:  # noqa: BLE001
                logger.error("Recovery failed for saga %s: %s", state.id, exc)

    async def process_timeouts(self, limit: int = 10) -> None:
        """Process expired suspended sagas."""
        registry = get_hook_registry()
        await registry.execute_all(
            "saga.recovery.timeouts",
            {"saga.limit": limit, "correlation_id": get_correlation_id()},
            lambda: self._process_timeouts_internal(limit),
        )

    async def _process_timeouts_internal(self, limit: int = 10) -> None:
        expired = await self.repository.find_expired_suspended_sagas(limit)

        for state in expired:
            logger.info(
                "Processing timeout for saga %s (reason: %s)",
                state.id,
                state.suspension_reason,
            )
            saga_class = self.registry.get_saga_type(state.saga_type)
            if saga_class is None:
                logger.error(
                    "Could not find saga class %s for timeout processing",
                    state.saga_type,
                )
                continue

            saga = saga_class(state, self.message_registry)
            try:
                await saga.on_timeout()
            except Exception as exc:  # noqa: BLE001
                logger.error("Error in on_timeout for saga %s: %s", state.id, exc)
                if state.status != SagaStatus.FAILED:
                    await saga.fail(f"Timeout handler failed: {exc}")

            # If on_timeout didn't resolve the suspension, force failure.
            now = datetime.now(timezone.utc)
            if (
                state.status == SagaStatus.SUSPENDED
                and state.timeout_at is not None
                and state.timeout_at <= now
            ):
                await saga.fail(
                    "Timeout handler did not resolve suspension", compensate=False
                )

            # Dispatch any commands queued during on_timeout.
            commands = saga.collect_commands()
            for cmd in commands:
                try:
                    await self.command_bus.send(cmd)
                except Exception as cmd_err:  # noqa: BLE001
                    logger.error(
                        "Failed to dispatch timeout command for saga %s: %s",
                        state.id,
                        cmd_err,
                    )

            await self.repository.add(state)

    async def process_tcc_timeouts(self, limit: int = 10) -> None:
        """Process expired TIME_BASED TCC steps for running sagas."""
        registry = get_hook_registry()
        await registry.execute_all(
            "saga.recovery.tcc_timeouts",
            {"saga.limit": limit, "correlation_id": get_correlation_id()},
            lambda: self._process_tcc_timeouts_internal(limit),
        )

    async def _process_tcc_timeouts_internal(self, limit: int = 10) -> None:
        running = await self.repository.find_running_sagas_with_tcc_steps(limit)

        for state in running:
            saga_class = self.registry.get_saga_type(state.saga_type)
            if saga_class is None:
                logger.error(
                    "Could not find saga class %s for TCC timeout processing",
                    state.saga_type,
                )
                continue

            saga = saga_class(state, self.message_registry)
            try:
                saga.check_tcc_timeouts()
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Error in check_tcc_timeouts for saga %s: %s",
                    state.id,
                    exc,
                )
                continue

            commands = saga.collect_commands()
            for cmd in commands:
                try:
                    await self.command_bus.send(cmd)
                except Exception as cmd_err:  # noqa: BLE001
                    logger.error(
                        "Failed to dispatch TCC cancel command for saga %s: %s",
                        state.id,
                        cmd_err,
                    )

            await self.repository.add(state)

    # ── Serialisation ────────────────────────────────────────────────

    def _deserialize_command(self, cmd_data: dict[str, Any]) -> Command[Any]:
        type_name = cmd_data["type_name"]
        data = cmd_data.get("data", {})

        command = self.message_registry.hydrate_command(type_name, data)
        if command is None:
            # Fallback for manual tests or unregistered types (less safe)
            module_name = cmd_data.get("module_name")
            if module_name:
                module = importlib.import_module(module_name)
                command_class = getattr(module, type_name)
                return cast("Command[Any]", command_class(**data))
            raise HandlerNotRegisteredError(
                f"Command type {type_name} not registered in MessageRegistry"
            )
        return command
