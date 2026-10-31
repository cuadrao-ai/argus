"""Load and settle a month, and read open items across months, from the same
activities the export already reads.

The settlement row is an annotation. This module does not copy amounts.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal

from psycopg.errors import CheckViolation, UniqueViolation
from psycopg.rows import dict_row

from argus.domain.business import ledger
from argus.domain.business.authority import ActionContext, ActionError, authorize
from argus.domain.business.dgii_columns import COLUMNS
from argus.domain.business.dgii_export import FOREIGN_CURRENCY_NOTE, fiscal_manifest
from argus.domain.business.dgii_snapshot import fiscal_snapshot
from argus.domain.business.month_close import (
    IMPLICIT,
    PAYMENT_METHODS,
    Settlement,
    month_period,
    open_items,
    project_documents,
    set_document_status,
    summarize,
)
from argus.domain.business.rnc_registry import postgres_rnc_fetch, registry_from_config

Capability = Literal["read", "prepare"]

_DRAFTS = """
select e.activity_id::text as activity_id,
       e.updated_at,
       e.resolution
from public.financial_import_events e
where e.user_id = %s
  and e.owner_space_id = %s
  and e.activity_id is not null
  and e.resolution ? 'business'
order by e.updated_at desc, e.id desc
"""

_SETTLEMENTS = """
select activity_id::text as activity_id,
       status,
       settled_on,
       payment_method
from public.business_document_settlements
where space_id = %s
  and owner_id = %s
"""

_LOCK = """
select status, settled_on, payment_method
from public.business_document_settlements
where space_id = %s and activity_id = %s
for update
"""

_INSERT = """
insert into public.business_document_settlements (
    space_id, owner_id, activity_id, document_kind,
    status, settled_on, payment_method
) values (%s, %s, %s, %s, %s, %s, %s)
"""

_UPDATE = """
update public.business_document_settlements
set document_kind = %s,
    status = %s,
    settled_on = %s,
    payment_method = %s,
    updated_at = clock_timestamp()
where space_id = %s and activity_id = %s
"""

_REVISION = """
insert into public.business_document_settlement_revisions (
    space_id, activity_id, actor_id,
    previous_status, previous_settled_on, previous_payment_method
) values (%s, %s, %s, %s, %s, %s)
"""


class _Race(Exception):
    """Another request inserted this settlement first."""


def read_month(authority, context: ActionContext, month: str) -> dict:
    start, end = month_period(month)
    today = ledger.today()
    with _session(authority, context, "read") as (connection, auth):
        documents, by_id = _collect(authority, connection, auth.context)
        forms, foreign = _form_statuses(
            connection, auth.context, tuple(by_id.values()), start, end, today
        )
    return month_close(month, today, documents, forms, foreign)


def foreign_currency(manifest_forms: dict) -> dict:
    """Per form, how many foreign-currency lines wait for a rate, in words.

    A form missing the count (an older summary) reads as zero."""

    result = {}
    for form in COLUMNS:
        count = manifest_forms.get(form, {}).get("foreign_currency_pending_rate_count", 0)
        result[form] = {
            "pending_rate_count": count,
            "reason": FOREIGN_CURRENCY_NOTE if count else None,
        }
    return result


def empty_month(month: str) -> dict:
    """The month as it reads with no documents and no store: the whole shape,
    nothing in it, and the forms with no operations."""

    return month_close(month, ledger.today(), (), dict.fromkeys(COLUMNS, "no_operations"))


def month_close(  # noqa: ANN001
    month: str, today, documents, forms: dict[str, str], foreign: dict | None = None
) -> dict:
    start, end = month_period(month)
    return {
        "month": month,
        "today": today,
        "payment_methods": list(PAYMENT_METHODS),
        "dgii_forms": forms,
        "dgii_foreign_currency": foreign or foreign_currency({}),
        **summarize(documents, start, end),
    }


def _form_statuses(
    connection, context: ActionContext, activities, start, end, today
) -> tuple[dict[str, str], dict]:
    """Each form's status word and foreign-currency count, read from the summary the export packet writes."""

    with connection.cursor(row_factory=dict_row) as cursor:
        records, rnc, name = fiscal_snapshot(cursor, context, activities)

        def lookup(sql, params):
            cursor.execute(sql, params)
            return cursor.fetchone()

        manifest, _rows = fiscal_manifest(
            records,
            rnc=rnc,
            business_name=name,
            start=start,
            end=end,
            captured_on=today,
            registry=registry_from_config("dgii", postgres_rnc_fetch(lookup)),
        )
    statuses = {form: shape["status"] for form, shape in manifest["forms"].items()}
    return statuses, foreign_currency(manifest["forms"])


def read_open(authority, context: ActionContext) -> dict:
    today = ledger.today()
    with _session(authority, context, "read") as (connection, auth):
        documents, _by_id = _collect(authority, connection, auth.context)
    return open_items(documents, today)


def settle_document(
    authority,
    context: ActionContext,
    activity_id: str,
    command: Settlement,
) -> dict:
    """Settle one document. A lost insert race retries in a new transaction.

    The first attempt can miss a row that commits after its snapshot. Repeating
    the insert in that same transaction raises again, and the route would turn
    that into a 503. The second attempt starts clean. If it still collides,
    the caller gets a conflict, not an outage.
    """
    for attempt in (1, 2):
        try:
            return _settle_once(
                authority, context, activity_id, command, retry=attempt == 1
            )
        except _Race:
            continue
    raise ActionError("idempotency_conflict", "business_document_settlement_conflict")


def _settle_once(
    authority,
    context: ActionContext,
    activity_id: str,
    command: Settlement,
    *,
    retry: bool,
) -> dict:
    with _session(authority, context, "prepare") as (connection, auth):
        documents, by_id = _collect(authority, connection, auth.context)
        found = by_id.get(activity_id)
        if found is None:
            raise ActionError("not_found", "business_record_not_found")
        if found["kind"] not in {"income", "expense"}:
            raise ActionError("invalid_input", "activity_kind_unsupported")
        row = _lock(connection, auth.context, activity_id)
        current = (
            IMPLICIT
            if row is None
            else Settlement(row["status"], row["settled_on"], row["payment_method"])
        )

        def write(previous: Settlement, planned: Settlement) -> None:
            _persist(
                connection,
                auth.context,
                found,
                previous,
                planned,
                existed=row is not None,
                retry=retry,
            )

        role, settlement, changed = set_document_status(
            auth,
            documents,
            str(auth.context.actor.space_id),
            activity_id,
            command,
            current,
            write,
        )
        return {
            "activity_id": activity_id,
            "document_kind": role,
            "status": settlement.status,
            "settled_on": settlement.settled_on,
            "payment_method": settlement.payment_method,
            "changed": changed,
        }


def current_settlement(
    connection, context: ActionContext, activity_id: str
) -> tuple[Settlement, bool]:
    """The document's settlement, locked, and whether a row holds it."""

    row = _lock(connection, context, activity_id)
    if row is None:
        return IMPLICIT, False
    return Settlement(row["status"], row["settled_on"], row["payment_method"]), True


def write_settlement(
    connection,
    context: ActionContext,
    activity,
    previous: Settlement,
    planned: Settlement,
    *,
    existed: bool,
) -> None:
    """Write ``planned`` with a revision row, unless it is already stored."""

    if planned != previous:
        _persist(
            connection, context, activity, previous, planned, existed=existed, retry=False
        )


def _lock(connection, context: ActionContext, activity_id: str):
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(_LOCK, (context.actor.space_id, activity_id))
        return cursor.fetchone()


def _persist(
    connection,
    context: ActionContext,
    activity,
    previous: Settlement,
    planned: Settlement,
    *,
    existed: bool,
    retry: bool,
) -> None:
    kind = "invoice" if activity["kind"] == "income" else "receipt"
    space_id = context.actor.space_id
    activity_id = activity["activity_id"]
    try:
        with connection.transaction():
            if existed:
                connection.execute(
                    _UPDATE,
                    (
                        kind,
                        planned.status,
                        planned.settled_on,
                        planned.payment_method,
                        space_id,
                        activity_id,
                    ),
                )
            else:
                connection.execute(
                    _INSERT,
                    (
                        space_id,
                        context.owner_id,
                        activity_id,
                        kind,
                        planned.status,
                        planned.settled_on,
                        planned.payment_method,
                    ),
                )
            connection.execute(
                _REVISION,
                (
                    space_id,
                    activity_id,
                    context.actor.actor_id,
                    previous.status,
                    previous.settled_on,
                    previous.payment_method,
                ),
            )
    except UniqueViolation:
        if retry:
            raise _Race() from None
        raise ActionError(
            "idempotency_conflict", "business_document_settlement_conflict"
        ) from None
    except CheckViolation as error:
        if error.diag.message_primary != "business_document_matched":
            raise
        raise ActionError("idempotency_conflict", "business_document_matched") from None


@contextmanager
def _session(
    authority, context: ActionContext, capability: Capability
) -> Iterator[tuple]:
    with authority.pool.connection() as connection, connection.transaction():
        connection.execute("set transaction isolation level repeatable read")
        auth = authorize(connection, context.actor, context.grant_id)
        auth.require(capability)
        if auth.context.owner_id != context.owner_id:
            raise ActionError("not_found", "business_record_not_found")
        yield connection, auth


def _collect(authority, connection, context: ActionContext):
    return collect_documents(
        authority.pool, connection, context.owner_id, str(context.actor.space_id)
    )


def collect_documents(pool, connection, owner_id: str, space_id: str):
    """The Business's recorded documents and their activities, read on
    ``connection``. Bank matching reads the same documents."""

    from argus.domain.owner_scope import BusinessSpace
    from argus.domain.recording.canonical_groups import VisibleAccounts, load
    from argus.domain.recording.money_reads import current_activities
    from argus.domain.recording.postgres_repository import (
        PostgresFinancialAccountRepository,
    )

    canonical = load(
        PostgresFinancialAccountRepository(pool),
        connection,
        {owner_id},
        scope=BusinessSpace(space_id),
    )
    activities = tuple(
        current_activities(
            VisibleAccounts(
                [
                    stored
                    for stored in canonical.records
                    if stored.account.user_id == owner_id
                ],
                canonical,
            )
        )
    )
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(_DRAFTS, (owner_id, space_id))
        resolutions = cursor.fetchall()
        settlements = read_settlements(cursor, owner_id, space_id)
    documents = project_documents(activities, resolutions, settlements, space_id)
    return documents, {str(activity["activity_id"]): activity for activity in activities}


def read_settlements(cursor, owner_id: str, space_id: str) -> dict[str, dict]:
    """Every stored settlement of the Business, by activity id, on the
    caller's own snapshot. The export reads them beside its activities."""

    cursor.execute(_SETTLEMENTS, (space_id, owner_id))
    return {row["activity_id"]: row for row in cursor.fetchall()}
