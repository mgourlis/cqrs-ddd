"""Handler base classes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Generic, TypeVar

if TYPE_CHECKING:
    from .command import Command
    from .query import Query
    from .response import CommandResponse, QueryResponse

TResult = TypeVar("TResult")  # Result type
E = TypeVar("E")  # Event type


class CommandHandler(ABC, Generic[TResult]):
    """Base class for command handlers.

    Handlers must be registered explicitly with a ``HandlerRegistry``.
    See :class:`~cqrs_ddd_core.cqrs.mediator.Mediator` for dependency injection.

    Usage::

        class CreateOrderHandler(CommandHandler[OrderId]):
            async def handle(
                self, command: CreateOrderCommand
            ) -> CommandResponse[OrderId]:
                ...
    """

    @abstractmethod
    async def handle(self, command: Command[TResult]) -> CommandResponse[TResult]:
        """Execute the command and return a CommandResponse."""
        ...


class QueryHandler(ABC, Generic[TResult]):
    """Base class for query handlers.

    Handlers must be registered explicitly with a ``HandlerRegistry``.
    See :class:`~cqrs_ddd_core.cqrs.mediator.Mediator` for dependency injection.

    Usage::

        class GetOrderHandler(QueryHandler[OrderDTO]):
            async def handle(self, query: GetOrderQuery) -> QueryResponse[OrderDTO]:
                ...
    """

    @abstractmethod
    async def handle(self, query: Query[TResult]) -> QueryResponse[TResult]:
        """Execute the query and return a QueryResponse."""
        ...


class EventHandler(ABC, Generic[E]):
    """Base class for domain-event handlers.

    Handlers must be registered explicitly with the event dispatcher.

    Usage::

        class OrderCreatedHandler(EventHandler[OrderCreated]):
            async def handle(self, event: OrderCreated) -> None:
                ...
    """

    @abstractmethod
    async def handle(self, event: E) -> None:
        """React to the domain event."""
        ...
