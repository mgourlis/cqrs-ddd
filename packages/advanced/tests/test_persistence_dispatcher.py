from collections.abc import Sequence
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from cqrs_ddd_advanced_core.persistence.dispatcher import (
    PersistenceDispatcher,
    PersistenceRegistry,
)
from cqrs_ddd_advanced_core.ports import (
    IOperationPersistence,
    IQueryPersistence,
    IQuerySpecificationPersistence,
    IRetrievalPersistence,
)
from cqrs_ddd_core.domain.aggregate import AggregateRoot
from cqrs_ddd_core.domain.events import DomainEvent
from cqrs_ddd_core.domain.specification import ISpecification
from cqrs_ddd_core.ports.unit_of_work import UnitOfWork

# --- Mock Domain ---


class MockEntity(AggregateRoot[Any]):
    name: str


class MockEvent(DomainEvent):
    pass


class MockResult:
    def __init__(self, id: Any, name: str) -> None:
        self.id = id
        self.name = name


# --- Mock Persistence Handlers ---


class MockOperationPersistence(IOperationPersistence[MockEntity, Any]):
    async def persist(
        self,
        entity: MockEntity,
        uow: UnitOfWork,
        events: list[Any] | None = None,
    ) -> Any:
        return entity.id


class MockRetrievalPersistence(IRetrievalPersistence[MockEntity, Any]):
    async def retrieve(self, ids: Sequence[Any], uow: UnitOfWork) -> list[MockEntity]:
        return [MockEntity(id=eid, name="Mock") for eid in ids]


class MockQueryPersistence(IQueryPersistence[MockResult, Any]):
    async def fetch(self, ids: Sequence[Any], uow: UnitOfWork) -> list[MockResult]:
        return [MockResult(id=eid, name="Mock") for eid in ids]


class MockQuerySpecPersistence(IQuerySpecificationPersistence[MockResult]):
    async def fetch(
        self, specification: ISpecification, uow: UnitOfWork
    ) -> list[MockResult]:
        return [MockResult(id="spec", name="From Spec")]


# --- Mock UoW ---


class MockUoW(UnitOfWork):
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


# --- Tests ---


@pytest.mark.asyncio
async def test_dispatcher_apply_modification() -> None:
    registry = PersistenceRegistry()
    registry.register_operation(MockEntity, MockOperationPersistence)

    dispatcher = PersistenceDispatcher(
        uow_factories={"default": lambda: MockUoW()}, registry=registry
    )

    entity = MockEntity(id=uuid4(), name="Test")

    result = await dispatcher.apply(entity)
    assert result == entity.id


@pytest.mark.asyncio
async def test_dispatcher_multi_source_routing() -> None:
    uow_default = MagicMock(spec=MockUoW)
    uow_olap = MagicMock(spec=MockUoW)

    # Simple async mocks for context managers
    uow_default.__aenter__ = AsyncMock(return_value=uow_default)
    uow_default.__aexit__ = AsyncMock()
    uow_olap.__aenter__ = AsyncMock(return_value=uow_olap)
    uow_olap.__aexit__ = AsyncMock()

    registry = PersistenceRegistry()
    registry.register_retrieval(MockEntity, MockRetrievalPersistence, source="olap")

    dispatcher = PersistenceDispatcher(
        uow_factories={"default": lambda: uow_default, "olap": lambda: uow_olap},
        registry=registry,
    )

    entity_id = uuid4()
    await dispatcher.fetch_domain(MockEntity, [entity_id])

    # Verify olap UoW was used, not default
    uow_olap.__aenter__.assert_called()
    uow_default.__aenter__.assert_not_called()


@pytest.mark.asyncio
async def test_dispatcher_fetch_domain() -> None:
    registry = PersistenceRegistry()
    registry.register_retrieval(MockEntity, MockRetrievalPersistence)

    dispatcher = PersistenceDispatcher(
        uow_factories={"default": lambda: MockUoW()}, registry=registry
    )

    entity_id = uuid4()
    results = await dispatcher.fetch_domain(MockEntity, [entity_id])

    assert len(results) == 1
    assert results[0].id == entity_id


@pytest.mark.asyncio
async def test_dispatcher_fetch_query_with_ids() -> None:
    registry = PersistenceRegistry()
    registry.register_query(MockResult, MockQueryPersistence)

    dispatcher = PersistenceDispatcher(
        uow_factories={"default": lambda: MockUoW()}, registry=registry
    )

    ids = [uuid4()]
    search_result = await dispatcher.fetch(MockResult, ids)
    results = await search_result

    assert len(results) == 1
    assert results[0].id == ids[0]


@pytest.mark.asyncio
async def test_dispatcher_fetch_query_with_specification() -> None:
    registry = PersistenceRegistry()
    registry.register_query_spec(MockResult, MockQuerySpecPersistence)

    dispatcher = PersistenceDispatcher(
        uow_factories={"default": lambda: MockUoW()}, registry=registry
    )

    class MySpec(ISpecification):
        def is_satisfied_by(self, candidate: Any) -> bool:
            return True

        def to_dict(self) -> dict:
            return {}

    search_result = await dispatcher.fetch(MockResult, MySpec())
    results = await search_result

    assert len(results) == 1
    assert results[0].name == "From Spec"


@pytest.mark.asyncio
async def test_dispatcher_apply_with_explicit_uow() -> None:
    """apply() can use an explicit UoW instead of creating one."""
    registry = PersistenceRegistry()
    registry.register_operation(MockEntity, MockOperationPersistence)

    explicit_uow = MockUoW()
    dispatcher = PersistenceDispatcher(
        uow_factories={"default": lambda: MockUoW()}, registry=registry
    )

    entity = MockEntity(id=uuid4(), name="Test")

    result = await dispatcher.apply(entity, uow=explicit_uow)

    assert result == entity.id


@pytest.mark.asyncio
async def test_dispatcher_apply_missing_handler_raises_error() -> None:
    """apply() raises HandlerNotRegisteredError when no handler found."""
    from cqrs_ddd_advanced_core.exceptions import HandlerNotRegisteredError

    registry = PersistenceRegistry()
    # Don't register any handler

    dispatcher = PersistenceDispatcher(
        uow_factories={"default": lambda: MockUoW()}, registry=registry
    )

    entity = MockEntity(id=uuid4(), name="Test")

    with pytest.raises(HandlerNotRegisteredError):
        await dispatcher.apply(entity)


@pytest.mark.asyncio
async def test_dispatcher_fetch_domain_missing_handler_raises_error() -> None:
    """fetch_domain() raises HandlerNotRegisteredError when no handler found."""
    from cqrs_ddd_advanced_core.exceptions import HandlerNotRegisteredError

    registry = PersistenceRegistry()
    # Don't register any handler

    dispatcher = PersistenceDispatcher(
        uow_factories={"default": lambda: MockUoW()}, registry=registry
    )

    with pytest.raises(HandlerNotRegisteredError):
        await dispatcher.fetch_domain(MockEntity, [uuid4()])


@pytest.mark.asyncio
async def test_dispatcher_missing_source_raises_error() -> None:
    """Dispatcher raises SourceNotRegisteredError for unknown source."""
    from cqrs_ddd_advanced_core.exceptions import SourceNotRegisteredError

    registry = PersistenceRegistry()
    registry.register_retrieval(MockEntity, MockRetrievalPersistence, source="unknown")

    # Don't register 'unknown' source in uow_factories
    dispatcher = PersistenceDispatcher(
        uow_factories={"default": lambda: MockUoW()}, registry=registry
    )

    with pytest.raises(SourceNotRegisteredError):
        await dispatcher.fetch_domain(MockEntity, [uuid4()])


@pytest.mark.asyncio
async def test_dispatcher_fetch_id_based_streaming() -> None:
    """fetch() with IDs supports streaming with batch_size."""
    registry = PersistenceRegistry()
    registry.register_query(MockResult, MockQueryPersistence)

    dispatcher = PersistenceDispatcher(
        uow_factories={"default": lambda: MockUoW()}, registry=registry
    )

    ids = [uuid4(), uuid4(), uuid4()]
    search_result = await dispatcher.fetch(MockResult, ids)

    # Test streaming
    results = []
    async for item in search_result.stream(batch_size=2):
        results.append(item)

    assert len(results) == 3


@pytest.mark.asyncio
async def test_dispatcher_fetch_spec_build_search_result() -> None:
    """fetch() with specification builds SearchResult with list and stream."""
    registry = PersistenceRegistry()
    registry.register_query_spec(MockResult, MockQuerySpecPersistence)

    dispatcher = PersistenceDispatcher(
        uow_factories={"default": lambda: MockUoW()}, registry=registry
    )

    class MySpec(ISpecification):
        def is_satisfied_by(self, candidate: Any) -> bool:
            return True

        def to_dict(self) -> dict:
            return {}

    search_result = await dispatcher.fetch(MockResult, MySpec())

    # Test list mode
    results_list = await search_result
    assert len(results_list) == 1

    # Note: stream mode requires explicit UoW, so we skip testing it here


@pytest.mark.asyncio
async def test_dispatcher_fetch_query_missing_handler_raises_error() -> None:
    """fetch() raises HandlerNotRegisteredError when no query handler found."""
    from cqrs_ddd_advanced_core.exceptions import HandlerNotRegisteredError

    registry = PersistenceRegistry()
    # Don't register query handler

    dispatcher = PersistenceDispatcher(
        uow_factories={"default": lambda: MockUoW()}, registry=registry
    )

    # Need to await the SearchResult to trigger the error
    result = await dispatcher.fetch(MockResult, [uuid4()])
    with pytest.raises(HandlerNotRegisteredError):
        await result


@pytest.mark.asyncio
async def test_dispatcher_apply_uses_highest_priority_handler() -> None:
    """apply() uses the highest priority handler when multiple are registered."""
    registry = PersistenceRegistry()

    # Register two handlers with different priorities
    registry.register_operation(MockEntity, MockOperationPersistence, priority=1)

    class HighPriorityHandler:
        async def persist(
            self,
            entity: Any,
            uow: Any,
            events: list[Any] | None = None,
        ) -> Any:
            return "high_priority"

    registry.register_operation(MockEntity, HighPriorityHandler, priority=10)

    dispatcher = PersistenceDispatcher(
        uow_factories={"default": lambda: MockUoW()}, registry=registry
    )

    entity = MockEntity(id=uuid4(), name="Test")

    result = await dispatcher.apply(entity)

    # Should use high priority handler
    assert result == "high_priority"
