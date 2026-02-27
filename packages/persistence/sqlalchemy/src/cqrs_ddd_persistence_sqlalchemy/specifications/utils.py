"""
SQLAlchemy-specific utilities for the specifications compiler.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy.schema import Table
from sqlalchemy.sql.selectable import Join

if TYPE_CHECKING:
    from sqlalchemy.sql import Select


def extract_tables_from_statement(stmt: Select[Any]) -> list[Table]:
    """
    Extract all tables present in the FROM clause of a statement
    (including joins).

    Useful for hooks to check if a table is already joined.
    """
    tables: set[Table] = set()
    for from_obj in stmt.get_final_froms():
        _extract_tables_recursive(from_obj, tables)
    return list(tables)


def _extract_tables_recursive(from_obj: object, tables: set[Table]) -> None:
    """Recursively extract tables from a FROM object (Table or Join)."""
    if isinstance(from_obj, Join):
        _extract_tables_recursive(from_obj.left, tables)
        _extract_tables_recursive(from_obj.right, tables)
    elif hasattr(from_obj, "element"):  # AliasedClass
        element = from_obj.element
        if hasattr(element, "__table__"):
            tables.add(element.__table__)
        elif hasattr(from_obj, "__table__"):
            tables.add(from_obj.__table__)
    elif hasattr(from_obj, "__table__"):  # DeclarativeBase model
        tables.add(from_obj.__table__)
    elif isinstance(from_obj, Table):
        tables.add(from_obj)
