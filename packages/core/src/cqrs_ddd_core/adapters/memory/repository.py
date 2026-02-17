"""InMemoryRepository — dict-backed fake for unit tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from cqrs_ddd_core.domain.aggregate import ID, AggregateRoot
from cqrs_ddd_core.ports.repository import IRepository
from cqrs_ddd_core.ports.search_result import SearchResult

if TYPE_CHECKING:
    import builtins
    from collections.abc import AsyncIterator

    from cqrs_ddd_core.domain.specification import ISpecification
    from cqrs_ddd_core.ports.unit_of_work import UnitOfWork


class InMemoryRepository(IRepository[Any, ID]):
    """In-memory implementation of ``IRepository[T, ID]``.

    Stores aggregates in a plain dict keyed by their ``id``.
    """

    def __init__(self) -> None:
        self._store: dict[ID, AggregateRoot[ID]] = {}

    async def add(
        self, entity: AggregateRoot[ID], _uow: UnitOfWork | None = None
    ) -> ID:
        self._store[entity.id] = entity
        return entity.id

    async def get(
        self,
        entity_id: ID,
        uow: UnitOfWork | None = None,  # noqa: ARG002
    ) -> AggregateRoot[ID] | None:
        return self._store.get(entity_id)

    async def delete(
        self,
        entity_id: ID,
        uow: UnitOfWork | None = None,  # noqa: ARG002
    ) -> ID:
        self._store.pop(entity_id, None)
        return entity_id

    async def list_all(
        self,
        entity_ids: list[ID] | None = None,
        uow: UnitOfWork | None = None,  # noqa: ARG002
    ) -> builtins.list[AggregateRoot[ID]]:
        if entity_ids is None:
            return list(self._store.values())
        return [
            entity
            for entity_id, entity in self._store.items()
            if entity_id in entity_ids
        ]

    async def search(
        self,
        specification: ISpecification[AggregateRoot[ID]],
        uow: UnitOfWork | None = None,  # noqa: ARG002
    ) -> SearchResult[AggregateRoot[ID]]:
        """Search for entities matching the specification (in-memory filtering)."""

        async def list_fn() -> list[AggregateRoot[ID]]:
            return [
                entity
                for entity in self._store.values()
                if specification.is_satisfied_by(entity)
            ]

        def stream_fn(batch_size: int | None) -> AsyncIterator[AggregateRoot[ID]]:
            async def gen() -> AsyncIterator[AggregateRoot[ID]]:
                items = await list_fn()
                batch = batch_size or len(items) or 1
                for i in range(0, len(items), batch):
                    for item in items[i : i + batch]:
                        yield item

            return gen()

        return SearchResult(list_fn=list_fn, stream_fn=stream_fn)

    # ── Test helpers ─────────────────────────────────────────────

    def clear(self) -> None:
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)
