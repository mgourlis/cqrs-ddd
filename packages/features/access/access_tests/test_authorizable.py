"""Tests for AuthorizableEntity, ResourceTypeRegistry, and @register_access_entity."""

from __future__ import annotations

import pytest

from cqrs_ddd_access_control.authorizable import (
    ResourceTypeRegistry,
    get_access_config,
    register_access_entity,
)
from cqrs_ddd_access_control.events import ACLGrantRequested
from cqrs_ddd_access_control.models import AccessRule, FieldMapping, ResourceTypeConfig

# ---------------------------------------------------------------------------
# ResourceTypeRegistry
# ---------------------------------------------------------------------------


class TestResourceTypeRegistry:
    def test_register_and_get(self) -> None:
        registry = ResourceTypeRegistry()
        config = ResourceTypeConfig(
            name="order",
            field_mapping=FieldMapping(),
            actions=["read", "write"],
        )
        registry.register(config)
        assert registry.get_config("order") is config

    def test_get_missing_returns_none(self) -> None:
        registry = ResourceTypeRegistry()
        assert registry.get_config("unknown") is None

    def test_list_types(self) -> None:
        registry = ResourceTypeRegistry()
        registry.register(ResourceTypeConfig(name="a", field_mapping=FieldMapping()))
        registry.register(ResourceTypeConfig(name="b", field_mapping=FieldMapping()))
        assert sorted(registry.list_types()) == ["a", "b"]

    def test_get_config_for_entity(self) -> None:
        class Order:
            pass

        registry = ResourceTypeRegistry()
        config = ResourceTypeConfig(
            name="order",
            field_mapping=FieldMapping(),
            entity_class=Order,
        )
        registry.register(config)
        assert registry.get_config_for_entity(Order) is config

    def test_get_config_for_unregistered_entity(self) -> None:
        class Nope:
            pass

        registry = ResourceTypeRegistry()
        assert registry.get_config_for_entity(Nope) is None


# ---------------------------------------------------------------------------
# @register_access_entity decorator
# ---------------------------------------------------------------------------


class TestRegisterAccessEntity:
    def test_stores_config(self) -> None:
        @register_access_entity(
            resource_type="invoice",
            field_mapping=FieldMapping(
                mappings={"owner_id": "created_by"},
                external_id_field="id",
            ),
            actions=["read", "write", "delete"],
        )
        class Invoice:
            pass

        config = get_access_config(Invoice)
        assert config is not None
        assert config.name == "invoice"
        assert config.actions == ["read", "write", "delete"]
        assert config.entity_class is Invoice

    def test_adds_protocol_methods(self) -> None:
        @register_access_entity(
            resource_type="document",
            field_mapping=FieldMapping(mappings={"author": "author_id"}),
            actions=["read"],
        )
        class Document:
            pass

        assert Document.access_resource_type() == "document"  # type: ignore[attr-defined]
        assert Document.access_field_mapping().mappings == {"author": "author_id"}  # type: ignore[attr-defined]
        assert Document.access_syncable_fields() == ["author"]  # type: ignore[attr-defined]
        assert Document.access_valid_actions() == ["read"]  # type: ignore[attr-defined]

    def test_grant_access_emits_event(self) -> None:
        @register_access_entity(
            resource_type="project",
            field_mapping=FieldMapping(external_id_field="id"),
            actions=["read", "admin"],
        )
        class Project:
            def __init__(self, id: str) -> None:
                self.id = id

        proj = Project(id="p-123")
        rules = [AccessRule(principal_name="alice", action="read")]
        events = proj.grant_access(rules)  # type: ignore[attr-defined]
        assert len(events) == 1
        assert isinstance(events[0], ACLGrantRequested)
        assert events[0].resource_type == "project"
        assert events[0].resource_id == "p-123"
        assert events[0].access_rules == rules

    def test_undecorated_returns_none(self) -> None:
        class Plain:
            pass

        assert get_access_config(Plain) is None

    def test_default_actions_empty(self) -> None:
        @register_access_entity(
            resource_type="tag",
            field_mapping=FieldMapping(),
        )
        class Tag:
            pass

        config = get_access_config(Tag)
        assert config is not None
        assert config.actions == []
        assert Tag.access_valid_actions() == []  # type: ignore[attr-defined]

    def test_is_public_flag(self) -> None:
        @register_access_entity(
            resource_type="public_page",
            field_mapping=FieldMapping(),
            is_public=True,
        )
        class PublicPage:
            pass

        config = get_access_config(PublicPage)
        assert config is not None
        assert config.is_public is True

    def test_auto_register_false(self) -> None:
        @register_access_entity(
            resource_type="manual",
            field_mapping=FieldMapping(),
            auto_register_resources=False,
        )
        class ManualEntity:
            pass

        config = get_access_config(ManualEntity)
        assert config is not None
        assert config.auto_register_resources is False
