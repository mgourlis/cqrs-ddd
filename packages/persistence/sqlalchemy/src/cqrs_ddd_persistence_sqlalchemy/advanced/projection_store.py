"""SQLAlchemy projection store implementing IProjectionWriter and IProjectionReader."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from cqrs_ddd_advanced_core.ports.projection import (
    DocId,
    IProjectionReader,
    IProjectionWriter,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from cqrs_ddd_advanced_core.projections.schema import ProjectionSchema
    from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

    AsyncSessionFactory = Callable[
        [], Any
    ]  # async context manager yielding AsyncSession

logger = logging.getLogger("cqrs_ddd.projection.sqlalchemy")

# Regex for valid SQL table/column names (prevents SQL injection)
_VALID_IDENTIFIER = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


class SQLAlchemyProjectionStore(IProjectionWriter, IProjectionReader):
    """
    SQLAlchemy implementation of IProjectionWriter and IProjectionReader.

    Features:
    - SQL injection protection via identifier validation
    - Version-based concurrency control (optimistic locking)
    - Idempotent event processing via _last_event_id
    - Composite primary key support
    - Efficient batch upserts

    Constructor accepts a session_factory (callable returning async context manager
    that yields AsyncSession) and optional allow_auto_ddl. When allow_auto_ddl is False,
    ensure_collection raises; use migrations in production.
    """

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        *,
        allow_auto_ddl: bool = False,
        default_id_column: str = "id",
    ) -> None:
        self._session_factory = session_factory
        self._allow_auto_ddl = allow_auto_ddl
        self._default_id_column = default_id_column

    def _validate_identifier(self, name: str, context: str = "identifier") -> str:
        """Validate SQL identifier to prevent injection attacks."""
        if not _VALID_IDENTIFIER.match(name):
            raise ValueError(f"Invalid SQL {context}: {name!r}")
        return name

    def _validate_table_name(self, name: str) -> str:
        """Validate table name for SQL injection prevention."""
        return self._validate_identifier(name, "table name")

    def _validate_column_name(self, name: str) -> str:
        """Validate column name for SQL injection prevention."""
        return self._validate_identifier(name, "column name")

    def _get_session(self, uow: UnitOfWork | None) -> AsyncSession | None:
        if uow is None:
            return None
        return getattr(uow, "session", None)

    async def _run_with_session(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        session = self._get_session(kwargs.get("uow"))
        if session is not None:
            return await fn(session, *args, **kwargs)
        async with self._session_factory() as session:
            kwargs["uow"] = type("UoW", (), {"session": session})()
            return await fn(session, *args, **kwargs)

    async def ensure_collection(
        self,
        collection: str,
        *,
        schema: ProjectionSchema | None = None,
    ) -> None:
        collection = self._validate_table_name(collection)
        if not self._allow_auto_ddl:
            raise RuntimeError(
                "Auto-DDL disabled. Run migrations manually: alembic upgrade head. "
                "See docs/projection_schemas.md."
            )
        if schema is None:
            return
        async with self._session_factory() as session:
            await session.execute(text(schema.create_ddl()))
            await session.commit()

    async def collection_exists(self, collection: str) -> bool:
        collection = self._validate_table_name(collection)
        async with self._session_factory() as session:
            # PostgreSQL / SQLite: check information_schema or sqlite_master
            try:
                r = await session.execute(
                    text(
                        "SELECT 1 FROM information_schema.tables "
                        "WHERE table_name = :name"
                    ),
                    {"name": collection},
                )
                return r.scalar() is not None
            except Exception:
                r = await session.execute(
                    text(
                        "SELECT 1 FROM sqlite_master "
                        "WHERE type = 'table' AND name = :name"
                    ),
                    {"name": collection},
                )
                return r.scalar() is not None

    async def truncate_collection(self, collection: str) -> None:
        collection = self._validate_table_name(collection)
        async with self._session_factory() as session:
            await session.execute(text(f"TRUNCATE TABLE {collection}"))
            await session.commit()

    async def drop_collection(self, collection: str) -> None:
        collection = self._validate_table_name(collection)
        async with self._session_factory() as session:
            await session.execute(text(f"DROP TABLE IF EXISTS {collection} CASCADE"))
            await session.commit()

    def _where_from_doc_id(
        self, collection: str, doc_id: DocId
    ) -> tuple[str, dict[str, Any], list[str]]:
        """
        Build WHERE clause from doc_id.

        Returns:
            Tuple of (where_clause, params, conflict_columns)
        """
        if isinstance(doc_id, (str, int)):
            col = self._default_id_column
            self._validate_column_name(col)
            return f"{col} = :id", {"id": doc_id}, [col]
        if isinstance(doc_id, dict):
            # Validate all column names
            for k in doc_id:
                self._validate_column_name(k)
            cond = " AND ".join(f"{k} = :{k}" for k in doc_id)
            return cond, dict(doc_id), list(doc_id.keys())
        raise ValueError(f"Invalid doc_id type: {type(doc_id)}")

    async def get(
        self,
        collection: str,
        doc_id: DocId,
        *,
        uow: UnitOfWork | None = None,
    ) -> dict[str, Any] | None:
        collection = self._validate_table_name(collection)
        where, params, _ = self._where_from_doc_id(collection, doc_id)
        session = self._get_session(uow)
        if session is not None:
            r = await session.execute(
                text(f"SELECT * FROM {collection} WHERE {where}"), params
            )
            row = r.mappings().fetchone()
            return dict(row) if row else None
        async with self._session_factory() as session:
            r = await session.execute(
                text(f"SELECT * FROM {collection} WHERE {where}"), params
            )
            row = r.mappings().fetchone()
            return dict(row) if row else None

    async def get_batch(
        self,
        collection: str,
        doc_ids: list[DocId],
        *,
        uow: UnitOfWork | None = None,
    ) -> list[dict[str, Any] | None]:
        """Fetch multiple documents by IDs, preserving order."""
        collection = self._validate_table_name(collection)
        if not doc_ids:
            return []

        results: list[dict[str, Any] | None] = [None] * len(doc_ids)
        id_col = self._default_id_column
        self._validate_column_name(id_col)

        # Build IN clause for simple IDs
        if all(isinstance(d, (str, int)) for d in doc_ids):
            placeholders = ", ".join(f":id_{i}" for i in range(len(doc_ids)))
            params = {f"id_{i}": d for i, d in enumerate(doc_ids)}
            query = text(
                f"SELECT * FROM {collection} WHERE {id_col} IN ({placeholders})"
            )

            session = self._get_session(uow)
            if session is None:
                async with self._session_factory() as session:
                    r = await session.execute(query, params)
                    rows = {row._mapping[id_col]: dict(row._mapping) for row in r}
            else:
                r = await session.execute(query, params)
                rows = {row._mapping[id_col]: dict(row._mapping) for row in r}

            # Map back to original order
            for i, doc_id in enumerate(doc_ids):
                results[i] = rows.get(doc_id)
        else:
            # Fallback: individual queries for composite keys
            for i, doc_id in enumerate(doc_ids):
                results[i] = await self.get(collection, doc_id, uow=uow)

        return results

    async def find(
        self,
        collection: str,
        filter: dict[str, Any],
        *,
        limit: int = 100,
        offset: int = 0,
        uow: UnitOfWork | None = None,
    ) -> list[dict[str, Any]]:
        """Query documents by filter dict."""
        collection = self._validate_table_name(collection)

        # Validate filter column names
        for k in filter:
            self._validate_column_name(k)

        where_parts = []
        params: dict[str, Any] = {}
        for i, (k, v) in enumerate(filter.items()):
            param_name = f"param_{i}"
            where_parts.append(f"{k} = :{param_name}")
            params[param_name] = v

        where_clause = " AND ".join(where_parts) if where_parts else "1=1"
        query = text(
            f"SELECT * FROM {collection} WHERE {where_clause} "
            f"LIMIT :limit OFFSET :offset"
        )
        params["limit"] = limit
        params["offset"] = offset

        session = self._get_session(uow)
        if session is None:
            async with self._session_factory() as session:
                r = await session.execute(query, params)
                return [dict(row._mapping) for row in r]
        else:
            r = await session.execute(query, params)
            return [dict(row._mapping) for row in r]

    async def upsert(
        self,
        collection: str,
        doc_id: DocId,
        data: dict[str, Any] | Any,
        *,
        event_position: int | None = None,
        event_id: str | None = None,
        uow: UnitOfWork | None = None,
    ) -> bool:
        collection = self._validate_table_name(collection)

        if hasattr(data, "model_dump"):
            data = data.model_dump(mode="json")
        data = dict(data)

        # Merge doc_id into data for composite keys
        if isinstance(doc_id, dict):
            data.update(doc_id)

        # Idempotency check: skip if we've already processed this event
        if event_id:
            existing = await self.get(collection, doc_id, uow=uow)
            if existing and existing.get("_last_event_id") == event_id:
                logger.debug(
                    "Skipping duplicate event %s for %s/%s",
                    event_id,
                    collection,
                    doc_id,
                )
                return False

        # Version check: skip if existing version is >= event_position
        if event_position is not None:
            existing = await self.get(collection, doc_id, uow=uow)
            if existing:
                existing_version = existing.get("_version", 0)
                if existing_version >= event_position:
                    logger.debug(
                        "Skipping stale event at position %s (current: %s) for %s/%s",
                        event_position,
                        existing_version,
                        collection,
                        doc_id,
                    )
                    return False

        # Add version metadata
        if event_position is not None:
            data["_version"] = event_position
        if event_id is not None:
            data["_last_event_id"] = event_id
        if event_position is not None:
            data["_last_event_position"] = event_position

        session = self._get_session(uow)
        if session is None:
            async with self._session_factory() as session:
                return await self._upsert_impl(session, collection, doc_id, data)
        return await self._upsert_impl(session, collection, doc_id, data)

    async def _upsert_impl(
        self,
        session: AsyncSession,
        collection: str,
        doc_id: DocId,
        data: dict[str, Any],
    ) -> bool:
        """Execute upsert with composite key support."""
        # Validate all column names
        for k in data:
            self._validate_column_name(k)

        # Get conflict columns from doc_id
        _, _, conflict_columns = self._where_from_doc_id(collection, doc_id)
        conflict_target = ", ".join(conflict_columns)

        cols = ", ".join(data.keys())
        placeholders = ", ".join(f":{k}" for k in data)
        # Exclude version columns from update to preserve monotonicity
        exclude_from_update = {"_version", "_last_event_id", "_last_event_position"}
        update_cols = [
            k
            for k in data
            if k not in conflict_columns and k not in exclude_from_update
        ]
        updates = ", ".join(f"{k} = EXCLUDED.{k}" for k in update_cols)

        stmt = text(
            f"""
            INSERT INTO {collection} ({cols})
            VALUES ({placeholders})
            ON CONFLICT ({conflict_target}) DO UPDATE SET {updates}
            """
        )
        await session.execute(stmt, data)
        return True

    async def upsert_batch(
        self,
        collection: str,
        docs: list[dict[str, Any] | Any],
        *,
        id_field: str = "id",
        uow: UnitOfWork | None = None,
    ) -> None:
        """Bulk upsert using execute_values pattern for efficiency."""
        collection = self._validate_table_name(collection)
        self._validate_column_name(id_field)

        if not docs:
            return

        normalized = []
        for doc in docs:
            if hasattr(doc, "model_dump"):
                doc = doc.model_dump(mode="json")
            normalized.append(dict(doc))

        # Validate all columns upfront
        for doc in normalized:
            for k in doc:
                self._validate_column_name(k)

        cols = list(normalized[0].keys())
        cols_str = ", ".join(cols)

        # Build batch insert with ON CONFLICT
        values_parts = []
        params: dict[str, Any] = {}
        for i, doc in enumerate(normalized):
            placeholders = ", ".join(f":{k}_{i}" for k in cols)
            values_parts.append(f"({placeholders})")
            for k, v in doc.items():
                params[f"{k}_{i}"] = v

        exclude_from_update = {
            "_version",
            "_last_event_id",
            "_last_event_position",
            id_field,
        }
        updates = ", ".join(
            f"{k} = EXCLUDED.{k}" for k in cols if k not in exclude_from_update
        )

        stmt = text(
            f"""
            INSERT INTO {collection} ({cols_str})
            VALUES {", ".join(values_parts)}
            ON CONFLICT ({id_field}) DO UPDATE SET {updates}
            """
        )

        session = self._get_session(uow)
        if session is None:
            async with self._session_factory() as session:
                await session.execute(stmt, params)
                await session.commit()
        else:
            await session.execute(stmt, params)

    async def delete(
        self,
        collection: str,
        doc_id: DocId,
        *,
        cascade: bool = False,
        uow: UnitOfWork | None = None,
    ) -> None:
        collection = self._validate_table_name(collection)
        where, params, _ = self._where_from_doc_id(collection, doc_id)
        session = self._get_session(uow)
        if session is None:
            async with self._session_factory() as session:
                await session.execute(
                    text(f"DELETE FROM {collection} WHERE {where}"), params
                )
                await session.commit()
            return
        await session.execute(text(f"DELETE FROM {collection} WHERE {where}"), params)

    async def ensure_ttl_index(
        self,
        collection: str,
        field: str,
        expire_after_seconds: int,
    ) -> None:
        # TTL not supported natively in PostgreSQL/SQLite; no-op
        pass
