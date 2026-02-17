"""
Resolution hooks for field-path resolution.

These are pure-Python abstractions used by both memory evaluation and
persistence backends (SQLAlchemy, etc.).  The backend extends
:class:`ResolutionContext` with backend-specific capabilities and
provides its own hooks.

Ported from ``search_query_dsl.core.hooks``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, Protocol, TypeVar, cast

T = TypeVar("T")


@dataclass
class HookResult(Generic[T]):
    """
    Result from a resolution hook.

    Attributes:
        value: The resolved value (column, expression, etc.)
        handled: If ``True``, skip default resolution.
            If ``False``, continue with default.
    """

    value: T
    handled: bool = True

    @classmethod
    def skip(cls) -> HookResult[None]:
        """Return to let default resolution handle it."""
        # Use cast to allow None value for HookResult[None]
        result = cls(value=None, handled=False)  # type: ignore[arg-type]
        return cast("HookResult[None]", result)


@dataclass
class ResolutionContext:
    """
    Base context for field resolution hooks.

    Backends extend this with backend-specific capabilities.
    Hooks receive this context and can return :class:`HookResult` to
    override the default field resolution behaviour.

    Attributes:
        field_path: Full dot-notation path (e.g. ``"element_type.label"``).
        parts: Split path parts (e.g. ``["element_type", "label"]``).
        current_part: The part currently being resolved.
        current_index: Index of ``current_part`` in ``parts``.
        value: The condition value being compared.
        value_type: Optional type hint for value casting.
    """

    field_path: str
    parts: list[str] = field(default_factory=list)
    current_part: str = ""
    current_index: int = 0
    value: Any = None
    value_type: str | None = None

    @property
    def remaining_parts(self) -> list[str]:
        """Parts after ``current_part``."""
        return self.parts[self.current_index + 1 :]

    @property
    def is_last_part(self) -> bool:
        """True if ``current_part`` is the final part of the path."""
        return self.current_index == len(self.parts) - 1

    @classmethod
    def from_field(
        cls,
        field_path: str,
        value: Any,
        value_type: str | None = None,
    ) -> ResolutionContext:
        """Create context from a field path."""
        parts = field_path.split(".")
        return cls(
            field_path=field_path,
            parts=parts,
            current_part=parts[0] if parts else "",
            current_index=0,
            value=value,
            value_type=value_type,
        )


class ResolutionHook(Protocol):
    """
    Protocol for field resolution hooks.

    A hook receives a :class:`ResolutionContext` and returns a
    :class:`HookResult`.  If ``result.handled`` is ``True``, the
    default resolution is skipped and ``result.value`` is used.
    """

    def __call__(self, ctx: ResolutionContext) -> HookResult[Any]:
        ...
