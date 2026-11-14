"""The one registry of Registros table columns.

Each column's key, the locale path of its name, its rules and the record
families that offer it live here. The stored layout, the report answer, the
export preview and the export file read this registry; the web renders what
the answer says and keeps no copy.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from argus.domain.business.country import business_country

Family = Literal["sale", "purchase"]
TableColumn = Literal[
    "counterparty_id",
    "counterparty",
    "fiscal_number",
    "date",
    "net_amount",
    "itbis_amount",
    "gross_amount",
    "stage",
    "note",
    "attachment",
    "expense_type",
    "payment_form",
    "funding",
]
#: The export file's columns: the table's, and Moneda when it holds every currency.
FileColumn = Literal[TableColumn, "currency"]
#: Moneda's name. It follows the gross amount in a file of every currency.
CURRENCY_LABEL = "business.transactions.columns.moneda"

_EVERY_FAMILY: frozenset[Family] = frozenset({"sale", "purchase"})
_PURCHASE: frozenset[Family] = frozenset({"purchase"})


@dataclass(frozen=True)
class ColumnSpec:
    key: TableColumn
    #: Locale path of the column's name; the web and the file read its words.
    label: str
    #: Always shown: the person cannot hide it.
    required: bool = False
    #: Fixed first: the person cannot move it, and every export file holds it.
    pinned: bool = False
    #: Hidden in the default layout and when a stored layout first meets it.
    hidden: bool = False
    #: The record families whose table offers it.
    families: frozenset[Family] = _EVERY_FAMILY


COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec(
        "counterparty_id",
        "business.transactions.columns.rnc_cedula",
        pinned=True,
    ),
    ColumnSpec("counterparty", "business.transactions.columns.contraparte"),
    ColumnSpec("date", "business.transactions.columns.fecha"),
    ColumnSpec("fiscal_number", "business.transactions.columns.ncf"),
    ColumnSpec(
        "expense_type",
        "business.dossier.placeholder.expense_type",
        families=_PURCHASE,
    ),
    ColumnSpec("net_amount", "business.terms.net_amount"),
    ColumnSpec("itbis_amount", "business.terms.itbis"),
    ColumnSpec("gross_amount", "business.terms.total", required=True),
    ColumnSpec("stage", "business.transactions.layout.column_state"),
    ColumnSpec("note", "business.transactions.columns.notas"),
    ColumnSpec("attachment", "business.transactions.layout.column_attachment"),
    ColumnSpec(
        "payment_form",
        "business.dossier.placeholder.payment_form",
        hidden=True,
        families=_PURCHASE,
    ),
    ColumnSpec("funding", "business.transactions.columns.cuenta", hidden=True),
)
SPECS: dict[TableColumn, ColumnSpec] = {spec.key: spec for spec in COLUMNS}
TABLE_COLUMNS: tuple[TableColumn, ...] = tuple(SPECS)
HIDDEN_COLUMNS = tuple(spec.key for spec in COLUMNS if spec.hidden)
REQUIRED_COLUMNS = frozenset(spec.key for spec in COLUMNS if spec.required)
PINNED_COLUMNS = tuple(spec.key for spec in COLUMNS if spec.pinned)


def offered_columns(families: Iterable[Family], country: str) -> frozenset[TableColumn]:
    """The columns a table of these families offers in a Business of this
    country. No family named means every family."""

    wanted = frozenset(families) or _EVERY_FAMILY
    omitted = business_country(country).omitted_columns
    return frozenset(
        spec.key for spec in COLUMNS if spec.families & wanted and spec.key not in omitted
    )
