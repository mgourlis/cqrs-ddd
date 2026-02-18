"""Geometry / PostGIS operators for SQLAlchemy."""

from __future__ import annotations

import json
from typing import Any, cast

from sqlalchemy import ColumnElement, func

from cqrs_ddd_specifications.operators import SpecificationOperator

from ..strategy import SQLAlchemyOperator


def _geojson_to_str(value: Any) -> str:
    """Convert GeoJSON dict to string if needed."""
    if isinstance(value, str):
        return value
    return json.dumps(value)


class IntersectsOperator(SQLAlchemyOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.INTERSECTS

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        geom = func.ST_SetSRID(func.ST_GeomFromGeoJSON(_geojson_to_str(value)), 4326)
        return cast(
            "ColumnElement[bool]",
            func.ST_Intersects(func.ST_Transform(column, 4326), geom),
        )


class WithinOperator(SQLAlchemyOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.WITHIN

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        geom = func.ST_SetSRID(func.ST_GeomFromGeoJSON(_geojson_to_str(value)), 4326)
        return cast(
            "ColumnElement[bool]", func.ST_Within(func.ST_Transform(column, 4326), geom)
        )


class DWithinOperator(SQLAlchemyOperator):
    """
    Expects ``value = (geojson, distance_meters)``.

    **SRID Assumption:** This operator assumes both the database column and the
    input GeoJSON are in WGS 84 (EPSG:4326). Both geometries are transformed
    to Web Mercator (EPSG:3857) for distance calculation. If your database
    uses a different SRID, you will need to customize this operator.
    """

    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.DWITHIN

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        geom, distance = value
        query_geom = func.ST_Transform(
            func.ST_SetSRID(func.ST_GeomFromGeoJSON(_geojson_to_str(geom)), 4326),
            3857,
        )
        return cast(
            "ColumnElement[bool]",
            func.ST_DWithin(func.ST_Transform(column, 3857), query_geom, distance),
        )


class BboxIntersectsOperator(SQLAlchemyOperator):
    """Expects ``value = (minx, miny, maxx, maxy)``.

    Uses ST_Intersects(col, ST_MakeEnvelope(...)) for dialect compatibility.
    On SpatiaLite, ST_MakeEnvelope is rewritten to BuildMbr
    via @compiles in types/spatialite.py.
    """

    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.BBOX_INTERSECTS

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        minx, miny, maxx, maxy = value
        bbox_geom = func.ST_MakeEnvelope(minx, miny, maxx, maxy, 4326)
        return cast(
            "ColumnElement[bool]",
            func.ST_Intersects(column, bbox_geom),
        )


class ContainsGeomOperator(SQLAlchemyOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.CONTAINS_GEOM

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        geom = func.ST_SetSRID(func.ST_GeomFromGeoJSON(_geojson_to_str(value)), 4326)
        return cast(
            "ColumnElement[bool]",
            func.ST_Contains(func.ST_Transform(column, 4326), geom),
        )


class TouchesOperator(SQLAlchemyOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.TOUCHES

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        geom = func.ST_SetSRID(func.ST_GeomFromGeoJSON(_geojson_to_str(value)), 4326)
        return cast(
            "ColumnElement[bool]",
            func.ST_Touches(func.ST_Transform(column, 4326), geom),
        )


class CrossesOperator(SQLAlchemyOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.CROSSES

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        geom = func.ST_SetSRID(func.ST_GeomFromGeoJSON(_geojson_to_str(value)), 4326)
        return cast(
            "ColumnElement[bool]",
            func.ST_Crosses(func.ST_Transform(column, 4326), geom),
        )


class OverlapsOperator(SQLAlchemyOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.OVERLAPS

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        geom = func.ST_SetSRID(func.ST_GeomFromGeoJSON(_geojson_to_str(value)), 4326)
        return cast(
            "ColumnElement[bool]",
            func.ST_Overlaps(func.ST_Transform(column, 4326), geom),
        )


class DisjointOperator(SQLAlchemyOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.DISJOINT

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        geom = func.ST_SetSRID(func.ST_GeomFromGeoJSON(_geojson_to_str(value)), 4326)
        return cast(
            "ColumnElement[bool]",
            func.ST_Disjoint(func.ST_Transform(column, 4326), geom),
        )


class GeomEqualsOperator(SQLAlchemyOperator):
    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.GEOM_EQUALS

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        geom = func.ST_SetSRID(func.ST_GeomFromGeoJSON(_geojson_to_str(value)), 4326)
        return cast(
            "ColumnElement[bool]", func.ST_Equals(func.ST_Transform(column, 4326), geom)
        )


class DistanceLtOperator(SQLAlchemyOperator):
    """
    Expects ``value = (geojson, distance_meters)``.

    **SRID Assumption:** This operator assumes both the database column and
    input GeoJSON are in WGS 84 (EPSG:4326). Both geometries are
    transformed to Web Mercator (EPSG:3857) for distance calculation.
    If your database uses a different SRID, you will need to customize
    this operator.
    """

    @property
    def name(self) -> SpecificationOperator:
        return SpecificationOperator.DISTANCE_LT

    def apply(self, column: Any, value: Any) -> ColumnElement[bool]:
        geom, distance = value
        query_geom = func.ST_Transform(
            func.ST_SetSRID(func.ST_GeomFromGeoJSON(_geojson_to_str(geom)), 4326),
            3857,
        )
        return cast(
            "ColumnElement[bool]",
            func.ST_Distance(func.ST_Transform(column, 3857), query_geom) < distance,
        )
