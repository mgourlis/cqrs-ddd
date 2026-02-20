"""Set/array operators -> $in, $nin, $elemMatch, $all."""

from __future__ import annotations

from typing import Any

from cqrs_ddd_specifications.operators import SpecificationOperator


def compile_set(field: str, op: str, val: Any) -> dict[str, Any] | None:
    """Compile set/array operators. Returns None if not a set op."""
    try:
        spec_op = SpecificationOperator(op)
    except ValueError:
        return None
    if spec_op == SpecificationOperator.IN:
        return {field: {"$in": val if isinstance(val, list) else [val]}}
    if spec_op == SpecificationOperator.NOT_IN:
        return {field: {"$nin": val if isinstance(val, list) else [val]}}
    if spec_op == SpecificationOperator.ALL:
        return {field: {"$all": val if isinstance(val, list) else [val]}}
    # $elemMatch for "array element matches condition" — val would be a sub-query
    # Handled at query_builder level if we need nested conditions on array elements
    return None
