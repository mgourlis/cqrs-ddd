from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Sequence
from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast
from uuid import UUID

from sqlalchemy import delete, select

from cqrs_ddd_core.domain.aggregate import AggregateRoot
from cqrs_ddd_core.ports.repository import IRepository
from cqrs_ddd_core.ports.search_result import SearchResult

if TYPE_CHECKING:
    from cqrs_ddd_core.domain.specification import ISpecification
    from cqrs_ddd_core.ports.unit_of_work import UnitOfWork
    from cqrs_ddd_specifications.hooks import ResolutionHook

from sqlalchemy.orm.exc import StaleDataError

from cqrs_ddd_core.primitives.exceptions import OptimisticConcurrencyError

from ..specifications.compiler import apply_query_options, build_sqla_filter
from .model_mapper import ModelMapper
from .uow import SQLAlchemyUnitOfWork
from .versioning import set_version_after_merge, set_version_for_insert

ID = TypeVar("ID", str, int, UUID)
T = TypeVar("T", bound=AggregateRoot[Any])
UnitOfWorkFactory = Callable[[], SQLAlchemyUnitOfWork]


class SQLAlchemyRepository(IRepository[T, ID], Generic[T, ID]):
    """
    Implementation of IRepository using SQLAlchemy.

    Separates the domain entity type (``entity_cls``, a Pydantic
    ``AggregateRoot``) from the persistence model (``db_model_cls``, a
    SQLAlchemy ``DeclarativeBase`` subclass).

    Mapping between the two is handled by a :class:`ModelMapper` instance,
    exposed via ``to_model`` / ``from_model`` (still overridable by
    subclasses such as ``SQLAlchemySagaRepository``).

    The ``search`` method accepts ``ISpecification[T]`` or ``QueryOptions``
    and returns a :class:`SearchResult[T]` — ``await`` for a ``list`` or
    ``.stream()`` for an ``AsyncIterator``::

        result = await repo.search(spec)
        items = await result
        async for item in (await repo.search(spec)).stream(batch_size=100):
            ...

    Supports two UoW patterns:

    1. **Per-call UoW** (recommended):
       ``await repo.add(entity, uow=uow)``

    2. **Factory-injected UoW**:
       ``SQLAlchemyRepository(Order, OrderModel, uow_factory=factory)``
    """

    def __init__(
        self,
        entity_cls: type[T],
        db_model_cls: type[Any] | None = None,
        uow_factory: UnitOfWorkFactory | None = None,
        *,
        hooks: Sequence[ResolutionHook] | None = None,
        relationship_depth: int = 0,
    ) -> None:
        self.entity_cls = entity_cls
        self.db_model_cls = db_model_cls or entity_cls
        self._uow_factory = uow_factory
        self._hooks = hooks or []
        self._mapper = ModelMapper(
            entity_cls,
            self.db_model_cls,
            relationship_depth=relationship_depth,
        )

    # -- UoW helpers --------------------------------------------------------

    def _get_active_uow(
        self, uow: UnitOfWork | None = None
    ) -> SQLAlchemyUnitOfWork | None:
        if uow is not None:
            return cast("SQLAlchemyUnitOfWork", uow)
        if self._uow_factory is not None:
            return self._uow_factory()
        return None

    def _require_uow(self, uow: UnitOfWork | None = None) -> SQLAlchemyUnitOfWork:
        active = self._get_active_uow(uow)
        if active is None:
            raise ValueError("No UnitOfWork provided or configured.")
        return active

    # -- mapping (delegates to ModelMapper, overridable) --------------------

    def to_model(self, entity: T) -> Any:
        """Convert domain entity → SQLAlchemy model."""
        return self._mapper.to_model(entity)

    def from_model(self, model: Any) -> T:
        """Convert SQLAlchemy model → domain entity."""
        return self._mapper.from_model(model)

    # -- CRUD ---------------------------------------------------------------

    async def add(self, entity: T, uow: UnitOfWork | None = None) -> ID:
        active_uow = self._require_uow(uow)
        model = self.to_model(entity)

        if entity.version == 0:
            set_version_for_insert(model)
            active_uow.session.add(model)
            if entity.id is None:
                await active_uow.session.flush()
                if hasattr(entity, "id") and hasattr(model, "id"):
                    object.__setattr__(entity, "id", model.id)
            object.__setattr__(entity, "_version", 1)
        else:
            try:
                merged = await active_uow.session.merge(model)
                set_version_after_merge(merged, entity)
                model = merged
            except StaleDataError as e:
                raise OptimisticConcurrencyError(
                    f"Aggregate {entity.id} version conflict. "
                    f"Expected version {entity.version} but was modified concurrently."
                ) from e

        return model.id  # type: ignore[no-any-return]

    async def get(self, entity_id: Any, uow: UnitOfWork | None = None) -> T | None:
        active_uow = self._require_uow(uow)
        model = await active_uow.session.get(self.db_model_cls, entity_id)
        if model is None:
            return None
        return self.from_model(model)

    async def delete(self, entity_id: Any, uow: UnitOfWork | None = None) -> ID:
        active_uow = self._require_uow(uow)
        await active_uow.session.execute(
            delete(self.db_model_cls).where(self.db_model_cls.id == entity_id)
        )
        return entity_id  # type: ignore[no-any-return]

    async def list_all(
        self,
        entity_ids: list[Any] | None = None,
        uow: UnitOfWork | None = None,
    ) -> list[T]:
        active_uow = self._require_uow(uow)
        query = select(self.db_model_cls)
        if entity_ids is not None:
            query = query.where(self.db_model_cls.id.in_(entity_ids))
        result = await active_uow.session.execute(query)
        return [self.from_model(m) for m in result.scalars().all()]

    # -- unified search -----------------------------------------------------

    async def search(
        self,
        criteria: ISpecification[T] | Any,
        uow: UnitOfWork | None = None,
    ) -> SearchResult[T]:
        """
        Search for aggregates matching a specification or QueryOptions.

        Returns a :class:`SearchResult[T]`:

        - ``result = await repo.search(spec); items = await result``
        - ``result = await repo.search(spec); async for item in result.stream(
            batch_size=100
        ): ...``
        """
        spec, options = self._normalise_criteria(criteria)

        return SearchResult(
            list_fn=lambda: self._execute_search(spec, options, uow),
            stream_fn=lambda batch_size: self._execute_stream(
                spec,
                options,
                uow,
                batch_size=batch_size,
            ),
        )

    # -- internal search implementation -------------------------------------

    @staticmethod
    def _normalise_criteria(
        criteria: Any,
    ) -> tuple[Any | None, Any | None]:
        """
        Normalise *criteria* into ``(specification, query_options)``.

        - ``ISpecification`` → ``(spec, None)``
        - ``QueryOptions``   → ``(options.specification, options)``
        """
        if hasattr(criteria, "specification"):
            # It's a QueryOptions
            return getattr(criteria, "specification", None), criteria
        # It's a bare ISpecification
        return criteria, None

    async def _execute_search(
        self,
        spec: Any | None,
        options: Any | None,
        uow: UnitOfWork | None,
    ) -> list[T]:
        """Run the query and return a list of domain entities."""
        active_uow = self._require_uow(uow)

        query = select(self.db_model_cls)

        # Apply specification filter
        if spec is not None:
            spec_data = spec.to_dict()
            if spec_data:
                where_clause = build_sqla_filter(
                    self.db_model_cls,
                    spec_data,
                    hooks=self._hooks,
                )
                query = query.where(where_clause)

        # Apply query options (ordering, pagination, distinct, group_by)
        if options is not None:
            query = apply_query_options(query, self.db_model_cls, options)

        result = await active_uow.session.execute(query)
        models = list(result.scalars().all())

        aggregates = [self.from_model(m) for m in models]

        # In-memory post-filter for correctness (only when spec present)
        if spec is not None and hasattr(spec, "is_satisfied_by"):
            return [a for a in aggregates if spec.is_satisfied_by(a)]
        return aggregates

    async def _execute_stream(
        self,
        spec: Any | None,
        options: Any | None,
        uow: UnitOfWork | None,
        *,
        batch_size: int | None = None,
    ) -> AsyncIterator[T]:
        """Stream entities matching the query."""
        active_uow = self._require_uow(uow)

        query = select(self.db_model_cls)

        if spec is not None:
            spec_data = spec.to_dict()
            if spec_data:
                where_clause = build_sqla_filter(
                    self.db_model_cls,
                    spec_data,
                    hooks=self._hooks,
                )
                query = query.where(where_clause)

        if options is not None:
            query = apply_query_options(query, self.db_model_cls, options)

        effective_batch = batch_size or 100
        result = await active_uow.session.stream_scalars(
            query.execution_options(yield_per=effective_batch)
        )

        async for model in result:
            entity = self.from_model(model)
            if spec is not None and hasattr(spec, "is_satisfied_by"):
                if spec.is_satisfied_by(entity):
                    yield entity
            else:
                yield entity
