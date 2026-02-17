"""
In-memory operator evaluation strategy.

Provides the MemoryOperator protocol and a default registry
that maps SpecificationOperator → evaluation function.

New operators are added by subclassing MemoryOperator and
registering via ``register()`` or ``register_func()``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .operators import SpecificationOperator


class MemoryOperator(ABC):
    """
    Strategy interface for in-memory operator evaluation.

    Each operator is an isolated class with a single ``evaluate`` method.
    """

    @property
    @abstractmethod
    def name(self) -> SpecificationOperator:
        """The operator this strategy handles."""
        ...

    @abstractmethod
    def evaluate(
        self,
        field_value: Any,
        condition_value: Any,
    ) -> bool:
        """
        Evaluate the operator against concrete values.

        Args:
            field_value: The actual value resolved from the candidate object.
            condition_value: The value provided in the specification.

        Returns:
            True if the condition is satisfied.
        """
        ...


class MemoryOperatorRegistry:
    """
    Registry of MemoryOperator instances keyed by SpecificationOperator.

    Usage::

        registry = MemoryOperatorRegistry()
        registry.register(EqualOperator())

        result = registry.evaluate(SpecificationOperator.EQ, actual, expected)
    """

    def __init__(self) -> None:
        self._operators: dict[SpecificationOperator, MemoryOperator] = {}

    # -- registration --------------------------------------------------------

    def register(self, operator: MemoryOperator) -> None:
        """Register an operator strategy instance."""
        self._operators[operator.name] = operator

    def register_all(self, *operators: MemoryOperator) -> None:
        """Register multiple operator strategy instances at once."""
        for op in operators:
            self.register(op)

    def unregister(self, name: SpecificationOperator) -> None:
        """Remove an operator from the registry."""
        self._operators.pop(name, None)

    # -- look-up -------------------------------------------------------------

    def get(self, name: SpecificationOperator) -> MemoryOperator | None:
        """Return the registered operator or ``None``."""
        return self._operators.get(name)

    def has(self, name: SpecificationOperator) -> bool:
        return name in self._operators

    @property
    def supported_operators(self) -> set[SpecificationOperator]:
        return set(self._operators.keys())

    # -- evaluation shortcut -------------------------------------------------

    def evaluate(
        self,
        name: SpecificationOperator,
        field_value: Any,
        condition_value: Any,
    ) -> bool:
        """
        Look up the operator and evaluate.

        Raises:
            ValueError: If the operator is not registered.
        """
        op = self.get(name)
        if op is None:
            raise ValueError(f"Unsupported operator for in-memory evaluation: {name}")
        return op.evaluate(field_value, condition_value)
