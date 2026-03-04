from uuid import UUID, uuid4

import pytest

from cqrs_ddd_core.domain.aggregate import AggregateRoot
from cqrs_ddd_specifications import (
    AttributeSpecification,
    SpecificationFactory,
    SpecificationOperator,
)


class MockAggregate(AggregateRoot[UUID]):
    name: str
    age: int
    status: str


@pytest.fixture
def candidate() -> MockAggregate:
    return MockAggregate(id=uuid4(), name="John Doe", age=30, status="active")


def test_attribute_specification_eq(candidate: MockAggregate, registry):
    spec = AttributeSpecification(
        "name", SpecificationOperator.EQ, "John Doe", registry=registry
    )
    assert spec.is_satisfied_by(candidate) is True

    spec = AttributeSpecification(
        "name", SpecificationOperator.EQ, "Jane Doe", registry=registry
    )
    assert spec.is_satisfied_by(candidate) is False


def test_attribute_specification_string_ops(candidate: MockAggregate, registry):
    # ILIKE
    spec = AttributeSpecification(
        "name", SpecificationOperator.ILIKE, "john%", registry=registry
    )
    assert spec.is_satisfied_by(candidate) is True

    # CONTAINS
    spec = AttributeSpecification(
        "name", SpecificationOperator.CONTAINS, "Doe", registry=registry
    )
    assert spec.is_satisfied_by(candidate) is True

    # ICONTAINS
    spec = AttributeSpecification(
        "name", SpecificationOperator.ICONTAINS, "doe", registry=registry
    )
    assert spec.is_satisfied_by(candidate) is True

    # STARTSWITH
    spec = AttributeSpecification(
        "name", SpecificationOperator.STARTSWITH, "John", registry=registry
    )
    assert spec.is_satisfied_by(candidate) is True

    # REGEX
    spec = AttributeSpecification(
        "name", SpecificationOperator.REGEX, r"J\w+ D\w+", registry=registry
    )
    assert spec.is_satisfied_by(candidate) is True


def test_attribute_specification_between(candidate: MockAggregate, registry):
    spec = AttributeSpecification(
        "age", SpecificationOperator.BETWEEN, [25, 35], registry=registry
    )
    assert spec.is_satisfied_by(candidate) is True

    spec = AttributeSpecification(
        "age", SpecificationOperator.BETWEEN, [35, 45], registry=registry
    )
    assert spec.is_satisfied_by(candidate) is False


def test_attribute_specification_null_checks(candidate: MockAggregate, registry):
    spec = AttributeSpecification(
        "status", SpecificationOperator.IS_NOT_NULL, None, registry=registry
    )
    assert spec.is_satisfied_by(candidate) is True

    spec = AttributeSpecification(
        "status", SpecificationOperator.IS_NULL, None, registry=registry
    )
    assert spec.is_satisfied_by(candidate) is False


def test_attribute_specification_gt(candidate: MockAggregate, registry):
    spec = AttributeSpecification(
        "age", SpecificationOperator.GT, 25, registry=registry
    )
    assert spec.is_satisfied_by(candidate) is True

    spec = AttributeSpecification(
        "age", SpecificationOperator.GT, 35, registry=registry
    )
    assert spec.is_satisfied_by(candidate) is False


def test_composite_specification_and(candidate: MockAggregate, registry):
    name_spec = AttributeSpecification(
        "name", SpecificationOperator.EQ, "John Doe", registry=registry
    )
    age_spec = AttributeSpecification(
        "age", SpecificationOperator.GT, 25, registry=registry
    )

    and_spec = name_spec & age_spec
    assert and_spec.is_satisfied_by(candidate) is True

    wrong_name_spec = AttributeSpecification(
        "name", SpecificationOperator.EQ, "Jane Doe", registry=registry
    )
    fail_and_spec = wrong_name_spec & age_spec
    assert fail_and_spec.is_satisfied_by(candidate) is False


def test_composite_specification_or(candidate: MockAggregate, registry):
    name_spec = AttributeSpecification(
        "name", SpecificationOperator.EQ, "John Doe", registry=registry
    )
    wrong_name_spec = AttributeSpecification(
        "name", SpecificationOperator.EQ, "Jane Doe", registry=registry
    )

    or_spec = name_spec | wrong_name_spec
    assert or_spec.is_satisfied_by(candidate) is True


def test_specification_factory_from_dict(registry):
    data = {
        "op": "and",
        "conditions": [
            {"op": "=", "attr": "name", "val": "John Doe"},
            {"op": ">", "attr": "age", "val": 25},
        ],
    }
    spec = SpecificationFactory.from_dict(data, registry=registry)

    candidate = MockAggregate(id=uuid4(), name="John Doe", age=30, status="active")
    assert spec.is_satisfied_by(candidate) is True

    assert spec.to_dict() == data
