"""In-memory implementation of command scheduling for testing."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from cqrs_ddd_advanced_core.ports.scheduling import ICommandScheduler

if TYPE_CHECKING:
    from cqrs_ddd_core.cqrs.command import Command


class InMemoryCommandScheduler(ICommandScheduler):
    """
    Dict-backed :class:`ICommandScheduler` for unit / integration tests.
    """

    def __init__(self) -> None:
        self._scheduled: dict[str, tuple[Command[Any], datetime, str | None]] = {}

    async def schedule(
        self,
        command: Command[Any],
        execute_at: datetime,
        description: str | None = None,
    ) -> str:
        # Ensure UTC if missing timezone
        if execute_at.tzinfo is None:
            execute_at = execute_at.replace(tzinfo=timezone.utc)

        schedule_id = str(uuid.uuid4())
        self._scheduled[schedule_id] = (command, execute_at, description)
        return schedule_id

    async def get_due_commands(self) -> list[tuple[str, Command[Any]]]:
        now = datetime.now(timezone.utc)
        due: list[tuple[str, Command[Any]]] = []

        for sid, (cmd, execute_at, _) in self._scheduled.items():
            if execute_at <= now:
                due.append((sid, cmd))

        # Sort by execution time
        due.sort(key=lambda x: self._scheduled[x[0]][1])
        return due

    async def cancel(self, schedule_id: str) -> bool:
        if schedule_id in self._scheduled:
            del self._scheduled[schedule_id]
            return True
        return False

    async def delete_executed(self, schedule_id: str) -> None:
        self._scheduled.pop(schedule_id, None)

    # --- Test helpers ---

    def clear(self) -> None:
        self._scheduled.clear()

    @property
    def scheduled_count(self) -> int:
        return len(self._scheduled)
