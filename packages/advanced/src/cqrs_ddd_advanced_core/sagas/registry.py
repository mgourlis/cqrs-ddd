"""SagaRegistry — maps event types to saga classes."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .orchestration import Saga

logger = logging.getLogger("cqrs_ddd.sagas")


class SagaRegistry:
    """
    Injectable registry that maps ``event_type`` → ``List[Type[Saga]]``.

    Multiple sagas can react to the same event type.  Saga classes are
    also registered by name for lookup during recovery / timeout
    handling.

    **Quick registration** via :meth:`register_saga`::

        saga_registry.register_saga(OrderFulfillmentSaga)
        # Automatically registers for all events declared in listened_events()

    **Manual registration** via :meth:`register`::

        saga_registry.register(OrderCreated, OrderFulfillmentSaga)
    """

    def __init__(self) -> None:
        self._event_map: dict[type, list[type[Saga[Any]]]] = {}
        self._type_map: dict[str, type[Saga[Any]]] = {}

    # ── Bulk Registration ────────────────────────────────────────────

    def register_saga(self, saga_class: type[Saga[Any]]) -> None:
        """Register a saga class for all events declared in :meth:`listened_events`.

        This is the preferred registration method.  It reads the class-level
        ``listened_events()`` declaration and registers the saga for each
        event type automatically::

            class OrderSaga(Saga[OrderSagaState]):
                @classmethod
                def listened_events(cls):
                    return [OrderCreated, PaymentReceived, ShipmentConfirmed]

            saga_registry.register_saga(OrderSaga)
            # Equivalent to:
            #   saga_registry.register(OrderCreated, OrderSaga)
            #   saga_registry.register(PaymentReceived, OrderSaga)
            #   saga_registry.register(ShipmentConfirmed, OrderSaga)

        If ``listened_events()`` returns an empty list, only the type-name
        mapping is registered (for recovery lookups).

        Raises:
            ValueError: If ``listened_events()`` is not implemented or
                returns a non-list.
        """
        events = saga_class.listened_events()
        if events:
            for event_type in events:
                self.register(event_type, saga_class)
        else:
            # Still register by name even if no events declared.
            self.register_type(saga_class)
            logger.warning(
                "Saga %s has no listened events (listens_to is empty). "
                "Set listens_to on the saga class or use SagaBuilder "
                "to enable event registration.",
                saga_class.__name__,
            )

    # ── Per-Event Registration ───────────────────────────────────────

    def register(self, event_type: type, saga_class: type[Saga[Any]]) -> None:
        """Register *saga_class* as a handler for *event_type*.

        Prefer :meth:`register_saga` for bulk registration using
        ``listened_events()``.
        """
        if event_type not in self._event_map:
            self._event_map[event_type] = []

        if saga_class not in self._event_map[event_type]:
            self._event_map[event_type].append(saga_class)
            logger.debug(
                "Registered Saga %s for event %s",
                saga_class.__name__,
                event_type.__name__,
            )

        # Also register by name for recovery lookups.
        self.register_type(saga_class)

    def register_type(self, saga_class: type[Saga[Any]]) -> None:
        """Register a saga class by its ``__name__`` only (no event binding)."""
        self._type_map[saga_class.__name__] = saga_class

    # ── Queries ──────────────────────────────────────────────────────

    @property
    def registered_event_types(self) -> list[type]:
        """Return all event types that have at least one saga registered."""
        return list(self._event_map.keys())

    def get_sagas_for_event(self, event_type: type) -> list[type[Saga[Any]]]:
        """Return all saga classes registered for *event_type*."""
        return self._event_map.get(event_type, [])

    def get_saga_type(self, name: str) -> type[Saga[Any]] | None:
        """Look up a saga class by its ``__name__``."""
        return self._type_map.get(name)

    # ── Housekeeping ─────────────────────────────────────────────────

    def clear(self) -> None:
        """Remove all registrations."""
        self._event_map.clear()
        self._type_map.clear()
