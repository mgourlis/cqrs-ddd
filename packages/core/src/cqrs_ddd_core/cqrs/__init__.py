"""CQRS primitives: commands, queries, handlers, mediator, dispatching."""

from __future__ import annotations

from ..ports.unit_of_work import UnitOfWork
from .command import Command
from .consumers import BaseEventConsumer
from .event_dispatcher import EventDispatcher
from .handler import CommandHandler, EventHandler, QueryHandler
from .mediator import Mediator, get_current_uow
from .outbox import BufferedOutbox, OutboxService
from .publishers import PublishingEventHandler, TopicRoutingPublisher, route_to
from .query import Query
from .registry import HandlerRegistry
from .response import CommandResponse, QueryResponse

__all__ = [
    "Command",
    "CommandHandler",
    "CommandResponse",
    "EventHandler",
    "EventDispatcher",
    "Mediator",
    "Query",
    "QueryHandler",
    "QueryResponse",
    "HandlerRegistry",
    "UnitOfWork",
    "get_current_uow",
    "BufferedOutbox",
    "OutboxService",
    "BaseEventConsumer",
    "TopicRoutingPublisher",
    "PublishingEventHandler",
    "route_to",
]
