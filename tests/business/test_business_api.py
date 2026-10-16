"""/api/v1/business called the way web/lib/business-api.ts calls it."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import pytest
from argus.api.business_spaces import business_spaces
from argus.api.documents import documents_service
from argus.domain.business.scope import BusinessScope, resolve_business_scope
from fastapi.testclient import TestClient

from tests.business.conftest import ALICE, BOB
from tests.business.receipt_stub import PURCHASE, ReceiptStub

BASE = "/api/v1/business"
RECEIPT = (
    Path(__file__).parents[1] / "document_extraction_fixtures/receipt-dop.png"
).read_bytes()
EVIDENCE = {
    "merchant": "FERRETERIA LA ESQUINA SRL",
    "occurred_on": "2026-10-06",
    "total": "3450.00",
    "currency": "DOP",
    "tax": "526.27",
    "tip": None,
    "service": None,
    "lines": [
        {"description": "Pintura blanca 1 gal", "amount": "1850.00"},
        {"description": "Brochas x3", "amount": "1073.73"},
    ],
}


class Owner:
    """One signed-in person's calls, with the headers the web client sends."""

    def __init__(self, client: TestClient, token: str, person: str = "") -> None:
        self.client = client
        self.person = person
        self.auth = {"Authorization": f"Bearer {token}"}

    def scope(self) -> BusinessScope:
        spaces = business_spaces()
        assert spaces is not None
        scope = resolve_business_scope(spaces, self.person)
        assert scope is not None
        return scope

    def start(self, body: dict | None = None):
        return self.client.post(BASE + "/space", json=body or {}, headers=self.auth)

    def get(self, path: str, **params: str):
        return self.client.get(BASE + path, params=params, headers=self.auth)

    def post(self, path: str, body: object = None, key: str | None = None, **headers):
        if path == "/receipt-reading" and key is None:
            key = str(uuid4())
        if key is not None:
            headers["Idempotency-Key"] = key
        return self.client.post(BASE + path, json=body, headers={**self.auth, **headers})

    def reading(self, enabled: bool):
        shown = self.get("/receipt-reading").json()
        return self.post("/receipt-reading", {"enabled": enabled, "scope_version": 1, "disclosure_token": shown["disclosure_token"]})

    def account(self, currency: str = "DOP", nickname: str = "Operating") -> str:
        created = self.post(
            "/accounts",
            {"nickname": nickname, "type": "checking", "currency": currency},
            key=str(uuid4()),
        )
        assert created.status_code == 201, created.text
        return created.json()["id"]

    def upload(
        self,
        content: bytes = RECEIPT,
        consent: bool = True,
        name: str = "recibo.png",
        media_type: str = "image/png",
    ):
        headers = {
            **self.auth,
            "Content-Type": media_type,
            "Idempotency-Key": str(uuid4()),
            "X-Document-Filename": quote(name),
        }
        shown = self.get("/receipt-reading").json()
        if not consent and shown["enabled"]:
            assert self.post("/receipt-reading", {"enabled": False, "scope_version": 1}).status_code == 200
        if consent:
            if not shown["enabled"]:
                enabled = self.post(
                    "/receipt-reading",
                    {
                        "enabled": True,
                        "scope_version": shown["scope_version"],
                        "disclosure_token": shown["disclosure_token"],
                    },
                )
                assert enabled.status_code == 200, enabled.text
            headers["X-Extraction-Consent"] = "true"
        return self.client.post(BASE + "/receipts", content=content, headers=headers)

    def review(self, receipt_id: str, version: int, **fields):
        return self.client.patch(
            f"{BASE}/receipts/{receipt_id}/review",
            json={"version": version, "fields": fields},
            headers=self.auth,
        )

    def confirm(self, receipt_id: str, version: int, key: str):
        return self.post(f"/receipts/{receipt_id}/confirm", {"version": version}, key=key)

    def detail(self, receipt_id: str) -> dict:
        found = self.get(f"/receipts/{receipt_id}")
        assert found.status_code == 200, found.text
        return found.json()


def started(owner: Owner) -> Owner:
    assert owner.start().status_code == 201
    return owner


@pytest.fixture
def alice(biz: TestClient, identities) -> Owner:  # noqa: ANN001
    return started(Owner(biz, ALICE, identities[ALICE]["id"]))


@pytest.fixture
def bob(biz: TestClient, identities) -> Owner:  # noqa: ANN001
    return started(Owner(biz, BOB, identities[BOB]["id"]))


def prepared(alice: Owner) -> str:
    uploaded = alice.upload()
    assert uploaded.status_code == 200, uploaded.text
    return uploaded.json()["id"]


def test_flag_off_every_route_is_404_before_auth(client: TestClient, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("ARGUS_DOCUMENT_EXTRACTION_ENABLED", "true")
    monkeypatch.delenv("ARGUS_BUSINESS_PILOT_ENABLED", raising=False)
    receipt = f"{BASE}/receipts/{uuid4()}"
    calls = [
        client.get(f"{BASE}/workspace"),
        client.post(f"{BASE}/accounts", json={}),
        client.post(f"{BASE}/receipts", content=b"x"),
        client.get(f"{BASE}/receipts"),
        client.get(receipt),
        client.get(f"{receipt}/source"),
        client.post(f"{receipt}/prepare"),
        client.patch(f"{receipt}/review", json={}),
        client.post(f"{receipt}/confirm", json={}),
        client.get(f"{BASE}/expenses"),
        client.post(f"{BASE}/expenses", json={}),
        client.get(f"{BASE}/overview"),
        client.get(f"{BASE}/updates"),
        client.get(f"{BASE}/search", params={"q": "x"}),
        client.get(f"{BASE}/space"),
        client.post(f"{BASE}/space", json={}),
        client.patch(f"{BASE}/space", json={"name": "x"}),
    ]
    assert [(r.status_code, r.json()["code"]) for r in calls] == [
        (404, "business_unavailable")
    ] * 17
    assert {r.headers["Cache-Control"] for r in calls} == {"no-store"}


def test_document_intake_off_keeps_saved_receipts_and_owner_actions(
    alice: Owner, monkeypatch: pytest.MonkeyPatch
) -> None:
    account = alice.account()
    receipt_id = prepared(alice)
    monkeypatch.setenv("ARGUS_DOCUMENT_EXTRACTION_ENABLED", "false")

    assert alice.get("/space").status_code == 200
    assert receipt_id in [r["id"] for r in alice.get("/receipts").json()["items"]]
    source = alice.get(f"/receipts/{receipt_id}/source")
    assert source.status_code == 200
    assert source.headers["content-type"] == "image/jpeg"
    assert source.content.startswith(b"\xff\xd8") and source.content != RECEIPT
    refused = [
        alice.upload(content=RECEIPT + b"new"),
        alice.post(
            f"/receipts/{receipt_id}/prepare", None, **{"X-Extraction-Consent": "true"}
        ),
    ]
    assert [r.status_code for r in refused] == [404, 404]

    version = alice.review(
        receipt_id, alice.detail(receipt_id)["version"], account_id=account
    ).json()["version"]
    confirmed = alice.confirm(receipt_id, version, str(uuid4()))
    assert confirmed.json()["status"] == "confirmed", confirmed.text


def test_business_is_off_while_ingestion_is_off(
    biz: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    alice = Owner(biz, ALICE)
    monkeypatch.setenv("ARGUS_INGESTION_ENABLED", "false")
    off = [
        alice.start(),
        alice.get("/space"),
        alice.get("/receipts"),
        biz.patch(f"{BASE}/space", json={"name": "Taller"}, headers=alice.auth),
    ]
    assert [r.status_code for r in off] == [404] * 4


def test_flag_on_still_requires_a_registered_session(biz: TestClient) -> None:
    assert biz.get(f"{BASE}/workspace").status_code == 401
    assert biz.post(f"{BASE}/space", json={}).status_code == 401


def test_every_route_waits_for_the_space_and_starting_it_is_idempotent(
    biz: TestClient,
) -> None:
    alice = Owner(biz, ALICE)
    receipt = f"/receipts/{uuid4()}"
    before = [
        alice.get("/workspace"),
        alice.get("/receipts"),
        alice.get(receipt),
        alice.get("/expenses", **{"from": "2026-10-01", "to": "2026-10-31"}),
        alice.get("/overview", **{"from": "2026-10-01", "to": "2026-10-31"}),
        alice.get("/updates"),
        alice.get("/search", q="ferreteria"),
        alice.get("/space"),
        biz.patch(f"{BASE}/space", json={"name": "Taller"}, headers=alice.auth),
    ]
    assert [(r.status_code, r.json()["code"]) for r in before] == [
        (404, "business_space_missing")
    ] * 9
    first = alice.start()
    assert first.status_code == 201
    assert first.json()["name"] == "Mi negocio"
    again = alice.start({"name": "Otro nombre"})
    assert (again.status_code, again.json()) == (200, first.json())
    renamed = biz.patch(
        f"{BASE}/space", json={"name": "  Taller Gómez "}, headers=alice.auth
    )
    assert renamed.json() == {"id": first.json()["id"], "name": "Taller Gómez"}
    assert alice.get("/space").json() == renamed.json()
    assert alice.get("/workspace").status_code == 200
    bob = Owner(biz, BOB)
    english = bob.start({"language": "en"})
    assert (english.status_code, english.json()["name"]) == (201, "My business")
    assert english.json()["id"] != first.json()["id"]
    assert alice.get("/space").json()["name"] == "Taller Gómez"
    refused = [
        alice.start({"name": "   "}),
        biz.patch(f"{BASE}/space", json={"name": "x" * 81}, headers=alice.auth),
        alice.start({"space_id": first.json()["id"]}),
    ]
    assert [r.status_code for r in refused] == [422, 422, 422]


def test_business_and_personal_never_see_each_other(alice: Owner) -> None:
    client, auth = alice.client, alice.auth
    personal = client.post(
        "/api/v1/financial-accounts",
        json={"type": "checking", "currency": "DOP", "nickname": "Casa"},
        headers={**auth, "Idempotency-Key": str(uuid4())},
    )
    assert personal.status_code == 201, personal.text
    personal_id = personal.json()["id"]
    business_id = alice.account("DOP", "Caja")
    assert [a["id"] for a in alice.get("/workspace").json()["accounts"]] == [business_id]
    listed = client.get("/api/v1/financial-accounts", headers=auth).json()
    assert [a["id"] for a in listed["accounts"]] == [personal_id]
    assert (
        client.get(f"/api/v1/financial-accounts/{business_id}", headers=auth).status_code
        == 404
    )
    expense = {
        "account_id": personal_id,
        "amount": "125.00",
        "occurred_on": "2026-10-06",
        "merchant": "Colmado",
        "category_id": None,
    }
    refused = alice.post("/expenses", expense, key=str(uuid4()))
    assert refused.status_code == 404, refused.text
    receipt_id = prepared(alice)
    documents = client.get("/api/v1/financial-documents", headers=auth).json()
    assert receipt_id not in {d["connection_id"] for d in documents["items"]}
    assert (
        client.get(f"/api/v1/financial-documents/{receipt_id}", headers=auth).status_code
        == 404
    )
    personal_upload = client.post(
        "/api/v1/financial-documents",
        content=RECEIPT,
        headers={**auth, "Content-Type": "image/png"},
    )
    assert personal_upload.status_code in (200, 201), personal_upload.text
    personal_document = personal_upload.json()["connection_id"]
    assert personal_document != receipt_id
    assert [r["id"] for r in alice.get("/receipts", view="all").json()["items"]] == [
        receipt_id
    ]
    assert alice.get(f"/receipts/{personal_document}").status_code == 404


def test_workspace_lists_expense_accounts_and_document_limits(alice: Owner) -> None:
    empty = alice.get("/workspace").json()
    assert empty["accounts"] == [] and empty["currencies"] == []
    dop = alice.account("DOP", "Operating")
    usd = alice.account("USD", "Card")
    workspace = alice.get("/workspace")
    assert workspace.headers["Cache-Control"] == "no-store"
    assert workspace.json() == {
        "accounts": [
            {"id": dop, "nickname": "Operating", "type": "checking", "currency": "DOP"},
            {"id": usd, "nickname": "Card", "type": "checking", "currency": "USD"},
        ],
        "currencies": ["DOP", "USD"],
        "assistant_available": False,
        "chat_available": False,
        "receipt_limits": {
            "max_bytes": 10485760,
            "media_types": [
                "application/pdf",
                "image/jpeg",
                "image/png",
                "text/plain",
                "text/csv",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "application/xml",
                "text/xml",
                "message/rfc822",
            ],
        },
    }


def test_workspace_says_whether_business_chat_is_on(alice: Owner, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("ARGUS_BUSINESS_CHAT_ENABLED", "true")
    assert alice.get("/workspace").json()["chat_available"] is True
    monkeypatch.setenv("ARGUS_BUSINESS_CHAT_ENABLED", "false")
    assert alice.get("/workspace").json()["chat_available"] is False


def test_create_account_needs_a_key_and_replays(alice: Owner) -> None:
    body = {"nickname": "Caja chica", "type": "cash", "currency": "DOP"}
    assert alice.post("/accounts", body).json()["code"] == "idempotency_key_required"
    first = alice.post("/accounts", body, key="acct-1")
    again = alice.post("/accounts", body, key="acct-1")
    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json() == first.json()
    assert first.json()["nickname"] == "Caja chica"
    refused = alice.post("/accounts", {**body, "type": "property"}, key="acct-2")
    assert refused.status_code == 422


def test_upload_with_consent_prepares_a_reviewable_receipt(
    alice: Owner, stub: ReceiptStub
) -> None:
    uploaded = alice.upload(name="recibo ferretería.png")
    assert uploaded.status_code == 200, uploaded.text
    summary = uploaded.json()
    assert (summary["status"], summary["channel"], summary["filename"]) == (
        "queued",
        "web",
        "recibo ferretería.png",
    )
    assert summary["media_type"] == "image/png"
    assert summary["size_bytes"] == len(RECEIPT)
    detail = alice.detail(summary["id"])
    assert stub.calls == [summary["id"]]
    assert {
        key: detail[key]
        for key in (
            "status",
            "merchant",
            "occurred_on",
            "amount",
            "currency",
            "account_id",
            "expense_id",
            "missing_fields",
            "evidence",
        )
    } == {
        "status": "review_ready",
        "merchant": "FERRETERIA LA ESQUINA SRL",
        "occurred_on": "2026-10-06",
        "amount": "3450",
        "currency": "DOP",
        "account_id": None,
        "expense_id": None,
        "missing_fields": ["account_id"],
        "evidence": EVIDENCE,
    }
    assert detail["version"] >= 1
    [listed] = alice.get("/receipts", view="inbox").json()["items"]
    assert listed["id"] == summary["id"] and listed["status"] == "review_ready"


def test_upload_rejects_what_documents_reject(alice: Owner) -> None:
    missing_key = alice.client.post(
        BASE + "/receipts",
        content=RECEIPT,
        headers={**alice.auth, "Content-Type": "image/png"},
    )
    assert missing_key.json()["code"] == "idempotency_key_required"
    gif = alice.client.post(
        BASE + "/receipts",
        content=b"GIF89a",
        headers={**alice.auth, "Content-Type": "image/gif", "Idempotency-Key": "k"},
    )
    assert (gif.status_code, gif.json()["code"]) == (
        415,
        "document_media_type_unsupported",
    )


def test_saved_receipt_prepares_only_with_consent(
    alice: Owner, stub: ReceiptStub
) -> None:
    uploaded = alice.upload(consent=False).json()
    assert uploaded["status"] == "saved"
    receipt = alice.detail(uploaded["id"])
    assert (receipt["version"], receipt["evidence"], receipt["missing_fields"]) == (
        0,
        None,
        ["account_id", "amount", "currency", "occurred_on"],
    )
    refused = alice.post(f"/receipts/{uploaded['id']}/prepare")
    assert (refused.status_code, refused.json()["code"]) == (
        422,
        "document_extraction_consent_required",
    )
    assert stub.calls == []
    shown = alice.get("/receipt-reading").json()
    enabled = alice.post(
        "/receipt-reading",
        {
            "enabled": True,
            "scope_version": shown["scope_version"],
            "disclosure_token": shown["disclosure_token"],
        },
    )
    assert enabled.status_code == 200, enabled.text
    assert alice.detail(uploaded["id"])["status"] == "review_ready"
    assert alice.detail(uploaded["id"])["status"] == "review_ready"
    assert stub.calls == [uploaded["id"]]


def test_review_corrects_fields_and_never_the_evidence(alice: Owner) -> None:
    receipt_id = prepared(alice)
    account = alice.account()
    before = alice.detail(receipt_id)
    reviewed = alice.review(
        receipt_id,
        before["version"],
        merchant="Ferretería La Esquina",
        amount="3400.00",
        account_id=account,
        category_id="housing",
    )
    assert reviewed.status_code == 200, reviewed.text
    after = reviewed.json()
    assert {
        key: after[key]
        for key in (
            "merchant",
            "amount",
            "account_id",
            "category_id",
            "missing_fields",
            "evidence",
        )
    } == {
        "merchant": "Ferretería La Esquina",
        "amount": "3400",
        "account_id": account,
        "category_id": "housing",
        "missing_fields": [],
        "evidence": EVIDENCE,
    }
    assert after["version"] == before["version"] + 1
    stale = alice.review(receipt_id, before["version"], merchant="Otra")
    assert (stale.status_code, stale.json()["code"]) == (409, "stale_version")
    cleared = alice.review(receipt_id, after["version"], merchant=None).json()
    assert cleared["merchant"] == "FERRETERIA LA ESQUINA SRL"


def test_confirm_refuses_missing_fields_and_currency_mismatch(alice: Owner) -> None:
    receipt_id = prepared(alice)
    version = alice.detail(receipt_id)["version"]
    missing = alice.confirm(receipt_id, version, "c-1")
    assert (missing.status_code, missing.json()["code"]) == (422, "missing_fields")
    usd = alice.account("USD", "Card")
    version = alice.review(receipt_id, version, account_id=usd).json()["version"]
    mismatch = alice.confirm(receipt_id, version, "c-2")
    assert (mismatch.status_code, mismatch.json()["code"]) == (422, "currency_mismatch")
    dop = alice.account("DOP")
    version = alice.review(receipt_id, version, account_id=dop, amount="10.001").json()[
        "version"
    ]
    precision = alice.confirm(receipt_id, version, "c-3")
    assert (precision.status_code, precision.json()["code"]) == (422, "amount_precision")
    assert alice.get(
        "/expenses", **{"from": "2026-10-01", "to": "2026-10-31"}
    ).json() == {"items": []}


def test_confirm_saves_one_expense_across_replays(alice: Owner) -> None:
    receipt_id = prepared(alice)
    account = alice.account()
    version = alice.review(
        receipt_id,
        alice.detail(receipt_id)["version"],
        account_id=account,
        merchant="Ferretería La Esquina",
    ).json()["version"]
    confirmed = alice.confirm(receipt_id, version, "confirm-1")
    assert confirmed.status_code == 200, confirmed.text
    body = confirmed.json()
    assert (body["status"], body["merchant"]) == ("confirmed", "Ferretería La Esquina")
    expense_id = body["expense_id"]
    replay = alice.confirm(receipt_id, version, "confirm-1").json()
    other_key = alice.confirm(receipt_id, version, "confirm-2").json()
    assert replay["expense_id"] == other_key["expense_id"] == expense_id
    assert alice.get(
        "/expenses", **{"from": "2026-10-01", "to": "2026-10-31"}
    ).json() == {
        "items": [
            {
                "id": expense_id,
                "merchant": "Ferretería La Esquina",
                "amount": "3450.00",
                "currency": "DOP",
                "category_id": None,
                "account_id": account,
                "occurred_on": "2026-10-06",
                "receipt_id": receipt_id,
                "fiscal_known": True,
            }
        ]
    }
    assert alice.get("/receipts", view="inbox").json() == {
        "items": [],
        "activity": {
            "reading_count": 0,
            "unread_count": 0,
            "presentation": "none",
            "pending_review_count": 0,
            "needs_attention_count": 0,
        },
    }
    [saved] = alice.get("/receipts", view="all").json()["items"]
    assert (saved["status"], saved["expense_id"]) == ("confirmed", expense_id)


def test_manual_expense_is_canonical_and_replays(alice: Owner) -> None:
    account = alice.account()
    entered = {
        "account_id": account,
        "amount": "1250.00",
        "occurred_on": "2026-10-04",
        "merchant": "Comedor Doña Ana",
        "category_id": "dining",
    }
    first = alice.post("/expenses", entered, key="exp-1")
    again = alice.post("/expenses", entered, key="exp-1")
    assert (first.status_code, again.status_code) == (201, 201)
    assert (
        first.json()
        == again.json()
        == {
            "id": first.json()["id"],
            "merchant": "Comedor Doña Ana",
            "amount": "1250.00",
            "currency": "DOP",
            "category_id": "dining",
            "account_id": account,
            "occurred_on": "2026-10-04",
            "receipt_id": None,
            "fiscal_known": True,
        }
    )
    conflict = alice.post("/expenses", {**entered, "amount": "99.00"}, key="exp-1")
    assert (conflict.status_code, conflict.json()["code"]) == (
        409,
        "idempotency_conflict",
    )
    precision = alice.post("/expenses", {**entered, "amount": "1.001"}, key="exp-2")
    assert (precision.status_code, precision.json()["code"]) == (422, "amount_precision")
    listed = alice.get("/expenses", **{"from": "2026-10-04", "to": "2026-10-04"}).json()
    assert [item["id"] for item in listed["items"]] == [first.json()["id"]]
    assert alice.get(
        "/expenses", **{"from": "2026-10-05", "to": "2026-10-31"}
    ).json() == {"items": []}


def test_overview_totals_each_currency_and_counts_the_inbox(alice: Owner) -> None:
    dop, usd = alice.account("DOP"), alice.account("USD", "Card")
    for account, amount in ((dop, "1000.50"), (dop, "200.00"), (usd, "24.00")):
        alice.post(
            "/expenses",
            {"account_id": account, "amount": amount, "occurred_on": "2026-10-02"},
            key=str(uuid4()),
        )
    prepared(alice)
    alice.post("/receipt-reading", {"enabled": False, "scope_version": 1})
    alice.upload(content=RECEIPT + b"\0", consent=False)
    overview = alice.get("/overview", **{"from": "2026-10-01", "to": "2026-10-31"}).json()
    assert {
        key: overview[key]
        for key in (
            "from",
            "to",
            "totals",
            "awaiting_review",
            "needs_attention",
        )
    } == {
        "from": "2026-10-01",
        "to": "2026-10-31",
        "totals": [
            {"currency": "DOP", "amount": "1200.50", "count": 2},
            {"currency": "USD", "amount": "24.00", "count": 1},
        ],
        "awaiting_review": 2,
        "needs_attention": 0,
    }
    assert overview["last_received_at"] is not None
    assert overview["last_confirmed_at"] is not None


def test_updates_follow_receipt_states(alice: Owner) -> None:
    receipt_id = prepared(alice)
    account = alice.account()
    assert [
        (u["kind"], u["receipt_id"]) for u in alice.get("/updates").json()["items"]
    ] == [("receipt_ready", receipt_id)]
    version = alice.review(
        receipt_id, alice.detail(receipt_id)["version"], account_id=account
    )
    expense_id = alice.confirm(receipt_id, version.json()["version"], "k").json()[
        "expense_id"
    ]
    [update] = alice.get("/updates").json()["items"]
    assert {key: update[key] for key in ("id", "kind", "expense_id", "label")} == {
        "id": f"expense_confirmed:{receipt_id}",
        "kind": "expense_confirmed",
        "expense_id": expense_id,
        "label": "FERRETERIA LA ESQUINA SRL",
    }


def test_source_returns_only_rebuilt_bytes_to_the_owner(alice: Owner, bob: Owner) -> None:
    receipt_id = prepared(alice)
    source = alice.get(f"/receipts/{receipt_id}/source")
    assert source.status_code == 200
    assert source.content.startswith(b"\xff\xd8") and source.content != RECEIPT
    store = documents_service().store
    assert store.source(user_id=alice.scope().person_id, connection_id=receipt_id) == RECEIPT
    before = dict(store.objects.objects)
    assert alice.get(f"/receipts/{receipt_id}/source").content == source.content
    assert store.objects.objects == before
    assert (source.headers["Cache-Control"], source.headers["Content-Type"]) == (
        "no-store",
        "image/jpeg",
    )
    assert source.headers["X-Content-Type-Options"] == "nosniff"
    from unittest.mock import patch

    from argus.domain.ingestion.documents.objects import SourceStorageUnavailable

    with patch.object(
        documents_service().store,
        "download_source",
        side_effect=SourceStorageUnavailable("unavailable"),
    ):
        unavailable = alice.get(f"/receipts/{receipt_id}/source")
    assert unavailable.status_code == 503
    assert unavailable.json()["code"] == "document_storage_unavailable"

    account = alice.account()
    version = alice.review(
        receipt_id, alice.detail(receipt_id)["version"], account_id=account
    )
    expense_id = alice.confirm(receipt_id, version.json()["version"], "k").json()[
        "expense_id"
    ]
    calls = [
        bob.get(f"/receipts/{receipt_id}"),
        bob.get(f"/receipts/{receipt_id}/source"),
        bob.review(receipt_id, 1, merchant="mine"),
        bob.confirm(receipt_id, 1, "bob"),
        bob.post(f"/receipts/{receipt_id}/prepare", **{"X-Extraction-Consent": "true"}),
    ]
    assert [(r.status_code, r.json()["code"]) for r in calls] == [
        (404, "receipt_not_found")
    ] * 5
    assert bob.get("/receipts", view="all").json() == {
        "items": [],
        "activity": {
            "reading_count": 0,
            "unread_count": 0,
            "presentation": "none",
            "pending_review_count": 0,
            "needs_attention_count": 0,
        },
    }
    window = {"from": "2026-10-01", "to": "2026-10-31"}
    assert bob.get("/expenses", **window).json() == {"items": []}
    assert [e["id"] for e in alice.get("/expenses", **window).json()["items"]] == [
        expense_id
    ]


def test_a_multi_row_csv_waits_for_attention_with_every_row_kept(
    alice: Owner, stub: ReceiptStub
) -> None:
    """A spreadsheet is not one receipt: it is set aside, and its rows stay as evidence."""
    stub.rows = [
        PURCHASE,
        {**PURCHASE, "row": 2, "amount": "100.00", "merchant": "COLMADO DON JOSE"},
    ]
    rows = b"date,amount,merchant\n2026-10-06,3450.00,Ferreteria\n2026-10-06,100.00,Colmado\n"
    uploaded = alice.upload(content=rows, name="gastos.csv", media_type="text/csv")
    assert uploaded.status_code == 200, uploaded.text
    receipt_id = uploaded.json()["id"]
    detail = alice.detail(receipt_id)
    assert (detail["status"], detail["attention"], detail["media_type"]) == (
        "needs_attention",
        "several_purchases",
        "text/csv",
    )
    assert detail["filename"] == "gastos.csv"
    scope = alice.scope()
    batch = documents_service().store.get(
        user_id=scope.person_id, connection_id=receipt_id
    )
    # Nothing becomes a candidate purchase; every read row stays in the saved batch.
    assert batch.candidates == ()
    assert [row.amount for row in batch.observations] == ["3450.00", "100.00"]
    assert "receipt_purchase_ambiguous" in {issue.code for issue in batch.issues}
    source = alice.get(f"/receipts/{receipt_id}/source")
    assert source.status_code == 200
    assert source.content == rows
    assert alice.get(
        "/expenses", **{"from": "2026-10-01", "to": "2026-10-31"}
    ).json() == {"items": []}


def test_upload_header_does_not_enable_business_reading(alice, stub):
    response = alice.client.post(
        BASE + "/receipts",
        content=RECEIPT,
        headers={
            **alice.auth,
            "Content-Type": "image/png",
            "Idempotency-Key": str(uuid4()),
            "X-Extraction-Consent": "true",
        },
    )
    assert response.status_code == 200
    assert response.json()["activity"]["state"] == "saved_unread"
    assert stub.calls == []
    assert alice.get("/receipt-reading").json()["enabled"] is False


def test_owner_enabling_reads_backlog_once_and_disabling_stops_new_reads(alice, stub):
    saved = alice.upload(consent=False).json()
    assert alice.get("/receipt-activity").json()["unread_count"] == 1
    shown = alice.get("/receipt-reading").json()
    body = {
        "enabled": True,
        "scope_version": 1,
        "disclosure_token": shown["disclosure_token"],
    }
    assert alice.post("/receipt-reading", body).status_code == 200
    assert alice.detail(saved["id"])["activity"]["state"] == "ready"
    assert len(stub.calls) == 1
    assert alice.post("/receipt-reading", body).status_code == 200
    assert len(stub.calls) == 1
    assert (
        alice.post("/receipt-reading", {"enabled": False, "scope_version": 1}).status_code
        == 200
    )
    second = alice.upload(content=RECEIPT + b"another", consent=False).json()
    assert second["activity"]["state"] == "saved_unread"
    assert len(stub.calls) == 1


def test_receipt_list_and_detail_share_cursor_and_ack_does_not_record_money(alice):
    rid = prepared(alice)
    detail = alice.detail(rid)
    listed = next(
        row for row in alice.get("/receipts").json()["items"] if row["id"] == rid
    )
    assert (
        listed["activity"]["completion_cursor"] == detail["activity"]["completion_cursor"]
    )
    before = alice.get("/expenses", **{"from": "2026-10-01", "to": "2026-10-31"}).json()
    ack = alice.post(
        f"/receipts/{rid}/read",
        {"completion_cursor": detail["activity"]["completion_cursor"]},
    )
    assert ack.status_code == 200, ack.text
    assert ack.json()["unread"] is False
    assert (
        alice.get("/expenses", **{"from": "2026-10-01", "to": "2026-10-31"}).json()
        == before
    )


def test_missing_source_does_not_strand_other_unread_receipts(alice, stub):
    first = alice.upload(consent=False).json()
    second = alice.upload(content=RECEIPT + b"second", consent=False).json()
    documents = documents_service()
    draft = documents.store.draft(
        user_id=alice.scope().person_id, connection_id=first["id"]
    )
    documents._update(alice.scope().person_id, draft, source_available=False)
    shown = alice.get("/receipt-reading").json()
    enabled = alice.post(
        "/receipt-reading",
        {
            "enabled": True,
            "scope_version": 1,
            "disclosure_token": shown["disclosure_token"],
        },
    )
    assert enabled.status_code == 200, enabled.text
    assert alice.detail(second["id"])["activity"]["state"] in ("ready", "read_failed")
    assert len(stub.calls) == 1
    assert alice.detail(first["id"])["activity"]["state"] == "saved_unread"
