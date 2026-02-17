"""UndoService — orchestrates undo/redo by looking up and executing handlers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cqrs_ddd_core.domain.events import DomainEvent

    from ..ports.undo import IUndoExecutorRegistry

logger = logging.getLogger("cqrs_ddd.undo")


class UndoService:
    """Orchestrates undo/redo operations by delegating to registered executors.

    When undo is requested for an event type:
    1. Look up the executor in the registry
    2. Check business rules via ``can_undo()``
    3. Execute reversal via ``undo()``
    4. Return compensating events

    Usage::

        service = UndoService(executor_registry)

        # Undo a domain event
        undo_events = await service.undo(order_created_event)
        # Returns list of compensating events (e.g., [OrderCancelled])

        # Redo a previously undone event
        redo_events = await service.redo(
            order_created_event,
            undo_event=order_cancelled_event,
        )
    """

    def __init__(self, registry: IUndoExecutorRegistry) -> None:
        self._registry = registry

    async def undo(self, event: DomainEvent) -> list[DomainEvent]:
        """Execute undo on a domain event.

        Args:
            event: The event to undo.

        Returns:
            List of compensating domain events (e.g., [Cancelled]).
            Empty list if undo cannot be performed.

        Raises:
            ValueError: If no executor is registered for the event type.
        """
        event_type = type(event).__name__
        executor = self._registry.get(event_type)

        if not executor:
            logger.warning("No UndoExecutor registered for event type '%s'", event_type)
            raise ValueError(
                f"No UndoExecutor registered for event type '{event_type}'"
            )

        # Check business rules
        can_undo = await executor.can_undo(event)
        if not can_undo:
            logger.info("Event '%s' cannot be undone (business rule)", event_type)
            return []

        # Execute undo
        try:
            undo_events = await executor.undo(event)
            logger.info(
                "Undo executed for event '%s', generated %d compensating events",
                event_type,
                len(undo_events),
            )
            return undo_events
        except Exception:
            logger.exception("Failed to undo event '%s'", event_type)
            raise

    async def redo(
        self,
        event: DomainEvent,
        undo_event: DomainEvent,
    ) -> list[DomainEvent]:
        """Re-apply a previously undone event.

        Args:
            event: The original event to redo.
            undo_event: The compensating event from the prior undo.

        Returns:
            List of events generated during redo.

        Raises:
            ValueError: If no executor is registered for the event type.
        """
        event_type = type(event).__name__
        executor = self._registry.get(event_type)

        if not executor:
            logger.warning("No UndoExecutor registered for event type '%s'", event_type)
            raise ValueError(
                f"No UndoExecutor registered for event type '{event_type}'"
            )

        # Execute redo
        try:
            redo_events = await executor.redo(event, undo_event)
            logger.info(
                "Redo executed for event '%s', generated %d events",
                event_type,
                len(redo_events),
            )
            return redo_events
        except Exception:
            logger.exception("Failed to redo event '%s'", event_type)
            raise
