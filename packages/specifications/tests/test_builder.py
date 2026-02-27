"""Tests for the SpecificationBuilder fluent API."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from cqrs_ddd_core.domain.aggregate import AggregateRoot
from cqrs_ddd_specifications import (
    AndSpecification,
    AttributeSpecification,
    NotSpecification,
    OrSpecification,
    SpecificationBuilder,
    SpecificationOperator,
)


class MockAggregate(AggregateRoot[UUID]):
    name: str
    age: int
    status: str


@pytest.fixture
def builder(registry) -> SpecificationBuilder:
    return SpecificationBuilder(registry=registry)


@pytest.fixture
def alice() -> MockAggregate:
    return MockAggregate(id=uuid4(), name="Alice", age=28, status="active")


@pytest.fixture
def bob() -> MockAggregate:
    return MockAggregate(id=uuid4(), name="Bob", age=45, status="inactive")


# -- Single condition -------------------------------------------------------


def test_single_where(builder: SpecificationBuilder, alice: MockAggregate):
    spec = builder.where("name", "=", "Alice").build()
    assert isinstance(spec, AttributeSpecification)
    assert spec.is_satisfied_by(alice) is True


def test_single_where_string_op(builder: SpecificationBuilder, alice: MockAggregate):
    spec = builder.where("name", SpecificationOperator.CONTAINS, "lic").build()
    assert spec.is_satisfied_by(alice) is True


# -- Implicit AND ------------------------------------------------------------


def test_multiple_where_implicit_and(
    builder: SpecificationBuilder,
    alice: MockAggregate,
    bob: MockAggregate,
):
    spec = builder.where("name", "=", "Alice").where("age", "<", 30).build()
    assert isinstance(spec, AndSpecification)
    assert spec.is_satisfied_by(alice) is True
    assert spec.is_satisfied_by(bob) is False


# -- Explicit groups ---------------------------------------------------------


def test_or_group(
    builder: SpecificationBuilder,
    alice: MockAggregate,
    bob: MockAggregate,
):
    spec = (
        builder.or_group()
        .where("name", "=", "Alice")
        .where("name", "=", "Bob")
        .end_group()
        .build()
    )
    assert isinstance(spec, OrSpecification)
    assert spec.is_satisfied_by(alice) is True
    assert spec.is_satisfied_by(bob) is True


def test_and_group(
    builder: SpecificationBuilder,
    alice: MockAggregate,
    bob: MockAggregate,
):
    spec = (
        builder.and_group()
        .where("status", "=", "active")
        .where("age", "<", 35)
        .end_group()
        .build()
    )
    assert spec.is_satisfied_by(alice) is True
    assert spec.is_satisfied_by(bob) is False


def test_not_group(builder: SpecificationBuilder, alice: MockAggregate):
    spec = builder.not_group().where("status", "=", "inactive").end_group().build()
    assert isinstance(spec, NotSpecification)
    assert spec.is_satisfied_by(alice) is True


# -- Nesting -----------------------------------------------------------------


def test_nested_groups(
    builder: SpecificationBuilder,
    alice: MockAggregate,
    bob: MockAggregate,
):
    # (name = Alice AND age < 30)  OR  (status = inactive)
    spec = (
        builder.or_group()
        .and_group()
        .where("name", "=", "Alice")
        .where("age", "<", 30)
        .end_group()
        .and_group()
        .where("status", "=", "inactive")
        .end_group()
        .end_group()
        .build()
    )
    assert spec.is_satisfied_by(alice) is True
    assert spec.is_satisfied_by(bob) is True


# -- .add() -----------------------------------------------------------------


def test_add_existing_spec(
    builder: SpecificationBuilder, alice: MockAggregate, registry
):
    existing = AttributeSpecification(
        "age", SpecificationOperator.GT, 20, registry=registry
    )
    spec = builder.where("name", "=", "Alice").add(existing).build()
    assert isinstance(spec, AndSpecification)
    assert spec.is_satisfied_by(alice) is True


# -- .reset() ---------------------------------------------------------------


def test_reset(builder: SpecificationBuilder, alice: MockAggregate):
    builder.where("name", "=", "Bob")
    builder.reset()
    spec = builder.where("name", "=", "Alice").build()
    assert spec.is_satisfied_by(alice) is True


# -- Edge cases---------------------------------------------------------------


def test_build_empty_raises(builder: SpecificationBuilder):
    with pytest.raises(ValueError, match="No conditions"):
        builder.build()


def test_end_group_on_root_raises(builder: SpecificationBuilder):
    with pytest.raises(ValueError, match="No open group"):
        builder.end_group()


def test_build_with_unclosed_group_raises(builder: SpecificationBuilder):
    builder.or_group().where("name", "=", "Alice")
    with pytest.raises(ValueError, match="still open"):
        builder.build()


# -- serialisation round-trip ------------------------------------------------


def test_to_dict_round_trip(builder: SpecificationBuilder):
    spec = builder.where("name", "=", "Alice").where("age", ">", 20).build()
    d = spec.to_dict()
    assert d["op"] == "and"
    assert len(d["conditions"]) == 2
