"""Unit tests for string operators in MongoDB query builder."""

from __future__ import annotations

import pytest

from cqrs_ddd_persistence_mongo.exceptions import MongoQueryError
from cqrs_ddd_persistence_mongo.operators.string import _regex_escape, compile_string

# Phase 1, Step 4: String Operators Tests (12 tests)


class TestRegexEscape:
    """Tests for _regex_escape helper function."""

    def test_regex_escapes_special_chars(self):
        """Test that regex special characters are escaped."""
        assert _regex_escape("test.value") == r"test\.value"
        assert _regex_escape("test*value") == r"test\*value"
        assert _regex_escape("test+value") == r"test\+value"
        assert _regex_escape("test?value") == r"test\?value"
        assert _regex_escape("test^value") == r"test\^value"
        assert _regex_escape("test$value") == r"test\$value"
        assert _regex_escape("test|value") == r"test\|value"
        assert _regex_escape("test\\value") == r"test\\value"
        assert _regex_escape("test(value)") == r"test\(value\)"
        assert _regex_escape("test[value]") == r"test\[value\]"
        assert _regex_escape("test{value}") == r"test\{value\}"


class TestStringOperators:
    """Tests for string operator compilation."""

    def test_contains_operator(self):
        """Test CONTAINS operator."""
        result = compile_string("field", "contains", "test")
        assert result == {"field": {"$regex": "test", "$options": ""}}

    def test_icontains_operator(self):
        """Test ICONTAINS (case-insensitive contains) operator."""
        result = compile_string("field", "icontains", "test")
        assert result == {"field": {"$regex": "test", "$options": "i"}}

    def test_startswith_operator(self):
        """Test STARTSWITH operator."""
        result = compile_string("field", "startswith", "test")
        assert result == {"field": {"$regex": "^test", "$options": ""}}

    def test_istartswith_operator(self):
        """Test ISTARTSWITH (case-insensitive startswith) operator."""
        result = compile_string("field", "istartswith", "test")
        assert result == {"field": {"$regex": "^test", "$options": "i"}}

    def test_endswith_operator(self):
        """Test ENDSWITH operator."""
        result = compile_string("field", "endswith", "test")
        assert result == {"field": {"$regex": "test$", "$options": ""}}

    def test_iendswith_operator(self):
        """Test IENDSWITH (case-insensitive endswith) operator."""
        result = compile_string("field", "iendswith", "test")
        assert result == {"field": {"$regex": "test$", "$options": "i"}}

    def test_like_operator(self):
        """Test LIKE operator (SQL LIKE syntax)."""
        result = compile_string("field", "like", "test%")
        assert result == {"field": {"$regex": "^test.*$", "$options": ""}}

    def test_ilike_operator(self):
        """Test ILIKE (case-insensitive LIKE) operator."""
        result = compile_string("field", "ilike", "test%")
        assert result == {"field": {"$regex": "^test.*$", "$options": "i"}}

    def test_regex_operator(self):
        """Test REGEX operator."""
        result = compile_string("field", "regex", "^test\\d+$")
        assert result == {"field": {"$regex": "^test\\d+$", "$options": ""}}

    def test_iregex_operator(self):
        """Test IREGEX (case-insensitive regex) operator."""
        result = compile_string("field", "iregex", "^test\\d+$")
        assert result == {"field": {"$regex": "^test\\d+$", "$options": "i"}}

    def test_not_like_operator(self):
        """Test NOT_LIKE operator."""
        result = compile_string("field", "not_like", "test%")
        assert result == {"field": {"$not": {"$regex": "^test.*$"}}}

    def test_regex_escaping(self):
        """Test that regex patterns are properly escaped for non-REGEX operators."""
        # Special regex characters should be escaped for CONTAINS
        result = compile_string("field", "contains", "test.value")
        assert result == {"field": {"$regex": r"test\.value", "$options": ""}}

        # But NOT for REGEX operator
        result = compile_string("field", "regex", "test\\.value")
        assert result == {"field": {"$regex": r"test\.value", "$options": ""}}


class TestStringOperatorErrors:
    """Tests for error handling in string operators."""

    def test_string_operator_requires_string_value(self):
        """Test that string operators raise error for non-string values."""
        with pytest.raises(MongoQueryError, match="String operator"):
            compile_string("field", "contains", 123)

        with pytest.raises(MongoQueryError, match="String operator"):
            compile_string("field", "startswith", None)

    def test_unknown_operator_returns_none(self):
        """Test that unknown operators return None."""
        result = compile_string("field", "unknown_op", "test")
        assert result is None
