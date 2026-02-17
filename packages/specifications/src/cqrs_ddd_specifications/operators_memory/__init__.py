"""
In-memory operator implementations.

Provides concrete MemoryOperator subclasses for each SpecificationOperator
and a ready-to-use default registry.

Usage::

    from cqrs_ddd_specifications.operators.memory import DEFAULT_REGISTRY

    result = DEFAULT_REGISTRY.evaluate(SpecificationOperator.EQ, actual, expected)
"""

from __future__ import annotations

from ..evaluator import MemoryOperatorRegistry
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
    AllOperator,
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


def build_default_registry() -> MemoryOperatorRegistry:
    """Create a registry with all built-in operators."""
    registry = MemoryOperatorRegistry()
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
        AllOperator(),
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
        # Full-text search
        FtsOperator(),
        FtsPhraseOperator(),
        # Geometry
        IntersectsOperator(),
        WithinOperator(),
        ContainsGeomOperator(),
        TouchesOperator(),
        CrossesOperator(),
        OverlapsOperator(),
        DisjointOperator(),
        GeomEqualsOperator(),
        DWithinOperator(),
        DistanceLtOperator(),
        BboxIntersectsOperator(),
    )
    return registry


DEFAULT_REGISTRY: MemoryOperatorRegistry = build_default_registry()

__all__ = [
    "DEFAULT_REGISTRY",
    "build_default_registry",
    "MemoryOperatorRegistry",
]
