"""Unit tests for MongoQueryBuilder."""

from __future__ import annotations

from cqrs_ddd_persistence_mongo.query_builder import MongoQueryBuilder
from cqrs_ddd_specifications.ast import AttributeSpecification
from cqrs_ddd_specifications.base import AndSpecification, OrSpecification
from cqrs_ddd_specifications.operators import SpecificationOperator


def test_build_match_eq() -> None:
    qb = MongoQueryBuilder()
    spec = AttributeSpecification("status", SpecificationOperator.EQ, "active")
    m = qb.build_match(spec)
    assert m == {"status": {"$eq": "active"}}


def test_build_match_gt_gte() -> None:
    qb = MongoQueryBuilder()
    spec = AttributeSpecification("amount", SpecificationOperator.GE, 100)
    m = qb.build_match(spec)
    assert m == {"amount": {"$gte": 100}}


def test_build_match_in() -> None:
    qb = MongoQueryBuilder()
    spec = AttributeSpecification("status", SpecificationOperator.IN, ["a", "b"])
    m = qb.build_match(spec)
    assert m == {"status": {"$in": ["a", "b"]}}


def test_build_match_and() -> None:
    qb = MongoQueryBuilder()
    s1 = AttributeSpecification("status", SpecificationOperator.EQ, "active")
    s2 = AttributeSpecification("amount", SpecificationOperator.GE, 100)
    spec = AndSpecification(s1, s2)
    m = qb.build_match(spec)
    assert m == {"$and": [{"status": {"$eq": "active"}}, {"amount": {"$gte": 100}}]}


def test_build_match_or() -> None:
    qb = MongoQueryBuilder()
    s1 = AttributeSpecification("status", SpecificationOperator.EQ, "active")
    s2 = AttributeSpecification("status", SpecificationOperator.EQ, "pending")
    spec = OrSpecification(s1, s2)
    m = qb.build_match(spec)
    assert m == {"$or": [{"status": {"$eq": "active"}}, {"status": {"$eq": "pending"}}]}


def test_build_match_contains() -> None:
    qb = MongoQueryBuilder()
    spec = AttributeSpecification("name", SpecificationOperator.CONTAINS, "foo")
    m = qb.build_match(spec)
    assert "name" in m
    assert m["name"]["$regex"] == "foo"
    assert m["name"].get("$options") != "i"


def test_build_match_icontains() -> None:
    qb = MongoQueryBuilder()
    spec = AttributeSpecification("name", SpecificationOperator.ICONTAINS, "foo")
    m = qb.build_match(spec)
    assert m["name"].get("$options") == "i"


def test_build_match_dot_notation() -> None:
    qb = MongoQueryBuilder()
    spec = AttributeSpecification("address.city", SpecificationOperator.EQ, "Athens")
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
