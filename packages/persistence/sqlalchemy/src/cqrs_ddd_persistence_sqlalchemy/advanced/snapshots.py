"""
SQLAlchemy implementation of Snapshot Store.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, select

from ..compat import require_advanced
from .models import SnapshotModel

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from ..core.repository import UnitOfWorkFactory


class SQLAlchemySnapshotStore:
    """
    SQLAlchemy-backed Snapshot Store.
    Requires cqrs-ddd-advanced-core.
    """

    async def _get_session(self) -> AsyncSession:
        """Retrieve the active session from UnitOfWork."""

        # If we have a factory, use it.
        if self._uow_factory:
            uow = self._uow_factory()
            return uow.session

        raise ValueError("No uow_factory provided to snapshot store.")

    def __init__(self, uow_factory: UnitOfWorkFactory | None = None) -> None:
        require_advanced("SQLAlchemySnapshotStore")
        self._uow_factory = uow_factory

    async def save_snapshot(
        self,
        aggregate_type: str,
        aggregate_id: Any,
        snapshot_data: dict[str, Any],
        version: int,
    ) -> None:
        """Save a snapshot of an aggregate's state."""
        # Convert aggregate_id to str
        agg_id_str = str(aggregate_id)

        model = SnapshotModel(
            aggregate_id=agg_id_str,
            aggregate_type=aggregate_type,
            version=version,
            snapshot_data=snapshot_data,
        )
        session = await self._get_session()
        session.add(model)

    async def get_latest_snapshot(
        self,
        aggregate_type: str,
        aggregate_id: Any,
    ) -> dict[str, Any] | None:
        """Retrieve the most recent snapshot for an aggregate."""
        stmt = (
            select(SnapshotModel)
            .where(
                SnapshotModel.aggregate_id == str(aggregate_id),
                SnapshotModel.aggregate_type == aggregate_type,
            )
            .order_by(SnapshotModel.version.desc())
            .limit(1)
        )
        session = await self._get_session()
        result = await session.execute(stmt)
        model = result.scalar_one_or_none()

        if not model:
            return None

        return {
            "snapshot_data": model.snapshot_data,
            "version": model.version,
            "created_at": model.created_at,
        }

    async def delete_snapshot(
        self,
        aggregate_type: str,
        aggregate_id: Any,
    ) -> None:
        """Delete all snapshots for an aggregate."""
        stmt = delete(SnapshotModel).where(
            SnapshotModel.aggregate_id == str(aggregate_id),
            SnapshotModel.aggregate_type == aggregate_type,
        )
        session = await self._get_session()
        await session.execute(stmt)
