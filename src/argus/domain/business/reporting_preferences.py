"""Version two preserves table setup separately from exported field selection."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BeforeValidator, Field, model_validator

from argus.domain.business.reporting_query import (
    Contract,
    ReportFilters,
    ReportRecipe,
    ReportRequest,
)

TableColumn = Literal[
    "counterparty",
    "date",
    "gross_amount",
    "currency",
    "family",
    "category",
    "stage",
    "note",
    "attachment",
    "funding",
]
TABLE_COLUMNS: tuple[TableColumn, ...] = (
    "counterparty",
    "date",
    "gross_amount",
    "currency",
    "family",
    "category",
    "stage",
    "note",
    "attachment",
    "funding",
)
Sort = Literal[
    "date_desc", "date_asc", "name_asc", "name_desc", "amount_asc", "amount_desc"
]


class Presentation(Contract):
    order: tuple[TableColumn, ...] = TABLE_COLUMNS
    hidden: tuple[TableColumn, ...] = ("funding",)
    density: Literal[40, 48, 56] = 48

    @model_validator(mode="after")
    def canonical_columns(self) -> Presentation:
        if (
            len(self.order) != len(TABLE_COLUMNS)
            or set(self.order) != set(TABLE_COLUMNS)
            or self.order[0] != "counterparty"
        ):
            raise ValueError("all table columns occur once; counterparty is pinned first")
        if len(set(self.hidden)) != len(self.hidden) or set(self.hidden) & {
            "counterparty",
            "gross_amount",
            "currency",
        }:
            raise ValueError(
                "required columns cannot be hidden; hidden columns are unique"
            )
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
    presentation: Presentation = Presentation()
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
