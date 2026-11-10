"""On real local Postgres: the approval and needs-review analytics readers run
their SQL against the schema after the approval committed, a replay sends
nothing again, and a failing analytics read never touches the approval."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from functools import partial
from typing import Any
from uuid import UUID, uuid4

import httpx
import psycopg
import pytest
from argus.domain.business import analytics as business_analytics
from argus.domain.business.analytics_events import business_hash_for_id
from argus.domain.business.contracts.actions import ApproveExpense, CaptureNote
from argus.domain.business.transactions import ActionTransaction
from argus.observability import envelope
from argus.observability.product_events import actor_hash_for_user

from tests import test_business_approval_fiscal_postgres as fiscal

users = fiscal.users
shared_actions = fiscal.shared_actions
actions = fiscal.actions
pytestmark = fiscal.pytestmark


class Inline:
    def submit(self, fn: Callable[[], object]) -> None:
        fn()


class Sent(list):
    """The bodies sent, in order. ``on_post`` hooks run inside each send, to
    see what was committed by then."""

    def __init__(self) -> None:
        super().__init__()
        self.hooks: list[Callable[[dict[str, Any]], None]] = []

    def on_post(self, hook: Callable[[dict[str, Any]], None]) -> None:
        self.hooks.append(hook)


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> Sent:
    """A configured project whose transport records each body, sent inline."""

    bodies = Sent()

    def fake_post(url: str, *, json: dict[str, Any], timeout: float) -> httpx.Response:
        for hook in bodies.hooks:
            hook(json)
        bodies.append(json)
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setenv("POSTHOG_PROJECT_TOKEN", "ph_project_token")
    monkeypatch.setenv("POSTHOG_REGION", "us")
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setattr(envelope.httpx, "post", fake_post)
    monkeypatch.setattr(envelope, "_SENDER", Inline())
    return bodies


def _events(bodies: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    return [body["properties"] for body in bodies if body["event"] == name]


def _sources(service, draft: UUID) -> list[tuple[UUID, str | None, datetime]]:  # noqa: ANN001
    with service.authority.pool.connection() as db:
        return db.execute(
            "select s.id,s.connection_id,s.received_at from public.business_draft_sources l"
            " join public.business_sources s on s.id=l.source_id"
            " where l.draft_id=%s order by s.received_at",
            (draft,),
        ).fetchall()


def _earlier_note(service, context, draft: UUID) -> datetime:  # noqa: ANN001
    """A note that reached the Business two hours before the photo, linked to
    the same draft. Sources are immutable, so the arrival is set at insert."""

    [(_, _, photo_at)] = _sources(service, draft)
    received = photo_at - timedelta(hours=2)
    with service.authority.pool.connection() as db:
        note = db.execute(
            "insert into public.business_sources"
            " (space_id,kind,channel,source_key,text_content,received_at)"
            " values (%s,'message','web',%s,%s,%s) returning id",
            (context.actor.space_id, str(uuid4()), "la nota de antes", received),
        ).fetchone()[0]
        db.execute(
            "insert into public.business_draft_sources (space_id,draft_id,source_id)"
            " values (%s,%s,%s)",
            (context.actor.space_id, draft, note),
        )
    return received


def _receipt_outcome(service, context, key: str) -> str | None:  # noqa: ANN001
    with service.authority.pool.connection() as db:
        row = db.execute(
            "select outcome->>'outcome' from public.business_action_receipts"
            " where space_id=%s and actor_id=%s and idempotency_key=%s",
            (context.actor.space_id, context.actor.actor_id, key),
        ).fetchone()
    return row[0] if row else None


def test_approval_reads_the_corrected_names_and_the_first_arrival(actions, sent):  # noqa: ANN001
    service, context = actions
    read = fiscal.colmado()
    draft, version = fiscal.receipt_draft(service, context, read, "DOP")
    received = _earlier_note(service, context, draft)
    approved = fiscal.reviewed(service, context, draft, version)
    key = str(uuid4())
    settled: list[str | None] = []
    sent.on_post(lambda body: settled.append(_receipt_outcome(service, context, key)))

    before = datetime.now(timezone.utc)
    outcome = service.approve(
        context, draft, ApproveExpense(version=approved, action="record_expense"), key
    )
    after = datetime.now(timezone.utc)

    assert outcome.outcome == "applied", outcome
    assert [body["event"] for body in sent] == [
        "business_record_approved",
        "business_record_recorded",
    ]
    # The approval's receipt was settled before either event left.
    assert settled == ["applied", "applied"]
    [approval] = _events(sent, "business_record_approved")
    # The review set who paid and the Business share; the read's facts stay.
    assert approval["changed_fields"] == ["funding", "business_share"]
    assert approval["changed_count"] == 2
    expected = range(
        int((before - received).total_seconds()),
        int((after - received).total_seconds()) + 1,
    )
    assert approval["seconds_to_approve"] in expected
    [recorded] = _events(sent, "business_record_recorded")
    assert (recorded["direction"], recorded["document_type"]) == ("compra", "recibo")
    for body in sent:
        assert body["distinct_id"] == actor_hash_for_user(str(context.actor.actor_id))
        assert body["properties"]["business_hash"] == business_hash_for_id(
            str(context.actor.space_id)
        )
    leaked = json.dumps(sent)
    for value in (
        fiscal.SUPPLIER,
        fiscal.FILER,
        fiscal.NCF,
        "1180",
        read["merchant"],
        str(context.actor.space_id),
        str(context.actor.actor_id),
        str(draft),
    ):
        assert value not in leaked

    # The same approval again replays the stored outcome and reports nothing again.
    replayed = service.approve(
        context, draft, ApproveExpense(version=approved, action="record_expense"), key
    )
    assert replayed == outcome
    assert len(sent) == 2


def test_a_failing_analytics_read_leaves_the_approval_committed(
    actions,
    sent,
    monkeypatch,  # noqa: ANN001
):
    service, context = actions
    draft, version = fiscal.receipt_draft(service, context, fiscal.colmado(), "DOP")
    approved = fiscal.reviewed(service, context, draft, version)
    rows = ActionTransaction.rows

    def broken(self: ActionTransaction, sql: str, params: Any = None) -> Any:
        if sql.startswith("select actor->>'actor_kind'"):
            raise psycopg.errors.UndefinedColumn("column after_facts does not exist")
        return rows(self, sql, params)

    monkeypatch.setattr(ActionTransaction, "rows", broken)
    key = str(uuid4())

    outcome = service.approve(
        context, draft, ApproveExpense(version=approved, action="record_expense"), key
    )

    assert outcome.outcome == "applied", outcome
    assert _receipt_outcome(service, context, key) == "applied"
    assert fiscal.revisions(service, draft)[-1]["version"] == approved + 1
    assert sent == []


def test_review_gaps_reads_a_prepared_drafts_gaps_from_postgres(actions, sent):  # noqa: ANN001
    service, context = actions
    draft, version = fiscal.receipt_draft(service, context, fiscal.colmado(), "DOP")
    [(_, connection_id, _)] = _sources(service, draft)
    reasons = partial(
        service.review_gaps,
        user_id=context.owner_id,
        connection_id=str(connection_id),
        scope=context.scope,
        draft_id=draft,
    )

    # Read and bound, the draft still waits on who paid, so it is not Listos.
    gaps = reasons()
    assert gaps and gaps[0] != "not_read", gaps
    assert all(isinstance(gap, str) for gap in gaps)
    print("gaps", gaps)
    business_analytics.document_needs_review(
        business_id=str(context.actor.space_id),
        user_id=context.owner_id,
        reasons=reasons,
    )
    [review] = _events(sent, "business_document_needs_review")
    assert review["reason_codes"] == list(gaps)


def test_a_failing_gap_read_sends_nothing_and_raises_nothing(actions, sent):  # noqa: ANN001
    service, context = actions

    def reasons() -> tuple[str, ...]:
        raise psycopg.errors.UndefinedTable("relation does not exist")

    business_analytics.document_needs_review(
        business_id=str(context.actor.space_id),
        user_id=context.owner_id,
        reasons=reasons,
    )

    assert sent == []


def test_a_typed_note_is_received_once(actions, sent):  # noqa: ANN001
    service, context = actions
    key = str(uuid4())
    request = CaptureNote(text="Pagu\u00e9 3450 en la ferreter\u00eda, RNC 101010101")

    first = service.capture(context, request, key)
    again = service.capture(context, request, key)

    assert first.outcome == "applied", first
    assert again == first
    [received] = _events(sent, "business_document_received")
    assert received["channel"] == "note"
    assert "file_type" not in received and "size_bucket" not in received
    leaked = json.dumps(sent)
    for value in ("3450", "ferreter", "101010101", str(context.actor.space_id)):
        assert value not in leaked
