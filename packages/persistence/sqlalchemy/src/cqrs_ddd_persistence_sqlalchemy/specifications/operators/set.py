"""Set operators for SQLAlchemy: in, not_in, between, not_between."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from cqrs_ddd_specifications.operators import SpecificationOperator

from ..strategy import SQLAlchemyOperator

if TYPE_CHECKING:
    from sqlalchemy.sql.elements import ColumnElement


class InOperator(SQLAlchemyOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.IN

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        return cast("ColumnElement[bool]", column.in_(value))


class NotInOperator(SQLAlchemyOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.NOT_IN

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        return cast("ColumnElement[bool]", ~column.in_(value))


class BetweenOperator(SQLAlchemyOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.BETWEEN

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        return cast("ColumnElement[bool]", column.between(value[0], value[1]))


class NotBetweenOperator(SQLAlchemyOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.NOT_BETWEEN

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        return cast("ColumnElement[bool]", ~column.between(value[0], value[1]))
