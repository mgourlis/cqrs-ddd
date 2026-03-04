from __future__ import annotations

import asyncio

import pytest

from cqrs_ddd_core.correlation import (
    CorrelationIdPropagator,
    generate_correlation_id,
    get_causation_id,
    get_context_vars,
    get_correlation_id,
    set_context_vars,
    set_correlation_id,
    with_correlation_context,
)


@pytest.mark.asyncio
async def test_correlation_propagator_sets_context_from_message() -> None:
    class Msg:
        correlation_id = "cid-123"
        event_id = "evt-456"

    set_correlation_id(None)
    prop = CorrelationIdPropagator()

    async def _next(_message: object) -> None:
        return None

    await prop(Msg(), _next)
    assert get_correlation_id() == "cid-123"
    assert get_causation_id() == "evt-456"


@pytest.mark.asyncio
async def test_correlation_propagator_injects_into_pydantic_like_message() -> None:
    class Msg:
        def __init__(self, correlation_id: str | None = None) -> None:
            self.correlation_id = correlation_id

        def model_copy(self, update: dict[str, str]) -> Msg:
            return Msg(correlation_id=update.get("correlation_id"))

    set_correlation_id("cid-abc")
    prop = CorrelationIdPropagator()
    seen: Msg | None = None

    async def _next(message: Msg) -> None:
        nonlocal seen
        seen = message

    await prop(Msg(), _next)
    assert seen is not None
    assert seen.correlation_id == "cid-abc"


def test_context_helpers_roundtrip() -> None:
    set_context_vars(correlation_id="c1", causation_id="k1")
    vals = get_context_vars()
    assert vals["correlation_id"] == "c1"
    assert vals["causation_id"] == "k1"


def test_generate_correlation_id_format() -> None:
    first = generate_correlation_id()
    second = generate_correlation_id()
    assert first != second
    assert len(first) == 36
    assert len(second) == 36


@pytest.mark.asyncio
async def test_with_correlation_context_preserves_task_context() -> None:
    set_correlation_id("parent-correlation")

    @with_correlation_context
    async def child() -> str | None:
        await asyncio.sleep(0)
        return get_correlation_id()

    result = await asyncio.create_task(child())
    assert result == "parent-correlation"
