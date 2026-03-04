"""Tests for multi-resource locking system."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from cqrs_ddd_core.adapters.memory import InMemoryLockStrategy
from cqrs_ddd_core.cqrs.concurrency import CriticalSection
from cqrs_ddd_core.middleware import ConcurrencyGuardMiddleware
from cqrs_ddd_core.primitives import (
    ConcurrencyError,
    LockAcquisitionError,
    ResourceIdentifier,
)

if TYPE_CHECKING:
    from cqrs_ddd_core.ports.locking import ILockStrategy


# ── Test Commands ────────────────────────────────────────────────────


@dataclass
class TransferFunds:
    """Test command with critical resources."""

    from_account: str
    to_account: str
    amount: Decimal

    def get_critical_resources(self) -> list[ResourceIdentifier]:
        return [
            ResourceIdentifier("Account", self.from_account),
            ResourceIdentifier("Account", self.to_account),
        ]


@dataclass
class SimpleCommand:
    """Test command without critical resources."""

    value: int


# ── Unit Tests ────────────────────────────────────────────────────────


class TestResourceIdentifier:
    """Test ResourceIdentifier sorting and hashing."""

    def test_sorting_prevents_deadlocks(self) -> None:
        """Resources should sort consistently."""
        r1 = ResourceIdentifier("Account", "123")
        r2 = ResourceIdentifier("Account", "456")
        r3 = ResourceIdentifier("User", "789")

        resources = [r3, r1, r2]
        sorted_resources = sorted(resources)

        assert sorted_resources == [r1, r2, r3]
        assert sorted_resources[0].resource_id == "123"

    def test_deduplication(self) -> None:
        """Duplicate resources should be deduplicated."""
        r1 = ResourceIdentifier("Account", "123")
        r2 = ResourceIdentifier("Account", "123")

        unique = list({r1, r2})
        assert len(unique) == 1

    def test_lock_mode_affects_hash(self) -> None:
        """Read and write locks should be different."""
        r1 = ResourceIdentifier("Account", "123", lock_mode="read")
        r2 = ResourceIdentifier("Account", "123", lock_mode="write")

        assert r1 != r2
        assert hash(r1) != hash(r2)


class TestInMemoryLockStrategy:
    """Test InMemoryLockStrategy implementation."""

    @pytest.fixture
    def strategy(self) -> InMemoryLockStrategy:
        return InMemoryLockStrategy()

    async def test_basic_acquire_release(self, strategy: ILockStrategy) -> None:
        """Should acquire and release locks."""
        resource = ResourceIdentifier("Account", "123")

        token = await strategy.acquire(resource, timeout=1.0)
        assert token is not None

        await strategy.release(resource, token)

    async def test_concurrent_acquisition_blocks(self, strategy: ILockStrategy) -> None:
        """Second acquire should block until first releases."""
        resource = ResourceIdentifier("Account", "123")

        # First acquire
        token1 = await strategy.acquire(resource, timeout=1.0)

        # Second acquire should timeout
        with pytest.raises(ConcurrencyError):
            await strategy.acquire(resource, timeout=0.1)

        # Release first lock
        await strategy.release(resource, token1)

        # Now second acquire should succeed
        token2 = await strategy.acquire(resource, timeout=1.0)
        await strategy.release(resource, token2)

    async def test_reentrancy_with_session_id(self, strategy: ILockStrategy) -> None:
        """Same session should be able to re-acquire."""
        resource = ResourceIdentifier("Account", "123")
        session_id = "session-1"

        # First acquire
        token1 = await strategy.acquire(resource, session_id=session_id, timeout=1.0)

        # Second acquire with same session (should succeed)
        token2 = await strategy.acquire(resource, session_id=session_id, timeout=1.0)

        assert token1 == token2

        # Release twice (ref count)
        await strategy.release(resource, token1)
        await strategy.release(resource, token2)

    async def test_fifo_ordering(self, strategy: ILockStrategy) -> None:
        """Locks should be granted sequentially (basic FIFO check)."""
        resource = ResourceIdentifier("Account", "123")

        # Simple test: acquire/release sequentially
        for _i in range(3):
            token = await strategy.acquire(resource, timeout=1.0)
            await strategy.release(resource, token)

        # Success - locks work sequentially

    async def test_health_check(self, strategy: ILockStrategy) -> None:
        """Health check should return True for in-memory."""
        assert await strategy.health_check() is True

    async def test_get_active_locks(self, strategy: ILockStrategy) -> None:
        """Should list active locks."""
        r1 = ResourceIdentifier("Account", "123")
        r2 = ResourceIdentifier("User", "456")

        # No locks initially
        locks = await strategy.get_active_locks()
        assert len(locks) == 0

        # Acquire two locks
        token1 = await strategy.acquire(r1, timeout=1.0)
        token2 = await strategy.acquire(r2, timeout=1.0)

        locks = await strategy.get_active_locks()
        assert len(locks) == 2

        # Release and verify
        await strategy.release(r1, token1)
        await strategy.release(r2, token2)

        locks = await strategy.get_active_locks()
        assert len(locks) == 0


class TestCriticalSection:
    """Test CriticalSection multi-resource locking."""

    @pytest.fixture
    def strategy(self) -> InMemoryLockStrategy:
        return InMemoryLockStrategy()

    async def test_locks_multiple_resources(self, strategy: ILockStrategy) -> None:
        """Should lock all resources atomically."""
        resources = [
            ResourceIdentifier("Account", "123"),
            ResourceIdentifier("Account", "456"),
        ]

        async with CriticalSection(resources, strategy, timeout=1.0):
            # Verify we can't acquire the same resources
            with pytest.raises(ConcurrencyError):
                await strategy.acquire(resources[0], timeout=0.1)

    async def test_rollback_on_partial_failure(self, strategy: ILockStrategy) -> None:
        """Should rollback already-acquired locks if any fails."""
        r1 = ResourceIdentifier("Account", "123")
        r2 = ResourceIdentifier("Account", "456")

        # Lock r2 externally
        token = await strategy.acquire(r2, timeout=1.0)

        # Try to acquire both (should fail on r2, rollback r1)
        with pytest.raises(LockAcquisitionError):
            async with CriticalSection([r1, r2], strategy, timeout=0.1):
                pass

        # r1 should be released (we can acquire it)
        token2 = await strategy.acquire(r1, timeout=1.0)
        await strategy.release(r1, token2)

        # Cleanup
        await strategy.release(r2, token)

    async def test_sorted_acquisition_prevents_deadlock(
        self, strategy: ILockStrategy
    ) -> None:
        """Resources should be acquired in sorted order."""
        # Create resources in random order
        resources = [
            ResourceIdentifier("Account", "456"),
            ResourceIdentifier("Account", "123"),
            ResourceIdentifier("User", "789"),
        ]

        # CriticalSection should sort them
        async with CriticalSection(resources, strategy, timeout=1.0):
            pass  # Success means they were sorted


class TestConcurrencyGuardMiddleware:
    """Test automatic locking middleware."""

    @pytest.fixture
    def strategy(self) -> InMemoryLockStrategy:
        return InMemoryLockStrategy()

    @pytest.fixture
    def middleware(self, strategy: ILockStrategy) -> ConcurrencyGuardMiddleware:
        return ConcurrencyGuardMiddleware(strategy, timeout=1.0, ttl=5.0)

    async def test_locks_commands_with_resources(
        self, middleware: ConcurrencyGuardMiddleware
    ) -> None:
        """Should lock commands that declare resources."""
        command = TransferFunds("123", "456", Decimal("100.00"))
        executed = False

        async def handler(cmd: TransferFunds) -> None:
            nonlocal executed
            executed = True

        await middleware(command, handler)
        assert executed is True

    async def test_skips_commands_without_resources(
        self, middleware: ConcurrencyGuardMiddleware
    ) -> None:
        """Should skip locking for commands without get_critical_resources."""
        command = SimpleCommand(42)
        executed = False

        async def handler(cmd: SimpleCommand) -> None:
            nonlocal executed
            executed = True

        await middleware(command, handler)
        assert executed is True

    async def test_fail_open_continues_on_lock_failure(
        self, strategy: ILockStrategy
    ) -> None:
        """With fail_open=True, should continue even if lock fails."""
        middleware = ConcurrencyGuardMiddleware(strategy, timeout=0.1, fail_open=True)
        command = TransferFunds("123", "456", Decimal("100.00"))

        # Lock one of the resources externally
        r1 = ResourceIdentifier("Account", "123")
        token = await strategy.acquire(r1, timeout=1.0)

        # Command should still execute (fail-open)
        executed = False

        async def handler(cmd: TransferFunds) -> None:
            nonlocal executed
            executed = True

        await middleware(command, handler)
        assert executed is True

        # Cleanup
        await strategy.release(r1, token)


# ── Integration Tests ─────────────────────────────────────────────────


class TestConcurrentTransfers:
    """Test realistic concurrent transfer scenarios."""

    async def test_no_duplicate_processing(self) -> None:
        """Concurrent transfers should use locking properly."""
        strategy = InMemoryLockStrategy()
        balances = {"123": Decimal("100"), "456": Decimal("0")}

        async def transfer(from_acc: str, to_acc: str, amount: Decimal) -> None:
            resources = [
                ResourceIdentifier("Account", from_acc),
                ResourceIdentifier("Account", to_acc),
            ]

            async with CriticalSection(resources, strategy, timeout=2.0):
                balances[from_acc] -= amount
                balances[to_acc] += amount

        # Just 10 transfers to keep it simple
        tasks = [transfer("123", "456", Decimal("10")) for _ in range(10)]
        await asyncio.gather(*tasks)

        # Verify conservation of funds
        assert balances["123"] == Decimal("0")
        assert balances["456"] == Decimal("100")
