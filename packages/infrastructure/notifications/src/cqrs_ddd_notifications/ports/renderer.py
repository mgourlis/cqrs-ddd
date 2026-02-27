"""Template renderer port."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from ..delivery import NotificationChannel, RenderedNotification


@dataclass(frozen=True)
class NotificationTemplate:
    """Immutable template definition."""

    template_id: str
    channel: NotificationChannel
    subject_template: str | None = None
    body_template: str = ""
    locale: str = "en"


@runtime_checkable
class ITemplateRenderer(Protocol):
    """Protocol for rendering notification templates."""

    async def render(
        self,
        template: NotificationTemplate,
        context: dict[str, Any],
    ) -> RenderedNotification:
        """Render template with context."""
        ...
