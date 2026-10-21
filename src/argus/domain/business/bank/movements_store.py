"""Read Transacciones for one Business and period from Postgres.

The documents are the ones month close reads. Offers the rules allow that
were never stored are stored here, so a document approved after the
statement still reaches its line. Storing an offer confirms nothing.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from psycopg.rows import dict_row

from argus.domain.business.authority import ActionContext, ActionError, authorize
from argus.domain.business.bank.matching import expected_kind, new_offers
from argus.domain.business.bank.model import (
    MATCH_WINDOW_DAYS,
    BankLine,
    BankMatchingError,
    MatchTarget,
    ScoreParts,
    TargetKind,
)
from argus.domain.business.bank.movements import (
    Account,
    Document,
    LiveOutcome,
    Movement,
    Segment,
    StoredPair,
    build_movements,
    coverage_payload,
    documents_from,
    item_payload,
    page,
    taken_documents,
    totals,
    unmoved_documents,
)
from argus.domain.business.bank.store_postgres import LINE_COLUMNS, line_from_row
from argus.domain.business.month_close_store import collect_documents

_ACCOUNTS = """
select ba.id::text as bank_account_id, ba.account_id::text as account_id,
       fa.nickname, fa.type, ba.currency,
       (select max(l.occurred_on) from public.business_bank_lines l
        where l.bank_account_id = ba.id) as covered_through
from public.business_bank_accounts ba
join public.financial_accounts fa on fa.id = ba.account_id
where ba.space_id = %s
order by ba.created_at, ba.id
"""

_LINES = f"""
select {LINE_COLUMNS}
from public.business_bank_lines
where space_id = %s and occurred_on between %s and %s
order by occurred_on, id
"""

_PAIRS = """
select id::text as suggestion_id, line_id::text as line_id, target_kind, target_id,
       status, amount_score, date_score, merchant_score
from public.business_bank_suggestions
where space_id = %s and line_id = any(%s)
"""

_OUTCOMES = """
select line_id::text as line_id, kind, target_id::text as target_id, reason
from public.business_bank_line_outcomes
where space_id = %s and ended_at is null
"""

_LINE = f"""
select {LINE_COLUMNS}
from public.business_bank_lines
where id = %s and space_id = %s
"""

_OFFER = """
insert into public.business_bank_suggestions (
    space_id, line_id, target_kind, target_id, status,
    amount_score, date_score, merchant_score
) values (%s, %s, %s, %s, 'pending', %s, %s, %s)
on conflict (line_id, target_kind, target_id) do nothing
"""


def read_movements(
    pool,  # noqa: ANN001
    context: ActionContext,
    *,
    period_start: date,
    period_end: date,
    segment: Segment,
    sense: str | None,
    limit: int,
    cursor: str | None,
) -> dict:
    with bank_session(pool, context, "read") as connection:
        documents, _activities = load_documents(pool, connection, context)
        space_id = context.actor.space_id
        lines = _lines(connection, space_id, period_start, period_end)
        accounts = _accounts(connection, space_id)
        outcomes = _outcomes(connection, space_id)
        _store_offers(connection, space_id, lines, documents, outcomes)
        movements = _movements(connection, space_id, lines, accounts, documents, outcomes)
    taken = taken_documents(outcomes)
    unmoved = unmoved_documents(
        documents.values(), accounts.values(), taken, period_start, period_end
    )
    items = [*movements, *unmoved]
    shown, following = page(
        items, segment=segment, sense=sense, limit=limit, cursor=cursor
    )
    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "segment": segment,
        "sense": sense,
        "accounts": [coverage_payload(account) for account in accounts.values()],
        "totals": totals(items),
        "items": [item_payload(item) for item in shown],
        "next_cursor": following,
    }


def line_item(pool, connection, context: ActionContext, line: BankLine) -> dict:  # noqa: ANN001
    """One line as the movements read shows it, on the action's connection."""

    documents, _activities = load_documents(pool, connection, context)
    space_id = context.actor.space_id
    accounts = _accounts(connection, space_id)
    outcomes = _outcomes(connection, space_id)
    [movement] = _movements(connection, space_id, [line], accounts, documents, outcomes)
    return item_payload(movement)


def load_documents(
    pool, connection, context: ActionContext
) -> tuple[dict[str, Document], Mapping[str, Mapping]]:  # noqa: ANN001
    month_documents, activities = collect_documents(
        pool, connection, context.owner_id, str(context.actor.space_id)
    )
    documents = documents_from(month_documents, activities)
    return {document.activity_id: document for document in documents}, activities


def lock_line(connection, space_id, line_id, *, lock: bool = True) -> BankLine:  # noqa: ANN001
    """The line, locked so actions on one line run one at a time."""

    rows = _rows(connection, _LINE + (" for update" if lock else ""), (line_id, space_id))
    if not rows:
        raise BankMatchingError("line_not_found")
    return line_from_row(rows[0])


def account_of_line(connection, line: BankLine) -> Account:  # noqa: ANN001
    return _accounts(connection, line.space_id)[str(line.bank_account_id)]


class DocumentCatalog:
    """Recorded documents as statement-import targets, from the same read."""

    def __init__(self, pool) -> None:  # noqa: ANN001
        self.pool = pool

    def approved_targets(
        self,
        space_id,  # noqa: ANN001
        *,
        kind: TargetKind,
        period_start: date,
        period_end: date,
    ) -> tuple[MatchTarget, ...]:
        return tuple(
            document
            for document in self._documents(space_id)
            if document.kind == kind
            and period_start <= document.occurred_on <= period_end
        )

    def _documents(self, space_id) -> tuple[Document, ...]:  # noqa: ANN001
        with self.pool.connection() as connection, connection.transaction():
            row = connection.execute(
                "select created_by::text from public.spaces where id = %s",
                (space_id,),
            ).fetchone()
            if row is None:
                return ()
            month_documents, activities = collect_documents(
                self.pool, connection, row[0], str(space_id)
            )
        return documents_from(month_documents, activities)


@contextmanager
def bank_session(pool, context: ActionContext, capability: str) -> Iterator[Any]:  # noqa: ANN001
    """One read-committed transaction with the caller's live grant checked."""

    with pool.connection() as connection, connection.transaction():
        auth = authorize(connection, context.actor, context.grant_id)
        auth.require(capability)
        if auth.context.owner_id != context.owner_id:
            raise ActionError("not_found", "business_record_not_found")
        yield connection


def _rows(connection, sql: str, params: tuple) -> list[dict[str, Any]]:  # noqa: ANN001
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(sql, params)
        return list(cursor.fetchall())


def _accounts(connection, space_id) -> dict[str, Account]:  # noqa: ANN001
    accounts = (
        Account(
            bank_account_id=row["bank_account_id"],
            account_id=row["account_id"],
            name=row["nickname"],
            type=row["type"],
            currency=row["currency"],
            covered_through=row["covered_through"],
        )
        for row in _rows(connection, _ACCOUNTS, (space_id,))
    )
    return {account.bank_account_id: account for account in accounts}


def _outcomes(connection, space_id) -> dict[str, LiveOutcome]:  # noqa: ANN001
    return {
        row["line_id"]: LiveOutcome(
            row["line_id"], row["kind"], row["target_id"], row["reason"]
        )
        for row in _rows(connection, _OUTCOMES, (space_id,))
    }


def _movements(
    connection,  # noqa: ANN001
    space_id,  # noqa: ANN001
    lines: list[BankLine],
    accounts: Mapping[str, Account],
    documents: Mapping[str, Document],
    outcomes: Mapping[str, LiveOutcome],
) -> list[Movement]:
    return build_movements(
        lines,
        accounts,
        documents,
        _pairs(connection, space_id, lines),
        outcomes,
        taken_documents(outcomes),
    )


def _lines(connection, space_id, start: date, end: date) -> list[BankLine]:  # noqa: ANN001
    return [
        line_from_row(row) for row in _rows(connection, _LINES, (space_id, start, end))
    ]


def _pairs(connection, space_id, lines: list[BankLine]) -> list[StoredPair]:  # noqa: ANN001
    if not lines:
        return []
    return [
        StoredPair(
            suggestion_id=row["suggestion_id"],
            line_id=row["line_id"],
            target_kind=row["target_kind"],
            target_id=row["target_id"],
            status=row["status"],
            parts=ScoreParts(
                amount_score=Decimal(row["amount_score"]),
                date_score=Decimal(row["date_score"]),
                merchant_score=Decimal(row["merchant_score"]),
            ),
        )
        for row in _rows(connection, _PAIRS, (space_id, [line.id for line in lines]))
    ]


def _store_offers(
    connection,  # noqa: ANN001
    space_id,  # noqa: ANN001
    lines: list[BankLine],
    documents: Mapping[str, Document],
    outcomes: Mapping[str, LiveOutcome],
) -> None:
    stored = _pairs(connection, space_id, lines)
    open_lines = [
        line
        for line in lines
        if str(line.id) not in outcomes and expected_kind(line.amount) is not None
    ]
    if not open_lines:
        return
    window = timedelta(days=MATCH_WINDOW_DAYS)
    start = min(line.occurred_on for line in open_lines) - window
    end = max(line.occurred_on for line in open_lines) + window
    nearby = [
        document
        for document in documents.values()
        if start <= document.occurred_on <= end
    ]
    known = frozenset((pair.line_id, pair.target_id) for pair in stored)
    for line, target, parts in new_offers(
        open_lines, nearby, known, taken_documents(outcomes)
    ):
        connection.execute(
            _OFFER,
            (
                space_id,
                line.id,
                target.kind,
                target.id,
                parts.amount_score,
                parts.date_score,
                parts.merchant_score,
            ),
        )
