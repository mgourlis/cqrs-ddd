"""Unit tests for JSON/JSONB operators in MongoDB query builder."""

from __future__ import annotations

import pytest

from cqrs_ddd_persistence_mongo.operators.jsonb import compile_jsonb


# Phase 2, Step 7: JSON/JSONB Operators Tests (8 tests)


class TestJsonOperators:
    """Tests for JSON operator compilation."""

    def test_json_has_key(self):
        """Test JSON_HAS_KEY operator."""
        result = compile_jsonb("data.field", "json_has_key", "test")
        assert result == {"data.field": {"$exists": True, "$ne": None}}

    def test_json_has_any(self):
        """Test JSON_HAS_ANY operator."""
        # With list value
        result = compile_jsonb("tags", "json_has_any", ["tag1", "tag2"])
        assert result == {"tags": {"$in": ["tag1", "tag2"]}}

        # With single value (converted to list)
        result = compile_jsonb("tags", "json_has_any", "tag1")
        assert result == {"tags": {"$in": ["tag1"]}}

    def test_json_has_all(self):
        """Test JSON_HAS_ALL operator."""
        # With list value
        result = compile_jsonb("tags", "json_has_all", ["tag1", "tag2", "tag3"])
        assert result == {"tags": {"$all": ["tag1", "tag2", "tag3"]}}

        # With single value (converted to list)
        result = compile_jsonb("tags", "json_has_all", "tag1")
        assert result == {"tags": {"$all": ["tag1"]}}

    def test_json_contains(self):
        """Test JSON_CONTAINS operator."""
        # With array value (contains all elements)
        result = compile_jsonb("tags", "json_contains", ["tag1", "tag2"])
        assert result == {"tags": {"$all": ["tag1", "tag2"]}}

        # With single value (exact match)
        result = compile_jsonb("status", "json_contains", "active")
        assert result == {"status": {"$eq": "active"}}

    def test_json_path_exists(self):
        """Test JSON_PATH_EXISTS operator."""
        result = compile_jsonb("data.nested.field", "json_path_exists", None)
        assert result == {"data.nested.field": {"$exists": True}}

    def test_json_with_nested_path(self):
        """Test JSON operators with nested field paths."""
        result = compile_jsonb("user.profile.email", "json_has_key", "test")
        assert result == {"user.profile.email": {"$exists": True, "$ne": None}}

    def test_json_with_array(self):
        """Test JSON operators with array fields."""
        result = compile_jsonb("items.0.name", "json_has_key", "test")
        assert result == {"items.0.name": {"$exists": True, "$ne": None}}

    def test_json_with_null_value(self):
        """Test JSON operators with null values."""
        result = compile_jsonb("nullable_field", "json_has_key", None)
        # JSON_HAS_KEY checks $ne: None, so null values should not match
        assert result == {"nullable_field": {"$exists": True, "$ne": None}}


class TestJsonOperatorErrors:
    """Tests for error handling in JSON operators."""

    def test_unknown_json_operator_returns_none(self):
        """Test that unknown JSON operators return None."""
        result = compile_jsonb("field", "unknown_op", "test")
        assert result is None
