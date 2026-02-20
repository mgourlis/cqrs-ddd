"""Phase 1 package boundary tests: no cross-layer imports."""

from pytest_archon import archrule


def test_messaging_no_persistence_or_features() -> None:
    """Messaging must not import persistence or features."""
    (
        archrule("messaging_independence")
        .match("cqrs_ddd_messaging*")
        .should_not_import("cqrs_ddd_persistence_*")
        .should_not_import("cqrs_ddd_filtering*")
        .check("cqrs_ddd_messaging")
    )


def test_mongo_no_messaging_or_observability() -> None:
    """Mongo persistence must not import messaging or observability."""
    (
        archrule("mongo_independence")
        .match("cqrs_ddd_persistence_mongo*")
        .should_not_import("cqrs_ddd_messaging*")
        .should_not_import("cqrs_ddd_observability*")
        .check("cqrs_ddd_persistence_mongo")
    )


def test_projections_no_filtering() -> None:
    """Projections engine must not import filtering."""
    (
        archrule("projections_no_filtering")
        .match("cqrs_ddd_projections*")
        .should_not_import("cqrs_ddd_filtering*")
        .check("cqrs_ddd_projections")
    )


def test_filtering_no_infrastructure() -> None:
    """Filtering must not import infrastructure packages (messaging, observability)."""
    (
        archrule("filtering_no_infrastructure")
        .match("cqrs_ddd_filtering*")
        .should_not_import("cqrs_ddd_messaging*")
        .should_not_import("cqrs_ddd_observability*")
        .check("cqrs_ddd_filtering")
    )


def test_observability_no_persistence() -> None:
    """Observability must not import persistence."""
    (
        archrule("observability_no_persistence")
        .match("cqrs_ddd_observability*")
        .should_not_import("cqrs_ddd_persistence_*")
        .check("cqrs_ddd_observability")
    )
