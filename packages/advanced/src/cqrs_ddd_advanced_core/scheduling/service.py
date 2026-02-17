"""CommandSchedulerService — coordination for scheduled commands."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

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
        due = await self._scheduler.get_due_commands()
        if not due:
            return 0

        count = 0
        for schedule_id, command in due:
            try:
                logger.info(
                    "Executing scheduled command %s (ID: %s)",
                    command.__class__.__name__,
                    schedule_id,
                )
                await self._send_fn(command)
                await self._scheduler.delete_executed(schedule_id)
                count += 1
            except Exception:
                logger.exception(
                    "Failed to execute scheduled command %s (ID: %s)",
                    command.__class__.__name__,
                    schedule_id,
                )

        return count
