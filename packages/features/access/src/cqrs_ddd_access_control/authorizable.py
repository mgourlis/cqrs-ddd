"""AuthorizableEntity protocol, decorator, and ResourceTypeRegistry.

No global state — the application owns the ``ResourceTypeRegistry`` instance
and decides how to manage its lifecycle (DI container, singleton, etc.).

The ``@register_access_entity`` decorator stores a ``ResourceTypeConfig``
on the **class** (``__access_config__``) so the application can discover
decorated entities and register them into its own registry at startup.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from .models import AccessRule, FieldMapping, ResourceTypeConfig

if TYPE_CHECKING:
    from cqrs_ddd_core import DomainEvent

# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class AuthorizableEntity(Protocol):
    """Entities implement this to declare their ABAC configuration."""

    @classmethod
    def access_resource_type(cls) -> str: ...

    @classmethod
    def access_field_mapping(cls) -> FieldMapping: ...

    @classmethod
    def access_syncable_fields(cls) -> list[str]: ...

    @classmethod
    def access_valid_actions(cls) -> list[str]: ...

    def grant_access(self, rules: list[AccessRule]) -> list[DomainEvent]: ...


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class ResourceTypeRegistry:
    """Application-owned registry of access-controlled resource types.

    Populated by the application at startup — either by scanning for
    decorated classes (``get_access_config``) or by manual registration.

    Example::

        registry = ResourceTypeRegistry()

        # Option A: auto-discover decorated entities
        for entity_cls in [Order, Document, Project]:
            config = get_access_config(entity_cls)
            if config is not None:
                registry.register(config)

        # Option B: manual
        registry.register(ResourceTypeConfig(name="order", ...))
    """

    def __init__(self) -> None:
        self._configs: dict[str, ResourceTypeConfig] = {}
        self._entity_map: dict[type, str] = {}

    def register(self, config: ResourceTypeConfig) -> None:
        self._configs[config.name] = config
        if config.entity_class is not None:
            self._entity_map[config.entity_class] = config.name

    def get_config(self, resource_type: str) -> ResourceTypeConfig | None:
        return self._configs.get(resource_type)

    def get_config_for_entity(self, entity_cls: type) -> ResourceTypeConfig | None:
        name = self._entity_map.get(entity_cls)
        return self._configs.get(name) if name else None

    def list_types(self) -> list[str]:
        return list(self._configs.keys())


# ---------------------------------------------------------------------------
# Helper — read config from a decorated class
# ---------------------------------------------------------------------------

_ACCESS_CONFIG_ATTR = "__access_config__"


def get_access_config(cls: type) -> ResourceTypeConfig | None:
    """Return the ``ResourceTypeConfig`` stored by ``@register_access_entity``,
    or ``None`` if the class was not decorated."""
    return getattr(cls, _ACCESS_CONFIG_ATTR, None)


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------


def register_access_entity(
    resource_type: str,
    field_mapping: FieldMapping,
    actions: list[str] | None = None,
    *,
    is_public: bool = False,
    auto_register_resources: bool = True,
) -> Any:
    """Class decorator that marks an entity for access-control.

    At class definition time this:
    1. Builds and stores a ``ResourceTypeConfig`` as ``cls.__access_config__``.
    2. Adds ``AuthorizableEntity`` protocol methods to the class.
    3. Makes the entity discoverable by ``get_access_config()`` for later
       registration into an application-owned ``ResourceTypeRegistry``.
    """

    def decorator(cls: type) -> type:
        config = ResourceTypeConfig(
            name=resource_type,
            field_mapping=field_mapping,
            is_public=is_public,
            auto_register_resources=auto_register_resources,
            entity_class=cls,
            actions=actions or [],
        )
        setattr(cls, _ACCESS_CONFIG_ATTR, config)

        # Add protocol methods
        cls.access_resource_type = classmethod(lambda _: resource_type)  # type: ignore[attr-defined]
        cls.access_field_mapping = classmethod(lambda _: field_mapping)  # type: ignore[attr-defined]
        cls.access_syncable_fields = classmethod(  # type: ignore[attr-defined]
            lambda _: list(field_mapping.mappings.keys())
        )
        cls.access_valid_actions = classmethod(lambda _: actions or [])  # type: ignore[attr-defined]

        def _grant_access(self: Any, rules: list[AccessRule]) -> list[DomainEvent]:
            from .events import ACLGrantRequested

            resource_id = getattr(self, field_mapping.external_id_field, None)
            return [
                ACLGrantRequested(
                    resource_type=resource_type,
                    resource_id=str(resource_id) if resource_id else None,
                    access_rules=rules,
                    aggregate_id=str(resource_id) if resource_id else None,
                    aggregate_type=resource_type,
                )
            ]

        cls.grant_access = _grant_access  # type: ignore[attr-defined]
        return cls

    return decorator
