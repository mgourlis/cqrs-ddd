"""MongoDB implementation of Saga persistence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from cqrs_ddd_advanced_core.ports.saga_repository import ISagaRepository
from cqrs_ddd_advanced_core.sagas.state import SagaState
from cqrs_ddd_advanced_core.sagas.state import SagaStatus as DomainSagaStatus

from ..core.repository import MongoRepository
from ..query_builder import MongoQueryBuilder

if TYPE_CHECKING:
    from cqrs_ddd_core.domain.specification import ISpecification

    from ..connection import MongoConnectionManager


class MongoSagaRepository(MongoRepository[SagaState], ISagaRepository):
    """
    MongoDB-backed repository for Saga state.
    Inherits from the generic MongoRepository for standard CRUD,
    and implements ISagaRepository for specialized saga queries.
    """

    def __init__(
        self,
        connection: MongoConnectionManager,
        collection: str = "sagas",
        saga_cls: type[SagaState] = SagaState,
        database: str | None = None,
    ) -> None:
        super().__init__(
            connection=connection,
            collection=collection,
            model_cls=saga_cls,
            database=database,
        )
        self._saga_domain_cls = saga_cls

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

    @property
    def saga_type(self) -> str:
        return self._saga_domain_cls.__name__

    async def find_by_correlation_id(
        self, correlation_id: str, saga_type: str
    ) -> SagaState | None:
        """Find a saga instance by its correlation_id and type."""
        coll = self._collection()
        doc = await coll.find_one(
            {
                "correlation_id": correlation_id,
                "saga_type": saga_type,
            }
        )
        return self._mapper.from_doc(doc) if doc else None

    async def find_stalled_sagas(
        self,
        limit: int = 10,
        *,
        specification: ISpecification[Any] | None = None,
    ) -> list[SagaState]:
        """Return sagas that are RUNNING but have stalled (beyond update threshold)."""
        threshold = datetime.now(timezone.utc) - timedelta(minutes=5)

        base_query = {
            "status": DomainSagaStatus.RUNNING.value,
            "updated_at": {"$lt": threshold},
            "saga_type": self.saga_type,
        }
        query = self._merge_spec(base_query, specification)

        cursor = self._collection().find(query).limit(limit)

        results = []
        async for doc in cursor:
            results.append(self._mapper.from_doc(doc))
        return results

    async def find_suspended_sagas(
        self,
        limit: int = 10,
        *,
        specification: ISpecification[Any] | None = None,
    ) -> list[SagaState]:
        """Return all currently suspended sagas."""
        base_query = {
            "status": DomainSagaStatus.SUSPENDED.value,
            "saga_type": self.saga_type,
        }
        query = self._merge_spec(base_query, specification)

        cursor = self._collection().find(query).limit(limit)

        results = []
        async for doc in cursor:
            results.append(self._mapper.from_doc(doc))
        return results

    async def find_expired_suspended_sagas(
        self,
        limit: int = 10,
        *,
        specification: ISpecification[Any] | None = None,
    ) -> list[SagaState]:
        """Return suspended sagas whose timeout_at has passed."""
        now = datetime.now(timezone.utc)

        base_query = {
            "status": DomainSagaStatus.SUSPENDED.value,
            "timeout_at": {"$lt": now},
            "saga_type": self.saga_type,
        }
        query = self._merge_spec(base_query, specification)

        cursor = self._collection().find(query).limit(limit)

        results = []
        async for doc in cursor:
            results.append(self._mapper.from_doc(doc))
        return results

    async def find_running_sagas_with_tcc_steps(
        self,
        limit: int = 10,
        *,
        specification: ISpecification[Any] | None = None,
    ) -> list[SagaState]:
        """Return RUNNING sagas that have TCC steps (state.tcc_steps non-empty)."""
        base_query = {
            "status": DomainSagaStatus.RUNNING.value,
            "tcc_steps": {"$exists": True, "$ne": []},
            "saga_type": self.saga_type,
        }
        query = self._merge_spec(base_query, specification)

        cursor = self._collection().find(query).limit(limit)

        results = []
        async for doc in cursor:
            results.append(self._mapper.from_doc(doc))
        return results
