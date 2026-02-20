"""SQLAlchemy implementations for projections infrastructure."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Mapped, mapped_column

from .core.models import Base

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.dialects.postgresql.dml import Insert as PGInsert
    from sqlalchemy.ext.asyncio import AsyncSession


class ProjectionCheckpoint(Base):
    """SQLAlchemy model for projection checkpoint storage."""

    __tablename__ = "projection_checkpoints"

    projection_name: Mapped[str] = mapped_column(String, primary_key=True)
    position: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (Index("ix_projection_checkpoints_name", "projection_name"),)


class SQLAlchemyProjectionCheckpointStore:
    """Persistent projection checkpoint store using SQLAlchemy.

    Provides atomic upsert operations for checkpointing projection positions
    across restarts.
    """

    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        """
        Initialize checkpoint store with session factory.

        Args:
            session_factory: Factory function that creates new AsyncSession instances.
        """
        self._session_factory = session_factory

    async def get_position(self, projection_name: str) -> int | None:
        """Retrieve checkpoint position from database."""
        async with self._session_factory() as session:
            from sqlalchemy import select

            stmt = select(ProjectionCheckpoint).where(
                ProjectionCheckpoint.projection_name == projection_name
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            return row.position if row else None

    async def save_position(self, projection_name: str, position: int) -> None:
        """Save or update checkpoint position in database."""
        async with self._session_factory() as session:
            if session.bind.dialect.name == "postgresql":
                # PostgreSQL: ON CONFLICT DO UPDATE

                stmt: PGInsert = (
                    pg_insert(ProjectionCheckpoint)
                    .values(
                        projection_name=projection_name,
                        position=position,
                        updated_at=datetime.now(timezone.utc),
                    )
                    .on_conflict_do_update(
                        index_elements=["projection_name"],
                        set_={
                            "position": position,
                            "updated_at": datetime.now(timezone.utc),
                        },
                    )
                )
                await session.execute(stmt)
            else:
                # Fallback for SQLite: try insert, then update on duplicate
                from sqlalchemy import insert

                stmt = insert(ProjectionCheckpoint).values(  # type: ignore[assignment]
                    projection_name=projection_name,
                    position=position,
                    updated_at=datetime.now(timezone.utc),
                )
                try:
                    await session.execute(stmt)
                except Exception:  # noqa: BLE001
                    # Update on duplicate key
                    from sqlalchemy import select

                    update_stmt = select(ProjectionCheckpoint).where(
                        ProjectionCheckpoint.projection_name == projection_name
                    )
                    result = await session.execute(update_stmt)
                    checkpoint = result.scalar_one_or_none()
                    if checkpoint:
                        checkpoint.position = position
                        checkpoint.updated_at = datetime.now(timezone.utc)
            await session.commit()
