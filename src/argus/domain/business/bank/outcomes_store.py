"""Igualar, desigualar, decline, and mark a line as needing no comprobante.

A match and the document's settlement change in one transaction. The match
stores the settlement it replaced, and undoing the match writes that back.
Each action locks its line first, so two actions on one line run in turn; a
document matched from two lines at once is refused by the live-document index.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row

from argus.domain.business.authority import ActionContext, ActionError
from argus.domain.business.bank.matching import derive_confidence, score_parts
from argus.domain.business.bank.model import BankMatchingError, ScoreParts
from argus.domain.business.bank.movements import (
    Document,
    applied_settlement,
    match_refusal,
)
from argus.domain.business.bank.movements_store import (
    account_of_line,
    bank_session,
    line_item,
    load_documents,
    lock_line,
)
from argus.domain.business.month_close import Settlement
from argus.domain.business.month_close_store import (
    current_settlement,
    write_settlement,
)

_SUGGESTION = """
select id, space_id, line_id, target_kind, target_id, status, amount_score,
       date_score, merchant_score, decision_key
from public.business_bank_suggestions
where id = %s and space_id = %s
"""

_LIVE = """
select id, kind, target_kind, target_id::text as target_id, reason, create_key,
       prior_status, prior_settled_on, prior_payment_method,
       applied_status, applied_settled_on, applied_payment_method
from public.business_bank_line_outcomes
where line_id = %s and ended_at is null
"""

_BY_CREATE_KEY = """
select kind, target_id::text as target_id, reason
from public.business_bank_line_outcomes
where line_id = %s and create_key = %s
"""

_ENDED_WITH = """
select 1 from public.business_bank_line_outcomes
where line_id = %s and end_key = %s
"""

_INSERT_MATCH = """
insert into public.business_bank_line_outcomes (
    space_id, line_id, kind, target_kind, target_id,
    prior_status, prior_settled_on, prior_payment_method,
    applied_status, applied_settled_on, applied_payment_method,
    created_by, create_key
) values (%s, %s, 'match', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

_INSERT_NO_RECEIPT = """
insert into public.business_bank_line_outcomes (
    space_id, line_id, kind, reason, created_by, create_key
) values (%s, %s, 'no_receipt', %s, %s, %s)
"""

_END = """
update public.business_bank_line_outcomes
set ended_at = clock_timestamp(), ended_by = %s, end_key = %s
where id = %s and ended_at is null
"""

_DECLINE = """
update public.business_bank_suggestions
set status = 'declined', decided_at = now(), decided_by = %s, decision_key = %s
where id = %s and space_id = %s and status = 'pending'
"""

_HISTORY = """
select id::text as id, kind, target_kind, target_id::text as target_id, reason,
       created_at, ended_at
from public.business_bank_line_outcomes
where line_id = %s and space_id = %s
order by created_at, id
"""

_UNIQUE_CODES = {
    "business_bank_line_outcomes_live_line_idx": "line_already_confirmed",
    "business_bank_line_outcomes_live_document_idx": "document_already_matched",
    "business_bank_line_outcomes_line_id_create_key_key": "idempotency_conflict",
}


def confirm_suggestion(
    pool, context: ActionContext, suggestion_id: UUID, key: str
) -> dict:  # noqa: ANN001
    with bank_session(pool, context, "prepare") as connection:
        space_id = context.actor.space_id
        offer = _suggestion(connection, suggestion_id, space_id)
        line = lock_line(connection, space_id, offer["line_id"])
        live = _one(connection, _LIVE, (line.id,))
        if live is not None and live["target_id"] == offer["target_id"]:
            if live["create_key"] == key:
                return _suggestion_view(connection, offer)
            raise BankMatchingError("suggestion_not_pending")
        if offer["status"] == "declined":
            raise BankMatchingError("pair_declined")
        _refuse_live(live)
        documents, activities = load_documents(pool, connection, context)
        document = documents.get(offer["target_id"])
        if (
            document is None
            or document.kind != offer["target_kind"]
            or score_parts(line, document) is None
        ):
            raise BankMatchingError("target_not_approved")
        _match(connection, context, line, document, activities, key)
        return _suggestion_view(connection, offer)


def decline_suggestion(
    pool, context: ActionContext, suggestion_id: UUID, key: str
) -> dict:  # noqa: ANN001
    with bank_session(pool, context, "prepare") as connection:
        space_id = context.actor.space_id
        offer = _suggestion(connection, suggestion_id, space_id)
        lock_line(connection, space_id, offer["line_id"])
        live = _one(connection, _LIVE, (offer["line_id"],))
        if live is not None and live["target_id"] == offer["target_id"]:
            raise BankMatchingError("suggestion_not_pending")
        if offer["status"] == "declined":
            if offer["decision_key"] == key:
                return _suggestion_view(connection, offer)
            raise BankMatchingError("suggestion_not_pending")
        connection.execute(
            _DECLINE, (context.actor.actor_id, key, suggestion_id, space_id)
        )
        return _suggestion_view(
            connection, _suggestion(connection, suggestion_id, space_id)
        )


def match_line(
    pool, context: ActionContext, line_id: UUID, activity_id: UUID, key: str
) -> dict:  # noqa: ANN001
    with bank_session(pool, context, "prepare") as connection:
        space_id = context.actor.space_id
        line = lock_line(connection, space_id, line_id)
        if _replayed(connection, line_id, key, kind="match", target=str(activity_id)):
            return line_item(pool, connection, context, line)
        live = _one(connection, _LIVE, (line_id,))
        _refuse_live(live)
        documents, activities = load_documents(pool, connection, context)
        document = documents.get(str(activity_id))
        if document is None:
            raise ActionError("not_found", "business_record_not_found")
        refusal = match_refusal(line, document)
        if refusal is not None:
            raise BankMatchingError(refusal)
        _match(connection, context, line, document, activities, key)
        return line_item(pool, connection, context, line)


def unmatch_line(pool, context: ActionContext, line_id: UUID, key: str) -> dict:  # noqa: ANN001
    with bank_session(pool, context, "prepare") as connection:
        space_id = context.actor.space_id
        line = lock_line(connection, space_id, line_id)
        live = _one(connection, _LIVE, (line_id,))
        if live is None or live["kind"] != "match":
            if _one(connection, _ENDED_WITH, (line_id, key)) is not None:
                return line_item(pool, connection, context, line)
            raise BankMatchingError("line_not_matched")
        connection.execute(_END, (context.actor.actor_id, key, live["id"]))
        activity_id = live["target_id"]
        current, existed = current_settlement(connection, context, activity_id)
        prior = Settlement(
            live["prior_status"], live["prior_settled_on"], live["prior_payment_method"]
        )
        write_settlement(
            connection,
            context,
            _activity(activity_id, live["target_kind"]),
            current,
            prior,
            existed=existed,
        )
        return line_item(pool, connection, context, line)


def set_disposition(
    pool, context: ActionContext, line_id: UUID, reason: str, key: str
) -> dict:  # noqa: ANN001
    with bank_session(pool, context, "prepare") as connection:
        space_id = context.actor.space_id
        line = lock_line(connection, space_id, line_id)
        live = _one(connection, _LIVE, (line_id,))
        if live is not None and live["kind"] == "match":
            raise BankMatchingError("line_already_confirmed")
        if live is not None and live["reason"] == reason:
            return line_item(pool, connection, context, line)
        if _replayed(connection, line_id, key, kind="no_receipt", reason=reason):
            return line_item(pool, connection, context, line)
        if live is not None:
            connection.execute(_END, (context.actor.actor_id, key, live["id"]))
        _insert(
            connection,
            _INSERT_NO_RECEIPT,
            (space_id, line_id, reason, context.actor.actor_id, key),
        )
        return line_item(pool, connection, context, line)


def clear_disposition(pool, context: ActionContext, line_id: UUID, key: str) -> dict:  # noqa: ANN001
    with bank_session(pool, context, "prepare") as connection:
        space_id = context.actor.space_id
        line = lock_line(connection, space_id, line_id)
        live = _one(connection, _LIVE, (line_id,))
        if live is None or live["kind"] != "no_receipt":
            if _one(connection, _ENDED_WITH, (line_id, key)) is not None:
                return line_item(pool, connection, context, line)
            raise BankMatchingError("line_not_marked")
        connection.execute(_END, (context.actor.actor_id, key, live["id"]))
        return line_item(pool, connection, context, line)


def line_history(pool, context: ActionContext, line_id: UUID) -> list[dict]:  # noqa: ANN001
    with bank_session(pool, context, "read") as connection:
        space_id = context.actor.space_id
        lock_line(connection, space_id, line_id, lock=False)
        return [
            {
                "id": row["id"],
                "kind": row["kind"],
                "target_kind": row["target_kind"],
                "activity_id": row["target_id"],
                "reason": row["reason"],
                "created_at": row["created_at"],
                "ended_at": row["ended_at"],
            }
            for row in _rows(connection, _HISTORY, (line_id, space_id))
        ]


def _match(
    connection,  # noqa: ANN001
    context: ActionContext,
    line,  # noqa: ANN001
    document: Document,
    activities: Mapping[str, Mapping],
    key: str,
) -> None:
    """Record the match, then write the settlement it implies. The settlement
    trigger accepts the new settlement only once the match is live."""

    planned = applied_settlement(document.kind, line, account_of_line(connection, line))
    prior, existed = current_settlement(connection, context, document.activity_id)
    _insert(
        connection,
        _INSERT_MATCH,
        (
            context.actor.space_id,
            line.id,
            document.kind,
            document.activity_id,
            prior.status,
            prior.settled_on,
            prior.payment_method,
            planned.status,
            planned.settled_on,
            planned.payment_method,
            context.actor.actor_id,
            key,
        ),
    )
    write_settlement(
        connection,
        context,
        activities[document.activity_id],
        prior,
        planned,
        existed=existed,
    )


def _insert(connection, sql: str, params: tuple) -> None:  # noqa: ANN001
    try:
        with connection.transaction():
            connection.execute(sql, params)
    except UniqueViolation as error:
        code = _UNIQUE_CODES.get(error.diag.constraint_name or "", "idempotency_conflict")
        raise BankMatchingError(code) from None


def _refuse_live(live: dict | None) -> None:
    if live is None:
        return
    if live["kind"] == "match":
        raise BankMatchingError("line_already_confirmed")
    raise BankMatchingError("line_marked_no_receipt")


def _replayed(
    connection,  # noqa: ANN001
    line_id: UUID,
    key: str,
    *,
    kind: str,
    target: str | None = None,
    reason: str | None = None,
) -> bool:
    """True when this key already made this outcome on this line. The same key
    for another outcome is a conflict."""

    row = _one(connection, _BY_CREATE_KEY, (line_id, key))
    if row is None:
        return False
    if (row["kind"], row["target_id"], row["reason"]) != (kind, target, reason):
        raise BankMatchingError("idempotency_conflict")
    return True


def _activity(activity_id: str, target_kind: str) -> dict:
    """The two activity facts a settlement write reads."""

    return {
        "activity_id": activity_id,
        "kind": "expense" if target_kind == "receipt" else "income",
    }


def _suggestion(connection, suggestion_id: UUID, space_id) -> dict:  # noqa: ANN001
    row = _one(connection, _SUGGESTION, (suggestion_id, space_id))
    if row is None:
        raise BankMatchingError("suggestion_not_found")
    return row


def _suggestion_view(connection, offer: dict) -> dict:  # noqa: ANN001
    """The suggestion as the bank routes return it, with its status derived
    from the line's live outcome."""

    live = _one(connection, _LIVE, (offer["line_id"],))
    confirmed = live is not None and live["target_id"] == offer["target_id"]
    taken = _one(
        connection,
        "select 1 from public.business_bank_line_outcomes"
        " where space_id = %s and target_id::text = %s and kind = 'match'"
        " and ended_at is null",
        (offer["space_id"], offer["target_id"]),
    )
    parts = ScoreParts(
        offer["amount_score"], offer["date_score"], offer["merchant_score"]
    )
    return {
        "id": offer["id"],
        "line_id": offer["line_id"],
        "target_id": offer["target_id"],
        "target_kind": offer["target_kind"],
        "status": "confirmed" if confirmed else offer["status"],
        "amount_score": parts.amount_score,
        "date_score": parts.date_score,
        "merchant_score": parts.merchant_score,
        "confidence": derive_confidence(parts),
        "actionable": offer["status"] == "pending" and live is None and taken is None,
    }


def _rows(connection, sql: str, params: tuple) -> list[dict[str, Any]]:  # noqa: ANN001
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(sql, params)
        return list(cursor.fetchall())


def _one(connection, sql: str, params: tuple) -> dict[str, Any] | None:  # noqa: ANN001
    rows = _rows(connection, sql, params)
    return rows[0] if rows else None
