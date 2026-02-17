"""Bus protocols — ICommandBus and IQueryBus."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypeVar

if TYPE_CHECKING:
    from ..cqrs.command import Command
    from ..cqrs.query import Query
    from ..cqrs.response import CommandResponse, QueryResponse

TResult = TypeVar("TResult")


class ICommandBus(Protocol):
    """
    Interface for dispatching commands to their respective handlers.
    """

    async def send(self, command: Command[TResult]) -> CommandResponse[TResult]: ...


class IQueryBus(Protocol):
    """
    Interface for dispatching queries to their respective handlers.
    """

    async def query(self, query: Query[TResult]) -> QueryResponse[TResult]: ...
