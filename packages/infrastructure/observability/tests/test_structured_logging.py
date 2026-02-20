"""Tests for StructuredLoggingMiddleware."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from cqrs_ddd_observability.structured_logging import StructuredLoggingMiddleware


@pytest.mark.asyncio
async def test_logs_success() -> None:
    log = MagicMock()
    mw = StructuredLoggingMiddleware(logger=log)
    next_handler = AsyncMock(return_value="ok")
    result = await mw("message", next_handler)
    assert result == "ok"
    assert log.info.called
    args = log.info.call_args[0][0]
    assert "message_type" in args
    assert "outcome" in args
    assert "duration_ms" in args


@pytest.mark.asyncio
async def test_failure_does_not_swallow() -> None:
    mw = StructuredLoggingMiddleware()
    next_handler = AsyncMock(side_effect=RuntimeError("x"))
    with pytest.raises(RuntimeError):
        await mw("msg", next_handler)
