"""
Fluent builder for constructing specification trees.

Example::

    spec = (
        SpecificationBuilder()
        .where("status", "=", "active")
        .where("age", ">", 18)
        .build()
    )
    # → AND(status == "active", age > 18)

    spec = (
        SpecificationBuilder()
        .or_group()
            .where("role", "=", "admin")
            .where("role", "=", "superuser")
        .end_group()
        .where("active", "=", True)
        .build()
    )
    # → AND(OR(role == "admin", role == "superuser"), active == True)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .ast import AttributeSpecification
from .base import AndSpecification, NotSpecification, OrSpecification
from .operators_memory import build_default_registry

if TYPE_CHECKING:
    from .evaluator import MemoryOperatorRegistry
    from .operators import SpecificationOperator

try:
    from cqrs_ddd_core.domain.specification import ISpecification
except ImportError:  # pragma: no cover
    ISpecification = Any  # type: ignore[assignment,misc]


class SpecificationBuilder:
    """
    Fluent builder for composing specification trees.

    Conditions added at the same level are combined with AND by default.
    Use ``or_group()`` / ``and_group()`` / ``not_group()`` for explicit
    grouping, and ``end_group()`` to close the current group.
    """

    def __init__(
        self,
        registry: MemoryOperatorRegistry | None = None,
    ) -> None:
        self._registry = registry if registry is not None else build_default_registry()
        self._specs: list[ISpecification[Any]] = []
        self._stack: list[tuple[str, list[ISpecification[Any]]]] = []
        # stack items: (group_operator, specs_list)

    # -- leaf conditions -----------------------------------------------------

    def where(
        self,
        attr: str,
        op: SpecificationOperator | str,
        val: Any = None,
    ) -> SpecificationBuilder:
        """Add a single attribute condition to the current group."""
        self._current_list().append(
            AttributeSpecification(attr, op, val, registry=self._registry)
        )
        return self

    def add(self, spec: ISpecification[Any]) -> SpecificationBuilder:
        """Add an already-constructed specification to the current group."""
        self._current_list().append(spec)
        return self

    # -- grouping ------------------------------------------------------------

    def and_group(self) -> SpecificationBuilder:
        """Open a new AND group.  Close with ``end_group()``."""
        self._stack.append(("and", []))
        return self

    def or_group(self) -> SpecificationBuilder:
        """Open a new OR group.  Close with ``end_group()``."""
        self._stack.append(("or", []))
        return self

    def not_group(self) -> SpecificationBuilder:
        """Open a new NOT group (single child).  Close with ``end_group()``."""
        self._stack.append(("not", []))
        return self

    def end_group(self) -> SpecificationBuilder:
        """Close the current group and add it to the parent."""
        if not self._stack:
            raise ValueError("No open group to close")
        group_op, specs = self._stack.pop()
        composite = _combine(group_op, specs)
        self._current_list().append(composite)
        return self

    # -- build ---------------------------------------------------------------

    def build(self) -> ISpecification[Any]:
        """
        Finalise and return the composed specification.

        If there is a single condition, returns it directly.
        Multiple conditions at the top level are combined with AND.

        Raises:
            ValueError: If groups are still open or no conditions were added.
        """
        if self._stack:
            raise ValueError(
                f"{len(self._stack)} group(s) still open — "
                f"call end_group() before build()"
            )
        if not self._specs:
            raise ValueError("No conditions added to builder")
        return _combine("and", self._specs)

    def reset(self) -> SpecificationBuilder:
        """Clear all conditions and return ``self`` for reuse."""
        self._specs.clear()
        self._stack.clear()
        return self

    # -- internals -----------------------------------------------------------

    def _current_list(self) -> list[ISpecification[Any]]:
        """Return the list that new specs should be appended to."""
        if self._stack:
            return self._stack[-1][1]
        return self._specs


def _combine(op: str, specs: list[ISpecification[Any]]) -> ISpecification[Any]:
    """Combine a list of specs with the given logical operator."""
    if not specs:
        raise ValueError("Cannot create an empty group")
    if op == "and":
        return specs[0] if len(specs) == 1 else AndSpecification(*specs)
    if op == "or":
        return specs[0] if len(specs) == 1 else OrSpecification(*specs)
    if op == "not":
        if len(specs) != 1:
            raise ValueError("NOT group must contain exactly one condition")
        return NotSpecification(specs[0])
    raise ValueError(f"Unknown group operator: {op}")
