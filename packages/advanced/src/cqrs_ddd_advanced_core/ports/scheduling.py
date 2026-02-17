"""ICommandScheduler — protocol for deferred command execution."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from datetime import datetime

    from cqrs_ddd_core.cqrs.command import Command


@runtime_checkable
class ICommandScheduler(Protocol):
    """Port for scheduling commands to execute at a future time.

    Usage::

        scheduler = RedisCommandScheduler(redis_conn)

        # Schedule a command to run in 1 hour
        await scheduler.schedule(
            command=CancelOrderCommand(order_id="ord-123"),
            execute_at=datetime.now() + timedelta(hours=1)
        )

        # Retrieve scheduled commands and execute them
        due = await scheduler.get_due_commands()
        for cmd in due:
            await mediator.send(cmd)
    """

    async def schedule(
        self,
        command: Command[Any],
        execute_at: datetime,
        description: str | None = None,
    ) -> str:
        """Schedule a command for future execution.

        Args:
            command: The command to schedule.
            execute_at: When to execute the command (UTC).
            description: Optional human-readable description.

        Returns:
            Unique ID of the scheduled command (for cancellation).
        """
        ...

    async def get_due_commands(self) -> list[tuple[str, Command[Any]]]:
        """Retrieve all commands due for execution (now or before).

        Returns:
            List of (schedule_id, command) tuples.
        """
        ...

    async def cancel(self, schedule_id: str) -> bool:
        """Cancel a scheduled command.

        Args:
            schedule_id: ID returned by schedule().

        Returns:
            True if cancelled, False if not found.
        """
        ...

    async def delete_executed(self, schedule_id: str) -> None:
        """Remove a command from the schedule after execution."""
        ...
