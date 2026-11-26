"""Over HTTP, on the real app, Auth and Postgres, the fields the web stops
computing: each receipt's ``bandeja`` membership and the closed counts on the
receipt list, ``has_more`` and ``earlier_count`` on the notes, and on the
dossier ``approval_action``, ``fiscal_inclusion_available`` and
``refund_candidates``. Each count equals the rows flagged, and each gate
agrees with the action it describes."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from argus.api import whatsapp as whatsapp_api
from argus.api.documents import documents_service
from argus.api.email_intake import configure_email_intake
from argus.domain.business.contracts.actions import ProposeActivity
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.contracts.dossier import AttachmentSource
from argus.domain.business.contracts.facts import BusinessFactPatch
from faker import Faker
from psycopg import Connection

from tests.business.receipt_stub import receipt_details, receipt_purchase
from tests.business.test_business_api import RECEIPT
from tests.business_accept_support import accepting
from tests.document_reads_support import leave_reads_waiting, read_receipt
from tests.ingestion.whatsapp_support import ALICE_PHONE
from tests.test_business_actions_postgres import prepare
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
from tests.test_business_receipt_uploader_routes_postgres import (  # noqa: F401
    _emailed,
    phone,
)
from tests.test_business_review_counts_routes_postgres import EXPENSE, _review
from tests.test_business_scope_switch_routes_postgres import API, _as, _note
from tests.test_business_scope_switch_routes_postgres import (
    pytestmark as _local_supabase,
)
from tests.test_financial_accounts_postgres import DSN

pytestmark = _local_supabase
NONE = {"por_revisar": False, "con_problema": False, "leyendo": False}
PURCHASE_NCF = "B0100000001"
CREDIT_NCF = "B0400000002"


@pytest.fixture(autouse=True)
def _typed_notes(typed_notes_on: None) -> None:
    """These flows start a draft by typing a note: typed notes on."""


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


@pytest.mark.parametrize(("channel", "file_before_message"), [
    ("web", False), ("email", False), ("whatsapp", False), ("whatsapp", True),
])
def test_receipt_summary_and_dossier_report_one_origin(
    web,  # noqa: ANN001, F811
    faker: Faker,
    channel: str,
    file_before_message: bool,
    phone,  # noqa: ANN001, F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _reading(web, True).status_code == 200
    content = RECEIPT + faker.binary(length=16)
    if channel == "web" or file_before_message:
        uploaded = _upload(web, content)
        assert uploaded.status_code == 200, uploaded.text
        if file_before_message:
            _capture_stored_file(web.alice.id, uploaded.json()["id"], faker)
    elif channel == "email":
        _emailed(web, monkeypatch, content)
        configure_email_intake(None)
    else:
        phone(ALICE_PHONE, content)
        [saved] = _get(web, "/business/receipts", web.alice.headers, view="all")["items"]
        asyncio.run(read_receipt(web.documents, web.alice.id, saved["id"]))
        whatsapp_api.configure_whatsapp(None)

    headers = web.alice.headers
    page = _get(web, "/business/receipts", headers, view="all")
    [summary] = [item for item in page["items"] if item["media_type"] == "image/png"]
    receipt_id = summary["id"]
    detail = _get(web, f"/business/receipts/{receipt_id}", headers)
    draft = detail["draft_id"]
    dossier = _get(web, f"/business/drafts/{draft}/dossier", headers)
    assert dossier["original_connection_id"] == receipt_id
    expected_sender = (
        "email:proveedor@example.test" if channel == "email" else f"member:{web.alice.id}"
    )
    filename = "whatsapp-image" if channel == "whatsapp" and not file_before_message else "recibo.png"
    origin = {
        key: summary[key]
        for key in ("channel", "sent_by", "received_at", "filename", "size_bytes")
    }
    assert (
        origin["channel"],
        origin["sent_by"]["id"],
        origin["filename"],
        origin["size_bytes"],
    ) == (channel, expected_sender, filename, len(content))
    assert origin["received_at"]
    if file_before_message:
        assert origin["received_at"] == uploaded.json()["received_at"]
    assert dossier["origin"] == origin == {key: detail[key] for key in origin}
    title = dossier["facts"]["counterparty"]["value"]
    assert summary["title"] == detail["title"] == dossier["title"] == title

    _check_annotated_origin(web, draft, dossier, headers, faker, channel)


def _capture_stored_file(owner: UUID, receipt: str, faker: Faker) -> None:
    """A stored capture can identify the sender after the file was saved."""
    sender = uuid4().bytes + uuid4().bytes
    with Connection.connect(DSN) as db:
        link, = db.execute(
            "insert into public.whatsapp_sender_links"
            "(destination_owner_id,wa_id_hash,last4,reply_language,status,linked_at)"
            " values(%s,%s,%s,'es-419','active',now()) returning id",
            (owner, sender, faker.numerify("####")),
        ).fetchone()
        db.execute(
            "insert into public.whatsapp_inbound_messages"
            "(provider_message_key,sender_hash,destination_owner_id,status,connection_id,"
            "sender_link_id,received_at,updated_at) values(%s,%s,%s,'captured',%s,%s,now(),now())",
            (uuid4().bytes + uuid4().bytes, sender, owner, receipt, link),
        )


def _check_annotated_origin(
    rig, draft: str, dossier: dict, headers: dict, faker: Faker, channel: str
) -> None:  # noqa: ANN001
    note = rig.client.put(
        f"{API}/business/drafts/{draft}/current-note",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"expected_version": dossier["version"], "note": faker.sentence()},
    )
    assert note.status_code == 200, note.text
    edited = note.json()["dossier"]
    capture = rig.client.post(
        f"{API}/business/captures",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "draft": {"draft_id": draft, "version": edited["version"]},
            "text": faker.sentence(),
        },
    )
    assert capture.status_code == 200, capture.text
    for response in (edited, capture.json()):
        assert (response["origin"], response["title"]) == (
            dossier["origin"],
            dossier["title"],
        )
        file = next(
            s
            for s in response["sources"]
            if s.get("connection_id") == dossier["original_connection_id"]
        )
        assert file["channel"] == response["origin"]["channel"] == channel


def test_a_granted_member_sees_the_stored_attachment_channel_without_a_webhook_row(
    world,  # noqa: ANN001, F811
    faker: Faker,
) -> None:
    """A stored attachment can identify its channel even without a capture ledger entry."""
    saved = _upload(world, RECEIPT + faker.binary(length=16))
    assert saved.status_code == 200, saved.text
    file = saved.json()
    service = documents_service().business_actions
    actor = service.resolve_actor(
        TrustedActor(
            space_id=world.alice.space_id, actor_id=world.alice.id, actor_kind="member"
        )
    )
    source = service.record_source(
        actor,
        f"attachment:{file['id']}",
        AttachmentSource(
            id=uuid4(),
            connection_id=UUID(file["id"]),
            channel="whatsapp",
            filename=file["filename"],
            media_type=file["media_type"],
            received_at=file["received_at"],
        ),
    )
    command = ProposeActivity(
        source_ids=(source,),
        facts=BusinessFactPatch(
            counterparty={"state": "known", "value": faker.company()}
        ),
    )
    key, lease = prepare(service, actor, [command])
    result = service.execute(actor, key, 0, lease=lease)
    assert result.outcome == "applied", result
    draft = str(result.draft_id)
    headers = _as(world.bob, world.grant)
    page = _get(world, "/business/receipts", headers, view="all")
    [row] = page["items"]
    dossier = _get(world, f"/business/drafts/{draft}/dossier", headers)
    assert row["channel"] == dossier["origin"]["channel"] == "whatsapp"
    assert row["id"] == dossier["original_connection_id"] == file["id"]
    assert dossier["sources"][0]["channel"] == "whatsapp"
    _check_annotated_origin(world, draft, dossier, headers, faker, "whatsapp")


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
    web.stub.rows = [{**receipt_purchase(), "merchant": "PAPELERIA CENTRAL", "amount": "980.50"}]
    web.stub.details = {**receipt_details(), "merchant": "PAPELERIA CENTRAL", "total": "980.50"}
    read = saved(RECEIPT + b"\x42")
    web.stub.failure = "extraction_provider_failed"
    failed = saved(RECEIPT + b"\x43")
    web.stub.failure = "encrypted_document"
    unreadable = saved(RECEIPT + b"\x44")
    web.stub.failure = None
    leave_reads_waiting(monkeypatch)
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
        accepting(reviewed.json(), "record_expense"),
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
    # The accountant working in Alice's Business reads the same page. Alice has
    # no name, so she reads her own email and the accountant, who does not
    # manage the Business, reads only that a member sent it.
    assert all(item["delete_available"] for item in page["items"])
    assert {item["sent_by"]["person"]["shown_as"] for item in page["items"]} == {"email"}
    unnamed ={"display_name": None, "email": None, "shown_as": "member"}
    assert _get(world, "/business/captures", _as(world.bob, world.grant), limit=2) == {
        **page,
        "items": [
            {
                **item,
                "delete_available": False,
                "sent_by": {**item["sent_by"], "person": unnamed},
            }
            for item in page["items"]
        ],
    }


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
        accepting(reviewed, "record_expense"),
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


def _account(world, person, currency: str) -> str:  # noqa: ANN001, F811
    account = world.client.post(
        f"{API}/business/accounts",
        json={"nickname": f"Cuenta {currency}", "type": "checking", "currency": currency},
        headers={**person.headers, "Idempotency-Key": str(uuid4())},
    )
    assert account.status_code == 201, account.text
    return account.json()["id"]


def _naming(dgii: dict, activity_id: str) -> dict:
    """The same declaration, its refund naming ``activity_id`` as the purchase."""

    return {
        **dgii,
        "declaration": {**dgii["declaration"], "purchase_activity_id": activity_id},
    }


def _approved_purchase(world, person, facts: dict, dgii: dict) -> str:  # noqa: ANN001, F811
    """An approved expense's activity id: what a credit note's declaration names."""

    note = _note(world, person, f"Compra en {facts['counterparty']}")
    assert note.status_code == 200, note.text
    draft = note.json()["draft_id"]
    reviewed = _review_with(world, draft, facts, dgii, person.headers)
    approved = _post(
        world,
        f"/business/drafts/{draft}/approve",
        accepting(reviewed, "record_expense"),
        person.headers,
    )
    assert approved.status_code == 200, approved.text
    return approved.json()["approval_result"]["activity_id"]


def test_the_server_picks_the_purchases_a_credit_note_may_refund(world) -> None:  # noqa: ANN001, F811
    """The candidates are exactly the purchases the refund approval accepts:
    the same supplier, currency and 30-day window, and never a purchase paid
    from the owner's own money, which the money write refuses to refund."""

    alice = world.alice
    accounts = {currency: _account(world, alice, currency) for currency in ("DOP", "USD")}
    from_account = {"kind": "business_account", "account_id": accounts["DOP"]}
    paid = _approved_purchase(
        world,
        alice,
        {**EXPENSE, "funding": from_account},
        _fiscal(SUPPLIER, PURCHASE_NCF),
    )
    owner_paid = _approved_purchase(
        world, alice, EXPENSE, _fiscal(SUPPLIER, "B0100000003")
    )
    _approved_purchase(
        world,
        alice,
        {
            **EXPENSE,
            "currency": "USD",
            "funding": {"kind": "business_account", "account_id": accounts["USD"]},
        },
        _fiscal(SUPPLIER, "B0100000004"),
    )

    credit = _note(world, alice, "Nota de crédito de Ferretería Prueba")
    assert credit.status_code == 200, credit.text
    draft = credit.json()["draft_id"]
    refund = {
        **EXPENSE,
        "kind": "refund",
        "amount": "100",
        "occurred_on": "2026-10-20",
        "funding": from_account,
    }
    declaration = _fiscal(
        SUPPLIER,
        CREDIT_NCF,
        actual_refund=True,
        modified_ncf=PURCHASE_NCF,
        payment_method="06",
    )
    dossier = _review_with(world, draft, refund, declaration, alice.headers)
    # The DOP purchase from the account, and only it: not the owner-funded one
    # of the same supplier and day, not the USD one.
    [candidate] = dossier["refund_candidates"]
    assert candidate["id"] == paid
    assert candidate["merchant"] == EXPENSE["counterparty"]
    assert candidate["occurred_on"] == EXPENSE["occurred_on"]
    assert Decimal(candidate["amount"]) == Decimal(EXPENSE["amount"])
    assert candidate["currency"] == "DOP"
    assert (dossier["approval_available"], dossier["approval_action"]) == (
        True,
        "record_refund",
    )
    # The same list on a reload.
    assert _get(world, f"/business/drafts/{draft}/dossier", alice.headers)[
        "refund_candidates"
    ] == [candidate]

    # The 30 days up to the note's date: the purchase of 2026-10-09 is a
    # candidate for a note of 2026-11-08, not of 2026-11-09, and not of a
    # note dated before it.
    for day, listed in (
        ("2026-11-08", True),
        ("2026-11-09", False),
        ("2026-10-08", False),
    ):
        dated = _review_with(
            world, draft, {**refund, "occurred_on": day}, declaration, alice.headers
        )
        assert [item["id"] for item in dated["refund_candidates"]] == (
            [paid] if listed else []
        ), day
    # Another supplier's credit note refunds none of this supplier's purchases.
    elsewhere = _review_with(
        world, draft, refund, _fiscal(EDITED_SUPPLIER, CREDIT_NCF), alice.headers
    )
    assert elsewhere["refund_candidates"] == []
    # An ordinary expense with an ordinary invoice refunds nothing.
    plain = _review_with(
        world,
        draft,
        {**EXPENSE, "occurred_on": "2026-10-20"},
        _fiscal(SUPPLIER, PURCHASE_NCF),
        alice.headers,
    )
    assert plain["refund_candidates"] == []

    # Naming the owner-funded purchase is what the candidates spare the person:
    # the approval refuses it. Naming the candidate records the refund.
    refused = _review_with(
        world,
        draft,
        refund,
        _naming(declaration, owner_paid),
        alice.headers,
    )
    assert refused["refund_candidates"] == [candidate]
    denied = _post(
        world,
        f"/business/drafts/{draft}/approve",
        accepting(refused, "record_refund"),
        alice.headers,
    )
    assert (denied.status_code, denied.json()["code"]) == (
        422,
        "recorded_correction_unsupported",
    )
    named = _review_with(
        world,
        draft,
        refund,
        _naming(declaration, candidate["id"]),
        alice.headers,
    )
    recorded = _post(
        world,
        f"/business/drafts/{draft}/approve",
        accepting(named, "record_refund"),
        alice.headers,
    )
    assert recorded.status_code == 200, recorded.text
    assert recorded.json()["review_state"] == "accepted"
    assert recorded.json()["approval_result"]["activity_id"]
