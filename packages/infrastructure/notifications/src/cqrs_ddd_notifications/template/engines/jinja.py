"""Jinja2 template renderer."""

from __future__ import annotations

import logging
from typing import Any

from cqrs_ddd_notifications.delivery import RenderedNotification
from cqrs_ddd_notifications.ports.renderer import ITemplateRenderer, NotificationTemplate

logger = logging.getLogger(__name__)

try:
    from jinja2 import StrictUndefined
    from jinja2 import Template as JinjaTemplate

    _JINJA2_AVAILABLE = True
except ImportError:
    _JINJA2_AVAILABLE = False
    JinjaTemplate = None


class JinjaTemplateRenderer(ITemplateRenderer):
    """
    Renders notifications using the Jinja2 engine.
    """

    def __init__(self) -> None:
        if not _JINJA2_AVAILABLE or JinjaTemplate is None:
            raise ImportError(
                "Jinja2 is required. Install with: pip install 'cqrs-ddd-notifications[jinja2]'"
            )

    async def render(
        self, template: NotificationTemplate, context: dict[str, Any]
    ) -> RenderedNotification:
        """Render template using Jinja2."""
        try:
            # Render Subject (if applicable to the channel, like Email)
            subject = None
            if template.subject_template:
                subject = JinjaTemplate(
                    template.subject_template,
                    undefined=StrictUndefined,
                ).render(**context)

            # Render Body
            body = JinjaTemplate(
                template.body_template,
                undefined=StrictUndefined,
            ).render(**context)

            # Detect HTML and set body_html if applicable
            body_html = None
            if "<html>" in body.lower() or "<body>" in body.lower():
                body_html = body

            return RenderedNotification(
                subject=subject,
                body_text=body,
                body_html=body_html,
            )
        except Exception as e:
            logger.error(f"Jinja2 rendering failed: {e}")
            raise
