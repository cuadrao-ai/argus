from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from argus.domain.business.actions import plans
from argus.domain.business.actions.dossier import rnc_registry
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.actions import Applied
from argus.domain.business.contracts.dgii import TaxId
from argus.domain.business.fiscal_identity import normalized_filer_tax_id
from argus.domain.business.space_name import given_name
from argus.domain.business.spaces import MAX_NAME_LENGTH
from argus.domain.business.transactions import transaction

_CODES = (
    "tax_id_type",
    "tax_id_not_digits",
    "tax_id_length",
    "tax_id_all_zero",
    "business_name_invalid",
    "legal_name_invalid",
    "legal_name_confirmation_required",
)
#: The longest legal name the profile stores; the registry's names fit.
LEGAL_NAME_MAX = 250


class TaxIdDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: str
    value: str


class FiscalProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    previous_name: str | None
    tax_id: TaxIdDraft | None
    previous_tax_id: TaxIdDraft | None


class FiscalProfileChange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: Literal["set_business_rnc"] = "set_business_rnc"
    name: str
    previous_name: str | None
    tax_id: TaxId | None
    previous_tax_id: TaxId | None

    @field_validator("name", "previous_name")
    @classmethod
    def business_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned or len(cleaned) > MAX_NAME_LENGTH:
            raise ValueError("business_name_invalid")
        return cleaned

    @field_validator("tax_id", "previous_tax_id", mode="before")
    @classmethod
    def filer_tax_id(cls, value):
        return _filer_tax_id(value)


def _filer_tax_id(value):
    """A tax id as a person keys it, to the digits the profile stores."""

    if value is None or isinstance(value, TaxId):
        return value
    if not isinstance(value, dict):
        raise ValueError("tax_id_type")
    kind = value.get("type")
    raw = value.get("value")
    if not isinstance(kind, str) or not isinstance(raw, str):
        raise ValueError("tax_id_type")
    return {"type": kind, "value": normalized_filer_tax_id(kind, raw)}


def _legal_name(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned or len(cleaned) > LEGAL_NAME_MAX:
        raise ValueError("legal_name_invalid")
    return cleaned


class LegalNameInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    legal_name: str | None
    previous_legal_name: str | None
    tax_id: TaxIdDraft
    confirmed: bool = False


class LegalNameChange(BaseModel):
    """A person who manages the Business confirms the registry's name for the
    stored tax id. ``legal_name`` is the name they saw; the server stores the
    registry row's own name. Null clears it and needs no confirmation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: Literal["set_business_legal_name"] = "set_business_legal_name"
    legal_name: str | None
    previous_legal_name: str | None
    tax_id: TaxId
    confirmed: bool

    @field_validator("legal_name", "previous_legal_name")
    @classmethod
    def legal_name_shape(cls, value: str | None) -> str | None:
        return _legal_name(value)

    @field_validator("tax_id", mode="before")
    @classmethod
    def filer_tax_id(cls, value):
        return _filer_tax_id(value)

    @field_validator("confirmed")
    @classmethod
    def confirmation(cls, value: bool, info) -> bool:
        if info.data.get("legal_name") is not None and not value:
            raise ValueError("legal_name_confirmation_required")
        return value


class RegistryLookupInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tax_id: TaxIdDraft


class RegistryQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tax_id: TaxId

    @field_validator("tax_id", mode="before")
    @classmethod
    def filer_tax_id(cls, value):
        return _filer_tax_id(value)


def validation_code(error: ValidationError) -> str:
    text = str(error)
    return next((code for code in _CODES if code in text), "invalid_input")


def _accepted(model, body: BaseModel):
    try:
        return model.model_validate(body.model_dump())
    except ValidationError as error:
        raise ActionError("invalid_input", validation_code(error)) from None


def accepted_change(body: FiscalProfileInput) -> FiscalProfileChange:
    return _accepted(FiscalProfileChange, body)


def accepted_legal_name(body: LegalNameInput) -> LegalNameChange:
    return _accepted(LegalNameChange, body)


def accepted_query(body: RegistryLookupInput) -> RegistryQuery:
    return _accepted(RegistryQuery, body)


def _tax_id(row) -> dict | None:
    if row["business_rnc"] is None:
        return None
    return {"type": row["business_tax_id_type"], "value": row["business_rnc"]}


def _stored_tax_id(row) -> TaxId | None:
    parsed = _tax_id(row)
    return None if parsed is None else TaxId.model_validate(parsed)


_PROFILE = (
    "select name, business_rnc, business_tax_id_type, business_legal_name,"
    " business_legal_name_confirmed_at from public.spaces where id=%s"
)


def _stored_legal_name(row) -> dict | None:
    if row["business_legal_name"] is None:
        return None
    return {
        "value": row["business_legal_name"],
        "confirmed_at": row["business_legal_name_confirmed_at"],
    }


def read_profile(authority, context):
    with transaction(authority, context) as tx:
        row = tx.rows(_PROFILE, (context.actor.space_id,))[0]
        return {
            "name": row["name"],
            "tax_id": _tax_id(row),
            "legal_name": _stored_legal_name(row),
            "can_edit": context.actor.actor_kind == "member"
            and "manage" in tx.authorization.permissions,
        }


def _require_manager(context) -> None:
    if context.actor.actor_kind != "member":
        raise ActionError("permission_denied", "business_owner_required")


def _replayed(tx, key: str, command) -> bool:
    saved = plans.receipt(tx, key, command)
    if saved is None:
        return False
    result = plans.replay(saved)
    if result.outcome not in {"applied", "replayed"}:
        raise ActionError(result.outcome, result.code)
    return True


def _registry_answer(tx, tax_id: TaxId) -> dict:
    """The registry's answer for one tax id, in the words counterparties get:
    verificado, no_activo or sin_verificar."""

    found = rnc_registry(tx).lookup(tax_id.value)
    if found is None:
        return {"tax_id": tax_id, "verification": "sin_verificar", "record": None}
    return {
        "tax_id": tax_id,
        "verification": found.verification,
        "record": {
            "rnc": found.rnc,
            "name": found.name,
            "trade_name": found.trade_name,
            "status": found.status,
            "file_date": found.file_date,
        },
    }


def lookup_registry(authority, context, query: RegistryQuery) -> dict:
    """Checks a tax id the person is about to save as the Business's own
    against the registry. Only someone who can manage the Business asks."""

    with transaction(authority, context, "manage") as tx:
        _require_manager(context)
        return {
            **_registry_answer(tx, query.tax_id),
            "checked_at": tx.rows("select clock_timestamp() as now")[0]["now"],
        }


def set_legal_name(authority, context, command: LegalNameChange, key: str):
    """Stores the registry's name for the stored tax id, who confirmed it and
    when. Refused when the registry lacks the tax id or names it differently
    from what the person saw."""

    with transaction(authority, context, "manage") as tx:
        _require_manager(context)
        if not _replayed(tx, key, command):
            row = tx.rows(_PROFILE + " for update", (context.actor.space_id,))[0]
            if (
                row["business_legal_name"] != command.previous_legal_name
                or _stored_tax_id(row) != command.tax_id
            ):
                raise ActionError("stale_version", "stale_version")
            stored = None
            if command.legal_name is not None:
                record = _registry_answer(tx, command.tax_id)["record"]
                if record is None:
                    raise ActionError("invalid_input", "legal_name_not_in_registry")
                # The registry owns the name. The person's copy only proves which
                # name they saw; another one (refreshed since, or invented) is stale.
                stored = record["name"].strip()
                if command.legal_name != stored:
                    raise ActionError("stale_version", "stale_version")
            plans.start_receipt(tx, key, command)
            confirmed = stored is not None
            tx.rows(
                "update public.spaces set business_legal_name=%s,"
                " business_legal_name_confirmed_by=%s,"
                " business_legal_name_confirmed_at="
                " case when %s then clock_timestamp() end"
                " where id=%s returning id",
                (
                    stored,
                    context.actor.actor_id if confirmed else None,
                    confirmed,
                    context.actor.space_id,
                ),
            )
            plans.finish_receipt(tx, key, Applied(outcome="applied"))
    return read_profile(authority, context)


def set_profile(authority, context, command: FiscalProfileChange, key: str):
    with transaction(authority, context, "manage") as tx:
        _require_manager(context)
        if not _replayed(tx, key, command):
            row = tx.rows(_PROFILE + " for update", (context.actor.space_id,))[0]
            if (
                given_name(row["name"]) != command.previous_name
                or _stored_tax_id(row) != command.previous_tax_id
            ):
                raise ActionError("stale_version", "stale_version")
            plans.start_receipt(tx, key, command)
            tax_id = command.tax_id
            # A legal name was confirmed for one tax id; another one clears it.
            keep_legal_name = _stored_tax_id(row) == tax_id
            tx.rows(
                "update public.spaces"
                " set name=%s, business_rnc=%s, business_tax_id_type=%s,"
                " business_legal_name=case when %s then business_legal_name end,"
                " business_legal_name_confirmed_by="
                " case when %s then business_legal_name_confirmed_by end,"
                " business_legal_name_confirmed_at="
                " case when %s then business_legal_name_confirmed_at end"
                " where id=%s returning id",
                (
                    command.name,
                    None if tax_id is None else tax_id.value,
                    None if tax_id is None else tax_id.type,
                    keep_legal_name,
                    keep_legal_name,
                    keep_legal_name,
                    context.actor.space_id,
                ),
            )
            plans.finish_receipt(tx, key, Applied(outcome="applied"))
    return read_profile(authority, context)
