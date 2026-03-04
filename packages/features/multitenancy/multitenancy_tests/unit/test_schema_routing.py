from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cqrs_ddd_multitenancy.context import SYSTEM_TENANT, reset_tenant, set_tenant
from cqrs_ddd_multitenancy.exceptions import (
    TenantIsolationError,
    TenantProvisioningError,
)
from cqrs_ddd_multitenancy.isolation import IsolationConfig, TenantIsolationStrategy
from cqrs_ddd_multitenancy.schema_routing import (
    SchemaRouter,
    reset_search_path,
    set_search_path,
    with_tenant_schema,
)


def make_schema_config(**kwargs):
    return IsolationConfig(
        strategy=TenantIsolationStrategy.SCHEMA_PER_TENANT,
        **kwargs,
    )


@pytest.fixture
def mock_session():
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = "public"
    session.execute.return_value = mock_result
    return session


def test_schema_router_requires_schema_strategy():
    config = IsolationConfig(strategy=TenantIsolationStrategy.DISCRIMINATOR_COLUMN)
    with pytest.raises(ValueError, match="SCHEMA_PER_TENANT"):
        SchemaRouter(config)


def test_schema_router_config_property():
    config = make_schema_config()
    router = SchemaRouter(config)
    assert router.config is config


def test_schema_router_default_search_path_property():
    config = make_schema_config(default_schema="myschema")
    router = SchemaRouter(config)
    assert router.default_search_path == "myschema"

    router2 = SchemaRouter(config, default_search_path="override")
    assert router2.default_search_path == "override"


def test_schema_router_get_schema_name():
    config = make_schema_config(schema_prefix="tenant_")
    router = SchemaRouter(config)
    assert router.get_schema_name("t1") == "tenant_t1"


def test_schema_router_get_search_path():
    config = make_schema_config(schema_prefix="tenant_")
    router = SchemaRouter(config, default_search_path="public")
    assert router.get_search_path("t1") == "tenant_t1, public"


@pytest.mark.asyncio
async def test_schema_router_set_search_path(mock_session):
    config = make_schema_config()
    router = SchemaRouter(config)

    path = await router.set_search_path(mock_session, "t1")
    assert path == "public"

    # Two executes: SHOW search_path, then SET search_path
    assert mock_session.execute.call_count == 2
    args, _ = mock_session.execute.call_args
    assert "SET search_path TO" in str(args[0])


@pytest.mark.asyncio
async def test_schema_router_set_search_path_invalid_schema():
    config = make_schema_config(schema_prefix="bad!schema!")
    router = SchemaRouter(config)
    session = AsyncMock()
    with pytest.raises(TenantIsolationError):
        await router.set_search_path(session, "t1")


@pytest.mark.asyncio
async def test_schema_router_reset_search_path(mock_session):
    config = make_schema_config()
    router = SchemaRouter(config)

    await router.reset_search_path(mock_session, "public")

    mock_session.execute.assert_called_once()
    args, _ = mock_session.execute.call_args
    assert "SET search_path TO" in str(args[0])


@pytest.mark.asyncio
async def test_schema_router_reset_search_path_uses_default(mock_session):
    config = make_schema_config(default_schema="mydefault")
    router = SchemaRouter(config)

    await router.reset_search_path(mock_session)  # no previous_path
    args, _ = mock_session.execute.call_args
    assert "SET search_path TO" in str(args[0])


@pytest.mark.asyncio
async def test_schema_router_reset_search_path_invalid_path():
    config = make_schema_config()
    router = SchemaRouter(config)
    session = AsyncMock()
    with pytest.raises(TenantIsolationError):
        await router.reset_search_path(session, previous_path="bad!path!")


def test_schema_router_get_schema_translate_map():
    config = make_schema_config()
    router = SchemaRouter(config)
    translate_map = router.get_schema_translate_map("t1")
    assert translate_map["tenant"] == "tenant_t1"


def test_schema_router_get_schema_translate_map_no_tenant():
    config = make_schema_config()
    router = SchemaRouter(config)
    # No tenant in context → empty dict
    result = router.get_schema_translate_map()
    assert result == {}


def test_schema_router_get_schema_translate_map_explicit_tenant():
    config = make_schema_config(schema_prefix="acme_")
    router = SchemaRouter(config)
    result = router.get_schema_translate_map(tenant_id="foo")
    assert result["tenant"] == "acme_foo"


@pytest.mark.asyncio
async def test_schema_router_with_schema_uses_context(mock_session):
    config = make_schema_config(schema_prefix="t_")
    router = SchemaRouter(config)

    token = set_tenant("acme")
    try:
        async with router.with_schema(mock_session) as schema:
            assert schema == "t_acme"
    finally:
        reset_tenant(token)


@pytest.mark.asyncio
async def test_schema_router_with_schema_explicit_tenant(mock_session):
    config = make_schema_config(schema_prefix="t_")
    router = SchemaRouter(config)

    async with router.with_schema(mock_session, "widget") as schema:
        assert schema == "t_widget"


@pytest.mark.asyncio
async def test_schema_router_with_schema_resets_on_exit(mock_session):
    config = make_schema_config(schema_prefix="t_")
    router = SchemaRouter(config)

    async with router.with_schema(mock_session, "acme"):
        pass  # just verify entry and clean exit

    # SHOW call + SET enter + SET restore
    assert mock_session.execute.call_count == 3


@pytest.mark.asyncio
async def test_schema_router_with_schema_no_tenant_raises():
    config = make_schema_config()
    router = SchemaRouter(config)
    session = AsyncMock()

    with pytest.raises(TenantIsolationError, match="no tenant"):
        async with router.with_schema(session):
            pass


@pytest.mark.asyncio
async def test_schema_router_create_tenant_schema_already_exists(mock_session):
    config = make_schema_config()
    router = SchemaRouter(config)

    # schema_exists → returns a row (not None)
    result_exists = MagicMock()
    result_exists.scalar.return_value = 1
    mock_session.execute.return_value = result_exists

    await router.create_tenant_schema(mock_session, "t1")
    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_schema_router_create_tenant_schema_creates_new(mock_session):
    config = make_schema_config()
    router = SchemaRouter(config)

    call_count = 0

    async def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        # First call: information_schema check → None (doesn't exist)
        result.scalar.return_value = None if call_count == 1 else None
        return result

    mock_session.execute.side_effect = side_effect
    await router.create_tenant_schema(mock_session, "t1")
    assert call_count == 2  # select + create


@pytest.mark.asyncio
async def test_schema_router_create_tenant_schema_rollback_on_error():
    config = make_schema_config()
    router = SchemaRouter(config)
    session = AsyncMock()

    # First execute succeeds (schema check), second raises
    call_count = 0

    async def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            result = MagicMock()
            result.scalar.return_value = None
            return result
        raise RuntimeError("DB error")

    session.execute.side_effect = side_effect
    with pytest.raises(TenantProvisioningError):
        await router.create_tenant_schema(session, "t1")
    session.rollback.assert_called_once()


@pytest.mark.asyncio
async def test_schema_router_drop_tenant_schema(mock_session):
    config = make_schema_config()
    router = SchemaRouter(config)

    await router.drop_tenant_schema(mock_session, "t1")
    mock_session.execute.assert_called_once()
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_schema_router_drop_tenant_schema_cascade(mock_session):
    config = make_schema_config()
    router = SchemaRouter(config)

    await router.drop_tenant_schema(mock_session, "t1", cascade=True)
    args, _ = mock_session.execute.call_args
    assert "CASCADE" in str(args[0])


@pytest.mark.asyncio
async def test_schema_router_drop_tenant_schema_rollback_on_error():
    config = make_schema_config()
    router = SchemaRouter(config)
    session = AsyncMock()
    session.execute.side_effect = RuntimeError("DB error")

    with pytest.raises(TenantProvisioningError):
        await router.drop_tenant_schema(session, "t1")
    session.rollback.assert_called_once()


@pytest.mark.asyncio
async def test_schema_router_schema_exists_true(mock_session):
    config = make_schema_config()
    router = SchemaRouter(config)

    result = MagicMock()
    result.scalar.return_value = 1
    mock_session.execute.return_value = result

    assert await router.schema_exists(mock_session, "t1") is True


@pytest.mark.asyncio
async def test_schema_router_schema_exists_false(mock_session):
    config = make_schema_config()
    router = SchemaRouter(config)

    result = MagicMock()
    result.scalar.return_value = None
    mock_session.execute.return_value = result

    assert await router.schema_exists(mock_session, "t1") is False


def test_schema_router_get_connection_from_session():
    config = make_schema_config()
    router = SchemaRouter(config)

    # A session has .connection attribute
    session = MagicMock()
    session.connection = MagicMock()

    result = router._get_connection(session)
    # When session has .connection, it returns the session itself
    assert result is session


def test_schema_router_get_connection_from_connection():
    config = make_schema_config()
    router = SchemaRouter(config)

    # A raw connection has no .connection attribute
    conn = MagicMock(spec=[])  # no .connection attribute

    result = router._get_connection(conn)
    assert result is conn


@pytest.mark.asyncio
async def test_module_set_search_path(mock_session):
    config = make_schema_config()
    previous = await set_search_path(mock_session, "t1", config=config)
    assert previous == "public"


@pytest.mark.asyncio
async def test_module_reset_search_path(mock_session):
    config = make_schema_config()
    await reset_search_path(mock_session, "public", config=config)
    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_module_with_tenant_schema(mock_session):
    config = make_schema_config(schema_prefix="tnt_")

    async with with_tenant_schema(mock_session, "foo", config=config) as schema:
        assert schema == "tnt_foo"
