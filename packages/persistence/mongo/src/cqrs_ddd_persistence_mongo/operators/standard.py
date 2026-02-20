"""Standard comparison operators for MongoDB query compilation."""

from __future__ import annotations

from typing import Any

from cqrs_ddd_specifications.operators import SpecificationOperator

from ..exceptions import MongoQueryError

_MONGO_OP_MAP: dict[SpecificationOperator, str] = {
    SpecificationOperator.EQ: "$eq",
    SpecificationOperator.NE: "$ne",
    SpecificationOperator.GT: "$gt",
    SpecificationOperator.GE: "$gte",
    SpecificationOperator.LT: "$lt",
    SpecificationOperator.LE: "$lte",
    SpecificationOperator.IN: "$in",
    SpecificationOperator.NOT_IN: "$nin",
}


def compile_standard(field: str, op: str, val: Any) -> dict[str, Any] | None:
    """Compile standard comparison operators to MongoDB query fragments."""
    try:
        spec_op = SpecificationOperator(op)
    except ValueError:
        return None

    mongo_op = _MONGO_OP_MAP.get(spec_op)
    if mongo_op:
        normalized = val if isinstance(val, list) else [val]
        if spec_op in {SpecificationOperator.IN, SpecificationOperator.NOT_IN}:
            return {field: {mongo_op: normalized}}
        return {field: {mongo_op: val}}

    if spec_op == SpecificationOperator.BETWEEN:
        lo, hi = _validate_range_operand(val, op_name="between")
        return {"$and": [{field: {"$gte": lo}}, {field: {"$lte": hi}}]}

    if spec_op == SpecificationOperator.NOT_BETWEEN:
        lo, hi = _validate_range_operand(val, op_name="not_between")
        return {"$or": [{field: {"$lt": lo}}, {field: {"$gt": hi}}]}

    return None


def _validate_range_operand(val: Any, *, op_name: str) -> tuple[Any, Any]:
    if not isinstance(val, (list, tuple)) or len(val) != 2:
        raise MongoQueryError(f"{op_name} requires a list of two values")
    return val[0], val[1]
