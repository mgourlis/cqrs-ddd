"""Tests for BaseSpecification.merge() and NOT specification."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from cqrs_ddd_core.domain.aggregate import AggregateRoot
from cqrs_ddd_specifications import (
    AndSpecification,
    AttributeSpecification,
    NotSpecification,
    SpecificationOperator,
)


class MockAggregate(AggregateRoot[UUID]):
    name: str
    age: int
    status: str


@pytest.fixture
def alice() -> MockAggregate:
    return MockAggregate(id=uuid4(), name="Alice", age=28, status="active")


@pytest.fixture
def bob() -> MockAggregate:
    return MockAggregate(id=uuid4(), name="Bob", age=45, status="inactive")


# -- merge -------------------------------------------------------------------


def test_merge_creates_and(alice: MockAggregate, registry):
    spec_a = AttributeSpecification(
        "name", SpecificationOperator.EQ, "Alice", registry=registry
    )
    spec_b = AttributeSpecification(
        "age", SpecificationOperator.GT, 20, registry=registry
    )

    merged = spec_a.merge(spec_b)
    assert isinstance(merged, AndSpecification)
    assert merged.is_satisfied_by(alice) is True


def test_merge_fails_when_one_doesnt_match(alice: MockAggregate, registry):
    spec_a = AttributeSpecification(
        "name", SpecificationOperator.EQ, "Alice", registry=registry
    )
    spec_b = AttributeSpecification(
        "age", SpecificationOperator.GT, 30, registry=registry
    )

    merged = spec_a.merge(spec_b)
    assert merged.is_satisfied_by(alice) is False


def test_merge_chainable(alice: MockAggregate, registry):
    spec = (
        AttributeSpecification(
            "name", SpecificationOperator.EQ, "Alice", registry=registry
        )
        .merge(
            AttributeSpecification(
                "age", SpecificationOperator.GT, 20, registry=registry
            )
        )
        .merge(
            AttributeSpecification(
                "status", SpecificationOperator.EQ, "active", registry=registry
            )
        )
    )
    assert spec.is_satisfied_by(alice) is True


# -- NOT specification -------------------------------------------------------


def test_not_inverts(alice: MockAggregate, bob: MockAggregate, registry):
    spec = ~AttributeSpecification(
        "status", SpecificationOperator.EQ, "active", registry=registry
    )
    assert isinstance(spec, NotSpecification)
    assert spec.is_satisfied_by(alice) is False
    assert spec.is_satisfied_by(bob) is True


def test_not_serialisation(registry):
    spec = ~AttributeSpecification(
        "name", SpecificationOperator.EQ, "Alice", registry=registry
    )
    d = spec.to_dict()
    assert d["op"] == "not"
    assert len(d["conditions"]) == 1
    assert d["conditions"][0]["op"] == "="


# -- complex composition-----------------------------------------------------


def test_complex_composition(alice: MockAggregate, bob: MockAggregate, registry):
    # (name = Alice) OR NOT(status = inactive)
    spec = AttributeSpecification(
        "name", SpecificationOperator.EQ, "Alice", registry=registry
    ) | ~AttributeSpecification(
        "status", SpecificationOperator.EQ, "inactive", registry=registry
    )
    assert spec.is_satisfied_by(alice) is True  # name match + not inactive
    assert spec.is_satisfied_by(bob) is False  # name != Alice AND status = inactive


# -- JSON operators (in-memory) ----------------------------------------------


def test_json_contains_dict(registry):
    class DocAggregate(AggregateRoot[UUID]):
        data: dict

    agg = DocAggregate(id=uuid4(), data={"a": 1, "b": 2, "c": 3})
    spec = AttributeSpecification(
        "data", SpecificationOperator.JSON_CONTAINS, {"a": 1}, registry=registry
    )
    assert spec.is_satisfied_by(agg) is True


def test_json_has_key(registry):
    class DocAggregate(AggregateRoot[UUID]):
        data: dict

    agg = DocAggregate(id=uuid4(), data={"name": "test", "value": 42})
    spec = AttributeSpecification(
        "data", SpecificationOperator.JSON_HAS_KEY, "name", registry=registry
    )
    assert spec.is_satisfied_by(agg) is True
    spec2 = AttributeSpecification(
        "data", SpecificationOperator.JSON_HAS_KEY, "missing", registry=registry
    )
    assert spec2.is_satisfied_by(agg) is False


# -- Set operators -----------------------------------------------------------


def test_in_operator(alice: MockAggregate, registry):
    spec = AttributeSpecification(
        "name", SpecificationOperator.IN, ["Alice", "Carol"], registry=registry
    )
    assert spec.is_satisfied_by(alice) is True


def test_not_in_operator(alice: MockAggregate, registry):
    spec = AttributeSpecification(
        "name", SpecificationOperator.NOT_IN, ["Bob", "Carol"], registry=registry
    )
    assert spec.is_satisfied_by(alice) is True


def test_not_between(alice: MockAggregate, registry):
    spec = AttributeSpecification(
        "age", SpecificationOperator.NOT_BETWEEN, [10, 20], registry=registry
    )
    assert spec.is_satisfied_by(alice) is True

    spec2 = AttributeSpecification(
        "age", SpecificationOperator.NOT_BETWEEN, [25, 35], registry=registry
    )
    assert spec2.is_satisfied_by(alice) is False


# -- Null / empty operators --------------------------------------------------


def test_is_empty(registry):
    class ListAggregate(AggregateRoot[UUID]):
        items: list

    agg = ListAggregate(id=uuid4(), items=[])
    spec = AttributeSpecification(
        "items", SpecificationOperator.IS_EMPTY, None, registry=registry
    )
    assert spec.is_satisfied_by(agg) is True


def test_is_not_empty(registry):
    class ListAggregate(AggregateRoot[UUID]):
        items: list

    agg = ListAggregate(id=uuid4(), items=[1, 2])
    spec = AttributeSpecification(
        "items", SpecificationOperator.IS_NOT_EMPTY, None, registry=registry
    )
    assert spec.is_satisfied_by(agg) is True
