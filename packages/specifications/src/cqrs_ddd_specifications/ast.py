from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast

from cqrs_ddd_core.domain.aggregate import AggregateRoot

from .base import (
    AndSpecification,
    BaseSpecification,
    NotSpecification,
    OrSpecification,
)
from .exceptions import OperatorNotFoundError, ValidationError
from .operators import SpecificationOperator
from .utils import cast_value

if TYPE_CHECKING:
    from collections.abc import Sequence

    from cqrs_ddd_core.domain.specification import ISpecification

    from .evaluator import MemoryOperatorRegistry

T = TypeVar("T", contravariant=True, bound=AggregateRoot[Any])

# Pre-compute valid operator values for validation
_VALID_OPERATORS: frozenset[str] = frozenset(m.value for m in SpecificationOperator)
_LOGICAL_OPERATORS: frozenset[str] = frozenset(
    {SpecificationOperator.AND, SpecificationOperator.OR, SpecificationOperator.NOT}
)


class AttributeSpecification(BaseSpecification[T]):
    """
    Specification that checks a single attribute value.

    Delegates in-memory evaluation to a :class:`MemoryOperatorRegistry`
    (strategy pattern). A registry MUST be explicitly provided via
    dependency injection for better testability and explicit dependencies.
    """

    def __init__(
        self,
        attr: str,
        op: SpecificationOperator | str,
        val: Any,
        *,
        registry: MemoryOperatorRegistry,
    ) -> None:
        self.attr = attr
        self.op = SpecificationOperator(op) if isinstance(op, str) else op
        self.val = val
        if registry is None:
            raise ValueError(
                "registry parameter is required. "
                "Use build_default_registry() from operators_memory to create one."
            )
        self._registry = registry

    def is_satisfied_by(self, candidate: T) -> bool:
        actual_val = self._resolve_field(candidate, self.attr)
        return self._registry.evaluate(self.op, actual_val, self.val)

    # -- field resolution ----------------------------------------------------

    @staticmethod
    def _resolve_field(obj: Any, attr_path: str) -> Any:
        """
        Resolve a dot-separated attribute path on *obj*.

        Supports nested attribute access (``address.city``) and
        implicit list traversal (``items.name`` where ``items`` is a
        list returns ``[item.name for item in items]``).
        """
        for part in attr_path.split("."):
            if obj is None:
                return None
            if isinstance(obj, list | tuple):
                # Implicit list traversal — map the remaining path
                return [
                    AttributeSpecification._resolve_field(item, part) for item in obj
                ]
            obj = obj.get(part) if isinstance(obj, dict) else getattr(obj, part, None)
        return obj

    # -- serialisation -------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "op": self.op.value,
            "attr": self.attr,
            "val": self.val,
        }


class SpecificationFactory(Generic[T]):
    """
    Factory for creating specifications from dictionary / JSON representations.

    Supports:
    - ``from_dict(data)`` — parse a nested dict tree
    - ``from_json(text)`` — parse a JSON string
    - ``validate(data)``  — validate without constructing
    - Automatic ``value_type`` casting via :func:`cast_value`
    """

    # ------------------------------------------------------------------ #
    # Public API                                                          #
    # ------------------------------------------------------------------ #

    @staticmethod
    def from_dict(
        data: dict[str, Any],
        *,
        allowed_fields: Sequence[str] | None = None,
        registry: MemoryOperatorRegistry,
    ) -> ISpecification[T]:
        """
        Create a specification tree from a dictionary.

        Parameters
        ----------
        data:
            The specification dictionary (potentially nested).
        allowed_fields:
            Optional whitelist of valid field/attribute names.  If
            provided, any ``attr`` not in this list raises
            :class:`ValidationError`.
        registry:
            Required :class:`MemoryOperatorRegistry` to be injected
            into every :class:`AttributeSpecification` leaf.
        """
        SpecificationFactory._validate_node(data, allowed_fields=allowed_fields)
        return SpecificationFactory._build(
            data,
            allowed_fields=allowed_fields,
            registry=registry,
        )

    @staticmethod
    def from_json(
        text: str,
        *,
        allowed_fields: Sequence[str] | None = None,
        registry: MemoryOperatorRegistry,
    ) -> ISpecification[T]:
        """Parse a JSON string and build a specification tree."""
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValidationError(
                f"Invalid JSON: {exc}",
                path="<root>",
            ) from exc

        if not isinstance(data, dict):
            raise ValidationError(
                "Top-level JSON value must be an object",
                path="<root>",
            )

        return SpecificationFactory.from_dict(
            data,
            allowed_fields=allowed_fields,
            registry=registry,
        )

    @staticmethod
    def validate(
        data: dict[str, Any],
        *,
        allowed_fields: Sequence[str] | None = None,
    ) -> list[str]:
        """
        Validate a specification dict and return a list of error messages.

        Returns an empty list when the structure is valid.
        """
        errors: list[str] = []
        SpecificationFactory._collect_errors(
            data, errors, path="<root>", allowed_fields=allowed_fields
        )
        return errors

    # ------------------------------------------------------------------ #
    # Internal — recursive build                                          #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _build(
        data: dict[str, Any],
        *,
        allowed_fields: Sequence[str] | None = None,
        registry: MemoryOperatorRegistry,
    ) -> ISpecification[T]:
        op_str = data.get("op", "").lower()

        if op_str == SpecificationOperator.AND:
            conditions = data.get("conditions", [])
            specs: list[ISpecification[T]] = [
                SpecificationFactory._build(
                    c, allowed_fields=allowed_fields, registry=registry
                )
                for c in conditions
            ]
            return AndSpecification(
                *cast("tuple[ISpecification[T], ...]", tuple(specs))
            )
        if op_str == SpecificationOperator.OR:
            conditions = data.get("conditions", [])
            or_specs: list[ISpecification[T]] = [
                SpecificationFactory._build(
                    c, allowed_fields=allowed_fields, registry=registry
                )
                for c in conditions
            ]
            return OrSpecification(
                *cast("tuple[ISpecification[T], ...]", tuple(or_specs))
            )
        if op_str == SpecificationOperator.NOT:
            conditions = data.get("conditions", [])
            if not conditions and "condition" in data:
                return NotSpecification(
                    SpecificationFactory._build(
                        data["condition"],
                        allowed_fields=allowed_fields,
                        registry=registry,
                    )
                )
            return NotSpecification(
                SpecificationFactory._build(
                    conditions[0], allowed_fields=allowed_fields, registry=registry
                )
            )

        # Leaf node
        attr = data["attr"]
        val = data.get("val")

        # Optional type casting
        value_type = data.get("value_type")
        if value_type is not None:
            val = cast_value(val, value_type)

        return AttributeSpecification(attr, op_str, val, registry=registry)

    # ------------------------------------------------------------------ #
    # Internal — validation                                               #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _validate_logical_node(
        data: dict[str, Any],
        op_str: str,
        path: str,
        allowed_fields: Sequence[str] | None,
    ) -> None:
        """Validate logical operator node."""
        conditions = data.get("conditions")
        if not conditions and "condition" not in data:
            raise ValidationError(
                f"Logical operator '{op_str}' requires 'conditions' list",
                path=path,
            )
        if conditions is not None:
            if not isinstance(conditions, list):
                raise ValidationError(
                    "'conditions' must be a list",
                    path=path,
                )
            for idx, child in enumerate(conditions):
                SpecificationFactory._validate_node(
                    child,
                    path=f"{path}.conditions[{idx}]",
                    allowed_fields=allowed_fields,
                )
        elif "condition" in data:
            SpecificationFactory._validate_node(
                data["condition"],
                path=f"{path}.condition",
                allowed_fields=allowed_fields,
            )

    @staticmethod
    def _validate_leaf_node(
        data: dict[str, Any],
        op_lower: str,
        path: str,
        allowed_fields: Sequence[str] | None,
    ) -> None:
        """Validate leaf node."""
        if op_lower not in _VALID_OPERATORS:
            raise OperatorNotFoundError(
                op_lower,
                [m.value for m in SpecificationOperator],
            )

        attr = data.get("attr")
        if not attr or not isinstance(attr, str):
            raise ValidationError(
                f"Leaf specification missing 'attr': {data}",
                path=path,
            )

        if allowed_fields is not None and attr not in allowed_fields:
            raise ValidationError(
                f"Field '{attr}' is not in the allowed fields list",
                path=path,
            )

    @staticmethod
    def _validate_node(
        data: dict[str, Any],
        *,
        path: str = "<root>",
        allowed_fields: Sequence[str] | None = None,
    ) -> None:
        """Raise on first validation error (fail-fast)."""
        if not isinstance(data, dict):
            raise ValidationError(
                f"Expected a dict, got {type(data).__name__}",
                path=path,
            )

        op_str = data.get("op")
        if not op_str or not isinstance(op_str, str):
            raise ValidationError("Missing or empty 'op' key", path=path)

        op_lower = op_str.lower()

        if op_lower in _LOGICAL_OPERATORS:
            SpecificationFactory._validate_logical_node(
                data, op_str, path, allowed_fields
            )
        else:
            SpecificationFactory._validate_leaf_node(
                data, op_lower, path, allowed_fields
            )

    @staticmethod
    def _collect_logical_errors(
        data: dict[str, Any],
        op_str: str,
        errors: list[str],
        path: str,
        allowed_fields: Sequence[str] | None,
    ) -> None:
        """Collect errors for logical operator node."""
        conditions = data.get("conditions")
        if not conditions and "condition" not in data:
            errors.append(f"{path}: logical '{op_str}' requires 'conditions'")
            return

        if conditions is not None:
            if not isinstance(conditions, list):
                errors.append(f"{path}: 'conditions' must be a list")
                return
            for idx, child in enumerate(conditions):
                SpecificationFactory._collect_errors(
                    child,
                    errors,
                    path=f"{path}.conditions[{idx}]",
                    allowed_fields=allowed_fields,
                )
        elif "condition" in data:
            SpecificationFactory._collect_errors(
                data["condition"],
                errors,
                path=f"{path}.condition",
                allowed_fields=allowed_fields,
            )

    @staticmethod
    def _collect_leaf_errors(
        data: dict[str, Any],
        op_lower: str,
        errors: list[str],
        path: str,
        allowed_fields: Sequence[str] | None,
    ) -> None:
        """Collect errors for leaf node."""
        if op_lower not in _VALID_OPERATORS:
            errors.append(f"{path}: unknown operator '{op_lower}'")

        attr = data.get("attr")
        if not attr or not isinstance(attr, str):
            errors.append(f"{path}: missing 'attr'")
            return

        if allowed_fields is not None and attr not in allowed_fields:
            errors.append(f"{path}: field '{attr}' not allowed")

    @staticmethod
    def _collect_errors(
        data: Any,
        errors: list[str],
        *,
        path: str,
        allowed_fields: Sequence[str] | None = None,
    ) -> None:
        """Recursive error collection (non-throwing)."""
        if not isinstance(data, dict):
            errors.append(f"{path}: expected dict, got {type(data).__name__}")
            return

        op_str = data.get("op")
        if not op_str or not isinstance(op_str, str):
            errors.append(f"{path}: missing or empty 'op' key")
            return

        op_lower = op_str.lower()

        if op_lower in _LOGICAL_OPERATORS:
            SpecificationFactory._collect_logical_errors(
                data, op_str, errors, path, allowed_fields
            )
        else:
            SpecificationFactory._collect_leaf_errors(
                data, op_lower, errors, path, allowed_fields
            )
