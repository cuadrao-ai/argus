"""Who may land in Bandeja when pending senders are on.

A sender with an ``authorized`` row lands, whatever the verdict (the routing
rules then say where and with which note). Any other sender's mail is not
stored: its row is recorded as ``pending`` and the delivery ends rejected
``email_sender_pending``. Blocked senders never get here.

The Business's own people (owner and team, by their account address) are
approved by default: their first message writes an ``authorized`` row,
unless a row for that address already exists."""

from __future__ import annotations

from typing import Protocol

from argus.domain.ingestion.email_intake.alignment import bare_address
from argus.domain.ingestion.email_intake.standing import SENDER_PENDING

PENDING_CODE = SENDER_PENDING


#: The one switch for the owner/team default. False (shipped, Lucas Oct 31):
#: their address alone approves them, whatever the verdict. True: only an
#: aligned message approves them; failed, none, ambiguous and no_result stay
#: pending (Sin verificar). The tag on the row is shown either way.
DEFAULT_APPROVAL_REQUIRES_ALIGNED = False


def default_approves(is_member: bool, verdict: str) -> bool:
    """Whether this message approves its sender as one of the Business's people."""

    return is_member and (verdict == "aligned" or not DEFAULT_APPROVAL_REQUIRES_ALIGNED)


class SenderRows(Protocol):
    def sender_standing(self, space_id: str, address: str | None) -> str: ...

    def member_addresses(self, space_id: str) -> frozenset[str]: ...

    def add_default_sender(self, space_id: str, address: str | None) -> None: ...

    def record_sender(self, space_id: str, address: str | None, verdict: str) -> None: ...


def admitted(store: SenderRows, space_id: str, sender: str | None, verdict: str) -> bool:
    """Record the sender's row and say whether its mail may be stored."""

    if store.sender_standing(space_id, sender) == "new" and default_approves(
        _member(store, space_id, sender), verdict
    ):
        store.add_default_sender(space_id, sender)
    store.record_sender(space_id, sender, verdict)
    return store.sender_standing(space_id, sender) == "authorized"


def _member(store: SenderRows, space_id: str, sender: str | None) -> bool:
    address = bare_address(sender)
    return bool(address) and address.lower() in store.member_addresses(space_id)


def tag(last_auth_result: str | None) -> str | None:
    """``verified`` for an aligned last verdict, ``unverified`` for any other,
    null when no mail from the sender was seen since the column existed."""

    if last_auth_result is None:
        return None
    return "verified" if last_auth_result == "aligned" else "unverified"
