"""
SQLAlchemy operator implementations and default registry.

Usage::

    from cqrs_ddd_persistence_sqlalchemy.specifications.operators import (
        DEFAULT_SQLA_REGISTRY,
    )

    expr = DEFAULT_SQLA_REGISTRY.apply(SpecificationOperator.EQ, column, value)
"""

from __future__ import annotations

from ..strategy import SQLAlchemyOperatorRegistry
from .fts import (
    FtsOperator,
    FtsPhraseOperator,
)
from .geometry import (
    BboxIntersectsOperator,
    ContainsGeomOperator,
    CrossesOperator,
    DisjointOperator,
    DistanceLtOperator,
    DWithinOperator,
    GeomEqualsOperator,
    IntersectsOperator,
    OverlapsOperator,
    TouchesOperator,
    WithinOperator,
)
from .jsonb import (
    JsonContainedByOperator,
    JsonContainsOperator,
    JsonHasAllOperator,
    JsonHasAnyOperator,
    JsonHasKeyOperator,
    JsonPathExistsOperator,
)
from .null import (
    IsEmptyOperator,
    IsNotEmptyOperator,
    IsNotNullOperator,
    IsNullOperator,
)
from .set import (
    BetweenOperator,
    InOperator,
    NotBetweenOperator,
    NotInOperator,
)
from .standard import (
    EqualOperator,
    GreaterEqualOperator,
    GreaterThanOperator,
    LessEqualOperator,
    LessThanOperator,
    NotEqualOperator,
)
from .string import (
    ContainsOperator,
    EndsWithOperator,
    IContainsOperator,
    IEndsWithOperator,
    ILikeOperator,
    IRegexOperator,
    IStartsWithOperator,
    LikeOperator,
    NotLikeOperator,
    RegexOperator,
    StartsWithOperator,
)


def build_default_sqla_registry() -> SQLAlchemyOperatorRegistry:
    """Create a registry with all built-in SQLAlchemy operators."""
    registry = SQLAlchemyOperatorRegistry()
    registry.register_all(
        # Standard comparison
        EqualOperator(),
        NotEqualOperator(),
        GreaterThanOperator(),
        LessThanOperator(),
        GreaterEqualOperator(),
        LessEqualOperator(),
        # Set
        InOperator(),
        NotInOperator(),
        BetweenOperator(),
        NotBetweenOperator(),
        # String
        LikeOperator(),
        NotLikeOperator(),
        ILikeOperator(),
        ContainsOperator(),
        IContainsOperator(),
        StartsWithOperator(),
        IStartsWithOperator(),
        EndsWithOperator(),
        IEndsWithOperator(),
        RegexOperator(),
        IRegexOperator(),
        # Null / empty
        IsNullOperator(),
        IsNotNullOperator(),
        IsEmptyOperator(),
        IsNotEmptyOperator(),
        # JSON
        JsonContainsOperator(),
        JsonContainedByOperator(),
        JsonHasKeyOperator(),
        JsonHasAnyOperator(),
        JsonHasAllOperator(),
        JsonPathExistsOperator(),
        # Geometry / PostGIS
        IntersectsOperator(),
        WithinOperator(),
        DWithinOperator(),
        BboxIntersectsOperator(),
        ContainsGeomOperator(),
        TouchesOperator(),
        CrossesOperator(),
        OverlapsOperator(),
        DisjointOperator(),
        GeomEqualsOperator(),
        DistanceLtOperator(),
        # Full-text search
        FtsOperator(),
        FtsPhraseOperator(),
    )
    return registry


DEFAULT_SQLA_REGISTRY: SQLAlchemyOperatorRegistry = build_default_sqla_registry()

__all__ = [
    "DEFAULT_SQLA_REGISTRY",
    "build_default_sqla_registry",
    "SQLAlchemyOperatorRegistry",
]
