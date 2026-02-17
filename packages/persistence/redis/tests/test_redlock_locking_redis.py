"""Tests for Redis-based distributed locking."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cqrs_ddd_core.primitives import LockAcquisitionError, ResourceIdentifier
from cqrs_ddd_redis import RedlockLockStrategy
from cqrs_ddd_redis.exceptions import RedisLockError


@pytest.fixture
def redis_urls() -> list[str]:
    return [
        "redis://localhost:6379",
        "redis://localhost:6380",
        "redis://localhost:6381",
    ]


@pytest.fixture
def mock_lock() -> MagicMock:
    lock = MagicMock()
    lock.valid = True
    lock.value = "test-redlock-token"
    return lock


@pytest.fixture
async def strategy(redis_urls: list[str], mock_lock: MagicMock) -> RedlockLockStrategy:
    with patch("cqrs_ddd_redis.redlock_locking.AsyncRedlock") as mock_redlock_cls:
        # Mock AsyncRedlock
        mock_redlock = mock_redlock_cls.return_value
        # Mock the internal client instances that we zip in __init__
        mock_instances = [MagicMock() for _ in redis_urls]
        for inst in mock_instances:
            inst.eval = AsyncMock(return_value=1)
            inst.ping = AsyncMock()
            inst.aclose = AsyncMock()

        mock_redlock.client.instances = mock_instances
        mock_redlock.acquire = AsyncMock(return_value=mock_lock)
        mock_redlock.unlock = AsyncMock()

        strategy = RedlockLockStrategy(redis_urls)
        yield strategy
        await strategy.close()


@pytest.mark.asyncio
class TestRedlockLockStrategy:
    """Test RedlockLockStrategy implementation with mocks."""

    async def test_basic_acquire_release(
        self, strategy: RedlockLockStrategy, mock_lock: MagicMock
    ) -> None:
        """Should acquire and release locks using composite tokens."""
        resource = ResourceIdentifier("Account", "123")

        # Acquire
        token = await strategy.acquire(resource, timeout=1.0, ttl=30.0)
        assert token == f"lock:Account:123:write:{mock_lock.value}"

        # Verify Redlock call
        strategy._redlock.acquire.assert_called_once()

        # Release
        await strategy.release(resource, token)
        # redlock-ng unlock(key, token)
        key = strategy._make_key(resource)
        strategy._redlock.unlock.assert_called_with(key, mock_lock.value)

    async def test_reentrancy_increments_ref_count(
        self, strategy: RedlockLockStrategy, mock_lock: MagicMock
    ) -> None:
        """Same session should re-acquire without calling Redis (after first call)."""
        resource = ResourceIdentifier("Account", "123")
        session_id = "session-1"

        # First acquire (calls Redis)
        token1 = await strategy.acquire(resource, session_id=session_id)
        assert strategy._redlock.acquire.call_count == 1

        # Second acquire (reentrant - refreshes TTL, increments ref_count)
        # We need to mock 'extend' successfully
        with patch.object(
            strategy, "extend", AsyncMock(return_value=True)
        ) as mock_extend:
            token2 = await strategy.acquire(resource, session_id=session_id)
            assert token1 == token2
            assert strategy._redlock.acquire.call_count == 1  # Still 1
            mock_extend.assert_called_once()

            # Check internal ref_count
            key = strategy._make_key(resource)
            assert strategy._lock_metadata[key][4] == 2

        # Release 1
        await strategy.release(resource, token1)
        assert strategy._redlock.unlock.call_count == 0  # Not released yet

        # Release 2
        await strategy.release(resource, token2)
        assert strategy._redlock.unlock.call_count == 1  # Fully released

    async def test_reentrancy_fallback_on_extend_failure(
        self, strategy: RedlockLockStrategy, mock_lock: MagicMock
    ) -> None:
        """If reentrant extension fails, should fall back to fresh acquisition."""
        resource = ResourceIdentifier("Account", "123")
        session_id = "session-1"

        # First acquire
        await strategy.acquire(resource, session_id=session_id)

        # Mock extend failure (lock disappeared in Redis)
        with patch.object(strategy, "extend", AsyncMock(return_value=False)):
            await strategy.acquire(resource, session_id=session_id)

            # Should have called acquire() a second time
            assert strategy._redlock.acquire.call_count == 2

    async def test_acquire_timeout_throws_acquisition_error(
        self, strategy: RedlockLockStrategy
    ) -> None:
        """Should throw LockAcquisitionError on timeout."""
        resource = ResourceIdentifier("Account", "123")

        # Mock asyncio.wait_for timeout safely closing the mock coroutine
        async def mock_wait_for(coro, timeout):
            coro.close()
            raise asyncio.TimeoutError

        with patch("asyncio.wait_for", side_effect=mock_wait_for):
            with pytest.raises(LockAcquisitionError) as exc:
                await strategy.acquire(resource, timeout=0.1)
            assert "timed out" in str(exc.value)

    async def test_quorum_failure_throws_acquisition_error(
        self, strategy: RedlockLockStrategy, mock_lock: MagicMock
    ) -> None:
        """Should throw LockAcquisitionError if lock is invalid (failed quorum)."""
        resource = ResourceIdentifier("Account", "123")
        mock_lock.valid = False

        with pytest.raises(LockAcquisitionError) as exc:
            await strategy.acquire(resource)
        assert "Quorum not reached" in str(exc.value)

    async def test_technical_failure_throws_redis_lock_error(
        self, strategy: RedlockLockStrategy
    ) -> None:
        """Should throw RedisLockError on technical error."""
        resource = ResourceIdentifier("Account", "123")
        strategy._redlock.acquire.side_effect = Exception("Redis crash")

        with pytest.raises(RedisLockError) as exc:
            await strategy.acquire(resource)
        assert "Technical failure" in str(exc.value)

    async def test_extend_lua_logic(self, strategy: RedlockLockStrategy) -> None:
        """Verify extend uses Lua script and quorum."""
        resource = ResourceIdentifier("Account", "123")
        token = "lock:Account:123:write:token123"  # noqa: S105

        success = await strategy.extend(resource, token, ttl=60.0)
        assert success is True

        # Verify lua script was called on clients
        for client in strategy._redis_clients.values():
            client.eval.assert_called_once()
            args = client.eval.call_args[0]
            assert "KEYS[1]" in args[0]  # Lua script
            assert args[3] == "token123"  # Redlock ID check (ARGV[1])

    async def test_health_check_quorum(self, strategy: RedlockLockStrategy) -> None:
        """Health check should require quorum (2/3 in our test case)."""
        # 3 nodes configured. Quorum = 3//2 = 1. Need > 1 (i.e., 2)

        # 1. All nodes UP
        assert await strategy.health_check() is True

        # 2. Only 1 node UP (under quorum)
        it = iter([AsyncMock(), Exception("Down"), Exception("Down")])
        for client in strategy._redis_clients.values():
            client.ping.side_effect = next(it)

        assert await strategy.health_check() is False

    async def test_metadata_pruning(self, strategy: RedlockLockStrategy) -> None:
        """Stale metadata should be removed."""
        resource = ResourceIdentifier("Account", "123")
        key = strategy._make_key(resource)

        # Manually inject expired metadata (ttl=1s, acquired 10s ago)
        long_ago = datetime.now(timezone.utc) - timedelta(seconds=10)
        strategy._lock_metadata[key] = [long_ago, 1.0, "session-1", "token-1", 1]

        # Call acquire (pruning happens at start)
        await strategy.acquire(resource)
        # Verify it was pruned and replaced with new acquisition
        assert strategy._lock_metadata[key][0] > long_ago

    async def test_get_active_locks_filters_expired(
        self, strategy: RedlockLockStrategy
    ) -> None:
        """Active locks list should not include expired metadata."""
        r1 = ResourceIdentifier("Account", "123")
        r2 = ResourceIdentifier("Account", "456")

        # r1 is active
        await strategy.acquire(r1)

        # r2 is expired in metadata
        key2 = strategy._make_key(r2)
        long_ago = datetime.now(timezone.utc) - timedelta(seconds=10)
        strategy._lock_metadata[key2] = [long_ago, 1.0, None, "token-2", 1]

        locks = await strategy.get_active_locks()
        assert len(locks) == 1
        assert locks[0].resource_id == "123"
        assert key2 not in strategy._lock_metadata

    async def test_reentrancy_different_session_treats_as_new_acquisition(
        self, strategy: RedlockLockStrategy, mock_lock: MagicMock
    ) -> None:
        """Different session ID should trigger new acquisition even if lock held locally."""
        resource = ResourceIdentifier("Account", "123")

        # Acquire with Session A
        await strategy.acquire(resource, session_id="session-A")
        assert strategy._redlock.acquire.call_count == 1

        # Acquire with Session B (should NOT use local metadata, but try Redis)
        # Mock Redis returning a NEW lock object (simulating wait/success)
        new_lock = MagicMock()
        new_lock.valid = True
        new_lock.value = "token-B"
        strategy._redlock.acquire.return_value = new_lock

        token_b = await strategy.acquire(resource, session_id="session-B")

        assert strategy._redlock.acquire.call_count == 2
        assert "token-B" in token_b

    async def test_reentrancy_local_expiration_triggers_fresh_acquisition(
        self, strategy: RedlockLockStrategy
    ) -> None:
        """If local metadata says expired, ignore reentrancy and acquire fresh."""
        resource = ResourceIdentifier("Account", "123")
        session_id = "session-A"

        # Acquire
        await strategy.acquire(resource, session_id=session_id)

        # Manually expire local metadata
        key = strategy._make_key(resource)
        long_ago = datetime.now(timezone.utc) - timedelta(seconds=40)
        strategy._lock_metadata[key][0] = long_ago  # expired acquired_at

        # Re-acquire (should be fresh)
        await strategy.acquire(resource, session_id=session_id)

        # Should have called acquire twice (initial + fresh)
        # Note: extend() is NOT called because it's expired locally
        assert strategy._redlock.acquire.call_count == 2

    async def test_release_handles_invalid_token_gracefully(
        self, strategy: RedlockLockStrategy
    ) -> None:
        """Should log error and return without crashing."""
        resource = ResourceIdentifier("Account", "123")

        # Malformed token
        await strategy.release(resource, "invalid-token-format")

        # Should not call unlock
        strategy._redlock.unlock.assert_not_called()

    async def test_release_unknown_lock_attempts_redis_unlock(
        self, strategy: RedlockLockStrategy
    ) -> None:
        """If lock unknown locally (e.g. after restart), should still try Redis unlock."""
        resource = ResourceIdentifier("Account", "123")
        token = "lock:Account:123:write:random-id"  # noqa: S105

        # No local metadata

        await strategy.release(resource, token)

        # Should verify token and call unlock
        key = strategy._make_key(resource)
        strategy._redlock.unlock.assert_called_with(key, "random-id")

    async def test_release_cleans_metadata_even_on_redis_failure(
        self, strategy: RedlockLockStrategy
    ) -> None:
        """Local metadata should be removed even if Redis unlock fails."""
        resource = ResourceIdentifier("Account", "123")

        # Acquire
        token = await strategy.acquire(resource)
        key = strategy._make_key(resource)

        # Mock unlock failure
        strategy._redlock.unlock.side_effect = Exception("Network down")

        await strategy.release(resource, token)

        # Metadata should be gone
        assert key not in strategy._lock_metadata

    async def test_extend_handles_invalid_token(
        self, strategy: RedlockLockStrategy
    ) -> None:
        """Should return False if token is malformed."""
        resource = ResourceIdentifier("Account", "123")
        success = await strategy.extend(resource, "bad-token", 10.0)
        assert success is False

    async def test_extend_partial_node_failures_with_quorum(
        self, strategy: RedlockLockStrategy
    ) -> None:
        """Should return True if at least N/2 + 1 nodes succeed."""
        resource = ResourceIdentifier("Account", "123")
        token = "lock:Account:123:write:token"  # noqa: S105

        # 3 clients. 2 succeed, 1 fails.
        # We need to set side_effect on the individual client mocks.
        # The strategy._redis_clients values are what we need to touch.
        clients = list(strategy._redis_clients.values())

        # Client 1: Success (1)
        clients[0].eval.return_value = 1
        # Client 2: Success (1)
        clients[1].eval.return_value = 1
        # Client 3: Failure (Exception)
        clients[2].eval.side_effect = Exception("Connection lost")

        success = await strategy.extend(resource, token, 10.0)

        assert success is True
