"""Tests for FifoRedisLockStrategy (Fair Locking)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cqrs_ddd_core.primitives import LockAcquisitionError, ResourceIdentifier
from cqrs_ddd_redis import FifoRedisLockStrategy
from cqrs_ddd_redis.exceptions import RedisLockError


@pytest.fixture
def mock_redis() -> MagicMock:
    redis = MagicMock()
    redis.eval = AsyncMock(return_value=1)
    redis.zrem = AsyncMock()
    redis.ping = AsyncMock()
    redis.aclose = AsyncMock()
    return redis


@pytest.fixture
def strategy(mock_redis: MagicMock) -> FifoRedisLockStrategy:
    return FifoRedisLockStrategy(mock_redis)


@pytest.mark.asyncio
class TestFifoRedisLockStrategy:
    """Test FifoRedisLockStrategy with mocks."""

    async def test_basic_acquire_release(
        self, strategy: FifoRedisLockStrategy, mock_redis: MagicMock
    ) -> None:
        """Should acquire and release locks."""
        resource = ResourceIdentifier("Account", "123")

        # 1. Acquire
        token = await strategy.acquire(resource, timeout=1.0, ttl=30.0)
        assert token is not None

        # Verify lua script call
        mock_redis.eval.assert_called_once()
        args = mock_redis.eval.call_args[0]
        assert "ZADD" in args[0]  # Fair acquisition script
        assert args[4] == token  # token (ARGV[1])

        # 2. Release
        await strategy.release(resource, token)
        # Lua script: KEYS[1]=lock, KEYS[2]=queue, ARGV[1]=token
        assert mock_redis.eval.call_count == 2
        release_args = mock_redis.eval.call_args[0]
        assert "DEL" in release_args[0]
        assert release_args[4] == token

    async def test_reentrancy_increments_ref_count(
        self, strategy: FifoRedisLockStrategy, mock_redis: MagicMock
    ) -> None:
        """Same session should re-acquire without fresh fair acquisition (uses extend)."""
        resource = ResourceIdentifier("Account", "123")
        session_id = "sess-123"

        # First acquisition
        token = await strategy.acquire(resource, session_id=session_id)
        assert mock_redis.eval.call_count == 1

        # Second acquisition (reentrant)
        # Mock extend success
        with patch.object(
            strategy, "extend", AsyncMock(return_value=True)
        ) as mock_extend:
            token2 = await strategy.acquire(resource, session_id=session_id)
            assert token == token2
            assert mock_redis.eval.call_count == 1  # Still 1 call to fair script
            mock_extend.assert_called_once()

            # Internal check
            lock_key = strategy._lock_key(resource)
            assert strategy._lock_metadata[lock_key][4] == 2

        # Release 1
        await strategy.release(resource, token)
        assert mock_redis.eval.call_count == 1  # Not called yet

        # Release 2
        await strategy.release(resource, token)
        assert mock_redis.eval.call_count == 2  # Fully released

    async def test_acquire_timeout_throws_error(
        self, strategy: FifoRedisLockStrategy, mock_redis: MagicMock
    ) -> None:
        """Should throw LockAcquisitionError and cleanup queue on timeout."""
        resource = ResourceIdentifier("Account", "123")
        # Mock result as 0 (not acquired)
        mock_redis.eval.return_value = 0

        # Short timeout for test
        with pytest.raises(LockAcquisitionError) as exc:
            await strategy.acquire(resource, timeout=0.2)

        assert "timed out" in str(exc.value)
        # Should have called zrem to cleanup queue
        mock_redis.zrem.assert_called_once()

    async def test_technical_failure_throws_error(
        self, strategy: FifoRedisLockStrategy, mock_redis: MagicMock
    ) -> None:
        """Should wrap technical exceptions."""
        resource = ResourceIdentifier("Account", "123")
        mock_redis.eval.side_effect = Exception("Redis crash")

        with pytest.raises(RedisLockError):
            await strategy.acquire(resource)

    async def test_extend_updates_metadata(
        self, strategy: FifoRedisLockStrategy, mock_redis: MagicMock
    ) -> None:
        """Should update local metadata on successful extension."""
        resource = ResourceIdentifier("Account", "123")
        token = await strategy.acquire(resource)

        # Mock successful PEXPIRE
        mock_redis.eval.return_value = 1

        success = await strategy.extend(resource, token, ttl=60.0)
        assert success is True

        lock_key = strategy._lock_key(resource)
        assert strategy._lock_metadata[lock_key][1] == 60.0

    async def test_health_check(
        self, strategy: FifoRedisLockStrategy, mock_redis: MagicMock
    ) -> None:
        """Simple ping check."""
        assert await strategy.health_check() is True
        mock_redis.ping.assert_called_once()

        mock_redis.ping.side_effect = Exception("Down")
        assert await strategy.health_check() is False

    async def test_get_active_locks(self, strategy: FifoRedisLockStrategy) -> None:
        """Should return list of active locks from metadata."""
        r1 = ResourceIdentifier("Account", "1")
        r2 = ResourceIdentifier("Account", "2")

        await strategy.acquire(r1)
        await strategy.acquire(r2)

        locks = await strategy.get_active_locks()
        assert len(locks) == 2
        ids = {lock.resource_id for lock in locks}
        assert "1" in ids
        assert "2" in ids
