"""Geometry operators -> $geoWithin, $geoIntersects, $near (2dsphere)."""

from __future__ import annotations

from typing import Any

from cqrs_ddd_specifications.operators import SpecificationOperator


def compile_geometry(field: str, op: str, val: Any) -> dict[str, Any] | None:
    """Compile geometry operators for 2dsphere index.

    Returns ``None`` when the operator is not geometry-related.
    """
    try:
        spec_op = SpecificationOperator(op)
    except ValueError:
        return None
    if spec_op == SpecificationOperator.WITHIN:
        return {field: {"$geoWithin": val}}
    if spec_op == SpecificationOperator.INTERSECTS:
        return {field: {"$geoIntersects": val}}
    if spec_op == SpecificationOperator.CONTAINS_GEOM:
        # MongoDB: $geoWithin with swapped geometry (containing shape)
        return (
            {"$expr": {"$geoWithin": [val, f"${field}"]}}
            if isinstance(val, dict)
            else None
        )
    if spec_op == SpecificationOperator.DISTANCE_LT:
        # val: { "type": "Point", "coordinates": [lng, lat] }, "maxDistance": metres
        if isinstance(val, dict) and "coordinates" in val and "maxDistance" in val:
            return {
                field: {
                    "$near": {
                        "$geometry": {
                            "type": val.get("type", "Point"),
                            "coordinates": val["coordinates"],
                        },
                        "$maxDistance": val["maxDistance"],
                    }
                }
            }
        return {field: {"$near": val}}
    if spec_op == SpecificationOperator.DWITHIN:
        return {field: {"$geoWithin": {"$centerSphere": val}}}
    if spec_op in (
        SpecificationOperator.TOUCHES,
        SpecificationOperator.CROSSES,
        SpecificationOperator.OVERLAPS,
        SpecificationOperator.DISJOINT,
        SpecificationOperator.GEOM_EQUALS,
        SpecificationOperator.BBOX_INTERSECTS,
    ):
        # Map to $geoIntersects or custom $expr where supported
        return {field: {"$geoIntersects": val}}
    return None
