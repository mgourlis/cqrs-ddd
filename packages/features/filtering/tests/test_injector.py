"""Tests for SecurityConstraintInjector."""

from __future__ import annotations

import pytest

from cqrs_ddd_filtering.exceptions import SecurityConstraintError
from cqrs_ddd_filtering.injector import SecurityConstraintInjector
from cqrs_ddd_specifications import build_default_registry
from cqrs_ddd_specifications.ast import AttributeSpecification
from cqrs_ddd_specifications.operators import SpecificationOperator


def test_inject_tenant() -> None:
    registry = build_default_registry()
    injector = SecurityConstraintInjector(registry, get_tenant_id=lambda: "t1")
    spec = AttributeSpecification(
        "status", SpecificationOperator.EQ, "active", registry=registry
    )
    out = injector.inject(spec)
    assert out is not None


def test_inject_requires_tenant_raises() -> None:
    registry = build_default_registry()
    injector = SecurityConstraintInjector(
        registry, get_tenant_id=lambda: None, require_tenant=True
    )
    with pytest.raises(SecurityConstraintError):
        injector.inject(None)
