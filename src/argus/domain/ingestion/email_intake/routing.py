"""Where one inbound message lands. Pure: standing, alignment, and the cap."""

from __future__ import annotations

from dataclasses import dataclass

BOUNCE_TEXT = "Esta dirección ya no recibe recibos."
REPORT_LABEL = "Reportar dirección"
REPORT_MAILBOX = "admin@cuadrao.ai"
UNVERIFIED_NOTE = "No pudimos verificar este remitente."
FIRST_SCAN_LABEL = "Prueba recibida"


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


def decide(standing: str, auth: str, *, first_authorized: bool) -> IntakeDecision:
    """Authorized mail with a failed or unknown check stays in the tray as pending.

    The skip flag stays false. Nothing from email is approved here.
    """

    if standing == "new":
        return IntakeDecision("remitentes_nuevos", auth, None, False, False, False)
    if standing != "authorized":
        return IntakeDecision(None, auth, None, False, False, False)
    note = None if auth == "aligned" else UNVERIFIED_NOTE
    return IntakeDecision("bandeja", auth, note, False, first_authorized, False)
