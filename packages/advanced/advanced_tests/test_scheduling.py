"""Tests for the scheduling package."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from cqrs_ddd_advanced_core.adapters.memory.scheduling import InMemoryCommandScheduler
from cqrs_ddd_advanced_core.scheduling.service import CommandSchedulerService
from cqrs_ddd_core.cqrs.command import Command


class MockCommand(Command[None]):
    pass


@pytest.mark.asyncio
async def test_scheduler_service_executes_due_commands() -> None:
    scheduler = InMemoryCommandScheduler()
    send_fn = AsyncMock()
    service = CommandSchedulerService(scheduler, send_fn)

    # Schedule a command for the past
    cmd = MockCommand()
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    await scheduler.schedule(cmd, past)

    # Process due commands
    count = await service.process_due_commands()

    assert count == 1
    send_fn.assert_called_once_with(cmd)
    assert scheduler.scheduled_count == 0


@pytest.mark.asyncio
async def test_scheduler_service_skips_future_commands() -> None:
    scheduler = InMemoryCommandScheduler()
    send_fn = AsyncMock()
    service = CommandSchedulerService(scheduler, send_fn)

    # Schedule a command for the future
    cmd = MockCommand()
    future = datetime.now(timezone.utc) + timedelta(minutes=1)
    await scheduler.schedule(cmd, future)

    # Process due commands
    count = await service.process_due_commands()

    assert count == 0
    send_fn.assert_not_called()
    assert scheduler.scheduled_count == 1


@pytest.mark.asyncio
async def test_scheduler_service_handles_execution_failure() -> None:
    scheduler = InMemoryCommandScheduler()
    send_fn = AsyncMock(side_effect=Exception("Execution failed"))
    service = CommandSchedulerService(scheduler, send_fn)

    # Schedule a command for the past
    cmd = MockCommand()
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    await scheduler.schedule(cmd, past)

    # Process due commands
    count = await service.process_due_commands()

    assert count == 0
    send_fn.assert_called_once_with(cmd)
    # Command should still be in scheduler if execution failed
    # (Actually, in our simple impl it might stay or be removed.
    # Current impl: it stays because delete_executed is after await send_fn)
    assert scheduler.scheduled_count == 1


@pytest.mark.asyncio
async def test_scheduler_worker_run_once() -> None:
    from cqrs_ddd_advanced_core.scheduling.worker import CommandSchedulerWorker

    scheduler = InMemoryCommandScheduler()
    send_fn = AsyncMock()
    service = CommandSchedulerService(scheduler, send_fn)
    worker = CommandSchedulerWorker(service)

    # Schedule a command for the past
    cmd = MockCommand()
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    await scheduler.schedule(cmd, past)

    # Run worker once
    count = await worker.run_once()

    assert count == 1
    send_fn.assert_called_once_with(cmd)
    assert scheduler.scheduled_count == 0


@pytest.mark.asyncio
async def test_scheduler_worker_lifecycle() -> None:
    from cqrs_ddd_advanced_core.scheduling.worker import CommandSchedulerWorker

    scheduler = InMemoryCommandScheduler()
    send_fn = AsyncMock()
    service = CommandSchedulerService(scheduler, send_fn)
    worker = CommandSchedulerWorker(service, poll_interval=0.01)

    await worker.start()
    assert worker._running is True

    # Schedule a command
    cmd = MockCommand()
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    await scheduler.schedule(cmd, past)

    # Wait for poll
    await asyncio.sleep(0.05)

    await worker.stop()
    assert worker._running is False

    assert send_fn.called
    assert scheduler.scheduled_count == 0
