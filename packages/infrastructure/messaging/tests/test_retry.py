"""Tests for RetryPolicy."""

from __future__ import annotations

import pytest

from cqrs_ddd_messaging.retry import RetryPolicy


def test_should_retry() -> None:
    policy = RetryPolicy(max_attempts=3)
    assert policy.should_retry(1) is True
    assert policy.should_retry(2) is True
    assert policy.should_retry(3) is False
    assert policy.should_retry(0) is False


def test_delay_for_attempt_exponential() -> None:
    policy = RetryPolicy(base_delay=1.0, max_delay=100.0, jitter=False)
    assert policy.delay_for_attempt(1) == 1.0
    assert policy.delay_for_attempt(2) == 2.0
    assert policy.delay_for_attempt(3) == 4.0
    assert policy.delay_for_attempt(10) == 100.0  # capped


def test_delay_with_jitter_in_range() -> None:
    policy = RetryPolicy(base_delay=2.0, max_delay=10.0, jitter=True)
    for _ in range(20):
        d = policy.delay_for_attempt(2)
        # attempt 2 -> base_delay * 2^1 = 4.0; jitter 0.5..1.5 -> 2.0..6.0
        assert 2.0 <= d <= 6.0


def test_invalid_max_attempts_raises() -> None:
    with pytest.raises(ValueError, match=r"max_attempts"):
        RetryPolicy(max_attempts=0)


def test_delay_for_attempt_zero_returns_zero() -> None:
    """Attempt < 1 returns 0.0 (no delay)."""
    policy = RetryPolicy(base_delay=1.0, jitter=False)
    assert policy.delay_for_attempt(0) == 0.0


def test_invalid_delays_raise() -> None:
    with pytest.raises(ValueError, match="base_delay and max_delay"):
        RetryPolicy(base_delay=-0.1, max_delay=1.0)
    with pytest.raises(ValueError, match="base_delay and max_delay"):
        RetryPolicy(base_delay=1.0, max_delay=-1.0)
    with pytest.raises(ValueError, match="base_delay must be <= max_delay"):
        RetryPolicy(base_delay=10.0, max_delay=1.0)


@pytest.mark.asyncio
async def test_wait_before_retry() -> None:
    policy = RetryPolicy(base_delay=0.01, jitter=False)
    import time

    t0 = time.monotonic()
    await policy.wait_before_retry(2)
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.01
