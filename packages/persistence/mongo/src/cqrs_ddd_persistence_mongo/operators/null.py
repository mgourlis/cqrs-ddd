"""Null/empty checks -> $exists, $type."""

from __future__ import annotations

from typing import Any

from cqrs_ddd_specifications.operators import SpecificationOperator


def compile_null(field: str, op: str, _val: Any) -> dict[str, Any] | None:
    """Compile null/empty operators. Returns None if not a null op."""
    try:
        spec_op = SpecificationOperator(op)
    except ValueError:
        return None
    if spec_op == SpecificationOperator.IS_NULL:
        return {"$or": [{field: {"$exists": False}}, {field: {"$eq": None}}]}
    if spec_op == SpecificationOperator.IS_NOT_NULL:
        return {field: {"$exists": True, "$ne": None}}
    if spec_op == SpecificationOperator.IS_EMPTY:
        return {
            "$or": [
                {field: {"$exists": False}},
                {field: {"$eq": None}},
                {field: {"$eq": ""}},
                {field: {"$size": 0}},
            ]
        }
    if spec_op == SpecificationOperator.IS_NOT_EMPTY:
        return {
            "$and": [
                {field: {"$exists": True}},
                {field: {"$ne": None}},
                {field: {"$ne": ""}},
            ]
        }
    return None
