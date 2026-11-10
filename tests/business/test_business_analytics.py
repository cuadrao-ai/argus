"""The Business pilot's analytics events, over the real routes and read step.

The PostHog transport is faked and sends run inline, so each test sees exactly
what would leave the server, and when.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from contextlib import contextmanager, nullcontext
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import httpx
import pytest
from argus.api import business_reports
from argus.api.business import require_business_person, require_business_surface
from argus.api.business_drafts import require_drafts
from argus.api.documents import documents_service
from argus.domain.business import analytics as business_analytics
from argus.domain.business.analytics_events import business_hash_for_id
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.actions import Applied, ApproveExpense
from argus.domain.business.reporting_file import RecordsFile
from argus.domain.ingestion.documents.jobs import PreparationJobs
from argus.domain.ingestion.documents.models import ExtractionBatch
from argus.observability import envelope
from argus.observability.analytics_events import TECHNICAL_PROPERTIES
from argus.observability.product_events import actor_hash_for_user
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.business.receipt_stub import ReceiptStub
from tests.business.test_business_api import RECEIPT, Owner, alice  # noqa: F401
from tests.document_reads_support import read_receipt


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


def _keys(*names: str) -> set[str]:
    return TECHNICAL_PROPERTIES | {"business_hash", *names}


class MeteredStub(ReceiptStub):
    """The stub read, with the route receipts the real extractor records."""

    def __init__(self, receipts: list[dict[str, Any]]) -> None:
        super().__init__()
        self.receipts = receipts

    async def extract(self, **kwargs: Any) -> ExtractionBatch:
        batch = await super().extract(**kwargs)
        return batch.model_copy(
            update={"metadata": {**batch.metadata, "route_receipts": self.receipts}}
        )


def _receipt(cost: float | None, prompt: int = 1200, completion: int = 300) -> dict:
    return {
        "task": "document_extraction",
        "tier": "vision",
        "model": "vision-model",
        "outcome": "succeeded",
        "token_usage": {"prompt_tokens": prompt, "completion_tokens": completion},
        "usage_cost_usd": cost,
    }


def _space_id(owner: Owner) -> str:
    return owner.scope().owner.space_id


def test_upload_sends_received_then_read_after_each_commits(
    alice: Owner,  # noqa: F811
    sent: Sent,
) -> None:
    store = documents_service().store
    seen: dict[str, str | None] = {}

    def committed(body: dict[str, Any]) -> None:
        connections = documents_service().hub.connections.list(
            user_id=alice.person, scope=alice.scope().owner
        )
        draft = (
            store.draft(user_id=alice.person, connection_id=connections[0].id)
            if connections
            else None
        )
        seen[body["event"]] = draft.status if draft else None

    sent.on_post(committed)

    uploaded = alice.upload(name="recibo ferretería RNC 101010101.png")

    assert uploaded.status_code == 200, uploaded.text
    assert [body["event"] for body in sent] == [
        "business_document_received",
        "business_document_read",
    ]
    # The capture and the settled read were committed before each send.
    assert seen == {
        "business_document_received": "queued",
        "business_document_read": "review_ready",
    }
    [received] = _events(sent, "business_document_received")
    assert set(received) == _keys("channel", "file_type", "page_count", "size_bucket")
    assert (received["channel"], received["file_type"], received["page_count"]) == (
        "upload",
        "png",
        1,
    )
    assert received["size_bucket"] == business_analytics.size_bucket(len(RECEIPT))
    [read] = _events(sent, "business_document_read")
    assert set(read) == _keys("result", "latency_ms")
    assert read["result"] == "read"
    business_hash = business_hash_for_id(_space_id(alice))
    for body in sent:
        assert body["distinct_id"] == actor_hash_for_user(alice.person)
        assert body["properties"]["business_hash"] == business_hash
    leaked = json.dumps(sent)
    for value in ("101010101", "ferreter", "FERRETERIA", "3450", alice.person):
        assert value not in leaked


def test_the_same_bytes_again_are_not_received_twice(
    alice: Owner,  # noqa: F811
    sent: Sent,
) -> None:
    assert alice.upload().status_code == 200
    assert alice.upload().status_code == 200

    # The second upload replays the saved read: nothing reached the model.
    assert len(_events(sent, "business_document_received")) == 1
    assert len(_events(sent, "business_document_read")) == 1


def test_a_read_with_recorded_usage_reports_its_exact_cost(
    alice: Owner,  # noqa: F811
    sent: Sent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipts = [_receipt(0.0000581), _receipt(0.0004434, prompt=800, completion=100)]
    monkeypatch.setattr(documents_service(), "extractor", MeteredStub(receipts))

    assert alice.upload().status_code == 200

    [read] = _events(sent, "business_document_read")
    assert set(read) == _keys(
        "result",
        "latency_ms",
        "model_tier",
        "input_tokens",
        "output_tokens",
        "cost_micro_usd",
    )
    assert (read["model_tier"], read["input_tokens"], read["output_tokens"]) == (
        "vision",
        2000,
        400,
    )
    # 0.0000581 + 0.0004434 = 0.0005015 USD, 501.5 micro-USD, half to even.
    # Summed in floats it is 0.00050149999... and would round to 501.
    assert read["cost_micro_usd"] == 502


def test_a_read_with_an_unpriced_call_sends_no_cost() -> None:
    usage = business_analytics.read_usage(
        {"route_receipts": [_receipt(0.0002), _receipt(None)]}
    )

    assert "cost_micro_usd" not in usage
    assert usage["input_tokens"] == 2400


def test_a_failed_read_says_why_and_needs_no_review_event(
    alice: Owner,  # noqa: F811
    sent: Sent,
) -> None:
    stub = documents_service().extractor
    stub.failure = "extraction_provider_failed"

    alice.upload()

    [read] = _events(sent, "business_document_read")
    assert set(read) == _keys("result", "latency_ms", "failure_reason")
    assert (read["result"], read["failure_reason"]) == ("failed", "ai_unavailable")
    assert _events(sent, "business_document_needs_review") == []


class Bridge:
    """The canonical Business bridge, answering as the database would."""

    def __init__(
        self, prepared: Callable[[], object], gaps: tuple[str, ...] = ()
    ) -> None:
        self.prepared, self.gaps, self.calls = prepared, gaps, []

    def check_attachment_preparation(self, **_: object) -> None:
        return None

    def prepare_attachment(self, **_: object) -> object:
        return self.prepared()

    def review_gaps(self, **kwargs: object) -> tuple[str, ...]:
        self.calls.append(kwargs["draft_id"])
        return self.gaps


def _read_through(
    alice: Owner,  # noqa: F811
    sent: Sent,
    bridge: Bridge,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run the worker's read step with the canonical bridge in place: the
    upload's own read fails first, then the receipt is queued and read again."""

    service = documents_service()
    service.extractor.failure = "extraction_provider_failed"
    receipt = alice.upload().json()["id"]
    sent.clear()
    service.queue(
        user_id=alice.person,
        connection_id=receipt,
        consent=True,
        scope=alice.scope().owner,
    )
    monkeypatch.setattr(service, "business_actions", bridge)
    PreparationJobs(service).start(user_id=alice.person, connection_id=receipt)
    assert asyncio.run(read_receipt(service, alice.person, receipt)) is not None


def test_an_unsure_read_needs_review_with_its_reason(
    alice: Owner,  # noqa: F811
    sent: Sent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse() -> object:
        raise ActionError("invalid_input", "not_a_receipt")

    _read_through(alice, sent, Bridge(refuse), monkeypatch)

    [read] = _events(sent, "business_document_read")
    assert (read["result"], read["failure_reason"]) == ("unsure", "not_a_receipt")
    [review] = _events(sent, "business_document_needs_review")
    assert set(review) == _keys("reason_codes")
    assert review["reason_codes"] == ["not_a_receipt"]


def test_a_prepared_draft_needs_review_for_every_gap(
    alice: Owner,  # noqa: F811
    sent: Sent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    draft_id = uuid4()
    bridge = Bridge(
        lambda: Applied(outcome="applied", draft_id=draft_id, version=1),
        gaps=("missing_rnc", "missing_itbis"),
    )
    _read_through(alice, sent, bridge, monkeypatch)

    assert bridge.calls == [draft_id]
    [read] = _events(sent, "business_document_read")
    assert read["result"] == "read"
    [review] = _events(sent, "business_document_needs_review")
    assert review["reason_codes"] == ["missing_rnc", "missing_itbis"]


def test_a_listo_draft_sends_no_review_event(
    alice: Owner,  # noqa: F811
    sent: Sent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = Bridge(lambda: Applied(outcome="applied", draft_id=uuid4(), version=1))
    _read_through(alice, sent, bridge, monkeypatch)

    assert _events(sent, "business_document_needs_review") == []


@pytest.mark.parametrize(
    ("token", "region"),
    [("", "us"), ("ph_project_token", "")],
    ids=["blank_token", "blank_region"],
)
def test_a_half_configured_project_reads_nothing_for_an_approval(
    monkeypatch: pytest.MonkeyPatch, token: str, region: str
) -> None:
    """Off means no database read either: the approval's facts are read only
    when there is a project to send them to, which takes a token and a region."""

    monkeypatch.setenv("POSTHOG_PROJECT_TOKEN", token)
    monkeypatch.setenv("POSTHOG_REGION", region)
    monkeypatch.setattr(envelope, "_SENDER", Inline())
    posts: list[object] = []
    monkeypatch.setattr(envelope.httpx, "post", lambda *a, **k: posts.append(a))
    reads: list[object] = []
    monkeypatch.setattr(
        business_analytics, "read_approval", lambda *args: reads.append(args)
    )
    context = SimpleNamespace(actor=SimpleNamespace(space_id=uuid4(), actor_id=uuid4()))

    business_analytics.record_approved(
        None, context, uuid4(), 1, datetime.now(timezone.utc)
    )

    assert reads == []
    assert posts == []


def test_a_saved_read_replayed_by_the_worker_reports_no_read(
    alice: Owner,  # noqa: F811
    sent: Sent,
) -> None:
    """Reading a receipt whose batch is already saved replays it: no provider
    call, so no read to report."""

    service = documents_service()
    receipt = alice.upload().json()["id"]
    assert [body["event"] for body in sent] == [
        "business_document_received",
        "business_document_read",
    ]
    sent.clear()
    service.queue(
        user_id=alice.person,
        connection_id=receipt,
        consent=True,
        scope=alice.scope().owner,
    )
    PreparationJobs(service).start(user_id=alice.person, connection_id=receipt)
    asyncio.run(read_receipt(service, alice.person, receipt))

    assert _events(sent, "business_document_read") == []


def test_a_blank_token_sends_nothing_and_raises_nothing(
    alice: Owner,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POSTHOG_PROJECT_TOKEN", "")
    monkeypatch.setenv("POSTHOG_REGION", "us")
    monkeypatch.setattr(envelope, "_SENDER", Inline())
    posts: list[object] = []
    monkeypatch.setattr(envelope.httpx, "post", lambda *a, **k: posts.append(a))

    assert alice.upload().status_code == 200

    assert posts == []


def test_a_transport_error_does_not_change_the_response(
    alice: Owner,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POSTHOG_PROJECT_TOKEN", "ph_project_token")
    monkeypatch.setenv("POSTHOG_REGION", "us")
    monkeypatch.setattr(envelope, "_SENDER", Inline())

    def down(*_: object, **__: object) -> httpx.Response:
        raise httpx.ConnectError("analytics host down")

    monkeypatch.setattr(envelope.httpx, "post", down)

    uploaded = alice.upload()

    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["status"] == "queued"


def _facts(**values: object) -> dict[str, Any]:
    fiscal = values.pop("fiscal", {})
    known = lambda value: {"state": "known", "value": value}  # noqa: E731
    return {
        **{name: known(value) for name, value in values.items()},
        "fiscal": {name: known(value) for name, value in fiscal.items()},
    }


def test_approval_names_the_fields_a_person_changed_never_their_values(
    sent: Sent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    space, person, draft = uuid4(), uuid4(), uuid4()
    received = datetime(2026, 11, 3, 14, 0, tzinfo=timezone.utc)
    read = _facts(
        amount="3450.00",
        currency="DOP",
        counterparty="FERRETERIA LA ESQUINA SRL",
        fiscal={"rnc": "101010101", "ncf": "B0100000001"},
    )
    approved = _facts(
        amount="3450",
        currency="DOP",
        counterparty="Ferreteria La Esquina",
        fiscal={"rnc": "131313131", "ncf": "B0100000001", "itbis": "526.27"},
    )
    facts = business_analytics.ApprovalFacts(read, received, "recibo")
    monkeypatch.setattr(
        business_analytics, "read_approval", lambda *args: (facts, approved)
    )
    context = SimpleNamespace(actor=SimpleNamespace(space_id=space, actor_id=person))

    business_analytics.record_approved(
        None, context, draft, 3, received + timedelta(minutes=90)
    )

    [approval] = _events(sent, "business_record_approved")
    assert set(approval) == _keys("changed_fields", "changed_count", "seconds_to_approve")
    # 3450.00 and 3450 are the same amount, so only the name and fiscal facts changed.
    assert approval["changed_fields"] == ["counterparty", "rnc", "itbis"]
    assert approval["changed_count"] == 3
    assert approval["seconds_to_approve"] == 5400
    [recorded] = _events(sent, "business_record_recorded")
    assert set(recorded) == _keys("direction", "document_type")
    assert (recorded["direction"], recorded["document_type"]) == ("compra", "recibo")
    for body in sent:
        assert body["distinct_id"] == actor_hash_for_user(str(person))
        assert body["properties"]["business_hash"] == business_hash_for_id(str(space))
    leaked = json.dumps(sent)
    for value in ("131313131", "101010101", "Ferreteria", "526.27", "3450"):
        assert value not in leaked


def test_a_typed_note_approval_has_no_read_to_compare(
    sent: Sent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facts = business_analytics.ApprovalFacts(None, None, "venta")
    monkeypatch.setattr(
        business_analytics, "read_approval", lambda *args: (facts, _facts(kind="income"))
    )
    context = SimpleNamespace(actor=SimpleNamespace(space_id=uuid4(), actor_id=uuid4()))

    business_analytics.record_approved(
        None, context, uuid4(), 2, datetime.now(timezone.utc)
    )

    [approval] = _events(sent, "business_record_approved")
    assert set(approval) == _keys()
    [recorded] = _events(sent, "business_record_recorded")
    assert (recorded["direction"], recorded["document_type"]) == ("venta", "venta")


@pytest.fixture
def reports(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, SimpleNamespace]:
    actor = SimpleNamespace(actor=SimpleNamespace(space_id=uuid4(), actor_id=uuid4()))
    app = FastAPI()
    app.include_router(business_reports.router)
    app.dependency_overrides[require_business_surface] = lambda: None
    app.dependency_overrides[require_drafts] = lambda: SimpleNamespace(
        service=SimpleNamespace(authority=None),
        for_space=lambda request, spaces: actor,
    )
    app.dependency_overrides[require_business_person] = lambda: SimpleNamespace(
        person_id=str(actor.actor.actor_id), spaces=None
    )
    return TestClient(app), actor


def test_an_export_reports_its_format_scope_and_row_count(
    reports: tuple[TestClient, SimpleNamespace],
    sent: Sent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, actor = reports
    built: list[str] = []

    def export_file(authority: object, context: object, choice: object) -> RecordsFile:
        built.append("built")
        return RecordsFile("606.csv", "text/csv", b"a,b\n1,2\n", 7)

    monkeypatch.setattr(business_reports, "export_file", export_file)
    sent.on_post(lambda body: built.append("sent"))

    answer = client.post(
        "/reports/export",
        json={
            "report": {
                "schema_version": 2,
                "filters": {"record_families": ["purchase"], "currencies": ["DOP"]},
            },
            "mode": "dgii",
            "format": "csv",
        },
    )

    assert answer.status_code == 200, answer.text
    assert built == ["built", "sent"]
    [export] = _events(sent, "business_records_exported")
    assert set(export) == _keys("format", "scope", "row_count")
    assert (export["format"], export["scope"], export["row_count"]) == ("csv", "dgii", 7)
    assert sent[0]["distinct_id"] == actor_hash_for_user(str(actor.actor.actor_id))


class _SettlementPool:
    """A pool whose only statement is the approval's settlement update, which
    finds ``rows`` receipts to settle."""

    def __init__(self, rows: int) -> None:
        self.rows = rows

    @contextmanager
    def connection(self):  # noqa: ANN202
        yield SimpleNamespace(
            transaction=lambda: nullcontext(),
            execute=lambda *args: SimpleNamespace(rowcount=self.rows),
        )


@pytest.mark.parametrize(
    ("settled_rows", "approvals"), [(1, 1), (0, 0)], ids=["settled", "lost_the_race"]
)
def test_approval_events_go_only_to_the_request_that_settles_the_receipt(
    monkeypatch: pytest.MonkeyPatch, settled_rows: int, approvals: int
) -> None:
    """Two requests under one key can both see the receipt unsettled and both
    finish the idempotent write; the receipt settles for exactly one of them,
    and only that one reports the approval."""

    from argus.domain.business.actions import approval, plans

    key, draft_id = "k" * 32, uuid4()
    actor = SimpleNamespace(actor_id=uuid4(), space_id=uuid4(), actor_kind="member")
    context = SimpleNamespace(actor=actor, owner_id="owner", scope=None)
    event = SimpleNamespace(
        resolution={"approval_receipt": {"actor_id": str(actor.actor_id), "key": key}}
    )
    tx = SimpleNamespace(
        authorization=SimpleNamespace(require=lambda name: None),
        imports=SimpleNamespace(event=lambda draft: event),
    )
    monkeypatch.setattr(approval, "transaction", lambda *args: nullcontext(tx))
    monkeypatch.setattr(
        plans, "receipt", lambda *args: {"outcome": {"outcome": "outcome_unknown"}}
    )
    service = SimpleNamespace(
        imports=SimpleNamespace(
            _write=lambda *args, **kwargs: {"activity": {"activity_id": uuid4()}},
            clock=lambda: datetime.now(timezone.utc),
        ),
        authority=SimpleNamespace(pool=_SettlementPool(settled_rows)),
    )
    reported: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        business_analytics, "record_approved", lambda *args: reported.append(args)
    )

    outcome = approval.approve(
        service, context, draft_id, ApproveExpense(version=3, action="record_expense"), key
    )

    assert outcome.outcome == "applied", outcome
    assert len(reported) == approvals
