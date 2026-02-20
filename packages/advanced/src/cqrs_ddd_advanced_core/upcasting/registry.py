"""Upcasting infrastructure — base class, chain, and registry.

Event upcasting transforms serialised events written with an older schema
into the current schema **at read time**, so domain code can always work
with the latest version of an event.

Quick-start::

    # 1. Define an upcaster
    class OrderCreatedV1ToV2(EventUpcaster):
        event_type = "OrderCreated"
        source_version = 1
        target_version = 2

        def upcast(self, data: dict[str, Any]) -> dict[str, Any]:
            data.setdefault("currency", "EUR")
            return data

    # 2. Build a registry
    registry = UpcasterRegistry()
    registry.register(OrderCreatedV1ToV2())

    # 3. Transform stored event data
    chain = registry.chain_for("OrderCreated")
    data, final_version = chain.upcast("OrderCreated", raw_data, stored_version=1)

"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from cqrs_ddd_core.correlation import get_correlation_id
from cqrs_ddd_core.instrumentation import fire_and_forget_hook, get_hook_registry

if TYPE_CHECKING:
    from ..ports.upcasting import IEventUpcaster

logger = logging.getLogger("cqrs_ddd.upcasting")


# ── Concrete base class ─────────────────────────────────────────────


class EventUpcaster:
    """Convenience base class implementing :class:`IEventUpcaster`.

    Subclasses set the three class-level attributes and override
    :meth:`upcast`.  ``target_version`` defaults to ``source_version + 1``
    if not explicitly provided.

    Example::

        class OrderCreatedV1ToV2(EventUpcaster):
            event_type = "OrderCreated"
            source_version = 1
            # target_version auto-computed as 2

            def upcast(self, data: dict[str, Any]) -> dict[str, Any]:
                data.setdefault("currency", "EUR")
                return data
    """

    event_type: str = ""
    source_version: int = 0
    target_version: int = 0

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Auto-compute target_version if not explicitly set.
        if cls.target_version == 0 and cls.source_version > 0:
            cls.target_version = cls.source_version + 1

    def upcast(self, event_data: dict[str, Any]) -> dict[str, Any]:
        """Transform *event_data* from ``source_version`` → ``target_version``."""
        raise NotImplementedError


# ── Upcaster chain ──────────────────────────────────────────────────


class UpcasterChain:
    """Chains multiple upcasters together to transform events through versions.

    Returned by :meth:`UpcasterRegistry.chain_for`.
    """

    def __init__(self, upcasters: list[IEventUpcaster]) -> None:
        # Pre-sort by source_version for efficient iteration.
        self._upcasters = sorted(upcasters, key=lambda u: u.source_version)

    def upcast(
        self,
        event_type: str,
        event_data: dict[str, Any],
        stored_version: int,
    ) -> tuple[dict[str, Any], int]:
        """Recursively apply upcasters starting from *stored_version*.

        Returns:
            A ``(transformed_data, final_version)`` tuple.
        """
        data = event_data
        version = stored_version

        for upcaster in self._upcasters:
            if upcaster.event_type != event_type:
                continue
            if upcaster.source_version == version:
                fire_and_forget_hook(
                    get_hook_registry(),
                    f"upcast.apply.{event_type}",
                    {
                        "event.type": event_type,
                        "schema.from": version,
                        "schema.to": upcaster.target_version,
                        "correlation_id": get_correlation_id(),
                    },
                )
                data = upcaster.upcast(data)
                version = upcaster.target_version
                logger.debug(
                    "Upcast %s v%d → v%d",
                    event_type,
                    upcaster.source_version,
                    upcaster.target_version,
                )

        return data, version

    @property
    def latest_version(self) -> int:
        """The highest target version reachable by this chain."""
        if not self._upcasters:
            return 0
        return max(u.target_version for u in self._upcasters)


# ── Registry ────────────────────────────────────────────────────────


class UpcasterRegistry:
    """Central registry that indexes upcasters by event type.

    Usage::

        registry = UpcasterRegistry()
        registry.register(OrderCreatedV1ToV2())
        registry.register(OrderCreatedV2ToV3())

        chain = registry.chain_for("OrderCreated")
        data, version = chain.upcast("OrderCreated", raw, stored_version=1)
    """

    def __init__(self) -> None:
        self._upcasters: dict[str, list[IEventUpcaster]] = {}

    def register(self, upcaster: IEventUpcaster) -> None:
        """Register an upcaster instance."""
        key = upcaster.event_type
        if key not in self._upcasters:
            self._upcasters[key] = []

        # Guard against duplicate source_version for the same event type.
        for existing in self._upcasters[key]:
            if existing.source_version == upcaster.source_version:
                raise ValueError(
                    f"Duplicate upcaster for {key} v{upcaster.source_version} → "
                    f"v{upcaster.target_version}; already registered."
                )

        self._upcasters[key].append(upcaster)
        logger.debug(
            "Registered upcaster %s v%d → v%d",
            key,
            upcaster.source_version,
            upcaster.target_version,
        )

    def chain_for(self, event_type: str) -> UpcasterChain:
        """Return a :class:`UpcasterChain` for the given event type.

        Returns an empty chain if no upcasters are registered.
        """
        return UpcasterChain(self._upcasters.get(event_type, []))

    def upcast(
        self,
        event_type: str,
        event_data: dict[str, Any],
        stored_version: int,
    ) -> tuple[dict[str, Any], int]:
        """Convenience: upcast in one call without building a chain first."""
        return self.chain_for(event_type).upcast(event_type, event_data, stored_version)

    def has_upcasters(self, event_type: str) -> bool:
        """Return *True* if any upcasters are registered for *event_type*."""
        return bool(self._upcasters.get(event_type))

    def registered_event_types(self) -> list[str]:
        """Return all event types that have registered upcasters."""
        return list(self._upcasters.keys())

    def clear(self) -> None:
        """Remove all registrations (testing utility)."""
        self._upcasters.clear()
