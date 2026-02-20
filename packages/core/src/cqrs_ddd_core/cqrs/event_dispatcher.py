"""EventDispatcher — dual-queue synchronous + background dispatch."""

from __future__ import annotations

import asyncio
import logging
from inspect import isawaitable
from typing import (
    TYPE_CHECKING,
    Generic,
    TypeVar,
    cast,
)

from cqrs_ddd_core.domain.events import DomainEvent
from cqrs_ddd_core.instrumentation import get_hook_registry

from ..correlation import get_correlation_id

logger = logging.getLogger(__name__)

E = TypeVar("E", bound=DomainEvent)
E_contra = TypeVar("E_contra", bound=DomainEvent, contravariant=True)


if TYPE_CHECKING:
    from ..ports.event_dispatcher import EventHandler


class EventDispatcher(Generic[E]):
    """Local execution engine for domain events.

    This class manages the local execution of domain event handlers. It holds
    handler **instances** and executes them concurrently using a semaphore
    to prevent process exhaustion.

    **Architectural Role**:
    - In the **Mediator**: Used to run synchronous, in-transaction handlers.
    - In the **Worker/Consumer**: Used to run asynchronous handlers after
      receiving them from a message broker.
    """

    def __init__(self, max_concurrency: int = 10) -> None:
        self._handlers: dict[type[E], list[EventHandler[E]]] = {}
        self._semaphore = asyncio.Semaphore(max_concurrency)

    # ── Registration ─────────────────────────────────────────────

    def register(
        self,
        event_type: type[E],
        handler: EventHandler[E],
    ) -> None:
        """Register a handler for a specific event type."""
        handlers = self._handlers.setdefault(event_type, [])
        if handler not in handlers:
            handlers.append(handler)

    # ── Dispatching ──────────────────────────────────────────────

    async def dispatch(self, events: list[DomainEvent]) -> None:
        """Dispatch events to all registered handlers concurrently."""
        if not events:
            return

        registry = get_hook_registry()
        for event in events:
            event_type = type(event)
            handlers = self._handlers.get(cast("type[E]", event_type), [])
            if not handlers:
                continue

            event_name = event_type.__name__
            correlation_id = get_correlation_id() or getattr(
                event, "correlation_id", None
            )
            attributes: dict[str, object] = {
                "event.type": event_name,
                "event.id": str(event.event_id),
                "message_type": type(event),
                "correlation_id": correlation_id,
            }

            async def _dispatch_handlers(
                current_handlers: list[EventHandler[E]] = handlers,
                current_event_name: str = event_name,
                base_attributes: dict[str, object] = attributes,
                current_event: DomainEvent = event,
            ) -> None:
                tasks = []
                for handler in current_handlers:
                    handler_name = type(handler).__name__
                    operation = f"event.handler.{current_event_name}.{handler_name}"
                    handler_attrs = {
                        "handler.type": handler_name,
                        **base_attributes,
                    }

                    async def _invoke_handler(
                        h: EventHandler[E] = handler,
                    ) -> None:
                        await self._invoke(h, current_event)

                    tasks.append(
                        registry.execute_all(
                            operation,
                            handler_attrs,
                            _invoke_handler,
                        )
                    )
                await asyncio.gather(*tasks)

            await registry.execute_all(
                f"event.dispatch.{event_name}",
                attributes,
                _dispatch_handlers,
            )

    async def _invoke(self, handler: EventHandler[E], event: DomainEvent) -> None:
        """Invoke a single handler within the concurrency limit."""
        async with self._semaphore:
            try:
                if hasattr(handler, "handle"):
                    result = handler.handle(cast("E", event))
                elif callable(handler):
                    result = handler(cast("E", event))
                else:
                    raise TypeError(
                        "Handler must be a callable or have a handle() method"
                    )

                if isawaitable(result):
                    await result
            except Exception:
                logger.exception(
                    "Error executing handler %s for event %s",
                    type(handler).__name__,
                    type(event).__name__,
                )
                raise

    # ── Introspection ────────────────────────────────────────────

    def get_registered_handlers(self) -> dict[type[E], list[EventHandler[E]]]:
        """Return all registered handlers (debugging utility)."""
        return {k: list(v) for k, v in self._handlers.items()}

    def clear(self) -> None:
        """Remove all handler registrations (testing utility)."""
        self._handlers.clear()
