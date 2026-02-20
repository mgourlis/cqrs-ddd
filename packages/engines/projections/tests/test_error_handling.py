"""Tests for ProjectionErrorPolicy."""

from __future__ import annotations

import pytest

from cqrs_ddd_core.domain.events import DomainEvent
from cqrs_ddd_projections.error_handling import ProjectionErrorPolicy
from cqrs_ddd_projections.exceptions import ProjectionHandlerError


class FakeEvent(DomainEvent):
    pass


@pytest.mark.asyncio
async def test_retry_then_dead_letter_retries_before_callback() -> None:
    calls: list[tuple[DomainEvent, Exception]] = []

    async def dead_letter(event: DomainEvent, error: Exception) -> None:
        calls.append((event, error))

    policy = ProjectionErrorPolicy(
        policy=ProjectionErrorPolicy.RETRY_THEN_DEAD_LETTER,
        max_retries=2,
        dead_letter_callback=dead_letter,
    )
    event = FakeEvent()
    error = RuntimeError("boom")

    with pytest.raises(ProjectionHandlerError):
        await policy.handle_failure(event, error, attempt=0)
    with pytest.raises(ProjectionHandlerError):
        await policy.handle_failure(event, error, attempt=1)

    assert calls == []

    with pytest.raises(ProjectionHandlerError):
        await policy.handle_failure(event, error, attempt=2)

    assert len(calls) == 1
    assert calls[0][0] == event
    assert str(calls[0][1]) == "boom"


@pytest.mark.asyncio
async def test_retry_then_dead_letter_without_callback_still_raises() -> None:
    policy = ProjectionErrorPolicy(
        policy=ProjectionErrorPolicy.RETRY_THEN_DEAD_LETTER,
        max_retries=1,
        dead_letter_callback=None,
    )

    with pytest.raises(ProjectionHandlerError):
        await policy.handle_failure(FakeEvent(), RuntimeError("boom"), attempt=1)


@pytest.mark.asyncio
async def test_register_custom_policy_without_modifying_core() -> None:
    seen: list[str] = []

    async def custom(
        policy: ProjectionErrorPolicy,
        event: DomainEvent,
        error: Exception,
        attempt: int,
    ) -> None:
        del policy, event, error, attempt
        seen.append("handled")

    policy = ProjectionErrorPolicy(policy="custom")
    policy.register_policy("custom", custom)

    await policy.handle_failure(FakeEvent(), RuntimeError("boom"), attempt=0)

    assert seen == ["handled"]


@pytest.mark.asyncio
async def test_unknown_policy_raises_handler_error() -> None:
    policy = ProjectionErrorPolicy(policy="does_not_exist")

    with pytest.raises(ProjectionHandlerError, match="Unknown projection error policy"):
        await policy.handle_failure(FakeEvent(), RuntimeError("boom"), attempt=0)
