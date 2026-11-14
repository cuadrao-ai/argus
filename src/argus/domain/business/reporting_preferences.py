"""Version two preserves table setup separately from exported field selection."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from argus.domain.business.contracts.dgii import ExpenseType
from argus.domain.business.reporting_columns import (
    HIDDEN_COLUMNS,
    TABLE_COLUMNS,
    Family,
    TableColumn,
)
from argus.domain.recording.currency import normalize_currency, parse_minor_units
from argus.domain.recording.errors import RecordingInputError

#: A recorded row's place on the way to the DGII. Registros lists approved
#: records only; a draft waits in the Bandeja and is no stage here.
Stage = Literal["needs_review", "needs_fiscal_data", "ready_for_export", "exported"]
FiscalData = Literal["complete", "missing"]
DocumentKind = Literal["invoice", "receipt", "credit_note", "unknown"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Period(Contract):
    kind: Literal[
        "all", "custom", "this_month", "last_month", "this_year", "latest_month"
    ] = "all"
    from_date: date | None = None
    to_date: date | None = None

    @model_validator(mode="after")
    def bounds(self) -> Period:
        if self.kind == "custom":
            if (
                self.from_date is None
                or self.to_date is None
                or self.from_date > self.to_date
            ):
                raise ValueError("custom period requires ordered inclusive dates")
        elif self.from_date is not None or self.to_date is not None:
            raise ValueError("only custom periods accept dates")
        return self


class ReportFilters(Contract):
    q: str = Field(default="", max_length=200)
    period: Period = Period()
    record_families: tuple[Family, ...] = ()
    review_stages: tuple[Stage, ...] = ()
    fiscal_data: FiscalData | None = None
    has_document: bool | None = None
    currencies: tuple[str, ...] = Field(default=(), max_length=200)
    amount_min: str | None = None
    amount_max: str | None = None
    counterparties: tuple[str, ...] = Field(default=(), max_length=200)
    categories: tuple[str, ...] = Field(default=(), max_length=200)
    #: 606 tipo de gasto codes, or `missing` for a purchase that still needs one.
    expense_types: tuple[ExpenseType | Literal["missing"], ...] = ()
    funding_sources: tuple[str, ...] = Field(default=(), max_length=200)
    document_kinds: tuple[DocumentKind, ...] = ()
    fiscal_classifications: tuple[str, ...] = Field(default=(), max_length=100)

    @field_validator("review_stages", mode="before")
    @classmethod
    def drop_removed_stage(cls, value: Any) -> Any:
        """Registros no longer lists open drafts, so a saved view or an old tab
        that still names `awaiting_approval` keeps its other stages."""

        if isinstance(value, (list, tuple)):
            return [stage for stage in value if stage != "awaiting_approval"]
        return value

    @model_validator(mode="after")
    def amounts(self) -> ReportFilters:
        try:
            for currency in self.currencies:
                if normalize_currency(currency) != currency:
                    raise ValueError("currency must use its canonical code")
            if self.amount_min is not None or self.amount_max is not None:
                if len(set(self.currencies)) != 1:
                    raise ValueError("amount range requires one currency")
                values = [
                    parse_minor_units(value, self.currencies[0])
                    if value is not None
                    else None
                    for value in (self.amount_min, self.amount_max)
                ]
                if any(value is not None and value < 0 for value in values):
                    raise ValueError("amount range uses gross magnitude")
                if all(value is not None for value in values) and values[0] > values[1]:
                    raise ValueError("amount range must be ordered")
        except RecordingInputError as error:
            raise ValueError(error.code) from None
        for values in (
            self.counterparties,
            self.categories,
            self.funding_sources,
            self.fiscal_classifications,
        ):
            if any(not value or len(value) > 128 for value in values):
                raise ValueError("invalid filter key")
        return self


class ReportRecipe(Contract):
    schema_version: Literal[1] = 1
    filters: ReportFilters = ReportFilters()
    sort: Literal["date_desc"] = "date_desc"

    @model_validator(mode="before")
    @classmethod
    def drop_unread_columns(cls, value: Any) -> Any:
        """Saved views and old tabs still carry the first table's `columns`
        list. Nothing reads it, so it is dropped on the way in."""

        if isinstance(value, dict) and "columns" in value:
            return {key: item for key, item in value.items() if key != "columns"}
        return value


class ReportRequest(ReportRecipe):
    page: int = Field(default=1, ge=1, strict=True)
    page_size: Literal[25, 50, 100] = 25


Sort = Literal[
    "date_desc", "date_asc", "name_asc", "name_desc", "amount_asc", "amount_desc"
]


def _current_columns(value: Any) -> Any:
    """Upgrade a stored or linked layout to today's columns. A column the
    layout does not name joins it at the end, hidden.
    Tipo de gasto, Forma de pago and the net amount keep their shipped places."""

    if not isinstance(value, dict) or not isinstance(value.get("order"), list):
        return value
    order = [
        "expense_type" if key == "category" else key
        for key in value["order"]
        if key not in ("family", "currency")
    ]
    hidden = [
        "expense_type" if key == "category" else key
        for key in value.get("hidden", list(HIDDEN_COLUMNS))
        if key not in ("family", "currency")
    ]
    if "payment_form" not in order and "expense_type" in order:
        order.insert(order.index("expense_type") + 1, "payment_form")
        if "payment_form" not in hidden:
            hidden.append("payment_form")
    if "net_amount" not in order:
        index = order.index("gross_amount") if "gross_amount" in order else len(order)
        order.insert(index, "net_amount")
    for key in TABLE_COLUMNS:
        if key not in order:
            order.append(key)
            if key not in hidden:
                hidden.append(key)
    return {**value, "order": order, "hidden": hidden}


class Presentation(Contract):
    order: tuple[TableColumn, ...] = Field(default_factory=lambda: TABLE_COLUMNS)
    hidden: tuple[TableColumn, ...] = Field(default_factory=lambda: HIDDEN_COLUMNS)
    density: Literal[40, 48, 56] = 48

    @model_validator(mode="before")
    @classmethod
    def legacy_columns(cls, value: Any) -> Any:
        return _current_columns(value)

    @model_validator(mode="after")
    def canonical_columns(self) -> Presentation:
        if len(self.order) != len(TABLE_COLUMNS) or set(self.order) != set(TABLE_COLUMNS):
            raise ValueError("all table columns occur once")
        if len(set(self.hidden)) != len(self.hidden) or len(self.hidden) >= len(
            self.order
        ):
            raise ValueError("hidden columns are unique; one column stays shown")
        return self


class ReportFiltersV2(ReportFilters):
    @model_validator(mode="after")
    def input_precision(self) -> ReportFiltersV2:
        for value in (self.amount_min, self.amount_max):
            if (
                value is not None
                and len(value.strip().partition(".")[0].lstrip("0")) > 15
            ):
                raise ValueError(
                    "amount input permits at most 15 significant whole digits"
                )
        return self


class ReportRecipeV2(ReportRecipe):
    schema_version: Literal[2] = 2
    filters: ReportFiltersV2 = ReportFiltersV2()
    sort: Sort = "date_desc"
    presentation: Presentation = Field(default_factory=Presentation)
    page_size: Literal[25, 50, 100] = 25


class ReportRequestV2(ReportRecipeV2):
    page: int = Field(default=1, ge=1, strict=True)


def legacy_version(value: Any) -> Any:
    if isinstance(value, dict) and "schema_version" not in value:
        return {"schema_version": 1, **value}
    return value


RecipeInput = Annotated[
    ReportRecipe | ReportRecipeV2,
    Field(discriminator="schema_version"),
    BeforeValidator(legacy_version),
]
ReportInput = Annotated[
    ReportRequest | ReportRequestV2,
    Field(discriminator="schema_version"),
    BeforeValidator(legacy_version),
]
