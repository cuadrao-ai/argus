"""Private query recipes; every read and replay requires the current selected grant."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from psycopg.types.json import Jsonb
from pydantic import Field, field_validator

from argus.domain.business.authority import ActionContext, ActionError, BusinessAuthority
from argus.domain.business.reporting_preferences import RecipeInput
from argus.domain.business.reporting_query import Contract, ReportRecipe
from argus.domain.business.transactions import transaction


class CreateView(Contract):
    name: str = Field(min_length=1, max_length=120)
    recipe: RecipeInput = ReportRecipe()

    @field_validator("name")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("view name is blank")
        return value.strip()


class UpdateView(CreateView):
    expected_version: int = Field(ge=1, strict=True)


class SavedView(CreateView):
    id: UUID
    version: int
    created_at: datetime
    updated_at: datetime


_FIELDS = "id,name,recipe,version,created_at,updated_at"


def list_views(
    authority: BusinessAuthority, context: ActionContext
) -> tuple[SavedView, ...]:
    with transaction(authority, context) as tx:
        rows = tx.rows(
            f"select {_FIELDS} from argus_private.business_saved_report_views where space_id=%s and actor_id=%s order by created_at,id",
            (context.actor.space_id, context.actor.actor_id),
        )
        return tuple(SavedView.model_validate(row) for row in rows)


def _mutate(
    authority: BusinessAuthority, context: ActionContext, command: dict, key: str
) -> dict:
    if not key.strip() or len(key) > 200:
        raise ActionError("invalid_input", "invalid_idempotency_key")
    with transaction(authority, context) as tx:
        # The existing scoped transaction serializes preference edits and their receipts.
        params = (context.actor.space_id, context.actor.actor_id)
        receipts = tx.rows(
            "select command,result from argus_private.business_report_view_commands where space_id=%s and actor_id=%s and command_key=%s",
            (*params, key),
        )
        if receipts:
            if receipts[0]["command"] != command:
                raise ActionError("idempotency_conflict", "idempotency_conflict")
            return receipts[0]["result"]
        identifier = command.get("view_id")
        if identifier:
            rows = tx.rows(
                f"select {_FIELDS} from argus_private.business_saved_report_views where space_id=%s and actor_id=%s and id=%s for update",
                (*params, identifier),
            )
            if not rows:
                raise ActionError("not_found", "business_report_view_not_found")
            if rows[0]["version"] != command["expected_version"]:
                raise ActionError("stale_version", "business_report_view_changed")
        if command["operation"] == "delete":
            tx.rows(
                "delete from argus_private.business_saved_report_views where space_id=%s and actor_id=%s and id=%s",
                (*params, identifier),
            )
            result = {"deleted": True}
        else:
            name, recipe = command["name"], Jsonb(command["recipe"])
            if identifier:
                rows = tx.rows(
                    f"update argus_private.business_saved_report_views set name=%s,recipe=%s,version=version+1,updated_at=clock_timestamp() where space_id=%s and actor_id=%s and id=%s returning {_FIELDS}",
                    (name, recipe, *params, identifier),
                )
            else:
                rows = tx.rows(
                    f"insert into argus_private.business_saved_report_views (space_id,actor_id,name,recipe) values (%s,%s,%s,%s) returning {_FIELDS}",
                    (*params, name, recipe),
                )
            result = SavedView.model_validate(rows[0]).model_dump(mode="json")
        tx.rows(
            "insert into argus_private.business_report_view_commands (space_id,actor_id,command_key,command,result) values (%s,%s,%s,%s,%s)",
            (*params, key, Jsonb(command), Jsonb(result)),
        )
        return result


def save_view(
    authority: BusinessAuthority,
    context: ActionContext,
    command: CreateView | UpdateView,
    key: str,
    view_id: UUID | None = None,
) -> SavedView:
    if (view_id is not None) != isinstance(command, UpdateView):
        raise ValueError("view update requires expected version and id")
    payload = command.model_dump(mode="json") | {
        "operation": "update" if view_id else "create",
        "view_id": str(view_id) if view_id else None,
    }
    return SavedView.model_validate(_mutate(authority, context, payload, key))


def delete_view(
    authority: BusinessAuthority,
    context: ActionContext,
    view_id: UUID,
    expected_version: int,
    key: str,
) -> None:
    _mutate(
        authority,
        context,
        {
            "operation": "delete",
            "view_id": str(view_id),
            "expected_version": expected_version,
        },
        key,
    )
