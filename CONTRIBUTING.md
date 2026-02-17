# Contributing to CQRS-DDD Toolkit

Thank you for your interest in contributing! This document outlines the process for submitting changes.

## Pull Request Process

When you open a Pull Request (PR), a template will automatically load. Here is how to fill it out:

1.  **Description**:
    -   Replace the comment `<!-- Provide a brief description... -->` with a summary of your changes.
    -   Explain *why* the change is needed and *how* it addresses the issue.

2.  **Type of Change**:
    -   Mark the checkbox that applies to your change by putting an `x` in the brackets.
    -   Example: `[x] Bug fix`

3.  **Quality Assurance Checklist**:
    -   You **MUST** verify these items before submitting.
    -   Run `nox` locally to ensure all tests and linting pass.
    -   Run `pre-commit run --all-files` to ensure hooks pass.
    -   Mark each item with `[x]` as you confirm it.

4.  **Architectural Compliance**:
    -   Review your code against the architectural rules (defined in `system-prompt.md`).
    -   Ensure `cqrs-ddd-core` has no new dependencies.
    -   Mark items with `[x]` to certify compliance.

5.  **Testing**:
    -   Confirm that you have added tests for your changes.
    -   Mark with `[x]`.

## Development Workflow

1.  **Environment**: Use `.venv` and install dependencies with `pip install -e ".[dev]"`.
2.  **Testing**: Run `pytest` or `nox` to run tests.
3.  **Linting**: use `ruff check .` to lint your code.

## Definition of Done

A PR is considered "Done" when:
-   All CI checks pass (GitHub Actions).
-   Code coverage is preserved or increased.
-   The PR template is fully filled out.
