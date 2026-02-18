"""SQLAlchemy model mixin for geometry columns (GeoAlchemy2).

Follows the GeoPackage support plan: adds a single geometry column per model
using GeoAlchemy2's Geometry type directly. GeoPackage allows only one
geometry column per table.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from ..compat import require_geometry

require_geometry("SpatialModelMixin")
from geoalchemy2 import Geometry  # noqa: E402


class SpatialModelMixin:
    """Adds a geometry column using GeoAlchemy2 Geometry type directly.

    Override ``__geometry_type__`` and ``__geometry_srid__`` on your model
    to customize. GeoPackage supports only one geometry column per table.
    """

    __geometry_type__: str = "GEOMETRY"
    __geometry_srid__: int = 4326

    @declared_attr
    def geom(cls) -> Mapped[Any]:  # noqa: N805
        return mapped_column(
            Geometry(
                geometry_type=cls.__geometry_type__,
                srid=cls.__geometry_srid__,
                spatial_index=True,
            )
        )
