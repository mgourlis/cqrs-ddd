"""MongoDB implementation of Saga persistence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from cqrs_ddd_advanced_core.ports.saga_repository import ISagaRepository
from cqrs_ddd_advanced_core.sagas.state import SagaState
from cqrs_ddd_advanced_core.sagas.state import SagaStatus as DomainSagaStatus

from ..core.repository import MongoRepository

if TYPE_CHECKING:
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

    @property
    def saga_type(self) -> str:
        return self._saga_domain_cls.__name__

    async def find_by_correlation_id(
        self, correlation_id: str, saga_type: str
    ) -> SagaState | None:
        """Find a saga instance by its correlation_id and type."""
        coll = self._collection()
        doc = await coll.find_one({
            "correlation_id": correlation_id,
            "saga_type": saga_type,
        })
        return self._mapper.from_doc(doc) if doc else None

    async def find_stalled_sagas(self, limit: int = 10) -> list[SagaState]:
        """Return sagas that are RUNNING but have stalled (beyond update threshold)."""
        threshold = datetime.now(timezone.utc) - timedelta(minutes=5)

        cursor = self._collection().find({
            "status": DomainSagaStatus.RUNNING.value,
            "updated_at": {"$lt": threshold},
            "saga_type": self.saga_type,
        }).limit(limit)

        results = []
        async for doc in cursor:
            results.append(self._mapper.from_doc(doc))
        return results

    async def find_suspended_sagas(self, limit: int = 10) -> list[SagaState]:
        """Return all currently suspended sagas."""
        cursor = self._collection().find({
            "status": DomainSagaStatus.SUSPENDED.value,
            "saga_type": self.saga_type,
        }).limit(limit)

        results = []
        async for doc in cursor:
            results.append(self._mapper.from_doc(doc))
        return results

    async def find_expired_suspended_sagas(self, limit: int = 10) -> list[SagaState]:
        """Return suspended sagas whose timeout_at has passed."""
        now = datetime.now(timezone.utc)

        cursor = self._collection().find({
            "status": DomainSagaStatus.SUSPENDED.value,
            "timeout_at": {"$lt": now},
            "saga_type": self.saga_type,
        }).limit(limit)

        results = []
        async for doc in cursor:
            results.append(self._mapper.from_doc(doc))
        return results
