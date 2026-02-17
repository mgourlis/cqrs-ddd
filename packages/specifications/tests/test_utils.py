"""Tests for utility functions."""

from __future__ import annotations

import datetime as dt
import uuid as uuid_module
from datetime import datetime, timedelta, timezone

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

    def test_integer_variants(self):
        """Test all integer type names (int, integer, smallinteger, biginteger)."""
        assert cast_value("42", "integer") == 42
        assert cast_value("100", "smallinteger") == 100
        assert cast_value("999999", "biginteger") == 999999

    def test_float(self):
        assert cast_value("3.14", "float") == pytest.approx(3.14)

    def test_float_variants(self):
        """Test all float type names (float, double, decimal, numeric)."""
        assert cast_value("3.14", "double") == pytest.approx(3.14)
        assert cast_value("2.5", "decimal") == pytest.approx(2.5)
        assert cast_value("1.234", "numeric") == pytest.approx(1.234)

    def test_bool_true(self):
        assert cast_value("true", "bool") is True
        assert cast_value("1", "bool") is True
        assert cast_value("yes", "bool") is True

    def test_bool_false(self):
        assert cast_value("false", "bool") is False
        assert cast_value("0", "bool") is False
        assert cast_value("no", "bool") is False

    def test_bool_from_actual_bool(self):
        """Boolean values pass through correctly."""
        assert cast_value(True, "boolean") is True
        assert cast_value(False, "boolean") is False

    def test_str(self):
        assert cast_value(42, "str") == "42"
        assert cast_value(3.14, "text") == "3.14"

    def test_date(self):
        result = cast_value("2024-01-15", "date")
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_date_from_date_object(self):
        """Date objects pass through correctly."""
        date_obj = dt.date(2024, 1, 15)
        result = cast_value(date_obj, "date")
        assert result == date_obj

    def test_datetime(self):
        result = cast_value("2024-01-15T10:30:00", "datetime")
        assert isinstance(result, datetime)
        assert result.hour == 10

    def test_datetime_with_timezone_z(self):
        """Datetime with Z suffix is converted to UTC."""
        result = cast_value("2024-01-15T10:30:00Z", "datetime")
        assert isinstance(result, datetime)
        assert result.tzinfo is not None

    def test_datetime_from_datetime_object(self):
        """Datetime objects pass through correctly."""
        dt_obj = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = cast_value(dt_obj, "datetime")
        assert result == dt_obj

    def test_time(self):
        """Time values are parsed correctly."""
        result = cast_value("14:30:00", "time")
        assert isinstance(result, dt.time)
        assert result.hour == 14
        assert result.minute == 30

    def test_time_from_time_object(self):
        """Time objects pass through correctly."""
        time_obj = dt.time(14, 30, 0)
        result = cast_value(time_obj, "time")
        assert result == time_obj

    def test_interval(self):
        """Interval values are parsed to timedelta."""
        result = cast_value("2 days", "interval")
        assert result == timedelta(days=2)

    def test_interval_from_timedelta_object(self):
        """Timedelta objects pass through correctly."""
        td = timedelta(hours=24)
        result = cast_value(td, "interval")
        assert result == td

    def test_uuid(self):
        """UUID strings are parsed to UUID objects."""
        uuid_str = "123e4567-e89b-12d3-a456-426614174000"
        result = cast_value(uuid_str, "uuid")
        assert isinstance(result, uuid_module.UUID)
        assert str(result) == uuid_str

    def test_uuid_from_uuid_object(self):
        """UUID objects pass through correctly."""
        uuid_obj = uuid_module.uuid4()
        result = cast_value(uuid_obj, "uuid")
        assert result == uuid_obj

    def test_json_from_dict(self):
        """Dict values pass through for JSON type."""
        data = {"key": "value", "count": 42}
        result = cast_value(data, "json")
        assert result == data

    def test_json_from_list(self):
        """List values pass through for JSON type."""
        data = [1, 2, 3, {"key": "value"}]
        result = cast_value(data, "json")
        assert result == data

    def test_json_from_string(self):
        """JSON strings are parsed to dict/list."""
        json_str = '{"key": "value", "count": 42}'
        result = cast_value(json_str, "json")
        assert result == {"key": "value", "count": 42}

    def test_largebinary_from_bytes(self):
        """Bytes values pass through correctly."""
        data = b"binary data"
        result = cast_value(data, "largebinary")
        assert result == data

    def test_largebinary_from_string(self):
        """Strings are encoded to bytes."""
        result = cast_value("text data", "largebinary")
        assert result == b"text data"

    def test_list(self):
        result = cast_value("a,b,c", "list")
        assert result == ["a", "b", "c"]

    def test_list_recursive_casting(self):
        """List items are cast recursively."""
        result = cast_value(["1", "2", "3"], "int")
        assert result == [1, 2, 3]

    def test_auto_inference_int(self):
        assert cast_value("42", "auto") == 42

    def test_auto_inference_float(self):
        assert cast_value("3.14", "auto") == pytest.approx(3.14)

    def test_auto_inference_bool(self):
        assert cast_value("true", "auto") is True
        assert cast_value("false", "auto") is False

    def test_auto_inference_string_fallback(self):
        assert cast_value("hello", "auto") == "hello"

    def test_none_inference_datetime(self):
        """Auto-infer datetime from ISO format string."""
        result = cast_value("2024-01-15T10:30:00")
        assert isinstance(result, datetime)

    def test_none_inference_date(self):
        """Auto-infer date from ISO format string."""
        result = cast_value("2024-01-15")
        assert isinstance(result, dt.date)

    def test_none_inference_uuid(self):
        """Auto-infer UUID from valid UUID string."""
        uuid_str = "123e4567-e89b-12d3-a456-426614174000"
        result = cast_value(uuid_str)
        assert isinstance(result, uuid_module.UUID)

    def test_none_inference_json(self):
        """Auto-infer JSON from valid JSON string."""
        result = cast_value('{"key": "value"}')
        assert result == {"key": "value"}

    def test_none_inference_non_string_passthrough(self):
        """Non-string values pass through when no type specified."""
        assert cast_value(42) == 42
        assert cast_value([1, 2, 3]) == [1, 2, 3]

    def test_cast_failure_returns_original(self):
        """Invalid casting returns original value."""
        result = cast_value("not-a-number", "int")
        assert result == "not-a-number"

    def test_unknown_type_returns_as_is(self):
        assert cast_value("foo", "unsupported") == "foo"


# -- parse_list_value -------------------------------------------------------


class TestParseListValue:
    def test_list_passthrough(self):
        assert parse_list_value([1, 2, 3]) == [1, 2, 3]

    def test_tuple_conversion(self):
        """Tuples are converted to lists."""
        assert parse_list_value((1, 2, 3)) == [1, 2, 3]

    def test_set_conversion(self):
        """Sets are converted to lists."""
        result = parse_list_value({1, 2, 3})
        assert len(result) == 3
        assert set(result) == {1, 2, 3}

    def test_comma_separated_string(self):
        assert parse_list_value("a,b,c") == ["a", "b", "c"]

    def test_bracketed_string(self):
        """Bracketed strings are parsed correctly."""
        assert parse_list_value("[a, b, c]") == ["a", "b", "c"]

    def test_bracketed_string_with_quotes(self):
        """Bracketed strings with quoted values."""
        assert parse_list_value("['a', 'b', 'c']") == ["a", "b", "c"]
        assert parse_list_value('["x", "y", "z"]') == ["x", "y", "z"]

    def test_empty_bracketed_string(self):
        """Empty bracketed strings return empty list."""
        assert parse_list_value("[]") == []
        assert parse_list_value("[ ]") == []

    def test_empty_string(self):
        """Empty strings return empty list."""
        assert parse_list_value("") == []
        assert parse_list_value("  ") == []

    def test_single_string(self):
        assert parse_list_value("hello") == ["hello"]

    def test_scalar(self):
        assert parse_list_value(42) == [42]

    def test_whitespace_handling(self):
        """Whitespace is stripped from list items."""
        assert parse_list_value(" a , b , c ") == ["a", "b", "c"]
        assert parse_list_value("[ a , b , c ]") == ["a", "b", "c"]


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

    def test_shorthand_with_whitespace(self):
        """Shorthand formats work with whitespace."""
        assert parse_interval("7 d") == timedelta(days=7)
        assert parse_interval("24 h") == timedelta(hours=24)

    def test_shorthand_case_insensitive(self):
        """Shorthand formats are case-insensitive."""
        assert parse_interval("7D") == timedelta(days=7)
        assert parse_interval("24H") == timedelta(hours=24)

    def test_hms_format(self):
        """HH:MM:SS format is parsed correctly."""
        assert parse_interval("1:30:00") == timedelta(hours=1, minutes=30)
        assert parse_interval("0:45:30") == timedelta(minutes=45, seconds=30)
        assert parse_interval("12:00:00") == timedelta(hours=12)

    def test_natural_language_days(self):
        """Natural language 'N days' format."""
        assert parse_interval("1 day") == timedelta(days=1)
        assert parse_interval("5 days") == timedelta(days=5)

    def test_natural_language_hours(self):
        """Natural language 'N hours' format."""
        assert parse_interval("2 hours") == timedelta(hours=2)
        assert parse_interval("1 hour") == timedelta(hours=1)

    def test_natural_language_minutes(self):
        """Natural language 'N minutes' format."""
        assert parse_interval("30 minutes") == timedelta(minutes=30)
        assert parse_interval("1 minute") == timedelta(minutes=1)

    def test_natural_language_seconds(self):
        """Natural language 'N seconds' format."""
        assert parse_interval("45 seconds") == timedelta(seconds=45)
        assert parse_interval("1 second") == timedelta(seconds=1)

    def test_natural_language_combination(self):
        """Natural language with multiple units."""
        result = parse_interval("1 day 2 hours 30 minutes")
        expected = timedelta(days=1, hours=2, minutes=30)
        assert result == expected

    def test_natural_language_case_insensitive(self):
        """Natural language is case-insensitive."""
        assert parse_interval("2 Days") == timedelta(days=2)
        assert parse_interval("3 HOURS") == timedelta(hours=3)

    def test_numeric_string_as_seconds(self):
        """Plain numeric strings are treated as seconds."""
        assert parse_interval("120") == timedelta(seconds=120)
        assert parse_interval("3600") == timedelta(seconds=3600)

    def test_float_seconds(self):
        """Float values for seconds."""
        assert parse_interval("1.5") == timedelta(seconds=1.5)
        assert parse_interval("0.5") == timedelta(seconds=0.5)

    def test_timedelta_passthrough(self):
        """Timedelta objects pass through unchanged."""
        td = timedelta(hours=3)
        assert parse_interval(td) == td

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
