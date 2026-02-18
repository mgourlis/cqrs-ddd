"""Integration tests: execute geospatial specification operators against a real SpatiaLite database.

All tests are skipped when the geometry extra is not installed or when mod_spatialite
cannot be loaded.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Integer, String, create_engine, event, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from cqrs_ddd_persistence_sqlalchemy.compat import HAS_GEOMETRY
from cqrs_ddd_persistence_sqlalchemy.mixins import SpatialModelMixin
from cqrs_ddd_persistence_sqlalchemy.specifications.compiler import build_sqla_filter
from cqrs_ddd_persistence_sqlalchemy.types.spatialite import (
    geojson_to_geometry,
    register_spatialite_mappings,
)

if not HAS_GEOMETRY:
    pytest.skip("Geometry extra not installed", allow_module_level=True)

# Import to register @compiles overrides for ST_DWithin, ST_MakeEnvelope
import cqrs_ddd_persistence_sqlalchemy.types.spatialite  # noqa: F401

# ---------------------------------------------------------------------------
# ORM model and seed data (used by fixtures)
# ---------------------------------------------------------------------------


class _Base(DeclarativeBase):
    pass


class PlaceModel(SpatialModelMixin, _Base):
    __tablename__ = "places_operators"
    __geometry_type__ = "GEOMETRY"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)


# Seed geometries (WGS84)
_SEED = [
    {
        "id": 1,
        "name": "NYC",
        "geom": {"type": "Point", "coordinates": [-73.9857, 40.7484]},
    },
    {
        "id": 2,
        "name": "London",
        "geom": {"type": "Point", "coordinates": [-0.1278, 51.5074]},
    },
    {
        "id": 3,
        "name": "Paris",
        "geom": {"type": "Point", "coordinates": [2.3522, 48.8566]},
    },
    {
        "id": 4,
        "name": "Manhattan Polygon",
        "geom": {
            "type": "Polygon",
            "coordinates": [
                [
                    [-74.01, 40.70],
                    [-73.96, 40.70],
                    [-73.96, 40.78],
                    [-74.01, 40.78],
                    [-74.01, 40.70],
                ]
            ],
        },
    },
    {
        "id": 5,
        "name": "East-West Line",
        "geom": {
            "type": "LineString",
            "coordinates": [[-74.05, 40.74], [-73.95, 40.74]],
        },
    },
    {
        "id": 6,
        "name": "Disjoint Island",
        "geom": {"type": "Point", "coordinates": [-160.0, 20.0]},
    },
    {
        "id": 7,
        "name": "Overlap Polygon",
        "geom": {
            "type": "Polygon",
            "coordinates": [
                [
                    [-73.98, 40.72],
                    [-73.94, 40.72],
                    [-73.94, 40.76],
                    [-73.98, 40.76],
                    [-73.98, 40.72],
                ]
            ],
        },
    },
]


def _load_spatialite_and_create_tables(engine: object) -> None:
    """Load SpatiaLite on connection and create tables. Raises if mod_spatialite unavailable."""
    with engine.connect() as _:
        pass  # connect event fires here; if mod_spatialite fails, connection raises
    _Base.metadata.create_all(engine)


def _seed_places(engine: object) -> None:
    with Session(engine) as session:
        for row in _SEED:
            geom = geojson_to_geometry(row["geom"])
            session.add(PlaceModel(id=row["id"], name=row["name"], geom=geom))
        session.commit()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def spatialite_engine():
    """Create SpatiaLite-backed in-memory engine with mappings and tables. Skip if mod_spatialite unavailable."""
    register_spatialite_mappings()
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def load_spatialite(dbapi_conn, connection_record):
        dbapi_conn.enable_load_extension(True)
        dbapi_conn.load_extension("mod_spatialite")
        dbapi_conn.execute("SELECT InitSpatialMetaData(1)")

    try:
        _load_spatialite_and_create_tables(engine)
        _seed_places(engine)
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"SpatiaLite not available: {e}")
    yield engine
    engine.dispose()


@pytest.fixture
def spatialite_session(spatialite_engine):
    """Per-test session against the seeded SpatiaLite database."""
    with Session(spatialite_engine) as session:
        yield session


def _proj_available(session: Session) -> bool:
    """Return True if ST_Transform (PROJ) works for distance tests."""
    try:
        from sqlalchemy import text

        session.execute(
            text(
                "SELECT ST_AsText(ST_Transform(ST_GeomFromText('Point(0 0)', 4326), 3857))"
            )
        )
        return True
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# Tests: topological operators
# ---------------------------------------------------------------------------


class TestSpatialOperatorsAgainstDB:
    """Execute every geometry operator against a real SpatiaLite database."""

    def test_intersects_returns_matching_geometries(
        self, spatialite_session: Session
    ) -> None:
        # Polygon overlapping Manhattan and containing NYC point
        spec = {
            "op": "intersects",
            "attr": "geom",
            "val": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-74.02, 40.69],
                        [-73.95, 40.69],
                        [-73.95, 40.79],
                        [-74.02, 40.79],
                        [-74.02, 40.69],
                    ]
                ],
            },
        }
        clause = build_sqla_filter(PlaceModel, spec)
        rows = (
            spatialite_session.execute(select(PlaceModel).where(clause)).scalars().all()
        )
        names = {r.name for r in rows}
        assert "NYC" in names
        assert "Manhattan Polygon" in names
        assert "East-West Line" in names
        assert "London" not in names
        assert "Disjoint Island" not in names

    def test_within_returns_geometries_inside_polygon(
        self, spatialite_session: Session
    ) -> None:
        # Large polygon containing NYC and Manhattan, not London/Paris
        spec = {
            "op": "within",
            "attr": "geom",
            "val": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-75.0, 40.0],
                        [-72.0, 40.0],
                        [-72.0, 41.5],
                        [-75.0, 41.5],
                        [-75.0, 40.0],
                    ]
                ],
            },
        }
        clause = build_sqla_filter(PlaceModel, spec)
        rows = (
            spatialite_session.execute(select(PlaceModel).where(clause)).scalars().all()
        )
        names = {r.name for r in rows}
        assert "NYC" in names
        assert "Manhattan Polygon" in names
        assert "East-West Line" in names
        assert "London" not in names
        assert "Paris" not in names

    def test_contains_geom_returns_containers(
        self, spatialite_session: Session
    ) -> None:
        # Manhattan polygon contains NYC point; query: rows whose geom contains the given point
        spec = {
            "op": "contains_geom",
            "attr": "geom",
            "val": {"type": "Point", "coordinates": [-73.9857, 40.7484]},
        }
        clause = build_sqla_filter(PlaceModel, spec)
        rows = (
            spatialite_session.execute(select(PlaceModel).where(clause)).scalars().all()
        )
        names = {r.name for r in rows}
        assert "Manhattan Polygon" in names
        # NYC is a point at the same location; ST_Contains(point, point) is implementation-defined

    def test_touches_returns_boundary_shared(self, spatialite_session: Session) -> None:
        # Point on the boundary of a polygon: point at (-74.01, 40.74) touches Manhattan's west edge
        spec = {
            "op": "touches",
            "attr": "geom",
            "val": {"type": "Point", "coordinates": [-74.01, 40.74]},
        }
        clause = build_sqla_filter(PlaceModel, spec)
        rows = (
            spatialite_session.execute(select(PlaceModel).where(clause)).scalars().all()
        )
        names = {r.name for r in rows}
        assert "Manhattan Polygon" in names

    def test_crosses_detects_line_crossing_polygon(
        self, spatialite_session: Session
    ) -> None:
        # Line that crosses Manhattan; query: rows whose geom crosses the given line
        spec = {
            "op": "crosses",
            "attr": "geom",
            "val": {
                "type": "LineString",
                "coordinates": [[-74.02, 40.74], [-73.94, 40.74]],
            },
        }
        clause = build_sqla_filter(PlaceModel, spec)
        rows = (
            spatialite_session.execute(select(PlaceModel).where(clause)).scalars().all()
        )
        names = {r.name for r in rows}
        assert "Manhattan Polygon" in names
        # East-West Line may or may not be "crosses" per DE-9IM (line-line)

    def test_overlaps_detects_partial_overlap(
        self, spatialite_session: Session
    ) -> None:
        # Query polygon partially overlaps Manhattan; ST_Overlaps = shared area, neither contains
        spec = {
            "op": "overlaps",
            "attr": "geom",
            "val": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-73.99, 40.71],
                        [-73.93, 40.71],
                        [-73.93, 40.77],
                        [-73.99, 40.77],
                        [-73.99, 40.71],
                    ]
                ],
            },
        }
        clause = build_sqla_filter(PlaceModel, spec)
        rows = (
            spatialite_session.execute(select(PlaceModel).where(clause)).scalars().all()
        )
        names = {r.name for r in rows}
        assert "Manhattan Polygon" in names
        # Overlap Polygon may be considered within/equal to query polygon by implementation

    def test_disjoint_returns_non_overlapping(
        self, spatialite_session: Session
    ) -> None:
        # Query: geometries disjoint from a small NYC-area polygon
        spec = {
            "op": "disjoint",
            "attr": "geom",
            "val": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-73.99, 40.74],
                        [-73.98, 40.74],
                        [-73.98, 40.75],
                        [-73.99, 40.75],
                        [-73.99, 40.74],
                    ]
                ],
            },
        }
        clause = build_sqla_filter(PlaceModel, spec)
        rows = (
            spatialite_session.execute(select(PlaceModel).where(clause)).scalars().all()
        )
        names = {r.name for r in rows}
        assert "Disjoint Island" in names
        assert "London" in names
        assert "Paris" in names
        assert "NYC" not in names

    def test_geom_equals_exact_match(self, spatialite_session: Session) -> None:
        spec = {
            "op": "geom_equals",
            "attr": "geom",
            "val": {"type": "Point", "coordinates": [-73.9857, 40.7484]},
        }
        clause = build_sqla_filter(PlaceModel, spec)
        rows = (
            spatialite_session.execute(select(PlaceModel).where(clause)).scalars().all()
        )
        names = {r.name for r in rows}
        assert names == {"NYC"}

    def test_dwithin_distance_threshold(self, spatialite_session: Session) -> None:
        if not _proj_available(spatialite_session):
            pytest.skip("ST_Transform/PROJ not available for metric distance")
        # Points within ~50km of NYC (NYC itself and Manhattan area; not London)
        spec = {
            "op": "dwithin",
            "attr": "geom",
            "val": ({"type": "Point", "coordinates": [-73.9857, 40.7484]}, 50_000.0),
        }
        clause = build_sqla_filter(PlaceModel, spec)
        rows = (
            spatialite_session.execute(select(PlaceModel).where(clause)).scalars().all()
        )
        names = {r.name for r in rows}
        assert "NYC" in names
        assert "Manhattan Polygon" in names or "East-West Line" in names
        assert "London" not in names
        assert "Disjoint Island" not in names

    def test_distance_lt_threshold(self, spatialite_session: Session) -> None:
        if not _proj_available(spatialite_session):
            pytest.skip("ST_Transform/PROJ not available for metric distance")
        spec = {
            "op": "distance_lt",
            "attr": "geom",
            "val": ({"type": "Point", "coordinates": [-73.9857, 40.7484]}, 100.0),
        }
        clause = build_sqla_filter(PlaceModel, spec)
        rows = (
            spatialite_session.execute(select(PlaceModel).where(clause)).scalars().all()
        )
        names = {r.name for r in rows}
        assert "NYC" in names
        assert "London" not in names

    def test_bbox_intersects_bounding_box(self, spatialite_session: Session) -> None:
        # Bbox around NYC area: minx, miny, maxx, maxy
        spec = {
            "op": "bbox_intersects",
            "attr": "geom",
            "val": (-74.0, 40.7, -73.97, 40.76),
        }
        clause = build_sqla_filter(PlaceModel, spec)
        rows = (
            spatialite_session.execute(select(PlaceModel).where(clause)).scalars().all()
        )
        names = {r.name for r in rows}
        assert "NYC" in names
        assert "Manhattan Polygon" in names
        assert "London" not in names
        assert "Disjoint Island" not in names
