"""Multi-channel notification infrastructure for CQRS/DDD — Email, SMS, Push, Webhooks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .delivery import (
    AttachmentVO,
    DeliveryRecord,
    DeliveryStatus,
    NotificationChannel,
    RenderedNotification,
)
from .handler import NotificationEventHandler
from .ports.provider import ITemplateProvider
from .ports.renderer import ITemplateRenderer, NotificationTemplate
from .ports.sender import INotificationSender
from .ports.tracker import IDeliveryTracker

# Template engines
from .template.engines.string import StringFormatRenderer

if TYPE_CHECKING:
    from .template.engines.jinja import JinjaTemplateRenderer
else:
    try:
        from .template.engines.jinja import JinjaTemplateRenderer as _JinjaTemplateRenderer
        JinjaTemplateRenderer = _JinjaTemplateRenderer  # type: ignore[misc]
        _jinja_available = True
    except ImportError:
        _jinja_available = False
        JinjaTemplateRenderer = None  # type: ignore[assignment]

# Template registry and providers
# Memory adapters for testing
from .memory.console import ConsoleSender
from .memory.fake import InMemorySender

# Sanitization
from .sanitization import MetadataSanitizer
from .template.providers.filesystem import FileSystemTemplateLoader
from .template.providers.memory import InMemoryTemplateProvider
from .template.registry import TemplateRegistry

__all__ = [
    "AttachmentVO",
    "DeliveryRecord",
    "DeliveryStatus",
    "NotificationChannel",
    "NotificationEventHandler",
    "NotificationTemplate",
    "RenderedNotification",
    "INotificationSender",
    "ITemplateRenderer",
    "IDeliveryTracker",
    "ITemplateProvider",
    "StringFormatRenderer",
    "JinjaTemplateRenderer",
    "TemplateRegistry",
    "InMemoryTemplateProvider",
    "FileSystemTemplateLoader",
    "ConsoleSender",
    "InMemorySender",
    "MetadataSanitizer",
]
