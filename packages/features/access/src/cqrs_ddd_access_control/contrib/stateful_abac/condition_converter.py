"""ConditionConverter — bidirectional ABAC DSL ↔ Specification conversion.

The stateful-abac conditions DSL and ``cqrs-ddd-specifications`` share the
same ``{"op", "attr", "val"}`` / ``{"op", "conditions"}`` structure, so
conversion is primarily field-name mapping.
"""

from __future__ import annotations

import copy
from typing import Any

from ...models import AuthorizationConditionsResult, AuthorizationFilter, FieldMapping


class ConditionConverter:
    """Convert ABAC conditions DSL ↔ ``BaseSpecification``.

    Parameters
    ----------
    field_mapping:
        Maps between app entity field names and ABAC attribute names.
    """

    def __init__(self, field_mapping: FieldMapping) -> None:
        self._mapping = field_mapping

    # ------------------------------------------------------------------
    # DSL → Specification
    # ------------------------------------------------------------------

    def dsl_to_specification(
        self,
        conditions_result: AuthorizationConditionsResult,
    ) -> AuthorizationFilter:
        """Convert ``AuthorizationConditionsResult`` → ``AuthorizationFilter``.

        Handles ``granted_all`` / ``denied_all`` short-circuits.
        Strips ``source``, maps attribute names, builds via
        ``SpecificationFactory``.
        """
        if conditions_result.granted_all:
            return AuthorizationFilter.grant_all()

        if conditions_result.denied_all:
            return AuthorizationFilter.deny_all()

        if (
            not conditions_result.has_conditions
            or conditions_result.conditions_dsl is None
        ):
            return AuthorizationFilter.deny_all()

        # Import late — specifications is an optional dependency
        from cqrs_ddd_specifications import SpecificationFactory
        from cqrs_ddd_specifications.operators_memory import build_default_registry

        mapped = self._map_dsl_to_app(conditions_result.conditions_dsl)
        spec: Any = SpecificationFactory.from_dict(
            mapped, registry=build_default_registry()
        )
        return AuthorizationFilter.from_specification(spec)

    def _map_dsl_to_app(self, dsl: dict[str, Any]) -> dict[str, Any]:
        """Recursively map ABAC attribute names to app field names."""
        result = copy.deepcopy(dsl)
        return self._remap_dsl_node(result, reverse=True)

    # ------------------------------------------------------------------
    # Specification → DSL
    # ------------------------------------------------------------------

    def specification_to_dsl(self, spec: Any) -> dict[str, Any]:
        """Convert specification → ABAC conditions DSL.

        Maps attribute names via forward mapping, adds ``source: resource``.
        """
        spec_dict = spec.to_dict() if hasattr(spec, "to_dict") else dict(spec)
        return self._remap_dsl_node(spec_dict, reverse=False)

    # ------------------------------------------------------------------
    # Internal mapping
    # ------------------------------------------------------------------

    def _remap_logical_node(
        self, node: dict[str, Any], *, reverse: bool
    ) -> dict[str, Any]:
        """Recurse into children of logical (and/or/not) nodes."""
        node["conditions"] = [
            self._remap_dsl_node(c, reverse=reverse) for c in node.get("conditions", [])
        ]
        node.pop("source", None)
        return node

    def _remap_leaf_attr_reverse(self, node: dict[str, Any], attr: str) -> None:
        """Map ABAC attribute name → app field name (reverse direction)."""
        if attr == "external_id":
            node["attr"] = self._mapping.external_id_field
            if "val" in node:
                node["val"] = self._mapping.cast_external_id(node["val"])
        else:
            node["attr"] = self._mapping.get_field(attr)

    def _remap_leaf_attr_forward(self, node: dict[str, Any], attr: str) -> None:
        """Map app field name → ABAC attribute name (forward direction)."""
        if attr == self._mapping.external_id_field:
            node["attr"] = "external_id"
        else:
            node["attr"] = self._mapping.get_abac_attr(attr)
        node["source"] = "resource"

    def _remap_spatial_op(self, node: dict[str, Any], *, reverse: bool) -> None:
        """Normalise spatial operator names between ABAC and specification DSL."""
        op = node.get("op", "")
        if op in ("st_dwithin", "dwithin"):
            node["op"] = "dwithin" if reverse else "st_dwithin"

    def _remap_dsl_node(self, node: dict[str, Any], *, reverse: bool) -> dict[str, Any]:
        """Recursively remap attribute names in a DSL node.

        Parameters
        ----------
        reverse:
            ``True`` = ABAC→app (for ``dsl_to_specification``).
            ``False`` = app→ABAC (for ``specification_to_dsl``).
        """
        op = node.get("op", "")

        if op in ("and", "or", "not"):
            return self._remap_logical_node(node, reverse=reverse)

        attr = node.get("attr")
        if attr:
            if reverse:
                self._remap_leaf_attr_reverse(node, attr)
            else:
                self._remap_leaf_attr_forward(node, attr)

        if reverse:
            node.pop("source", None)

        self._remap_spatial_op(node, reverse=reverse)
        return node
