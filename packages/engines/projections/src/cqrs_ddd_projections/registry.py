"""ProjectionRegistry — maps event types to handlers."""

from __future__ import annotations

from typing import Any

from .ports import IProjectionHandler, IProjectionRegistry


class ProjectionRegistry(IProjectionRegistry):
    """Maps event type names to list of handlers;
    multiple handlers per event supported."""

    def __init__(self) -> None:
        self._by_type: dict[str, list[IProjectionHandler]] = {}

    def register(self, handler: IProjectionHandler) -> None:
        for event_cls in handler.handles:
            name = getattr(event_cls, "__name__", str(event_cls))
            self._by_type.setdefault(name, []).append(handler)

    def get_handlers(self, event_type: str) -> list[Any]:
        return list(self._by_type.get(event_type, []))
