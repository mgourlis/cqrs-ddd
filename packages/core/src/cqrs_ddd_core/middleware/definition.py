"""MiddlewareDefinition — descriptor for middleware in pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..utils import default_dict_factory

if TYPE_CHECKING:
    from collections.abc import Callable

    from ..ports.middleware import IMiddleware


@dataclass
class MiddlewareDefinition:
    """Descriptor for a middleware in the pipeline.

    Supports **deferred instantiation**: supply *middleware_cls* and
    optional *factory* for lazy construction.
    """

    middleware_cls: type[IMiddleware]
    priority: int = 0
    factory: Callable[..., IMiddleware] | None = None
    kwargs: dict[str, object] = field(default_factory=default_dict_factory)

    def build(self) -> IMiddleware:
        """Construct the middleware instance."""
        if self.factory is not None:
            return self.factory(**self.kwargs)
        return self.middleware_cls(**self.kwargs)
