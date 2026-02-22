"""Unit tests for set operators in MongoDB query builder."""

from __future__ import annotations

import pytest

from cqrs_ddd_persistence_mongo.operators.set import compile_set


# Phase 3, Step 9: Set Operators Tests (5 tests)


class TestSetOperators:
    """Tests for set operator compilation."""

    def test_all_operator(self):
        """Test ALL operator."""
        # With list value
        result = compile_set("tags", "all", ["tag1", "tag2"])
        assert result == {"tags": {"$all": ["tag1", "tag2"]}}

        # With single value (converted to list)
        result = compile_set("tags", "all", "tag1")
        assert result == {"tags": {"$all": ["tag1"]}}

    def test_in_operator(self):
        """Test IN operator."""
        # With list value
        result = compile_set("status", "in", ["active", "pending"])
        assert result == {"status": {"$in": ["active", "pending"]}}

        # With single value (converted to list)
        result = compile_set("status", "in", "active")
        assert result == {"status": {"$in": ["active"]}}

    def test_not_in_operator(self):
        """Test NOT_IN operator."""
        # With list value
        result = compile_set("status", "not_in", ["deleted", "archived"])
        assert result == {"status": {"$nin": ["deleted", "archived"]}}

        # With single value (converted to list)
        result = compile_set("status", "not_in", "deleted")
        assert result == {"status": {"$nin": ["deleted"]}}

    def test_set_with_single_value(self):
        """Test set operators with single value (should convert to list)."""
        # ALL with single value
        result1 = compile_set("tags", "all", "single")
        assert result1 == {"tags": {"$all": ["single"]}}

        # IN with single value
        result2 = compile_set("category", "in", "tech")
        assert result2 == {"category": {"$in": ["tech"]}}

    def test_set_with_list(self):
        """Test set operators with list values."""
        # ALL with multiple values
        result1 = compile_set("tags", "all", ["tag1", "tag2", "tag3"])
        assert result1 == {"tags": {"$all": ["tag1", "tag2", "tag3"]}}

        # IN with multiple values
        result2 = compile_set("status", "in", ["status1", "status2", "status3"])
        assert result2 == {"status": {"$in": ["status1", "status2", "status3"]}}

        # NOT_IN with multiple values
        result3 = compile_set("type", "not_in", ["type1", "type2"])
        assert result3 == {"type": {"$nin": ["type1", "type2"]}}


class TestSetOperatorErrors:
    """Tests for error handling in set operators."""

    def test_unknown_set_operator_returns_none(self):
        """Test that unknown set operators return None."""
        result = compile_set("field", "unknown_op", ["value"])
        assert result is None
