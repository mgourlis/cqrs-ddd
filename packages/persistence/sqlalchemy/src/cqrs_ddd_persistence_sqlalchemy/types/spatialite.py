"""SpatiaLite / GeoPackage dialect utilities.

Provides SpatiaLite function name mappings, event listeners for async
engines, and GeoPackage initialization functions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from geoalchemy2 import functions  # noqa: E402
from geoalchemy2.admin.dialects.sqlite import (
    register_sqlite_mapping as _register_sqlite_mapping,  # noqa: E402
)
from geoalchemy2.elements import WKBElement
from geojson_pydantic.geometries import (
    Geometry,
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
    parse_geometry_obj,
)
from shapely import wkb
from shapely.geometry import mapping, shape
from sqlalchemy import event
from sqlalchemy.ext.compiler import compiles

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine
    from sqlalchemy.sql.compiler import SQLCompiler

# ----------------------------------------------------------------------
# Function Mappings
# ----------------------------------------------------------------------

# PostGIS functions that need different names in SpatiaLite
SPATIALITE_FUNCTION_MAPPINGS = {
    "ST_Buffer": "Buffer",
    "ST_Envelope": "Envelope",
    "ST_Centroid": "Centroid",
    "ST_Length": "GLength",
    "ST_MakePoint": "MakePoint",
    "ST_IsValid": "IsValid",
    "ST_AsText": "AsText",
    "ST_GeomFromText": "GeomFromText",
    "ST_Transform": "Transform",
    "ST_Simplify": "Simplify",
    # Used by geometry specification operators (PostGIS ST_* -> SpatiaLite names)
    "ST_GeomFromGeoJSON": "GeomFromGeoJSON",
    "ST_SetSRID": "SetSRID",
}


def register_spatialite_mappings() -> None:
    """Register SpatiaLite function name translations globally (call once).

    This registers the mappings so that when operators use
    func.ST_Buffer, GeoAlchemy2 translates it to "Buffer"
    for SpatiaLite/GeoPackage.
    """
    _register_sqlite_mapping(SPATIALITE_FUNCTION_MAPPINGS)


def setup_spatialite_engine(engine: Engine) -> None:
    """Register event listener to load SpatiaLite on every new connection.

    Uses engine.sync_engine (not the async engine) so this works
    with aiosqlite async engines.

    Args:
        engine: SQLAlchemy Engine (can be sync_engine of an async engine).
    """
    listen_engine = getattr(engine, "sync_engine", engine)

    @event.listens_for(listen_engine, "connect")
    def _load_spatialite(dbapi_conn: Any, _connection_record: Any) -> None:
        dbapi_conn.enable_load_extension(True)
        dbapi_conn.load_extension("mod_spatialite")
        dbapi_conn.execute("SELECT InitSpatialMetaData(1)")


def setup_geopackage_engine(engine: Engine) -> None:
    """Register event listener for GeoPackage init on every new connection."""
    listen_engine = getattr(engine, "sync_engine", engine)

    @event.listens_for(listen_engine, "connect")
    def _load_geopackage(dbapi_conn: Any, _connection_record: Any) -> None:
        dbapi_conn.enable_load_extension(True)
        dbapi_conn.load_extension("mod_spatialite")
        dbapi_conn.execute("SELECT AutoGpkgStart()")
        dbapi_conn.execute("SELECT EnableGpkgAmphibiousMode()")


def init_geopackage(engine: Engine, *, register_mappings: bool = True) -> None:
    """One-call setup: event listener + function mappings.

    This is the recommended entry point for GeoPackage support. It:
    - Sets up SpatiaLite/GeoPackage extension loading via event listener
    - Optionally registers SpatiaLite function name mappings globally

    Args:
        engine: SQLAlchemy Engine (can be sync_engine of an async engine).
        register_mappings: If True (default), calls register_spatialite_mappings().
                           Set to False if you want to call it separately.

    Usage::

        # At application startup
        from cqrs_ddd_persistence_sqlalchemy.types.spatialite import init_geopackage

        init_geopackage(engine)

        # Now all operators work with GeoPackage
    """
    setup_geopackage_engine(engine)
    if register_mappings:
        register_spatialite_mappings()


# ----------------------------------------------------------------------
# Custom @compiles for SpatiaLite Missing Functions
# ----------------------------------------------------------------------


@compiles(functions.ST_DWithin, "sqlite")
def _st_dwithin_sqlite(element: Any, compiler: SQLCompiler, **kw: Any) -> str:
    """ST_DWithin does not exist in SpatiaLite; rewrite to ST_Distance < threshold."""
    args = list(element.clauses)
    geom_a = compiler.process(args[0], **kw)
    geom_b = compiler.process(args[1], **kw)
    distance = compiler.process(args[2], **kw)
    return f"ST_Distance({geom_a}, {geom_b}) < {distance}"


@compiles(functions.ST_MakeEnvelope, "sqlite")
def _st_make_envelope_sqlite(element: Any, compiler: SQLCompiler, **kw: Any) -> str:
    """ST_MakeEnvelope does not exist in SpatiaLite; rewrite to BuildMbr."""
    args = list(element.clauses)
    minx = compiler.process(args[0], **kw)
    miny = compiler.process(args[1], **kw)
    maxx = compiler.process(args[2], **kw)
    maxy = compiler.process(args[3], **kw)
    srid = compiler.process(args[4], **kw)
    return f"BuildMbr({minx}, {miny}, {maxx}, {maxy}, {srid})"


# ----------------------------------------------------------------------
# Version Detection
# ----------------------------------------------------------------------


# ----------------------------------------------------------------------
# GeoJSON <-> Geometry coercers (for ModelMapper type_coercers)
# ----------------------------------------------------------------------

# All concrete geometry types for geometry_type_coercers()
_GEOMETRY_TYPES = (
    Point,
    MultiPoint,
    LineString,
    MultiLineString,
    Polygon,
    MultiPolygon,
    GeometryCollection,
)


def geojson_to_geometry(value: Geometry | dict[str, Any]) -> WKBElement:
    """
    Convert geojson_pydantic Geometry or GeoJSON dict -> WKBElement (for DB).

    Returns a WKBElement suitable for GeoAlchemy2 Geometry columns.
    Assumes WGS 84 (SRID 4326) for GeoJSON input.
    """
    if isinstance(value, dict):
        shapely_geom = shape(value)
    else:
        # geojson_pydantic Geometry (Pydantic model)
        shapely_geom = shape(value.model_dump())

    # Convert Shapely geometry to WKB bytes and wrap in WKBElement
    # Use SRID 4326 (WGS 84) for GeoJSON data
    wkb_bytes = wkb.dumps(shapely_geom)
    return WKBElement(wkb_bytes, srid=4326)


def geometry_to_geojson(value: Any) -> Geometry:
    """
    Convert Shapely or WKB geometry -> geojson_pydantic Geometry (for domain).

    Handles WKBElement, hex strings, Shapely geometries, and GeoJSON dicts.
    """
    # Check for WKBElement first (GeoAlchemy2 specific type)
    if isinstance(value, WKBElement):
        raw: bytes
        if hasattr(value, "data"):
            data = value.data
            raw = data if isinstance(data, bytes) else data.encode()
        else:
            raw = bytes(value)
        geom = wkb.loads(raw)
        return parse_geometry_obj(mapping(geom))

    # Shapely geometry (has __geo_interface__)
    if hasattr(value, "__geo_interface__"):
        return parse_geometry_obj(mapping(value))

    # Already a GeoJSON-like dict (e.g. from GeoAlchemy2 or model_dump)
    if isinstance(value, dict) and "type" in value:
        return parse_geometry_obj(value)

    # GeoAlchemy2: column can return hex string
    if isinstance(value, str):
        from shapely import from_hex

        geom = from_hex(value)
        return parse_geometry_obj(mapping(geom))

    # Fallback: try to treat as bytes-like (WKB)
    raw = bytes(value)
    geom = wkb.loads(raw)
    return parse_geometry_obj(mapping(geom))


def geometry_type_coercers() -> dict[type, Any]:
    """
    Return type_coercers dict for all geojson_pydantic geometry types (to_model).

    Also handles dict objects that are GeoJSON representations (result of model_dump()).
    """
    coercers: dict[type, Any] = dict.fromkeys(_GEOMETRY_TYPES, geojson_to_geometry)
    # Add dict coercer to handle model_dump() results
    coercers[dict] = geojson_to_geometry
    return coercers


def reverse_geometry_type_coercers() -> dict[type, Any]:
    """Return reverse_type_coercers for WKBElement -> Geometry (from_model)."""
    return {WKBElement: geometry_to_geojson}


# ----------------------------------------------------------------------
# Version Detection
# ----------------------------------------------------------------------


def get_spatialite_version(dbapi_conn: Any) -> str | None:
    """Detect SpatiaLite version from the database connection.

    Returns:
        Version string (e.g., "4.3.0", "5.0.0") or None if unavailable.

    Note: This requires SpatiaLite to already be loaded.
    """
    try:
        result = dbapi_conn.execute("SELECT spatialite_version();")
        row = result.fetchone() if result else None
        return row[0] if row else None
    except Exception:  # noqa: BLE001
        # SpatiaLite may not support this query
        return None
