"""MongoDB implementation of ISnapshotStore."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from cqrs_ddd_advanced_core.ports.snapshots import ISnapshotStore

from ..exceptions import MongoPersistenceError
from ..query_builder import MongoQueryBuilder

# Re-export type for use in signature
if TYPE_CHECKING:
    from cqrs_ddd_core.domain.specification import ISpecification

    from ..connection import MongoConnectionManager


def _doc_id(aggregate_type: str, aggregate_id: Any) -> str:
    return f"{aggregate_type}|{aggregate_id}"


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
            raise MongoPersistenceError(
                "Database name must be set when using MongoConnectionManager"
            )
        return connection.client, db
    raise MongoPersistenceError(
        "Provide (client, database) or (connection=..., database=...)"
    )


class MongoSnapshotStore(ISnapshotStore):
    """
    MongoDB implementation of ISnapshotStore.

    Uses a dedicated collection (default "snapshots"). Document id:
    {aggregate_type}|{aggregate_id}. Saves snapshot_data, version, created_at.
    """

    COLLECTION = "snapshots"

    def __init__(
        self,
        client: Any = None,
        database: str | None = None,
        *,
        connection: MongoConnectionManager | None = None,
        collection: str | None = None,
    ) -> None:
        self._client, self._database = _get_client_and_db(
            client=client, database=database, connection=connection
        )
        self._collection_name = collection or self.COLLECTION

    def _coll(self) -> Any:
        """Get the MongoDB collection."""
        return self._client[self._database][self._collection_name]

    def _merge_spec(
        self, query: dict[str, Any], specification: ISpecification[Any] | None
    ) -> dict[str, Any]:
        """Merge a specification filter into a MongoDB query dict."""
        if specification is None:
            return query
        builder = MongoQueryBuilder()
        spec_filter = builder.build_match(specification)
        if not spec_filter:
            return query
        if query:
            return {"$and": [query, spec_filter]}
        return spec_filter

    def _extract_value_from_filter(self, v: Any) -> Any | None:
        """Extract plain value from MongoDB filter value (plain or {$eq: value})."""
        if not isinstance(v, dict):
            return v
        if "$eq" in v and len(v) == 1:
            return v["$eq"]
        return None

    def _fields_from_clause(self, clause: dict[str, Any]) -> dict[str, Any]:
        """Extract queryable fields from a single $and clause dict."""
        out: dict[str, Any] = {}
        for k, v in clause.items():
            if not k.startswith("$"):
                extracted = self._extract_value_from_filter(v)
                if extracted is not None:
                    out[k] = extracted
        return out

    def _extract_spec_fields(
        self, specification: ISpecification[Any] | None
    ) -> dict[str, Any]:
        """Extract queryable fields from a specification for document storage.

        When a specification like ``AttributeSpecification(attr='tenant_id',
        op=EQ, val='tenant-a')`` is provided, this extracts ``{'tenant_id':
        'tenant-a'}`` so the field can be stored at the document top level,
        making it queryable by the same specification later.
        """
        if specification is None:
            return {}
        builder = MongoQueryBuilder()
        spec_filter = builder.build_match(specification)
        if not spec_filter:
            return {}
        fields: dict[str, Any] = {}
        clauses = spec_filter.get("$and", [spec_filter])
        for clause in clauses:
            if isinstance(clause, dict):
                fields.update(self._fields_from_clause(clause))
        return fields

    async def save_snapshot(
        self,
        aggregate_type: str,
        aggregate_id: Any,
        snapshot_data: dict[str, Any],
        version: int,
        *,
        specification: ISpecification[Any] | None = None,
    ) -> None:
        doc_id = _doc_id(aggregate_type, aggregate_id)
        now = datetime.now(timezone.utc)
        doc: dict[str, Any] = {
            "_id": doc_id,
            "snapshot_data": snapshot_data,
            "version": version,
            "created_at": now,
        }
        # Persist specification fields (e.g. tenant_id) at document top level
        # so they are queryable by the same specification on read.
        spec_fields = self._extract_spec_fields(specification)
        doc.update(spec_fields)
        filter_query = self._merge_spec({"_id": doc_id}, specification)
        await self._coll().replace_one(
            filter_query,
            doc,
            upsert=True,
        )

    async def get_latest_snapshot(
        self,
        aggregate_type: str,
        aggregate_id: Any,
        *,
        specification: ISpecification[Any] | None = None,
    ) -> dict[str, Any] | None:
        doc_id = _doc_id(aggregate_type, aggregate_id)
        filter_query = self._merge_spec({"_id": doc_id}, specification)
        doc = await self._coll().find_one(filter_query)
        if doc is None:
            return None
        return {
            "snapshot_data": doc["snapshot_data"],
            "version": doc["version"],
            "created_at": doc["created_at"],
        }

    async def delete_snapshot(
        self,
        aggregate_type: str,
        aggregate_id: Any,
        *,
        specification: ISpecification[Any] | None = None,
    ) -> None:
        doc_id = _doc_id(aggregate_type, aggregate_id)
        filter_query = self._merge_spec({"_id": doc_id}, specification)
        await self._coll().delete_one(filter_query)
