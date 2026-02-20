"""Tests for ProjectionHandler dispatch mapping."""

from __future__ import annotations

import pytest

from cqrs_ddd_core.domain.events import DomainEvent
from cqrs_ddd_projections.handler import ProjectionHandler


class BaseEvent(DomainEvent):
    value: int = 0


class ChildEvent(BaseEvent):
    pass


class OtherEvent(DomainEvent):
    pass


@pytest.mark.asyncio
async def test_add_handler_registers_event_type() -> None:
    projection = ProjectionHandler()

    async def on_base(event: DomainEvent) -> None:
        return None

    projection.add_handler(BaseEvent, on_base)

    assert projection.handles == {BaseEvent}


@pytest.mark.asyncio
async def test_handle_dispatches_exact_event_type() -> None:
    projection = ProjectionHandler()
    seen: list[int] = []

    async def on_base(event: DomainEvent) -> None:
        assert isinstance(event, BaseEvent)
        seen.append(event.value)

    projection.add_handler(BaseEvent, on_base)

    await projection.handle(BaseEvent(value=7))

    assert seen == [7]


@pytest.mark.asyncio
async def test_handle_uses_parent_mapping_fallback() -> None:
    projection = ProjectionHandler()
    seen: list[int] = []

    async def on_base(event: DomainEvent) -> None:
        assert isinstance(event, BaseEvent)
        seen.append(event.value)

    projection.add_handler(BaseEvent, on_base)

    await projection.handle(ChildEvent(value=11))

    assert seen == [11]


@pytest.mark.asyncio
async def test_handle_noop_for_unmapped_event() -> None:
    projection = ProjectionHandler()
    called = False

    async def on_base(event: DomainEvent) -> None:
        nonlocal called
        called = True

    projection.add_handler(BaseEvent, on_base)

    await projection.handle(OtherEvent())

    assert called is False
