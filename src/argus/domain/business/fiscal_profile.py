from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from argus.domain.business.actions import plans
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.actions import Applied
from argus.domain.business.transactions import transaction


class FiscalProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rnc: str | None = Field(pattern=r"^[0-9]{9}$")
    previous_rnc: str | None = Field(pattern=r"^[0-9]{9}$")

    @field_validator("rnc", "previous_rnc")
    @classmethod
    def nonzero_rnc(cls, value):
        if value == "000000000":
            raise ValueError("RNC must have a nonzero digit")
        return value


class FiscalProfileChange(FiscalProfileInput):
    action: Literal["set_business_rnc"] = "set_business_rnc"


def read_profile(authority, context):
    with transaction(authority, context) as tx:
        row = tx.rows(
            "select business_rnc from public.spaces where id=%s",
            (context.actor.space_id,),
        )[0]
        return {
            "rnc": row["business_rnc"],
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
                "select business_rnc from public.spaces where id=%s for update",
                (context.actor.space_id,),
            )[0]
            if row["business_rnc"] != command.previous_rnc:
                raise ActionError("stale_version", "stale_version")
            plans.start_receipt(tx, key, command)
            tx.rows(
                "update public.spaces set business_rnc=%s where id=%s returning id",
                (command.rnc, context.actor.space_id),
            )
            plans.finish_receipt(tx, key, Applied(outcome="applied"))
    return read_profile(authority, context)
