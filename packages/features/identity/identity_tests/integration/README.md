# Keycloak Integration Tests

This directory contains integration tests for the Keycloak OAuth2 and Admin adapters.

## Prerequisites

- Docker installed and running
- `testcontainers` Python package installed

## Installation

Install the required dependencies:

```bash
pip install -e ".[keycloak-tests]"
```

Or manually install:

```bash
pip install testcontainers python-keycloak joserfc requests
```

## Running Tests

Run all integration tests:

```bash
pytest tests/integration/ -m integration
```

Run only OAuth2 tests:

```bash
pytest tests/integration/test_keycloak_oauth2.py -m integration
```

Run only Admin tests:

```bash
pytest tests/integration/test_keycloak_admin.py -m integration
```

Run with verbose output:

```bash
pytest tests/integration/ -m integration -v
```

## How It Works

The tests use `testcontainers-python` to spin up a real Keycloak instance in a Docker container:

1. **Container Setup**: The `keycloak_container` fixture starts Keycloak in development mode
2. **Readiness Check**: Waits for Keycloak's health endpoint to respond
3. **Test Execution**: Runs tests against the real Keycloak instance
4. **Cleanup**: Stops and removes the container after tests complete

## Test Fixtures

- `keycloak_container`: Manages the Keycloak Docker container lifecycle
- `keycloak_base_url`: Provides the Keycloak URL (http://localhost:<random-port>)
- `keycloak_oauth_config`: OAuth2 configuration for testing
- `keycloak_admin_config`: Admin configuration for testing
- `keycloak_identity_provider`: Initialized OAuth2 provider instance
- `keycloak_admin_adapter`: Initialized admin adapter instance
- `keycloak_test_realm`: Creates an isolated test realm (optional)

## Notes

- Tests use the `master` realm by default for simplicity
- Default admin credentials: `admin` / `admin123`
- Tests are marked with `@pytest.mark.integration` marker
- Container is shared across all tests in a module for efficiency
- Each test creates/uses test data that doesn't affect other tests

## Troubleshooting

### Container Won't Start

Ensure Docker is running:

```bash
docker ps
```

### Connection Refused

Wait for Keycloak to fully initialize - it may take 30-60 seconds on first run.

### Port Conflicts

The fixture automatically assigns random ports, so conflicts shouldn't occur.

### Slow Tests

Keycloak startup is slower than typical unit tests. This is expected for integration testing.
