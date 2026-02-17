"""Full-text search operators for SQLAlchemy (PostgreSQL)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import ColumnElement, func

from cqrs_ddd_specifications.operators import SpecificationOperator

from ..strategy import SQLAlchemyOperator


class FtsOperator(SQLAlchemyOperator):
    """``to_tsvector(column) @@ to_tsquery(value)``"""

    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.FTS

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        return func.to_tsvector(column).op("@@")(func.to_tsquery(value))


class FtsPhraseOperator(SQLAlchemyOperator):
    """``to_tsvector(column) @@ phraseto_tsquery(value)``"""

    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.FTS_PHRASE

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        return func.to_tsvector(column).op("@@")(func.phraseto_tsquery(value))
