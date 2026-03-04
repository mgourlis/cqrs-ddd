"""Unit tests for specification.py — MetadataTenantSpecification and helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from cqrs_ddd_multitenancy.context import reset_tenant, set_tenant
from cqrs_ddd_multitenancy.exceptions import TenantContextMissingError
from cqrs_ddd_multitenancy.specification import (
    MetadataTenantSpecification,
    TenantSpecification,
    build_tenant_filter_dict,
    create_tenant_specification,
    with_tenant_filter,
)

# ── Helpers ────────────────────────────────────────────────────────────


@dataclass
class EntityWithDirectAttr:
    tenant_id: str
    id: str = "e1"


@dataclass
class EntityWithMetadata:
    metadata: dict
    id: str = "e1"


class EntityWithPrivateMeta:
    def __init__(self, tenant_id: str) -> None:
        self._metadata = {"tenant_id": tenant_id}
        self.id = "e1"


class EntityWithNoTenant:
    id: str = "e1"


# ── Tests: MetadataTenantSpecification.is_satisfied_by ─────────────────


def test_is_satisfied_by_direct_attribute_match():
    spec = MetadataTenantSpecification("tenant-A")
    entity = EntityWithDirectAttr(tenant_id="tenant-A")
    assert spec.is_satisfied_by(entity)


def test_is_satisfied_by_direct_attribute_no_match():
    spec = MetadataTenantSpecification("tenant-A")
    entity = EntityWithDirectAttr(tenant_id="tenant-B")
    assert not spec.is_satisfied_by(entity)


def test_is_satisfied_by_metadata_dict_match():
    spec = MetadataTenantSpecification("tenant-A")
    entity = EntityWithMetadata(metadata={"tenant_id": "tenant-A"})
    assert spec.is_satisfied_by(entity)


def test_is_satisfied_by_metadata_dict_no_match():
    spec = MetadataTenantSpecification("tenant-A")
    entity = EntityWithMetadata(metadata={"tenant_id": "tenant-B"})
    assert not spec.is_satisfied_by(entity)


def test_is_satisfied_by_private_metadata():
    spec = MetadataTenantSpecification("tenant-A")
    entity = EntityWithPrivateMeta("tenant-A")
    assert spec.is_satisfied_by(entity)


def test_is_satisfied_by_private_metadata_no_match():
    spec = MetadataTenantSpecification("tenant-A")
    entity = EntityWithPrivateMeta("tenant-B")
    assert not spec.is_satisfied_by(entity)


def test_is_satisfied_by_no_tenant_returns_false():
    spec = MetadataTenantSpecification("tenant-A")
    entity = EntityWithNoTenant()
    assert not spec.is_satisfied_by(entity)


def test_is_satisfied_by_empty_metadata_returns_false():
    spec = MetadataTenantSpecification("tenant-A")
    entity = EntityWithMetadata(metadata={})
    assert not spec.is_satisfied_by(entity)


def test_custom_metadata_key():
    spec = MetadataTenantSpecification("tenant-A", metadata_key="org_id")
    entity = EntityWithMetadata(metadata={"org_id": "tenant-A"})
    assert spec.is_satisfied_by(entity)


def test_custom_tenant_column():
    spec = MetadataTenantSpecification("tenant-A", tenant_column="org_id")

    class E:
        org_id = "tenant-A"

    assert spec.is_satisfied_by(E())


# ── Tests: MetadataTenantSpecification.to_dict ─────────────────────────


def test_to_dict_returns_correct_structure():
    spec = MetadataTenantSpecification("tenant-X")
    d = spec.to_dict()
    assert d["attr"] == "tenant_id"
    assert d["op"] == "eq"
    assert d["val"] == "tenant-X"


def test_to_dict_custom_column():
    spec = MetadataTenantSpecification("tenant-X", tenant_column="org_id")
    d = spec.to_dict()
    assert d["attr"] == "org_id"


# ── Tests: MetadataTenantSpecification operators ───────────────────────


def test_and_operator_composes():
    spec_a = MetadataTenantSpecification("tenant-A")
    spec_b = MetadataTenantSpecification("tenant-A")
    combined = spec_a & spec_b
    assert combined is not None


def test_or_operator_composes():
    spec_a = MetadataTenantSpecification("tenant-A")
    spec_b = MetadataTenantSpecification("tenant-A")
    combined = spec_a | spec_b
    assert combined is not None


def test_invert_operator():
    spec = MetadataTenantSpecification("tenant-A")
    inverted = ~spec
    assert inverted is not None


def test_repr():
    spec = MetadataTenantSpecification("tenant-A")
    r = repr(spec)
    assert "tenant-A" in r


# ── Tests: create_tenant_specification ────────────────────────────────


def test_create_tenant_specification_returns_spec():
    from cqrs_ddd_specifications.operators_memory import build_default_registry

    registry = build_default_registry()
    spec = create_tenant_specification("tenant-X", registry=registry)
    assert spec is not None


def test_create_tenant_specification_is_satisfied_by():
    from cqrs_ddd_specifications.operators_memory import build_default_registry

    registry = build_default_registry()
    spec = create_tenant_specification("tenant-X", registry=registry)
    entity = EntityWithDirectAttr(tenant_id="tenant-X")
    assert spec.is_satisfied_by(entity)

    entity_other = EntityWithDirectAttr(tenant_id="tenant-Y")
    assert not spec.is_satisfied_by(entity_other)


def test_create_tenant_specification_custom_column():
    from cqrs_ddd_specifications.operators_memory import build_default_registry

    registry = build_default_registry()
    spec = create_tenant_specification("tenant-X", "org_id", registry)
    assert spec is not None


# ── Tests: TenantSpecification factory ────────────────────────────────


def test_for_current_tenant():
    token = set_tenant("tenant-A")
    try:
        from cqrs_ddd_specifications.operators_memory import build_default_registry

        registry = build_default_registry()
        spec = TenantSpecification.for_current_tenant(registry)
        assert spec is not None
        entity = EntityWithDirectAttr(tenant_id="tenant-A")
        assert spec.is_satisfied_by(entity)
    finally:
        reset_tenant(token)


def test_for_current_tenant_raises_when_no_tenant():
    from cqrs_ddd_specifications.operators_memory import build_default_registry

    registry = build_default_registry()
    with pytest.raises(TenantContextMissingError):
        TenantSpecification.for_current_tenant(registry)


def test_for_tenant():
    from cqrs_ddd_specifications.operators_memory import build_default_registry

    registry = build_default_registry()
    spec = TenantSpecification.for_tenant("tenant-X", registry)
    entity = EntityWithDirectAttr(tenant_id="tenant-X")
    assert spec.is_satisfied_by(entity)


def test_for_current_tenant_or_none_with_tenant():
    token = set_tenant("tenant-A")
    try:
        from cqrs_ddd_specifications.operators_memory import build_default_registry

        registry = build_default_registry()
        spec = TenantSpecification.for_current_tenant_or_none(registry)
        assert spec is not None
    finally:
        reset_tenant(token)


def test_for_current_tenant_or_none_without_tenant():
    from cqrs_ddd_specifications.operators_memory import build_default_registry

    registry = build_default_registry()
    spec = TenantSpecification.for_current_tenant_or_none(registry)
    assert spec is None


# ── Tests: with_tenant_filter ──────────────────────────────────────────


def test_with_tenant_filter_returns_composed_spec():
    token = set_tenant("tenant-A")
    try:
        from cqrs_ddd_specifications.operators_memory import build_default_registry

        registry = build_default_registry()
        tenant_spec = create_tenant_specification("tenant-A", registry=registry)
        combined = with_tenant_filter(tenant_spec, registry)
        assert combined is not None
    finally:
        reset_tenant(token)


def test_with_tenant_filter_none_spec():
    token = set_tenant("tenant-A")
    try:
        from cqrs_ddd_specifications.operators_memory import build_default_registry

        registry = build_default_registry()
        combined = with_tenant_filter(None, registry)
        assert combined is not None
    finally:
        reset_tenant(token)


def test_with_tenant_filter_system_tenant_returns_passthrough():
    from cqrs_ddd_multitenancy.context import clear_tenant, system_operation

    clear_tenant()
    from cqrs_ddd_multitenancy.context import set_tenant as _set

    tok = _set("__system__")
    try:
        from cqrs_ddd_specifications.operators_memory import build_default_registry

        registry = build_default_registry()
        result = with_tenant_filter(None, registry)
        assert result is not None
        # System tenant passthrough: every entity satisfies the spec
        entity = EntityWithDirectAttr(tenant_id="any-tenant")
        assert result.is_satisfied_by(entity)
    finally:
        reset_tenant(tok)


def test_with_tenant_filter_system_tenant_with_spec():
    from cqrs_ddd_multitenancy.context import set_tenant as _set

    tok = _set("__system__")
    try:
        from cqrs_ddd_specifications.operators_memory import build_default_registry

        registry = build_default_registry()
        original_spec = create_tenant_specification("tenant-A", registry=registry)
        result = with_tenant_filter(original_spec, registry)
        assert result is not None
    finally:
        reset_tenant(tok)


def test_with_tenant_filter_with_explicit_tenant_id():
    token = set_tenant("tenant-A")
    try:
        from cqrs_ddd_specifications.operators_memory import build_default_registry

        registry = build_default_registry()
        combined = with_tenant_filter(None, registry, tenant_id="tenant-X")
        entity_x = EntityWithDirectAttr(tenant_id="tenant-X")
        entity_a = EntityWithDirectAttr(tenant_id="tenant-A")
        assert combined.is_satisfied_by(entity_x)
        assert not combined.is_satisfied_by(entity_a)
    finally:
        reset_tenant(token)


# ── Tests: build_tenant_filter_dict ───────────────────────────────────


def test_build_tenant_filter_dict_with_current_tenant():
    token = set_tenant("tenant-A")
    try:
        result = build_tenant_filter_dict()
        assert result["attr"] == "tenant_id"
        assert result["op"] == "="
        assert result["val"] == "tenant-A"
    finally:
        reset_tenant(token)


def test_build_tenant_filter_dict_with_explicit_tenant():
    result = build_tenant_filter_dict(tenant_id="tenant-X")
    assert result["val"] == "tenant-X"


def test_build_tenant_filter_dict_no_tenant_returns_empty():
    result = build_tenant_filter_dict()
    assert result == {}


def test_build_tenant_filter_dict_custom_column():
    result = build_tenant_filter_dict(tenant_id="tenant-X", tenant_column="org_id")
    assert result["attr"] == "org_id"
    assert result["val"] == "tenant-X"
