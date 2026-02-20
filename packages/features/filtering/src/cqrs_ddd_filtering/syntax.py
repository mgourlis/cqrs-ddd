"""FilterSyntax — pluggable syntax (colon-separated, JSON, bracket)."""

from __future__ import annotations

from typing import Any

from cqrs_ddd_specifications.operators import SpecificationOperator

from .exceptions import FilterParseError

# Map common names to SpecificationOperator values
_OP_ALIASES: dict[str, str] = {
    "eq": SpecificationOperator.EQ,
    "=": SpecificationOperator.EQ,
    "ne": SpecificationOperator.NE,
    "!=": SpecificationOperator.NE,
    "gt": SpecificationOperator.GT,
    ">": SpecificationOperator.GT,
    "gte": SpecificationOperator.GE,
    ">=": SpecificationOperator.GE,
    "lt": SpecificationOperator.LT,
    "<": SpecificationOperator.LT,
    "lte": SpecificationOperator.LE,
    "<=": SpecificationOperator.LE,
    "in": SpecificationOperator.IN,
    "not_in": SpecificationOperator.NOT_IN,
    "contains": SpecificationOperator.CONTAINS,
    "icontains": SpecificationOperator.ICONTAINS,
}


class FilterSyntax:
    """Base for filter syntax parsers."""

    def parse_filter(self, raw: Any) -> dict[str, Any]:
        """Parse raw input to specification dict (op, attr, val or conditions)."""
        raise NotImplementedError


class ColonSeparatedSyntax(FilterSyntax):
    """Parse field:op:value,field2:op2:value2 (comma-separated clauses, AND)."""

    def parse_filter(self, raw: Any) -> dict[str, Any]:
        if not raw or not isinstance(raw, str):
            return {}
        clauses = []
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            tokens = part.split(":", 2)
            if len(tokens) != 3:
                raise FilterParseError(f"Expected field:op:value, got: {part!r}")
            field, op, value = (
                tokens[0].strip(),
                tokens[1].strip().lower(),
                tokens[2].strip(),
            )
            op_val = _OP_ALIASES.get(op, op)
            op_str = getattr(op_val, "value", op_val)
            try:
                val = self._parse_value(value)
            except ValueError as e:
                raise FilterParseError(f"Invalid value {value!r}: {e}") from e
            clauses.append({"op": op_str, "attr": field, "val": val})
        if not clauses:
            return {}
        if len(clauses) == 1:
            return clauses[0]
        return {"op": SpecificationOperator.AND.value, "conditions": clauses}

    def _parse_value(self, s: str) -> Any:
        if s.lower() == "true":
            return True
        if s.lower() == "false":
            return False
        if s.lower() == "null":
            return None
        try:
            return int(s)
        except ValueError:
            pass
        try:
            return float(s)
        except ValueError:
            pass
        return s


class JsonFilterSyntax(FilterSyntax):
    """Parse JSON object: {"and": [{"field": "x", "op": "eq", "value": "y"}]}."""

    def parse_filter(self, raw: Any) -> dict[str, Any]:
        if raw is None:
            return {}
        if isinstance(raw, dict):
            return self._normalise(raw)
        if isinstance(raw, str):
            import json

            try:
                data = json.loads(raw)
            except json.JSONDecodeError as e:
                raise FilterParseError(str(e)) from e
            return self._normalise(data) if isinstance(data, dict) else {}
        return {}

    def _normalise(self, data: dict[str, Any]) -> dict[str, Any]:
        if "attr" in data and "op" in data:
            data = dict(data)
            if "value" in data and "val" not in data:
                data["val"] = data.pop("value")
            return data
        if "and" in data:
            return {
                "op": SpecificationOperator.AND.value,
                "conditions": [self._normalise(c) for c in data["and"]],
            }
        if "or" in data:
            return {
                "op": SpecificationOperator.OR.value,
                "conditions": [self._normalise(c) for c in data["or"]],
            }
        if "field" in data and "op" in data:
            op = data["op"]
            op_val = _OP_ALIASES.get(op, op)
            op_str = getattr(op_val, "value", op_val)
            return {
                "op": op_str,
                "attr": data["field"],
                "val": data.get("value", data.get("val")),
            }
        return data
