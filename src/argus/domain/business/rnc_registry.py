from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from psycopg import Connection

Verification = Literal["verificado", "no_activo"]
DGII_RNC_LOOKUP = """
    select hit.*, case when hit.rnc is null then exists (select 1 from public.dgii_rnc)
                       else true end as loaded
    from (values (1)) as request(n) left join public.dgii_rnc_lookup(%s) as hit on true
"""


_EXCLUDED_NOTICE = (
    "La DGII puede no aceptar el ITBIS de esta factura, por eso quedó fuera del 606. "
    "Si ya lo confirmaste con el suplidor, puedes incluirla."
)


class RegistryStatus(str, Enum):
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


ACTIVE_STATUS = RegistryStatusInfo(RegistryStatus.VERIFICADO, None, None)
INACTIVE_BY_RAW: dict[str, RegistryStatusInfo] = {
    "SUSPENDIDO": RegistryStatusInfo(
        RegistryStatus.SUSPENDIDO,
        "Suplidor suspendido en la DGII",
        _EXCLUDED_NOTICE,
    ),
    "DADO DE BAJA": RegistryStatusInfo(
        RegistryStatus.DADO_DE_BAJA,
        "Suplidor dado de baja en la DGII",
        _EXCLUDED_NOTICE,
    ),
    "CESE TEMPORAL": RegistryStatusInfo(
        RegistryStatus.CESE_TEMPORAL,
        "Suplidor en cese temporal en la DGII",
        _EXCLUDED_NOTICE,
    ),
    "ANULADO": RegistryStatusInfo(
        RegistryStatus.ANULADO,
        "RNC anulado en la DGII",
        _EXCLUDED_NOTICE,
    ),
    "RECHAZADO": RegistryStatusInfo(
        RegistryStatus.RECHAZADO,
        "RNC rechazado en la DGII",
        _EXCLUDED_NOTICE,
    ),
}
UNKNOWN_STATUS = RegistryStatusInfo(
    status=RegistryStatus.DESCONOCIDO,
    label=None,
    notice=None,
)


RncRegistryStatus = RegistryStatus | Literal["not_found"]


@dataclass(frozen=True)
class RncRecord:
    rnc: str
    name: str
    trade_name: str | None
    status: str
    file_date: date | None
    verification: Verification

    @property
    def mapped(self) -> RegistryStatusInfo:
        if self.verification == "verificado":
            return ACTIVE_STATUS
        return INACTIVE_BY_RAW.get(self.status.strip().upper(), UNKNOWN_STATUS)


@dataclass(frozen=True)
class RncAnswer:
    record: RncRecord | None
    loaded: bool

    @property
    def status(self) -> RncRegistryStatus | None:
        if self.record is not None:
            return self.record.mapped.status
        return "not_found" if self.loaded else None


class RncRegistry(Protocol):
    def lookup(self, number: str) -> RncRecord | None: ...


@dataclass(frozen=True)
class RncRegistrySnapshot:
    entries: Mapping[str, RncRecord | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", MappingProxyType(dict(self.entries)))

    def lookup(self, number: str) -> RncRecord | None:
        return self.entries.get(number)


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

    @classmethod
    def for_connection(cls, connection: Connection) -> DgiiRncRegistry:
        from psycopg.rows import dict_row

        def execute(query: str, params: tuple[str]) -> Mapping[str, object] | None:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(query, params)
                return cursor.fetchone()

        return cls(postgres_rnc_fetch(execute))

    def lookup(self, number: str) -> RncRecord | None:
        return self.read(number).record

    def read(self, number: str) -> RncAnswer:
        row = self._fetch(number)
        verification = row.get("verification") if row else None
        if not row or verification not in ("verificado", "no_activo"):
            return RncAnswer(None, bool(row and row.get("loaded")))
        trade_name = row.get("trade_name")
        record = RncRecord(
            rnc=str(row.get("rnc") or number),
            name=str(row.get("name") or ""),
            trade_name=str(trade_name) if trade_name else None,
            status=str(row.get("status") or ""),
            file_date=_date(row.get("file_date")),
            verification=verification,
        )
        return RncAnswer(record, True)


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
