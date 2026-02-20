"""FieldWhitelist — per-resource filterable/sortable/projectable fields."""

from __future__ import annotations

from .exceptions import FieldNotAllowedError


class FieldWhitelist:
    """Per-resource allowed fields and operators."""

    def __init__(
        self,
        *,
        filterable_fields: dict[str, set[str]] | None = None,
        sortable_fields: set[str] | None = None,
        projectable_fields: set[str] | None = None,
    ) -> None:
        self.filterable_fields = filterable_fields or {}
        self.sortable_fields = sortable_fields or set()
        self.projectable_fields = projectable_fields or set()

    def allow_filter(self, field: str, op: str) -> None:
        """Raise FieldNotAllowedError if field or operator is not allowed."""
        if field not in self.filterable_fields:
            raise FieldNotAllowedError(f"Field {field!r} is not filterable")
        allowed_ops = self.filterable_fields[field]
        op_normalized = _OP_TO_ALIAS.get(op, op)
        if op_normalized not in allowed_ops and op not in allowed_ops:
            raise FieldNotAllowedError(
                f"Operator {op!r} not allowed for field {field!r}"
            )

    def allow_sort(self, field: str) -> None:
        if field not in self.sortable_fields:
            raise FieldNotAllowedError(f"Field {field!r} is not sortable")

    def allow_project(self, field: str) -> None:
        if field not in self.projectable_fields:
            raise FieldNotAllowedError(f"Field {field!r} is not projectable")


_OP_TO_ALIAS = {"=": "eq", "!=": "ne", ">": "gt", ">=": "gte", "<": "lt", "<=": "lte"}
