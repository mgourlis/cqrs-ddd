"""Pydantic model <-> BSON document round-trip (datetime, UUID, Decimal).

.. deprecated::
    Prefer :class:`cqrs_ddd_persistence_mongo.core.model_mapper.MongoDBModelMapper`
    for BSON type preservation (mode='python', Decimal128). See docs/mongodb_model_mapper.md.
"""

from __future__ import annotations

import warnings
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

    .. deprecated::
        Use ``MongoDBModelMapper(entity_cls).to_doc(entity)`` for BSON preservation.
        See docs/mongodb_model_mapper.md.
    """
    warnings.warn(
        "model_to_doc is deprecated. Use MongoDBModelMapper(entity_cls).to_doc(entity) "
        "instead. See docs/mongodb_model_mapper.md.",
        DeprecationWarning,
        stacklevel=2,
    )
    try:
        data = model.model_dump()
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

    .. deprecated::
        Use ``MongoDBModelMapper(cls).from_doc(doc)`` instead.
        See docs/mongodb_model_mapper.md.
    """
    warnings.warn(
        "model_from_doc is deprecated. Use MongoDBModelMapper(cls).from_doc(doc) "
        "instead. See docs/mongodb_model_mapper.md.",
        DeprecationWarning,
        stacklevel=2,
    )
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
