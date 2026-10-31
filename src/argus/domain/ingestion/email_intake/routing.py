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
#: Verdicts never read: the From is in doubt. ``unknown`` is how older rows
#: stored both an ambiguous From and a missing result, so it stays refused.
UNVERIFIED_REFUSED = frozenset({"ambiguous", "unknown"})
#: The provider gave no check result. An authorized sender's mail is read as
#: usual, in Bandeja with no note (Lucas, Oct 31).
NO_RESULT = "no_result"


def verdict_readable(auth_result, inbox_group, review_note) -> bool:  # noqa: ANN001
    """Whether a stored delivery may be read or approved by its verdict alone.

    ``aligned`` may, and so may ``no_result`` in Bandeja with no note: an
    authorized sender's mail the provider gave no check result for. ``failed`` may only as Pendiente: Bandeja with the
    unverified note, the one row a person sees the warning on. A failed row
    held in Remitentes nuevos (sender authorized later, a retry after the
    sender was removed, or a row from before the note) stays refused, as does
    every other value and NULL.
    """

    if auth_result == "aligned":
        return True
    if auth_result == NO_RESULT:
        return inbox_group == "bandeja" and review_note is None
    return (
        auth_result == "failed"
        and inbox_group == "bandeja"
        and review_note == UNVERIFIED_SENDER_NOTE
    )


def stored_auth(verdict: str) -> str:
    """The ``auth_result`` column value for a verdict.

    ``no_result`` is stored as itself (the column allows it since
    20261031020000), so the read gate can tell it from an ambiguous From.
    ``ambiguous`` is still stored as ``unknown`` and ``none`` as ``failed``:
    the standing check at read and approve time reads the column, where
    ``unknown`` is refused and ``failed`` is readable only as Pendiente.
    """

    if verdict == NO_RESULT:
        return verdict
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
    if standing == "authorized" and auth == NO_RESULT:
        return IntakeDecision("bandeja", stored, None, False, False, False)
    if auth != "aligned" or standing == "new":
        group = "remitentes_nuevos" if standing == "new" else None
        return IntakeDecision(group, stored, None, False, False, False)
    if standing != "authorized":
        return IntakeDecision(None, stored, None, False, False, False)
    return IntakeDecision("bandeja", stored, None, False, first_authorized, False)
