"""Filesystem template loader using Jinja2."""

from __future__ import annotations

import logging
from pathlib import Path

from ...delivery import NotificationChannel
from ...ports.provider import ITemplateProvider
from ...ports.renderer import NotificationTemplate

logger = logging.getLogger(__name__)


class FileSystemTemplateLoader(ITemplateProvider):
    """
    Loads notification templates from filesystem using Jinja2 Environment.
    Directory structure: templates/{channel}/{event_type}_{locale}.j2
    """

    def __init__(
        self,
        templates_dir: Path,
        autoescape: bool = True,
    ):
        self.templates_dir = templates_dir

        # Lazy import of jinja2
        try:
            from jinja2 import Environment, FileSystemLoader, select_autoescape

            autoescape_param = select_autoescape(["html", "xml"]) if autoescape else False
            self._env = Environment(
                loader=FileSystemLoader(str(templates_dir)),
                autoescape=autoescape_param,
            )
        except ImportError as e:
            raise ImportError(
                "Jinja2 is required for FileSystemTemplateLoader. "
                "Install with: pip install 'cqrs-ddd-notifications[jinja2]'"
            ) from e

    async def load(
        self,
        event_type: str,
        channel: NotificationChannel,
        locale: str,
    ) -> NotificationTemplate | None:
        """
        Load template from filesystem.

        Expected path: templates/{channel}/{event_type}_{locale}.j2
        """
        # Expected path: email/TwoFactorCodeRequested_en.j2
        filename = f"{channel.value}/{event_type}_{locale}.j2"
        try:
            template = self._env.get_template(filename)
            # Parse frontmatter or use convention for subject/body
            # For simplicity, we treat the entire file as body template
            # Subject can be defined via frontmatter: Subject: line
            template_source = template.module.__dict__.get("template_source") or getattr(
                template, "source", ""
            )
            subject, body = self._parse_template_content(template_source or "")

            return NotificationTemplate(
                template_id=f"{event_type}_{channel.value}_{locale}",
                channel=channel,
                subject_template=subject,
                body_template=body,
                locale=locale,
            )
        except Exception as e:
            logger.debug(f"Template not found: {filename} - {e}")
            return None

    def _parse_template_content(self, source: str) -> tuple[str | None, str]:
        """
        Parse template content for optional subject line.

        Format:
        ---
        Subject: {customer_name}, welcome!
        ---
        Body content here...
        """
        lines = source.split("\n")
        if len(lines) > 1 and "---" in lines[0]:
            parts = source.split("---", 2)
            if len(parts) == 3:
                frontmatter = parts[1].strip()
                body = parts[2].strip()
                # Parse subject from frontmatter
                for line in frontmatter.split("\n"):
                    if line.startswith("Subject:"):
                        return line[8:].strip(), body
                return None, body
        # No frontmatter, use entire source as body
        return None, source

    async def save(self, event_type: str, template: NotificationTemplate) -> None:
        """Not implemented for filesystem loader (read-only)."""
        raise NotImplementedError(
            "FileSystemTemplateLoader is read-only. "
            "Use InMemoryTemplateProvider for runtime registration."
        )
