import pytest

from cqrs_ddd_core.cqrs.command import Command
from cqrs_ddd_core.cqrs.query import Query

# --- Test Models ---


class CreateUser(Command):
    username: str


class GetUser(Query):
    user_id: str


# --- Tests ---


def test_command_immutability() -> None:
    """Verifies that commands are immutable."""
    cmd = CreateUser(username="alice")
    assert cmd.username == "alice"
    with pytest.raises(Exception, match="is immutable|cannot set attribute|frozen"):
        cmd.username = "bob"


def test_query_immutability() -> None:
    """Verifies that queries are immutable."""
    qry = GetUser(user_id="user-123")
    assert qry.user_id == "user-123"
    with pytest.raises(Exception, match="is immutable|cannot set attribute|frozen"):
        qry.user_id = "user-456"


def test_command_serialization() -> None:
    """Verifies that commands can be serialized."""
    cmd = CreateUser(username="alice")
    data = cmd.model_dump()
    assert data["username"] == "alice"
