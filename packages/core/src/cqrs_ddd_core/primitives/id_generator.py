import uuid
from typing import Protocol


class IIDGenerator(Protocol):
    """
    Protocol for ID generation strategies.
    Useful for ensuring compatibility with different ID formats
    (UUIDv4, UUIDv7, Snowflake).
    """

    def next_id(self) -> object:
        """Generates the next unique identifier."""
        ...


class UUID4Generator(IIDGenerator):
    """
    Default fallback ID generator using UUIDv4.
    Zero external dependencies.
    """

    def next_id(self) -> str:
        """Returns a string representation of a random UUIDv4."""
        return str(uuid.uuid4())
