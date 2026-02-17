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


def test_attribute_specification_eq(candidate: MockAggregate):
    spec = AttributeSpecification("name", SpecificationOperator.EQ, "John Doe")
    assert spec.is_satisfied_by(candidate) is True

    spec = AttributeSpecification("name", SpecificationOperator.EQ, "Jane Doe")
    assert spec.is_satisfied_by(candidate) is False


def test_attribute_specification_string_ops(candidate: MockAggregate):
    # ILIKE
    spec = AttributeSpecification("name", SpecificationOperator.ILIKE, "john%")
    assert spec.is_satisfied_by(candidate) is True

    # CONTAINS
    spec = AttributeSpecification("name", SpecificationOperator.CONTAINS, "Doe")
    assert spec.is_satisfied_by(candidate) is True

    # ICONTAINS
    spec = AttributeSpecification("name", SpecificationOperator.ICONTAINS, "doe")
    assert spec.is_satisfied_by(candidate) is True

    # STARTSWITH
    spec = AttributeSpecification("name", SpecificationOperator.STARTSWITH, "John")
    assert spec.is_satisfied_by(candidate) is True

    # REGEX
    spec = AttributeSpecification("name", SpecificationOperator.REGEX, r"J\w+ D\w+")
    assert spec.is_satisfied_by(candidate) is True


def test_attribute_specification_between(candidate: MockAggregate):
    spec = AttributeSpecification("age", SpecificationOperator.BETWEEN, [25, 35])
    assert spec.is_satisfied_by(candidate) is True

    spec = AttributeSpecification("age", SpecificationOperator.BETWEEN, [35, 45])
    assert spec.is_satisfied_by(candidate) is False


def test_attribute_specification_null_checks(candidate: MockAggregate):
    spec = AttributeSpecification("status", SpecificationOperator.IS_NOT_NULL, None)
    assert spec.is_satisfied_by(candidate) is True

    spec = AttributeSpecification("status", SpecificationOperator.IS_NULL, None)
    assert spec.is_satisfied_by(candidate) is False


def test_attribute_specification_gt(candidate: MockAggregate):
    spec = AttributeSpecification("age", SpecificationOperator.GT, 25)
    assert spec.is_satisfied_by(candidate) is True

    spec = AttributeSpecification("age", SpecificationOperator.GT, 35)
    assert spec.is_satisfied_by(candidate) is False


def test_composite_specification_and(candidate: MockAggregate):
    name_spec = AttributeSpecification("name", SpecificationOperator.EQ, "John Doe")
    age_spec = AttributeSpecification("age", SpecificationOperator.GT, 25)

    and_spec = name_spec & age_spec
    assert and_spec.is_satisfied_by(candidate) is True

    wrong_name_spec = AttributeSpecification(
        "name", SpecificationOperator.EQ, "Jane Doe"
    )
    fail_and_spec = wrong_name_spec & age_spec
    assert fail_and_spec.is_satisfied_by(candidate) is False


def test_composite_specification_or(candidate: MockAggregate):
    name_spec = AttributeSpecification("name", SpecificationOperator.EQ, "John Doe")
    wrong_name_spec = AttributeSpecification(
        "name", SpecificationOperator.EQ, "Jane Doe"
    )

    or_spec = name_spec | wrong_name_spec
    assert or_spec.is_satisfied_by(candidate) is True


def test_specification_factory_from_dict():
    data = {
        "op": "and",
        "conditions": [
            {"op": "=", "attr": "name", "val": "John Doe"},
            {"op": ">", "attr": "age", "val": 25},
        ],
    }
    spec = SpecificationFactory.from_dict(data)

    candidate = MockAggregate(id=uuid4(), name="John Doe", age=30, status="active")
    assert spec.is_satisfied_by(candidate) is True

    assert spec.to_dict() == data
