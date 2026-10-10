from __future__ import annotations

from datetime import date
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    StringConstraints,
    model_serializer,
    model_validator,
)
from typing_extensions import TypeAliasType

T = TypeVar("T")


def _canonical_amount(value: str) -> str:
    return value.rstrip("0").rstrip(".") if "." in value else value


Amount = Annotated[
    str,
    StringConstraints(pattern=r"^(?:0|[1-9]\d*)(?:\.\d+)?$", max_length=40),
    AfterValidator(_canonical_amount),
]
Currency = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
FactOrigin = Literal["extracted", "owner_stated", "member_set", "matched", "default"]
ActivityKind = Literal[
    "expense",
    "income",
    "transfer",
    "refund",
    "owner_contribution",
    "owner_withdrawal",
    "credit_purchase",
    "payable_payment",
    "loan_received",
    "loan_payment",
]
FactField = Literal[
    "kind",
    "amount",
    "currency",
    "occurred_on",
    "counterparty",
    "funding",
    "business_share",
    "receipt_state",
    "category_id",
]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Known(Contract, Generic[T]):
    state: Literal["known"] = "known"
    value: T
    origin: FactOrigin
    verified: bool = False
    source_ids: tuple[UUID, ...]

    @model_validator(mode="after")
    def provenance(self) -> Known[T]:
        if self.origin == "default":
            if self.verified or self.source_ids:
                raise ValueError("default facts are unverified and have no source")
        elif not self.source_ids:
            raise ValueError("known facts require a source")
        return self


class Unknown(Contract):
    state: Literal["unknown"] = "unknown"
    value: None = None
    origin: Literal["extracted", "owner_stated", "member_set", "matched"] | None = None
    verified: Literal[False] = False
    source_ids: tuple[UUID, ...] = ()


class OwnerDoesNotKnow(Contract):
    state: Literal["owner_does_not_know"] = "owner_does_not_know"
    value: None = None
    origin: Literal["owner_stated", "member_set"]
    verified: Literal[False] = False
    source_ids: tuple[UUID, ...] = Field(min_length=1)


Fact = TypeAliasType(
    "Fact",
    Annotated[Known[T] | Unknown | OwnerDoesNotKnow, Field(discriminator="state")],
    type_params=(T,),
)


class BusinessAccountFunding(Contract):
    kind: Literal["business_account"] = "business_account"
    account_id: UUID


class OwnerFunding(Contract):
    kind: Literal["owner_funds"] = "owner_funds"


Funding = Annotated[BusinessAccountFunding | OwnerFunding, Field(discriminator="kind")]


class WholeBusinessShare(Contract):
    kind: Literal["all", "none"]


class PartialBusinessShare(Contract):
    kind: Literal["partial"] = "partial"
    amount: Amount


BusinessShare = Annotated[
    WholeBusinessShare | PartialBusinessShare, Field(discriminator="kind")
]
ReceiptState = Literal["fiscal_receipt", "informal_receipt", "no_receipt"]


class FiscalFacts(Contract):
    rnc: Fact[str] = Unknown()
    ncf: Fact[str] = Unknown()
    ecf: Fact[str] = Unknown()
    itbis: Fact[Amount] = Unknown()

    @model_validator(mode="after")
    def no_fiscal_defaults(self) -> FiscalFacts:
        for name in type(self).model_fields:
            fact = getattr(self, name)
            if fact.origin == "default":
                raise ValueError("fiscal facts cannot default")
        return self


class BusinessFacts(Contract):
    kind: Fact[ActivityKind] = Unknown()
    amount: Fact[Amount] = Unknown()
    currency: Fact[Currency] = Unknown()
    occurred_on: Fact[date] = Unknown()
    counterparty: Fact[str] = Unknown()
    funding: Fact[Funding] = Unknown()
    business_share: Fact[BusinessShare] = Unknown()
    receipt_state: Fact[ReceiptState] = Unknown()
    category_id: Fact[str] = Unknown()
    fiscal: FiscalFacts | None = None

    @model_validator(mode="after")
    def currency_only_default(self) -> BusinessFacts:
        for name in type(self).model_fields:
            if name == "fiscal":
                continue
            fact = getattr(self, name)
            if fact.origin == "default" and (name != "currency" or fact.value != "DOP"):
                raise ValueError("only DOP currency may default")
        return self


class BusinessResolution(Contract):
    schema_version: Literal[1] = 1
    facts: BusinessFacts


class KnownInput(Contract, Generic[T]):
    state: Literal["known"] = "known"
    value: T


class UncertainInput(Contract):
    state: Literal["unknown", "owner_does_not_know"]
    value: None = None


FactInput = TypeAliasType(
    "FactInput",
    Annotated[KnownInput[T] | UncertainInput, Field(discriminator="state")],
    type_params=(T,),
)


class BusinessFactPatch(Contract):
    kind: FactInput[ActivityKind] | None = None
    amount: FactInput[Amount] | None = None
    currency: FactInput[Currency] | None = None
    occurred_on: FactInput[date] | None = None
    counterparty: FactInput[str] | None = None
    funding: FactInput[Funding] | None = None
    business_share: FactInput[BusinessShare] | None = None
    receipt_state: FactInput[ReceiptState] | None = None
    category_id: FactInput[str] | None = None

    @model_serializer(mode="wrap")
    def serialize_patch(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, object]:
        return {name: value for name, value in handler(self).items() if value is not None}

    @model_validator(mode="after")
    def explicit_fact_states(self) -> BusinessFactPatch:
        if not self.model_fields_set:
            raise ValueError("supply at least one fact")
        if any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("use an explicit unknown state instead of null")
        return self


def legacy_projection(facts: BusinessFacts) -> dict[str, object]:
    names = {
        "kind": "kind",
        "amount": "amount",
        "currency": "currency",
        "occurred_on": "occurred_on",
        "counterparty": "note",
        "category_id": "category_id",
    }
    values = facts.model_dump(mode="json")
    projected = {target: values[source]["value"] for source, target in names.items()}
    projected["direction"] = {"expense": "outflow", "income": "inflow"}.get(
        values["kind"]["value"]
    )
    funding = facts.funding
    projected["account_id"] = (
        str(funding.value.account_id)
        if isinstance(funding, Known)
        and isinstance(funding.value, BusinessAccountFunding)
        else None
    )
    return projected
