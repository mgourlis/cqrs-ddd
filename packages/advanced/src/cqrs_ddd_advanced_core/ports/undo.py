"""IUndoExecutor / IUndoExecutorRegistry — undo/redo pattern protocols."""

from __future__ import annotations

from typing import Any, Protocol, TypeVar, runtime_checkable

from cqrs_ddd_core.domain.events import DomainEvent

T = TypeVar("T", bound=DomainEvent, contravariant=True)


@runtime_checkable
class IUndoExecutor(Protocol[T]):
    """
    Port for reversing a specific domain event type.

    Each event type that supports undo has a corresponding executor.
    The event carries ``aggregate_id`` and ``aggregate_type``, so the executor
    knows which aggregate instance to load and modify.
    """

    @property
    def event_type(self) -> str:
        """The domain event type name this executor handles."""
        ...

    async def can_undo(self, event: T) -> bool:
        """Return *True* if the event can still be undone (business rules).

        Implementation should:
        1. Extract aggregate_id from event
        2. Load aggregate from repository
        3. Check if undo is allowed (time window, state, etc.)
        """
        ...

    async def undo(self, event: T) -> list[DomainEvent]:
        """Execute undo, returning compensating events.

        Implementation should:
        1. Extract aggregate_id and aggregate_type from event
        2. Load the aggregate from repository
        3. Apply undo logic (revert state changes)
        4. Save aggregate and return compensating events
        """
        ...

    async def redo(self, event: T, undo_event: DomainEvent) -> list[DomainEvent]:
        """Re-apply a previously undone event.

        Args:
            event: The original event to redo
            undo_event: The compensating event from the prior undo (required)

        Returns:
            List of events generated during redo
        """
        ...


@runtime_checkable
class IUndoExecutorRegistry(Protocol):
    """Port for looking up undo executors by event type."""

    def register(self, executor: IUndoExecutor[Any]) -> None:
        """Register an undo executor instance."""
        ...

    def get(self, event_type: str) -> IUndoExecutor[Any] | None:
        """Get the executor for *event_type*, or *None*."""
        ...

    def has_executor(self, event_type: str) -> bool:
        """Return *True* if an executor is registered for *event_type*."""
        ...
