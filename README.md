# System Architecture Guide: The Modular CQRS/DDD Toolkit

# Core Philosophy
This framework is a composable ecosystem for building Enterprise-grade, Domain-Driven Design (DDD) applications.

# 🚀 Technology Stack
- **Python**: 3.10, 3.11, 3.12 (Supported & Tested)
- **Domain Modeling**: Pydantic v2
- **Persistence**: SQLAlchemy 2.0 (Async) / PostgreSQL

Rule #1: Strict Isolation. cqrs-ddd-core must never depend on extensions (Identity, Multitenancy, etc.).

Rule #2: Intent-Based Packaging. We do not have a generic "utils" package. We have messaging, caching, notifications.

Rule #3: Polyglot Persistence. We explicitly separate the Write Side (Postgres/SQLAlchemy) from the Read Side (Mongo) to allow for scalable CQRS.

# Implementation Rules
Composition over Inheritance: When defining a Repository, use Mixins.

Correct: class MyRepo(MultitenantMixin, CachingMixin, SQLAlchemyRepository): ...

Context Propagation: Never pass tenant_id or user_id as function arguments in the Domain. Use the ContextVars provided by multitenancy and identity.

One-Way Data Flow: The Read Model (persistence-mongo) never writes back to the Event Store.

Interface Segregation: Domain services depend on IBlobStorage (in Core), never on boto3 (in file-storage).

# GROUP 1: The Foundation (Mandatory)

## cqrs-ddd-core

Scope: Interfaces (IRepository, IBlobStorage, IIdentityProvider), base classes (Aggregate, Command, Event), and In-Memory implementations.

No external dependencies.

## cqrs-ddd-persistence-sqlalchemy

Scope: PostgreSQL/SQLite implementation of Event Store, Outbox, and Repositories.

Why: ACID transactional safety for the "Write Side".

## cqrs-ddd-advanced-core (Optional)

Role: High-Complexity Patterns.

Contents: Snapshotting strategies, Upcasters, Conflict Resolution policies.

# Group 2: The Data & Scale Layer (High Performance)

## cqrs-ddd-persistence-mongo

Scope: MongoDB implementation for Read Models (Projections).

Why: Speed and flexibility for the "Read Side".

## cqrs-ddd-projections

Scope: The engine that syncs Write -> Read.

Features: Checkpointing, Replay, Async Workers.

## cqrs-ddd-caching (Renamed from parts of integrations)

Scope: Redis / Memcached implementations of ICache and IDistributedLock.

Why: Distributed locking is critical for Sagas.

# Group 3: The Security Layer (Identity & Access)

## cqrs-ddd-identity (Renamed from auth)

Scope: "Who are you?" (Authentication).

Implementations (Extras):

[keycloak]: OIDC/Keycloak handlers.

[ldap]: For legacy corporate directories.

[db]: Simple username/password tables (if not using OIDC).

Why: Rename to identity to distinguish from authz.

## cqrs-ddd-access-control (Renamed from authz)

Scope: "What can you do?" (Authorization).

Implementations:

RBAC: Simple Role-Based checks.

ABAC: The connector to your Stateful ABAC Engine.

Why: Keeps the complex policy logic separate from simple identity verification.

## cqrs-ddd-multitenancy

Scope: Context propagation (tenant_id) and DB isolation rules.

Why: Cross-cutting concern that touches almost every other package.

# Group 4: The Infrastructure Abstractions (Consolidated)
Here we solve the "Too Many Packages" problem. Use extras.

## cqrs-ddd-file-storage (Renamed from storage)

Scope: Implementations of IBlobStorage.

Extras: pip install cqrs-ddd-file-storage[s3, azure, gcs, dropbox]

Why: You don't want 5 different packages for "saving a file". One package, many drivers.

## cqrs-ddd-messaging (Extracted from integrations)

Scope: Implementations of IMessageBroker (for Domain Events).

Extras: [rabbitmq], [kafka], [redis], [sqs].

Why: Messaging is a distinct, complex architectural component.

## cqrs-ddd-observability (Renamed from telemetry)

Scope: Tracing, Metrics, and Logging.

Extras: [opentelemetry], [sentry], [prometheus].

Why: "Observability" is the modern term covering all three pillars.

## cqrs-ddd-notifications (New/Extracted)

Scope: Sending emails, SMS, Push.

Extras: [smtp], [sendgrid], [twilio].

Why: Keeps your domain pure from "side effects".

# Group 5: The "Intelligence" Layer

## cqrs-ddd-filtering

Scope: Your search_query_dsl integration and security wrapper. (https://github.com/mgourlis/search_query_dsl)

Why: Safe, flexible API filtering.

## cqrs-ddd-audit

Scope: Compliance logging (User X did Y).

Why: Distinct from technical logs; required for business/legal.

## cqrs-ddd-analytics

Scope: Connectors for Data Warehousing (OLAP).

Implementations:

Flatteners: Converts complex Events -> Flat Rows.

Loaders: [bigquery], [snowflake], [clickhouse].

Why: Moving data to the warehouse is different from Projections.

## cqrs-ddd-feature-flags

Scope: Toggles.

Implementations: Local DB, [unleash], [launchdarkly].

# Group 6: The Interface Adapters

## cqrs-ddd-fastapi

Scope: REST API helpers, Dependency Injection, Middleware.

## cqrs-ddd-django

Scope: Admin views, Signal bridges.

## cqrs-ddd-graphql

Scope: Strawberry integration for Mutations/Queries.

## cqrs-ddd-cli (New Suggestion)

Scope: Typer or Click helpers.

Why: This package helps write management commands like myapp replay-events or myapp create-tenant.
