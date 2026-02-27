"""Template provider port for external sources."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..delivery import NotificationChannel
from ..ports.renderer import NotificationTemplate


@runtime_checkable
class ITemplateProvider(Protocol):
    """
    Protocol for loading templates from external sources.

    Implementations: InMemoryTemplateProvider, FileSystemTemplateLoader.
    """

    async def load(
        self,
        event_type: str,
        channel: NotificationChannel,
        locale: str,
    ) -> NotificationTemplate | None:
        """Load template by event type, channel, and locale."""
        ...
