"""Tests for enhanced operator support (Tier 2 operators)."""

from __future__ import annotations

import pytest

from cqrs_ddd_filtering.exceptions import FilterParseError
from cqrs_ddd_filtering.syntax import ColonSeparatedSyntax, JsonFilterSyntax


class TestColonSeparatedNullOperators:
    """Test null check operators in colon syntax."""

    def test_is_null_operator(self) -> None:
        syntax = ColonSeparatedSyntax()
        result = syntax.parse_filter("deleted_at:is_null:true")
        assert result["op"] == "is_null"
        assert result["attr"] == "deleted_at"
        assert result["val"] is True

    def test_is_null_shorthand(self) -> None:
        syntax = ColonSeparatedSyntax()
        result = syntax.parse_filter("deleted_at:null:true")
        assert result["op"] == "is_null"

    def test_is_not_null_operator(self) -> None:
        syntax = ColonSeparatedSyntax()
        result = syntax.parse_filter("email:is_not_null:true")
        assert result["op"] == "is_not_null"
        assert result["attr"] == "email"

    def test_is_not_null_shorthand(self) -> None:
        syntax = ColonSeparatedSyntax()
        result = syntax.parse_filter("email:not_null:true")
        assert result["op"] == "is_not_null"


class TestColonSeparatedStringOperators:
    """Test string matching operators in colon syntax."""

    def test_startswith_operator(self) -> None:
        syntax = ColonSeparatedSyntax()
        result = syntax.parse_filter("name:startswith:John")
        assert result["op"] == "startswith"
        assert result["attr"] == "name"
        assert result["val"] == "John"

    def test_starts_with_alias(self) -> None:
        syntax = ColonSeparatedSyntax()
        result = syntax.parse_filter("name:starts_with:John")
        assert result["op"] == "startswith"

    def test_endswith_operator(self) -> None:
        syntax = ColonSeparatedSyntax()
        result = syntax.parse_filter("file:endswith:.pdf")
        assert result["op"] == "endswith"
        assert result["attr"] == "file"
        assert result["val"] == ".pdf"

    def test_ends_with_alias(self) -> None:
        syntax = ColonSeparatedSyntax()
        result = syntax.parse_filter("file:ends_with:.pdf")
        assert result["op"] == "endswith"

    def test_like_operator(self) -> None:
        syntax = ColonSeparatedSyntax()
        result = syntax.parse_filter("name:like:John%")
        assert result["op"] == "like"
        assert result["val"] == "John%"

    def test_ilike_operator(self) -> None:
        syntax = ColonSeparatedSyntax()
        result = syntax.parse_filter("email:ilike:%@gmail.com")
        assert result["op"] == "ilike"
        assert result["val"] == "%@gmail.com"


class TestColonSeparatedRangeOperators:
    """Test range query operators in colon syntax."""

    def test_between_operator(self) -> None:
        syntax = ColonSeparatedSyntax()
        result = syntax.parse_filter("age:between:18,65")
        assert result["op"] == "between"
        assert result["attr"] == "age"
        assert result["val"] == [18, 65]

    def test_not_between_operator(self) -> None:
        syntax = ColonSeparatedSyntax()
        result = syntax.parse_filter("price:not_between:100,200")
        assert result["op"] == "not_between"
        assert result["val"] == [100, 200]

    def test_between_with_strings(self) -> None:
        syntax = ColonSeparatedSyntax()
        result = syntax.parse_filter("date:between:2024-01-01,2024-12-31")
        assert result["op"] == "between"
        assert result["val"] == ["2024-01-01", "2024-12-31"]


class TestColonSeparatedSetOperators:
    """Test enhanced set operators (in, not_in)."""

    def test_in_operator_with_numbers(self) -> None:
        syntax = ColonSeparatedSyntax()
        result = syntax.parse_filter("status:in:1,2,3")
        assert result["op"] == "in"
        assert result["val"] == [1, 2, 3]

    def test_in_operator_with_strings(self) -> None:
        syntax = ColonSeparatedSyntax()
        result = syntax.parse_filter("category:in:electronics,books")
        assert result["op"] == "in"
        assert result["val"] == ["electronics", "books"]

    def test_not_in_operator(self) -> None:
        syntax = ColonSeparatedSyntax()
        result = syntax.parse_filter("role:not_in:admin,banned")
        assert result["op"] == "not_in"
        assert result["val"] == ["admin", "banned"]


class TestColonSeparatedComplexQueries:
    """Test complex queries with multiple operators."""

    def test_multiple_conditions(self) -> None:
        syntax = ColonSeparatedSyntax()
        result = syntax.parse_filter(
            "status:eq:active,age:gte:18,deleted_at:is_null:true"
        )
        assert result["op"] == "and"
        assert len(result["conditions"]) == 3

        # Check each condition
        conditions = result["conditions"]
        assert any(
            c["op"] == "=" and c["attr"] == "status" and c["val"] == "active"
            for c in conditions
        )
        assert any(
            c["op"] == ">=" and c["attr"] == "age" and c["val"] == 18
            for c in conditions
        )
        assert any(
            c["op"] == "is_null" and c["attr"] == "deleted_at" for c in conditions
        )

    def test_mixed_operators(self) -> None:
        syntax = ColonSeparatedSyntax()
        result = syntax.parse_filter(
            "name:startswith:John,age:between:25,40,role:in:admin,user"
        )
        assert result["op"] == "and"
        assert len(result["conditions"]) == 3


class TestJsonSyntaxEnhancedOperators:
    """Test enhanced operators in JSON syntax."""

    def test_null_operators(self) -> None:
        syntax = JsonFilterSyntax()
        result = syntax.parse_filter(
            {
                "field": "deleted_at",
                "op": "is_null",
                "value": True,
            }
        )
        assert result["op"] == "is_null"
        assert result["attr"] == "deleted_at"
        assert result["val"] is True

    def test_string_operators(self) -> None:
        syntax = JsonFilterSyntax()
        result = syntax.parse_filter(
            {
                "field": "name",
                "op": "startswith",
                "value": "John",
            }
        )
        assert result["op"] == "startswith"
        assert result["val"] == "John"

    def test_range_operators(self) -> None:
        syntax = JsonFilterSyntax()
        result = syntax.parse_filter(
            {
                "field": "age",
                "op": "between",
                "value": [18, 65],
            }
        )
        assert result["op"] == "between"
        assert result["val"] == [18, 65]

    def test_composite_with_enhanced_operators(self) -> None:
        syntax = JsonFilterSyntax()
        result = syntax.parse_filter(
            {
                "and": [
                    {"field": "status", "op": "eq", "value": "active"},
                    {"field": "deleted_at", "op": "is_null", "value": True},
                    {"field": "name", "op": "startswith", "value": "John"},
                ]
            }
        )
        assert result["op"] == "and"
        assert len(result["conditions"]) == 3


class TestJsonSyntaxAllOperators:
    """Test that JSON syntax supports ALL specification operators."""

    def test_json_contains_operator(self) -> None:
        syntax = JsonFilterSyntax()
        result = syntax.parse_filter(
            {
                "field": "metadata",
                "op": "json_contains",
                "value": {"verified": True},
            }
        )
        assert result["op"] == "json_contains"

    def test_geo_within_operator(self) -> None:
        syntax = JsonFilterSyntax()
        result = syntax.parse_filter(
            {
                "field": "location",
                "op": "within",
                "value": {"type": "Polygon", "coordinates": [...]},
            }
        )
        assert result["op"] == "within"

    def test_regex_operator(self) -> None:
        syntax = JsonFilterSyntax()
        result = syntax.parse_filter(
            {
                "field": "phone",
                "op": "regex",
                "value": r"^\d{3}-\d{4}$",
            }
        )
        assert result["op"] == "regex"

    def test_invalid_operator_raises_error(self) -> None:
        syntax = JsonFilterSyntax()
        with pytest.raises(FilterParseError, match="Unknown operator"):
            syntax.parse_filter(
                {
                    "field": "status",
                    "op": "invalid_op",
                    "value": "active",
                }
            )


class TestValueParsing:
    """Test value parsing for different operators."""

    def test_boolean_parsing(self) -> None:
        syntax = ColonSeparatedSyntax()

        result = syntax.parse_filter("active:eq:true")
        assert result["val"] is True

        result = syntax.parse_filter("active:eq:false")
        assert result["val"] is False

    def test_null_value_parsing(self) -> None:
        syntax = ColonSeparatedSyntax()
        result = syntax.parse_filter("deleted:eq:null")
        assert result["val"] is None

    def test_numeric_parsing(self) -> None:
        syntax = ColonSeparatedSyntax()

        result = syntax.parse_filter("age:eq:25")
        assert result["val"] == 25
        assert isinstance(result["val"], int)

        result = syntax.parse_filter("price:eq:99.99")
        assert result["val"] == 99.99
        assert isinstance(result["val"], float)

    def test_string_unchanged(self) -> None:
        syntax = ColonSeparatedSyntax()
        result = syntax.parse_filter("name:eq:John Doe")
        assert result["val"] == "John Doe"
        assert isinstance(result["val"], str)


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_value(self) -> None:
        syntax = ColonSeparatedSyntax()
        result = syntax.parse_filter("name:eq:")
        assert result["val"] == ""

    def test_whitespace_handling(self) -> None:
        syntax = ColonSeparatedSyntax()
        result = syntax.parse_filter(" name : eq : John ")
        assert result["attr"] == "name"
        assert (
            result["op"] == "="
        )  # "eq" is normalized to "=" (SpecificationOperator.EQ)
        assert result["val"] == "John"

    def test_special_characters_in_value(self) -> None:
        syntax = ColonSeparatedSyntax()
        result = syntax.parse_filter("email:eq:user@example.com")
        assert result["val"] == "user@example.com"

    def test_between_single_value(self) -> None:
        """Between with single value parses as scalar (not a list)."""
        syntax = ColonSeparatedSyntax()
        result = syntax.parse_filter("age:between:25")
        # Single value without comma is parsed as scalar
        assert result["val"] == 25
