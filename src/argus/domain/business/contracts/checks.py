"""What Cuadrao checked on an electronic invoice, kept on the draft.

Each check names one fact a person can rely on, says whether it held, and
when it was read. A failed check never blocks capture or review: it is
shown for a person to resolve. Nothing here says DGII accepted the invoice.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    # The same shape as the facts contracts; defined here so the resolution
    # (facts.py) can hold a verification without importing in a circle.
    model_config = ConfigDict(extra="forbid", frozen=True)


CheckName = Literal[
    "signature_integrity",
    "totals_arithmetic",
    "read_matches_xml",
    "certificate_validity",
    "certificate_issuer",
    "dgii_accepted",
    "security_code",
    "subject_rnc",
    "qr_present",
    "qr_matches_read",
]
CheckState = Literal["verified", "failed", "not_checked"]


class EcfCheck(Contract):
    name: CheckName
    state: CheckState
    #: Why a check failed or was not checked; None for a plain verified check.
    code: str | None = Field(default=None, max_length=80)
    #: Small named facts behind the state (expected and found values, dates).
    detail: dict[str, str] = Field(default_factory=dict)


class EcfVerification(Contract):
    #: The e-NCF and document type the XML names, shown neutrally (31 crédito
    #: fiscal, 32 consumo), never a blocker.
    encf: str | None = Field(default=None, max_length=40)
    tipo_ecf: str | None = Field(default=None, max_length=8)
    checked_at: datetime
    checks: tuple[EcfCheck, ...] = Field(max_length=16)


class DgiiQr(Contract):
    """The DGII consultation link a receipt's QR carries, as typed facts. Only
    DGII's own hosts are kept; the link is for a person to open, never fetched
    by Cuadrao."""

    url: str = Field(max_length=2048)
    host: str = Field(max_length=64)
    rnc_emisor: str = Field(max_length=64)
    encf: str = Field(max_length=64)
    monto_total: str | None = Field(default=None, max_length=64)
    codigo_seguridad: str | None = Field(default=None, max_length=64)
    fecha_emision: date | None = None
    fecha_firma: str | None = Field(default=None, max_length=64)
    rnc_comprador: str | None = Field(default=None, max_length=64)
