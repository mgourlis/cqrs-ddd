"""Tests for the enhanced SpecificationFactory (validation, from_json, value_type)."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest

from cqrs_ddd_core.domain.aggregate import AggregateRoot
from cqrs_ddd_specifications import (
    SpecificationFactory,
)
from cqrs_ddd_specifications.exceptions import (
    OperatorNotFoundError,
    ValidationError,
)


class MockAggregate(AggregateRoot[UUID]):
    name: str
    age: int
    status: str


@pytest.fixture
def candidate() -> MockAggregate:
    return MockAggregate(id=uuid4(), name="Alice", age=28, status="active")


# -- from_json ---------------------------------------------------------------


def test_from_json_basic(candidate: MockAggregate, registry):
    payload = json.dumps({"op": "=", "attr": "name", "val": "Alice"})
    spec = SpecificationFactory.from_json(payload, registry=registry)
    assert spec.is_satisfied_by(candidate) is True


def test_from_json_invalid_json(registry):
    with pytest.raises(ValidationError, match="Invalid JSON"):
        SpecificationFactory.from_json("not json {", registry=registry)


def test_from_json_non_object(registry):
    with pytest.raises(ValidationError, match="object"):
        SpecificationFactory.from_json('"just a string"', registry=registry)


# -- from_dict with validation -----------------------------------------------


def test_from_dict_missing_op(registry):
    with pytest.raises(ValidationError, match="op"):
        SpecificationFactory.from_dict({}, registry=registry)


def test_from_dict_unknown_operator(registry):
    with pytest.raises(OperatorNotFoundError):
        SpecificationFactory.from_dict(
            {"op": "invalid_op", "attr": "name", "val": "x"}, registry=registry
        )


def test_from_dict_missing_attr(registry):
    with pytest.raises(ValidationError, match="attr"):
        SpecificationFactory.from_dict({"op": "=", "val": "x"}, registry=registry)


def test_from_dict_logical_missing_conditions(registry):
    with pytest.raises(ValidationError, match="conditions"):
        SpecificationFactory.from_dict({"op": "and"}, registry=registry)


def test_from_dict_nested_validation_error(registry):
    with pytest.raises((ValidationError, OperatorNotFoundError)):
        SpecificationFactory.from_dict(
            {
                "op": "and",
                "conditions": [
                    {"op": "=", "attr": "name", "val": "Alice"},
                    {"op": "???", "attr": "age", "val": 10},  # bad op
                ],
            },
            registry=registry,
        )


# -- allowed_fields ----------------------------------------------------------


def test_from_dict_allowed_fields_pass(candidate: MockAggregate, registry):
    spec = SpecificationFactory.from_dict(
        {"op": "=", "attr": "name", "val": "Alice"},
        allowed_fields=["name", "age"],
        registry=registry,
    )
    assert spec.is_satisfied_by(candidate) is True


def test_from_dict_allowed_fields_reject(registry):
    with pytest.raises(ValidationError, match="not in the allowed"):
        SpecificationFactory.from_dict(
            {"op": "=", "attr": "secret_field", "val": "x"},
            allowed_fields=["name", "age"],
            registry=registry,
        )


# -- value_type casting -------------------------------------------------------


def test_value_type_int(candidate: MockAggregate, registry):
    spec = SpecificationFactory.from_dict(
        {"op": ">", "attr": "age", "val": "20", "value_type": "int"},
        registry=registry,
    )
    assert spec.is_satisfied_by(candidate) is True


def test_value_type_bool(registry):
    class FlagAggregate(AggregateRoot[UUID]):
        active: bool

    agg = FlagAggregate(id=uuid4(), active=True)
    spec = SpecificationFactory.from_dict(
        {"op": "=", "attr": "active", "val": "true", "value_type": "bool"},
        registry=registry,
    )
    assert spec.is_satisfied_by(agg) is True


# -- validate() non-throwing -------------------------------------------------


def test_validate_valid():
    errors = SpecificationFactory.validate(
        {
            "op": "and",
            "conditions": [
                {"op": "=", "attr": "name", "val": "Alice"},
            ],
        }
    )
    assert errors == []


def test_validate_returns_errors():
    errors = SpecificationFactory.validate(
        {
            "op": "and",
            "conditions": [
                {"op": "="},  # missing attr
            ],
        }
    )
    assert len(errors) == 1
    assert "attr" in errors[0].lower()


def test_validate_multiple_errors():
    errors = SpecificationFactory.validate(
        {
            "op": "and",
            "conditions": [
                {"op": "invalid_op", "attr": "x", "val": 1},
                {"op": "="},  # missing attr
            ],
        }
    )
    assert len(errors) == 2


# -- NOT with "condition" key ------------------------------------------------


def test_not_with_condition_key(candidate: MockAggregate, registry):
    spec = SpecificationFactory.from_dict(
        {
            "op": "not",
            "condition": {"op": "=", "attr": "name", "val": "Bob"},
        },
        registry=registry,
    )
    assert spec.is_satisfied_by(candidate) is True


# -- round-trip serialisation -------------------------------------------------


def test_round_trip_nested(candidate: MockAggregate, registry):
    original = {
        "op": "and",
        "conditions": [
            {"op": "=", "attr": "name", "val": "Alice"},
            {
                "op": "or",
                "conditions": [
                    {"op": ">", "attr": "age", "val": 20},
                    {"op": "=", "attr": "status", "val": "vip"},
                ],
            },
        ],
    }
    spec = SpecificationFactory.from_dict(original, registry=registry)
    rebuilt = spec.to_dict()
    assert rebuilt == original
    assert spec.is_satisfied_by(candidate) is True
