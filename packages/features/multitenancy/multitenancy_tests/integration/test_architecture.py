"""Architecture boundary tests for cqrs_ddd_multitenancy.

Enforces that intra-package import rules are respected using pytest-archon.
These tests protect against accidental coupling that would violate the
layered architecture of the multitenancy package.
"""

from __future__ import annotations

import pytest
from pytest_archon import archrule

PACKAGE = "cqrs_ddd_multitenancy"


# ---------------------------------------------------------------------------
# Core primitives must not import higher-level modules
# ---------------------------------------------------------------------------


def test_context_does_not_import_mixins():
    """context.py is a primitive — it must not import from mixins."""
    (
        archrule("context must not import mixins")
        .match(f"{PACKAGE}.context")
        .should_not_import(f"{PACKAGE}.mixins")
        .check(PACKAGE)
    )


def test_context_does_not_import_contrib():
    """context.py has no framework dependencies."""
    (
        archrule("context must not import contrib")
        .match(f"{PACKAGE}.context")
        .should_not_import(f"{PACKAGE}.contrib")
        .check(PACKAGE)
    )


def test_context_does_not_import_admin():
    """context.py must not import admin (no circular dependency)."""
    (
        archrule("context must not import admin")
        .match(f"{PACKAGE}.context")
        .should_not_import(f"{PACKAGE}.admin")
        .check(PACKAGE)
    )


def test_context_does_not_import_database_routing():
    """context.py must not import database_routing."""
    (
        archrule("context must not import database_routing")
        .match(f"{PACKAGE}.context")
        .should_not_import(f"{PACKAGE}.database_routing")
        .check(PACKAGE)
    )


def test_context_does_not_import_infrastructure():
    """context.py must not import infrastructure modules."""
    (
        archrule("context must not import infrastructure")
        .match(f"{PACKAGE}.context")
        .should_not_import(f"{PACKAGE}.infrastructure")
        .check(PACKAGE)
    )


# ---------------------------------------------------------------------------
# Exceptions module must stay pure
# ---------------------------------------------------------------------------


def test_exceptions_does_not_import_mixins():
    """exceptions.py has no mixin dependencies."""
    (
        archrule("exceptions must not import mixins")
        .match(f"{PACKAGE}.exceptions")
        .should_not_import(f"{PACKAGE}.mixins")
        .check(PACKAGE)
    )


def test_exceptions_does_not_import_contrib():
    """exceptions.py has no framework dependencies."""
    (
        archrule("exceptions must not import contrib")
        .match(f"{PACKAGE}.exceptions")
        .should_not_import(f"{PACKAGE}.contrib")
        .check(PACKAGE)
    )


def test_exceptions_does_not_import_admin():
    """exceptions.py must not create circular dependency with admin."""
    (
        archrule("exceptions must not import admin")
        .match(f"{PACKAGE}.exceptions")
        .should_not_import(f"{PACKAGE}.admin")
        .check(PACKAGE)
    )


def test_exceptions_does_not_import_database_routing():
    """exceptions.py must not import database_routing."""
    (
        archrule("exceptions must not import database_routing")
        .match(f"{PACKAGE}.exceptions")
        .should_not_import(f"{PACKAGE}.database_routing")
        .check(PACKAGE)
    )


def test_exceptions_does_not_import_infrastructure():
    """exceptions.py must not import infrastructure modules."""
    (
        archrule("exceptions must not import infrastructure")
        .match(f"{PACKAGE}.exceptions")
        .should_not_import(f"{PACKAGE}.infrastructure")
        .check(PACKAGE)
    )


# ---------------------------------------------------------------------------
# Isolation config must stay framework-agnostic
# ---------------------------------------------------------------------------


def test_isolation_does_not_import_contrib():
    """isolation.py is a pure config module — no framework coupling."""
    (
        archrule("isolation must not import contrib")
        .match(f"{PACKAGE}.isolation")
        .should_not_import(f"{PACKAGE}.contrib")
        .check(PACKAGE)
    )


def test_isolation_does_not_import_infrastructure():
    """isolation.py must not import infrastructure modules."""
    (
        archrule("isolation must not import infrastructure")
        .match(f"{PACKAGE}.isolation")
        .should_not_import(f"{PACKAGE}.infrastructure")
        .check(PACKAGE)
    )


# ---------------------------------------------------------------------------
# Domain mixins must stay decoupled from contrib and infrastructure
# ---------------------------------------------------------------------------


def test_domain_mixins_do_not_import_contrib():
    """Domain-layer mixins must not depend on framework integrations."""
    (
        archrule("domain mixins must not import contrib")
        .match(f"{PACKAGE}.domain")
        .should_not_import(f"{PACKAGE}.contrib")
        .check(PACKAGE)
    )


def test_domain_mixins_do_not_import_infrastructure():
    """Domain-layer mixins must not depend on infrastructure."""
    (
        archrule("domain mixins must not import infrastructure")
        .match(f"{PACKAGE}.domain")
        .should_not_import(f"{PACKAGE}.infrastructure")
        .check(PACKAGE)
    )


# ---------------------------------------------------------------------------
# Application-layer mixins must not import contrib
# ---------------------------------------------------------------------------


def test_mixins_do_not_import_contrib():
    """Application-layer mixins (mixins.*) must not import contrib."""
    (
        archrule("mixins must not import contrib")
        .match(f"{PACKAGE}.mixins")
        .should_not_import(f"{PACKAGE}.contrib")
        .check(PACKAGE)
    )


def test_mixins_do_not_import_admin():
    """mixins must not create upward dependency on admin."""
    (
        archrule("mixins must not import admin")
        .match(f"{PACKAGE}.mixins")
        .should_not_import(f"{PACKAGE}.admin")
        .check(PACKAGE)
    )


# ---------------------------------------------------------------------------
# Projections must not couple to contrib or domain mixins
# ---------------------------------------------------------------------------


def test_projections_do_not_import_contrib():
    """Projection engine modules are agnostic of framework integrations."""
    (
        archrule("projections must not import contrib")
        .match(f"{PACKAGE}.projections")
        .should_not_import(f"{PACKAGE}.contrib")
        .check(PACKAGE)
    )


def test_projections_do_not_import_domain_mixins():
    """Projection engine does not depend on the domain mixin layer."""
    (
        archrule("projections must not import domain.mixins")
        .match(f"{PACKAGE}.projections")
        .should_not_import(f"{PACKAGE}.domain")
        .check(PACKAGE)
    )


# ---------------------------------------------------------------------------
# Admin must not import contrib (it is framework-agnostic)
# ---------------------------------------------------------------------------


def test_admin_does_not_import_contrib():
    """admin.py is framework-agnostic and must not import contrib."""
    (
        archrule("admin must not import contrib")
        .match(f"{PACKAGE}.admin")
        .should_not_import(f"{PACKAGE}.contrib")
        .check(PACKAGE)
    )


# ---------------------------------------------------------------------------
# contrib must not import infrastructure (observability etc.)
# ---------------------------------------------------------------------------


def test_contrib_does_not_import_infrastructure():
    """FastAPI integration must not depend on infrastructure internals."""
    (
        archrule("contrib must not import infrastructure")
        .match(f"{PACKAGE}.contrib")
        .should_not_import(f"{PACKAGE}.infrastructure")
        .check(PACKAGE)
    )


# ---------------------------------------------------------------------------
# database_routing must not import contrib
# ---------------------------------------------------------------------------


def test_database_routing_does_not_import_contrib():
    """database_routing.py is a framework-agnostic engine — no contrib."""
    (
        archrule("database_routing must not import contrib")
        .match(f"{PACKAGE}.database_routing")
        .should_not_import(f"{PACKAGE}.contrib")
        .check(PACKAGE)
    )
