"""Unit tests for standard operators in MongoDB query builder."""

from __future__ import annotations

import pytest

from cqrs_ddd_persistence_mongo.exceptions import MongoQueryError
from cqrs_ddd_persistence_mongo.operators.standard import _validate_range_operand, compile_standard


# Phase 3, Step 10: Standard Operators Tests (4 tests)


class TestStandardOperators:
    """Tests for standard comparison operator compilation."""

    def test_between_operator(self):
        """Test BETWEEN operator."""
        result = compile_standard("value", "between", [10, 20])

        expected = {"$and": [{"value": {"$gte": 10}}, {"value": {"$lte": 20}}]}
        assert result == expected

    def test_not_between_operator(self):
        """Test NOT_BETWEEN operator."""
        result = compile_standard("value", "not_between", [10, 20])

        expected = {"$or": [{"value": {"$lt": 10}}, {"value": {"$gt": 20}}]}
        assert result == expected


class TestRangeValidation:
    """Tests for range operand validation."""

    def test_range_validation_with_valid_list(self):
        """Test range validation with valid list."""
        lo, hi = _validate_range_operand([10, 20], op_name="between")
        assert lo == 10
        assert hi == 20

    def test_range_validation_with_invalid_values(self):
        """Test range validation with invalid values."""
        # Not a list/tuple
        with pytest.raises(MongoQueryError, match="between requires a list"):
            _validate_range_operand(10, op_name="between")

        # Wrong length
        with pytest.raises(MongoQueryError, match="between requires a list"):
            _validate_range_operand([10], op_name="between")

        with pytest.raises(MongoQueryError, match="between requires a list"):
            _validate_range_operand([10, 20, 30], op_name="between")


class TestComparisonOperatorsComplete:
    """Tests for all standard comparison operators."""

    @pytest.mark.parametrize(
        "op,value,expected_mongo_op",
        [
            ("=", "test", "$eq"),
            ("!=", "test", "$ne"),
            (">", 10, "$gt"),
            (">=", 10, "$gte"),
            ("<", 10, "$lt"),
            ("<=", 10, "$lte"),
        ],
    )
    def test_comparison_operators_complete(self, op, value, expected_mongo_op):
        """Test that all standard comparison operators compile correctly."""
        result = compile_standard("field", op, value)

        assert result == {"field": {expected_mongo_op: value}}

    @pytest.mark.parametrize(
        "op,value",
        [
            ("in", ["val1", "val2"]),
            ("not_in", ["val1", "val2"]),
        ],
    )
    def test_in_not_in_operators(self, op, value):
        """Test IN and NOT_IN operators."""
        result = compile_standard("field", op, value)

        mongo_op = "$in" if op == "in" else "$nin"
        assert result == {"field": {mongo_op: value}}


class TestStandardOperatorErrors:
    """Tests for error handling in standard operators."""

    def test_unknown_standard_operator_returns_none(self):
        """Test that unknown standard operators return None."""
        result = compile_standard("field", "unknown_op", "test")
        assert result is None
