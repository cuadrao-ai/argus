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


def decide(standing: str, auth: str, *, first_authorized: bool) -> IntakeDecision:
    if standing == "authorized" and auth != "aligned":
        return IntakeDecision(
            "bandeja", auth, UNVERIFIED_SENDER_NOTE, False, False, False
        )
    if auth != "aligned" or standing == "new":
        group = "remitentes_nuevos" if standing == "new" else None
        return IntakeDecision(group, auth, None, False, False, False)
    if standing != "authorized":
        return IntakeDecision(None, auth, None, False, False, False)
    return IntakeDecision("bandeja", auth, None, False, first_authorized, False)
