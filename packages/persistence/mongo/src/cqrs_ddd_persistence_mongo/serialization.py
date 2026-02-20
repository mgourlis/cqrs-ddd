"""Pydantic model <-> BSON document round-trip (datetime, UUID, Decimal)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, TypeVar, cast
from uuid import UUID

from bson import Decimal128
from pydantic import BaseModel

from .exceptions import MongoPersistenceError

TModel = TypeVar("TModel", bound=BaseModel)


def _serialize_value(value: Any) -> Any:
    """Convert Python types to BSON-safe types."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return Decimal128(value)
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize_value(v) for v in value]
    return value


def _deserialize_value(value: Any) -> Any:
    """Convert BSON types back to Python types."""
    if isinstance(value, Decimal128):
        return value.to_decimal()
    if isinstance(value, datetime):
        return value
    if isinstance(value, dict):
        return {k: _deserialize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_deserialize_value(v) for v in value]
    return value


def model_to_doc(model: BaseModel, *, use_id_field: str = "id") -> dict[str, Any]:
    """Convert a Pydantic model to a BSON-ready document.

    Uses ``use_id_field`` as the document _id key if present (e.g. "id" -> "_id").
    """
    try:
        data = model.model_dump(mode="json")
    except Exception as e:
        raise MongoPersistenceError(str(e)) from e
    data = cast("dict[str, Any]", _serialize_value(data))
    if use_id_field in data:
        data["_id"] = data.pop(use_id_field)
    elif "_id" not in data:
        data["_id"] = None  # caller or repository may set
    return data


def model_from_doc(
    cls: type[TModel],
    doc: dict[str, Any],
    *,
    id_field: str = "id",
) -> TModel:
    """Convert a BSON document to a Pydantic model instance.

    Maps ``_id`` to ``id_field`` (e.g. "id") for the model.
    """
    if not isinstance(doc, dict):
        raise MongoPersistenceError("Document must be a dict")
    doc = dict(doc)
    if "_id" in doc:
        doc[id_field] = doc.pop("_id")
    doc = _deserialize_value(doc)
    try:
        return cls.model_validate(doc)
    except Exception as e:
        raise MongoPersistenceError(str(e)) from e
