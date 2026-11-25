"""Supplier registry lookup and receipt-date NCF check.

The service runs only when ``CUADRAO_BUSINESS_SUPPLIER_FAST_PATH_ENABLED``
is on. Callers pass a database connection and the time of the check.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

from argus.domain.business.fiscal_identity import normalized_ncf
from argus.domain.business.rnc_registry import DgiiRncRegistry, RegistryStatusInfo
from argus.settings_names import setting_value

_FLAG = "BUSINESS_SUPPLIER_FAST_PATH_ENABLED"
_INVALID_NCF = "Este comprobante no es válido. Pide al suplidor uno nuevo."
_NO_DUE_DATE = "Sin fecha de vencimiento"
_B_TYPES = frozenset({"01", "02", "03", "04", "11", "12", "13", "14", "15", "17"})


def supplier_fast_path_enabled() -> bool:
    from argus.domain.ingestion.documents.config import enabled_flag

    return enabled_flag(setting_value(_FLAG))


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
    text = normalized_ncf(ncf)
    if text is None:
        return NcfOnIssueDate(valid=False, note=_INVALID_NCF)
    if text.startswith("E"):
        return NcfOnIssueDate(valid=True, note=_NO_DUE_DATE)
    if text[1:3] not in _B_TYPES:
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
    file_date: date | None
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
    answer = DgiiRncRegistry.for_connection(connection).read(rnc)
    record = answer.record
    if record is None:
        return SupplierRegistryMiss(
            outcome="not_found" if answer.loaded else "not_loaded",
            rnc=rnc,
            checked_at=checked_at,
        )
    return SupplierRegistryHit(
        outcome="found",
        rnc=record.rnc,
        name=record.name,
        raw_status=record.status,
        mapped=record.mapped,
        file_date=record.file_date,
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
