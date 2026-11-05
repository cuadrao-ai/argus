"""Supplier registry lookup and receipt-date NCF check.

The service runs only when ``CUADRAO_BUSINESS_SUPPLIER_FAST_PATH_ENABLED``
is on. Callers pass a database connection. Nothing here opens one, and
nothing here is wired to a route.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Literal

from argus.domain.ingestion.documents.config import enabled_flag
from argus.domain.ingestion.documents.dgii_qr import tipo_ecf_of
from argus.settings_names import setting_value

_FLAG = "BUSINESS_SUPPLIER_FAST_PATH_ENABLED"
_EXCLUDED_NOTICE = (
    "La DGII puede no aceptar el ITBIS de esta factura, por eso quedó fuera del 606. "
    "Si ya lo confirmaste con el suplidor, puedes incluirla."
)
_INVALID_NCF = "Este comprobante no es válido. Pide al suplidor uno nuevo."
_NO_DUE_DATE = "Sin fecha de vencimiento"
_B_SERIES = re.compile(r"^B(?:0[1-4]|1[1-5]|17)\d{8}$", re.IGNORECASE)


class RegistryStatus(str, Enum):
    """Publisher status after the app mapping. Not the SQL verification column."""

    VERIFICADO = "verificado"
    SUSPENDIDO = "suspendido"
    DADO_DE_BAJA = "dado_de_baja"
    CESE_TEMPORAL = "cese_temporal"
    ANULADO = "anulado"
    RECHAZADO = "rechazado"
    DESCONOCIDO = "desconocido"


@dataclass(frozen=True)
class RegistryStatusInfo:
    status: RegistryStatus
    label: str | None
    notice: str | None


def _known(
    status: RegistryStatus,
    label: str | None,
    *,
    excluded: bool,
) -> RegistryStatusInfo:
    return RegistryStatusInfo(
        status=status,
        label=label,
        notice=_EXCLUDED_NOTICE if excluded else None,
    )


STATUS_BY_RAW: dict[str, RegistryStatusInfo] = {
    "ACTIVO": _known(RegistryStatus.VERIFICADO, None, excluded=False),
    "SUSPENDIDO": _known(
        RegistryStatus.SUSPENDIDO,
        "Suplidor suspendido en la DGII",
        excluded=True,
    ),
    "DADO DE BAJA": _known(
        RegistryStatus.DADO_DE_BAJA,
        "Suplidor dado de baja en la DGII",
        excluded=True,
    ),
    "CESE TEMPORAL": _known(
        RegistryStatus.CESE_TEMPORAL,
        "Suplidor en cese temporal en la DGII",
        excluded=True,
    ),
    "ANULADO": _known(
        RegistryStatus.ANULADO,
        "RNC anulado en la DGII",
        excluded=True,
    ),
    "RECHAZADO": _known(
        RegistryStatus.RECHAZADO,
        "RNC rechazado en la DGII",
        excluded=True,
    ),
}
UNKNOWN_STATUS = RegistryStatusInfo(
    status=RegistryStatus.DESCONOCIDO,
    label=None,
    notice=None,
)


def supplier_fast_path_enabled() -> bool:
    return enabled_flag(setting_value(_FLAG))


def map_registry_status(raw_status: str) -> RegistryStatusInfo:
    """Map trimmed, case-insensitive publisher text. Anything else is desconocido."""

    return STATUS_BY_RAW.get(str(raw_status).strip().upper(), UNKNOWN_STATUS)


@dataclass(frozen=True)
class NcfOnIssueDate:
    valid: bool
    note: str | None


def _as_date(value: date) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def ncf_valid_on_issue_date(
    ncf: str,
    issue_date: date,
    vencimiento: date | None = None,
) -> NcfOnIssueDate:
    """Whether the NCF was valid on the receipt's issue date.

    A B-series number with a printed due date is invalid only when the issue
    date is after that date. e-CF has no due date. This function does not
    read today's date.
    """

    issued = _as_date(issue_date)
    due = None if vencimiento is None else _as_date(vencimiento)
    text = (ncf or "").strip()
    if tipo_ecf_of(text) is not None:
        return NcfOnIssueDate(valid=True, note=_NO_DUE_DATE)
    if _B_SERIES.match(text) is None:
        return NcfOnIssueDate(valid=False, note=_INVALID_NCF)
    if due is None:
        return NcfOnIssueDate(valid=True, note=_NO_DUE_DATE)
    if issued > due:
        return NcfOnIssueDate(valid=False, note=_INVALID_NCF)
    return NcfOnIssueDate(valid=True, note=None)


@dataclass(frozen=True)
class SupplierRegistryHit:
    outcome: Literal["found"]
    rnc: str
    name: str
    raw_status: str
    mapped: RegistryStatusInfo
    file_date: date
    checked_at: datetime


@dataclass(frozen=True)
class SupplierRegistryMiss:
    outcome: Literal["not_found", "not_loaded"]
    rnc: str
    checked_at: datetime


@dataclass(frozen=True)
class SupplierFastPath:
    registry: SupplierRegistryHit | SupplierRegistryMiss
    ncf: NcfOnIssueDate


@dataclass(frozen=True)
class SupplierFastPathDisabled:
    outcome: Literal["disabled"] = "disabled"


def _lookup(
    connection: Any,
    rnc: str,
    checked_at: datetime,
) -> SupplierRegistryHit | SupplierRegistryMiss:
    with connection.cursor() as cursor:
        cursor.execute(
            "select rnc, name, status, file_date from public.dgii_rnc_lookup(%s)",
            (rnc,),
        )
        row = cursor.fetchone()
        if row is None:
            # No row covers two facts the function does not separate: the
            # registry table is empty, or this RNC is absent from a loaded file.
            cursor.execute("select exists (select 1 from public.dgii_rnc)")
            loaded = cursor.fetchone()
            outcome: Literal["not_found", "not_loaded"] = (
                "not_found" if loaded and loaded[0] else "not_loaded"
            )
            return SupplierRegistryMiss(
                outcome=outcome,
                rnc=rnc,
                checked_at=checked_at,
            )
    registry_rnc, name, raw_status, file_date = row
    raw_text = raw_status if isinstance(raw_status, str) else str(raw_status)
    return SupplierRegistryHit(
        outcome="found",
        rnc=str(registry_rnc),
        name=str(name),
        raw_status=raw_text,
        mapped=map_registry_status(raw_text),
        file_date=_as_date(file_date),
        checked_at=checked_at,
    )


def lookup_supplier_fast_path(
    connection: Any,
    *,
    rnc: str,
    ncf: str,
    issue_date: date,
    vencimiento: date | None,
    checked_at: datetime,
) -> SupplierFastPath | SupplierFastPathDisabled:
    if not supplier_fast_path_enabled():
        return SupplierFastPathDisabled()
    return SupplierFastPath(
        registry=_lookup(connection, rnc, checked_at),
        ncf=ncf_valid_on_issue_date(ncf, issue_date, vencimiento),
    )
