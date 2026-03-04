import pytest
from pydantic import BaseModel, ValidationError

from cqrs_ddd_multitenancy.domain.mixins import MultitenantMixin


class DummyEntity(MultitenantMixin, BaseModel):
    id: str
    name: str


def test_multitenant_mixin_valid():
    entity = DummyEntity(id="1", name="Test", tenant_id="tenant-1")
    assert entity.tenant_id == "tenant-1"

    # Should not raise
    entity.validate_tenant("tenant-1")


def test_multitenant_mixin_invalid_tenant():
    entity = DummyEntity(id="1", name="Test", tenant_id="tenant-1")
    with pytest.raises(ValueError, match="does not match expected tenant"):
        entity.validate_tenant("wrong-tenant")


def test_multitenant_mixin_missing_tenant_id():
    with pytest.raises(ValidationError):
        DummyEntity(id="1", name="Test")  # type: ignore


def test_multitenant_mixin_short_tenant_id():
    with pytest.raises(ValidationError):
        DummyEntity(id="1", name="Test", tenant_id="")
