"""Integration test configuration with Keycloak container."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pytest
import requests

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture(scope="module")
def keycloak_container() -> Generator:
    """
    Create a Keycloak container using testcontainers.

    Uses DockerContainer with start-dev command and admin/health env so the
    container starts Keycloak without requiring the python-keycloak package
    (unlike testcontainers.keycloak.KeycloakContainer which imports it).
    """
    pytest.importorskip("testcontainers")

    from testcontainers.core.container import DockerContainer

    keycloak = DockerContainer("quay.io/keycloak/keycloak:latest")
    keycloak.with_exposed_ports(8080, 9000)
    keycloak.with_env("KC_BOOTSTRAP_ADMIN_USERNAME", "admin")
    keycloak.with_env("KC_BOOTSTRAP_ADMIN_PASSWORD", "admin123")
    keycloak.with_env("KEYCLOAK_ADMIN", "admin")
    keycloak.with_env("KEYCLOAK_ADMIN_PASSWORD", "admin123")
    keycloak.with_env("KC_HEALTH_ENABLED", "true")
    keycloak.with_command("start-dev")

    keycloak.start()

    host = keycloak.get_container_host_ip()
    port_8080 = keycloak.get_exposed_port(8080)
    port_9000 = keycloak.get_exposed_port(9000)
    health_urls = [
        f"http://{host}:{port_9000}/health/ready",  # Keycloak 25+ management port
        f"http://{host}:{port_8080}/health/ready",
    ]
    max_attempts = 90
    ready = False
    for _ in range(max_attempts):
        for health_url in health_urls:
            try:
                if requests.get(health_url, timeout=2).status_code == 200:
                    ready = True
                    break
            except requests.RequestException:
                pass
        if ready:
            break
        time.sleep(1)
    if not ready:
        keycloak.stop()
        raise TimeoutError(
            f"Keycloak did not become ready within {max_attempts} seconds"
        )

    time.sleep(2)
    yield keycloak

    keycloak.stop()


@pytest.fixture(scope="module")
def keycloak_base_url(keycloak_container) -> str:
    """
    Get the base URL for Keycloak from the container.

    Returns:
        Base URL for Keycloak (e.g., "http://localhost:32768")
    """
    host = keycloak_container.get_container_host_ip()
    port = keycloak_container.get_exposed_port(8080)
    return f"http://{host}:{port}"


@pytest.fixture
def keycloak_admin_config(keycloak_base_url: str):
    """
    Create KeycloakAdminConfig for testing.

    Returns:
        KeycloakAdminConfig instance
    """
    from cqrs_ddd_identity.admin import KeycloakAdminConfig

    return KeycloakAdminConfig(
        server_url=keycloak_base_url,
        realm="master",
        client_id="admin-cli",
        admin_username="admin",
        admin_password="admin123",
        verify=False,
    )


@pytest.fixture
def keycloak_oauth_config(keycloak_base_url: str):
    """
    Create KeycloakConfig for OAuth2 testing.

    Returns:
        KeycloakConfig instance for OAuth2 operations
    """
    from cqrs_ddd_identity.oauth2 import KeycloakConfig

    return KeycloakConfig(
        server_url=keycloak_base_url,
        realm="master",
        client_id="admin-cli",
        verify=False,
    )


@pytest.fixture
async def keycloak_admin_adapter(keycloak_admin_config):
    """
    Create KeycloakAdminAdapter instance.

    Returns:
        Initialized KeycloakAdminAdapter
    """
    from cqrs_ddd_identity.admin import KeycloakAdminAdapter

    return KeycloakAdminAdapter(keycloak_admin_config)


@pytest.fixture
async def keycloak_identity_provider(keycloak_oauth_config):
    """
    Create KeycloakIdentityProvider instance.

    Returns:
        Initialized KeycloakIdentityProvider
    """
    from cqrs_ddd_identity.oauth2 import KeycloakIdentityProvider

    return KeycloakIdentityProvider(keycloak_oauth_config)


@pytest.fixture
async def keycloak_test_realm(keycloak_admin_adapter):
    """
    Create a test realm for isolated testing.

    This fixture creates a new realm with a test client and user
    to avoid polluting the master realm.

    Returns:
        Dictionary with realm name, client_id, and test user credentials
    """

    # Create a test realm
    realm_name = "test-realm"

    try:
        # Use keycloak admin client to create realm directly
        from keycloak import KeycloakAdmin

        admin_client = KeycloakAdmin(
            server_url=keycloak_admin_adapter.config.server_url,
            username=keycloak_admin_adapter.config.admin_username,
            password=keycloak_admin_adapter.config.admin_password,
            verify=keycloak_admin_adapter.config.verify,
        )
        admin_client.create_realm(
            payload={
                "realm": realm_name,
                "enabled": True,
            }
        )
    except Exception as e:
        # Realm might already exist from previous run
        print(f"Warning: Could not create realm {realm_name}: {e}")

    # Create a test client
    client_id = "test-client"
    try:
        admin_client.create_client(
            realm_name=realm_name,
            payload={
                "clientId": client_id,
                "secret": "test-secret",
                "redirectUris": ["http://localhost:8080/*"],
                "publicClient": False,
                "enabled": True,
                "directAccessGrantsEnabled": True,
                "serviceAccountsEnabled": True,
            },
        )
    except Exception as e:
        print(f"Warning: Could not create client {client_id}: {e}")

    # Create a test user
    username = "testuser"
    try:
        admin_client.create_user(
            realm_name=realm_name,
            payload={
                "username": username,
                "email": "test@example.com",
                "firstName": "Test",
                "lastName": "User",
                "enabled": True,
                "emailVerified": True,
                "credentials": [{"value": "password123", "type": "password"}],
            },
        )
    except Exception as e:
        print(f"Warning: Could not create user {username}: {e}")

    yield {
        "realm": realm_name,
        "client_id": client_id,
        "client_secret": "test-secret",
        "username": username,
        "password": "password123",
    }

    # Cleanup: Delete test realm
    try:
        admin_client.delete_realm(realm_name=realm_name)
    except Exception as e:
        print(f"Warning: Could not delete realm {realm_name}: {e}")
