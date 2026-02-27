"""Template registry for event/channel/locale lookup."""

from __future__ import annotations

import logging

from ..delivery import NotificationChannel
from ..ports.renderer import NotificationTemplate
from .providers.memory import InMemoryTemplateProvider

logger = logging.getLogger(__name__)


class TemplateRegistry:
    """
    Registry for notification templates with in-memory fallback.

    Can be composed with ITemplateProvider implementations
    for filesystem or database-backed templates.
    """

    def __init__(self, provider: InMemoryTemplateProvider | None = None):
        self._provider = provider or InMemoryTemplateProvider()

    async def get(
        self,
        event_type: str,
        channel: NotificationChannel,
        locale: str = "en",
    ) -> NotificationTemplate | None:
        """Get template by event type, channel, and locale."""
        return await self._provider.load(event_type, channel, locale)

    async def register(
        self,
        event_type: str,
        template: NotificationTemplate,
    ) -> None:
        """Register a template via the provider."""
        await self._provider.save(event_type, template)
