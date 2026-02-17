"""JSON operators for in-memory evaluation."""

from __future__ import annotations

from typing import Any

from ..evaluator import MemoryOperator
from ..operators import SpecificationOperator


def _dict_contains(haystack: Any, needle: Any) -> bool:
    """
    Recursive dict containment check.

    Mirrors PostgreSQL ``@>`` semantics:
    ``{"a": 1, "b": {"c": 2}} @> {"b": {"c": 2}}`` is True.
    """
    if isinstance(needle, dict) and isinstance(haystack, dict):
        return all(
            k in haystack and _dict_contains(haystack[k], v) for k, v in needle.items()
        )
    if isinstance(needle, list) and isinstance(haystack, list):
        return all(any(_dict_contains(h, n) for h in haystack) for n in needle)
    return bool(haystack == needle)


class JsonContainsOperator(MemoryOperator):
    """``field @> value`` — field contains the given JSON structure."""

    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.JSON_CONTAINS

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if field_value is None:
            return False
        return _dict_contains(field_value, condition_value)


class JsonContainedByOperator(MemoryOperator):
    """``field <@ value`` — field is contained by the given JSON structure."""

    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.JSON_CONTAINED_BY

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if field_value is None:
            return False
        return _dict_contains(condition_value, field_value)


class JsonHasKeyOperator(MemoryOperator):
    """``field ? key`` — field (dict) has the given key."""

    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.JSON_HAS_KEY

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if not isinstance(field_value, dict):
            return False
        return str(condition_value) in field_value


class JsonHasAnyOperator(MemoryOperator):
    """``field ?| keys`` — field has at least one of the given keys."""

    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.JSON_HAS_ANY

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if not isinstance(field_value, dict):
            return False
        keys = (
            condition_value
            if isinstance(condition_value, list | tuple)
            else [condition_value]
        )
        return any(str(k) in field_value for k in keys)


class JsonHasAllOperator(MemoryOperator):
    """``field ?& keys`` — field has all of the given keys."""

    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.JSON_HAS_ALL

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if not isinstance(field_value, dict):
            return False
        keys = (
            condition_value
            if isinstance(condition_value, list | tuple)
            else [condition_value]
        )
        return all(str(k) in field_value for k in keys)


class JsonPathExistsOperator(MemoryOperator):
    """Simple dot-path existence check for in-memory evaluation."""

    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.JSON_PATH_EXISTS

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if field_value is None:
            return False
        # Navigate the dot-separated path
        path = str(condition_value).lstrip("$").lstrip(".")
        current = field_value
        for part in path.split("."):
            if not part:
                continue
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return False
        return True
