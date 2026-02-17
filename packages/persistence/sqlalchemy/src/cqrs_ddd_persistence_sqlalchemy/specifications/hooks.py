"""
SQLAlchemy-specific resolution context for field resolution hooks.

Extends the pure-Python :class:`ResolutionContext` with a SQLAlchemy
``Select`` statement, model references, and an alias cache for
relationship traversal without duplicate JOINs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from cqrs_ddd_specifications.hooks import HookResult, ResolutionContext

if TYPE_CHECKING:
    from sqlalchemy.orm import DeclarativeBase
    from sqlalchemy.sql import Select


@dataclass
class SQLAlchemyResolutionContext(ResolutionContext):
    """
    SQLAlchemy-specific resolution context.

    Extends base context with statement, model, and JOIN capabilities.
    Hooks can ``isinstance`` check to see if they are running in a
    SQLAlchemy backend.

    Attributes:
        stmt: Current SQLAlchemy ``Select`` statement.
        model: Root SQLAlchemy model class.
        current_model: Model currently being traversed (follows rels).
        alias_cache: ``{dotted_path: aliased_model}`` to avoid dup joins.
    """

    stmt: Select[Any] | None = None
    model: type[DeclarativeBase] | None = None
    current_model: type[Any] | None = None
    alias_cache: dict[str, Any] = field(default_factory=dict)

    def get_column(self, name: str) -> Any:
        """
        Get a column from the current model.

        Raises:
            ValueError: If ``current_model`` is not set.
            AttributeError: If column doesn't exist.
        """
        if self.current_model is None:
            raise ValueError("current_model is not set")
        return getattr(self.current_model, name)

    @classmethod
    def create(
        cls,
        field_path: str,
        value: Any,
        stmt: Select[Any],
        model: type[DeclarativeBase],
        value_type: str | None = None,
        alias_cache: dict[str, Any] | None = None,
    ) -> SQLAlchemyResolutionContext:
        """Factory helper that fills ``parts`` / ``current_part`` automatically."""
        parts = field_path.split(".")
        return cls(
            field_path=field_path,
            parts=parts,
            current_part=parts[0] if parts else "",
            current_index=0,
            value=value,
            value_type=value_type,
            stmt=stmt,
            model=model,
            current_model=model,
            alias_cache=alias_cache or {},
        )


@dataclass
class SQLAlchemyHookResult(HookResult[Any]):
    """
    Extended hook result for SQLAlchemy.

    In addition to the base ``value`` / ``handled`` fields, allows hooks
    to return a modified statement and/or a new model for continued
    traversal.
    """

    new_statement: Select[Any] | None = None
    resolved_field: Any = None
    new_model: type[Any] | None = None
