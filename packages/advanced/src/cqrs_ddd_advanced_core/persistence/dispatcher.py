"""
Refined Persistence Dispatcher with explicit Registry and ID_contra type safety.
Removes global state and provides injectable configuration.
"""

import logging
from collections.abc import AsyncIterator, Callable, Sequence
from typing import (
    Any,
    TypeVar,
    cast,
)

from cqrs_ddd_advanced_core.exceptions import (
    HandlerNotRegisteredError,
    SourceNotRegisteredError,
)
from cqrs_ddd_advanced_core.ports import (
    T_ID,
    IOperationPersistence,
    IQueryPersistence,
    IQuerySpecificationPersistence,
    IRetrievalPersistence,
    T_Criteria,
)
from cqrs_ddd_advanced_core.ports.dispatcher import IPersistenceDispatcher
from cqrs_ddd_core.domain.aggregate import AggregateRoot
from cqrs_ddd_core.domain.specification import ISpecification
from cqrs_ddd_core.ports.search_result import SearchResult
from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

logger = logging.getLogger("cqrs_ddd.persistence")

T_Entity = TypeVar("T_Entity", bound=AggregateRoot[Any])  # Aggregate Root type
T_Result = TypeVar("T_Result")  # Query result type


class PersistenceHandlerEntry:
    """Registry entry for a handler with source metadata and priority."""

    def __init__(
        self, handler_cls: type, source: str = "default", priority: int = 0
    ) -> None:
        self.handler_cls = handler_cls
        self.source = source
        self.priority = priority


class PersistenceRegistry:
    """
    Registry for persistence handlers.
    Holds mappings for operations, retrievals, and queries.
    """

    def __init__(self) -> None:
        # Indexed by Entity Type (for operations) or Result Type (for queries)
        self._operation_handlers: dict[type, list[PersistenceHandlerEntry]] = {}
        self._retrieval_handlers: dict[type, PersistenceHandlerEntry] = {}
        self._query_handlers: dict[type, PersistenceHandlerEntry] = {}
        self._query_spec_handlers: dict[type, PersistenceHandlerEntry] = {}

    def register_operation(
        self,
        entity_type: type[AggregateRoot[Any]],
        handler_cls: type[IOperationPersistence[Any, Any]],
        source: str = "default",
        priority: int = 0,
    ) -> None:
        """Register a prioritizable IOperationPersistence handler."""
        if entity_type not in self._operation_handlers:
            self._operation_handlers[entity_type] = []
        if any(
            e.handler_cls is handler_cls for e in self._operation_handlers[entity_type]
        ):
            return
        self._operation_handlers[entity_type].append(
            PersistenceHandlerEntry(handler_cls, source, priority)
        )
        self._operation_handlers[entity_type].sort(
            key=lambda e: e.priority, reverse=True
        )

    def register_retrieval(
        self,
        entity_type: type[AggregateRoot[Any]],
        handler_cls: type[IRetrievalPersistence[Any, Any]],
        source: str = "default",
    ) -> None:
        """Register a unique IRetrievalPersistence handler."""
        self._retrieval_handlers[entity_type] = PersistenceHandlerEntry(
            handler_cls, source
        )

    def register_query(
        self,
        result_type: type,
        handler_cls: type[IQueryPersistence[Any, Any]],
        source: str = "default",
    ) -> None:
        """Register a unique ID-based IQueryPersistence handler."""
        self._query_handlers[result_type] = PersistenceHandlerEntry(handler_cls, source)

    def register_query_spec(
        self,
        result_type: type,
        handler_cls: type[IQuerySpecificationPersistence[Any]],
        source: str = "default",
    ) -> None:
        """Register a Specification-based IQueryPersistence handler."""
        self._query_spec_handlers[result_type] = PersistenceHandlerEntry(
            handler_cls, source
        )

    def get_operation_entries(self, entity_type: type) -> list[PersistenceHandlerEntry]:
        return self._operation_handlers.get(entity_type, [])

    def get_retrieval_entry(self, entity_type: type) -> PersistenceHandlerEntry | None:
        return self._retrieval_handlers.get(entity_type)

    def get_query_entry(self, result_type: type) -> PersistenceHandlerEntry | None:
        return self._query_handlers.get(result_type)

    def get_query_spec_entry(self, result_type: type) -> PersistenceHandlerEntry | None:
        return self._query_spec_handlers.get(result_type)


class PersistenceDispatcher(IPersistenceDispatcher):
    """
    Unified dispatcher for command (modifications/retrieval) and query persistence.
    """

    def __init__(
        self,
        uow_factories: dict[str, Callable[[], UnitOfWork]],
        registry: PersistenceRegistry,
        handler_factory: Callable[[type], Any] | None = None,
    ) -> None:
        self._uow_factories = uow_factories
        self._registry = registry
        self._handler_factory = handler_factory or (lambda cls: cls())

    def _get_uow_factory(self, source: str) -> Callable[[], UnitOfWork]:
        factory = self._uow_factories.get(source)
        if not factory:
            raise SourceNotRegisteredError(
                f"No UnitOfWork factory registered for source '{source}'"
            )
        return factory

    async def apply(
        self,
        entity: AggregateRoot[T_ID],
        uow: UnitOfWork | None = None,
        events: list[Any] | None = None,
    ) -> T_ID:
        """
        Apply a write (persist entity, optionally with events).
        The handler is resolved based on the type of entity.
        """
        entity_type = type(entity)
        entries = self._registry.get_operation_entries(entity_type)
        if not entries:
            raise HandlerNotRegisteredError(
                f"No IOperationPersistence handler for entity {entity_type.__name__}"
            )

        # Use the highest priority handler
        entry = entries[0]
        # Cast to IOperationPersistence to satisfy mypy
        handler = cast(
            "IOperationPersistence[Any, T_ID]", self._handler_factory(entry.handler_cls)
        )

        if uow:
            return await handler.persist(entity, uow, events=events)

        async with self._get_uow_factory(entry.source)() as new_uow:
            return await handler.persist(entity, new_uow, events=events)

    async def fetch_domain(
        self,
        entity_type: type[T_Entity],
        ids: Sequence[T_ID],
        uow: UnitOfWork | None = None,
    ) -> list[T_Entity]:
        """Fetch domain entities by ID."""
        entry = self._registry.get_retrieval_entry(entity_type)
        if not entry:
            raise HandlerNotRegisteredError(
                f"No IRetrievalPersistence handler for {entity_type.__name__}"
            )

        handler = cast(
            "IRetrievalPersistence[T_Entity, T_ID]",
            self._handler_factory(entry.handler_cls),
        )

        if uow:
            return await handler.retrieve(ids, uow)

        async with self._get_uow_factory(entry.source)() as uow:
            return await handler.retrieve(ids, uow)

    async def fetch(
        self,
        result_type: type[T_Result],
        criteria: T_Criteria[Any],
        uow: UnitOfWork | None = None,
    ) -> SearchResult[T_Result]:
        """
        Fetch read models by criteria (IDs, ISpecification, or QueryOptions).

        Returns a :class:`SearchResult` that can be ``await``-ed for a
        ``list`` or ``.stream()``-ed for an ``AsyncIterator``.
        """
        # Determine whether criteria is a specification/QueryOptions or IDs
        is_spec = isinstance(criteria, ISpecification) or hasattr(
            criteria, "specification"
        )

        if is_spec:
            return await self._search_result_for_specification(
                result_type, criteria, uow
            )

        # ID-based query — ensure criteria is a Sequence
        if not isinstance(criteria, Sequence):
            criteria = [criteria]

        # ID-based query — stream uses batch size
        async def list_fn() -> list[T_Result]:
            return await self._fetch_by_ids(result_type, criteria, uow)

        async def stream_fn(batch_size: int | None) -> AsyncIterator[T_Result]:
            async for item in self._ids_as_stream(
                result_type, criteria, uow, batch_size
            ):
                yield item

        return SearchResult(list_fn=list_fn, stream_fn=stream_fn)

    # -- internal: spec-based SearchResult ----------------------------------

    async def _search_result_for_specification(
        self,
        result_type: type[T_Result],
        criteria: Any,
        uow: UnitOfWork | None,
    ) -> SearchResult[T_Result]:
        """Build a SearchResult backed by IQuerySpecificationPersistence."""
        entry = self._registry.get_query_spec_entry(result_type)
        if not entry:
            msg = (
                f"No Specification-based IQueryPersistence handler "
                f"for {result_type.__name__}"
            )
            raise HandlerNotRegisteredError(msg)

        handler = cast(
            "IQuerySpecificationPersistence[T_Result]",
            self._handler_factory(entry.handler_cls),
        )

        async def list_fn() -> list[T_Result]:
            if uow:
                return await handler.fetch(criteria, uow)
            async with self._get_uow_factory(entry.source)() as source_uow:
                return await handler.fetch(criteria, source_uow)

        async def stream_fn(batch_size: int | None) -> AsyncIterator[T_Result]:
            if uow:
                async for item in handler.fetch(criteria, uow).stream(
                    batch_size=batch_size
                ):
                    yield item
            else:
                raise ValueError(
                    "Streaming requires an explicit UnitOfWork to keep the "
                    "session alive for the duration of iteration."
                )

        return SearchResult(list_fn=list_fn, stream_fn=stream_fn)

    async def _ids_as_stream(
        self,
        result_type: type[T_Result],
        ids: Any,
        uow: UnitOfWork | None,
        batch_size: int | None = None,
    ) -> AsyncIterator[T_Result]:
        """Yield items from an ID-based fetch, respecting batch_size."""
        if batch_size and batch_size > 0 and isinstance(ids, Sequence):
            # Process in batches
            for i in range(0, len(ids), batch_size):
                batch = ids[i : i + batch_size]
                items = await self._fetch_by_ids(result_type, batch, uow)
                for item in items:
                    yield item
        else:
            # Fetch all at once
            items = await self._fetch_by_ids(result_type, ids, uow)
            for item in items:
                yield item

    async def _fetch_by_ids(
        self,
        result_type: type[T_Result],
        ids: Sequence[Any],
        uow: UnitOfWork | None = None,
    ) -> list[T_Result]:
        """Fetch read models by IDs."""
        entry = self._registry.get_query_entry(result_type)
        if not entry:
            raise HandlerNotRegisteredError(
                f"No ID-based IQueryPersistence handler for {result_type.__name__}"
            )

        handler = cast(
            "IQueryPersistence[T_Result, Any]", self._handler_factory(entry.handler_cls)
        )

        if uow:
            return await handler.fetch(ids, uow)

        async with self._get_uow_factory(entry.source)() as source_uow:
            return await handler.fetch(ids, source_uow)
