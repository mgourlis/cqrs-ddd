"""Template registry and rendering components."""

from __future__ import annotations

import importlib.util

from .engines.string import StringFormatRenderer
from .providers.memory import InMemoryTemplateProvider
from .registry import TemplateRegistry

__all__ = [
    "TemplateRegistry",
    "InMemoryTemplateProvider",
    "StringFormatRenderer",
]

# Optional Jinja2 components
if importlib.util.find_spec("jinja2") is not None:
    from .engines.jinja import JinjaTemplateRenderer  # noqa: F401
    from .providers.filesystem import FileSystemTemplateLoader  # noqa: F401

    __all__.extend(["FileSystemTemplateLoader", "JinjaTemplateRenderer"])
