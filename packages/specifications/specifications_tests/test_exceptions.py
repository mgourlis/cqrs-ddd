"""Tests for exceptions module."""

from __future__ import annotations

from cqrs_ddd_specifications.exceptions import (
    FieldNotFoundError,
    FieldNotQueryableError,
    OperatorNotFoundError,
    RelationshipTraversalError,
    SpecificationError,
    ValidationError,
)

# -- OperatorNotFoundError ---------------------------------------------------


def test_operator_not_found_fuzzy_suggestion():
    err = OperatorNotFoundError(
        "contians",
        ["contains", "icontains", "startswith"],
    )
    assert "contians" in str(err)
    assert "contains" in str(err)  # fuzzy suggestion


def test_operator_not_found_no_matches():
    err = OperatorNotFoundError(
        "zzzzz",
        ["=", ">", "<"],
    )
    d = err.to_dict()
    assert d["error"] == "OPERATOR_NOT_FOUND"
    assert d["suggestions"] == []


def test_operator_not_found_to_dict():
    err = OperatorNotFoundError("eqq", ["eq", "ne", "gt"])
    d = err.to_dict()
    assert d["operator"] == "eqq"
    assert "eq" in d["suggestions"]


# -- FieldNotFoundError ------------------------------------------------------


def test_field_not_found_fuzzy():
    err = FieldNotFoundError(
        invalid_field="nme",
        model_name="UserModel",
        available_fields=["name", "age", "status"],
    )
    assert "nme" in str(err)
    assert "name" in str(err)  # fuzzy suggestion


def test_field_not_found_to_dict():
    err = FieldNotFoundError(
        invalid_field="emial",
        model_name="UserModel",
        available_fields=["email", "name"],
    )
    d = err.to_dict()
    assert d["field"] == "emial"
    assert "email" in d["suggestions"]


# -- ValidationError ---------------------------------------------------------


def test_validation_error_with_path():
    err = ValidationError("Missing 'attr'", path="<root>.conditions[0]")
    assert err.path == "<root>.conditions[0]"
    d = err.to_dict()
    assert d["path"] == "<root>.conditions[0]"


def test_validation_error_no_path():
    err = ValidationError("Something broke")
    d = err.to_dict()
    assert d["path"] is None


# -- RelationshipTraversalError -----------------------------------------------


def test_relationship_traversal_error():
    err = RelationshipTraversalError(
        field="product",
        model_name="Order",
        full_path="items.product.name",
    )
    assert "product" in str(err)
    assert "Order" in str(err)
    d = err.to_dict()
    assert d["field"] == "product"
    assert d["model"] == "Order"
    assert d["full_path"] == "items.product.name"


# -- FieldNotQueryableError --------------------------------------------------


def test_field_not_queryable():
    err = FieldNotQueryableError(
        field="password",
        model_name="User",
        available_fields=["name", "email"],
    )
    assert "password" in str(err)
    assert "not queryable" in str(err).lower()


# -- Hierarchy ---------------------------------------------------------------


def test_all_inherit_from_specification_error():
    assert issubclass(ValidationError, SpecificationError)
    assert issubclass(OperatorNotFoundError, SpecificationError)
    assert issubclass(FieldNotFoundError, SpecificationError)
    assert issubclass(RelationshipTraversalError, SpecificationError)
    assert issubclass(FieldNotQueryableError, SpecificationError)
