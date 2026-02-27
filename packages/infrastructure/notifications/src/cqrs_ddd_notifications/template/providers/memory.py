"""In-memory template provider for simple use cases."""

from __future__ import annotations

from typing import Dict, Tuple

from ...delivery import NotificationChannel
from ...ports.provider import ITemplateProvider
from ...ports.renderer import NotificationTemplate


class InMemoryTemplateProvider(ITemplateProvider):
    """Simple in-memory template provider for testing and inline templates."""

    def __init__(self) -> None:
        # Key: (event_name, channel, locale)
        self._templates: Dict[Tuple[str, NotificationChannel, str], NotificationTemplate] = {}

    async def load(
        self,
        event_type: str,
        channel: NotificationChannel,
        locale: str,
    ) -> NotificationTemplate | None:
        """Load template from memory."""
        return self._templates.get((event_type, channel, locale))

    async def save(self, event_type: str, template: NotificationTemplate) -> None:
        """Save template to memory."""
        key = (event_type, template.channel, template.locale)
        self._templates[key] = template
