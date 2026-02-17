"""Null / empty check operators: is_null, is_not_null, is_empty, is_not_empty."""

from __future__ import annotations

from typing import Any

from ..evaluator import MemoryOperator
from ..operators import SpecificationOperator


class IsNullOperator(MemoryOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.IS_NULL

    def evaluate(self, field_value: Any, _condition_value: Any) -> bool:
        return field_value is None


class IsNotNullOperator(MemoryOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.IS_NOT_NULL

    def evaluate(self, field_value: Any, _condition_value: Any) -> bool:
        return field_value is not None


class IsEmptyOperator(MemoryOperator):
    """True for None, empty strings, and empty collections."""

    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.IS_EMPTY

    def evaluate(self, field_value: Any, _condition_value: Any) -> bool:
        return not field_value


class IsNotEmptyOperator(MemoryOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.IS_NOT_EMPTY

    def evaluate(self, field_value: Any, _condition_value: Any) -> bool:
        return bool(field_value)
