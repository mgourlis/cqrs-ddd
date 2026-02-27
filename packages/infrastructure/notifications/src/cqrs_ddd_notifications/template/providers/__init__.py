"""Template provider implementations."""

from __future__ import annotations

from .memory import InMemoryTemplateProvider

try:
    from .filesystem import FileSystemTemplateLoader

    __all__ = ["InMemoryTemplateProvider", "FileSystemTemplateLoader"]
except ImportError:
    __all__ = ["InMemoryTemplateProvider"]
