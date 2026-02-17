"""
SQLAlchemy implementation of Command Scheduler.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import delete, select

from cqrs_ddd_advanced_core.exceptions import HandlerNotRegisteredError
from cqrs_ddd_advanced_core.ports.scheduling import ICommandScheduler

from ..compat import require_advanced
from .models import ScheduledCommandModel

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from cqrs_ddd_core.cqrs.command import Command
    from cqrs_ddd_core.cqrs.message_registry import MessageRegistry

    from ..core.repository import UnitOfWorkFactory


class SQLAlchemyCommandScheduler(ICommandScheduler):
    """
    SQLAlchemy-backed Command Scheduler.
    Requires cqrs-ddd-advanced-core.

    Uses a MessageRegistry to deserialize scheduled commands from stored payloads.
    """

    async def _get_session(self) -> AsyncSession:
        """Retrieve the active session from UnitOfWork."""

        # If we have a factory, use it.
        if self._uow_factory:
            uow = self._uow_factory()
            return uow.session

        raise ValueError("No uow_factory provided to scheduler.")

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory | None = None,
        message_registry: MessageRegistry | None = None,
    ) -> None:
        require_advanced("SQLAlchemyCommandScheduler")
        self._uow_factory = uow_factory
        self.message_registry = message_registry

    async def schedule(
        self,
        command: Command[Any],
        execute_at: datetime,
        description: str | None = None,
    ) -> str:
        """Schedule a command for future execution."""
        schedule_id = str(uuid4())

        # We need to serialize the command.
        # Typically command should be a Pydantic model or dataclass with as_dict/json.
        # Let's assume Pydantic's model_dump.
        payload = command.model_dump(mode="json")
        command_type = command.__class__.__name__

        model = ScheduledCommandModel(
            id=schedule_id,
            command_type=command_type,
            command_payload=payload,
            execute_at=execute_at,
            status="PENDING",
            created_at=datetime.now(timezone.utc),
            description=description,
        )
        session = await self._get_session()
        session.add(model)
        # Note: Session commit is external (Unit of Work)
        return schedule_id

    async def get_due_commands(self) -> list[tuple[str, Command[Any]]]:
        """
        Retrieve all commands due for execution.
        Returns tuples of (id, command).

        Uses the MessageRegistry to deserialize commands using their
        registered command classes.

        Raises HandlerNotRegisteredError if a scheduled command type is not
        registered in the MessageRegistry.
        """
        now = datetime.now(timezone.utc)
        stmt = (
            select(ScheduledCommandModel)
            .where(
                ScheduledCommandModel.execute_at <= now,
                ScheduledCommandModel.status == "PENDING",
            )
            .order_by(ScheduledCommandModel.execute_at)
        )
        session = await self._get_session()
        result = await session.execute(stmt)
        models = result.scalars().all()

        if self.message_registry is None:
            raise ValueError("message_registry is required for get_due_commands")

        commands: list[tuple[str, Command[Any]]] = []
        for m in models:
            cmd = self.message_registry.hydrate_command(
                m.command_type, m.command_payload
            )
            if cmd is None:
                raise HandlerNotRegisteredError(
                    f"Scheduled command type '{m.command_type}' not registered. "
                    f"Ensure it's registered in MessageRegistry."
                )
            commands.append((m.id, cmd))

        return commands

    async def cancel(self, schedule_id: str) -> bool:
        """Cancel a scheduled command."""
        stmt = select(ScheduledCommandModel).where(
            ScheduledCommandModel.id == schedule_id
        )
        session = await self._get_session()
        result = await session.execute(stmt)
        model = result.scalar_one_or_none()
        if model:
            model.status = "CANCELLED"
            return True
        return False

    async def delete_executed(self, schedule_id: str) -> None:
        """Remove a command from the schedule after execution."""
        session = await self._get_session()
        await session.execute(
            delete(ScheduledCommandModel).where(ScheduledCommandModel.id == schedule_id)
        )
