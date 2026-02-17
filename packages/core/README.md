# cqrs-ddd-core

**The lightweight, pure-Python foundation for Domain-Driven Design (DDD) and CQRS architectures.**

[PyPI version](https://badge.fury.io/py/cqrs-ddd-core) | [Python Versions](https://pypi.org/project/cqrs-ddd-core/) | [License: MIT](https://opensource.org/licenses/MIT)

---

## 📖 Overview

`cqrs-ddd-core` is the bedrock of a modular enterprise ecosystem. It provides the **Interfaces (Ports)**, **Base Classes**, and **Testing Utilities** needed to build complex applications without coupling your business logic to specific frameworks or databases.

### Key Philosophy
* **Zero Infrastructure Dependencies:** This package contains **NO** SQLAlchemy, Redis, or Web Framework code. It is pure Python logic.
* **Pydantic First (But Optional):** Classes are designed to work seamlessly with Pydantic for validation and schema generation, but gracefully degrade to standard Python objects if Pydantic is missing.
* **Batteries Included for Testing:** Includes in-memory implementations of all interfaces, allowing you to unit test your domain immediately without mocking.

---

## 📦 Installation

To install the core package:

    pip install cqrs-ddd-core

**Recommended:** If you want the Pydantic features (Validation, JSON Schema), use the extra:

    pip install "cqrs-ddd-core[pydantic]"

---

## 🚀 Quick Start

### 1. Define Domain Events
Events are immutable facts that happened in the past. We recommend inheriting from `DomainEvent`. If Pydantic is installed, this gives you automatic validation.

    from cqrs_ddd_core.domain.events import DomainEvent
    from uuid import UUID

    class UserRegistered(DomainEvent):
        user_id: UUID
        email: str
        username: str
        # Pydantic validation works automatically!

### 2. Define an Aggregate Root
Aggregates enforce consistency boundaries. They hold state and produce events.

    from cqrs_ddd_core.domain.aggregate import AggregateRoot
    from .events import UserRegistered
    import uuid

    class User(AggregateRoot):
        username: str
        email: str
        is_active: bool = True

        @classmethod
        def register(cls, username: str, email: str) -> "User":
            user_id = uuid.uuid4()
            # Initialize aggregate
            user = cls(id=user_id, username=username, email=email)

            # Record the event (staged for persistence)
            user.add_event(UserRegistered(
                user_id=user_id,
                email=email,
                username=username
            ))
            return user

### 3. Define Interfaces (Ports)
Your domain should depend on *contracts*, not implementations.

    from cqrs_ddd_core.ports.repository import IRepository

    # This is just a Protocol.
    # The actual implementation (SQLAlchemy/Mongo) lives in a separate package.
    class IUserRepository(IRepository[User]):
        pass

### 4. Use CQRS Commands
Commands represent intent. They are immutable and validated before execution.

    from cqrs_ddd_core.cqrs.command import Command

    class RegisterUser(Command):
        username: str
        email: str
        # Fields are immutable (frozen=True) by default

---

## 🧪 Testing (The "Batteries Included" Part)

You don't need to spin up Docker or install Postgres to test your domain logic. Use the `InMemory` fakes provided by the core.

    import pytest
    from cqrs_ddd_core.adapters.memory.repository import InMemoryRepository
    from my_app.domain.user import User

    @pytest.mark.asyncio
    async def test_user_persistence():
        # 1. Setup Fake Infrastructure
        repo = InMemoryRepository[User]()

        # 2. Execute Domain Logic
        user = User.register("alice", "alice@example.com")
        await repo.add(user)

        # 3. Assert
        fetched_user = await repo.get(user.id)
        assert fetched_user.username == "alice"

        # Check if events were generated
        events = user.collect_events()
        assert len(events) == 1
        assert events[0].email == "alice@example.com"

---

## 🧩 Ecosystem

This package is part of a larger modular toolkit:

| Package | Role |
| :--- | :--- |
| **`cqrs-ddd-core`** | **Foundational Interfaces & Logic (You are here)** |
| `cqrs-ddd-persistence-sqlalchemy` | Production-ready Event Store & Repositories (Postgres) |
| `cqrs-ddd-persistence-mongo` | High-performance Read Models (MongoDB) |
| `cqrs-ddd-fastapi` | Dependency Injection & Middleware |
| `cqrs-ddd-projections` | Async workers to sync Write -> Read models |

---

## 🛠️ Contribution

1.  **Strict Rule:** No external dependencies allowed in `core` (except Pydantic).
2.  **Typing:** All interfaces must use `typing.Protocol`.
3.  **Async:** All I/O interfaces must be `async`.

## 📄 License

MIT
