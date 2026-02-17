"""Full-text search operators for in-memory evaluation.

These provide a *best-effort* approximation of PostgreSQL FTS
using simple tokenisation.  For production accuracy, use the
SQLAlchemy backend.
"""

from __future__ import annotations

from typing import Any

from ..evaluator import MemoryOperator
from ..operators import SpecificationOperator


class FtsOperator(MemoryOperator):
    """All query tokens must appear somewhere in the text (case-insensitive)."""

    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.FTS

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if field_value is None:
            return False
        text = str(field_value).lower()
        tokens = str(condition_value).lower().split()
        return all(token in text for token in tokens)


class FtsPhraseOperator(MemoryOperator):
    """The exact phrase must appear as a contiguous substring (case-insensitive)."""

    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.FTS_PHRASE

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if field_value is None:
            return False
        return str(condition_value).lower() in str(field_value).lower()
