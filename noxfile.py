import nox

# Standard locations for the code
LOCATIONS = [
    "packages/core/src",
    "packages/specifications/src",
    "packages/advanced/src",
    "packages/persistence/sqlalchemy/src",
    "packages/persistence/mongo/src",
    "packages/infrastructure/redis/src",
    "packages/infrastructure/messaging/src",
    "packages/infrastructure/observability/src",
    "packages/engines/projections/src",
    "packages/features/filtering/src",
    "tests",
]


@nox.session(python=["3.10", "3.11", "3.12"])
def tests(session: nox.Session) -> None:
    """Run the complete test suite with coverage."""
    # Install packages in dependency order
    session.install("-e", "./packages/core")
    session.install("-e", "./packages/specifications")
    session.install("-e", "./packages/advanced")
    session.install("-e", "./packages/persistence/sqlalchemy")
    session.install("-e", "./packages/persistence/mongo")
    session.install("-e", "./packages/infrastructure/redis")
    session.install("-e", "./packages/infrastructure/messaging[rabbitmq,kafka,sqs]")
    session.install("-e", "./packages/infrastructure/observability")
    session.install("-e", "./packages/engines/projections")
    session.install("-e", "./packages/features/filtering")
    session.install("-e", ".[dev,geometry]")
    session.run("pytest", *session.posargs)


@nox.session(python=["3.10", "3.11", "3.12"])
def autoformat(session: nox.Session) -> None:
    """Fix linting issues and format code."""
    session.install("ruff")
    session.run("ruff", "check", "--fix", ".")
    session.run("ruff", "format", ".")


@nox.session(python=["3.10", "3.11", "3.12"])
def lint(session: nox.Session) -> None:
    """Run ruff linter and formatter checks."""
    session.install("ruff")
    session.run("ruff", "check", ".")
    session.run("ruff", "format", "--check", ".")


@nox.session(python=["3.10", "3.11", "3.12"])
def type_check(session: nox.Session) -> None:
    """Run mypy static type analysis."""
    # Install packages in dependency order
    session.install("-e", "./packages/core")
    session.install("-e", "./packages/specifications")
    session.install("-e", "./packages/advanced")
    session.install("-e", "./packages/persistence/sqlalchemy")
    session.install("-e", "./packages/persistence/mongo")
    session.install("-e", "./packages/infrastructure/redis")
    session.install("-e", "./packages/infrastructure/messaging[rabbitmq,kafka,sqs]")
    session.install("-e", "./packages/infrastructure/observability")
    session.install("-e", "./packages/engines/projections")
    session.install("-e", "./packages/features/filtering")
    session.install(
        "mypy",
        "pydantic",
        "sqlalchemy",
        "aiosqlite",
        "pytest",
        "pytest-asyncio",
    )
    session.run("mypy", ".")


@nox.session(python=["3.10", "3.11", "3.12"])
def complexity(session: nox.Session) -> None:
    """Measure cognitive complexity using complexipy."""
    session.install("complexipy")
    session.run("complexipy", ".")


@nox.session(python=["3.10", "3.11", "3.12"])
def arch_check(session: nox.Session) -> None:
    """Verify architectural boundaries using pytest-archon."""
    # Install packages in dependency order
    session.install("-e", "./packages/core")
    session.install("-e", "./packages/specifications")
    session.install("-e", "./packages/advanced")
    session.install("-e", "./packages/persistence/sqlalchemy")
    session.install("-e", "./packages/persistence/mongo")
    session.install("-e", "./packages/infrastructure/redis")
    session.install("-e", "./packages/infrastructure/messaging[rabbitmq,kafka,sqs]")
    session.install("-e", "./packages/infrastructure/observability")
    session.install("-e", "./packages/engines/projections")
    session.install("-e", "./packages/features/filtering")
    session.install("-e", ".[dev,geometry]")
    session.run("pytest", "--no-cov", "tests/architecture", *session.posargs)


@nox.session(python=["3.10", "3.11", "3.12"])
def spell_check(session: nox.Session) -> None:
    """Check spelling using cspell via npm."""
    session.run("npm", "install", "-g", "cspell", external=True)
    session.run("cspell", "**/*", "--config", "cspell.json", external=True)


@nox.session(python=["3.10", "3.11", "3.12"])
def dead_code(session: nox.Session) -> None:
    """Scan for unused code using vulture."""
    session.install("vulture")
    session.run("vulture", "--exclude", ".nox", *LOCATIONS)
