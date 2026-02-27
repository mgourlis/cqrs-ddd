"""FilterSyntax — pluggable syntax (colon-separated, JSON, bracket)."""

from __future__ import annotations

from typing import Any

from cqrs_ddd_specifications.operators import SpecificationOperator

from .exceptions import FilterParseError

# Map common names to SpecificationOperator values
_OP_ALIASES: dict[str, str] = {
    # Tier 1: Standard comparison operators
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
    # Tier 2: String operations (enhanced)
    "contains": SpecificationOperator.CONTAINS,
    "icontains": SpecificationOperator.ICONTAINS,
    "like": SpecificationOperator.LIKE,
    "ilike": SpecificationOperator.ILIKE,
    "startswith": SpecificationOperator.STARTSWITH,
    "starts_with": SpecificationOperator.STARTSWITH,
    "endswith": SpecificationOperator.ENDSWITH,
    "ends_with": SpecificationOperator.ENDSWITH,
    # Tier 2: Null checks
    "is_null": SpecificationOperator.IS_NULL,
    "null": SpecificationOperator.IS_NULL,
    "is_not_null": SpecificationOperator.IS_NOT_NULL,
    "not_null": SpecificationOperator.IS_NOT_NULL,
    # Tier 2: Range queries
    "between": SpecificationOperator.BETWEEN,
    "not_between": SpecificationOperator.NOT_BETWEEN,
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

        # Smart split: split by comma but preserve commas in values after colon
        # Example: "field:op:val1,val2,field2:op2:val3" -> ["field:op:val1,val2", ...]
        parts = self._smart_split(raw)

        for part in parts:
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
                val = self._parse_value(value, op_str)
            except ValueError as e:
                raise FilterParseError(f"Invalid value {value!r}: {e}") from e
            clauses.append({"op": op_str, "attr": field, "val": val})
        if not clauses:
            return {}
        if len(clauses) == 1:
            return clauses[0]
        return {"op": SpecificationOperator.AND.value, "conditions": clauses}

    def _smart_split(self, raw: str) -> list[str]:
        """
        Split filter string by commas, but preserve commas within field:op:value groups.

        Example:
            "field:op:val1,val2,field2:op2:val3"
            → ["field:op:val1,val2", "field2:op2:val3"]

        Strategy:
        1. Split by comma
        2. For each segment, check if it has 2+ colons (complete field:op:value)
        3. If not complete, append to previous segment
        """
        segments = raw.split(",")
        clauses = []

        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue

            # Check if this segment is a complete clause (has 2+ colons)
            colon_count = segment.count(":")

            if colon_count >= 2:
                # Complete clause - start new clause
                clauses.append(segment)
            elif clauses:
                # Incomplete segment - append to previous clause's value
                clauses[-1] += "," + segment
            else:
                # First segment is incomplete (malformed input)
                clauses.append(segment)

        return clauses

    def _parse_value(self, s: str, op: str | None = None) -> Any:
        """
        Parse string value to appropriate Python type.

        Args:
            s: String value to parse
            op: Operator being used (for context-specific parsing)

        Returns:
            Parsed value (bool, int, float, list, None, or str)
        """
        # Handle boolean values
        if s.lower() == "true":
            return True
        if s.lower() == "false":
            return False

        # Handle null values
        if s.lower() == "null":
            return None

        # Handle arrays for set/range operators
        if op in ("in", "not_in", "between", "not_between") and "," in s:
            return [self._parse_simple_value(v.strip()) for v in s.split(",")]

        # Try parsing as number or fallback to string
        return self._parse_simple_value(s)

    def _parse_simple_value(self, s: str) -> Any:
        """Parse single value (int, float, or string)."""
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
        """Normalise JSON filter dict to specification format."""
        # Handle leaf node (field/operator/value)
        if "attr" in data and "op" in data:
            data = dict(data)
            if "value" in data and "val" not in data:
                data["val"] = data.pop("value")
            return data

        # Handle composite AND
        if "and" in data:
            return {
                "op": SpecificationOperator.AND.value,
                "conditions": [self._normalise(c) for c in data["and"]],
            }

        # Handle composite OR
        if "or" in data:
            return {
                "op": SpecificationOperator.OR.value,
                "conditions": [self._normalise(c) for c in data["or"]],
            }

        # Handle alternative field format
        if "field" in data and "op" in data:
            op = data["op"]
            op_val = _OP_ALIASES.get(op, op)
            op_str = getattr(op_val, "value", op_val)

            # Validate operator exists
            valid_ops = [e.value for e in SpecificationOperator]
            if op_str not in valid_ops:
                raise FilterParseError(
                    f"Unknown operator '{op}'. Valid operators: {', '.join(valid_ops)}"
                )

            return {
                "op": op_str,
                "attr": data["field"],
                "val": data.get("value", data.get("val")),
            }

        return data
