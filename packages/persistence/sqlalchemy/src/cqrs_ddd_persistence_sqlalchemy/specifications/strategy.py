"""
SQLAlchemy operator compilation strategy.

Provides the ``SQLAlchemyOperator`` protocol, a registry, and a
default set of built-in operator implementations structured in
the same strategy pattern as the in-memory evaluator.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy import ColumnElement

    from cqrs_ddd_specifications.operators import SpecificationOperator


class SQLAlchemyOperator(ABC):
    """
    Strategy interface for compiling a specification operator
    into a SQLAlchemy ``ColumnElement[bool]``.
    """

    @property
    @abstractmethod
    def name(self) -> SpecificationOperator:
        """The operator this strategy handles."""
        ...

    @abstractmethod
    def apply(
        self,
        column: Any,
        value: Any,
    ) -> ColumnElement[bool]:
        """
        Build a SQLAlchemy filter clause.

        Args:
            column: A SQLAlchemy column or instrumented attribute.
            value: The condition value from the specification.

        Returns:
            A SQLAlchemy boolean expression.
        """
        ...


class SQLAlchemyOperatorRegistry:
    """
    Registry of ``SQLAlchemyOperator`` instances keyed by
    :class:`SpecificationOperator`.
    """

    def __init__(self) -> None:
        self._operators: dict[SpecificationOperator, SQLAlchemyOperator] = {}

    def register(self, operator: SQLAlchemyOperator) -> None:
        self._operators[operator.name] = operator

    def register_all(self, *operators: SQLAlchemyOperator) -> None:
        for op in operators:
            self.register(op)

    def unregister(self, name: SpecificationOperator) -> None:
        self._operators.pop(name, None)

    def get(self, name: SpecificationOperator) -> SQLAlchemyOperator | None:
        return self._operators.get(name)

    def has(self, name: SpecificationOperator) -> bool:
        return name in self._operators

    @property
    def supported_operators(self) -> set[SpecificationOperator]:
        return set(self._operators.keys())

    def apply(
        self,
        name: SpecificationOperator,
        column: Any,
        value: Any,
    ) -> ColumnElement[bool]:
        """
        Look up the operator and apply.

        Raises:
            ValueError: If the operator is not registered.
        """
        op = self.get(name)
        if op is None:
            raise ValueError(f"Unsupported operator for SQLAlchemy: {name}")
        return op.apply(column, value)
