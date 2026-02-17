"""Set operators: in, not_in, all, between, not_between."""

from __future__ import annotations

from typing import Any

from ..evaluator import MemoryOperator
from ..operators import SpecificationOperator


class InOperator(MemoryOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.IN

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        return field_value in condition_value


class NotInOperator(MemoryOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.NOT_IN

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        return field_value not in condition_value


class AllOperator(MemoryOperator):
    """Check that *all* expected values are present in the field value."""

    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.ALL

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if field_value is None:
            return False
        expected = (
            set(condition_value)
            if not isinstance(condition_value, set)
            else condition_value
        )
        return expected.issubset(set(field_value))


class BetweenOperator(MemoryOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.BETWEEN

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if field_value is None:
            return False
        low, high = condition_value
        return bool(low <= field_value <= high)


class NotBetweenOperator(MemoryOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.NOT_BETWEEN

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if field_value is None:
            return False
        low, high = condition_value
        return not (low <= field_value <= high)
