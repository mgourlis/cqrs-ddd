"""Mongo query builder from specification AST."""

from __future__ import annotations

from typing import Any

from cqrs_ddd_specifications.operators import SpecificationOperator

from .exceptions import MongoQueryError
from .operators import (
    compile_geometry,
    compile_jsonb,
    compile_null,
    compile_set,
    compile_standard,
    compile_string,
)

_COMPILERS = [
    compile_standard,
    compile_string,
    compile_jsonb,
    compile_null,
    compile_set,
    compile_geometry,
]


def _compile_leaf(data: dict[str, Any]) -> dict[str, Any]:
    """Compile a single attribute condition to a MongoDB query document."""
    op_str = data.get("op", "")
    attr = data.get("attr")
    val = data.get("val")
    if not attr:
        raise MongoQueryError(f"Specification missing 'attr': {data}")
    # Dot-notation for nested fields (e.g. address.city)
    field = attr
    for compiler in _COMPILERS:
        result = compiler(field, op_str, val)
        if result is not None:
            return result
    # Fallback: treat as equality
    return {field: {"$eq": val}}


def _compile_node(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively compile spec dict to MongoDB filter."""
    if not isinstance(data, dict):
        raise MongoQueryError("Specification node must be a dict")
    op_str = str(data.get("op", "")).lower()
    if op_str == SpecificationOperator.AND:
        conditions = data.get("conditions", [])
        if not conditions:
            return {}
        compiled = [_compile_node(c) for c in conditions]
        return {"$and": compiled}
    if op_str == SpecificationOperator.OR:
        conditions = data.get("conditions", [])
        if not conditions:
            return {}
        compiled = [_compile_node(c) for c in conditions]
        return {"$or": compiled}
    if op_str == SpecificationOperator.NOT:
        conditions = data.get("conditions", [])
        inner = _compile_node(conditions[0]) if conditions else {}
        if data.get("condition") is not None:
            inner = _compile_node(data["condition"])
        return {"$nor": [inner]} if inner else {}
    return _compile_leaf(data)


class MongoQueryBuilder:
    """Compiles BaseSpecification (via to_dict()) to MongoDB query documents."""

    def build_match(self, spec: Any) -> dict[str, Any]:
        """Build $match stage from a specification.

        Accepts either a specification instance (with to_dict()), a dict AST
        (with attr/op/conditions), or a raw MongoDB filter dict (e.g. {"field": {"$gte": 5}}).
        """
        if hasattr(spec, "to_dict"):
            data = spec.to_dict()
        elif isinstance(spec, dict):
            data = spec
        else:
            raise MongoQueryError("spec must be BaseSpecification or dict")
        if not data:
            return {}
        # Raw MongoDB filter: top-level keys are field names, no "attr"/"op"/"conditions"
        if not any(k in data for k in ("attr", "op", "conditions")):
            return data
        return _compile_node(data)

    def build_sort(
        self, order_by: list[tuple[str, str]] | list[str] | None
    ) -> list[tuple[str, int]]:
        """Build MongoDB sort tuples.

        Accepts either ``[(field, "asc"|"desc")]`` or ``["-field", "field"]``.
        """
        if not order_by:
            return []
        result: list[tuple[str, int]] = []
        for item in order_by:
            if isinstance(item, tuple):
                field, direction = item[0], item[1]
                result.append((field, -1 if str(direction).lower() == "desc" else 1))
            elif isinstance(item, str):
                if item.startswith("-"):
                    result.append((item[1:], -1))
                else:
                    result.append((item, 1))
        return result

    def build_project(self, fields: list[str] | None) -> dict[str, int] | None:
        """Build $project stage: { field: 1, ... }. None means no projection."""
        if not fields:
            return None
        return dict.fromkeys(fields, 1)
