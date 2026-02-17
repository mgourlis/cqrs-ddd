"""
ModelMapper — production-ready bidirectional mapper between Pydantic
``AggregateRoot`` entities and SQLAlchemy ``DeclarativeBase`` models.

Features
--------
- **Safe column extraction** — only reads columns defined in ``__table__``.
- **Private-attribute mapping** — extracts ``_version`` etc. that match DB columns.
- **Relationship handling** — traverses *only* already-loaded relationships
  (no lazy-load triggers → no N+1 queries).
- **Cycle detection** — tracks ``id(obj)`` to break bidirectional relationship
  loops.
- **Detached-model safety** — never accesses unloaded attributes on detached
  instances (avoids ``DetachedInstanceError``).
- **Nested Pydantic serialisation** — recursively calls ``model_dump`` for
  value-object / VO-list fields destined for JSON columns.
- **Configurable depth** — ``relationship_depth=0`` (default) ignores
  relationships entirely; increase to opt in.
- **Enum coercion** — converts Python ``Enum`` members to their ``.value``
  for DB storage.
- **Field mapping** — supports explicit field-to-column name mapping.
- **Field exclusion** — supports excluding specific fields from mapping.
- **Custom type coercers** — extensible type conversion system.
- **Batch operations** — bulk mapping methods for lists of entities/models.
"""

from __future__ import annotations

import contextlib
import enum
import logging
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from sqlalchemy import inspect as sa_inspect

from ..exceptions import MappingError

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

T_Entity = TypeVar("T_Entity")

# Sentinel used to detect unloaded attributes
_UNLOADED = object()


class ModelMapper(Generic[T_Entity]):
    """
    Bidirectional mapper between a Pydantic domain entity and a SQLAlchemy
    persistence model.

    Parameters
    ----------
    entity_cls:
        The Pydantic ``AggregateRoot`` (or any ``BaseModel``) subclass.
    db_model_cls:
        The SQLAlchemy ``DeclarativeBase`` subclass that represents the
        database table.
    relationship_depth:
        Maximum depth for traversing loaded relationships during
        ``from_model()``.  ``0`` (default) means relationships are
        ignored — the safest setting for avoiding accidental lazy loads.
    field_map:
        Dictionary mapping domain field names to DB column names.
        Example: ``{"metadata": "job_metadata"}``.
    exclude_fields:
        Set of field names to exclude from mapping in both directions.
    type_coercers:
        Dictionary mapping types to coercion functions for domain → DB conversion.
        Example: ``{UUID: str}`` or ``{UUID: lambda u: str(u)}``.
    """

    def _initialize_schema_info(
        self, db_model_cls: type[Any]
    ) -> tuple[bool, frozenset[str], frozenset[str]]:
        """Initialize schema information from DB model."""
        is_mapped = hasattr(db_model_cls, "__table__")
        columns: frozenset[str] = frozenset()
        relationships: frozenset[str] = frozenset()

        if is_mapped:
            columns = frozenset(db_model_cls.__table__.columns.keys())
            if hasattr(db_model_cls, "__mapper__"):
                relationships = frozenset(
                    rel.key for rel in db_model_cls.__mapper__.relationships
                )

        return is_mapped, columns, relationships

    def _initialize_private_attr_map(
        self, entity_cls: type[T_Entity], columns: frozenset[str]
    ) -> dict[str, str]:
        """Initialize private attribute mapping."""
        private_attr_map: dict[str, str] = {}

        if not hasattr(entity_cls, "__private_attributes__"):
            return private_attr_map

        for attr_name in entity_cls.__private_attributes__:  # type: ignore[attr-defined]
            if attr_name.startswith("_") and not attr_name.startswith("__"):
                public_name = attr_name.lstrip("_")
                # Only include if it maps to a DB column
                if public_name in columns:
                    private_attr_map[attr_name] = public_name

        return private_attr_map

    def _initialize_pydantic_fields(self, entity_cls: type[T_Entity]) -> frozenset[str]:
        """Initialize Pydantic fields."""
        if hasattr(entity_cls, "model_fields"):
            return frozenset(entity_cls.model_fields.keys())  # type: ignore[attr-defined]
        return frozenset()

    def __init__(
        self,
        entity_cls: type[T_Entity],
        db_model_cls: type[Any],
        *,
        relationship_depth: int = 0,
        field_map: dict[str, str] | None = None,
        exclude_fields: set[str] | None = None,
        type_coercers: dict[type, Callable[[Any], Any]] | None = None,
    ) -> None:
        self.entity_cls = entity_cls
        self.db_model_cls = db_model_cls
        self._relationship_depth = relationship_depth
        self._field_map: dict[str, str] = field_map or {}
        self._reverse_field_map: dict[str, str] = {
            v: k for k, v in self._field_map.items()
        }
        self._exclude_fields: frozenset[str] = frozenset(exclude_fields or ())
        self._type_coercers: dict[type, Callable[[Any], Any]] = type_coercers or {}

        # Pre-compute schema information once
        (
            self._is_mapped,
            self._columns,
            self._relationships,
        ) = self._initialize_schema_info(db_model_cls)

        # Cache Pydantic introspection
        self._private_attr_map = self._initialize_private_attr_map(
            entity_cls, self._columns
        )
        self._pydantic_fields = self._initialize_pydantic_fields(entity_cls)

    # ------------------------------------------------------------------
    # Domain → DB
    # ------------------------------------------------------------------

    def to_model(self, entity: T_Entity) -> Any:
        """
        Convert a *domain entity* (Pydantic model) to a *DB model*
        (SQLAlchemy instance) ready for ``session.add()`` / ``session.merge()``.

        Steps:
        1. Dump public fields via ``model_dump(mode="python")``.
        2. Extract private attributes (``_version``, ``_original_version``,
           etc.) that match DB column names.
        3. Apply field mapping (rename domain fields to DB columns).
        4. Filter to only columns present in the DB model (excludes
           relationships).
        5. Exclude specified fields.
        6. Coerce enums and custom types to their DB representation.
        7. Recursively serialise nested Pydantic objects to dicts for
           JSON/JSONB columns.
        """
        data = self._dump_entity(entity)
        data = self._extract_private_attrs(entity, data)
        data = self._apply_field_map(data, reverse=False)
        data = self._exclude_fields_from_data(data)
        data = self._filter_columns(data)
        data = self._coerce_values(data)
        return self.db_model_cls(**data)

    def to_models(self, entities: list[T_Entity]) -> list[Any]:
        """
        Batch convert domain entities to DB models.

        Parameters
        ----------
        entities:
            List of domain entities to convert.

        Returns
        -------
        List of DB model instances.
        """
        return [self.to_model(entity) for entity in entities]

    # ------------------------------------------------------------------
    # DB → Domain
    # ------------------------------------------------------------------

    def from_model(self, model: Any) -> T_Entity:
        """
        Convert a *DB model* (SQLAlchemy instance) to a *domain entity*.

        Steps:
        1. Extract column values, skipping any that are unloaded.
        2. Optionally traverse loaded relationships (respecting
           ``relationship_depth`` and cycle detection).
        3. Apply reverse field mapping (rename DB columns to domain fields).
        4. Exclude specified fields.
        5. Build the entity via ``model_validate()`` (dict mode — never
           ``from_attributes`` to avoid triggering lazy loads).
        6. Restore private attributes.
        """
        seen: set[int] = set()
        data = self._safe_extract(model, depth=self._relationship_depth, seen=seen)

        # Apply reverse field mapping (DB column -> domain field)
        data = self._apply_field_map(data, reverse=True)
        data = self._exclude_fields_from_data(data)

        # Build entity from safe dict (NOT from_attributes)
        entity = self._validate_entity(data, model)

        # Restore private attrs
        self._restore_private_attrs(entity, data)

        return entity

    def from_models(self, models: list[Any]) -> list[T_Entity]:
        """
        Batch convert DB models to domain entities.

        Parameters
        ----------
        models:
            List of DB model instances to convert.

        Returns
        -------
        List of domain entities.
        """
        return [self.from_model(model) for model in models]

    # ------------------------------------------------------------------
    # Internal helpers — to_model
    # ------------------------------------------------------------------

    @staticmethod
    def _dump_entity(entity: Any) -> dict[str, Any]:
        """Get a flat dict of public field values."""
        if hasattr(entity, "model_dump"):
            return dict(entity.model_dump(mode="python"))
        # Fallback for non-Pydantic objects
        return {k: v for k, v in entity.__dict__.items() if not k.startswith("_")}

    def _extract_private_attrs(
        self, entity: Any, data: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Pull private attributes that match column names into *data*.

        Uses cached ``__private_attributes__`` introspection for efficiency.
        """
        if not self._private_attr_map:
            return data

        for attr_name, public_name in self._private_attr_map.items():
            if public_name not in data:
                with contextlib.suppress(AttributeError):
                    data[public_name] = getattr(entity, attr_name)

        return data

    def _apply_field_map(
        self, data: dict[str, Any], *, reverse: bool = False
    ) -> dict[str, Any]:
        """
        Apply field mapping to rename keys.

        Parameters
        ----------
        data:
            Dictionary with keys to rename.
        reverse:
            If True, map DB column names → domain field names.
            If False, map domain field names → DB column names.

        Returns
        -------
        Dictionary with renamed keys.
        """
        if not self._field_map:
            return data

        mapping = self._reverse_field_map if reverse else self._field_map
        result: dict[str, Any] = {}

        for key, value in data.items():
            mapped_key = mapping.get(key, key)
            result[mapped_key] = value

        return result

    def _exclude_fields_from_data(self, data: dict[str, Any]) -> dict[str, Any]:
        """Remove excluded fields from the data dictionary."""
        if not self._exclude_fields:
            return data
        return {k: v for k, v in data.items() if k not in self._exclude_fields}

    def _filter_columns(self, data: dict[str, Any]) -> dict[str, Any]:
        """Keep only keys that correspond to DB columns (exclude relationships)."""
        if not self._columns:
            return data
        return {
            k: v
            for k, v in data.items()
            if k in self._columns and k not in self._relationships
        }

    def _coerce_values(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Coerce enums, custom types, and nested Pydantic models for DB storage.

        Handles Enum, Pydantic models, lists, dicts, sets, and custom coercers.
        """
        for key, value in list(data.items()):
            if value is None:
                continue

            # Check custom type coercers first
            value_type = type(value)
            if value_type in self._type_coercers:
                data[key] = self._type_coercers[value_type](value)
                continue

            # Built-in coercions
            if isinstance(value, enum.Enum):
                data[key] = value.value
            elif hasattr(value, "model_dump"):
                data[key] = value.model_dump(mode="python")
            elif isinstance(value, list):
                data[key] = [self._coerce_single(item) for item in value]
            elif isinstance(value, set | frozenset):
                # Convert sets to lists for JSON serialization
                data[key] = [self._coerce_single(item) for item in value]
            elif isinstance(value, dict):
                # Recursively coerce dict values
                data[key] = {k: self._coerce_single(v) for k, v in value.items()}

        return data

    def _coerce_single(self, value: Any) -> Any:
        """
        Coerce a single value (used inside lists, dicts, sets).

        Applies custom coercers, enum conversion, and Pydantic serialization.
        """
        if value is None:
            return value

        # Check custom type coercers
        value_type = type(value)
        if value_type in self._type_coercers:
            return self._type_coercers[value_type](value)

        # Built-in coercions
        if isinstance(value, enum.Enum):
            return value.value
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="python")
        if isinstance(value, dict):
            return {k: self._coerce_single(v) for k, v in value.items()}
        if isinstance(value, list | set | frozenset):
            return [self._coerce_single(item) for item in value]

        return value

    # ------------------------------------------------------------------
    # Internal helpers — from_model
    # ------------------------------------------------------------------

    def _safe_extract(
        self,
        model: Any,
        *,
        depth: int,
        seen: set[int],
    ) -> dict[str, Any]:
        """
        Build a dict from *model* without triggering lazy loads.

        Uses ``sqlalchemy.inspect()`` to detect unloaded attributes so
        that detached models and lazy relationships are handled safely.
        """
        if not self._is_mapped:
            # Non-SQLAlchemy model — just dump attributes
            return {k: v for k, v in model.__dict__.items() if not k.startswith("_")}

        model_identity = id(model)
        if model_identity in seen:
            return {}  # Cycle detected — return empty dict
        seen.add(model_identity)

        return self._extract_model_data(
            model=model,
            columns=self._columns,
            relationships=self._relationships,
            depth=depth,
            seen=seen,
        )

    def _extract_columns(
        self, model: Any, columns: frozenset[str], unloaded: frozenset[str]
    ) -> dict[str, Any]:
        """Extract column values from model."""
        data: dict[str, Any] = {}

        for col_name in columns:
            if col_name in unloaded:
                continue
            try:
                data[col_name] = getattr(model, col_name)
            except Exception:  # noqa: BLE001 — guard against any detached errors
                logger.debug(
                    "Skipping unloadable column %s on %s",
                    col_name,
                    type(model).__name__,
                )

        return data

    def _extract_relationships(
        self,
        model: Any,
        relationships: frozenset[str],
        unloaded: frozenset[str],
        depth: int,
        seen: set[int],
    ) -> dict[str, Any]:
        """Extract relationship values from model."""
        data: dict[str, Any] = {}

        if depth <= 0:
            return data

        for rel_key in relationships:
            if rel_key in unloaded:
                continue
            try:
                value = getattr(model, rel_key)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Failed to get relationship %s: %s", rel_key, exc)
                continue

            if value is None:
                data[rel_key] = None
            elif isinstance(value, list):
                data[rel_key] = [
                    self._extract_related(v, depth=depth - 1, seen=seen) for v in value
                ]
            else:
                data[rel_key] = self._extract_related(value, depth=depth - 1, seen=seen)

        return data

    def _extract_model_data(
        self,
        model: Any,
        *,
        columns: frozenset[str],
        relationships: frozenset[str],
        depth: int,
        seen: set[int],
    ) -> dict[str, Any]:
        """
        Extract data from a SQLAlchemy model instance.

        Shared implementation for both main model extraction and related
        model extraction.
        """
        unloaded = self._get_unloaded(model)
        data = self._extract_columns(model, columns, unloaded)
        data.update(
            self._extract_relationships(model, relationships, unloaded, depth, seen)
        )
        return data

    def _extract_related(
        self,
        model: Any,
        *,
        depth: int,
        seen: set[int],
    ) -> dict[str, Any] | None:
        """
        Extract a related model to a dict, with cycle + depth guards.

        Uses shared extraction logic via ``_extract_model_data``.
        """
        model_identity = id(model)
        if model_identity in seen:
            return None  # Cycle — break it

        seen.add(model_identity)

        if not hasattr(model, "__table__"):
            return {k: v for k, v in model.__dict__.items() if not k.startswith("_")}

        # Get columns and relationships for this related model
        related_columns = frozenset(model.__table__.columns.keys())
        related_relationships: frozenset[str] = frozenset()
        if hasattr(model, "__mapper__"):
            related_relationships = frozenset(
                rel.key for rel in model.__mapper__.relationships
            )

        return self._extract_model_data(
            model=model,
            columns=related_columns,
            relationships=related_relationships,
            depth=depth,
            seen=seen,
        )

    @staticmethod
    def _get_unloaded(model: Any) -> frozenset[str]:
        """Return the set of unloaded attribute names for a mapped instance."""
        try:
            insp = sa_inspect(model)
            return frozenset(insp.unloaded)
        except Exception:  # noqa: BLE001
            return frozenset()

    def _validate_entity(
        self, data: dict[str, Any], model: Any | None = None
    ) -> T_Entity:
        """
        Create the domain entity from a safe dict.

        Wraps Pydantic ValidationError in MappingError with context.
        """
        try:
            if hasattr(self.entity_cls, "model_validate"):
                return self.entity_cls.model_validate(data)  # type: ignore[no-any-return,attr-defined]
            # Fallback for non-Pydantic
            return self.entity_cls(**data)
        except Exception as e:  # noqa: BLE001
            # Catch all deserialization errors (validation, type errors, etc.)
            # Extract context for error message
            model_info = "unknown model"
            if model is not None:
                model_cls = type(model).__name__
                model_id = getattr(model, "id", None)
                model_info = f"{model_cls}(id={model_id})"

            raise MappingError(
                f"Failed to map DB model {model_info} to domain entity "
                f"{self.entity_cls.__name__}: {e}"
            ) from e

    def _restore_private_attrs(self, entity: Any, data: dict[str, Any]) -> None:
        """
        Restore all private attributes from the extracted data.

        Generalizes the previous version-only restoration to handle any
        private attributes that map to DB columns.
        """
        if not self._private_attr_map:
            return

        from contextlib import suppress

        for attr_name, public_name in self._private_attr_map.items():
            if public_name in data:
                with suppress(AttributeError, TypeError):
                    # Skip if attribute can't be set (e.g., frozen model)
                    object.__setattr__(entity, attr_name, data[public_name])
