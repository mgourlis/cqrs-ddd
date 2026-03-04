"""In-memory implementation of command scheduling for testing."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from cqrs_ddd_advanced_core.ports.scheduling import ICommandScheduler

if TYPE_CHECKING:
    from cqrs_ddd_core.cqrs.command import Command
    from cqrs_ddd_core.domain.specification import ISpecification


@dataclass
class _ScheduledEntry:
    """Internal storage entry for a scheduled command."""

    command: Command[Any]
    execute_at: datetime
    description: str | None = None
    tenant_id: str | None = None


class InMemoryCommandScheduler(ICommandScheduler):
    """
    Dict-backed :class:`ICommandScheduler` for unit / integration tests.
    """

    def __init__(self) -> None:
        self._scheduled: dict[str, _ScheduledEntry] = {}

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

        # Extract tenant_id from command metadata if present
        metadata = getattr(command, "_metadata", None) or {}
        tenant_id = metadata.get("_tenant_id") or metadata.get("tenant_id")

        self._scheduled[schedule_id] = _ScheduledEntry(
            command=command,
            execute_at=execute_at,
            description=description,
            tenant_id=tenant_id,
        )
        return schedule_id

    async def get_due_commands(
        self,
        *,
        specification: ISpecification[Any] | None = None,
    ) -> list[tuple[str, Command[Any]]]:
        now = datetime.now(timezone.utc)
        due: list[tuple[str, Command[Any]]] = []

        for sid, entry in self._scheduled.items():
            if entry.execute_at <= now:
                if specification is not None and not specification.is_satisfied_by(
                    entry
                ):
                    continue
                due.append((sid, entry.command))

        # Sort by execution time
        due.sort(key=lambda x: self._scheduled[x[0]].execute_at)
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
