"""String operators -> $regex, $options (case-insensitive)."""

from __future__ import annotations

import re
from typing import Any

from cqrs_ddd_specifications.operators import SpecificationOperator

from ..exceptions import MongoQueryError


def _regex_escape(s: str) -> str:
    """Escape special regex characters in a literal string."""
    return re.escape(s)


def compile_string(field: str, op: str, val: Any) -> dict[str, Any] | None:
    """Compile string operators to MongoDB $regex. Returns None if not a string op."""
    try:
        spec_op = SpecificationOperator(op)
    except ValueError:
        return None
    if not isinstance(val, str):
        raise MongoQueryError(f"String operator {op} requires string value")
    case_insensitive = spec_op in (
        SpecificationOperator.ILIKE,
        SpecificationOperator.ICONTAINS,
        SpecificationOperator.ISTARTSWITH,
        SpecificationOperator.IENDSWITH,
        SpecificationOperator.IREGEX,
    )
    options = "i" if case_insensitive else ""
    if spec_op in (SpecificationOperator.CONTAINS, SpecificationOperator.ICONTAINS):
        pattern = _regex_escape(val)
        return {field: {"$regex": pattern, "$options": options}}
    if spec_op in (SpecificationOperator.STARTSWITH, SpecificationOperator.ISTARTSWITH):
        pattern = "^" + _regex_escape(val)
        return {field: {"$regex": pattern, "$options": options}}
    if spec_op in (SpecificationOperator.ENDSWITH, SpecificationOperator.IENDSWITH):
        pattern = _regex_escape(val) + "$"
        return {field: {"$regex": pattern, "$options": options}}
    if spec_op in (SpecificationOperator.LIKE, SpecificationOperator.ILIKE):
        # SQL LIKE: % = any, _ = single char
        pattern = _regex_escape(val).replace("%", ".*").replace("_", ".")
        return {field: {"$regex": f"^{pattern}$", "$options": options}}
    if spec_op in (SpecificationOperator.REGEX, SpecificationOperator.IREGEX):
        return {field: {"$regex": val, "$options": options}}
    if spec_op == SpecificationOperator.NOT_LIKE:
        pattern = _regex_escape(val).replace("%", ".*").replace("_", ".")
        return {field: {"$not": {"$regex": f"^{pattern}$"}}}
    return None
