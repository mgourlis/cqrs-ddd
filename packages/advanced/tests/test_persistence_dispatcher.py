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
from cqrs_ddd_core.domain.aggregate import AggregateRoot, Modification
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
    async def persist(self, modification: Modification[Any], uow: UnitOfWork) -> Any:
        return modification.entity.id


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


@pytest.mark.asyncio()
async def test_dispatcher_apply_modification() -> None:
    registry = PersistenceRegistry()
    registry.register_operation(MockEntity, MockOperationPersistence)

    dispatcher = PersistenceDispatcher(
        uow_factories={"default": lambda: MockUoW()}, registry=registry
    )

    entity = MockEntity(id=uuid4(), name="Test")
    modification = Modification(entity)

    result = await dispatcher.apply(modification)
    assert result == entity.id


@pytest.mark.asyncio()
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


@pytest.mark.asyncio()
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


@pytest.mark.asyncio()
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


@pytest.mark.asyncio()
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
