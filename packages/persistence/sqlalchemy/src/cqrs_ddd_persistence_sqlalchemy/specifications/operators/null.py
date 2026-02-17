"""Null / empty check operators for SQLAlchemy."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from cqrs_ddd_specifications.operators import SpecificationOperator

from ..strategy import SQLAlchemyOperator

if TYPE_CHECKING:
    from sqlalchemy.sql.elements import ColumnElement


class IsNullOperator(SQLAlchemyOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.IS_NULL

    def apply(self, column: Any, _value: Any) -> ColumnElement[bool]:
        return cast("ColumnElement[bool]", column.is_(None))


class IsNotNullOperator(SQLAlchemyOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.IS_NOT_NULL

    def apply(self, column: Any, _value: Any) -> ColumnElement[bool]:
        return cast("ColumnElement[bool]", column.is_not(None))


class IsEmptyOperator(SQLAlchemyOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.IS_EMPTY

    def apply(self, column: Any, _value: Any) -> ColumnElement[bool]:
        return cast("ColumnElement[bool]", column == "")


class IsNotEmptyOperator(SQLAlchemyOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.IS_NOT_EMPTY

    def apply(self, column: Any, _value: Any) -> ColumnElement[bool]:
        return cast("ColumnElement[bool]", column != "")
