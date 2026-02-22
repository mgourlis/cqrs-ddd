"""Unit tests for connection edge cases."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from cqrs_ddd_persistence_mongo.connection import MongoConnectionManager
from cqrs_ddd_persistence_mongo.exceptions import MongoConnectionError


# Phase 3, Step 12: Connection Edge Cases Tests (6 tests)


class TestConnectionSuccess:
    """Tests for successful connection scenarios."""

    @pytest.mark.asyncio
    async def test_connect_success(self):
        """Test successful connection."""
        mgr = MongoConnectionManager(url="mongodb://localhost:27017")

        # Mock Motor client
        mock_client = MagicMock()
        mock_client.admin.command = AsyncMock(return_value={"ok": 1})

        # Patch motor import to return mock client
        import motor.motor_asyncio

        original_motor_client = motor.motor_asyncio.AsyncIOMotorClient

        def mock_motor_client(*args, **kwargs):
            return mock_client

        motor.motor_asyncio.AsyncIOMotorClient = mock_motor_client

        try:
            client = await mgr.connect()

            assert client is not None
            assert mgr._client is not None
        finally:
            motor.motor_asyncio.AsyncIOMotorClient = original_motor_client

    @pytest.mark.asyncio
    async def test_multiple_connect_calls(self):
        """Test that multiple connect() calls return the same client."""
        mgr = MongoConnectionManager(url="mongodb://localhost:27017")

        # Mock Motor client
        mock_client = MagicMock()
        mock_client.admin.command = AsyncMock(return_value={"ok": 1})

        # Patch motor import
        import motor.motor_asyncio

        original_motor_client = motor.motor_asyncio.AsyncIOMotorClient

        def mock_motor_client(*args, **kwargs):
            return mock_client

        motor.motor_asyncio.AsyncIOMotorClient = mock_motor_client

        try:
            client1 = await mgr.connect()
            client2 = await mgr.connect()

            assert client1 is client2  # Same instance
        finally:
            motor.motor_asyncio.AsyncIOMotorClient = original_motor_client


class TestConnectionFailure:
    """Tests for connection failure scenarios."""

    @pytest.mark.asyncio
    async def test_connect_failure(self):
        """Test connection failure raises MongoConnectionError."""
        mgr = MongoConnectionManager(url="mongodb://invalid:99999")

        # Patch motor import to raise exception
        import motor.motor_asyncio

        original_motor_client = motor.motor_asyncio.AsyncIOMotorClient

        def mock_motor_client(*args, **kwargs):
            raise ConnectionError("Connection failed")

        motor.motor_asyncio.AsyncIOMotorClient = mock_motor_client

        try:
            with pytest.raises(MongoConnectionError, match="Connection failed"):
                await mgr.connect()
        finally:
            motor.motor_asyncio.AsyncIOMotorClient = original_motor_client


class TestHealthCheck:
    """Tests for health check functionality."""

    @pytest.mark.asyncio
    async def test_health_check_healthy(self):
        """Test health_check returns True when server is healthy."""
        mgr = MongoConnectionManager(url="mongodb://localhost:27017")

        # Mock Motor client
        mock_client = MagicMock()
        mock_client.admin.command = AsyncMock(return_value={"ok": 1})

        # Patch motor import
        import motor.motor_asyncio

        original_motor_client = motor.motor_asyncio.AsyncIOMotorClient

        def mock_motor_client(*args, **kwargs):
            return mock_client

        motor.motor_asyncio.AsyncIOMotorClient = mock_motor_client

        try:
            await mgr.connect()
            is_healthy = await mgr.health_check()

            assert is_healthy is True
        finally:
            motor.motor_asyncio.AsyncIOMotorClient = original_motor_client

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self):
        """Test health_check returns False when server is unhealthy."""
        mgr = MongoConnectionManager(url="mongodb://localhost:27017")

        # Mock Motor client
        mock_client = MagicMock()
        mock_client.admin.command = AsyncMock(side_effect=Exception("Ping failed"))

        # Patch motor import
        import motor.motor_asyncio

        original_motor_client = motor.motor_asyncio.AsyncIOMotorClient

        def mock_motor_client(*args, **kwargs):
            return mock_client

        motor.motor_asyncio.AsyncIOMotorClient = mock_motor_client

        try:
            await mgr.connect()
            is_healthy = await mgr.health_check()

            assert is_healthy is False
        finally:
            motor.motor_asyncio.AsyncIOMotorClient = original_motor_client

    @pytest.mark.asyncio
    async def test_health_check_without_connect(self):
        """Test health_check returns False when not connected."""
        mgr = MongoConnectionManager(url="mongodb://localhost:27017")

        is_healthy = await mgr.health_check()

        assert is_healthy is False


class TestAccessBeforeConnect:
    """Tests for accessing client before connection."""

    def test_access_before_connect_raises(self):
        """Test that accessing client before connect raises error."""
        mgr = MongoConnectionManager(url="mongodb://localhost:27017")

        with pytest.raises(MongoConnectionError, match="Not connected"):
            _ = mgr.client
