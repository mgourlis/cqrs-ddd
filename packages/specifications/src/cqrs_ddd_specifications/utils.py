"""
Shared utility functions for the Specifications package.

These are pure-Python helpers with no infrastructure dependencies.
"""

from __future__ import annotations

import datetime
import json
import re
import uuid as uuid_module
from typing import Any

# ---------------------------------------------------------------------------
# GeoJSON helpers
# ---------------------------------------------------------------------------


def geojson_to_str(geojson: Any) -> str:
    """Convert a GeoJSON dict to a JSON string (pass-through if already str)."""
    if isinstance(geojson, dict):
        return json.dumps(geojson)
    return str(geojson)


# ---------------------------------------------------------------------------
# List parsing
# ---------------------------------------------------------------------------


def parse_list_value(value: Any) -> list[Any]:
    """
    Parse a value into a list.

    Supports:
    - Python collections (list, tuple, set)
    - Comma-separated strings: ``"val1, val2"``
    - Bracketed strings: ``"[val1, val2]"`` or ``"['val1', 'val2']"``
    """
    if isinstance(value, list | tuple | set):
        return list(value)
    if isinstance(value, str):
        content = value.strip()
        if content.startswith("[") and content.endswith("]"):
            content = content[1:-1].strip()
        if not content:
            return []
        return [v.strip().strip("'").strip('"') for v in content.split(",")]
    return [value]


# ---------------------------------------------------------------------------
# Interval parsing
# ---------------------------------------------------------------------------

_TIME_RE = re.compile(r"^(\d+):(\d+):(\d+)$")
_DAY_RE = re.compile(r"(\d+)\s*days?", re.IGNORECASE)
_HOUR_RE = re.compile(r"(\d+)\s*hours?", re.IGNORECASE)
_MIN_RE = re.compile(r"(\d+)\s*minutes?", re.IGNORECASE)
_SEC_RE = re.compile(r"(\d+)\s*seconds?", re.IGNORECASE)
# Shorthand: 7d, 24h, 30m, 90s, 2w
_SHORTHAND_RE = re.compile(r"^(\d+)\s*([dhmsw])$", re.IGNORECASE)


def parse_interval(value: str) -> datetime.timedelta:
    """
    Parse an interval string into a ``timedelta``.

    Supported formats:
    - ``"1:30:00"`` (HH:MM:SS)
    - ``"1 day"``, ``"2 days"``
    - ``"3 hours"``, ``"30 minutes"``, ``"45 seconds"``
    - ``"1 day 2 hours 30 minutes"``
    - Plain numeric string → treated as seconds
    """
    if isinstance(value, datetime.timedelta):
        return value

    text = str(value).strip()

    # Try shorthand: 7d, 24h, 30m, 90s, 2w
    sm = _SHORTHAND_RE.match(text)
    if sm:
        amount = int(sm.group(1))
        unit = sm.group(2).lower()
        unit_map = {
            "d": "days",
            "h": "hours",
            "m": "minutes",
            "s": "seconds",
            "w": "weeks",
        }
        return datetime.timedelta(**{unit_map[unit]: amount})

    # Try HH:MM:SS format
    m = _TIME_RE.match(text)
    if m:
        hours, minutes, seconds = map(int, m.groups())
        return datetime.timedelta(hours=hours, minutes=minutes, seconds=seconds)

    # Try natural-language format
    days = hours = minutes = seconds = 0
    dm = _DAY_RE.search(text)
    if dm:
        days = int(dm.group(1))
    hm = _HOUR_RE.search(text)
    if hm:
        hours = int(hm.group(1))
    mm = _MIN_RE.search(text)
    if mm:
        minutes = int(mm.group(1))
    sm = _SEC_RE.search(text)
    if sm:
        seconds = int(sm.group(1))

    if days or hours or minutes or seconds:
        return datetime.timedelta(
            days=days,
            hours=hours,
            minutes=minutes,
            seconds=seconds,
        )

    # Fallback: parse as seconds
    try:
        return datetime.timedelta(seconds=float(text))
    except ValueError as err:
        raise ValueError(f"Unrecognised interval format: {value}") from err


# ---------------------------------------------------------------------------
# Value casting
# ---------------------------------------------------------------------------


def cast_value(value: Any, value_type: str | None = None) -> Any:
    """
    Cast *value* to the appropriate Python type.

    If *value* is a list, each item is cast recursively.
    If *value_type* is ``None`` and *value* is a string, the function
    attempts to auto-infer the type (datetime → date → UUID → JSON).

    Supported *value_type* strings: ``string``, ``text``, ``integer``,
    ``int``, ``smallinteger``, ``biginteger``, ``float``, ``double``,
    ``decimal``, ``numeric``, ``boolean``, ``date``, ``datetime``,
    ``time``, ``interval``, ``uuid``, ``json``, ``largebinary``.
    """
    # Recursive list handling
    if isinstance(value, list):
        return [cast_value(item, value_type) for item in value]

    # Non-strings pass through unless explicit type given
    if not isinstance(value, str) and value_type is None:
        return value

    if value_type is not None:
        try:
            return _cast_explicit(value, value_type)
        except (ValueError, json.JSONDecodeError, TypeError):
            return value

    # Auto-inference for strings when value_type is None
    if isinstance(value, str):
        return _infer_type(value)

    return value


def _cast_numeric(value: Any, vt: str) -> Any | None:
    """Cast numeric types."""
    if vt in ("integer", "int", "smallinteger", "biginteger"):
        return int(value)
    if vt in ("float", "double", "decimal", "numeric"):
        return float(value)
    return None


def _cast_boolean(value: Any) -> bool:
    """Cast boolean type."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes")
    return bool(value)


def _cast_datetime_types(value: Any, vt: str) -> Any | None:
    """Cast datetime-related types."""
    if vt == "date":
        if isinstance(value, datetime.date):
            return value
        return datetime.datetime.fromisoformat(str(value)).date()
    if vt == "datetime":
        if isinstance(value, datetime.datetime):
            return value
        result = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if result.tzinfo is not None:
            result = result.astimezone(datetime.timezone.utc)
        return result
    if vt == "time":
        if isinstance(value, datetime.time):
            return value
        return datetime.time.fromisoformat(str(value))
    if vt == "interval":
        if isinstance(value, datetime.timedelta):
            return value
        return parse_interval(str(value))
    return None


def _cast_uuid(value: Any) -> uuid_module.UUID:
    """Cast value to UUID."""
    if isinstance(value, uuid_module.UUID):
        return value
    return uuid_module.UUID(str(value))


def _cast_json(value: Any) -> Any:
    """Cast value to JSON."""
    if isinstance(value, dict | list):
        return value
    return json.loads(str(value))


def _cast_largebinary(value: Any) -> bytes:
    """Cast value to bytes."""
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    return bytes(value)


def _cast_other_types(value: Any, vt: str) -> Any | None:
    """Cast other types (uuid, json, largebinary, list, auto)."""
    if vt == "uuid":
        return _cast_uuid(value)
    if vt == "json":
        return _cast_json(value)
    if vt == "largebinary":
        return _cast_largebinary(value)
    if vt == "list":
        return parse_list_value(value)
    if vt == "auto":
        if isinstance(value, str):
            return _infer_auto(value)
        return value
    return None


def _cast_explicit(value: Any, value_type: str) -> Any:
    """Cast with an explicit type hint."""
    vt = value_type.lower()

    if vt in ("string", "text", "str"):
        return str(value)

    result = _cast_numeric(value, vt)
    if result is not None:
        return result

    if vt in ("boolean", "bool"):
        return _cast_boolean(value)

    result = _cast_datetime_types(value, vt)
    if result is not None:
        return result

    result = _cast_other_types(value, vt)
    if result is not None:
        return result

    # Unknown type → pass through
    return value


def _infer_auto(value: str) -> Any:
    """Auto-infer type for 'auto' value_type."""
    # Try int
    try:
        return int(value)
    except ValueError:
        pass
    # Try float
    try:
        return float(value)
    except ValueError:
        pass
    # Try bool
    low = value.lower()
    if low in ("true", "yes", "1"):
        return True
    if low in ("false", "no", "0"):
        return False
    return value


def _infer_type(value: str) -> Any:
    """Best-effort type inference for string values."""
    if value.strip() == "":
        return value

    # Try datetime
    try:
        result = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is not None:
            result = result.astimezone(datetime.timezone.utc)
        return result
    except ValueError:
        pass

    # Try date
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        pass

    # Try UUID
    try:
        return uuid_module.UUID(value)
    except ValueError:
        pass

    # Try JSON
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        pass

    return value
