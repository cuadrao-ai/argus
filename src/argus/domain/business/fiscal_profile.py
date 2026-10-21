from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from argus.domain.business.actions import plans
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.actions import Applied
from argus.domain.business.contracts.dgii import TaxId
from argus.domain.business.fiscal_identity import normalized_filer_tax_id
from argus.domain.business.spaces import MAX_NAME_LENGTH
from argus.domain.business.transactions import transaction

_CODES = (
    "tax_id_type",
    "tax_id_not_digits",
    "tax_id_length",
    "tax_id_all_zero",
    "business_name_invalid",
)


class TaxIdDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: str
    value: str


class FiscalProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    previous_name: str
    tax_id: TaxIdDraft | None
    previous_tax_id: TaxIdDraft | None


class FiscalProfileChange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: Literal["set_business_rnc"] = "set_business_rnc"
    name: str
    previous_name: str
    tax_id: TaxId | None
    previous_tax_id: TaxId | None

    @field_validator("name", "previous_name")
    @classmethod
    def business_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned or len(cleaned) > MAX_NAME_LENGTH:
            raise ValueError("business_name_invalid")
        return cleaned

    @field_validator("tax_id", "previous_tax_id", mode="before")
    @classmethod
    def filer_tax_id(cls, value):
        if value is None or isinstance(value, TaxId):
            return value
        if not isinstance(value, dict):
            raise ValueError("tax_id_type")
        kind = value.get("type")
        raw = value.get("value")
        if not isinstance(kind, str) or not isinstance(raw, str):
            raise ValueError("tax_id_type")
        return {"type": kind, "value": normalized_filer_tax_id(kind, raw)}


def validation_code(error: ValidationError) -> str:
    text = str(error)
    return next((code for code in _CODES if code in text), "invalid_input")


def accepted_change(body: FiscalProfileInput) -> FiscalProfileChange:
    try:
        return FiscalProfileChange.model_validate(body.model_dump())
    except ValidationError as error:
        raise ActionError("invalid_input", validation_code(error)) from None


def _tax_id(row) -> dict | None:
    if row["business_rnc"] is None:
        return None
    return {"type": row["business_tax_id_type"], "value": row["business_rnc"]}


def _stored_tax_id(row) -> TaxId | None:
    parsed = _tax_id(row)
    return None if parsed is None else TaxId.model_validate(parsed)


def read_profile(authority, context):
    with transaction(authority, context) as tx:
        row = tx.rows(
            "select name, business_rnc, business_tax_id_type"
            " from public.spaces where id=%s",
            (context.actor.space_id,),
        )[0]
        return {
            "name": row["name"],
            "tax_id": _tax_id(row),
            "can_edit": context.actor.actor_kind == "member"
            and str(context.actor.actor_id) == str(context.owner_id)
            and "approve" in tx.authorization.capabilities,
        }


def set_profile(authority, context, command: FiscalProfileChange, key: str):
    with transaction(authority, context, "approve") as tx:
        if context.actor.actor_kind != "member" or str(context.actor.actor_id) != str(
            context.owner_id
        ):
            raise ActionError("permission_denied", "business_owner_required")
        saved = plans.receipt(tx, key, command)
        if saved is not None:
            result = plans.replay(saved)
            if result.outcome not in {"applied", "replayed"}:
                raise ActionError(result.outcome, result.code)
        else:
            row = tx.rows(
                "select name, business_rnc, business_tax_id_type"
                " from public.spaces where id=%s for update",
                (context.actor.space_id,),
            )[0]
            if (
                row["name"] != command.previous_name
                or _stored_tax_id(row) != command.previous_tax_id
            ):
                raise ActionError("stale_version", "stale_version")
            plans.start_receipt(tx, key, command)
            tax_id = command.tax_id
            tx.rows(
                "update public.spaces"
                " set name=%s, business_rnc=%s, business_tax_id_type=%s"
                " where id=%s returning id",
                (
                    command.name,
                    None if tax_id is None else tax_id.value,
                    None if tax_id is None else tax_id.type,
                    context.actor.space_id,
                ),
            )
            plans.finish_receipt(tx, key, Applied(outcome="applied"))
    return read_profile(authority, context)
