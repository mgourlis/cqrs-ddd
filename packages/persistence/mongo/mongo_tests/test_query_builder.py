"""Unit tests for MongoQueryBuilder."""

from __future__ import annotations

import pytest

from cqrs_ddd_persistence_mongo.query_builder import MongoQueryBuilder
from cqrs_ddd_specifications.ast import AttributeSpecification
from cqrs_ddd_specifications.base import AndSpecification, OrSpecification
from cqrs_ddd_specifications.operators import SpecificationOperator
from cqrs_ddd_specifications.operators_memory import build_default_registry


@pytest.fixture
def registry():
    return build_default_registry()


def test_build_match_eq(registry) -> None:
    qb = MongoQueryBuilder()
    spec = AttributeSpecification(
        "status", SpecificationOperator.EQ, "active", registry=registry
    )
    m = qb.build_match(spec)
    assert m == {"status": {"$eq": "active"}}


def test_build_match_gt_gte(registry) -> None:
    qb = MongoQueryBuilder()
    spec = AttributeSpecification(
        "amount", SpecificationOperator.GE, 100, registry=registry
    )
    m = qb.build_match(spec)
    assert m == {"amount": {"$gte": 100}}


def test_build_match_in(registry) -> None:
    qb = MongoQueryBuilder()
    spec = AttributeSpecification(
        "status", SpecificationOperator.IN, ["a", "b"], registry=registry
    )
    m = qb.build_match(spec)
    assert m == {"status": {"$in": ["a", "b"]}}


def test_build_match_and(registry) -> None:
    qb = MongoQueryBuilder()
    s1 = AttributeSpecification(
        "status", SpecificationOperator.EQ, "active", registry=registry
    )
    s2 = AttributeSpecification(
        "amount", SpecificationOperator.GE, 100, registry=registry
    )
    spec = AndSpecification(s1, s2)
    m = qb.build_match(spec)
    assert m == {"$and": [{"status": {"$eq": "active"}}, {"amount": {"$gte": 100}}]}


def test_build_match_or(registry) -> None:
    qb = MongoQueryBuilder()
    s1 = AttributeSpecification(
        "status", SpecificationOperator.EQ, "active", registry=registry
    )
    s2 = AttributeSpecification(
        "status", SpecificationOperator.EQ, "pending", registry=registry
    )
    spec = OrSpecification(s1, s2)
    m = qb.build_match(spec)
    assert m == {"$or": [{"status": {"$eq": "active"}}, {"status": {"$eq": "pending"}}]}


def test_build_match_contains(registry) -> None:
    qb = MongoQueryBuilder()
    spec = AttributeSpecification(
        "name", SpecificationOperator.CONTAINS, "foo", registry=registry
    )
    m = qb.build_match(spec)
    assert "name" in m
    assert m["name"]["$regex"] == "foo"
    assert m["name"].get("$options") != "i"


def test_build_match_icontains(registry) -> None:
    qb = MongoQueryBuilder()
    spec = AttributeSpecification(
        "name", SpecificationOperator.ICONTAINS, "foo", registry=registry
    )
    m = qb.build_match(spec)
    assert m["name"].get("$options") == "i"


def test_build_match_dot_notation(registry) -> None:
    qb = MongoQueryBuilder()
    spec = AttributeSpecification(
        "address.city", SpecificationOperator.EQ, "Athens", registry=registry
    )
    m = qb.build_match(spec)
    assert m == {"address.city": {"$eq": "Athens"}}


def test_build_match_from_dict() -> None:
    qb = MongoQueryBuilder()
    data = {"op": "=", "attr": "x", "val": 1}
    m = qb.build_match(data)
    assert m == {"x": {"$eq": 1}}


def test_build_sort_single_asc() -> None:
    qb = MongoQueryBuilder()
    out = qb.build_sort([("created_at", "asc")])
    assert out == [("created_at", 1)]


def test_build_sort_minus_prefix() -> None:
    qb = MongoQueryBuilder()
    out = qb.build_sort(["-created_at"])
    assert out == [("created_at", -1)]


def test_build_sort_empty() -> None:
    qb = MongoQueryBuilder()
    assert qb.build_sort(None) == []
    assert qb.build_sort([]) == []
