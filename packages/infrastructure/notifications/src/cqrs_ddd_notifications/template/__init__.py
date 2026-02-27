"""Template registry and rendering components."""

from __future__ import annotations

from .engines.string import StringFormatRenderer
from .providers.memory import InMemoryTemplateProvider
from .registry import TemplateRegistry

__all__ = [
    "TemplateRegistry",
    "InMemoryTemplateProvider",
    "StringFormatRenderer",
]

# Optional Jinja2 components
try:
    from .engines.jinja import JinjaTemplateRenderer
    from .providers.filesystem import FileSystemTemplateLoader

    __all__.extend(["FileSystemTemplateLoader", "JinjaTemplateRenderer"])
except ImportError:
    pass
