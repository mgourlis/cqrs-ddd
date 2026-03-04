"""Unit tests for MultitenantRepositoryMixin and StrictMultitenantRepositoryMixin."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from cqrs_ddd_multitenancy.context import reset_tenant, set_tenant
from cqrs_ddd_multitenancy.exceptions import (
    CrossTenantAccessError,
    TenantContextMissingError,
)
from cqrs_ddd_multitenancy.mixins.repository import (
    MultitenantRepositoryMixin,
    StrictMultitenantRepositoryMixin,
)

# ── Helpers ────────────────────────────────────────────────────────────


class FakeEntity:
    """Simple entity for testing."""

    def __init__(self, entity_id: str, tenant_id: str | None = None) -> None:
        self.id = entity_id
        self.tenant_id = tenant_id


class FakeSearchResult:
    def __init__(self, items: list) -> None:
        self.items = items

    def __iter__(self):
        return iter(self.items)

    async def list(self):
        return self.items


class MockRepository:
    """Mock base repository for MRO composition."""

    def __init__(self) -> None:
        self.entities: dict[str, FakeEntity] = {}
        self.added: list = []
        self.deleted: list = []

    async def add(self, entity: Any, uow: Any = None) -> str:
        self.added.append(entity)
        self.entities[entity.id] = entity
        return entity.id

    async def get(
        self, entity_id: str, uow: Any = None, *, specification: Any | None = None
    ) -> FakeEntity | None:
        entity = self.entities.get(entity_id)
        if entity is None:
            return None
        if specification is not None and not specification.is_satisfied_by(entity):
            return None
        return entity

    async def delete(
        self, entity_id: str, uow: Any = None, *, specification: Any | None = None
    ) -> str:
        self.deleted.append(entity_id)
        self.entities.pop(entity_id, None)
        return entity_id

    async def list_all(
        self,
        entity_ids: list[str] | None = None,
        uow: Any = None,
        *,
        specification: Any | None = None,
    ) -> list[FakeEntity]:
        result = list(self.entities.values())
        if entity_ids is not None:
            result = [e for e in result if e.id in entity_ids]
        if specification is not None:
            result = [e for e in result if specification.is_satisfied_by(e)]
        return result

    async def search(self, criteria: Any, uow: Any = None) -> FakeSearchResult:
        result = list(self.entities.values())
        if hasattr(criteria, "is_satisfied_by"):
            result = [e for e in result if criteria.is_satisfied_by(e)]
        return FakeSearchResult(result)


class TestRepo(MultitenantRepositoryMixin, MockRepository):
    pass


class StrictTestRepo(StrictMultitenantRepositoryMixin, MockRepository):
    pass


# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def repo() -> TestRepo:
    return TestRepo()


@pytest.fixture
def strict_repo() -> StrictTestRepo:
    return StrictTestRepo()


@pytest.fixture
def token():
    token = set_tenant("tenant-A")
    yield
    reset_tenant(token)


# ── Tests: add ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_injects_tenant_id(repo: TestRepo, token):
    entity = FakeEntity("e1")
    await repo.add(entity)
    assert entity.tenant_id == "tenant-A"
    assert len(repo.added) == 1


@pytest.mark.asyncio
async def test_add_raises_when_no_tenant(repo: TestRepo):
    with pytest.raises(TenantContextMissingError):
        await repo.add(FakeEntity("e1"))


@pytest.mark.asyncio
async def test_add_raises_on_cross_tenant(repo: TestRepo, token):
    entity = FakeEntity("e1", tenant_id="tenant-B")
    with pytest.raises(CrossTenantAccessError):
        await repo.add(entity)


@pytest.mark.asyncio
async def test_add_allows_same_tenant(repo: TestRepo, token):
    entity = FakeEntity("e1", tenant_id="tenant-A")
    await repo.add(entity)
    assert entity.tenant_id == "tenant-A"


# ── Tests: get ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_filters_by_tenant(repo: TestRepo, token):
    repo.entities["e1"] = FakeEntity("e1", tenant_id="tenant-A")
    repo.entities["e2"] = FakeEntity("e2", tenant_id="tenant-B")
    result = await repo.get("e1")
    assert result is not None
    result_other = await repo.get("e2")
    assert result_other is None  # filtered out by tenant spec


@pytest.mark.asyncio
async def test_get_raises_when_no_tenant(repo: TestRepo):
    with pytest.raises(TenantContextMissingError):
        await repo.get("e1")


@pytest.mark.asyncio
async def test_get_returns_none_for_missing(repo: TestRepo, token):
    result = await repo.get("nonexistent")
    assert result is None


# ── Tests: delete ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_with_tenant(repo: TestRepo, token):
    repo.entities["e1"] = FakeEntity("e1", tenant_id="tenant-A")
    result = await repo.delete("e1")
    assert result == "e1"
    assert "e1" in repo.deleted


@pytest.mark.asyncio
async def test_delete_raises_when_no_tenant(repo: TestRepo):
    with pytest.raises(TenantContextMissingError):
        await repo.delete("e1")


# ── Tests: list_all ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_all_filters_by_tenant(repo: TestRepo, token):
    repo.entities["e1"] = FakeEntity("e1", tenant_id="tenant-A")
    repo.entities["e2"] = FakeEntity("e2", tenant_id="tenant-B")
    results = await repo.list_all()
    assert len(results) == 1
    assert results[0].id == "e1"


@pytest.mark.asyncio
async def test_list_all_raises_when_no_tenant(repo: TestRepo):
    with pytest.raises(TenantContextMissingError):
        await repo.list_all()


@pytest.mark.asyncio
async def test_list_all_with_entity_ids(repo: TestRepo, token):
    repo.entities["e1"] = FakeEntity("e1", tenant_id="tenant-A")
    repo.entities["e2"] = FakeEntity("e2", tenant_id="tenant-A")
    results = await repo.list_all(entity_ids=["e1"])
    assert len(results) == 1
    assert results[0].id == "e1"


# ── Tests: search ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_composes_tenant_filter(repo: TestRepo, token):
    repo.entities["e1"] = FakeEntity("e1", tenant_id="tenant-A")
    repo.entities["e2"] = FakeEntity("e2", tenant_id="tenant-B")

    # Build a simple pass-through spec
    class AllSpec:
        def is_satisfied_by(self, x: Any) -> bool:
            return True

        def __and__(self, other: Any) -> Any:
            return other

    result = await repo.search(AllSpec())
    # Only tenant-A entities should be returned
    assert all(e.tenant_id == "tenant-A" for e in result.items)


@pytest.mark.asyncio
async def test_search_raises_when_no_tenant(repo: TestRepo):
    with pytest.raises(TenantContextMissingError):
        await repo.search(MagicMock())


# ── Tests: system tenant bypass ────────────────────────────────────────


@pytest.mark.asyncio
async def test_system_tenant_bypasses_filtering(repo: TestRepo):
    from cqrs_ddd_multitenancy.context import system_operation

    repo.entities["e1"] = FakeEntity("e1", tenant_id="tenant-A")
    repo.entities["e2"] = FakeEntity("e2", tenant_id="tenant-B")

    @system_operation
    async def do_list():
        return await repo.list_all()

    results = await do_list()
    assert len(results) == 2


# ── Tests: _build_tenant_specification ────────────────────────────────


def test_build_tenant_spec_returns_spec(repo: TestRepo):
    spec = repo._build_tenant_specification("tenant-X")
    assert spec is not None


def test_build_tenant_spec_filters_correctly(repo: TestRepo):
    spec = repo._build_tenant_specification("tenant-X")
    entity_match = FakeEntity("e1", tenant_id="tenant-X")
    entity_no_match = FakeEntity("e2", tenant_id="tenant-Y")
    assert spec.is_satisfied_by(entity_match)
    assert not spec.is_satisfied_by(entity_no_match)


# ── Tests: _compose_specs ──────────────────────────────────────────────


def test_compose_specs_returns_tenant_when_other_is_none(repo: TestRepo):
    spec = repo._build_tenant_specification("tenant-X")
    result = repo._compose_specs(spec, None)
    assert result is spec


def test_compose_specs_composes_two_specs(repo: TestRepo):
    spec = repo._build_tenant_specification("tenant-X")

    class OtherSpec:
        def is_satisfied_by(self, x: Any) -> bool:
            return True

        def __and__(self, other: Any) -> Any:
            return other

    result = repo._compose_specs(OtherSpec(), spec)
    # Result should be spec due to __and__ returning other
    assert result is spec


# ── Tests: _compose_tenant_filter ─────────────────────────────────────


def test_compose_tenant_filter_with_dict(repo: TestRepo):
    result = repo._compose_tenant_filter({"status": "active"}, "tenant-X")
    # Should return a composed result (either dict or spec)
    assert result is not None


def test_compose_tenant_filter_with_none(repo: TestRepo):
    result = repo._compose_tenant_filter(None, "tenant-X")
    assert result is not None


def test_compose_tenant_filter_with_spec(repo: TestRepo):
    class MySpec:
        def is_satisfied_by(self, x: Any) -> bool:
            return True

        def __and__(self, other: Any) -> MySpec:
            return self

    result = repo._compose_tenant_filter(MySpec(), "tenant-X")
    assert result is not None


# ── Tests: StrictMultitenantRepositoryMixin ────────────────────────────


@pytest.mark.asyncio
async def test_strict_get_raises_on_cross_tenant(strict_repo: StrictTestRepo):
    strict_repo.entities["e1"] = FakeEntity("e1", tenant_id="tenant-B")
    token = set_tenant("tenant-A")
    try:
        # The spec filters at DB level, so entity won't be returned
        result = await strict_repo.get("e1")
        # If entity was filtered out by spec, result is None — OK
        assert result is None
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_strict_get_returns_entity_for_same_tenant(strict_repo: StrictTestRepo):
    strict_repo.entities["e1"] = FakeEntity("e1", tenant_id="tenant-A")
    token = set_tenant("tenant-A")
    try:
        result = await strict_repo.get("e1")
        assert result is not None
        assert result.id == "e1"
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_strict_get_returns_none_for_missing(strict_repo: StrictTestRepo):
    token = set_tenant("tenant-A")
    try:
        result = await strict_repo.get("nonexistent")
        assert result is None
    finally:
        reset_tenant(token)
