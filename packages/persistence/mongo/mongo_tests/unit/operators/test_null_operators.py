"""Unit tests for null/empty operators in MongoDB query builder."""

from __future__ import annotations

import pytest

from cqrs_ddd_persistence_mongo.operators.null import compile_null


# Phase 3, Step 8: Null/Empty Operators Tests (6 tests)


class TestNullOperators:
    """Tests for null operator compilation."""

    def test_is_null(self):
        """Test IS_NULL operator."""
        result = compile_null("field", "is_null", None)

        # Should check for either non-existent or None values
        expected = {
            "$or": [
                {"field": {"$exists": False}},
                {"field": {"$eq": None}},
            ]
        }
        assert result == expected

    def test_is_not_null(self):
        """Test IS_NOT_NULL operator."""
        result = compile_null("field", "is_not_null", None)

        expected = {"field": {"$exists": True, "$ne": None}}
        assert result == expected

    def test_is_empty_string(self):
        """Test IS_EMPTY operator for string fields."""
        result = compile_null("name", "is_empty", None)

        # Should check for: non-existent, None, empty string, or empty array
        expected = {
            "$or": [
                {"name": {"$exists": False}},
                {"name": {"$eq": None}},
                {"name": {"$eq": ""}},
                {"name": {"$size": 0}},
            ]
        }
        assert result == expected

    def test_is_not_empty_string(self):
        """Test IS_NOT_EMPTY operator for string fields."""
        result = compile_null("name", "is_not_empty", None)

        # Should check for: exists, not None, not empty string
        expected = {
            "$and": [
                {"name": {"$exists": True}},
                {"name": {"$ne": None}},
                {"name": {"$ne": ""}},
            ]
        }
        assert result == expected

    def test_is_empty_array(self):
        """Test IS_EMPTY operator for array fields."""
        result = compile_null("tags", "is_empty", None)

        # Should check for: non-existent, None, empty string, or empty array
        expected = {
            "$or": [
                {"tags": {"$exists": False}},
                {"tags": {"$eq": None}},
                {"tags": {"$eq": ""}},
                {"tags": {"$size": 0}},
            ]
        }
        assert result == expected

    def test_is_not_empty_array(self):
        """Test IS_NOT_EMPTY operator for array fields."""
        result = compile_null("tags", "is_not_empty", None)

        # Should check for: exists, not None, not empty string
        # (Note: doesn't check array size > 0, but MongoDB will filter empty arrays)
        expected = {
            "$and": [
                {"tags": {"$exists": True}},
                {"tags": {"$ne": None}},
                {"tags": {"$ne": ""}},
            ]
        }
        assert result == expected


class TestNullOperatorErrors:
    """Tests for error handling in null operators."""

    def test_unknown_null_operator_returns_none(self):
        """Test that unknown null operators return None."""
        result = compile_null("field", "unknown_op", None)
        assert result is None
