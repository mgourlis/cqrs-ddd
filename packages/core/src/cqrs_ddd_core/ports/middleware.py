"""IMiddleware — LIFO middleware protocol."""

from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    Protocol,
    runtime_checkable,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


@runtime_checkable
class IMiddleware(Protocol):
    """Protocol for middleware in the command/query pipeline.

    Middleware wraps handler invocation and can inspect/modify messages,
    short-circuit execution, or perform side-effects.
    The chain is applied in **LIFO** order (first registered = outermost).
    """

    async def __call__(
        self,
        message: Any,
        next_handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        """Execute middleware logic and call next_handler to proceed.

        Parameters
        ----------
        message:
            The incoming message (command, query, or event).
        next_handler:
            Async callable representing the rest of the pipeline.

        Returns
        -------
        The result from the handler chain.
        """
        ...
