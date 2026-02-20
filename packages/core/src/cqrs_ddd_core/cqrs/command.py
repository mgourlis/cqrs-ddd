"""Command base class — immutable intent to change state."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Generic

from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import TypeVar

from ..correlation import get_correlation_id

if TYPE_CHECKING:
    from ..primitives.locking import ResourceIdentifier

TResult = TypeVar("TResult", default=None)


class Command(BaseModel, Generic[TResult]):
    """
    Base for all commands.

    Commands represent write operations that change system state. They:
    - Are named with imperative verbs (e.g., CreateUser, TransferFunds)
    - Return results via CommandResponse
    - Can be validated, logged, and persisted via middleware

    For commands that need pessimistic locking, override `get_critical_resources()`.

    The ``correlation_id`` is automatically inherited from the current context
    (see :func:`~cqrs_ddd_core.correlation.get_correlation_id`). If no
    correlation ID is active in the context, it defaults to ``None`` and the
    Mediator will generate one at dispatch time.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    command_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: str | None = Field(default_factory=get_correlation_id)

    def get_critical_resources(self) -> list[ResourceIdentifier]:
        """
        Declare resources that need locking for this command.

        Override this method to enable automatic resource locking via
        `ConcurrencyGuardMiddleware`. Resources are locked in sorted order
        to prevent deadlocks.

        Commands typically use write locks, but can also use read locks for
        resources that should not be modified concurrently.

        Returns:
            List of resources to lock. Empty list = no locking needed.

        Example (write locks only):
            ```python
            def get_critical_resources(self) -> list[ResourceIdentifier]:
                return [
                    ResourceIdentifier("Account", str(self.from_account)),
                    ResourceIdentifier("Account", str(self.to_account)),
                ]
            ```

        Example (mixed read/write locks):
            ```python
            def get_critical_resources(self) -> list[ResourceIdentifier]:
                return [
                    ResourceIdentifier("User", str(self.user_id), lock_mode="write"),
                    ResourceIdentifier("Settings", str(self.org_id), lock_mode="read"),
                ]
            ```
        """
        return []
