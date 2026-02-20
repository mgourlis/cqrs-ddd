"""JSON/dot-notation operators -> $exists, $all for nested documents."""

from __future__ import annotations

from typing import Any

from cqrs_ddd_specifications.operators import SpecificationOperator


def compile_jsonb(field: str, op: str, val: Any) -> dict[str, Any] | None:
    """Compile JSON-style operators for nested document fields.

    Dot-notation field names are used as-is. Returns ``None`` if unsupported.
    """
    try:
        spec_op = SpecificationOperator(op)
    except ValueError:
        return None
    if spec_op == SpecificationOperator.JSON_HAS_KEY:
        # Path exists and is not null
        return {field: {"$exists": True, "$ne": None}}
    if spec_op == SpecificationOperator.JSON_HAS_ANY:
        if not isinstance(val, list):
            val = [val]
        return {field: {"$in": val}}
    if spec_op == SpecificationOperator.JSON_HAS_ALL:
        if not isinstance(val, list):
            val = [val]
        return {field: {"$all": val}}
    if spec_op == SpecificationOperator.JSON_CONTAINS:
        # Value contains (for arrays: element in array; for object: subset)
        if isinstance(val, list):
            return {field: {"$all": val}}
        return {field: {"$eq": val}}
    if spec_op == SpecificationOperator.JSON_PATH_EXISTS:
        return {field: {"$exists": True}}
    return None
