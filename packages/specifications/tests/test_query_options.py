"""Tests for QueryOptions."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from cqrs_ddd_core.domain.aggregate import AggregateRoot
from cqrs_ddd_specifications import (
    AttributeSpecification,
    QueryOptions,
    SpecificationOperator,
)


class MockAggregate(AggregateRoot[UUID]):
    name: str
    age: int


def _name_eq(val: str) -> AttributeSpecification:
    return AttributeSpecification("name", SpecificationOperator.EQ, val)


# -- Construction -----------------------------------------------------------


def test_default_query_options():
    opts = QueryOptions()
    assert opts.specification is None
    assert opts.limit is None
    assert opts.offset is None
    assert opts.order_by == []
    assert opts.distinct is False
    assert opts.group_by == []
    assert opts.select_fields == []


def test_with_specification():
    spec = _name_eq("Alice")
    opts = QueryOptions().with_specification(spec)
    assert opts.specification is spec
    assert opts.limit is None  # unchanged


def test_with_pagination():
    opts = QueryOptions().with_pagination(limit=10, offset=20)
    assert opts.limit == 10
    assert opts.offset == 20
    assert opts.specification is None


def test_with_ordering():
    opts = QueryOptions().with_ordering("-created_at", "name")
    assert opts.order_by == ["-created_at", "name"]


# -- Merge ------------------------------------------------------------------


def test_merge_specifications_combined():
    spec_a = _name_eq("Alice")
    spec_b = _name_eq("Bob")
    opts_a = QueryOptions(specification=spec_a)
    opts_b = QueryOptions(specification=spec_b)

    merged = opts_a.merge(opts_b)
    # Combined via AND
    candidate_alice = MockAggregate(id=uuid4(), name="Alice", age=30)
    # Both specs can't match same name → AND = False
    assert merged.specification is not None
    assert merged.specification.is_satisfied_by(candidate_alice) is False


def test_merge_pagination_overrides():
    opts_a = QueryOptions(limit=5, offset=0)
    opts_b = QueryOptions(limit=10)
    merged = opts_a.merge(opts_b)
    assert merged.limit == 10
    assert merged.offset == 0  # kept from a


def test_merge_ordering_concatenates():
    opts_a = QueryOptions(order_by=["-created_at"])
    opts_b = QueryOptions(order_by=["name"])
    merged = opts_a.merge(opts_b)
    assert merged.order_by == ["-created_at", "name"]


def test_merge_distinct_or():
    opts_a = QueryOptions(distinct=False)
    opts_b = QueryOptions(distinct=True)
    assert opts_a.merge(opts_b).distinct is True


def test_merge_none_spec_keeps_existing():
    spec = _name_eq("Alice")
    opts_a = QueryOptions(specification=spec)
    opts_b = QueryOptions()
    merged = opts_a.merge(opts_b)
    assert merged.specification is spec


# -- Serialisation -----------------------------------------------------------


def test_to_dict_empty():
    assert QueryOptions().to_dict() == {}


def test_to_dict_full():
    spec = _name_eq("Alice")
    opts = QueryOptions(
        specification=spec,
        limit=10,
        offset=5,
        order_by=["-age"],
        distinct=True,
        group_by=["status"],
        select_fields=["name", "age"],
    )
    d = opts.to_dict()
    assert d["limit"] == 10
    assert d["offset"] == 5
    assert d["order_by"] == ["-age"]
    assert d["distinct"] is True
    assert d["group_by"] == ["status"]
    assert d["select_fields"] == ["name", "age"]
    assert d["specification"]["op"] == "="
    assert d["specification"]["attr"] == "name"


# -- Immutability ------------------------------------------------------------


def test_frozen():
    opts = QueryOptions(limit=5)
    with pytest.raises(AttributeError):
        opts.limit = 10  # type: ignore[misc]
