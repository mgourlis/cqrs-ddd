"""Notification event handler — bridges domain events to notification delivery."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, cast

from cqrs_ddd_core.correlation import get_causation_id, get_correlation_id

from .channel import ChannelRouter
from .delivery import NotificationChannel, RenderedNotification
from .ports.renderer import ITemplateRenderer
from .ports.sender import INotificationSender
from .ports.tracker import IDeliveryTracker
from .sanitization import MetadataSanitizer, default_sanitizer

logger = logging.getLogger(__name__)


class NotificationEventHandler:
    """
    Infrastructure handler that bridges Domain Events to actual notifications.
    Coordinates template retrieval, rendering, and multi-channel dispatch.
    """

    def __init__(
        self,
        sender: INotificationSender,
        renderer: ITemplateRenderer,
        registry: Any,  # TemplateRegistry
        router: ChannelRouter,
        tracker: IDeliveryTracker | None = None,
        sanitizer: MetadataSanitizer | None = None,
    ):
        self.sender = sender
        self.renderer = renderer
        self.registry = registry
        self.router = router
        self.tracker = tracker
        self.sanitizer = sanitizer or default_sanitizer

    async def handle(self, event: Any) -> None:
        """
        Processes a domain event and dispatches notifications to resolved channels.
        """
        # 1. Resolve recipient and target channels (e.g., from User Preferences)
        recipient_info = await self.router.resolve(event)
        if not recipient_info:
            logger.debug(f"No notification routing found for event {type(event).__name__}")
            return

        recipient = recipient_info.address
        locale = recipient_info.locale or "en"
        channels = recipient_info.channels

        # 2. Build safe metadata with correlation context (NOT raw event data!)
        base_metadata = self._build_safe_metadata(event)

        # 3. Dispatch to each channel concurrently
        tasks = [
            self._process_single_channel(event, recipient, channel, locale, base_metadata)
            for channel in channels
        ]

        # Use return_exceptions=True to ensure one provider failure doesn't
        # stop the execution of other notification channels.
        await asyncio.gather(*tasks, return_exceptions=True)

    def _build_safe_metadata(self, event: Any) -> dict[str, Any]:
        """
        Build metadata with ONLY safe, explicitly-extracted fields.
        Never pass raw event.__dict__ to prevent PII leakage.
        """
        raw_metadata = {
            "event_id": getattr(event, "id", None),
            "event_type": type(event).__name__,
            "correlation_id": get_correlation_id(),
            "causation_id": get_causation_id(),
        }
        # Sanitize to catch any accidentally included sensitive fields
        return self.sanitizer.sanitize(raw_metadata)

    async def _process_single_channel(
        self,
        event: Any,
        recipient: str,
        channel: NotificationChannel,
        locale: str,
        metadata: dict[str, Any],
    ) -> None:
        try:
            # 4. Fetch the template associated with this event type and channel
            template = await self.registry.get(
                event_type=type(event).__name__,
                channel=channel,
                locale=locale,
            )

            if not template:
                logger.warning(f"No template registered for {type(event).__name__} on {channel}")
                return

            # 5. Render content using event's notification context
            context = self._get_template_context(event)
            content: RenderedNotification = await self.renderer.render(
                template=template,
                context=context,
            )

            # 6. Send via the specific channel implementation (metadata already sanitized)
            record = await self.sender.send(
                recipient=recipient,
                content=content,
                channel=channel,
                metadata=metadata,
            )

            # 7. Record delivery status if a tracker is provided
            if self.tracker:
                await self.tracker.record(record)

        except Exception as e:
            logger.error(
                f"Failed to dispatch {channel} notification for {type(event).__name__}: {str(e)}",
                exc_info=True,
            )

    def _get_template_context(self, event: Any) -> dict[str, Any]:
        """
        Extract template context from event.

        Prefers to_notification_context() if available, falls back to __dict__
        (but sanitizes sensitive fields for rendering safety).
        """
        if hasattr(event, "to_notification_context"):
            return cast(dict[str, Any], event.to_notification_context())
        # Fallback: use __dict__ but sanitize for template rendering
        # (this is for templates, not metadata, so email/phone are preserved)
        raw = vars(event) if hasattr(event, "__dict__") else {}
        return self.sanitizer.sanitize(raw)
