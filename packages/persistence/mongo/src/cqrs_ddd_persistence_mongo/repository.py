"""MongoRepository[T] — generic read-model repository implementing IRepository."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, TypeVar

from cqrs_ddd_core.domain.aggregate import AggregateRoot
from cqrs_ddd_core.ports.repository import IRepository
from cqrs_ddd_core.ports.search_result import SearchResult

from .query_builder import MongoQueryBuilder
from .serialization import model_from_doc, model_to_doc

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

    from .connection import MongoConnectionManager

T = TypeVar("T", bound=AggregateRoot[Any])


class MongoRepository(IRepository[T, str], Generic[T]):
    """Read-model repository over MongoDB. search() returns SearchResult[T]."""

    def __init__(
        self,
        connection: MongoConnectionManager,
        collection: str,
        model_cls: type[T],
        *,
        id_field: str = "id",
        query_builder: MongoQueryBuilder | None = None,
    ) -> None:
        self._connection = connection
        self._collection_name = collection
        self._model_cls = model_cls
        self._id_field = id_field
        self._query_builder = query_builder or MongoQueryBuilder()

    def _collection(self) -> Any:
        return self._connection.client.get_database().get_collection(
            self._collection_name
        )

    async def add(self, entity: T, uow: UnitOfWork | None = None) -> str:  # noqa: ARG002
        """Insert or replace document. Returns entity id."""
        coll = self._collection()
        doc = model_to_doc(entity, use_id_field=self._id_field)
        doc_id = doc.get("_id")
        if doc_id is None:
            from bson import ObjectId

            doc["_id"] = ObjectId()
            doc_id = str(doc["_id"])
        await coll.replace_one(
            {"_id": doc["_id"]},
            doc,
            upsert=True,
        )
        return str(doc_id)

    async def get(self, entity_id: str, uow: UnitOfWork | None = None) -> T | None:  # noqa: ARG002
        """Load one document by id."""
        coll = self._collection()
        doc = await coll.find_one({"_id": entity_id})
        if doc is None:
            return None
        return model_from_doc(self._model_cls, doc, id_field=self._id_field)

    async def delete(self, entity_id: str, uow: UnitOfWork | None = None) -> str:  # noqa: ARG002
        """Remove document by id. Returns deleted id."""
        coll = self._collection()
        await coll.delete_one({"_id": entity_id})
        return entity_id

    async def list_all(
        self,
        entity_ids: list[str] | None = None,
        uow: UnitOfWork | None = None,  # noqa: ARG002
    ) -> list[T]:
        """List documents; if entity_ids given, filter by _id in list."""
        coll = self._collection()
        if entity_ids:
            cursor = coll.find({"_id": {"$in": entity_ids}})
        else:
            cursor = coll.find({})
        results = []
        async for doc in cursor:
            results.append(
                model_from_doc(self._model_cls, doc, id_field=self._id_field)
            )
        return results

    def _normalise_criteria(self, criteria: Any) -> tuple[Any, Any | None]:
        """Return ``(specification, options)`` from search criteria."""
        if hasattr(criteria, "specification"):
            return getattr(criteria, "specification", None), criteria
        return criteria, None

    def _extract_search_context(
        self, spec: Any, options: Any | None
    ) -> tuple[Any, Any, Any, Any]:
        order_by = None
        limit = None
        offset = None
        fields = None
        if options is not None:
            order_by = getattr(options, "order_by", None) or getattr(
                options, "sort", None
            )
            limit = getattr(options, "limit", None)
            offset = getattr(options, "offset", None)
            fields = getattr(options, "select_fields", None) or getattr(
                options, "fields", None
            )
        if order_by is None and spec is not None:
            order_by = getattr(spec, "order_by", None) or getattr(spec, "sort", None)
        if limit is None and spec is not None:
            limit = getattr(spec, "limit", None)
        if offset is None and spec is not None:
            offset = getattr(spec, "offset", None)
        if fields is None and spec is not None:
            fields = getattr(spec, "select_fields", None) or getattr(
                spec, "fields", None
            )
        return order_by, limit, offset, fields

    def _build_pipeline(
        self,
        *,
        match: dict[str, Any],
        sort_list: list[tuple[str, int]],
        offset: Any,
        limit: Any,
        fields: Any,
    ) -> list[dict[str, Any]]:
        pipeline: list[dict[str, Any]] = []
        if match:
            pipeline.append({"$match": match})
        if sort_list:
            pipeline.append({"$sort": dict(sort_list)})
        if offset is not None:
            pipeline.append({"$skip": offset})
        if limit is not None:
            pipeline.append({"$limit": limit})
        proj = self._query_builder.build_project(list(fields) if fields else None)
        if proj:
            pipeline.append({"$project": proj})
        return pipeline

    async def search(
        self,
        criteria: Any,
        uow: UnitOfWork | None = None,  # noqa: ARG002
    ) -> SearchResult[T]:
        """Search with specification or query options.

        Returns :class:`SearchResult[T]` for both list and streaming access.
        """
        spec, options = self._normalise_criteria(criteria)
        match = self._query_builder.build_match(spec) if spec else {}
        order_by, limit, offset, fields = self._extract_search_context(spec, options)
        sort_list = self._query_builder.build_sort(
            order_by if isinstance(order_by, list) else None
        )

        async def list_fn() -> list[T]:
            coll = self._collection()
            pipeline = self._build_pipeline(
                match=match,
                sort_list=sort_list,
                offset=offset,
                limit=limit,
                fields=fields,
            )
            cursor = coll.aggregate(pipeline)
            return [
                model_from_doc(self._model_cls, doc, id_field=self._id_field)
                async for doc in cursor
            ]

        async def stream_fn(batch_size: int | None) -> AsyncIterator[T]:
            coll = self._collection()
            pipeline = self._build_pipeline(
                match=match,
                sort_list=sort_list,
                offset=offset,
                limit=limit,
                fields=fields,
            )
            batch = batch_size or 100
            cursor = coll.aggregate(pipeline, batchSize=batch)
            async for doc in cursor:
                yield model_from_doc(self._model_cls, doc, id_field=self._id_field)

        return SearchResult(list_fn, stream_fn)
