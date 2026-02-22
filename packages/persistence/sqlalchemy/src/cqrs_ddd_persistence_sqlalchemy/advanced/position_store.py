"""SQLAlchemy projection position store implementing IProjectionPositionStore."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from cqrs_ddd_advanced_core.ports.projection import IProjectionPositionStore
from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

if TYPE_CHECKING:
    from collections.abc import Callable

    AsyncSessionFactory = Callable[[], Any]


TABLE_NAME = "projection_positions"


class SQLAlchemyProjectionPositionStore(IProjectionPositionStore):
    """
    SQLAlchemy implementation of IProjectionPositionStore.

    Stores positions in a table (default projection_positions) with columns
    projection_name (PK) and position. Uses uow.session when provided.
    """

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        *,
        table_name: str = TABLE_NAME,
    ) -> None:
        self._session_factory = session_factory
        self._table = table_name

    def _get_session(self, uow: UnitOfWork | None) -> AsyncSession | None:
        if uow is None:
            return None
        return getattr(uow, "session", None)

    async def get_position(
        self,
        projection_name: str,
        *,
        uow: UnitOfWork | None = None,
    ) -> int | None:
        session = self._get_session(uow)
        if session is not None:
            r = await session.execute(
                text(
                    f"SELECT position FROM {self._table} "
                    "WHERE projection_name = :name"
                ),
                {"name": projection_name},
            )
            row = r.fetchone()
            return int(row[0]) if row else None
        async with self._session_factory() as session:
            r = await session.execute(
                text(
                    f"SELECT position FROM {self._table} "
                    "WHERE projection_name = :name"
                ),
                {"name": projection_name},
            )
            row = r.fetchone()
            return int(row[0]) if row else None

    async def save_position(
        self,
        projection_name: str,
        position: int,
        *,
        uow: UnitOfWork | None = None,
    ) -> None:
        session = self._get_session(uow)
        if session is not None:
            await session.execute(
                text(
                    f"""
                    INSERT INTO {self._table} (projection_name, position)
                    VALUES (:name, :position)
                    ON CONFLICT (projection_name) DO UPDATE SET position = :position
                    """
                ),
                {"name": projection_name, "position": position},
            )
            return
        async with self._session_factory() as session:
            await session.execute(
                text(
                    f"""
                    INSERT INTO {self._table} (projection_name, position)
                    VALUES (:name, :position)
                    ON CONFLICT (projection_name) DO UPDATE SET position = :position
                    """
                ),
                {"name": projection_name, "position": position},
            )
            await session.commit()

    async def reset_position(
        self,
        projection_name: str,
        *,
        uow: UnitOfWork | None = None,
    ) -> None:
        session = self._get_session(uow)
        if session is not None:
            await session.execute(
                text(
                    f"DELETE FROM {self._table} WHERE projection_name = :name"
                ),
                {"name": projection_name},
            )
            return
        async with self._session_factory() as session:
            await session.execute(
                text(
                    f"DELETE FROM {self._table} WHERE projection_name = :name"
                ),
                {"name": projection_name},
            )
            await session.commit()
