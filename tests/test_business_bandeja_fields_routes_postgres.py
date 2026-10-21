"""Over HTTP, on the real app, Auth and Postgres, the fields the web stops
computing: each receipt's ``bandeja`` membership and the closed counts on the
receipt list, ``has_more`` and ``earlier_count`` on the notes, and on the
dossier ``approval_action``, ``fiscal_inclusion_available`` and
``refund_candidates``. Each count equals the rows flagged, and each gate
agrees with the action it describes."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from argus.domain.ingestion.documents.jobs import PreparationJobs

from tests.business.receipt_stub import DETAILS, PURCHASE
from tests.business.test_business_api import RECEIPT
from tests.test_business_approval_fiscal_postgres import (
    EDITED_SUPPLIER,
    SUPPLIER,
    saved_declaration,
)
from tests.test_business_fiscal_routes_postgres import _post, world  # noqa: F401
from tests.test_business_reading_setting_postgres import (  # noqa: F401
    _reading,
    _upload,
    web,
)
from tests.test_business_review_counts_routes_postgres import EXPENSE, _review
from tests.test_business_scope_switch_routes_postgres import API, PERIOD, _as, _note
from tests.test_business_scope_switch_routes_postgres import (
    pytestmark as _local_supabase,
)

pytestmark = _local_supabase
NONE = {"por_revisar": False, "con_problema": False, "leyendo": False}
PURCHASE_NCF = "B0100000001"
CREDIT_NCF = "B0400000002"


def _get(rig, path: str, headers: dict, **params):  # noqa: ANN001, ANN202
    answer = rig.client.get(f"{API}{path}", params=params, headers=headers)
    assert answer.status_code == 200, (path, answer.text)
    return answer.json()


def _flagged(page: dict) -> dict[str, dict]:
    return {item["id"]: item["bandeja"] for item in page["items"]}


def _counts_match_flags(page: dict, notes: int = 0) -> None:
    """Each Bandeja count equals the sum of its flag over every receipt."""

    flags = list(_flagged(page).values())
    activity = page["activity"]
    assert (
        activity["ready_to_review_count"] == sum(f["por_revisar"] for f in flags) + notes
    )
    assert activity["needs_attention_count"] == sum(f["con_problema"] for f in flags)
    assert activity["reading_count"] == sum(f["leyendo"] for f in flags)


def _fiscal(rnc: str, ncf: str, **declaration) -> dict:
    return {
        "fiscal": {"rnc": rnc, "ncf": ncf, "itbis": None},
        "declaration": saved_declaration(
            category="09",
            services_amount="0.00",
            goods_amount="850.00",
            paid_on="2026-10-09",
            **declaration,
        ),
    }


def _review_with(rig, draft: str, facts: dict, dgii: dict | None, headers: dict):  # noqa: ANN001, ANN202
    version = _get(rig, f"/business/drafts/{draft}/dossier", headers)["version"]
    body = {
        "version": version,
        "facts": {
            name: {"state": "known", "value": value} for name, value in facts.items()
        },
    }
    if dgii is not None:
        body["dgii"] = dgii
    answer = rig.client.patch(
        f"{API}/business/drafts/{draft}/review",
        json=body,
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert answer.status_code == 200, answer.text
    return answer.json()


def test_each_receipt_says_which_bandeja_buckets_it_sits_in_and_the_counts_agree(
    web,  # noqa: ANN001, F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alice = web.alice

    def saved(content: bytes) -> str:
        uploaded = _upload(web, content)
        assert uploaded.status_code == 200, uploaded.text
        return uploaded.json()["id"]

    unread = saved(RECEIPT + b"\x41")
    assert _reading(web, True).status_code == 200
    # Its own merchant and amount, so no earlier read makes it a duplicate.
    web.stub.rows = [{**PURCHASE, "merchant": "PAPELERIA CENTRAL", "amount": "980.50"}]
    web.stub.details = {**DETAILS, "merchant": "PAPELERIA CENTRAL", "total": "980.50"}
    read = saved(RECEIPT + b"\x42")
    web.stub.failure = "extraction_provider_failed"
    failed = saved(RECEIPT + b"\x43")
    web.stub.failure = "encrypted_document"
    unreadable = saved(RECEIPT + b"\x44")
    web.stub.failure = None
    attempts: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "argus.api.documents.document_jobs",
        lambda: PreparationJobs(web.documents, lambda *attempt: attempts.append(attempt)),
    )
    reading = saved(RECEIPT + b"\x45")

    page = _get(web, "/business/receipts", alice.headers, view="all")
    flags = _flagged(page)
    assert flags[unread] == {**NONE, "por_revisar": True}
    assert flags[read] == {**NONE, "por_revisar": True}
    assert flags[failed] == {**NONE, "por_revisar": True, "con_problema": True}
    assert flags[unreadable] == {**NONE, "con_problema": True}
    assert flags[reading] == {**NONE, "leyendo": True}
    _counts_match_flags(page)
    assert (page["activity"]["confirmed_count"], page["activity"]["dismissed_count"]) == (
        0,
        0,
    )
    # The inbox view carries the same counts and flags for the rows it lists.
    inbox = _get(web, "/business/receipts", alice.headers, view="inbox")
    assert inbox["activity"] == page["activity"]
    assert _flagged(inbox) == flags
    assert _get(web, "/business/receipt-activity", alice.headers) == page["activity"]

    # Approving the read receipt's record closes its row: the inbox stops
    # listing it, both views count it as confirmed, and its flags are all off.
    draft = _get(web, f"/business/receipts/{read}", alice.headers)["draft_id"]
    assert draft
    reviewed = _review(web, draft, EXPENSE, alice.headers)
    assert reviewed.status_code == 200, reviewed.text
    approved = _post(
        web,
        f"/business/drafts/{draft}/approve",
        {"version": reviewed.json()["version"], "action": "record_expense"},
        alice.headers,
    )
    assert approved.status_code == 200, approved.text
    for _reload in range(2):
        page = _get(web, "/business/receipts", alice.headers, view="all")
        inbox = _get(web, "/business/receipts", alice.headers, view="inbox")
        assert _flagged(page)[read] == NONE
        assert read not in _flagged(inbox)
        assert inbox["activity"] == page["activity"]
        assert page["activity"]["confirmed_count"] == 1
        assert page["activity"]["dismissed_count"] == 0
        assert page["activity"]["ready_to_review_count"] == 2
        _counts_match_flags(page)
        _counts_match_flags(inbox)


def test_notes_say_how_many_came_before_and_whether_the_page_is_the_whole_list(
    world,  # noqa: ANN001, F811
) -> None:
    alice = world.alice
    first = _note(world, alice, "Pagué 850 en Ferretería Prueba")
    assert first.status_code == 200, first.text
    draft = first.json()["draft_id"]
    version = first.json()["version"]
    for text in ("Con la tarjeta", "Fue el martes"):
        again = world.client.post(
            f"{API}/business/captures",
            json={"text": text, "draft": {"draft_id": draft, "version": version}},
            headers={**alice.headers, "Idempotency-Key": str(uuid4())},
        )
        assert again.status_code == 200, again.text
        version = again.json()["version"]
    other = _note(world, alice, "Gasolina 1200")
    assert other.status_code == 200, other.text

    page = _get(world, "/business/captures", alice.headers, limit=2)
    assert page["has_more"] is True
    assert [(item["text"], item["earlier_count"]) for item in page["items"]] == [
        ("Gasolina 1200", 0),
        ("Fue el martes", 2),
    ]
    whole = _get(world, "/business/captures", alice.headers, limit=50)
    assert whole["has_more"] is False
    assert [(item["text"], item["earlier_count"]) for item in whole["items"]] == [
        ("Gasolina 1200", 0),
        ("Fue el martes", 2),
        ("Con la tarjeta", 1),
        ("Pagué 850 en Ferretería Prueba", 0),
    ]
    # A search narrows the page, never the count of what came before.
    found = _get(world, "/business/captures", alice.headers, q="martes")
    assert found["has_more"] is False
    assert [(item["text"], item["earlier_count"]) for item in found["items"]] == [
        ("Fue el martes", 2)
    ]
    # Exactly a page's worth is not "more".
    exact = _get(world, "/business/captures", alice.headers, limit=4)
    assert (len(exact["items"]), exact["has_more"]) == (4, False)
    # The accountant working in Alice's Business reads the same page.
    assert _get(world, "/business/captures", _as(world.bob, world.grant), limit=2) == page


def test_the_dossier_names_its_approve_action_and_the_606_gate_agrees_with_the_action(
    world,  # noqa: ANN001, F811
) -> None:
    alice, bob = world.alice, world.bob
    accountant = _as(bob, world.grant)
    note = _note(world, alice, "Pagué 850 en Ferretería Prueba")
    assert note.status_code == 200, note.text
    draft = note.json()["draft_id"]
    blank = _get(world, f"/business/drafts/{draft}/dossier", alice.headers)
    assert (blank["approval_available"], blank["approval_action"]) == (False, None)
    assert blank["fiscal_inclusion_available"] is False
    assert blank["refund_candidates"] == []

    reviewed = _review_with(
        world, draft, EXPENSE, _fiscal(SUPPLIER, PURCHASE_NCF), alice.headers
    )
    assert (reviewed["approval_available"], reviewed["approval_action"]) == (
        True,
        "record_expense",
    )
    # Approval is the owner's alone, so the accountant's dossier names no action.
    theirs = _get(world, f"/business/drafts/{draft}/dossier", accountant)
    assert (theirs["approval_available"], theirs["approval_action"]) == (False, None)
    # Not personal yet: nobody may answer the 606 question, and the action agrees.
    assert theirs["fiscal_inclusion_available"] is False
    refused = _post(
        world,
        f"/business/drafts/{draft}/fiscal-inclusion",
        {"version": theirs["version"], "include": True},
        accountant,
    )
    assert (refused.status_code, refused.json()["code"]) == (
        409,
        "business_606_not_applicable",
    )

    approved = _post(
        world,
        f"/business/drafts/{draft}/approve",
        {"version": reviewed["version"], "action": "record_expense"},
        alice.headers,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["approval_action"] is None
    marked = _post(
        world,
        f"/business/drafts/{draft}/personal",
        {"version": approved.json()["version"], "personal": True},
        accountant,
    )
    assert marked.status_code == 200, marked.text
    # Personal with a fiscal number: the accountant may answer, the owner may not.
    assert marked.json()["fiscal_inclusion_available"] is True
    owners = _get(world, f"/business/drafts/{draft}/dossier", alice.headers)
    assert owners["fiscal_inclusion_available"] is False
    denied = _post(
        world,
        f"/business/drafts/{draft}/fiscal-inclusion",
        {"version": owners["version"], "include": True},
        alice.headers,
    )
    assert (denied.status_code, denied.json()["code"]) == (
        403,
        "business_permission_denied",
    )
    answered = _post(
        world,
        f"/business/drafts/{draft}/fiscal-inclusion",
        {"version": owners["version"], "include": True},
        accountant,
    )
    assert answered.status_code == 200, answered.text
    assert answered.json()["include_606"] is True
    # An answer may be changed, so the gate stays open to the accountant.
    assert answered.json()["fiscal_inclusion_available"] is True

    # An income draft, funded by a Business account, takes the income action.
    account = world.client.post(
        f"{API}/business/accounts",
        json={"nickname": "Operating", "type": "checking", "currency": "DOP"},
        headers={**alice.headers, "Idempotency-Key": str(uuid4())},
    )
    assert account.status_code == 201, account.text
    sale = _note(world, alice, "Venta a cliente 2000")
    assert sale.status_code == 200, sale.text
    income = _review_with(
        world,
        sale.json()["draft_id"],
        {
            **EXPENSE,
            "kind": "income",
            "amount": "2000",
            "counterparty": "Cliente Prueba",
            "funding": {"kind": "business_account", "account_id": account.json()["id"]},
        },
        None,
        alice.headers,
    )
    assert (income["approval_available"], income["approval_action"]) == (
        True,
        "record_income",
    )


def test_the_server_picks_the_purchases_a_credit_note_may_refund(world) -> None:  # noqa: ANN001, F811
    alice = world.alice
    purchase = _note(world, alice, "Compra en Ferretería Prueba")
    assert purchase.status_code == 200, purchase.text
    reviewed = _review_with(
        world,
        purchase.json()["draft_id"],
        EXPENSE,
        _fiscal(SUPPLIER, PURCHASE_NCF),
        alice.headers,
    )
    approved = _post(
        world,
        f"/business/drafts/{purchase.json()['draft_id']}/approve",
        {"version": reviewed["version"], "action": "record_expense"},
        alice.headers,
    )
    assert approved.status_code == 200, approved.text
    [expense] = _get(world, "/business/expenses", alice.headers, **PERIOD)["items"]

    credit = _note(world, alice, "Nota de crédito de Ferretería Prueba")
    assert credit.status_code == 200, credit.text
    draft = credit.json()["draft_id"]
    refund = {**EXPENSE, "kind": "refund", "amount": "100", "occurred_on": "2026-10-20"}
    dossier = _review_with(
        world,
        draft,
        refund,
        _fiscal(SUPPLIER, CREDIT_NCF, actual_refund=True),
        alice.headers,
    )
    [candidate] = dossier["refund_candidates"]
    assert candidate["id"] == expense["id"]
    assert candidate["merchant"] == EXPENSE["counterparty"]
    assert candidate["occurred_on"] == EXPENSE["occurred_on"]
    assert Decimal(candidate["amount"]) == Decimal(EXPENSE["amount"])
    assert candidate["currency"] == "DOP"
    # The same list on a reload, and the candidate is a record the 606 will accept.
    assert _get(world, f"/business/drafts/{draft}/dossier", alice.headers)[
        "refund_candidates"
    ] == [candidate]

    # Another supplier's credit note refunds none of this supplier's purchases.
    elsewhere = _review_with(
        world, draft, refund, _fiscal(EDITED_SUPPLIER, CREDIT_NCF), alice.headers
    )
    assert elsewhere["refund_candidates"] == []
    # Past the 30 days the 606 allows, the purchase is no candidate either.
    late = _review_with(
        world,
        draft,
        {**refund, "occurred_on": "2026-11-10"},
        _fiscal(SUPPLIER, CREDIT_NCF),
        alice.headers,
    )
    assert late["refund_candidates"] == []
    # An ordinary expense with an ordinary invoice refunds nothing.
    plain = _review_with(
        world,
        draft,
        {**EXPENSE, "occurred_on": "2026-10-20"},
        _fiscal(SUPPLIER, PURCHASE_NCF),
        alice.headers,
    )
    assert plain["refund_candidates"] == []
