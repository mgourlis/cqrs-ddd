"""Declarative projection schema system with version support."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, func
from sqlalchemy.schema import CreateTable

if TYPE_CHECKING:
    from cqrs_ddd_advanced_core.ports.projection import IProjectionWriter


class GeometryType(str, Enum):
    """Geometry column types for PostGIS/SpatiaLite."""

    POINT = "POINT"
    LINESTRING = "LINESTRING"
    POLYGON = "POLYGON"
    MULTIPOINT = "MULTIPOINT"
    MULTILINESTRING = "MULTILINESTRING"
    MULTIPOLYGON = "MULTIPOLYGON"
    GEOMETRYCOLLECTION = "GEOMETRYCOLLECTION"


class RelationshipType(str, Enum):
    """Relationship types between projections."""

    ONE_TO_MANY = "one_to_many"
    MANY_TO_ONE = "many_to_one"
    MANY_TO_MANY = "many_to_many"


class SpatialReferenceSystem:
    """Common spatial reference systems."""

    WGS84 = 4326  # GPS coordinates
    WEB_MERCATOR = 3857  # Google Maps / OpenStreetMap


@dataclass
class ProjectionRelationship:
    """Defines a relationship between two projection schemas."""

    name: str
    type: RelationshipType
    target_schema: str
    foreign_key: str | None = None
    back_populates: str | None = None
    cascade: bool = False


def _column_from_json(col_data: dict[str, Any]) -> Column[Any]:
    """Rebuild a SQLAlchemy Column from JSON-serialized column info."""
    name = col_data["name"]
    type_name = col_data.get("type", "String")
    primary_key = col_data.get("primary_key", False)
    nullable = col_data.get("nullable", True)
    if type_name == "String":
        return Column(name, String(255), primary_key=primary_key, nullable=nullable)
    if type_name == "Integer":
        return Column(name, Integer(), primary_key=primary_key, nullable=nullable)
    if type_name == "DateTime":
        return Column(
            name,
            DateTime(timezone=True),
            primary_key=primary_key,
            nullable=nullable,
            server_default=func.now(),
        )
    # Default to string for unknown types (e.g. Numeric, geometry)
    return Column(name, String(255), primary_key=primary_key, nullable=nullable)


@dataclass
class ProjectionSchema:
    """
    Declarative projection schema definition.

    Supports:
    - SQLAlchemy Column objects for type safety
    - Relationships (one-to-many, many-to-one, many-to-many)
    - Geometry columns (PostGIS, SpatiaLite)
    - Version tracking columns (REQUIRED for all projections)
    - JSON serialization (to_json, from_json)
    - File I/O (save_to_file, load_from_file)
    - DDL generation (create_ddl, drop_ddl)
    """

    name: str
    columns: list[Column[Any]]
    relationships: list[ProjectionRelationship] = field(default_factory=list)
    indexes: list[dict[str, Any]] = field(default_factory=list)
    srid: int = 4326  # Default spatial reference

    def to_json(self) -> dict[str, Any]:
        """Serialize schema to JSON."""
        return {
            "name": self.name,
            "columns": [
                {
                    "name": col.name,
                    "type": col.type.__class__.__name__,
                    "primary_key": col.primary_key,
                    "nullable": col.nullable,
                    "default": str(col.default) if col.default else None,
                }
                for col in self.columns
            ],
            "relationships": [
                {
                    "name": rel.name,
                    "type": rel.type.value,
                    "target_schema": rel.target_schema,
                    "foreign_key": rel.foreign_key,
                    "back_populates": rel.back_populates,
                    "cascade": rel.cascade,
                }
                for rel in self.relationships
            ],
            "indexes": self.indexes,
            "srid": self.srid,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ProjectionSchema:
        """Deserialize schema from JSON (rebuilds Column objects for common types)."""
        name = data["name"]
        columns = [_column_from_json(c) for c in data.get("columns", [])]
        relationships = [
            ProjectionRelationship(
                name=r["name"],
                type=RelationshipType(r["type"]),
                target_schema=r["target_schema"],
                foreign_key=r.get("foreign_key"),
                back_populates=r.get("back_populates"),
                cascade=r.get("cascade", False),
            )
            for r in data.get("relationships", [])
        ]
        indexes = data.get("indexes", [])
        srid = data.get("srid", 4326)
        return cls(
            name=name,
            columns=columns,
            relationships=relationships,
            indexes=indexes,
            srid=srid,
        )

    def save_to_file(self, path: str) -> None:
        """Save schema to JSON file."""
        with open(path, "w") as f:
            json.dump(self.to_json(), f, indent=2)

    @classmethod
    def load_from_file(cls, path: str) -> ProjectionSchema:
        """Load schema from JSON file."""
        with open(path) as f:
            data = json.load(f)
        return cls.from_json(data)

    def create_ddl(self) -> str:
        """Generate CREATE TABLE DDL."""
        metadata = MetaData()
        table = Table(self.name, metadata, *self.columns)
        return str(CreateTable(table))

    def drop_ddl(self) -> str:
        """Generate DROP TABLE DDL."""
        return f"DROP TABLE IF EXISTS {self.name} CASCADE;"


@dataclass
class ProjectionSchemaRegistry:
    """
    Registry for managing multiple projection schemas.

    Features:
    - Schema registration and lookup
    - Relationship resolution (auto-add FK columns)
    - Dependency ordering (topological sort)
    - JSON serialization for entire registry
    - Directory loading (load_from_directory)
    """

    _schemas: dict[str, ProjectionSchema] = field(default_factory=dict)

    def register(self, schema: ProjectionSchema) -> None:
        """Register a schema."""
        self._schemas[schema.name] = schema

    def get(self, name: str) -> ProjectionSchema | None:
        """Get a schema by name."""
        return self._schemas.get(name)

    def all(self) -> dict[str, ProjectionSchema]:
        """Get all schemas."""
        return self._schemas.copy()

    def resolve_relationships(self) -> None:
        """
        Resolve relationships and add foreign key columns.

        Example:
            order_summaries has many_to_one → customers
            Result: order_summaries.customer_id FK column added
        """
        for schema in self._schemas.values():
            for rel in schema.relationships:
                if rel.type == RelationshipType.MANY_TO_ONE and rel.foreign_key:
                    self._add_foreign_key(schema.name, rel.foreign_key)

    def _add_foreign_key(self, schema_name: str, fk_column: str) -> None:
        """Add foreign key column to schema."""
        schema = self._schemas.get(schema_name)
        if schema:
            if not any(col.name == fk_column for col in schema.columns):
                schema.columns.append(
                    Column(fk_column, String(255), nullable=False, index=True)
                )

    def get_initialization_order(self) -> list[str]:
        """
        Get dependency-ordered list of schema names.

        Uses topological sort to ensure dependent schemas
        are initialized first.
        """
        visited: set[str] = set()
        result: list[str] = []

        def visit(name: str) -> None:
            if name in visited:
                return
            visited.add(name)
            schema = self._schemas.get(name)
            if schema:
                for rel in schema.relationships:
                    if rel.type == RelationshipType.MANY_TO_ONE:
                        visit(rel.target_schema)
            result.append(name)

        for name in self._schemas:
            visit(name)
        return result

    def to_json(self) -> dict[str, Any]:
        """Serialize entire registry to JSON."""
        return {
            "schemas": [schema.to_json() for schema in self._schemas.values()],
            "initialization_order": self.get_initialization_order(),
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ProjectionSchemaRegistry:
        """Deserialize registry from JSON."""
        registry = cls()
        for schema_data in data.get("schemas", []):
            schema = ProjectionSchema.from_json(schema_data)
            registry.register(schema)
        return registry

    def save_to_file(self, path: str) -> None:
        """Save registry to JSON file."""
        with open(path, "w") as f:
            json.dump(self.to_json(), f, indent=2)

    @classmethod
    def load_from_file(cls, path: str) -> ProjectionSchemaRegistry:
        """Load registry from JSON file."""
        with open(path) as f:
            data = json.load(f)
        return cls.from_json(data)

    @classmethod
    def load_from_directory(cls, directory: str) -> ProjectionSchemaRegistry:
        """Load all JSON schema files from directory."""
        import glob

        registry = cls()
        for filepath in glob.glob(os.path.join(directory, "*.json")):
            with open(filepath) as f:
                data = json.load(f)
            schema = ProjectionSchema.from_json(data)
            registry.register(schema)
        registry.resolve_relationships()
        return registry

    async def initialize_all(self, writer: IProjectionWriter) -> None:
        """Initialize all schemas in dependency order."""
        for name in self.get_initialization_order():
            schema = self.get(name)
            if schema:
                await writer.ensure_collection(name, schema=schema)


# Required version columns for ALL projections
PROJECTION_VERSION_COLUMNS: list[Column[Any]] = [
    Column("_version", Integer, nullable=False, default=0, index=True),
    Column("_last_event_id", String(255), nullable=True, index=True),
    Column("_last_event_position", Integer, nullable=True),
    Column("_updated_at", DateTime, server_default=func.now(), onupdate=func.now()),
]


def create_schema(
    name: str,
    columns: list[Column[Any]],
    *,
    relationships: list[ProjectionRelationship] | None = None,
    indexes: list[dict[str, Any]] | None = None,
    srid: int = 4326,
) -> ProjectionSchema:
    """
    Factory function to create a ProjectionSchema with version columns.

    Automatically adds required version columns.

    Example:
        ```python
        order_schema = create_schema(
            "order_summaries",
            columns=[
                Column("id", String(255), primary_key=True),
                Column("total", Numeric(10, 2), nullable=False),
                Column("status", String(50), nullable=False),
            ],
            indexes=[
                {"name": "idx_status", "columns": ["status"], "unique": False},
            ],
        )
        ```
    """
    return ProjectionSchema(
        name=name,
        columns=columns + PROJECTION_VERSION_COLUMNS,
        relationships=relationships or [],
        indexes=indexes or [],
        srid=srid,
    )
