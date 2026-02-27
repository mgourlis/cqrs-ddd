"""MongoDB ModelMapper with BSON type preservation."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Generic, TypeVar

from bson.decimal128 import Decimal128
from pydantic import BaseModel

T_Entity = TypeVar("T_Entity", bound=BaseModel)


class MongoDBModelMapper(Generic[T_Entity]):
    """
    MongoDB-specific entity ↔ document mapper.

    Uses PyMongo's native type conversion (NOT JSON serialization).
    Uses model_dump(mode='python') to preserve native types; PyMongo converts
    datetime/UUID/bytes → BSON automatically; custom handlers for Decimal → Decimal128.
    """

    def __init__(
        self,
        entity_cls: type[T_Entity],
        *,
        id_field: str = "id",
        field_map: dict[str, str] | None = None,
        exclude_fields: set[str] | None = None,
    ) -> None:
        self.entity_cls = entity_cls
        self._id_field = id_field
        self._field_map = field_map or {}
        self._exclude_fields = exclude_fields or set()

    def to_doc(self, entity: T_Entity) -> dict[str, Any]:
        """
        Convert Pydantic entity → MongoDB document.
        Uses model_dump(mode='python'); custom Decimal → Decimal128; map id → _id.
        """
        data = entity.model_dump(mode="python")
        data = {k: v for k, v in data.items() if k not in self._exclude_fields}
        if self._field_map:
            data = self._apply_field_map(data, reverse=False)
        if self._id_field in data:
            data["_id"] = data.pop(self._id_field)
        return self._serialize_custom_types(data)

    def from_doc(self, doc: dict[str, Any]) -> T_Entity:
        """
        Convert MongoDB document → Pydantic entity.
        Map _id → id field; deserialize Decimal128 → Decimal; apply field map.
        """
        doc = dict(doc)
        if "_id" in doc:
            doc[self._id_field] = doc.pop("_id")
        doc = self._deserialize_custom_types(doc)
        if self._field_map:
            doc = self._apply_field_map(doc, reverse=True)
        return self.entity_cls.model_validate(doc)

    def _apply_field_map(
        self,
        data: dict[str, Any],
        *,
        reverse: bool = False,
    ) -> dict[str, Any]:
        if reverse:
            rev = {v: k for k, v in self._field_map.items()}
            return {rev.get(k, k): v for k, v in data.items()}
        return {self._field_map.get(k, k): v for k, v in data.items()}

    def _serialize_custom_types(self, data: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, Decimal):
                result[key] = Decimal128(str(value))
            elif isinstance(value, dict):
                result[key] = self._serialize_custom_types(value)
            elif isinstance(value, list):
                result[key] = [
                    self._serialize_custom_types({"_": v})["_"]
                    if isinstance(v, dict)
                    else Decimal128(str(v))
                    if isinstance(v, Decimal)
                    else v
                    for v in value
                ]
            else:
                result[key] = value
        return result

    def _deserialize_custom_types(self, data: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, Decimal128):
                result[key] = Decimal(str(value))
            elif isinstance(value, dict):
                result[key] = self._deserialize_custom_types(value)
            elif isinstance(value, list):
                result[key] = [
                    self._deserialize_custom_types({"_": v})["_"]
                    if isinstance(v, dict)
                    else Decimal(str(v))
                    if isinstance(v, Decimal128)
                    else v
                    for v in value
                ]
            else:
                result[key] = value
        return result

    def to_docs(self, entities: list[T_Entity]) -> list[dict[str, Any]]:
        """Convert multiple entities to documents."""
        return [self.to_doc(e) for e in entities]

    def from_docs(self, docs: list[dict[str, Any]]) -> list[T_Entity]:
        """Convert multiple documents to entities."""
        return [self.from_doc(d) for d in docs]
