"""Global Handler Registry with auto-discovery and conflict detection."""

from __future__ import annotations

import logging
from typing import Any

from ..primitives.exceptions import HandlerRegistrationError

logger = logging.getLogger(__name__)


class HandlerRegistry:
    """Primary declarative store for command, query, and event handlers.

    This is the **single source of truth** for your application's handler
    configuration. You should register your handler *classes* here during
    bootstrapping.

    When registering events, you can specify ``synchronous=True`` to mark them
    for synchronous, in-transaction execution. These are later loaded into
    the :class:`~cqrs_ddd_core.cqrs.event_dispatcher.EventDispatcher` for
    execution.

    **Conflict detection:** registering a second command handler (or
    query handler) for the same message type raises ``ValueError``.
    Multiple event handlers for the same event type are allowed.
    """

    def __init__(self) -> None:
        self._command_handlers: dict[type[Any], type[Any]] = {}
        self._query_handlers: dict[type[Any], type[Any]] = {}
        self._synchronous_event_handlers: dict[type[Any], list[type[Any]]] = {}
        self._asynchronous_event_handlers: dict[type[Any], list[type[Any]]] = {}

    # ── Registration ─────────────────────────────────────────────

    def register_command_handler(
        self, command_type: type[Any], handler_cls: type[Any]
    ) -> None:
        existing = self._command_handlers.get(command_type)
        if existing is not None and existing is not handler_cls:
            msg = (
                f"Duplicate command handler for {command_type.__name__}: "
                f"{existing.__name__} already registered, "
                f"cannot register {handler_cls.__name__}"
            )
            raise HandlerRegistrationError(msg)
        self._command_handlers[command_type] = handler_cls
        logger.debug(
            "Registered command handler %s -> %s",
            command_type.__name__,
            handler_cls.__name__,
        )

    def register_query_handler(
        self, query_type: type[Any], handler_cls: type[Any]
    ) -> None:
        existing = self._query_handlers.get(query_type)
        if existing is not None and existing is not handler_cls:
            msg = (
                f"Duplicate query handler for {query_type.__name__}: "
                f"{existing.__name__} already registered, "
                f"cannot register {handler_cls.__name__}"
            )
            raise HandlerRegistrationError(msg)
        self._query_handlers[query_type] = handler_cls
        logger.debug(
            "Registered query handler %s -> %s",
            query_type.__name__,
            handler_cls.__name__,
        )

    def register_event_handler(
        self,
        event_type: type[Any],
        handler_cls: type[Any],
        *,
        synchronous: bool = False,
    ) -> None:
        target_map = (
            self._synchronous_event_handlers
            if synchronous
            else self._asynchronous_event_handlers
        )
        handlers = target_map.setdefault(event_type, [])
        if handler_cls not in handlers:
            handlers.append(handler_cls)
            logger.debug(
                "Registered %s event handler %s -> %s",
                "synchronous" if synchronous else "background",
                event_type.__name__,
                handler_cls.__name__,
            )

    # ── Lookup ───────────────────────────────────────────────────

    def get_command_handler(self, command_type: type[Any]) -> type[Any] | None:
        return self._command_handlers.get(command_type)

    def get_query_handler(self, query_type: type[Any]) -> type[Any] | None:
        return self._query_handlers.get(query_type)

    def get_synchronous_event_handlers(self, event_type: type[Any]) -> list[type[Any]]:
        """Return all registered synchronous handlers for a specific event type."""
        return list(self._synchronous_event_handlers.get(event_type, []))

    def get_asynchronous_event_handlers(self, event_type: type[Any]) -> list[type[Any]]:
        """Return all registered asynchronous handlers for a specific event type."""
        return list(self._asynchronous_event_handlers.get(event_type, []))

    def get_event_handlers(self, event_type: type[Any]) -> dict[str, list[type[Any]]]:
        """Return all registered handlers for a specific event type (debugging)."""
        return {
            "synchronous": self.get_synchronous_event_handlers(event_type),
            "asynchronous": self.get_asynchronous_event_handlers(event_type),
        }

    def get_all_synchronous_event_handlers(self) -> dict[type[Any], list[type[Any]]]:
        """Return all registered synchronous event handlers."""
        return {k: list(v) for k, v in self._synchronous_event_handlers.items()}

    def get_all_asynchronous_event_handlers(self) -> dict[type[Any], list[type[Any]]]:
        """Return all registered asynchronous event handlers."""
        return {k: list(v) for k, v in self._asynchronous_event_handlers.items()}

    # ── Introspection ────────────────────────────────────────────

    def get_registered_handlers(self) -> dict[str, Any]:
        """Return a snapshot of all registered handlers (for debugging)."""
        return {
            "commands": {
                k.__name__: v.__name__ for k, v in self._command_handlers.items()
            },
            "queries": {
                k.__name__: v.__name__ for k, v in self._query_handlers.items()
            },
            "events": {
                "synchronous": {
                    k.__name__: [h.__name__ for h in v]
                    for k, v in self._synchronous_event_handlers.items()
                },
                "asynchronous": {
                    k.__name__: [h.__name__ for h in v]
                    for k, v in self._asynchronous_event_handlers.items()
                },
            },
        }

    # ── Cleanup ──────────────────────────────────────────────────

    def clear(self) -> None:
        """Clear all registered handlers (testing utility)."""
        self._command_handlers.clear()
        self._query_handlers.clear()
        self._synchronous_event_handlers.clear()
        self._asynchronous_event_handlers.clear()


__all__ = ["HandlerRegistry"]
