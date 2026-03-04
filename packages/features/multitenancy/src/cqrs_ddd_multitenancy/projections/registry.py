"""TenantAwareProjectionRegistry — wraps handlers with tenant context.

Decorator for ``IProjectionRegistry`` that automatically wraps every
returned handler with ``MultitenantProjectionHandler``, so that events
are always dispatched with the correct tenant context.

Usage::

    from cqrs_ddd_projections import ProjectionRegistry
    from cqrs_ddd_multitenancy.projections import TenantAwareProjectionRegistry

    inner = ProjectionRegistry()
    registry = TenantAwareProjectionRegistry(inner)
    registry.register(my_handler)
    # Handlers returned by get_handlers() will set tenant context automatically
"""

from __future__ import annotations

import logging
from typing import Any

from .handler import MultitenantProjectionHandler

__all__ = [
    "TenantAwareProjectionRegistry",
]

logger = logging.getLogger(__name__)


class TenantAwareProjectionRegistry:
    """Wraps an ``IProjectionRegistry`` so that all handlers returned
    by ``get_handlers()`` are automatically wrapped with
    ``MultitenantProjectionHandler``.

    The registry delegates ``register()`` directly to the inner registry,
    and wraps each handler returned by ``get_handlers()`` on-the-fly.

    Args:
        inner: The underlying projection registry to wrap.
        tenant_column: Metadata key to extract the tenant ID from.
            Defaults to ``"tenant_id"``.
        skip_system_events: Whether system tenant events should bypass
            tenant context switching. Defaults to ``True``.
    """

    def __init__(
        self,
        inner: Any,
        *,
        tenant_column: str = "tenant_id",
        skip_system_events: bool = True,
    ) -> None:
        self._inner = inner
        self._tenant_column = tenant_column
        self._skip_system_events = skip_system_events
        # Cache wrapped handlers to avoid re-wrapping
        self._wrapped_cache: dict[int, MultitenantProjectionHandler] = {}

    def register(self, handler: Any) -> None:
        """Delegate registration to the inner registry (unwrapped)."""
        self._inner.register(handler)

    def get_handlers(self, event_type: str) -> list[Any]:
        """Return handlers wrapped with ``MultitenantProjectionHandler``.

        Each inner handler is wrapped exactly once (cached by ``id``).
        """
        inner_handlers = self._inner.get_handlers(event_type)
        return [self._wrap(h) for h in inner_handlers]

    def _wrap(self, handler: Any) -> MultitenantProjectionHandler:
        """Wrap a handler with tenant context, caching by identity."""
        handler_id = id(handler)
        if handler_id not in self._wrapped_cache:
            self._wrapped_cache[handler_id] = MultitenantProjectionHandler(
                handler,
                tenant_column=self._tenant_column,
                skip_system_events=self._skip_system_events,
            )
        return self._wrapped_cache[handler_id]
