## Description
<!-- Provide a brief description of the changes and the architectural goal. -->

## Type of Change
- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Architectural Refactor
- [ ] Documentation update

## Quality Assurance Checklist
- [ ] **Nox**: All sessions passed locally (`nox`).
- [ ] **Pre-commit**: Hooks ran successfully (`pre-commit run --all-files`).
- [ ] **Test Coverage**: Logic coverage is **>80%**.
- [ ] **Type Safety**: No `mypy` errors (strict mode).
- [ ] **Linting**: Code is clean and formatted via `ruff`.

## Architectural Compliance
- [ ] **Layering**: `cqrs-ddd-core` imports NOTHING from `persistence` or `advanced-core`.
- [ ] **Verification**: `nox -s arch_check` passes.
- [ ] **DDD Patterns**: Proper use of Aggregate Roots, Events, and Value Objects.
- [ ] **Isolation**: Infrastructure concerns are kept out of the domain model.

## Testing
- [ ] **Unit Tests**: Added for all new logic.
- [ ] **Integration Tests**: Added for persistence/database interactions.
- [ ] **Edge Cases**: Verified Pydantic fallbacks (if applicable).

## Screenshots/Logs (if applicable)
<!-- Add any visual proof or execution logs. -->
