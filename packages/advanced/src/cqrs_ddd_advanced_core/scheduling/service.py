"""CommandSchedulerService — coordination for scheduled commands."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from cqrs_ddd_core.correlation import get_correlation_id
from cqrs_ddd_core.instrumentation import get_hook_registry

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from cqrs_ddd_core.cqrs.command import Command

    from ..ports.scheduling import ICommandScheduler

logger = logging.getLogger(__name__)


class CommandSchedulerService:
    """
    Service to manage command scheduling and execution.

    This service wraps an :class:`ICommandScheduler` port.
    """

    def __init__(
        self,
        scheduler: ICommandScheduler,
        mediator_send_fn: Callable[[Command[Any]], Awaitable[Any]],
    ) -> None:
        self._scheduler = scheduler
        self._send_fn = mediator_send_fn

    async def process_due_commands(self) -> int:
        """
        Retrieves all due commands and dispatches them via the mediator.

        Returns:
            The number of commands successfully dispatched.
        """
        registry = get_hook_registry()
        return cast(
            "int",
            await registry.execute_all(
                "scheduler.dispatch.batch",
                {"correlation_id": get_correlation_id()},
                self._process_due_commands_internal,
            ),
        )

    async def _process_due_commands_internal(self) -> int:
        due = await self._scheduler.get_due_commands()
        if not due:
            return 0

        count = 0
        for schedule_id, command in due:
            try:
                op_registry = get_hook_registry()
                logger.info(
                    "Executing scheduled command %s (ID: %s)",
                    command.__class__.__name__,
                    schedule_id,
                )
                await op_registry.execute_all(
                    f"scheduler.dispatch.{type(command).__name__}",
                    {
                        "command.type": type(command).__name__,
                        "schedule.id": schedule_id,
                        "message_type": type(command),
                        "correlation_id": get_correlation_id()
                        or getattr(command, "correlation_id", None),
                    },
                    self._dispatch_scheduled_command(command),
                )
                await self._scheduler.delete_executed(schedule_id)
                count += 1
            except Exception:
                logger.exception(
                    "Failed to execute scheduled command %s (ID: %s)",
                    command.__class__.__name__,
                    schedule_id,
                )

        return count

    def _dispatch_scheduled_command(
        self, command: Command[Any]
    ) -> Callable[[], Awaitable[Any]]:
        async def _dispatch() -> Any:
            return await self._send_fn(command)

        return _dispatch
