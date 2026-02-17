"""String operators for SQLAlchemy."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from cqrs_ddd_specifications.operators import SpecificationOperator

from ..strategy import SQLAlchemyOperator

if TYPE_CHECKING:
    from sqlalchemy.sql.elements import ColumnElement


class LikeOperator(SQLAlchemyOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.LIKE

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        return cast("ColumnElement[bool]", column.like(value))


class NotLikeOperator(SQLAlchemyOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.NOT_LIKE

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        return cast("ColumnElement[bool]", ~column.like(value))


class ILikeOperator(SQLAlchemyOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.ILIKE

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        return cast("ColumnElement[bool]", column.ilike(value))


class ContainsOperator(SQLAlchemyOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.CONTAINS

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        return cast("ColumnElement[bool]", column.contains(value))


class IContainsOperator(SQLAlchemyOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.ICONTAINS

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        return cast("ColumnElement[bool]", column.ilike(f"%{value}%"))


class StartsWithOperator(SQLAlchemyOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.STARTSWITH

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        return cast("ColumnElement[bool]", column.startswith(value))


class IStartsWithOperator(SQLAlchemyOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.ISTARTSWITH

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        return cast("ColumnElement[bool]", column.ilike(f"{value}%"))


class EndsWithOperator(SQLAlchemyOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.ENDSWITH

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        return cast("ColumnElement[bool]", column.endswith(value))


class IEndsWithOperator(SQLAlchemyOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.IENDSWITH

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        return cast("ColumnElement[bool]", column.ilike(f"%{value}"))


class RegexOperator(SQLAlchemyOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.REGEX

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        return cast("ColumnElement[bool]", column.regexp_match(str(value)))


class IRegexOperator(SQLAlchemyOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.IREGEX

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        return cast("ColumnElement[bool]", column.regexp_match(str(value), flags="i"))
