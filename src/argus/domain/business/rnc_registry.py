from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Literal, Protocol

Verification = Literal["verificado", "no_activo"]
DGII_RNC_LOOKUP = "select * from public.dgii_rnc_lookup(%s)"


@dataclass(frozen=True)
class RncRecord:
    rnc: str
    name: str
    trade_name: str | None
    status: str
    file_date: date | None
    verification: Verification


class RncRegistry(Protocol):
    def lookup(self, number: str) -> RncRecord | None: ...


class UnknownRncRegistry:
    """Nothing is on file. Every lookup is sin_verificar."""

    def lookup(self, number: str) -> None:
        return None


def _date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        return date.fromisoformat(value[:10])
    return None


class DgiiRncRegistry:
    """Reads public.dgii_rnc_lookup. The caller supplies the query."""

    def __init__(self, fetch: Callable[[str], Mapping[str, object] | None]):
        self._fetch = fetch

    def lookup(self, number: str) -> RncRecord | None:
        row = self._fetch(number)
        if not row:
            return None
        verification = row.get("verification")
        if verification not in ("verificado", "no_activo"):
            return None
        trade_name = row.get("trade_name")
        return RncRecord(
            rnc=str(row.get("rnc") or number),
            name=str(row.get("name") or ""),
            trade_name=str(trade_name) if trade_name else None,
            status=str(row.get("status") or ""),
            file_date=_date(row.get("file_date")),
            verification=verification,
        )


def postgres_rnc_fetch(execute: Callable[..., Mapping[str, object] | None]):
    def fetch(number: str) -> Mapping[str, object] | None:
        return execute(DGII_RNC_LOOKUP, (number,))

    return fetch


def registry_from_config(
    mode: str, fetch: Callable[[str], Mapping[str, object] | None] | None = None
) -> RncRegistry:
    if mode == "dgii":
        if fetch is None:
            raise ValueError("dgii rnc registry requires a lookup")
        return DgiiRncRegistry(fetch)
    return UnknownRncRegistry()
