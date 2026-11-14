"""The one registry of Registros table columns.

Each column's key, the locale path of its name, its rules and the record
families that offer it live here. The stored layout, the report answer, the
export preview and the export file read this registry; the web renders what
the answer says and keeps no copy.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, get_args

from argus.domain.business.country import COUNTRIES, business_country

Family = Literal["sale", "purchase"]
TableColumn = Literal[
    "counterparty_id",
    "counterparty",
    "date",
    "expense_type",
    "net_amount",
    "itbis_amount",
    "gross_amount",
    "stage",
    "fiscal_number",
    "note",
    "attachment",
    "payment_form",
    "funding",
]
#: What the "Lo que ves" file does with a column. `as_shown` offers it checked
#: when the table shows it. `default` offers it checked even while the table
#: hides it, and then it goes last. `always` holds it whatever the person picks.
FileRule = Literal["as_shown", "default", "always"]
#: The export file's columns: the table's, and Moneda when it holds every currency.
FileColumn = Literal[TableColumn, "currency"]
#: Moneda's name. It follows the gross amount in a file of every currency.
CURRENCY_LABEL = "business.transactions.columns.moneda"

_EVERY_FAMILY: frozenset[Family] = frozenset(get_args(Family))
_PURCHASE: frozenset[Family] = frozenset({"purchase"})


@dataclass(frozen=True)
class ColumnSpec:
    key: TableColumn
    #: Locale path of the column's name; the web and the file read its words.
    label: str
    #: Hidden in the default layout and when a stored layout first meets it.
    hidden: bool = False
    #: The record families whose table offers it.
    families: frozenset[Family] = _EVERY_FAMILY
    file: FileRule = "as_shown"


#: In the default order. The person can hide or move any of them.
COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("counterparty_id", "business.transactions.columns.rnc_cedula"),
    ColumnSpec(
        "counterparty",
        "business.transactions.columns.contraparte",
        hidden=True,
        file="always",
    ),
    ColumnSpec("date", "business.transactions.columns.fecha"),
    ColumnSpec(
        "expense_type", "business.dossier.placeholder.expense_type", families=_PURCHASE
    ),
    ColumnSpec("net_amount", "business.terms.net_amount"),
    ColumnSpec("itbis_amount", "business.terms.itbis"),
    ColumnSpec("gross_amount", "business.terms.total"),
    ColumnSpec("stage", "business.transactions.layout.column_state"),
    ColumnSpec("fiscal_number", "business.transactions.columns.ncf", hidden=True),
    ColumnSpec("note", "business.transactions.columns.notas", hidden=True),
    ColumnSpec(
        "attachment", "business.transactions.layout.column_attachment", hidden=True
    ),
    ColumnSpec(
        "payment_form",
        "business.dossier.placeholder.payment_form",
        hidden=True,
        families=_PURCHASE,
        file="default",
    ),
    ColumnSpec("funding", "business.transactions.columns.cuenta", hidden=True),
)
SPECS: dict[TableColumn, ColumnSpec] = {spec.key: spec for spec in COLUMNS}
TABLE_COLUMNS: tuple[TableColumn, ...] = tuple(SPECS)
HIDDEN_COLUMNS = tuple(spec.key for spec in COLUMNS if spec.hidden)


def offered_columns(families: Iterable[Family], country: str) -> frozenset[TableColumn]:
    """The columns a table of these families offers in a Business of this
    country. No family named means every family."""

    wanted = frozenset(families) or _EVERY_FAMILY
    omitted = business_country(country).omitted_columns
    return frozenset(
        spec.key for spec in COLUMNS if spec.families & wanted and spec.key not in omitted
    )


def offering_families(key: TableColumn) -> tuple[Family, ...]:
    """The families whose table offers this column, in `Family`'s order."""

    return tuple(family for family in get_args(Family) if family in SPECS[key].families)


def every_table_shows_one(shown: Iterable[TableColumn]) -> bool:
    """Whether each family's table, in each country, offers one of these
    columns. A layout that fails this draws some table with no column."""

    kept = frozenset(shown)
    return all(
        kept & offered_columns((family,), code)
        for family in _EVERY_FAMILY
        for code in COUNTRIES
    )
