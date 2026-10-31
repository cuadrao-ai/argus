"""Where one inbound message lands. Pure: standing, alignment, and the cap."""

from __future__ import annotations

from dataclasses import dataclass

BOUNCE_TEXT = "Esta dirección ya no recibe recibos."
REPORT_LABEL = "Reportar dirección"
REPORT_MAILBOX = "admin@cuadrao.ai"
FIRST_SCAN_LABEL = "Prueba recibida"
UNVERIFIED_SENDER_NOTE = "No pudimos verificar este remitente."


def bounce_copy() -> str:
    return f"{BOUNCE_TEXT}\n{REPORT_LABEL}: mailto:{REPORT_MAILBOX}"


@dataclass(frozen=True)
class IntakeDecision:
    group: str | None
    auth: str
    note: str | None
    skip: bool
    first_scan: bool
    approved: bool


#: Verdicts an authorized sender's mail is read with, in Bandeja with the note.
UNVERIFIED_READABLE = frozenset({"failed", "none"})
#: Verdicts never read: the From is in doubt or the provider said nothing.
#: ``unknown`` is how both are stored until the follow-up migration.
UNVERIFIED_REFUSED = frozenset({"ambiguous", "no_result", "unknown"})


def stored_auth(verdict: str) -> str:
    """The ``auth_result`` column value for a verdict.

    The column's check (20261019040000) allows only aligned, failed and
    unknown until a follow-up migration widens it. Until then ``ambiguous``
    and ``no_result`` are stored as ``unknown`` and ``none`` as ``failed``.
    Routing decides from the verdict in memory at intake; the standing check
    at read and approve time reads the column, where ``unknown`` is refused
    and ``failed`` is readable. Both mappings keep that split.
    """

    if verdict in UNVERIFIED_REFUSED:
        return "unknown"
    if verdict == "none":
        return "failed"
    return verdict


def decide(standing: str, auth: str, *, first_authorized: bool) -> IntakeDecision:
    stored = stored_auth(auth)
    if standing == "authorized" and auth in UNVERIFIED_READABLE:
        return IntakeDecision(
            "bandeja", stored, UNVERIFIED_SENDER_NOTE, False, False, False
        )
    if standing == "authorized" and auth in UNVERIFIED_REFUSED:
        return IntakeDecision(
            "remitentes_nuevos", stored, UNVERIFIED_SENDER_NOTE, False, False, False
        )
    if auth != "aligned" or standing == "new":
        group = "remitentes_nuevos" if standing == "new" else None
        return IntakeDecision(group, stored, None, False, False, False)
    if standing != "authorized":
        return IntakeDecision(None, stored, None, False, False, False)
    return IntakeDecision("bandeja", stored, None, False, first_authorized, False)
