"""Mediator — central dispatch point with ContextVar UoW scope."""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, TypeVar, cast

from ..ports.bus import ICommandBus, IQueryBus

if TYPE_CHECKING:
    from collections.abc import Callable

    from ..domain.events import DomainEvent
    from ..middleware.registry import MiddlewareRegistry
    from ..ports.unit_of_work import UnitOfWork
    from .command import Command
    from .event_dispatcher import EventDispatcher
    from .handler import CommandHandler, QueryHandler
    from .query import Query
    from .registry import HandlerRegistry
    from .response import CommandResponse, QueryResponse

logger = logging.getLogger(__name__)

TResult = TypeVar("TResult")

#: ContextVar tracking the current UoW — ``None`` means we are not inside
#: any command scope yet (root command will create a new one).
_current_uow: ContextVar[Any] = ContextVar("current_uow", default=None)


def get_current_uow() -> Any:
    """Return the active UoW (or *None* if outside a command scope)."""
    return _current_uow.get()


class Mediator(ICommandBus, IQueryBus):
    """Routes commands / queries through middleware to their handlers.

    **UoW scope detection:** uses :data:`_current_uow` to decide whether
    the incoming command is a *root* command (needs a fresh UoW) or a
    *nested* command (reuses the parent UoW).

    Parameters
    ----------
    registry:
        :class:`~cqrs_ddd_core.cqrs.registry.HandlerRegistry` instance.
    uow_factory:
        Async callable (or class) that returns an ``IUnitOfWork``
        async-context-manager.
    middleware_registry:
        Optional :class:`~cqrs_ddd_core.middleware.registry.MiddlewareRegistry`.
    event_dispatcher:
        Optional
        :class:`~cqrs_ddd_core.cqrs.event_dispatcher.EventDispatcher`\
        ``[DomainEvent]``.
    handler_factory:
        Optional callable ``(handler_cls) -> handler_instance``.
        Defaults to simple ``handler_cls()`` construction.
    """

    def __init__(
        self,
        registry: HandlerRegistry,
        uow_factory: Callable[..., UnitOfWork],
        *,
        middleware_registry: MiddlewareRegistry | None = None,
        event_dispatcher: EventDispatcher[DomainEvent] | None = None,
        handler_factory: Callable[[type[Any]], Any] | None = None,
    ) -> None:
        self._registry = registry
        self._uow_factory = uow_factory
        self._middleware_registry = middleware_registry
        # Import EventDispatcher here to avoid circular dependencies
        # if it imports Mediator
        from .event_dispatcher import EventDispatcher as EventDispatcherImpl

        self._event_dispatcher = event_dispatcher or EventDispatcherImpl()
        self._handler_factory: Callable[[type[Any]], Any] = handler_factory or (
            lambda cls: cls()
        )

        # Auto-Ignition: Bind synchronous event handlers from the registry
        self.autoload_event_handlers()

    # ── Public API ───────────────────────────────────────────────

    async def send(self, command: Command[TResult]) -> CommandResponse[TResult]:
        """Dispatch a *command* through the middleware pipeline.

        Root commands open a new UoW and commit/rollback automatically.
        Nested commands reuse the existing UoW (no double-commit).
        """
        existing_uow = _current_uow.get()
        if existing_uow is not None:
            # Nested command — reuse parent UoW
            return await self._dispatch_command(command)

        # Root command — new UoW scope
        # Ensure correlation_id exists for tracking
        if not command.correlation_id:
            import uuid

            # Use model_copy to keep Command immutable if it's Pydantic
            command = command.model_copy(update={"correlation_id": str(uuid.uuid4())})

        async with self._uow_factory() as uow:
            token = _current_uow.set(uow)
            try:
                result = await self._dispatch_command(command)
                # Success -> Root command scope handles commit and hooks
                # in its __aexit__. The UnitOfWork will trigger hooks
                # after commit.
            finally:
                _current_uow.reset(token)

        return result

    def autoload_event_handlers(self) -> None:
        """Instantiate and bind synchronous event handlers from the registry.

        Uses the configured ``handler_factory`` to create instances of the
        handler classes registered in
        :class:`~cqrs_ddd_core.cqrs.registry.HandlerRegistry` as synchronous.
        """
        if not self._event_dispatcher:
            return

        factory = (
            self._handler_factory
            if self._handler_factory is not None
            else (lambda cls: cls())
        )
        handlers_map = self._registry.get_all_synchronous_event_handlers()

        for event_type, handlers in handlers_map.items():
            for handler_cls in handlers:
                handler_instance = factory(handler_cls)
                self._event_dispatcher.register(event_type, handler_instance)

    async def query(self, query: Query[TResult]) -> QueryResponse[TResult]:
        """Dispatch a *query* (no UoW, no middleware)."""
        # Ensure correlation_id exists for tracking
        if not query.correlation_id:
            import uuid

            query = query.model_copy(update={"correlation_id": str(uuid.uuid4())})

        handler_cls = self._registry.get_query_handler(type(query))
        if handler_cls is None:
            raise ValueError(f"No handler registered for query {type(query).__name__}")
        handler = cast("QueryHandler[TResult]", self._handler_factory(handler_cls))
        result = await handler.handle(query)

        # Propagate IDs to response
        propagated = self._propagate_ids(query, result)
        return cast("QueryResponse[TResult]", propagated)

    # ── Internals ────────────────────────────────────────────────

    async def _dispatch_command(
        self, command: Command[TResult]
    ) -> CommandResponse[TResult]:
        """Build the middleware chain and invoke the handler."""
        handler_cls = self._registry.get_command_handler(type(command))
        if handler_cls is None:
            raise ValueError(
                f"No handler registered for command {type(command).__name__}"
            )

        handler = cast("CommandHandler[TResult]", self._handler_factory(handler_cls))

        async def _innermost(cmd: Command[TResult]) -> CommandResponse[TResult]:
            return await handler.handle(cmd)

        # Build middleware pipeline using the pipeline builder
        if self._middleware_registry is not None:
            from ..middleware.pipeline import build_pipeline

            middlewares = self._middleware_registry.get_ordered_middlewares()
            pipeline = build_pipeline(middlewares, _innermost)
        else:
            pipeline = _innermost

        result = await pipeline(command)

        # Propagate IDs to response
        propagated = self._propagate_ids(command, result)
        result = cast("CommandResponse[TResult]", propagated)

        # In-transaction event dispatch (local handlers)
        if self._event_dispatcher:
            from ..domain.events import enrich_event_metadata

            # Enrich events with correlation and causation info
            enriched_events = [
                enrich_event_metadata(
                    e,
                    correlation_id=result.correlation_id,
                    causation_id=result.causation_id,
                )
                for e in result.events
            ]

            # Update result with enriched events
            result = result.__class__(
                result=result.result,
                events=enriched_events,
                success=result.success,
                correlation_id=result.correlation_id,
                causation_id=result.causation_id,
            )

            await self._event_dispatcher.dispatch(result.events)

        return result

    def _propagate_ids(self, message: Any, response: Any) -> Any:
        """Propagate correlation ID and causation ID from command/query to response."""
        correlation_id = getattr(response, "correlation_id", None) or getattr(
            message, "correlation_id", None
        )

        causation_id = getattr(response, "causation_id", None)
        if not causation_id:
            causation_id = getattr(message, "command_id", None) or getattr(
                message, "query_id", None
            )

        # CommandResponse and QueryResponse are frozen dataclasses, use replace
        from dataclasses import replace

        return replace(
            response, correlation_id=correlation_id, causation_id=causation_id
        )
