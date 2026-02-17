"""UndoExecutorRegistry — maps event types to their undo executors."""

from __future__ import annotations

import logging
from typing import Any

from ..ports.undo import IUndoExecutor, IUndoExecutorRegistry

logger = logging.getLogger("cqrs_ddd.undo")


class UndoExecutorRegistry(IUndoExecutorRegistry):
    """Concrete registry of undo executors indexed by event type name.

    Usage::

        registry = UndoExecutorRegistry()
        executor = OrderCreatedUndoExecutor()
        registry.register(executor)

        # Later, lookup by event type
        found = registry.get("OrderCreated")
    """

    def __init__(self) -> None:
        self._executors: dict[str, IUndoExecutor[Any]] = {}

    def register(self, executor: IUndoExecutor[Any]) -> None:
        """Register an undo executor by event type."""
        event_type = executor.event_type
        self._executors[event_type] = executor
        logger.debug(
            "Registered UndoExecutor for %s: %s",
            event_type,
            type(executor).__name__,
        )

    def get(self, event_type: str) -> IUndoExecutor[Any] | None:
        """Look up an executor by event type name."""
        return self._executors.get(event_type)

    def has_executor(self, event_type: str) -> bool:
        """Return True if an executor is registered for event_type."""
        return event_type in self._executors

    def list_executors(self) -> dict[str, IUndoExecutor[Any]]:
        """Return all registered executors (shallow copy)."""
        return dict(self._executors)

    def clear(self) -> None:
        """Remove all executors (testing utility)."""
        self._executors.clear()
