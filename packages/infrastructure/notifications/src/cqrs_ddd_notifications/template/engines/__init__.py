"""Template rendering engines."""

from __future__ import annotations

from .string import StringFormatRenderer

try:
    from .jinja import JinjaTemplateRenderer

    __all__ = ["StringFormatRenderer", "JinjaTemplateRenderer"]
except ImportError:
    __all__ = ["StringFormatRenderer"]
