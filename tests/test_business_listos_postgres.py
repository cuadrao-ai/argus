"""Over HTTP, on the real app, Auth and Postgres: one rule puts every open
receipt in Listos or in Necesitan atención with one reason, the Bandeja, Inicio
and the sidebar read one pair of counts, and only the owner approves a named
list of Listos receipts, each on the approval path with its own idempotency."""

from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from email.message import EmailMessage
from types import SimpleNamespace
from uuid import uuid4

import pytest
from argus.api.documents import documents_service
from argus.domain.business.actions import approval
from argus.domain.business.contracts.checks import EcfCheck, EcfVerification
from argus.domain.ingestion.documents.jobs import PreparationJobs
from argus.domain.ingestion.reconcile.service import ReconciliationService
from psycopg import Connection
from psycopg.types.json import Jsonb

from tests import test_business_scope_switch_routes_postgres as scope
from tests import test_financial_accounts_postgres as shared
from tests.business.receipt_stub import DETAILS, PURCHASE, ReceiptStub
from tests.business.test_business_api import RECEIPT
from tests.business.test_business_email_api import WEBHOOK, signed
from tests.business_reading_support import ROUTE
from tests.test_business_approve_unpaid_postgres import _declaration
from tests.test_business_fiscal_routes_postgres import _known
from tests.test_business_reading_setting_postgres import (
    _email,
    _email_runtime,
    _reading,
    _upload,
)
from tests.test_business_scope_switch_routes_postgres import API, PERIOD, _as, _note

pytestmark = scope.pytestmark
people = scope.web
SUPPLIER = "199990021"
OTHER_SUPPLIER = "199990048"
BAD_CHECK_DIGIT = "199990022"
CEDULA = "00100000009"
BAD_CEDULA = "00100000008"
LISTED_BAD_DIGIT = "138888003"
ECF = "E310000000011"
SENDER = "proveedor@example.test"
ROUTE_PATH = "/business/drafts/approve-listos"
LIMIT = 50


@pytest.fixture
def rig(people, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN001, ANN201
    """Alice owns A with reading on; Bob owns B and prepares in A; Dave only
    prepares in A. A stub stands in for the provider's read."""

    documents = documents_service()
    stub = ReceiptStub()
    monkeypatch.setattr(documents, "extractor", stub)
    monkeypatch.setattr(
        documents.business_receipt_consent, "route_resolver", lambda: ROUTE
    )
    monkeypatch.setattr(
        "argus.domain.ingestion.whatsapp.receipt_consent.receipt_provider_route",
        lambda: ROUTE,
    )
    found = SimpleNamespace(
        client=people.client,
        alice=people.alice,
        bob=people.bob,
        dave=people.dave,
        grant_a=people.grant_a,
        grant_d=people.grant_d,
        documents=documents,
        stub=stub,
        reads=iter(range(1, 10_000)),
    )
    assert _reading(found, True).status_code == 200
    yield found
    from argus.api.email_intake import configure_email_intake

    configure_email_intake(None)


def _get(rig, path: str, headers: dict | None = None, **params):  # noqa: ANN001, ANN202
    answer = rig.client.get(
        f"{API}{path}", params=params, headers=headers or rig.alice.headers
    )
    assert answer.status_code == 200, (path, answer.text)
    return answer.json()


def _set_read(rig, index: int, read: dict) -> None:  # noqa: ANN001
    """What the stub reads next: a clean fiscal receipt with its own amount and
    comprobante, so no earlier read repeats it, changed by ``read``."""

    amount = f"{1000 + index}.00"
    details = {
        **DETAILS,
        "merchant": f"FERRETERIA {index}",
        "total": amount,
        "rnc": SUPPLIER,
        "ncf": f"B01{index:08d}",
        "itbis": "18.00",
        **read,
    }
    rig.stub.details = details
    rig.stub.rows = [
        {
            **PURCHASE,
            "merchant": details["merchant"],
            "amount": read.get("amount", amount),
            "currency": details["currency"],
            "occurred_on": details["occurred_on"],
        }
    ]


def _read(rig, read: dict | None = None) -> str:  # noqa: ANN001
    """One upload the stub reads; the receipt's id."""

    index = next(rig.reads)
    _set_read(rig, index, read or {})
    uploaded = _upload(rig, RECEIPT + index.to_bytes(4, "big"))
    assert uploaded.status_code == 200, uploaded.text
    return uploaded.json()["id"]


def _row(rig, receipt_id: str, headers: dict | None = None) -> dict:  # noqa: ANN001
    [row] = [
        item
        for item in _get(rig, "/business/receipts", headers, view="all")["items"]
        if item["id"] == receipt_id
    ]
    return row


def _group(rig, receipt_id: str) -> tuple[str | None, str | None]:  # noqa: ANN001
    found = _row(rig, receipt_id)["bandeja_group"]
    return found["group"], found["reason"]


def _named(rig, receipt_id: str) -> dict:  # noqa: ANN001
    found = _row(rig, receipt_id)["bandeja_group"]
    return {"draft_id": found["draft_id"], "version": found["version"]}


def _named_draft(rig, receipt_id: str) -> str:  # noqa: ANN001
    return _get(rig, f"/business/receipts/{receipt_id}")["draft_id"]


def _counts(rig, headers: dict | None = None) -> tuple[int, int]:  # noqa: ANN001
    """The two numbers, once every read gives them and they equal the rows."""

    page = _get(rig, "/business/receipts", headers, view="inbox")
    activity = _get(rig, "/business/receipt-activity", headers)
    overview = _get(rig, "/business/overview", headers, **PERIOD)
    numbers = (activity["bandeja_listo_count"], activity["bandeja_attention_count"])
    assert page["activity"] == activity
    assert (
        overview["bandeja_listo_count"],
        overview["bandeja_attention_count"],
    ) == numbers
    listed = [row["bandeja_group"]["group"] for row in page["items"]]
    assert listed.count("listo") == numbers[0]
    assert sum(numbers) == activity["pending_review_count"]
    return numbers


def _approve_many(rig, items: list[dict], key: str | None = None, headers=None):  # noqa: ANN001, ANN202
    return rig.client.post(
        f"{API}{ROUTE_PATH}",
        json={"items": items},
        headers={
            **(headers or rig.alice.headers),
            "Idempotency-Key": key or str(uuid4()),
        },
    )


def _results(answer) -> list[tuple[str, str | None]]:  # noqa: ANN001
    assert answer.status_code == 200, answer.text
    return [(item["outcome"], item["code"]) for item in answer.json()["results"]]


def _approve_alone(rig, item: dict, key: str | None = None):  # noqa: ANN001, ANN202
    return rig.client.post(
        f"{API}/business/drafts/{item['draft_id']}/approve",
        json={"version": item["version"], "action": "record_expense"},
        headers={**rig.alice.headers, "Idempotency-Key": key or str(uuid4())},
    )


def _review(rig, item: dict, body: dict):  # noqa: ANN001, ANN202
    answer = rig.client.patch(
        f"{API}/business/drafts/{item['draft_id']}/review",
        json={"version": item["version"], **body},
        headers={**rig.alice.headers, "Idempotency-Key": str(uuid4())},
    )
    assert answer.status_code == 200, answer.text
    return answer.json()


def _fiscal(rig, item: dict, **fiscal) -> dict:  # noqa: ANN001
    dossier = _get(rig, f"/business/drafts/{item['draft_id']}/dossier")
    known = dossier["facts"]["fiscal"]
    values = {
        "rnc": known["rnc"]["value"],
        "ncf": known["ecf"]["value"] or known["ncf"]["value"],
        "itbis": known["itbis"]["value"],
        **fiscal,
    }
    return _review(
        rig,
        item,
        {"dgii": {"fiscal": values, "declaration": _declaration("expense")}},
    )


def _money(rig) -> int:  # noqa: ANN001
    with Connection.connect(shared.DSN) as db:
        return db.execute(
            "select count(*) from public.financial_records where owner_space_id=%s",
            (rig.alice.space_id,),
        ).fetchone()[0]


def _ledger(rig) -> list[str]:  # noqa: ANN001
    """The approval rows the action ledger holds for Alice's Business."""

    with Connection.connect(shared.DSN) as db:
        return [
            row[0]
            for row in db.execute(
                "select command->>'draft_id' from public.business_action_receipts"
                " where space_id=%s and command->>'action'='approve_expense'"
                " order by created_at",
                (rig.alice.space_id,),
            ).fetchall()
        ]


def _state(item: dict) -> tuple:
    with Connection.connect(shared.DSN) as db:
        return db.execute(
            "select state, version from public.financial_import_events where id=%s",
            (item["draft_id"],),
        ).fetchone()


@pytest.mark.parametrize(
    ("read", "reason"),
    [
        pytest.param({}, None, id="a clean read"),
        pytest.param({"ncf": None, "ecf": ECF}, None, id="an e-CF"),
        pytest.param({"rnc": "1-99-99002-1"}, None, id="an RNC printed with dashes"),
        pytest.param({"rnc": CEDULA}, None, id="a good cedula"),
        pytest.param({"itbis": "0.00"}, None, id="ITBIS of zero"),
        pytest.param({"merchant": None}, "missing_merchant", id="no supplier"),
        pytest.param({"merchant": "   "}, "missing_merchant", id="a blank supplier"),
        pytest.param({"occurred_on": None}, "missing_date", id="no date"),
        pytest.param({"currency": None}, "missing_currency", id="no currency"),
        pytest.param({"rnc": None}, "missing_rnc", id="no RNC"),
        pytest.param({"rnc": BAD_CHECK_DIGIT}, "invalid_rnc", id="a bad check digit"),
        pytest.param({"rnc": BAD_CEDULA}, "invalid_rnc", id="a bad cedula"),
        pytest.param({"rnc": "12345"}, "invalid_rnc", id="an RNC of the wrong length"),
        pytest.param({"ncf": None}, "missing_ncf", id="no NCF"),
        pytest.param({"ncf": "B01000008"}, "invalid_ncf", id="a malformed NCF"),
        pytest.param(
            {"ncf": None, "ecf": "E3100000"}, "invalid_ncf", id="a malformed e-CF"
        ),
        pytest.param({"ncf": "", "ecf": ""}, "missing_ncf", id="a blank number"),
        pytest.param({"itbis": None}, "missing_itbis", id="no ITBIS"),
        pytest.param({"currency": "USD"}, "foreign_currency", id="USD"),
        pytest.param({"itbis": "900.00"}, "review_flag", id="ITBIS above the rate"),
        pytest.param({"ncf": "B0400000002"}, "credit_note", id="a credit note"),
    ],
)
def test_the_rule_gives_one_group_and_one_reason(rig, read: dict, reason) -> None:  # noqa: ANN001
    receipt = _read(rig, read)

    group = "attention" if reason else "listo"
    assert _group(rig, receipt) == (group, reason)
    assert _counts(rig) == ((0, 1) if reason else (1, 0))


def test_a_receipt_that_needs_a_person_can_still_be_approved_alone(rig) -> None:  # noqa: ANN001
    for read, reason in (
        ({"ncf": None}, "missing_ncf"),
        ({"currency": "USD"}, "foreign_currency"),
    ):
        receipt = _read(rig, read)
        assert _group(rig, receipt) == ("attention", reason)
        item = _named(rig, receipt)
        approved = _approve_alone(rig, item)
        assert approved.status_code == 200, approved.text
        assert _row(rig, receipt)["status"] == "confirmed"
        assert _group(rig, receipt) == (None, None)
    assert _money(rig) == 2
    assert _counts(rig) == (0, 0)


def test_a_receipt_not_yet_read_has_no_draft_to_approve(rig, monkeypatch) -> None:  # noqa: ANN001
    assert _reading(rig, False).status_code == 200
    unread = _upload(rig, RECEIPT + b"\xa1").json()["id"]
    assert _group(rig, unread) == ("attention", "not_read")
    assert _row(rig, unread)["bandeja_group"]["draft_id"] is None
    assert _reading(rig, True).status_code == 200

    attempts: list = []
    monkeypatch.setattr(
        "argus.api.documents.document_jobs",
        lambda: PreparationJobs(rig.documents, lambda *attempt: attempts.append(attempt)),
    )
    reading = _upload(rig, RECEIPT + b"\xa2").json()["id"]
    assert _group(rig, reading) == ("attention", "reading")
    assert _counts(rig)[0] == 0


def test_an_unfinished_read_never_reaches_listos(rig) -> None:  # noqa: ANN001
    rig.stub.failure = "encrypted_document"
    unreadable = _upload(rig, RECEIPT + b"\xa3").json()["id"]
    assert _group(rig, unreadable) == ("attention", "unreadable")

    rig.stub.failure = "extraction_provider_failed"
    failed = _upload(rig, RECEIPT + b"\xa4").json()["id"]
    assert _group(rig, failed) == ("attention", "ai_unavailable")

    clean = _read(rig)
    rig.stub.details = {**rig.stub.details, "ncf": "B0100000094"}
    rig.stub.rows = [
        {**PURCHASE, "amount": "100.00"},
        {**PURCHASE, "amount": "200.00"},
    ]
    many = _upload(rig, RECEIPT + b"\xa5").json()["id"]
    assert _group(rig, many) == ("attention", "several_purchases")
    assert _group(rig, clean) == ("listo", None)
    assert _counts(rig) == (1, 3)


def test_a_receipt_with_no_amount_needs_a_person(rig) -> None:  # noqa: ANN001
    receipt = _read(rig, {"total": None, "amount": None})
    assert _group(rig, receipt)[0] == "attention"
    assert _counts(rig) == (0, 1)


def test_an_approval_in_flight_is_not_listo(rig) -> None:  # noqa: ANN001
    receipt = _read(rig)
    item = _named(rig, receipt)
    with Connection.connect(shared.DSN) as db:
        db.execute(
            "update public.financial_import_events set state='accepting',"
            " accept_key='in-flight' where id=%s",
            (item["draft_id"],),
        )
    assert _group(rig, receipt) == ("attention", "check_details")
    assert _results(_approve_many(rig, [item])) == [
        ("refused", "business_draft_not_open")
    ]
    assert _money(rig) == 0


def test_a_read_with_an_issue_needs_a_person(rig) -> None:  # noqa: ANN001
    receipt = _read(rig)
    with Connection.connect(shared.DSN) as db:
        db.execute(
            "update public.financial_document_extractions"
            " set draft=jsonb_set(jsonb_set(draft,'{status}','\"needs_attention\"'),"
            " '{error_code}','\"incomplete_extraction\"') where connection_id=%s",
            (receipt,),
        )
    assert _group(rig, receipt) == ("attention", "check_details")


def _checked(rig, item: dict, state: str, encf: str | None) -> None:  # noqa: ANN001
    verification = EcfVerification(
        encf=encf,
        tipo_ecf="31",
        checked_at=datetime.now(timezone.utc),
        checks=(EcfCheck(name="totals_arithmetic", state=state),),
    )
    with Connection.connect(shared.DSN) as db:
        db.execute(
            "update public.financial_import_events"
            " set resolution=jsonb_set(resolution,'{business,ecf_checks}',%s)"
            " where id=%s",
            (Jsonb(verification.model_dump(mode="json")), item["draft_id"]),
        )


@pytest.mark.parametrize(
    ("read", "state", "encf", "reason"),
    [
        pytest.param({"ncf": None, "ecf": ECF}, "verified", ECF, None, id="verified"),
        pytest.param(
            {"ncf": None, "ecf": ECF},
            "failed",
            ECF,
            "ecf_check_failed",
            id="a failed check",
        ),
        pytest.param({}, "verified", ECF, "ecf_check_failed", id="the file says e-CF"),
    ],
)
def test_a_failed_check_on_the_e_cf_needs_a_person(
    rig,  # noqa: ANN001
    read: dict,
    state: str,
    encf: str,
    reason: str | None,
) -> None:
    receipt = _read(rig, read)
    _checked(rig, _named(rig, receipt), state, encf)
    assert _group(rig, receipt) == ("attention" if reason else "listo", reason)


def test_an_edit_moves_a_receipt_between_the_groups(rig) -> None:  # noqa: ANN001
    receipt = _read(rig, {"ncf": None})
    assert _group(rig, receipt) == ("attention", "missing_ncf")

    _fiscal(rig, _named(rig, receipt), ncf="B0100000091")
    assert _group(rig, receipt) == ("listo", None)
    assert _counts(rig) == (1, 0)

    _fiscal(rig, _named(rig, receipt), rnc=BAD_CHECK_DIGIT)
    assert _group(rig, receipt) == ("attention", "invalid_rnc")
    assert _counts(rig) == (0, 1)


def test_a_sale_stays_out_of_the_faster_way(rig) -> None:  # noqa: ANN001
    sale = _read(rig)
    _review(rig, _named(rig, sale), {"document_type": "venta"})
    assert _group(rig, sale) == ("attention", "sale")


def test_a_read_of_several_purchases_is_not_settled_by_an_amount(rig) -> None:  # noqa: ANN001
    receipt = _read(rig)
    item = _named(rig, receipt)
    purchases = [{"index": 1, "amount": "100.00"}, {"index": 2, "amount": "200.00"}]
    with Connection.connect(shared.DSN) as db:
        db.execute(
            "update public.financial_import_events"
            " set resolution=jsonb_set(resolution,'{business,read_purchases}',%s)"
            " where id=%s",
            (Jsonb(purchases), item["draft_id"]),
        )
    assert _get(rig, f"/business/drafts/{item['draft_id']}/dossier")["blockers"] == []

    assert _group(rig, receipt) == ("attention", "several_purchases")
    assert _results(_approve_many(rig, [item])) == [("refused", "not_listo")]
    assert _money(rig) == 0


def test_an_open_question_needs_a_person(rig) -> None:  # noqa: ANN001
    receipt = _read(rig)
    item = _named(rig, receipt)
    with Connection.connect(shared.DSN) as db:
        db.execute(
            "insert into public.business_questions"
            " (space_id,draft_id,field,asked_of,channel,state,prompt,allowed_answers)"
            " values (%s,%s,'funding','owner','web','open','¿Cómo se pagó?',"
            " array['known','owner_does_not_know'])",
            (rig.alice.space_id, item["draft_id"]),
        )
    assert _group(rig, receipt) == ("attention", "blocked")
    assert _results(_approve_many(rig, [item])) == [
        ("refused", "business_questions_unresolved")
    ]


def _mark_personal(rig, item: dict, personal: bool) -> dict:  # noqa: ANN001
    answer = rig.client.post(
        f"{API}/business/drafts/{item['draft_id']}/personal",
        json={"version": item["version"], "personal": personal},
        headers={**rig.alice.headers, "Idempotency-Key": str(uuid4())},
    )
    assert answer.status_code == 200, answer.text
    return answer.json()


def test_a_personal_mark_keeps_a_receipt_out_of_listos(rig) -> None:  # noqa: ANN001
    receipt = _read(rig)
    item = _named(rig, receipt)
    marked = _mark_personal(rig, item, True)

    assert _group(rig, receipt) == ("attention", "personal")
    listed = {"draft_id": item["draft_id"], "version": marked["version"]}
    assert _results(_approve_many(rig, [listed])) == [("refused", "not_listo")]
    assert _money(rig) == 0

    _mark_personal(rig, listed, False)
    assert _group(rig, receipt) == ("listo", None)


def test_a_repeat_needs_a_person_until_a_person_settles_it(rig) -> None:  # noqa: ANN001
    first = _read(rig)
    original = rig.stub.details
    rows = rig.stub.rows
    rig.stub.details, rig.stub.rows = {**original, "ncf": "B0100000092"}, rows
    repeat = _upload(rig, RECEIPT + b"\xa6").json()["id"]
    assert _group(rig, first) == ("listo", None)
    assert _group(rig, repeat) == ("attention", "duplicate")

    named = _named(rig, repeat)
    settled = rig.client.post(
        f"{API}/business/drafts/{named['draft_id']}/duplicate-resolution",
        json={
            "version": named["version"],
            "other_draft_id": _named(rig, first)["draft_id"],
            "other_version": _named(rig, first)["version"],
            "decision": "different_purchase",
        },
        headers={**rig.alice.headers, "Idempotency-Key": str(uuid4())},
    )
    assert settled.status_code == 200, settled.text
    assert _group(rig, repeat) == ("listo", None)
    assert _counts(rig) == (2, 0)


def test_one_comprobante_on_two_receipts_needs_a_person_on_both(rig) -> None:  # noqa: ANN001
    first = _read(rig, {"ncf": "B0100000093"})
    second = _read(rig, {"ncf": "B0100000093"})
    other_supplier = _read(rig, {"ncf": "B0100000093", "rnc": OTHER_SUPPLIER})

    assert _group(rig, first) == ("attention", "duplicate")
    assert _group(rig, second) == ("attention", "duplicate")
    assert _group(rig, other_supplier) == ("listo", None)

    assert _approve_alone(rig, _named(rig, first)).status_code == 200
    assert _group(rig, second) == ("attention", "duplicate")
    refused = _approve_alone(rig, _named(rig, second))
    assert (refused.status_code, refused.json()["code"]) == (
        422,
        "duplicate_comprobante",
    )
    [result] = _approve_many(rig, [_named(rig, second)]).json()["results"]
    assert (result["outcome"], result["code"]) == ("refused", "duplicate_comprobante")
    assert result["existing_record_id"] == _named_draft(rig, first)


def test_a_sale_with_the_same_comprobante_is_no_repeat_of_a_purchase(rig) -> None:  # noqa: ANN001
    purchase = _read(rig, {"ncf": "B0100000095"})
    sale = _read(rig, {"ncf": "B0100000095"})
    assert _group(rig, purchase) == ("attention", "duplicate")

    _review(rig, _named(rig, sale), {"document_type": "venta"})
    assert _group(rig, sale) == ("attention", "sale")
    assert _group(rig, purchase) == ("listo", None)


def test_a_number_the_register_lists_is_valid_as_the_606_reads_it(rig) -> None:  # noqa: ANN001
    with Connection.connect(shared.DSN) as db:
        db.execute(
            "insert into public.dgii_rnc (rnc, name, trade_name, status, file_date)"
            " values (%s, 'FERRETERIA REGISTRADA', 'FERRETERIA', 'ACTIVO', %s)",
            (LISTED_BAD_DIGIT, date(2026, 10, 17)),
        )
    try:
        receipt = _read(rig, {"rnc": LISTED_BAD_DIGIT})
        assert _group(rig, receipt) == ("listo", None)
    finally:
        with Connection.connect(shared.DSN) as db:
            db.execute("delete from public.dgii_rnc where rnc=%s", (LISTED_BAD_DIGIT,))
    assert _group(rig, receipt) == ("attention", "invalid_rnc")


def _delivered(rig, monkeypatch, content: bytes):  # noqa: ANN001, ANN202
    """One email through the signed webhook and the worker; its receipt and
    the runtime that holds the sender rules."""

    index = next(rig.reads)
    _set_read(rig, index, {})
    runtime, route = _email_runtime(rig, monkeypatch, _email(content))
    body = json.dumps(
        {
            "type": "email.received",
            "data": {"email_id": str(uuid4()), "to": [route.recipient]},
        }
    ).encode()
    received = rig.client.post(WEBHOOK, content=body, headers=signed(body))
    assert received.status_code == 202, received.text
    assert asyncio.run(runtime.next())
    items = _get(rig, "/business/receipts", view="all")["items"]
    [attachment] = [row for row in items if not row["email_original"]]
    [original] = [row for row in items if row["email_original"]]
    return runtime, attachment["id"], original["id"]


def test_an_email_is_listo_only_from_a_verified_sender(rig, monkeypatch) -> None:  # noqa: ANN001
    runtime, receipt, original = _delivered(rig, monkeypatch, RECEIPT + b"\xa7")
    assert _row(rig, receipt)["channel"] == "email"
    assert _group(rig, receipt) == ("listo", None)
    assert _group(rig, original) == (None, None)
    assert _counts(rig) == (1, 0)
    item = _named(rig, receipt)

    [rule] = runtime.store.list_senders(rig.alice.space_id)
    runtime.store.remove_sender(rig.alice.space_id, rule.id)
    assert _group(rig, receipt) == ("attention", "unverified_sender")
    assert _counts(rig) == (0, 1)
    # The sender changed and the draft did not: its version still matches.
    assert _results(_approve_many(rig, [item])) == [("refused", "not_listo")]
    assert _state(item)[0] == "open"
    assert _money(rig) == 0

    runtime.store.upsert_sender(rig.alice.space_id, "address", SENDER, "authorized")
    assert _group(rig, receipt) == ("listo", None)
    assert _results(_approve_many(rig, [item])) == [("applied", None)]
    assert _money(rig) == 1


def test_the_claim_reads_the_rule_again(rig, monkeypatch) -> None:  # noqa: ANN001
    runtime, receipt, _ = _delivered(rig, monkeypatch, RECEIPT + b"\xa8")
    item = _named(rig, receipt)
    reviewed = approval.reviewed_request

    def sender_removed_after_the_first_read(*args, **options):  # noqa: ANN002, ANN003, ANN202
        request = reviewed(*args, **options)
        [rule] = runtime.store.list_senders(rig.alice.space_id)
        runtime.store.remove_sender(rig.alice.space_id, rule.id)
        return request

    monkeypatch.setattr(approval, "reviewed_request", sender_removed_after_the_first_read)

    assert _results(_approve_many(rig, [item])) == [("refused", "not_listo")]
    assert _state(item)[0] == "open"
    assert _money(rig) == 0


def test_the_three_reads_agree_for_every_row_the_bandeja_lists(rig, monkeypatch) -> None:  # noqa: ANN001
    assert _counts(rig) == (0, 0)
    listo = _read(rig)
    assert _counts(rig) == (1, 0)
    _read(rig, {"ncf": None})
    assert _counts(rig) == (1, 1)

    note = _note(rig, rig.alice, "Pagué 850 en Ferretería Prueba")
    assert note.status_code == 200, note.text
    assert _counts(rig) == (1, 2)
    # The accountant working in Alice's Business reads the same two numbers.
    assert _counts(rig, _as(rig.bob, rig.grant_a)) == (1, 2)

    message = EmailMessage()
    message["From"] = SENDER
    message["Subject"] = "Sin adjunto"
    message.add_attachment(
        b"MZ", maintype="application", subtype="octet-stream", filename="virus.exe"
    )
    runtime, route = _email_runtime(rig, monkeypatch, message.as_bytes())
    body = json.dumps(
        {
            "type": "email.received",
            "data": {"email_id": str(uuid4()), "to": [route.recipient]},
        }
    ).encode()
    assert rig.client.post(WEBHOOK, content=body, headers=signed(body)).status_code == 202
    assert asyncio.run(runtime.next())
    assert _counts(rig) == (1, 3)

    assert _results(_approve_many(rig, [_named(rig, listo)])) == [("applied", None)]
    assert _counts(rig) == (0, 3)


def test_a_read_alone_never_approves(rig) -> None:  # noqa: ANN001
    receipt = _read(rig)
    assert _group(rig, receipt) == ("listo", None)
    _get(rig, "/business/receipts")
    _get(rig, "/business/overview", **PERIOD)
    assert _money(rig) == 0
    assert _ledger(rig) == []
    assert _row(rig, receipt)["status"] == "review_ready"


def test_the_owner_approves_a_named_list_and_each_record_keeps_its_audit(rig) -> None:  # noqa: ANN001
    receipts = [_read(rig) for _ in range(3)]
    left_open = _read(rig)
    items = [_named(rig, receipt) for receipt in receipts]

    answer = _approve_many(rig, items)

    assert _results(answer) == [("applied", None)] * 3
    results = answer.json()["results"]
    assert [item["draft_id"] for item in results] == [i["draft_id"] for i in items]
    assert len({item["activity_id"] for item in results}) == 3
    assert _money(rig) == 3
    assert _row(rig, left_open)["status"] == "review_ready"
    assert _counts(rig) == (1, 0)
    assert sorted(_ledger(rig)) == sorted(item["draft_id"] for item in items)
    for receipt, item, result in zip(receipts, items, results, strict=True):
        assert _row(rig, receipt)["status"] == "confirmed"
        dossier = _get(rig, f"/business/drafts/{item['draft_id']}/dossier")
        assert dossier["approval_result"]["status"] == "recorded"
        assert dossier["approval_result"]["activity_id"] == result["activity_id"]
        assert dossier["approval_result"]["actor"]["actor_id"] == rig.alice.id


def test_a_replay_answers_the_same_and_never_doubles_money(rig) -> None:  # noqa: ANN001
    items = [_named(rig, _read(rig)) for _ in range(2)]
    refused = _named(rig, _read(rig, {"ncf": None}))
    key = str(uuid4())

    first = _approve_many(rig, [*items, refused], key)
    assert _results(first) == [
        ("applied", None),
        ("applied", None),
        ("refused", "not_listo"),
    ]
    assert _money(rig) == 2
    ledger = _ledger(rig)

    again = _approve_many(rig, [*items, refused], key)
    assert again.json() == first.json()
    # Part of the same list, in another order, is the same answer item by item.
    part = _approve_many(rig, [items[1]], key)
    assert part.json()["results"] == [first.json()["results"][1]]
    assert _money(rig) == 2
    assert _ledger(rig) == ledger

    # A new key is a new request: the version it names is gone, and at the
    # current version the record is already recorded. Neither posts money.
    assert _results(_approve_many(rig, [items[0]])) == [("refused", "stale_version")]
    current = _state(items[0])[1]
    assert _results(_approve_many(rig, [{**items[0], "version": current}])) == [
        ("refused", "recorded_correction_unsupported")
    ]
    assert _money(rig) == 2


def test_the_same_key_with_another_version_is_a_conflict(rig) -> None:  # noqa: ANN001
    item = _named(rig, _read(rig, {"ncf": None}))
    key = str(uuid4())
    assert _results(_approve_many(rig, [item], key)) == [("refused", "not_listo")]

    moved = {**item, "version": item["version"] + 1}
    assert _results(_approve_many(rig, [moved], key)) == [
        ("refused", "business_action_conflict")
    ]


def test_a_concurrent_single_approve_records_each_receipt_once(rig) -> None:  # noqa: ANN001
    items = [_named(rig, _read(rig)) for _ in range(4)]
    key = str(uuid4())
    calls = [
        lambda: _approve_many(rig, items, key),
        lambda: _approve_many(rig, items, key),
        lambda: _approve_alone(rig, items[1]),
        lambda: _approve_alone(rig, items[2]),
        lambda: _approve_many(rig, items[2:]),
    ]
    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        answers = [future.result() for future in [pool.submit(call) for call in calls]]

    assert all(answer.status_code in (200, 409, 422) for answer in answers), [
        answer.text for answer in answers
    ]
    assert _money(rig) == 4
    for item in items:
        assert _state(item)[0] == "accepted"
    activities = {
        result["draft_id"]: result["activity_id"]
        for answer in answers[:2]
        for result in answer.json()["results"]
        if result["outcome"] == "applied"
    }
    assert len(set(activities.values())) == len(activities)


def test_a_note_with_every_fact_is_no_receipt_to_approve_in_a_list(rig) -> None:  # noqa: ANN001
    note = _note(rig, rig.alice, "Pagué 1180 en Ferretería Prueba").json()
    item = {"draft_id": note["draft_id"], "version": note["version"]}
    dossier = _get(rig, f"/business/drafts/{item['draft_id']}/dossier")
    item["version"] = dossier["version"]
    reviewed = _review(
        rig,
        item,
        {
            "facts": _known(
                {
                    "kind": "expense",
                    "amount": "1180.00",
                    "currency": "DOP",
                    "occurred_on": "2026-10-06",
                    "counterparty": "Ferretería Prueba",
                }
            ),
            "dgii": {
                "fiscal": {"rnc": SUPPLIER, "ncf": "B0100000096", "itbis": "18.00"},
                "declaration": _declaration("expense"),
            },
        },
    )
    assert reviewed["approval_available"] is True

    named = {**item, "version": reviewed["version"]}
    assert _results(_approve_many(rig, [named])) == [("refused", "not_listo")]
    assert _money(rig) == 0
    assert _approve_alone(rig, named).status_code == 200
    assert _money(rig) == 1


def test_a_receipt_on_two_drafts_is_not_listo(rig) -> None:  # noqa: ANN001
    first, second = _read(rig), _read(rig)
    one, other = _named(rig, first), _named(rig, second)
    with Connection.connect(shared.DSN) as db:
        db.execute(
            "insert into public.business_draft_sources (space_id,draft_id,source_id)"
            " select space_id,%s,source_id from public.business_draft_sources"
            " where draft_id=%s",
            (one["draft_id"], other["draft_id"]),
        )

    assert _group(rig, first) == ("attention", "check_details")
    assert _group(rig, second) == ("attention", "check_details")
    assert _results(_approve_many(rig, [one, other])) == [
        ("refused", "not_listo"),
        ("refused", "not_listo"),
    ]
    assert _money(rig) == 0


def test_a_receipt_edited_after_listing_is_refused_and_the_rest_go(rig) -> None:  # noqa: ANN001
    kept = [_read(rig) for _ in range(2)]
    edited = _read(rig)
    listed = [_named(rig, receipt) for receipt in [kept[0], edited, kept[1]]]

    _fiscal(rig, listed[1], rnc=OTHER_SUPPLIER)
    assert _group(rig, edited) == ("listo", None)

    assert _results(_approve_many(rig, listed)) == [
        ("applied", None),
        ("refused", "stale_version"),
        ("applied", None),
    ]
    assert _money(rig) == 2
    assert _group(rig, edited) == ("listo", None)
    assert _counts(rig) == (1, 0)


def test_one_failure_among_many_leaves_the_rest(rig) -> None:  # noqa: ANN001
    good = [_read(rig) for _ in range(2)]
    usd = _read(rig, {"currency": "USD"})
    note = _note(rig, rig.alice, "Pagué 850 en Ferretería Prueba").json()
    missing = {"draft_id": str(uuid4()), "version": 1}
    items = [
        _named(rig, good[0]),
        _named(rig, usd),
        {"draft_id": note["draft_id"], "version": note["version"]},
        missing,
        _named(rig, good[1]),
    ]

    assert _results(_approve_many(rig, items)) == [
        ("applied", None),
        ("refused", "not_listo"),
        ("refused", "fact_required"),
        ("refused", "business_record_not_found"),
        ("applied", None),
    ]
    assert _money(rig) == 2
    assert _group(rig, usd) == ("attention", "foreign_currency")


def test_a_money_write_that_fails_settles_on_replay_and_the_rest_go(
    rig,  # noqa: ANN001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    items = [_named(rig, _read(rig)) for _ in range(3)]
    write = ReconciliationService._write
    failed: list[str] = []

    def lost_on_the_second(self, user_id, event, *rest, **options):  # noqa: ANN001, ANN002, ANN003, ANN202
        if event.id == items[1]["draft_id"] and not failed:
            failed.append(event.id)
            raise ConnectionError("the write's answer was lost")
        return write(self, user_id, event, *rest, **options)

    monkeypatch.setattr(ReconciliationService, "_write", lost_on_the_second)
    key = str(uuid4())

    assert _results(_approve_many(rig, items, key)) == [
        ("applied", None),
        ("outcome_unknown", "business_recording_unsettled"),
        ("applied", None),
    ]
    assert _state(items[1])[0] == "accepting"
    assert _money(rig) == 2

    assert _results(_approve_many(rig, items, key)) == [("applied", None)] * 3
    assert _state(items[1])[0] == "accepted"
    assert _money(rig) == 3


def test_an_item_that_crashes_stays_with_that_item(
    rig,  # noqa: ANN001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    items = [_named(rig, _read(rig)) for _ in range(2)]
    approve = approval.approve

    def crash_on_the_first(service, context, draft_id, *rest, **options):  # noqa: ANN001, ANN002, ANN003, ANN202
        if str(draft_id) == items[0]["draft_id"]:
            raise RuntimeError("synthetic crash")
        return approve(service, context, draft_id, *rest, **options)

    monkeypatch.setattr(approval, "approve", crash_on_the_first)

    assert _results(_approve_many(rig, items)) == [
        ("outcome_unknown", "business_recording_unsettled"),
        ("applied", None),
    ]
    assert _state(items[0])[0] == "open"
    assert _money(rig) == 1


def test_only_the_owner_may_approve_a_list(rig) -> None:  # noqa: ANN001
    item = _named(rig, _read(rig))

    for person, grant in ((rig.bob, rig.grant_a), (rig.dave, rig.grant_d)):
        answer = _approve_many(rig, [item], headers=_as(person, grant))
        assert (answer.status_code, answer.json()["code"]) == (
            403,
            "business_permission_denied",
        )
    assert _state(item)[0] == "open"
    assert _money(rig) == 0
    assert _ledger(rig) == []


def test_a_draft_of_another_business_is_missing(rig) -> None:  # noqa: ANN001
    mine = _named(rig, _read(rig))
    theirs = _note(rig, rig.bob, "Una nota de otro negocio").json()
    foreign = {"draft_id": theirs["draft_id"], "version": theirs["version"]}

    assert _results(_approve_many(rig, [foreign, mine])) == [
        ("refused", "business_record_not_found"),
        ("applied", None),
    ]
    # Bob, in his own Business, cannot reach Alice's record either.
    other = _named(rig, _read(rig))
    answer = _approve_many(rig, [other], headers=rig.bob.headers)
    assert _results(answer) == [("refused", "business_record_not_found")]
    assert _state(other)[0] == "open"
    assert _ledger(rig) == [mine["draft_id"]]


def test_the_list_limit_is_stated_and_held(rig) -> None:  # noqa: ANN001
    unknown = [{"draft_id": str(uuid4()), "version": 1} for _ in range(LIMIT + 1)]

    assert len(_results(_approve_many(rig, unknown[:LIMIT]))) == LIMIT
    confirmed = {**unknown[0], "approve_anyway": True}
    for body in (unknown, [], [unknown[0], unknown[0]], [confirmed]):
        refused = _approve_many(rig, body)
        assert (refused.status_code, refused.json()["code"]) == (422, "validation_error")
    assert _ledger(rig) == []

    schema = rig.client.get("/openapi.json").json()["components"]["schemas"]
    assert schema["ApproveListos"]["properties"]["items"]["maxItems"] == LIMIT


def test_the_list_needs_an_idempotency_key(rig) -> None:  # noqa: ANN001
    item = _named(rig, _read(rig))
    answer = rig.client.post(
        f"{API}{ROUTE_PATH}", json={"items": [item]}, headers=rig.alice.headers
    )
    assert answer.status_code == 400, answer.text
    assert _money(rig) == 0
