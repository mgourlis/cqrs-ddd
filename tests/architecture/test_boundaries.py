from pytest_archon import archrule


def test_core_independence() -> None:
    """
    Core module should not import from persistence or advanced-core.
    It is the foundation and must remain independent.
    """
    (
        archrule("core_is_independent")
        .match("cqrs_ddd_core*")
        .should_not_import("cqrs_ddd_persistence_sqlalchemy*")
        .should_not_import("cqrs_ddd_advanced_core*")
        .check("cqrs_ddd_core")
    )


def test_persistence_layering() -> None:
    """
    Persistence layer can import from Core but not from Advanced Core.
    """
    (
        archrule("persistence_layering")
        .match("cqrs_ddd_persistence_sqlalchemy.core*")
        .should_not_import("cqrs_ddd_advanced_core*")
        .check("cqrs_ddd_persistence_sqlalchemy.core")
    )


def test_advanced_core_layering() -> None:
    """
    Advanced Core depends on Core. It typically shouldn't depend on specific persistence
    implementations, but that logic might vary. For now, we enforce it doesn't depend on
    SQL persistence to keep it generic.
    """
    (
        archrule("advanced_core_independence")
        .match("cqrs_ddd_advanced_core*")
        .should_not_import("cqrs_ddd_persistence_sqlalchemy*")
        .check("cqrs_ddd_advanced_core")
    )


def test_domain_isolation() -> None:
    """
    Domain layer should be self-contained.
    It must not import from adapters, ports, or middleware.
    """
    (
        archrule("domain_isolation")
        .match("cqrs_ddd_core.domain*")
        .should_not_import("cqrs_ddd_core.adapters*")
        .should_not_import("cqrs_ddd_core.ports*")
        .should_not_import("cqrs_ddd_core.middleware*")
        .check("cqrs_ddd_core")
    )


def test_primitives_isolation() -> None:
    """
    Primitives layer is the lowest level.
    It must not import from domain, adapters, ports, or middleware.
    """
    (
        archrule("primitives_isolation")
        .match("cqrs_ddd_core.primitives*")
        .should_not_import("cqrs_ddd_core.domain*")
        .should_not_import("cqrs_ddd_core.adapters*")
        .should_not_import("cqrs_ddd_core.ports*")
        .should_not_import("cqrs_ddd_core.middleware*")
        .check("cqrs_ddd_core")
    )


def test_ports_layering() -> None:
    """
    Ports (interfaces) should not depend on Adapters (implementations).
    """
    (
        archrule("ports_layering")
        .match("cqrs_ddd_core.ports*")
        .should_not_import("cqrs_ddd_core.adapters*")
        .check("cqrs_ddd_core")
    )


def test_advanced_ports_isolation() -> None:
    """
    Advanced Core Ports should not import from adapters.
    They may import from domain-like modules (sagas, background_jobs) for types.
    """
    (
        archrule("advanced_ports_isolation")
        .match("cqrs_ddd_advanced_core.ports*")
        .should_not_import("cqrs_ddd_advanced_core.adapters*")
        .check("cqrs_ddd_advanced_core")
    )


def test_advanced_adapters_isolation() -> None:
    """
    Core logic modules (sagas, cqrs, conflict) should not import from Adapters.
    Adapters are plugins/implementations and should be ignored by core logic.
    """
    (
        archrule("advanced_adapters_isolation")
        .match("cqrs_ddd_advanced_core.sagas*")
        .match("cqrs_ddd_advanced_core.cqrs*")
        .match("cqrs_ddd_advanced_core.conflict*")
        .should_not_import("cqrs_ddd_advanced_core.adapters*")
        .check("cqrs_ddd_advanced_core")
    )


def test_advanced_core_logic_isolation() -> None:
    """
    Advanced Core Logic (sagas, background_jobs) should be independent of adapters.
    (This overlaps with the above, but kept for clarity on specific modules).
    """
    (
        archrule("advanced_core_logic_isolation")
        .match("cqrs_ddd_advanced_core.sagas*")
        .match("cqrs_ddd_advanced_core.background_jobs*")
        .should_not_import("cqrs_ddd_advanced_core.adapters*")
        .check("cqrs_ddd_advanced_core")
    )
