"""Tests for CorrelationIdPropagator."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from cqrs_ddd_core.correlation import CorrelationIdPropagator, set_correlation_id
from cqrs_ddd_observability.context import ObservabilityContext


@pytest.mark.asyncio
async def test_propagator_sets_context_from_message() -> None:
    class Msg:
        correlation_id = "cid-123"

    set_correlation_id(None)
    prop = CorrelationIdPropagator()
    next_handler = AsyncMock(return_value=None)
    await prop(Msg(), next_handler)
    assert ObservabilityContext.get_correlation_id() == "cid-123"


@pytest.mark.asyncio
async def test_propagator_does_not_raise() -> None:
    prop = CorrelationIdPropagator()
    next_handler = AsyncMock(side_effect=ValueError("fail"))
    with pytest.raises(ValueError):
        await prop("message", next_handler)
