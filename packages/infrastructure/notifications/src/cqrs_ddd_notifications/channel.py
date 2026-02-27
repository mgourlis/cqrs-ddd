"""Channel routing and recipient resolution."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from .delivery import NotificationChannel

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RecipientInfo:
    """Resolved recipient information."""

    address: str
    channels: list[NotificationChannel]
    locale: str | None = None


class ChannelRouter:
    """
    Base router that resolves recipient information from events.

    Subclass or replace to implement custom routing logic
    (e.g., user preferences, tenant-specific routing).
    """

    async def resolve(self, event: Any) -> RecipientInfo | None:
        """
        Resolve recipient information from a domain event.

        Override this method to implement custom routing logic.
        Return None to skip notification for this event.
        """
        logger.debug(f"No routing configured for event {type(event).__name__}")
        return None
