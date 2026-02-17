"""MiddlewareRegistry — declarative registration with ordering."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .definition import MiddlewareDefinition

if TYPE_CHECKING:
    from collections.abc import Callable

    from ..ports.middleware import IMiddleware

logger = logging.getLogger(__name__)


class MiddlewareRegistry:
    """Collects middleware definitions and produces an ordered list.

    Middleware is registered with a ``priority`` — lower values execute
    first (outermost in the LIFO chain).
    """

    def __init__(self) -> None:
        self._definitions: list[MiddlewareDefinition] = []
        self._instances: list[IMiddleware] | None = None  # cache

    # ── Registration ─────────────────────────────────────────────

    def register(
        self,
        middleware_cls: type[Any],
        *,
        priority: int = 0,
        factory: Callable[..., IMiddleware] | None = None,
        **kwargs: object,
    ) -> None:
        """Register a middleware class.

        Parameters
        ----------
        middleware_cls:
            The middleware class (must implement ``apply(command, next)``).
        priority:
            Lower = outermost in pipe.  Default ``0``.
        factory:
            Optional custom constructor.
        **kwargs:
            Passed to the constructor or factory.
        """
        defn: MiddlewareDefinition = MiddlewareDefinition(
            middleware_cls=middleware_cls,
            priority=priority,
            factory=factory,
            kwargs=kwargs,
        )
        self._definitions.append(defn)
        self._instances = None  # invalidate cache
        logger.debug(
            "Registered middleware %s (priority=%d)", middleware_cls.__name__, priority
        )

    def add(
        self,
        middleware_cls: type[Any] | None = None,
        *,
        priority: int = 0,
        factory: Callable[..., IMiddleware] | None = None,
        **kwargs: object,
    ) -> Any:
        """Decorator-style registration.

        Usage::

            @registry.add
            class MyMiddleware: ...

            @registry.add(priority=10)
            class HighPriorityMiddleware: ...
        """
        if middleware_cls is None:
            # Called as @registry.add(priority=...)
            def wrapper(cls: type[Any]) -> type[Any]:
                self.register(cls, priority=priority, factory=factory, **kwargs)
                return cls

            return wrapper

        # Called as @registry.add
        self.register(middleware_cls, priority=priority, factory=factory, **kwargs)
        return middleware_cls

    # ── Retrieval ────────────────────────────────────────────────

    def get_ordered_middlewares(self) -> list[IMiddleware]:
        """Return middleware instances sorted by priority (ascending)."""
        if self._instances is None:
            sorted_defs = sorted(self._definitions, key=lambda d: d.priority)
            self._instances = [d.build() for d in sorted_defs]
        return list(self._instances)

    # ── Cleanup ──────────────────────────────────────────────────

    def clear(self) -> None:
        """Remove all registrations (testing utility)."""
        self._definitions.clear()
        self._instances = None
