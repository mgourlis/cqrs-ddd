"""Tests for SQLAlchemy specifications utils (extract_tables_from_statement)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Column, Integer, MetaData, String, Table, select

from cqrs_ddd_persistence_sqlalchemy.specifications.utils import (
    _extract_tables_recursive,
    extract_tables_from_statement,
)

if TYPE_CHECKING:
    from sqlalchemy.sql.selectable import Join

_metadata = MetaData()


def test_extract_tables_single_table() -> None:
    t = Table("users", _metadata, Column("id", Integer), Column("name", String))
    stmt = select(t)
    tables = extract_tables_from_statement(stmt)
    assert len(tables) == 1
    assert tables[0] is t


def test_extract_tables_join() -> None:
    a = Table("a", _metadata, Column("id", Integer))
    b = Table("b", _metadata, Column("id", Integer), Column("a_id", Integer))
    j = a.join(b, a.c.id == b.c.a_id)
    stmt = select(a).select_from(j)
    tables = extract_tables_from_statement(stmt)
    assert len(tables) == 2
    assert a in tables
    assert b in tables


def test_extract_tables_recursive_join() -> None:
    left = Table("left_t", _metadata, Column("id", Integer))
    right = Table("right_t", _metadata, Column("id", Integer))
    j: Join = left.join(right, left.c.id == right.c.id)
    tables_set: set = set()
    _extract_tables_recursive(j, tables_set)
    assert left in tables_set
    assert right in tables_set


def test_extract_tables_recursive_plain_table() -> None:
    t = Table("single", _metadata, Column("id", Integer))
    tables_set: set = set()
    _extract_tables_recursive(t, tables_set)
    assert t in tables_set
