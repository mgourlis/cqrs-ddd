"""JSON operators for SQLAlchemy.

Note: The underlying implementation uses PostgreSQL JSONB operators
(@>, <@, ?, ?|, ?&) but the operator names are backend-agnostic
(json_contains, json_has_key, etc.) to allow future backends to
provide their own implementations.
"""

from __future__ import annotations

import json
from typing import Any, cast

from sqlalchemy import ColumnElement, func, literal_column

from cqrs_ddd_specifications.operators import SpecificationOperator

from ..strategy import SQLAlchemyOperator


class JsonContainsOperator(SQLAlchemyOperator):
    """``column @> value``"""

    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.JSON_CONTAINS

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        json_val = json.dumps(value) if isinstance(value, dict | list) else str(value)
        escaped = json_val.replace("'", "''")
        return cast(
            "ColumnElement[bool]",
            column.op("@>")(literal_column(f"'{escaped}'::jsonb")),
        )


class JsonContainedByOperator(SQLAlchemyOperator):
    """``column <@ value``"""

    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.JSON_CONTAINED_BY

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        json_val = json.dumps(value) if isinstance(value, dict | list) else str(value)
        escaped = json_val.replace("'", "''")
        return cast(
            "ColumnElement[bool]",
            column.op("<@")(literal_column(f"'{escaped}'::jsonb")),
        )


class JsonHasKeyOperator(SQLAlchemyOperator):
    """``column ? key``"""

    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.JSON_HAS_KEY

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        return cast("ColumnElement[bool]", column.has_key(str(value)))  # noqa: W601


class JsonHasAnyOperator(SQLAlchemyOperator):
    """``column ?| ARRAY[keys]``"""

    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.JSON_HAS_ANY

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        keys = [str(k) for k in (value if isinstance(value, list | tuple) else [value])]
        keys_str = ", ".join(f"'{k}'" for k in keys)
        return cast(
            "ColumnElement[bool]", column.op("?|")(literal_column(f"ARRAY[{keys_str}]"))
        )


class JsonHasAllOperator(SQLAlchemyOperator):
    """``column ?& ARRAY[keys]``"""

    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.JSON_HAS_ALL

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        keys = [str(k) for k in (value if isinstance(value, list | tuple) else [value])]
        keys_str = ", ".join(f"'{k}'" for k in keys)
        return cast(
            "ColumnElement[bool]", column.op("?&")(literal_column(f"ARRAY[{keys_str}]"))
        )


class JsonPathExistsOperator(SQLAlchemyOperator):
    """``jsonb_path_exists(column, path)``"""

    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.JSON_PATH_EXISTS

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        return func.jsonb_path_exists(column, value)
