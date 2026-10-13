from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Generic, Literal, TypeVar
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
from pydantic.json_schema import SkipJsonSchema
from typing_extensions import TypeAliasType

from argus.domain.business.contracts.checks import DgiiQr, EcfVerification

T = TypeVar("T")


def _canonical_amount(value: str) -> str:
    return value.rstrip("0").rstrip(".") if "." in value else value


Amount = Annotated[
    str,
    StringConstraints(pattern=r"^(?:0|[1-9]\d*)(?:\.\d+)?$", max_length=40),
    AfterValidator(_canonical_amount),
]
Currency = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
FactOrigin = Literal[
    "extracted", "qr_decoded", "owner_stated", "member_set", "matched", "default"
]
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
    # The accountant's answer to "¿Incluir en 606?" for a personal receipt that
    # carries a fiscal number; never the app's and never the model's.
    include_606: Fact[bool] = Unknown()

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


class ReadPurchase(Contract):
    """One purchase a document read showed, kept as evidence on the draft when
    the read found more than one, or none it could settle."""

    index: int = Field(ge=1)
    amount: str | None = None
    currency: str | None = None
    occurred_on: date | None = None
    merchant: str | None = None
    kind_hint: str | None = None


class BusinessResolution(Contract):
    schema_version: Literal[1] = 1
    facts: BusinessFacts
    #: Empty for a single clean read. Several entries mean the read showed
    #: several purchases; the facts above hold only what they all share.
    read_purchases: tuple[ReadPurchase, ...] = ()
    #: The receipt total the read showed when it could not settle on one purchase.
    read_total: str | None = None
    #: What the e-CF file proved when the draft came from one; kept on later revisions.
    ecf_checks: EcfVerification | None = None
    #: The DGII QR the receipt carried, kept with the draft for the person to open.
    dgii_qr: DgiiQr | None = None
    #: A person settled the read purchases this draft does not record.
    remainder_settled: bool = False

    def unrecorded_purchases(self) -> int:
        """Read purchases this draft's amount does not account for. One read
        purchase with the draft's amount is the one this draft records; the
        count is 0 once a person settled the rest."""

        if self.remainder_settled:
            return 0
        remaining = list(self.read_purchases)
        amount = self.facts.amount
        if isinstance(amount, Known):
            recorded = _decimal(amount.value)
            for purchase in remaining:
                if recorded is not None and _decimal(purchase.amount) == recorded:
                    remaining.remove(purchase)
                    break
        return len(remaining)


def _decimal(value: str | None) -> Decimal | None:
    try:
        return None if value is None else Decimal(value)
    except InvalidOperation:
        return None


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


def _patch_json_schema(schema: dict[str, Any]) -> None:
    schema["minProperties"] = 1
    for field in schema["properties"].values():
        field.pop("default", None)


class BusinessFactPatch(Contract):
    model_config = ConfigDict(json_schema_extra=_patch_json_schema)

    kind: FactInput[ActivityKind] | SkipJsonSchema[None] = None
    amount: FactInput[Amount] | SkipJsonSchema[None] = None
    currency: FactInput[Currency] | SkipJsonSchema[None] = None
    occurred_on: FactInput[date] | SkipJsonSchema[None] = None
    counterparty: FactInput[str] | SkipJsonSchema[None] = None
    funding: FactInput[Funding] | SkipJsonSchema[None] = None
    business_share: FactInput[BusinessShare] | SkipJsonSchema[None] = None
    receipt_state: FactInput[ReceiptState] | SkipJsonSchema[None] = None
    category_id: FactInput[str] | SkipJsonSchema[None] = None

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


FiscalValue = Literal["ncf", "ecf"]


def fiscal_value(facts: BusinessFacts) -> FiscalValue | None:
    """Whether the receipt carries a fiscal number today: an NCF or an e-CF the
    draft knows, of any origin. The e-CF check state comes later."""

    if facts.fiscal is None:
        return None
    if isinstance(facts.fiscal.ecf, Known):
        return "ecf"
    if isinstance(facts.fiscal.ncf, Known):
        return "ncf"
    return None


def is_personal(facts: BusinessFacts) -> bool:
    """Marked by the owner as no part of the Business: business_share is none
    and the owner stated it. A none of any other origin (a model's reading, a
    default) is not a mark and excludes nothing."""

    share = facts.business_share
    return (
        isinstance(share, Known)
        and share.value.kind == "none"
        and share.origin == "owner_stated"
    )


def fiscal_inclusion(facts: BusinessFacts) -> bool | None:
    """The accountant's 606 answer when one applies, else None."""

    if not is_personal(facts) or fiscal_value(facts) is None or facts.fiscal is None:
        return None
    answer = facts.fiscal.include_606
    return answer.value if isinstance(answer, Known) else None
