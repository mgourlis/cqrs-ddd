"""MongoDB projection position store implementing IProjectionPositionStore."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from cqrs_ddd_advanced_core.ports.projection import IProjectionPositionStore

if TYPE_CHECKING:
    from cqrs_ddd_core.ports.unit_of_work import UnitOfWork


def _get_client_and_db(
    client: Any = None,
    database: str | None = None,
    connection: Any = None,
) -> tuple[Any, str]:
    if client is not None and database is not None:
        return client, database
    if connection is not None:
        db = database or getattr(connection, "_database", None)
        if db is None:
            raise ValueError("Database name must be set when using connection")
        return connection.client, db
    raise ValueError("Provide (client, database) or (connection=..., database=...)")


class MongoProjectionPositionStore(IProjectionPositionStore):
    """
    MongoDB implementation of IProjectionPositionStore.

    Stores positions in a dedicated collection (default projection_positions),
    keyed by projection_name. Uses uow.session when provided for same-transaction
    updates with projection writes.
    """

    def __init__(
        self,
        client: Any = None,
        database: str | None = None,
        *,
        connection: Any = None,
        collection: str = "projection_positions",
    ) -> None:
        self._client, self._database = _get_client_and_db(
            client=client, database=database, connection=connection
        )
        self._collection = collection

    def _coll(self) -> Any:
        return self._client.get_database(self._database)[self._collection]

    def _get_session(self, uow: UnitOfWork | None) -> Any:
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
        coll = self._coll()
        doc = await coll.find_one(
            {"projection_name": projection_name},
            session=session,
            projection={"position": 1},
        )
        if doc is None:
            return None
        pos = doc.get("position")
        return int(pos) if pos is not None else None

    async def save_position(
        self,
        projection_name: str,
        position: int,
        *,
        uow: UnitOfWork | None = None,
    ) -> None:
        session = self._get_session(uow)
        coll = self._coll()
        await coll.replace_one(
            {"projection_name": projection_name},
            {"projection_name": projection_name, "position": position},
            upsert=True,
            session=session,
        )

    async def reset_position(
        self,
        projection_name: str,
        *,
        uow: UnitOfWork | None = None,
    ) -> None:
        session = self._get_session(uow)
        coll = self._coll()
        await coll.delete_one(
            {"projection_name": projection_name},
            session=session,
        )
