"""Standard comparison operators: =, !=, >, <, >=, <=."""

from __future__ import annotations

from typing import Any

from ..evaluator import MemoryOperator
from ..operators import SpecificationOperator


class EqualOperator(MemoryOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.EQ

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        return bool(field_value == condition_value)


class NotEqualOperator(MemoryOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.NE

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        return bool(field_value != condition_value)


class GreaterThanOperator(MemoryOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.GT

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if field_value is None:
            return False
        return bool(field_value > condition_value)


class LessThanOperator(MemoryOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.LT

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if field_value is None:
            return False
        return bool(field_value < condition_value)


class GreaterEqualOperator(MemoryOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.GE

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if field_value is None:
            return False
        return bool(field_value >= condition_value)


class LessEqualOperator(MemoryOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.LE

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if field_value is None:
            return False
        return bool(field_value <= condition_value)
