"""Tests for utility functions."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from cqrs_ddd_specifications.utils import (
    cast_value,
    geojson_to_str,
    parse_interval,
    parse_list_value,
)

# -- cast_value ---------------------------------------------------------------


class TestCastValue:
    def test_int(self):
        assert cast_value("42", "int") == 42

    def test_float(self):
        assert cast_value("3.14", "float") == pytest.approx(3.14)

    def test_bool_true(self):
        assert cast_value("true", "bool") is True
        assert cast_value("1", "bool") is True

    def test_bool_false(self):
        assert cast_value("false", "bool") is False
        assert cast_value("0", "bool") is False

    def test_str(self):
        assert cast_value(42, "str") == "42"

    def test_date(self):
        result = cast_value("2024-01-15", "date")
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_datetime(self):
        result = cast_value("2024-01-15T10:30:00", "datetime")
        assert isinstance(result, datetime)
        assert result.hour == 10

    def test_list(self):
        result = cast_value("a,b,c", "list")
        assert result == ["a", "b", "c"]

    def test_auto_inference_int(self):
        assert cast_value("42", "auto") == 42

    def test_auto_inference_float(self):
        assert cast_value("3.14", "auto") == pytest.approx(3.14)

    def test_auto_inference_bool(self):
        assert cast_value("true", "auto") is True

    def test_auto_inference_string_fallback(self):
        assert cast_value("hello", "auto") == "hello"

    def test_unknown_type_returns_as_is(self):
        assert cast_value("foo", "unsupported") == "foo"


# -- parse_list_value -------------------------------------------------------


class TestParseListValue:
    def test_list_passthrough(self):
        assert parse_list_value([1, 2, 3]) == [1, 2, 3]

    def test_comma_separated_string(self):
        assert parse_list_value("a,b,c") == ["a", "b", "c"]

    def test_single_string(self):
        assert parse_list_value("hello") == ["hello"]

    def test_scalar(self):
        assert parse_list_value(42) == [42]


# -- parse_interval -----------------------------------------------------------


class TestParseInterval:
    def test_days(self):
        assert parse_interval("7d") == timedelta(days=7)

    def test_hours(self):
        assert parse_interval("24h") == timedelta(hours=24)

    def test_minutes(self):
        assert parse_interval("30m") == timedelta(minutes=30)

    def test_seconds(self):
        assert parse_interval("90s") == timedelta(seconds=90)

    def test_weeks(self):
        assert parse_interval("2w") == timedelta(weeks=2)

    def test_invalid_unit(self):
        with pytest.raises(ValueError, match="Unrecognised interval"):
            parse_interval("5x")

    def test_invalid_format(self):
        with pytest.raises(ValueError, match="Unrecognised interval"):
            parse_interval("abc")


# -- geojson_to_str -----------------------------------------------------------


class TestGeojsonToStr:
    def test_dict_roundtrip(self):
        geojson = {"type": "Point", "coordinates": [1.0, 2.0]}
        result = geojson_to_str(geojson)
        assert '"type"' in result
        assert '"Point"' in result

    def test_string_passthrough(self):
        s = '{"type": "Point"}'
        assert geojson_to_str(s) == s
