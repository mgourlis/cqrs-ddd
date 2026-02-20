"""Tests for ProjectionRegistry."""

from __future__ import annotations

from cqrs_ddd_core.domain.events import DomainEvent
from cqrs_ddd_projections.ports import IProjectionHandler
from cqrs_ddd_projections.registry import ProjectionRegistry


class FakeEvent(DomainEvent):
    pass


class HandlerA(IProjectionHandler):
    handles: set[type[DomainEvent]] = {FakeEvent}

    async def handle(self, event: DomainEvent) -> None:
        pass


def test_register_and_get() -> None:
    reg = ProjectionRegistry()
    reg.register(HandlerA())
    assert len(reg.get_handlers("FakeEvent")) == 1
    assert reg.get_handlers("Other") == []


def test_multiple_handlers_same_event() -> None:
    class HandlerB(IProjectionHandler):
        handles: set[type[DomainEvent]] = {FakeEvent}

        async def handle(self, event: DomainEvent) -> None:
            pass

    reg = ProjectionRegistry()
    reg.register(HandlerA())
    reg.register(HandlerB())
    assert len(reg.get_handlers("FakeEvent")) == 2
