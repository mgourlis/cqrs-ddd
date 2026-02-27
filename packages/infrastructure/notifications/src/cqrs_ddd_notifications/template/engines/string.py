"""Zero-dependency string format renderer."""

from __future__ import annotations

import logging
from typing import Any

from cqrs_ddd_notifications.delivery import RenderedNotification
from cqrs_ddd_notifications.ports.renderer import ITemplateRenderer, NotificationTemplate

logger = logging.getLogger(__name__)


class StringFormatRenderer(ITemplateRenderer):
    """
    Simple renderer using Python's native string formatting.
    No external dependencies.
    """

    async def render(
        self, template: NotificationTemplate, context: dict[str, Any]
    ) -> RenderedNotification:
        """Render template using str.format()."""
        try:
            subject = None
            if template.subject_template:
                subject = template.subject_template.format(**context)

            body = template.body_template.format(**context)

            return RenderedNotification(
                subject=subject,
                body_text=body,
            )
        except KeyError as e:
            logger.error(f"Missing template variable: {e}")
            raise
        except Exception as e:
            logger.error(f"Template rendering failed: {e}")
            raise
