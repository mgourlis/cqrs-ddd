"""
Geometry operators for in-memory evaluation.

Uses `Shapely <https://shapely.readthedocs.io/>`_ for geometry
operations.  If Shapely is not installed, these operators will raise
``NotImplementedError`` with an installation hint.
"""

from __future__ import annotations

from typing import Any

from ..evaluator import MemoryOperator
from ..operators import SpecificationOperator


def _to_shapely_geom(value: Any) -> Any:
    """Convert a GeoJSON dict or Shapely geometry to a Shapely geometry."""
    try:
        from shapely.geometry import shape
    except ImportError as err:
        raise NotImplementedError(
            "Geometry operations require shapely. Install with: pip install shapely"
        ) from err

    if value is None:
        return None
    # Already a Shapely geometry
    if hasattr(value, "is_valid"):
        return value
    # geojson_pydantic (or any Pydantic model with GeoJSON shape)
    if hasattr(value, "model_dump"):
        return shape(value.model_dump())
    # GeoJSON dict
    if isinstance(value, dict):
        return shape(value)
    raise ValueError(f"Cannot convert {type(value)} to geometry")


class IntersectsOperator(MemoryOperator):
    """Check if geometries intersect."""

    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.INTERSECTS

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if field_value is None:
            return False
        return bool(
            _to_shapely_geom(field_value).intersects(_to_shapely_geom(condition_value))
        )


class WithinOperator(MemoryOperator):
    """Check if field geometry is within the query geometry."""

    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.WITHIN

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if field_value is None:
            return False
        return bool(
            _to_shapely_geom(field_value).within(_to_shapely_geom(condition_value))
        )


class ContainsGeomOperator(MemoryOperator):
    """Check if field geometry contains the query geometry."""

    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.CONTAINS_GEOM

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if field_value is None:
            return False
        return bool(
            _to_shapely_geom(field_value).contains(_to_shapely_geom(condition_value))
        )


class TouchesOperator(MemoryOperator):
    """Check if geometries touch."""

    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.TOUCHES

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if field_value is None:
            return False
        return bool(
            _to_shapely_geom(field_value).touches(_to_shapely_geom(condition_value))
        )


class CrossesOperator(MemoryOperator):
    """Check if geometries cross."""

    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.CROSSES

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if field_value is None:
            return False
        return bool(
            _to_shapely_geom(field_value).crosses(_to_shapely_geom(condition_value))
        )


class OverlapsOperator(MemoryOperator):
    """Check if geometries overlap."""

    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.OVERLAPS

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if field_value is None:
            return False
        return bool(
            _to_shapely_geom(field_value).overlaps(_to_shapely_geom(condition_value))
        )


class DisjointOperator(MemoryOperator):
    """Check if geometries are disjoint."""

    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.DISJOINT

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if field_value is None:
            return False
        return bool(
            _to_shapely_geom(field_value).disjoint(_to_shapely_geom(condition_value))
        )


class GeomEqualsOperator(MemoryOperator):
    """Check if geometries are equal."""

    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.GEOM_EQUALS

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if field_value is None:
            return False
        return bool(
            _to_shapely_geom(field_value).equals(_to_shapely_geom(condition_value))
        )


class DWithinOperator(MemoryOperator):
    """
    Check if geometries are within a given distance.

    Expects ``condition_value = (geojson_or_geom, distance)``.
    Distance is in the same units as the coordinate system.
    """

    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.DWITHIN

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if field_value is None:
            return False
        geom, distance = condition_value
        return bool(
            _to_shapely_geom(field_value).distance(_to_shapely_geom(geom)) <= distance
        )


class DistanceLtOperator(MemoryOperator):
    """
    Check if distance between geometries is less than a threshold.

    Expects ``condition_value = (geojson_or_geom, distance)``.
    """

    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.DISTANCE_LT

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if field_value is None:
            return False
        geom, distance = condition_value
        return bool(
            _to_shapely_geom(field_value).distance(_to_shapely_geom(geom)) < distance
        )


class BboxIntersectsOperator(MemoryOperator):
    """
    Check if bounding boxes intersect.

    Expects ``condition_value = (minx, miny, maxx, maxy)``.
    Uses Shapely ``bounds`` for fast spatial index approximation.
    """

    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.BBOX_INTERSECTS

    def evaluate(self, field_value: Any, condition_value: Any) -> bool:
        if field_value is None:
            return False
        field_geom = _to_shapely_geom(field_value)
        fminx, fminy, fmaxx, fmaxy = field_geom.bounds
        cminx, cminy, cmaxx, cmaxy = condition_value
        # AABB overlap test
        return not (fmaxx < cminx or fminx > cmaxx or fmaxy < cminy or fminy > cmaxy)
