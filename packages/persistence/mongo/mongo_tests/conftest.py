"""Test configuration for MongoDB persistence package."""

import pytest

from cqrs_ddd_persistence_mongo import MongoConnectionManager

pytest_plugins = ["pytest_asyncio"]


class MockSession:
    """Mock MongoDB session for testing with mongomock.

    Motor's ClientSession uses sync start_transaction() and end_session();
    commit_transaction/abort_transaction are async. Match that so UoW doesn't
    await the wrong thing.
    """

    def __init__(self):
        self._in_transaction = False

    def in_transaction(self):
        """Check if session is in a transaction."""
        return self._in_transaction

    def start_transaction(self):
        """Start a transaction (sync like Motor)."""
        self._in_transaction = True

    async def commit_transaction(self):
        """Commit the transaction."""
        self._in_transaction = False

    async def abort_transaction(self):
        """Abort the transaction."""
        self._in_transaction = False

    def end_session(self):
        """End the session (sync like Motor)."""
        self._in_transaction = False


@pytest.fixture
async def mongo_connection():
    """Create a MongoDB connection for testing."""
    # Use mongomock for unit tests to avoid real database dependency
    try:
        from mongomock_motor import AsyncMongoMockClient

        # Create a mock connection manager
        connection = MongoConnectionManager.__new__(MongoConnectionManager)
        connection._client = AsyncMongoMockClient(default_database_name="test_db")
        connection._database = "test_db"
        connection._url = "mongodb://mock:27017"

        # Make connect() return the client and mark as "connected"
        async def _mock_connect():
            return connection._client

        connection.connect = _mock_connect

        yield connection

    except ImportError:
        pytest.skip("mongomock-motor not installed")


@pytest.fixture
async def mongo_connection_with_mock_session():
    """Create a MongoDB connection with session support for UoW tests."""
    # Use mongomock for unit tests to avoid real database dependency
    try:
        from mongomock_motor import AsyncMongoMockClient
        from unittest.mock import AsyncMock

        # Create a mock connection manager
        connection = MongoConnectionManager.__new__(MongoConnectionManager)
        client = AsyncMongoMockClient(default_database_name="test_db")
        connection._client = client
        connection._database = "test_db"
        connection._url = "mongodb://mock:27017"

        # Make connect() return the client
        async def _mock_connect():
            return connection._client

        connection.connect = _mock_connect

        # Mock start_session to return our MockSession
        async def _mock_start_session():
            return MockSession()

        client.start_session = _mock_start_session

        yield connection

    except ImportError:
        pytest.skip("mongomock-motor not installed")


@pytest.fixture(scope="module")
def mongo_container():
    """Create a MongoDB container using testcontainers."""
    pytest.importorskip("testcontainers")

    from testcontainers.mongodb import MongoDbContainer

    with MongoDbContainer("mongo:7.0") as mongo:
        mongo.start()
        yield mongo


# Collections dropped before each integration test (event store + test data)
_REAL_MONGO_TEST_COLLECTIONS = [
    "domain_events",
    "counters",
    "test_collection",
    "test_aggregates",
    "test_dtos",
    "test_projections",
    "test_entities",
    "test_ttl_collection",
    "test_batch_projections",
    "test_projections_resume",
    "test_ttl_projections",
]


@pytest.fixture
async def real_mongo_connection(mongo_container):
    """
    Create a real MongoDB connection using testcontainers.

    This fixture provides a real MongoDB instance for integration tests
    that need real MongoDB behavior (transactions, sessions, aggregation, etc.).
    Function scope avoids "Event loop is closed" when tests run in different loops.
    Drops test collections before each test for isolation.
    """
    connection = MongoConnectionManager(url=mongo_container.get_connection_url())
    await connection.connect()
    connection._database = "test_db"

    # Drop test collections for isolation (all integration tests get clean DB)
    db = connection.client.get_database("test_db")
    for name in _REAL_MONGO_TEST_COLLECTIONS:
        try:
            await db[name].drop()
        except Exception:
            pass

    yield connection

    # Cleanup
    connection.close()


