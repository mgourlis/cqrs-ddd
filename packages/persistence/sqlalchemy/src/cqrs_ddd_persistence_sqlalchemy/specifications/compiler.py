"""
Compile a specification dictionary (AST) into a SQLAlchemy filter expression.

Uses the strategy pattern: each operator is an isolated class in
``operators/``, registered in a ``SQLAlchemyOperatorRegistry``.
The ``build_sqla_filter`` function walks the AST tree and delegates
leaf-node compilation to the registry.

Hooks
-----
Pass a list of ``ResolutionHook`` callables to intercept field resolution.
Each hook receives a :class:`SQLAlchemyResolutionContext` and may return a
:class:`SQLAlchemyHookResult` to override default column resolution (e.g.
for computed fields, JSON lookups, or relationship aliasing).

Query Options
-------------
``apply_query_options`` takes a ``Select`` statement and a ``QueryOptions``
instance and applies ordering, limit/offset, distinct, and group_by.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import ColumnElement, Select, and_, asc, desc, not_, or_

from cqrs_ddd_specifications.operators import SpecificationOperator

from .hooks import SQLAlchemyResolutionContext
from .operators import DEFAULT_SQLA_REGISTRY

if TYPE_CHECKING:
    from collections.abc import Sequence

    from cqrs_ddd_specifications.hooks import ResolutionHook

    from .strategy import SQLAlchemyOperatorRegistry

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_sqla_filter(
    model: type[Any],
    data: dict[str, Any],
    *,
    registry: SQLAlchemyOperatorRegistry | None = None,
    hooks: Sequence[ResolutionHook] | None = None,
) -> ColumnElement[bool]:
    """
    Build a SQLAlchemy filter expression from a specification dictionary.

    Args:
        model: The SQLAlchemy model class.
        data: Specification dictionary (JSON AST produced by ``spec.to_dict()``).
        registry: Optional custom operator registry.  Falls back to
            ``DEFAULT_SQLA_REGISTRY``.
        hooks: Optional list of :class:`ResolutionHook` callables for
            custom field resolution.

    Returns:
        SQLAlchemy Boolean expression.
    """
    reg = registry or DEFAULT_SQLA_REGISTRY
    return _compile_node(model, data, reg, hooks=hooks)


def _apply_order_by(stmt: Select[Any], model: type[Any], options: Any) -> Select[Any]:
    """Apply order_by option to statement."""
    if not (hasattr(options, "order_by") and options.order_by):
        return stmt

    order_clauses: list[Any] = []
    for field_expr in options.order_by:
        if field_expr.startswith("-"):
            col = getattr(model, field_expr[1:], None)
            if col is not None:
                order_clauses.append(desc(col))
        else:
            col = getattr(model, field_expr, None)
            if col is not None:
                order_clauses.append(asc(col))

    if order_clauses:
        return stmt.order_by(*order_clauses)
    return stmt


def _apply_limit_offset(stmt: Select[Any], options: Any) -> Select[Any]:
    """Apply limit and offset options to statement."""
    if hasattr(options, "limit") and options.limit is not None:
        stmt = stmt.limit(options.limit)
    if hasattr(options, "offset") and options.offset is not None:
        stmt = stmt.offset(options.offset)
    return stmt


def _apply_distinct(stmt: Select[Any], options: Any) -> Select[Any]:
    """Apply distinct option to statement."""
    if hasattr(options, "distinct") and options.distinct:
        return stmt.distinct()
    return stmt


def _apply_group_by(stmt: Select[Any], model: type[Any], options: Any) -> Select[Any]:
    """Apply group_by option to statement."""
    if not (hasattr(options, "group_by") and options.group_by):
        return stmt

    group_cols = [getattr(model, f) for f in options.group_by if hasattr(model, f)]
    if group_cols:
        return stmt.group_by(*group_cols)
    return stmt


def apply_query_options(
    stmt: Select[Any],
    model: type[Any],
    options: Any,
) -> Select[Any]:
    """
    Apply a ``QueryOptions`` instance to a SQLAlchemy ``Select`` statement.

    Handles: ``order_by``, ``limit``, ``offset``, ``distinct``,
    ``group_by``, and ``select_fields`` (projection).

    Args:
        stmt: The base ``Select`` statement.
        model: The SQLAlchemy model class (used for column lookups).
        options: A ``QueryOptions`` instance (typed as ``Any`` to avoid
            hard dependency on specifications package).

    Returns:
        The modified ``Select`` statement.
    """
    if options is None:
        return stmt

    stmt = _apply_order_by(stmt, model, options)
    stmt = _apply_limit_offset(stmt, options)
    stmt = _apply_distinct(stmt, options)
    return _apply_group_by(stmt, model, options)


# ---------------------------------------------------------------------------
# Internal compilation
# ---------------------------------------------------------------------------


def _compile_logical_operator(
    model: type[Any],
    data: dict[str, Any],
    registry: SQLAlchemyOperatorRegistry,
    op_str: str,
    hooks: Sequence[ResolutionHook] | None,
) -> ColumnElement[bool] | None:
    """Compile logical operators (AND, OR, NOT).

    Returns None if not a logical operator.
    """
    if op_str == SpecificationOperator.AND:
        conditions = [
            _compile_node(model, c, registry, hooks=hooks)
            for c in data.get("conditions", [])
        ]
        return and_(*conditions)

    if op_str == SpecificationOperator.OR:
        conditions = [
            _compile_node(model, c, registry, hooks=hooks)
            for c in data.get("conditions", [])
        ]
        return or_(*conditions)

    if op_str == SpecificationOperator.NOT:
        conditions = data.get("conditions", [])
        if not conditions and "condition" in data:
            inner_expr = _compile_node(model, data["condition"], registry, hooks=hooks)
        else:
            inner_expr = (
                and_(
                    *[
                        _compile_node(model, c, registry, hooks=hooks)
                        for c in conditions
                    ]
                )
                if len(conditions) > 1
                else _compile_node(model, conditions[0], registry, hooks=hooks)
            )
        return not_(inner_expr)

    return None


def _compile_leaf_node(
    model: type[Any],
    data: dict[str, Any],
    registry: SQLAlchemyOperatorRegistry,
    op_str: str,
    hooks: Sequence[ResolutionHook] | None,
) -> ColumnElement[bool]:
    """Compile leaf node (attribute-based conditions)."""
    attr: str | None = data.get("attr")
    val = data.get("val")

    if not attr:
        raise ValueError(f"Specification missing 'attr': {data}")

    # Try hooks first
    if hooks:
        column = _resolve_with_hooks(model, attr, val, hooks)
        if column is not None:
            op = SpecificationOperator(op_str)
            return registry.apply(op, column, val)

    # Relationship traversal (e.g. "posts.title")
    if "." in attr:
        rel_name, nested_attr = attr.split(".", 1)
        rel_attr = getattr(model, rel_name, None)

        if rel_attr is None:
            raise AttributeError(f"Model {model} has no relationship {rel_name}")

        target_model = rel_attr.property.mapper.class_
        nested_data = {"op": op_str, "attr": nested_attr, "val": val}
        inner_expr = _compile_node(target_model, nested_data, registry, hooks=hooks)

        if rel_attr.property.uselist:
            return cast("ColumnElement[bool]", rel_attr.any(inner_expr))
        return cast("ColumnElement[bool]", rel_attr.has(inner_expr))

    # Standard column
    column = getattr(model, attr, None)
    if column is None:
        raise AttributeError(f"Model {model} has no attribute {attr}")

    op = SpecificationOperator(op_str)
    return registry.apply(op, column, val)


def _compile_node(
    model: type[Any],
    data: dict[str, Any],
    registry: SQLAlchemyOperatorRegistry,
    *,
    hooks: Sequence[ResolutionHook] | None = None,
) -> ColumnElement[bool]:
    op_str = data.get("op", "").lower()

    # Try logical operators first
    logical_result = _compile_logical_operator(model, data, registry, op_str, hooks)
    if logical_result is not None:
        return logical_result

    # Otherwise compile as leaf node
    return _compile_leaf_node(model, data, registry, op_str, hooks)


def _resolve_with_hooks(
    model: type[Any],
    attr: str,
    val: Any,
    hooks: Sequence[ResolutionHook],
) -> Any | None:
    """
    Attempt to resolve a field via hooks.

    Returns the resolved column/expression if a hook handled it,
    or ``None`` to fall back to default resolution.
    """
    ctx = SQLAlchemyResolutionContext.create(
        field_path=attr,
        value=val,
        # stmt is not available during filter compilation
        stmt=None,  # type: ignore[arg-type]
        model=model,
    )
    for hook in hooks:
        result = hook(ctx)
        if result.handled:
            return result.value
    return None
