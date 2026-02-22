"""Session helpers for MongoDB (Motor vs mock compatibility)."""

from __future__ import annotations

from typing import Any


def session_in_transaction(session: Any) -> bool:
    """Return whether the session is in an active transaction.

    Motor's ClientSession uses ``in_transaction`` as a property; mocks may use a method.
    """
    in_txn = getattr(session, "in_transaction", False)
    return in_txn() if callable(in_txn) else bool(in_txn)
