"""
Specification exception hierarchy with fuzzy-match suggestions.

All exceptions inherit from ``SpecificationError`` and provide
``to_dict()`` for API-friendly error responses.
"""

from __future__ import annotations

from difflib import get_close_matches
from typing import Any


class SpecificationError(Exception):
    """Base exception for all specification errors."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.__class__.__name__,
            "message": str(self),
        }


class ValidationError(SpecificationError):
    """Specification structure validation failed."""

    def __init__(self, message: str, path: str | None = None) -> None:
        self.message = message
        self.path = path
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": "VALIDATION_ERROR",
            "message": self.message,
            "path": self.path,
        }


class OperatorNotFoundError(SpecificationError):
    """
    Unknown operator specified.

    Provides fuzzy-matched suggestions for likely intended operators.
    """

    def __init__(self, operator: str, valid_operators: list[str]) -> None:
        self.operator = operator
        self.valid_operators = valid_operators
        self.suggestions = get_close_matches(operator, valid_operators, n=3, cutoff=0.6)

        message = f"Unknown operator: '{operator}'."
        if self.suggestions:
            message += f" Did you mean: {', '.join(self.suggestions)}?"
        message += f" Valid operators: {', '.join(sorted(valid_operators)[:10])}..."
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": "OPERATOR_NOT_FOUND",
            "operator": self.operator,
            "suggestions": self.suggestions,
            "valid_operators": sorted(self.valid_operators),
        }


class FieldNotFoundError(SpecificationError):
    """
    Invalid field path with helpful suggestions.

    Uses fuzzy matching to suggest similar valid field names.

    Example error message::

        Invalid field 'element_type' on model 'ElementModel'.
        Did you mean one of these?
          • element_type
          • element_types

        Available fields: id, name, label, element_type, ...
    """

    def __init__(
        self,
        invalid_field: str,
        model_name: str,
        available_fields: list[str],
        full_path: str | None = None,
        cutoff: float = 0.6,
    ) -> None:
        self.invalid_field = invalid_field
        self.model_name = model_name
        self.available_fields = available_fields
        self.full_path = full_path or invalid_field

        self.suggestions = get_close_matches(
            invalid_field, available_fields, n=5, cutoff=cutoff
        )

        message = self._build_message()
        super().__init__(message)

    def _build_message(self) -> str:
        lines = [f"Invalid field '{self.invalid_field}' on '{self.model_name}'."]
        if self.suggestions:
            lines.append("Did you mean one of these?")
            for s in self.suggestions:
                lines.append(f"  • {s}")

        sorted_fields = sorted(self.available_fields)
        preview = ", ".join(sorted_fields[:15])
        if len(sorted_fields) > 15:
            preview += ", ..."
        lines.append(f"Available fields: {preview}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": "FIELD_NOT_FOUND",
            "field": self.invalid_field,
            "model": self.model_name,
            "full_path": self.full_path,
            "suggestions": self.suggestions,
            "available_fields": sorted(self.available_fields),
        }


class RelationshipTraversalError(ValidationError):
    """
    Error when trying to traverse a field that is not a relationship.

    Happens when a query path like ``name.something`` is used, but
    ``name`` is a scalar column, not a relationship to another model.
    """

    def __init__(
        self,
        field: str,
        model_name: str,
        full_path: str | None = None,
    ) -> None:
        self.field = field
        self.model_name = model_name
        self.full_path = full_path or field

        message = (
            f"Cannot traverse '{field}' on '{model_name}': "
            f"it is not a relationship. Full path: '{self.full_path}'"
        )
        super().__init__(message, path=full_path)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": "RELATIONSHIP_TRAVERSAL_ERROR",
            "field": self.field,
            "model": self.model_name,
            "full_path": self.full_path,
        }


class FieldNotQueryableError(ValidationError):
    """
    Error when trying to query a field that exists but is not
    a valid column/attribute (e.g. a plain Python method or property).
    """

    def __init__(
        self,
        field: str,
        model_name: str,
        available_fields: list[str],
        full_path: str | None = None,
    ) -> None:
        self.field = field
        self.model_name = model_name
        self.available_fields = available_fields
        self.full_path = full_path or field
        self.suggestions = get_close_matches(field, available_fields, n=3, cutoff=0.6)

        message = (
            f"Field '{field}' on '{model_name}' exists but is not "
            f"queryable (not a mapped column or hybrid property). "
            f"Full path: '{self.full_path}'"
        )
        if self.suggestions:
            message += f"\nDid you mean: {', '.join(self.suggestions)}?"
        super().__init__(message, path=full_path)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": "FIELD_NOT_QUERYABLE",
            "field": self.field,
            "model": self.model_name,
            "full_path": self.full_path,
            "suggestions": self.suggestions,
            "available_fields": sorted(self.available_fields),
        }
