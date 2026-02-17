"""IEventUpcaster — protocol for evolving event schemas across versions."""

from __future__ import annotations

from typing import Any, Protocol


class IEventUpcaster(Protocol):
    """
    Interface for transforming a raw event dictionary from an older version
    to a newer version schema.

    The event data dict will always include:
    - ``aggregate_id``: Which aggregate instance this event belongs to
    - ``aggregate_type``: The aggregate class/type (Order, User, etc.)

    Upcasters can use this context for version-specific transformations.
    """

    @property
    def event_type(self) -> str:
        """The domain event class name this upcaster handles (e.g., 'OrderCreated')."""
        ...

    @property
    def source_version(self) -> int:
        """The source schema version this upcaster transforms from."""
        ...

    @property
    def target_version(self) -> int:
        """The target schema version this upcaster transforms to.

        By convention this is ``source_version + 1``.
        """
        ...

    def upcast(self, event_data: dict[str, Any]) -> dict[str, Any]:
        """
        Transforms the input data from an older schema to the next version.

        Args:
            event_data: Raw event dict with 'aggregate_id' and 'aggregate_type'

        Returns:
            Updated dictionary in the target schema version.
        """
        ...
