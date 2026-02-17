"""
Tests for the enhanced specification compiler.

Covers:
- apply_query_options (ordering, limit/offset, distinct, group_by)
- build_sqla_filter with hooks
- SQLAlchemyResolutionContext construction
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import Column, Integer, String, select
from sqlalchemy.orm import DeclarativeBase

from cqrs_ddd_persistence_sqlalchemy.specifications.compiler import (
    apply_query_options,
    build_sqla_filter,
)
from cqrs_ddd_persistence_sqlalchemy.specifications.hooks import (
    SQLAlchemyResolutionContext,
)
from cqrs_ddd_specifications import QueryOptions
from cqrs_ddd_specifications.hooks import HookResult, ResolutionContext

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


class Widget(Base):
    __tablename__ = "widgets"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    status = Column(String)
    priority = Column(Integer)


# ---------------------------------------------------------------------------
# apply_query_options tests
# ---------------------------------------------------------------------------


def test_apply_query_options_limit_offset():
    stmt = select(Widget)
    opts = QueryOptions(limit=10, offset=5)
    result = apply_query_options(stmt, Widget, opts)
    compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
    assert "LIMIT" in compiled
    assert "OFFSET" in compiled


def test_apply_query_options_order_asc():
    stmt = select(Widget)
    opts = QueryOptions(order_by=["name"])
    result = apply_query_options(stmt, Widget, opts)
    compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
    assert "ORDER BY" in compiled
    assert "widgets.name ASC" in compiled


def test_apply_query_options_order_desc():
    stmt = select(Widget)
    opts = QueryOptions(order_by=["-priority"])
    result = apply_query_options(stmt, Widget, opts)
    compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
    assert "ORDER BY" in compiled
    assert "widgets.priority DESC" in compiled


def test_apply_query_options_distinct():
    stmt = select(Widget)
    opts = QueryOptions(distinct=True)
    result = apply_query_options(stmt, Widget, opts)
    compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
    assert "DISTINCT" in compiled


def test_apply_query_options_group_by():
    stmt = select(Widget)
    opts = QueryOptions(group_by=["status"])
    result = apply_query_options(stmt, Widget, opts)
    compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
    assert "GROUP BY" in compiled
    assert "widgets.status" in compiled


def test_apply_query_options_none_passthrough():
    stmt = select(Widget)
    result = apply_query_options(stmt, Widget, None)
    # Should return the statement unchanged
    assert str(result.compile()) == str(stmt.compile())


def test_apply_query_options_combined():
    stmt = select(Widget)
    opts = QueryOptions(
        limit=20,
        offset=10,
        order_by=["-priority", "name"],
        distinct=True,
    )
    result = apply_query_options(stmt, Widget, opts)
    compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
    assert "LIMIT" in compiled
    assert "OFFSET" in compiled
    assert "DISTINCT" in compiled
    assert "ORDER BY" in compiled


# ---------------------------------------------------------------------------
# build_sqla_filter with hooks
# ---------------------------------------------------------------------------


def test_build_sqla_filter_with_hook():
    """Hook intercepts field resolution and returns a column."""

    def status_alias_hook(ctx: ResolutionContext) -> HookResult[Any]:
        if ctx.field_path == "is_active":
            return HookResult(value=Widget.status, handled=True)
        return HookResult.skip()

    data = {"op": "=", "attr": "is_active", "val": "active"}
    expr = build_sqla_filter(Widget, data, hooks=[status_alias_hook])
    compiled = str(expr.compile())
    assert "widgets.status" in compiled


def test_build_sqla_filter_hook_skip_fallback():
    """Hook that skips falls back to default resolution."""

    def noop_hook(ctx: ResolutionContext) -> HookResult[Any]:
        return HookResult.skip()

    data = {"op": "=", "attr": "name", "val": "test"}
    expr = build_sqla_filter(Widget, data, hooks=[noop_hook])
    compiled = str(expr.compile())
    assert "widgets.name" in compiled


def test_build_sqla_filter_no_hooks_unchanged():
    """Without hooks, behavior is unchanged."""
    data = {"op": "=", "attr": "priority", "val": 5}
    expr = build_sqla_filter(Widget, data)
    compiled = str(expr.compile())
    assert "widgets.priority" in compiled


# ---------------------------------------------------------------------------
# SQLAlchemyResolutionContext tests
# ---------------------------------------------------------------------------


def test_sqla_resolution_context_create():
    ctx = SQLAlchemyResolutionContext.create(
        field_path="status",
        value="active",
        stmt=select(Widget),
        model=Widget,
    )
    assert ctx.field_path == "status"
    assert ctx.parts == ["status"]
    assert ctx.current_part == "status"
    assert ctx.model is Widget
    assert ctx.current_model is Widget
    assert ctx.is_last_part


def test_sqla_resolution_context_dotted():
    ctx = SQLAlchemyResolutionContext.create(
        field_path="author.name",
        value="John",
        stmt=select(Widget),
        model=Widget,
    )
    assert ctx.parts == ["author", "name"]
    assert ctx.current_part == "author"
    assert not ctx.is_last_part
    assert ctx.remaining_parts == ["name"]


def test_sqla_resolution_context_get_column():
    ctx = SQLAlchemyResolutionContext.create(
        field_path="name",
        value="test",
        stmt=select(Widget),
        model=Widget,
    )
    col = ctx.get_column("name")
    assert col is not None


def test_sqla_resolution_context_get_column_no_model():
    ctx = SQLAlchemyResolutionContext(
        field_path="test",
        parts=["test"],
        current_part="test",
        current_index=0,
        value=None,
        current_model=None,
    )
    with pytest.raises(ValueError, match="current_model is not set"):
        ctx.get_column("test")
