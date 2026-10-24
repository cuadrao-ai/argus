from __future__ import annotations

import hashlib
import json
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Processing = Literal[
    "unreported", "REGISTERED", "TO_SEND", "WAITING_RESPONSE", "TO_NOTIFY", "FINISHED"
]
Legal = Literal["unreported", "ACCEPTED", "ACCEPTED_WITH_OBSERVATIONS", "REJECTED"]
ArtifactState = Literal["unreported", "available", "unavailable", "retrieval_failed"]


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FiscalPrepare(Strict):
    case_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")


class FiscalSubmit(Strict):
    payload_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class Case(Strict):
    case_id: str
    document_key: str
    business_id: UUID
    account_key: str
    company_id: str
    issuer: str = Field(pattern=r"^\d{9,11}$")
    kind: Literal["E31", "E32"]
    number: str = Field(pattern=r"^E3[12]\d{10}$")
    fixture_revision: str
    fixture_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    payload_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    payload: dict[str, Any]

    @model_validator(mode="after")
    def pinned(self) -> Case:
        if (
            not self.number.startswith(self.kind)
            or digest(self.payload) != self.payload_digest
        ):
            raise ValueError("fiscal_manifest_identity")
        # The manifest, installed by the operator, is the sole payload owner.
        if self.payload.get("idDoc", {}).get(
            "encf"
        ) != self.number or "paymentType" not in self.payload.get("idDoc", {}):
            raise ValueError("fiscal_manifest_payload")
        if self.payload.get("sender", {}).get("rnc") != self.issuer or any(
            k in self.payload for k in ("company", "idCompany")
        ):
            raise ValueError("fiscal_manifest_company")
        return self


class Observation(Strict):
    source: Literal["response", "callback", "poll", "artifact", "unknown", "conflict"]
    provider_id: str | None = Field(
        default=None, max_length=120, pattern=r"^[A-Za-z0-9_-]+$"
    )
    issuer: str | None = Field(default=None, max_length=11)
    number: str | None = Field(default=None, max_length=13)
    processing: Processing = "unreported"
    legal: Legal = "unreported"
    xml: ArtifactState = "unreported"
    pdf: ArtifactState = "unreported"
    code: str | None = Field(default=None, max_length=80, pattern=r"^[A-Za-z0-9_.:-]+$")
    evidence_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    # URLs are private credentials; excluded from public projection.
    xml_url: str | None = Field(default=None, max_length=4096)
    pdf_url: str | None = Field(default=None, max_length=4096)


class FiscalState(Strict):
    submission: Literal["prepared", "contacted", "unknown", "identified"]
    processing: Processing = "unreported"
    legal: Legal = "unreported"
    xml: ArtifactState = "unreported"
    pdf: ArtifactState = "unreported"
    delivery: Literal["not_requested"] = "not_requested"
    reconciliation: Literal[
        "not_needed", "pending", "identity_missing", "exhausted", "conflict"
    ] = "not_needed"
    diagnostics: tuple[str, ...] = ()
    needs_review: bool = False


class FiscalOperation(Strict):
    id: UUID
    business_id: UUID
    case_id: str
    kind: Literal["E31", "E32"]
    number: str
    payload_digest: str
    provider_id: str | None
    state: FiscalState
