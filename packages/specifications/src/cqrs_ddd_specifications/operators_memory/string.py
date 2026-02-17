"""String operators: like, not_like, ilike, contains, icontains, etc."""

from __future__ import annotations

import re
from typing import Any

from ..evaluator import MemoryOperator
from ..operators import SpecificationOperator


def _sql_pattern_to_regex(pattern: str) -> str:
    """Convert SQL LIKE pattern (``%``, ``_``) to a Python regex."""
    return pattern.replace("%", ".*").replace("_", ".")


class LikeOperator(MemoryOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.LIKE

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if field_value is None:
            return False
        regex = _sql_pattern_to_regex(str(condition_value))
        return bool(re.match(f"^{regex}$", str(field_value)))


class NotLikeOperator(MemoryOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.NOT_LIKE

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if field_value is None:
            return False
        regex = _sql_pattern_to_regex(str(condition_value))
        return not bool(re.match(f"^{regex}$", str(field_value)))


class ILikeOperator(MemoryOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.ILIKE

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if field_value is None:
            return False
        regex = _sql_pattern_to_regex(str(condition_value))
        return bool(re.match(f"^{regex}$", str(field_value), re.IGNORECASE))


class ContainsOperator(MemoryOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.CONTAINS

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if field_value is None:
            return False
        return str(condition_value) in str(field_value)


class IContainsOperator(MemoryOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.ICONTAINS

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if field_value is None:
            return False
        return str(condition_value).lower() in str(field_value).lower()


class StartsWithOperator(MemoryOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.STARTSWITH

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if field_value is None:
            return False
        return str(field_value).startswith(str(condition_value))


class IStartsWithOperator(MemoryOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.ISTARTSWITH

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if field_value is None:
            return False
        return str(field_value).lower().startswith(str(condition_value).lower())


class EndsWithOperator(MemoryOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.ENDSWITH

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if field_value is None:
            return False
        return str(field_value).endswith(str(condition_value))


class IEndsWithOperator(MemoryOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.IENDSWITH

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if field_value is None:
            return False
        return str(field_value).lower().endswith(str(condition_value).lower())


class RegexOperator(MemoryOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.REGEX

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if field_value is None:
            return False
        return bool(re.search(str(condition_value), str(field_value)))


class IRegexOperator(MemoryOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.IREGEX

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if field_value is None:
            return False
        return bool(re.search(str(condition_value), str(field_value), re.IGNORECASE))
