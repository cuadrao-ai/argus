"""Who may land in Bandeja when pending senders are on.

A sender with an ``authorized`` row lands, whatever the verdict (the routing
rules then say where and with which note). Any other sender's mail is not
stored: its row is recorded as ``pending`` and the delivery ends rejected
``email_sender_pending``. Blocked senders never get here."""

from __future__ import annotations

from typing import Protocol

from argus.domain.ingestion.email_intake.standing import SENDER_PENDING

PENDING_CODE = SENDER_PENDING


class SenderRows(Protocol):
    def sender_standing(self, space_id: str, address: str | None) -> str: ...

    def record_sender(self, space_id: str, address: str | None, verdict: str) -> None: ...


def admitted(store: SenderRows, space_id: str, sender: str | None, verdict: str) -> bool:
    """Record the sender's row and say whether its mail may be stored."""

    store.record_sender(space_id, sender, verdict)
    return store.sender_standing(space_id, sender) == "authorized"


def tag(last_auth_result: str | None) -> str | None:
    """``verified`` for an aligned last verdict, ``unverified`` for any other,
    null when no mail from the sender was seen since the column existed."""

    if last_auth_result is None:
        return None
    return "verified" if last_auth_result == "aligned" else "unverified"
