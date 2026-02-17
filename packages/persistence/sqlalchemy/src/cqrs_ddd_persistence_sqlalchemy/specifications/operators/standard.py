"""Standard comparison operators for SQLAlchemy."""

from __future__ import annotations

import operator as op_module
from typing import TYPE_CHECKING, Any, cast

from cqrs_ddd_specifications.operators import SpecificationOperator

from ..strategy import SQLAlchemyOperator

if TYPE_CHECKING:
    from sqlalchemy.sql.elements import ColumnElement


class EqualOperator(SQLAlchemyOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.EQ

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        return cast("ColumnElement[bool]", op_module.eq(column, value))


class NotEqualOperator(SQLAlchemyOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.NE

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        return cast("ColumnElement[bool]", op_module.ne(column, value))


class GreaterThanOperator(SQLAlchemyOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.GT

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        return cast("ColumnElement[bool]", op_module.gt(column, value))


class LessThanOperator(SQLAlchemyOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.LT

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        return cast("ColumnElement[bool]", op_module.lt(column, value))


class GreaterEqualOperator(SQLAlchemyOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.GE

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        return cast("ColumnElement[bool]", op_module.ge(column, value))


class LessEqualOperator(SQLAlchemyOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.LE

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        return cast("ColumnElement[bool]", op_module.le(column, value))
