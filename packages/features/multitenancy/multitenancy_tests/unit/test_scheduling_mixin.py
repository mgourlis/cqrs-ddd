"""Unit tests for MultitenantCommandSchedulerMixin."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

from cqrs_ddd_core.cqrs.command import Command
from cqrs_ddd_multitenancy.context import reset_tenant, set_tenant
from cqrs_ddd_multitenancy.exceptions import TenantContextMissingError
from cqrs_ddd_multitenancy.mixins.scheduling import MultitenantCommandSchedulerMixin

# ── Test Doubles ───────────────────────────────────────────────────────


class TestCommand(Command[str]):
    """Test command for scheduling."""

    value: str


class MockCommandScheduler:
    """Mock base command scheduler for testing."""

    def __init__(self) -> None:
        self.scheduled_commands: dict[str, tuple[Command[Any], datetime]] = {}
        self._next_id = 1

    async def schedule(
        self,
        command: Command[Any],
        execute_at: datetime,
        description: str | None = None,
    ) -> str:
        schedule_id = f"schedule-{self._next_id}"
        self._next_id += 1
        self.scheduled_commands[schedule_id] = (command, execute_at)
        return schedule_id

    async def get_due_commands(
        self, *, specification: Any | None = None
    ) -> list[tuple[str, Command[Any]]]:
        now = datetime.now(timezone.utc)
        result = [
            (schedule_id, command)
            for schedule_id, (command, execute_at) in self.scheduled_commands.items()
            if execute_at <= now
        ]
        if specification is not None:
            result = [
                (sid, cmd) for sid, cmd in result if specification.is_satisfied_by(cmd)
            ]
        return result

    async def cancel(self, schedule_id: str) -> bool:
        if schedule_id in self.scheduled_commands:
            del self.scheduled_commands[schedule_id]
            return True
        return False

    async def delete_executed(self, schedule_id: str) -> None:
        self.scheduled_commands.pop(schedule_id, None)


class TestMultitenantCommandScheduler(
    MultitenantCommandSchedulerMixin, MockCommandScheduler
):
    """Test implementation combining mixin with mock base."""


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def scheduler() -> TestMultitenantCommandScheduler:
    """Create test command scheduler."""
    return TestMultitenantCommandScheduler()


@pytest.fixture
def tenant_a() -> str:
    """Tenant A ID."""
    return "tenant-a"


@pytest.fixture
def tenant_b() -> str:
    """Tenant B ID."""
    return "tenant-b"


@pytest.fixture
def future_time() -> datetime:
    """Future execution time."""
    return datetime.now(timezone.utc) + timedelta(hours=1)


@pytest.fixture
def past_time() -> datetime:
    """Past execution time (for due commands)."""
    return datetime.now(timezone.utc) - timedelta(hours=1)


# ── Test Cases ──────────────────────────────────────────────────────────


class TestMultitenantCommandSchedulerSchedule:
    """Tests for schedule() method."""

    @pytest.mark.asyncio
    async def test_schedule_injects_tenant_metadata(
        self,
        scheduler: TestMultitenantCommandScheduler,
        tenant_a: str,
        future_time: datetime,
    ) -> None:
        """Should inject tenant_id into command metadata."""
        token = set_tenant(tenant_a)
        try:
            command = TestCommand(value="test")

            schedule_id = await scheduler.schedule(command, future_time)

            assert schedule_id is not None

            # Check that command has tenant metadata
            assert hasattr(command, "_metadata")
            assert command._metadata.get("_tenant_id") == tenant_a
        finally:
            reset_tenant(token)

    @pytest.mark.asyncio
    async def test_schedule_preserves_existing_metadata(
        self,
        scheduler: TestMultitenantCommandScheduler,
        tenant_a: str,
        future_time: datetime,
    ) -> None:
        """Should preserve existing command metadata."""
        token = set_tenant(tenant_a)
        try:
            command = TestCommand(value="test")
            command._metadata = {"correlation_id": "corr-123"}

            await scheduler.schedule(command, future_time)

            assert command._metadata.get("correlation_id") == "corr-123"
            assert command._metadata.get("_tenant_id") == tenant_a
        finally:
            reset_tenant(token)

    @pytest.mark.asyncio
    async def test_schedule_requires_tenant_context(
        self, scheduler: TestMultitenantCommandScheduler, future_time: datetime
    ) -> None:
        """Should require tenant context."""
        command = TestCommand(value="test")

        with pytest.raises(TenantContextMissingError):
            await scheduler.schedule(command, future_time)

    @pytest.mark.asyncio
    async def test_schedule_stores_command(
        self,
        scheduler: TestMultitenantCommandScheduler,
        tenant_a: str,
        future_time: datetime,
    ) -> None:
        """Should store command in scheduler."""
        token = set_tenant(tenant_a)
        try:
            command = TestCommand(value="test")

            schedule_id = await scheduler.schedule(command, future_time)

            assert schedule_id in scheduler.scheduled_commands
            stored_command, stored_time = scheduler.scheduled_commands[schedule_id]
            assert stored_command == command
            assert stored_time == future_time
        finally:
            reset_tenant(token)


class TestMultitenantCommandSchedulerGetDueCommands:
    """Tests for get_due_commands() method."""

    @pytest.mark.asyncio
    async def test_get_due_commands_filters_by_tenant(
        self,
        scheduler: TestMultitenantCommandScheduler,
        tenant_a: str,
        tenant_b: str,
        past_time: datetime,
    ) -> None:
        """Should filter due commands by tenant."""
        # Schedule command for tenant A
        token_a = set_tenant(tenant_a)
        command_a = TestCommand(value="command-a")
        schedule_id_a = await scheduler.schedule(command_a, past_time)
        reset_tenant(token_a)

        # Schedule command for tenant B
        token_b = set_tenant(tenant_b)
        command_b = TestCommand(value="command-b")
        _ = await scheduler.schedule(command_b, past_time)
        reset_tenant(token_b)

        # Get due commands for tenant A
        token_a = set_tenant(tenant_a)
        try:
            due_commands = await scheduler.get_due_commands()

            # Should only return tenant A's command
            assert len(due_commands) == 1
            assert due_commands[0][0] == schedule_id_a
            assert due_commands[0][1].value == "command-a"
        finally:
            reset_tenant(token_a)

    @pytest.mark.asyncio
    async def test_get_due_commands_returns_empty_for_no_due(
        self,
        scheduler: TestMultitenantCommandScheduler,
        tenant_a: str,
        future_time: datetime,
    ) -> None:
        """Should return empty list if no commands are due."""
        token = set_tenant(tenant_a)
        try:
            command = TestCommand(value="test")
            await scheduler.schedule(command, future_time)

            due_commands = await scheduler.get_due_commands()

            assert len(due_commands) == 0
        finally:
            reset_tenant(token)

    @pytest.mark.asyncio
    async def test_get_due_commands_requires_tenant_context(
        self, scheduler: TestMultitenantCommandScheduler
    ) -> None:
        """Should require tenant context."""
        with pytest.raises(TenantContextMissingError):
            await scheduler.get_due_commands()


class TestMultitenantCommandSchedulerCancel:
    """Tests for cancel() method."""

    @pytest.mark.asyncio
    async def test_cancel_removes_scheduled_command(
        self,
        scheduler: TestMultitenantCommandScheduler,
        tenant_a: str,
        future_time: datetime,
    ) -> None:
        """Should cancel scheduled command."""
        token = set_tenant(tenant_a)
        try:
            command = TestCommand(value="test")
            schedule_id = await scheduler.schedule(command, future_time)

            result = await scheduler.cancel(schedule_id)

            assert result is True
            assert schedule_id not in scheduler.scheduled_commands
        finally:
            reset_tenant(token)

    @pytest.mark.asyncio
    async def test_cancel_returns_false_for_not_found(
        self, scheduler: TestMultitenantCommandScheduler, tenant_a: str
    ) -> None:
        """Should return False if schedule_id not found."""
        token = set_tenant(tenant_a)
        try:
            result = await scheduler.cancel("nonexistent")

            assert result is False
        finally:
            reset_tenant(token)


class TestMultitenantCommandSchedulerDeleteExecuted:
    """Tests for delete_executed() method."""

    @pytest.mark.asyncio
    async def test_delete_executed_removes_command(
        self,
        scheduler: TestMultitenantCommandScheduler,
        tenant_a: str,
        future_time: datetime,
    ) -> None:
        """Should delete executed command."""
        token = set_tenant(tenant_a)
        try:
            command = TestCommand(value="test")
            schedule_id = await scheduler.schedule(command, future_time)

            await scheduler.delete_executed(schedule_id)

            assert schedule_id not in scheduler.scheduled_commands
        finally:
            reset_tenant(token)


class TestMultitenantCommandSchedulerTenantIsolation:
    """Tests for tenant isolation."""

    @pytest.mark.asyncio
    async def test_different_tenants_schedule_independently(
        self,
        scheduler: TestMultitenantCommandScheduler,
        tenant_a: str,
        tenant_b: str,
        future_time: datetime,
    ) -> None:
        """Should allow different tenants to schedule independently."""
        # Tenant A schedules command
        token_a = set_tenant(tenant_a)
        command_a = TestCommand(value="command-a")
        schedule_id_a = await scheduler.schedule(command_a, future_time)
        reset_tenant(token_a)

        # Tenant B schedules command
        token_b = set_tenant(tenant_b)
        command_b = TestCommand(value="command-b")
        schedule_id_b = await scheduler.schedule(command_b, future_time)
        reset_tenant(token_b)

        # Verify both commands exist
        assert schedule_id_a in scheduler.scheduled_commands
        assert schedule_id_b in scheduler.scheduled_commands

        # Verify tenant metadata
        assert (
            scheduler.scheduled_commands[schedule_id_a][0]._metadata["_tenant_id"]
            == tenant_a
        )
        assert (
            scheduler.scheduled_commands[schedule_id_b][0]._metadata["_tenant_id"]
            == tenant_b
        )

    @pytest.mark.asyncio
    async def test_tenant_cannot_access_other_tenant_commands(
        self,
        scheduler: TestMultitenantCommandScheduler,
        tenant_a: str,
        tenant_b: str,
        past_time: datetime,
    ) -> None:
        """Should prevent tenant from accessing other tenant's commands."""
        # Tenant B schedules command
        token_b = set_tenant(tenant_b)
        command_b = TestCommand(value="command-b")
        await scheduler.schedule(command_b, past_time)
        reset_tenant(token_b)

        # Tenant A gets due commands
        token_a = set_tenant(tenant_a)
        try:
            due_commands = await scheduler.get_due_commands()

            # Should not include tenant B's command
            assert len(due_commands) == 0
        finally:
            reset_tenant(token_a)


class TestMultitenantCommandSchedulerSystemTenant:
    """Tests for system tenant bypass."""

    @pytest.mark.asyncio
    async def test_schedule_system_tenant_bypasses(
        self, scheduler: TestMultitenantCommandScheduler, future_time: datetime
    ) -> None:
        """System tenant should bypass tenant injection."""
        from cqrs_ddd_multitenancy.context import SYSTEM_TENANT

        token = set_tenant(SYSTEM_TENANT)
        try:
            command = TestCommand(value="system-cmd")
            schedule_id = await scheduler.schedule(command, future_time)
            assert schedule_id is not None
            assert schedule_id in scheduler.scheduled_commands
        finally:
            reset_tenant(token)

    @pytest.mark.asyncio
    async def test_get_due_commands_system_tenant_returns_all(
        self,
        scheduler: TestMultitenantCommandScheduler,
        tenant_a: str,
        tenant_b: str,
        past_time: datetime,
    ) -> None:
        """System tenant should return all due commands."""
        from cqrs_ddd_multitenancy.context import SYSTEM_TENANT

        # Schedule for tenant A
        token_a = set_tenant(tenant_a)
        await scheduler.schedule(TestCommand(value="cmd-a"), past_time)
        reset_tenant(token_a)

        # Schedule for tenant B
        token_b = set_tenant(tenant_b)
        await scheduler.schedule(TestCommand(value="cmd-b"), past_time)
        reset_tenant(token_b)

        # System tenant gets all
        token = set_tenant(SYSTEM_TENANT)
        try:
            due_commands = await scheduler.get_due_commands()
            assert len(due_commands) == 2
        finally:
            reset_tenant(token)

    @pytest.mark.asyncio
    async def test_cancel_system_tenant_bypasses(
        self, scheduler: TestMultitenantCommandScheduler, future_time: datetime
    ) -> None:
        """System tenant should cancel any command."""
        from cqrs_ddd_multitenancy.context import SYSTEM_TENANT

        token = set_tenant(SYSTEM_TENANT)
        try:
            command = TestCommand(value="test")
            schedule_id = await scheduler.schedule(command, future_time)
            result = await scheduler.cancel(schedule_id)
            assert result is True
        finally:
            reset_tenant(token)

    @pytest.mark.asyncio
    async def test_delete_executed_system_tenant_bypasses(
        self, scheduler: TestMultitenantCommandScheduler, future_time: datetime
    ) -> None:
        """System tenant should delete any executed command."""
        from cqrs_ddd_multitenancy.context import SYSTEM_TENANT

        token = set_tenant(SYSTEM_TENANT)
        try:
            command = TestCommand(value="test")
            schedule_id = await scheduler.schedule(command, future_time)
            await scheduler.delete_executed(schedule_id)
            assert schedule_id not in scheduler.scheduled_commands
        finally:
            reset_tenant(token)

    @pytest.mark.asyncio
    async def test_get_tenant_from_command_reads_dedicated_attribute(
        self,
        scheduler: TestMultitenantCommandScheduler,
        tenant_a: str,
        future_time: datetime,
    ) -> None:
        """Should read tenant_id from dedicated attribute after injection."""
        token = set_tenant(tenant_a)
        try:
            command = TestCommand(value="test")
            await scheduler.schedule(command, future_time)

            # Verify dedicated attribute was set
            tenant = scheduler._get_tenant_from_command(command)
            assert tenant == tenant_a
            assert getattr(command, "tenant_id", None) == tenant_a
        finally:
            reset_tenant(token)
