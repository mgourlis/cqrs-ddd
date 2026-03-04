"""
SQLAlchemy implementation of Snapshot Store.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, select

from ..compat import require_advanced
from ..specifications.compiler import build_sqla_filter
from .models import SnapshotModel

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from cqrs_ddd_core.domain.specification import ISpecification

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
        *,
        specification: ISpecification[Any] | None = None,
    ) -> None:
        """Save a snapshot of an aggregate's state."""
        # Convert aggregate_id to str
        agg_id_str = str(aggregate_id)

        # Extract tenant_id from specification if provided
        tenant_id: str | None = None
        if specification is not None:
            spec_data = specification.to_dict()
            if spec_data.get("attr") == "tenant_id":
                tenant_id = spec_data.get("val") or spec_data.get("value")

        model = SnapshotModel(
            aggregate_id=agg_id_str,
            aggregate_type=aggregate_type,
            version=version,
            snapshot_data=snapshot_data,
            tenant_id=tenant_id,
        )
        session = await self._get_session()
        session.add(model)

    def _apply_spec(
        self,
        stmt: Any,
        specification: ISpecification[Any] | None,
    ) -> Any:
        """Compile an ISpecification to a WHERE clause and apply it."""
        if specification is None:
            return stmt
        spec_data = specification.to_dict()
        if spec_data:
            where_clause = build_sqla_filter(SnapshotModel, spec_data)
            stmt = stmt.where(where_clause)
        return stmt

    async def get_latest_snapshot(
        self,
        aggregate_type: str,
        aggregate_id: Any,
        *,
        specification: ISpecification[Any] | None = None,
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
        stmt = self._apply_spec(stmt, specification)
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
        *,
        specification: ISpecification[Any] | None = None,
    ) -> None:
        """Delete all snapshots for an aggregate."""
        stmt = delete(SnapshotModel).where(
            SnapshotModel.aggregate_id == str(aggregate_id),
            SnapshotModel.aggregate_type == aggregate_type,
        )
        if specification is not None:
            spec_data = specification.to_dict()
            if spec_data:
                where_clause = build_sqla_filter(SnapshotModel, spec_data)
                stmt = stmt.where(where_clause)
        session = await self._get_session()
        await session.execute(stmt)
