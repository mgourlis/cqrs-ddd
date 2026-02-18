"""
SQLAlchemy concrete bases for the advanced persistence dispatcher.

These abstract bases provide the SQLAlchemy session-aware scaffolding
for the four persistence roles:

- ``SQLAlchemyOperationPersistence``  — command-side writes
- ``SQLAlchemyRetrievalPersistence``  — command-side reads (aggregate retrieval)
- ``SQLAlchemyQueryPersistence``      — ID-based query-side reads
- ``SQLAlchemyQuerySpecificationPersistence`` — specification-based query reads

Each base resolves the ``AsyncSession`` from the UnitOfWork.  Write
and retrieval bases delegate mapping to a :class:`ModelMapper` instance
(DRY with ``SQLAlchemyRepository``).  Query bases require a subclass-
provided ``to_dto()`` hook.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm.exc import StaleDataError

from cqrs_ddd_advanced_core.ports.persistence import (
    IOperationPersistence,
    IQueryPersistence,
    IQuerySpecificationPersistence,
    IRetrievalPersistence,
)
from cqrs_ddd_core.domain.aggregate import AggregateRoot
from cqrs_ddd_core.ports.search_result import SearchResult

from ..core.model_mapper import ModelMapper
from ..core.uow import SQLAlchemyUnitOfWork
from ..exceptions import OptimisticConcurrencyError
from ..specifications.compiler import apply_query_options, build_sqla_filter

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from cqrs_ddd_core.domain.specification import ISpecification
    from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

T_Entity = TypeVar("T_Entity", bound=AggregateRoot[Any])
T_Result = TypeVar("T_Result")
T_ID = TypeVar("T_ID", str, int, UUID)


def _session_from(uow: UnitOfWork) -> AsyncSession:
    """Extract ``AsyncSession`` from a UnitOfWork, asserting SQLAlchemy type."""
    if not isinstance(uow, SQLAlchemyUnitOfWork):
        raise TypeError(f"Expected SQLAlchemyUnitOfWork, got {type(uow).__name__}")
    return uow.session


# ---------------------------------------------------------------------------
# Operation (Write) base
# ---------------------------------------------------------------------------


class SQLAlchemyOperationPersistence(
    IOperationPersistence[T_Entity, T_ID],
    Generic[T_Entity, T_ID],
):
    """
    Abstract base for persisting aggregate modifications via SQLAlchemy.

    Uses :class:`ModelMapper` for entity ↔ DB model conversion.
    Subclasses can override ``to_model`` / ``from_model`` for custom
    mapping (e.g. Saga state serialisation).
    """

    entity_cls: type[T_Entity]
    db_model_cls: type[Any]

    def __init__(
        self,
        entity_cls: type[T_Entity] | None = None,
        db_model_cls: type[Any] | None = None,
        *,
        relationship_depth: int = 0,
    ) -> None:
        if entity_cls is not None:
            self.entity_cls = entity_cls
        if db_model_cls is not None:
            self.db_model_cls = db_model_cls
        # Initialise mapper (requires entity_cls & db_model_cls to be set)
        self._mapper = ModelMapper(
            self.entity_cls,
            self.db_model_cls,
            relationship_depth=relationship_depth,
        )

    def to_model(self, entity: T_Entity) -> Any:
        """Convert domain aggregate → SQLAlchemy model."""
        return self._mapper.to_model(entity)

    def from_model(self, model: Any) -> T_Entity:
        """Convert SQLAlchemy model → domain aggregate."""
        return self._mapper.from_model(model)

    async def persist(
        self,
        entity: T_Entity,
        uow: UnitOfWork,
        events: Any = None,  # noqa: ARG002
    ) -> T_ID:
        """Persist the aggregate (events flow via middleware)."""
        session = _session_from(uow)
        model = self.to_model(entity)

        if entity.version == 0:
            if (
                hasattr(model, "__table__")
                and hasattr(model.__table__, "c")
                and "version" in model.__table__.c
            ):
                model.version = 1
            elif hasattr(model, "_version"):
                object.__setattr__(model, "_version", 1)
            session.add(model)
            if entity.id is None:
                await session.flush()
                if hasattr(model, "id"):
                    object.__setattr__(entity, "id", model.id)
            object.__setattr__(entity, "_version", 1)
        else:
            try:
                merged = await session.merge(model)
                if (
                    hasattr(merged, "__table__")
                    and hasattr(merged.__table__, "c")
                    and "version" in merged.__table__.c
                ):
                    merged.version = entity.version + 1
                object.__setattr__(entity, "_version", entity.version + 1)
                model = merged
            except StaleDataError as e:
                raise OptimisticConcurrencyError(
                    f"Aggregate {entity.id} version conflict. "
                    f"Expected version {entity.version} but was modified concurrently."
                ) from e

        return model.id  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Retrieval (command-side read) base
# ---------------------------------------------------------------------------


class SQLAlchemyRetrievalPersistence(
    IRetrievalPersistence[T_Entity, T_ID],
    Generic[T_Entity, T_ID],
):
    """
    Abstract base for retrieving aggregates by ID.

    Uses :class:`ModelMapper` for DB → domain conversion.
    """

    entity_cls: type[T_Entity]
    db_model_cls: type[Any]

    def __init__(
        self,
        entity_cls: type[T_Entity] | None = None,
        db_model_cls: type[Any] | None = None,
        *,
        relationship_depth: int = 0,
    ) -> None:
        if entity_cls is not None:
            self.entity_cls = entity_cls
        if db_model_cls is not None:
            self.db_model_cls = db_model_cls
        self._mapper = ModelMapper(
            self.entity_cls,
            self.db_model_cls,
            relationship_depth=relationship_depth,
        )

    def from_model(self, model: Any) -> T_Entity:
        """Convert SQLAlchemy model → domain aggregate."""
        return self._mapper.from_model(model)

    async def retrieve(self, ids: Sequence[T_ID], uow: UnitOfWork) -> list[T_Entity]:
        session = _session_from(uow)
        stmt = select(self.db_model_cls).where(self.db_model_cls.id.in_(ids))
        result = await session.execute(stmt)
        return [self.from_model(m) for m in result.scalars().all()]


# ---------------------------------------------------------------------------
# Query by ID (read-side) base
# ---------------------------------------------------------------------------


class SQLAlchemyQueryPersistence(
    IQueryPersistence[T_Result, T_ID],
    Generic[T_Result, T_ID],
):
    """
    Abstract base for fetching read-model DTOs by IDs.

    Subclasses must implement ``to_dto(model) -> T_Result``.
    """

    db_model_cls: type[Any]

    def __init__(self, db_model_cls: type[Any] | None = None) -> None:
        if db_model_cls is not None:
            self.db_model_cls = db_model_cls

    @abstractmethod
    def to_dto(self, model: Any) -> T_Result:
        """Convert a SQLAlchemy model instance to the result DTO."""
        ...

    async def fetch(self, ids: Sequence[T_ID], uow: UnitOfWork) -> list[T_Result]:
        session = _session_from(uow)
        stmt = select(self.db_model_cls).where(self.db_model_cls.id.in_(ids))
        result = await session.execute(stmt)
        return [self.to_dto(m) for m in result.scalars().all()]


# ---------------------------------------------------------------------------
# Query by Specification (read-side) base
# ---------------------------------------------------------------------------


class SQLAlchemyQuerySpecificationPersistence(
    IQuerySpecificationPersistence[T_Result],
    Generic[T_Result],
):
    """
    Abstract base for fetching read-model DTOs via specifications.

    ``fetch`` returns a :class:`SearchResult` — ``await`` for a list,
    or ``.stream()`` for an ``AsyncIterator``.

    Subclasses must implement ``to_dto(model) -> T_Result``.
    """

    db_model_cls: type[Any]

    def __init__(self, db_model_cls: type[Any] | None = None) -> None:
        if db_model_cls is not None:
            self.db_model_cls = db_model_cls

    @abstractmethod
    def to_dto(self, model: Any) -> T_Result:
        """Convert a SQLAlchemy model instance to the result DTO."""
        ...

    # -- normalise criteria -------------------------------------------------

    @staticmethod
    def _normalise_criteria(
        criteria: Any,
    ) -> tuple[Any | None, Any | None]:
        """Split criteria into (specification, query_options)."""
        if hasattr(criteria, "specification"):
            return getattr(criteria, "specification", None), criteria
        return criteria, None

    def _build_stmt(
        self,
        spec: Any | None,
        options: Any | None,
    ) -> Any:
        """Compile specification + query options into a Select statement."""
        stmt = select(self.db_model_cls)
        if spec is not None:
            spec_data = spec.to_dict()
            if spec_data:
                where_clause = build_sqla_filter(self.db_model_cls, spec_data)
                stmt = stmt.where(where_clause)
        if options is not None:
            stmt = apply_query_options(stmt, self.db_model_cls, options)
        return stmt

    # -- SearchResult API ---------------------------------------------------

    def fetch(
        self,
        criteria: ISpecification[Any] | Any,
        uow: UnitOfWork,
    ) -> SearchResult[T_Result]:
        spec, options = self._normalise_criteria(criteria)

        return SearchResult(
            list_fn=lambda: self._fetch_list(spec, options, uow),
            stream_fn=lambda batch_size: self._fetch_stream(
                spec,
                options,
                uow,
                batch_size=batch_size,
            ),
        )

    async def _fetch_list(
        self,
        spec: Any | None,
        options: Any | None,
        uow: UnitOfWork,
    ) -> list[T_Result]:
        session = _session_from(uow)
        stmt = self._build_stmt(spec, options)
        result = await session.execute(stmt)
        return [self.to_dto(m) for m in result.scalars().all()]

    async def _fetch_stream(
        self,
        spec: Any | None,
        options: Any | None,
        uow: UnitOfWork,
        *,
        batch_size: int | None = None,
    ) -> AsyncIterator[T_Result]:
        session = _session_from(uow)
        stmt = self._build_stmt(spec, options)
        effective_batch = batch_size or 100
        result = await session.stream_scalars(
            stmt.execution_options(yield_per=effective_batch)
        )
        async for model in result:
            yield self.to_dto(model)
