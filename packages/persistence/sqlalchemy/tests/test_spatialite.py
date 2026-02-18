"""Tests for SpatiaLite / GeoPackage support.

All tests are skipped when the geometry extra is not installed.
"""

from __future__ import annotations

import pytest
from sqlalchemy import String
from sqlalchemy.orm import Mapped  # noqa: TC002

from cqrs_ddd_persistence_sqlalchemy.compat import HAS_GEOMETRY

if HAS_GEOMETRY:
    from geoalchemy2 import (
        Geometry,  # noqa: F401, TC002 — for ORM class annotations in tests
    )

pytestmark = pytest.mark.skipif(
    not HAS_GEOMETRY,
    reason="Geometry extra not installed (pip install cqrs-ddd-persistence-sqlalchemy[geometry])",
)

# Import so that @compiles(ST_DWithin, "sqlite") and @compiles(ST_MakeEnvelope, "sqlite") are registered
if HAS_GEOMETRY:
    import cqrs_ddd_persistence_sqlalchemy.types.spatialite  # noqa: F401


@pytest.mark.skipif(not HAS_GEOMETRY, reason="geometry extra required")
class TestRegisterSpatialiteMappings:
    """Test that SpatiaLite function mappings can be registered."""

    def test_register_spatialite_mappings_no_error(self) -> None:
        """register_spatialite_mappings() does not raise."""
        from cqrs_ddd_persistence_sqlalchemy.types.spatialite import (
            register_spatialite_mappings,
        )

        register_spatialite_mappings()

    def test_spatialite_mappings_constant(self) -> None:
        """SPATIALITE_FUNCTION_MAPPINGS contains expected entries."""
        from cqrs_ddd_persistence_sqlalchemy.types.spatialite import (
            SPATIALITE_FUNCTION_MAPPINGS,
        )

        assert "ST_Transform" in SPATIALITE_FUNCTION_MAPPINGS
        assert SPATIALITE_FUNCTION_MAPPINGS["ST_Transform"] == "Transform"
        assert "ST_Length" in SPATIALITE_FUNCTION_MAPPINGS
        assert SPATIALITE_FUNCTION_MAPPINGS["ST_Length"] == "GLength"


@pytest.mark.skipif(not HAS_GEOMETRY, reason="geometry extra required")
class TestGeoJSONCoercers:
    """Test GeoJSON <-> geometry conversion."""

    def test_geojson_to_geometry_point(self) -> None:
        """geojson_to_geometry converts a Point (geojson_pydantic or dict) to WKBElement."""
        from geoalchemy2.elements import WKBElement
        from geojson_pydantic import Point

        from cqrs_ddd_persistence_sqlalchemy.types.spatialite import (
            geojson_to_geometry,
            geometry_to_geojson,
        )

        point = Point(type="Point", coordinates=(1.0, 2.0))
        geom = geojson_to_geometry(point)
        # Now returns WKBElement with proper SRID
        assert isinstance(geom, WKBElement)
        assert geom.srid == 4326
        # Convert back to verify correctness
        back = geometry_to_geojson(geom)
        assert back.type == "Point"
        assert tuple(back.coordinates) == (1.0, 2.0)

    def test_geojson_to_geometry_dict(self) -> None:
        """geojson_to_geometry accepts a plain GeoJSON dict."""
        from geoalchemy2.elements import WKBElement

        from cqrs_ddd_persistence_sqlalchemy.types.spatialite import (
            geojson_to_geometry,
            geometry_to_geojson,
        )

        geom = geojson_to_geometry({"type": "Point", "coordinates": [1.0, 2.0]})
        assert isinstance(geom, WKBElement)
        assert geom.srid == 4326
        # Convert back to verify the type
        back = geometry_to_geojson(geom)
        assert back.type == "Point"

    def test_geometry_to_geojson_point(self) -> None:
        """geometry_to_geojson converts Shapely Point to geojson_pydantic Geometry."""
        from geojson_pydantic import Point
        from shapely.geometry import Point as ShapelyPoint

        from cqrs_ddd_persistence_sqlalchemy.types.spatialite import (
            geometry_to_geojson,
        )

        point = ShapelyPoint(1.0, 2.0)
        result = geometry_to_geojson(point)
        assert isinstance(result, Point)
        assert result.type == "Point"
        assert tuple(result.coordinates) == (1.0, 2.0)

    def test_geojson_round_trip(self) -> None:
        """geojson_to_geometry then geometry_to_geojson preserves data."""
        from geoalchemy2.elements import WKBElement
        from geojson_pydantic import Point

        from cqrs_ddd_persistence_sqlalchemy.types.spatialite import (
            geojson_to_geometry,
            geometry_to_geojson,
        )

        point = Point(type="Point", coordinates=(10.5, -20.3))
        geom = geojson_to_geometry(point)
        # Returns WKBElement with SRID 4326
        assert isinstance(geom, WKBElement)
        assert geom.srid == 4326
        back = geometry_to_geojson(geom)
        assert back.type == point.type
        assert tuple(back.coordinates) == tuple(point.coordinates)

    def test_geometry_type_coercers(self) -> None:
        """geometry_type_coercers() returns dict with all 7 geometry types + dict."""
        from geoalchemy2.elements import WKBElement
        from geojson_pydantic import Point

        from cqrs_ddd_persistence_sqlalchemy.types.spatialite import (
            geojson_to_geometry,
            geometry_type_coercers,
        )

        coercers = geometry_type_coercers()
        # 7 geometry types + dict for model_dump() results
        assert len(coercers) == 8
        point = Point(type="Point", coordinates=(0.0, 0.0))
        assert type(point) in coercers
        assert coercers[type(point)] is geojson_to_geometry
        # Dict also handled for model_dump() results
        assert dict in coercers
        assert coercers[dict] is geojson_to_geometry
        # Verify coercer returns WKBElement
        result = coercers[type(point)](point)
        assert isinstance(result, WKBElement)
        assert result.srid == 4326

    def test_reverse_geometry_type_coercers(self) -> None:
        """reverse_geometry_type_coercers() returns WKBElement -> geometry_to_geojson."""
        from geoalchemy2.elements import WKBElement
        from shapely import wkb
        from shapely.geometry import Point

        from cqrs_ddd_persistence_sqlalchemy.types.spatialite import (
            geometry_to_geojson,
            reverse_geometry_type_coercers,
        )

        reverse = reverse_geometry_type_coercers()
        assert WKBElement in reverse
        assert reverse[WKBElement] is geometry_to_geojson
        # Round-trip: Point -> WKB -> reverse coerce -> Geometry
        pt = Point(1.0, 2.0)
        wkb_bytes = wkb.dumps(pt)
        wkb_elem = WKBElement(wkb_bytes)
        result = reverse[WKBElement](wkb_elem)
        assert result.type == "Point"
        assert tuple(result.coordinates) == (1.0, 2.0)


@pytest.mark.skipif(not HAS_GEOMETRY, reason="geometry extra required")
class TestGeometryOperatorCompilation:
    """Test that geometry operators compile to SpatiaLite SQL when dialect is sqlite."""

    def test_dwithin_compiles_to_st_distance_on_sqlite(self) -> None:
        """DWithinOperator compiles to ST_Distance < threshold for sqlite."""
        from geoalchemy2 import Geometry
        from sqlalchemy import Integer, create_engine
        from sqlalchemy.orm import DeclarativeBase, mapped_column

        from cqrs_ddd_persistence_sqlalchemy.specifications.operators.geometry import (
            DWithinOperator,
        )

        class Base(DeclarativeBase):
            pass

        class Place(Base):
            __tablename__ = "places"
            id: Mapped[int] = mapped_column(Integer, primary_key=True)
            geom: Mapped[Geometry] = mapped_column(Geometry("POINT", srid=4326))

        op = DWithinOperator()
        point_geojson = {"type": "Point", "coordinates": [0.0, 0.0]}
        expr = op.apply(Place.geom, (point_geojson, 1000.0))
        compiled = expr.compile(
            compile_kwargs={"literal_binds": True},
            dialect=create_engine("sqlite://").dialect,
        )
        sql = str(compiled)
        # SpatiaLite fallback: ST_Distance(...) < ...
        assert "ST_Distance" in sql
        assert " < " in sql

    def test_bbox_intersects_compiles_to_buildmbr_on_sqlite(self) -> None:
        """BboxIntersectsOperator compiles to BuildMbr for sqlite."""
        from geoalchemy2 import Geometry
        from sqlalchemy import Integer, create_engine
        from sqlalchemy.orm import DeclarativeBase, mapped_column

        from cqrs_ddd_persistence_sqlalchemy.specifications.operators.geometry import (
            BboxIntersectsOperator,
        )

        class Base(DeclarativeBase):
            pass

        class Place(Base):
            __tablename__ = "places"
            id: Mapped[int] = mapped_column(Integer, primary_key=True)
            geom: Mapped[Geometry] = mapped_column(Geometry("POINT", srid=4326))

        op = BboxIntersectsOperator()
        expr = op.apply(Place.geom, (0.0, 0.0, 1.0, 1.0))
        compiled = expr.compile(
            compile_kwargs={"literal_binds": True},
            dialect=create_engine("sqlite://").dialect,
        )
        sql = str(compiled)
        # SpatiaLite fallback: BuildMbr(...)
        assert "BuildMbr" in sql
        assert "ST_Intersects" in sql


@pytest.mark.skipif(not HAS_GEOMETRY, reason="geometry extra required")
class TestModelMapperGeometryIntegration:
    """Test ModelMapper with geometry_type_coercers and reverse_geometry_type_coercers."""

    def test_to_model_coerces_geometry_to_wkb_element(self) -> None:
        """to_model converts geojson_pydantic Point to WKBElement via type_coercers."""
        from geoalchemy2.elements import WKBElement
        from geojson_pydantic import Point
        from pydantic import BaseModel
        from sqlalchemy import Integer
        from sqlalchemy.orm import DeclarativeBase, mapped_column

        from cqrs_ddd_persistence_sqlalchemy.core.model_mapper import ModelMapper
        from cqrs_ddd_persistence_sqlalchemy.mixins import SpatialModelMixin
        from cqrs_ddd_persistence_sqlalchemy.types.spatialite import (
            geometry_to_geojson,
            geometry_type_coercers,
            reverse_geometry_type_coercers,
        )

        class PlaceEntity(BaseModel):
            id: int
            geometry: Point | None = None

        class Base(DeclarativeBase):
            pass

        class PlaceModel(SpatialModelMixin, Base):
            __tablename__ = "place_model_test"
            id: Mapped[int] = mapped_column(Integer, primary_key=True)

        coercers = geometry_type_coercers()
        reverse_coercers = reverse_geometry_type_coercers()
        mapper = ModelMapper(
            PlaceEntity,
            PlaceModel,
            field_map={"geometry": "geom"},
            type_coercers=coercers,
            reverse_type_coercers=reverse_coercers,
        )
        point = Point(type="Point", coordinates=(1.0, 2.0))
        entity = PlaceEntity(id=1, geometry=point)
        model = mapper.to_model(entity)
        assert model.geom is not None
        # Coercer ran: geometry -> WKBElement
        assert isinstance(model.geom, WKBElement)
        assert model.geom.srid == 4326
        # Round-trip via geometry_to_geojson
        back = geometry_to_geojson(model.geom)
        assert back.type == "Point"
        assert tuple(back.coordinates) == (1.0, 2.0)

    def test_from_model_round_trip_geometry(self) -> None:
        """Full round-trip: entity -> model -> entity with geometry."""
        from geoalchemy2.elements import WKBElement
        from geojson_pydantic import Point
        from pydantic import BaseModel
        from sqlalchemy import Integer
        from sqlalchemy.orm import DeclarativeBase, mapped_column

        from cqrs_ddd_persistence_sqlalchemy.core.model_mapper import ModelMapper
        from cqrs_ddd_persistence_sqlalchemy.mixins import SpatialModelMixin
        from cqrs_ddd_persistence_sqlalchemy.types.spatialite import (
            geometry_type_coercers,
            reverse_geometry_type_coercers,
        )

        class PlaceEntity(BaseModel):
            id: int
            name: str
            geometry: Point | None = None

        class Base(DeclarativeBase):
            pass

        class PlaceModel(SpatialModelMixin, Base):
            __tablename__ = "place_model_test"
            id: Mapped[int] = mapped_column(Integer, primary_key=True)
            name: Mapped[str] = mapped_column(String)  # type: ignore[name-defined]

        coercers = geometry_type_coercers()
        reverse_coercers = reverse_geometry_type_coercers()
        mapper = ModelMapper(
            PlaceEntity,
            PlaceModel,
            field_map={"geometry": "geom"},
            type_coercers=coercers,
            reverse_type_coercers=reverse_coercers,
        )

        # Domain -> DB
        point = Point(type="Point", coordinates=(-73.9857, 40.7484))
        entity = PlaceEntity(id=1, name="NYC", geometry=point)
        model = mapper.to_model(entity)

        assert model.geom is not None
        assert isinstance(model.geom, WKBElement)
        assert model.name == "NYC"

        # Simulate DB read (model would have WKBElement from database)
        # The coercer will convert WKBElement back to geojson_pydantic Geometry
        restored = mapper.from_model(model)

        assert restored.id == 1
        assert restored.name == "NYC"
        assert restored.geometry is not None
        assert restored.geometry.type == "Point"
        # Coordinates may have minor floating point differences
        assert abs(restored.geometry.coordinates[0] - (-73.9857)) < 0.0001
        assert abs(restored.geometry.coordinates[1] - 40.7484) < 0.0001

    def test_persistence_with_spatialite_geometry_round_trip(self) -> None:
        """
        Test actual database persistence with geometry using SpatiaLite.

        This test verifies:
        1. Domain entity with geometry -> DB model (with type_coercers)
        2. Save to database with SpatiaLite Geometry column
        3. Retrieve from database (SpatiaLite returns WKBElement)
        4. Convert back to domain entity (with reverse_type_coercers)
        5. Geometry is preserved through full database round-trip

        Note: Uses sync SQLAlchemy and loads SpatiaLite extension for
        spatial queries. The geometry coercion logic is identical in sync/async.
        """
        from geojson_pydantic import Point
        from pydantic import BaseModel
        from sqlalchemy import Integer, String, create_engine, event
        from sqlalchemy.orm import DeclarativeBase, Session, mapped_column

        from cqrs_ddd_persistence_sqlalchemy.core.model_mapper import ModelMapper
        from cqrs_ddd_persistence_sqlalchemy.mixins import SpatialModelMixin
        from cqrs_ddd_persistence_sqlalchemy.types.spatialite import (
            geometry_type_coercers,
            reverse_geometry_type_coercers,
        )

        class PlaceEntity(BaseModel):
            id: int
            name: str
            geometry: Point | None = None

        class Base(DeclarativeBase):
            pass

        # Use SpatialModelMixin to get Geometry column
        class PlaceModel(SpatialModelMixin, Base):
            __tablename__ = "places_spatialite"
            id: Mapped[int] = mapped_column(Integer, primary_key=True)
            name: Mapped[str] = mapped_column(String)  # type: ignore[name-defined]

        coercers = geometry_type_coercers()
        reverse_coercers = reverse_geometry_type_coercers()
        mapper = ModelMapper(
            PlaceEntity,
            PlaceModel,
            field_map={"geometry": "geom"},
            type_coercers=coercers,
            reverse_type_coercers=reverse_coercers,
        )

        # Create in-memory SQLite database
        engine = create_engine("sqlite:///:memory:")

        # Register SpatiaLite function mappings for SQLite
        import cqrs_ddd_persistence_sqlalchemy.types.spatialite  # noqa: F401
        from cqrs_ddd_persistence_sqlalchemy.types.spatialite import (
            register_spatialite_mappings,
        )

        register_spatialite_mappings()

        # Load SpatiaLite on connect (for in-memory SQLite)
        @event.listens_for(engine, "connect")
        def load_spatialite(dbapi_conn, connection_record):
            dbapi_conn.enable_load_extension(True)
            dbapi_conn.load_extension("mod_spatialite")
            dbapi_conn.execute("SELECT InitSpatialMetaData(1)")

        # Create tables with SpatiaLite loaded
        Base.metadata.create_all(engine)

        with Session(engine) as session:
            # 1. Create domain entity with Point geometry
            point_geom = Point(type="Point", coordinates=(-122.4194, 37.7749))
            entity = PlaceEntity(
                id=1,
                name="San Francisco",
                geometry=point_geom,
            )

            # 2. Convert to DB model (applies type_coercers -> WKBElement)
            model = mapper.to_model(entity)

            # Verify coercer created WKBElement with SRID 4326
            from geoalchemy2.elements import WKBElement

            assert isinstance(model.geom, WKBElement)
            assert model.geom.srid == 4326
            assert model.name == "San Francisco"

            # 3. Save to database (SpatiaLite Geometry column stores WKB)
            session.add(model)
            session.commit()

            # 4. Clear session to force fresh load
            session.expunge_all()

            # 5. Query from database (SpatiaLite returns WKBElement)
            from sqlalchemy import select

            stmt = select(PlaceModel).where(PlaceModel.id == 1)
            loaded_model = session.execute(stmt).scalar_one()

            # Verify loaded model has WKBElement from SpatiaLite
            assert loaded_model is not None
            assert isinstance(loaded_model.geom, WKBElement)
            assert loaded_model.name == "San Francisco"

            # 6. Convert back to domain entity (applies reverse_type_coercers)
            restored = mapper.from_model(loaded_model)

            # 7. Verify geometry is preserved through SpatiaLite round-trip
            assert restored.id == 1
            assert restored.name == "San Francisco"
            assert restored.geometry is not None
            assert restored.geometry.type == "Point"
            # Allow small floating point tolerance
            assert abs(restored.geometry.coordinates[0] - (-122.4194)) < 0.0001
            assert abs(restored.geometry.coordinates[1] - 37.7749) < 0.0001
