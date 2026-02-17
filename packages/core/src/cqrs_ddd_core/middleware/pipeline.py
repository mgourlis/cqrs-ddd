"""build_pipeline — construct middleware chain."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from ..ports.middleware import IMiddleware


def build_pipeline(
    middlewares: list[IMiddleware],
    handler_fn: Callable[[Any], Any],
) -> Callable[[Any], Any]:
    """Build a LIFO middleware chain ending at *handler_fn*.

    The first middleware in the list is the **outermost** wrapper.
    Each middleware must implement: ``async def __call__(message, next_handler)``.
    """
    pipeline: Callable[[Any], Any] = handler_fn

    for mw in reversed(middlewares):
        current_next = pipeline  # capture for closure

        async def _wrapper(
            message: Any,
            _mw: IMiddleware = mw,
            _next: Callable[[Any], Any] = current_next,
        ) -> Any:
            return await _mw(message, _next)

        pipeline = _wrapper

    return pipeline
