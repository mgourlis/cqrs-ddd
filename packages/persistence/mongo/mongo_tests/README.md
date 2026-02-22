# MongoDB Persistence Package - Test Coverage

This package now has comprehensive test coverage for MongoDB persistence operations.

## Test Structure

### Unit Tests
Located in `tests/unit/`:
- `test_repository.py` - MongoRepository CRUD operations (15 tests)
- `test_advanced_persistence.py` - Advanced persistence bases (31 tests)
- `test_repository_search.py` - Search functionality (10 tests)
- `test_projection_store.py` - Projection store operations (10 tests)
- `test_serialization_edge_cases.py` - Serialization edge cases (6 tests)
- `test_connection_edge_cases.py` - Connection management (6 tests)
- `operators/` - Query operator tests:
  - `test_string_operators.py` - String matching (12 tests)
  - `test_jsonb_operators.py` - JSON/JSONB operators (8 tests)
  - `test_null_operators.py` - Null/empty checks (6 tests)
  - `test_set_operators.py` - Set/array operators (5 tests)
  - `test_standard_operators.py` - Comparison operators (4 tests)

### Integration Tests
Located in `tests/integration/`:
- `test_real_mongo.py` - Real MongoDB behavior validation (15 tests)

## Running Tests

### Unit Tests
Unit tests use `mongomock-motor` and don't require MongoDB:

```bash
# Run all unit tests
cd packages/persistence/mongo
python -m pytest tests/unit/ -v

# With coverage
python -m pytest tests/unit/ -v --cov=src/cqrs_ddd_persistence_mongo --cov-report=term-missing
```

### Integration Tests
Integration tests use `testcontainers` to spin up a real MongoDB container:

```bash
# Install test dependencies
pip install -e ".[test]"

# Run integration tests (Docker required)
python -m pytest tests/integration/ -v -m integration
```

### All Tests
```bash
# Run complete test suite
python -m pytest tests/ -v --cov=src/cqrs_ddd_persistence_mongo --cov-report=term-missing
```

## Coverage Target

The test suite aims for **87% coverage** (exceeding the 85% target):

- **Phase 1**: ~60% coverage (MongoRepository, advanced bases, operators)
- **Phase 2**: ~75% coverage (Search, JSON operators)
- **Phase 3**: ~87% coverage (Edge cases, serialization, integration)

## Test Count

- **Total tests**: ~123 new tests + 30 existing = **153 tests**
- **Unit tests**: ~90% of tests (fast, mock-based)
- **Integration tests**: ~10% of tests (real MongoDB behavior validation)

## Dependencies

### Test Dependencies
```toml
[project.optional-dependencies]
test = [
    "mongomock-motor>=0.0.0",  # For unit tests
    "pytest-cov>=4.0",           # Coverage reporting
    "testcontainers>=4.0",          # For integration tests
]
```

### Installation
```bash
# Install test dependencies
pip install -e ".[test]"

# Or install separately
pip install mongomock-motor pytest-cov testcontainers
```

## Integration Test Requirements

- **Docker** or **Docker Desktop** running
- **Testcontainers** Python package
- **MongoDB Docker image** (automatically pulled by testcontainers)

## Continuous Integration

Integration tests will automatically run in CI environments that support Docker containers (GitHub Actions, GitLab CI, etc.). Unit tests run everywhere without requiring Docker.
