"""Over HTTP, on the real app, Auth and Postgres: a purchase typed with no paper
is saved sin comprobante, a person approves it and it counts, and it never
reaches the 606; the tipo de gasto a person chose for an RNC comes back as a
suggestion in that Business only and is stored only when a person keeps it; a
sale's payment split is written after approval until the line is exported."""

from __future__ import annotations

from uuid import uuid4

import pytest
from argus.domain.business.contracts.actions import CaptureNote, ReviewDraft
from argus.domain.business.contracts.facts import BusinessFactPatch
from psycopg import Connection

from tests import test_business_actions_postgres as business
from tests import test_business_fiscal_routes_postgres as routes
from tests import test_financial_accounts_postgres as shared
from tests.test_business_approve_unpaid_postgres import (
    BUYER_OR_SUPPLIER,
    SPAN,
    _approve,
    _block,
    _declaration,
    _declare,
    _export,
    _fiscal_profile,
    _get,
    _month,
    _recorded,
    _reviewed,
)
from tests.test_business_fiscal_routes_postgres import _known, _post, _review
from tests.test_business_scope_switch_routes_postgres import (
    API,
    _as,
    web,
)
from tests.test_business_scope_switch_routes_postgres import (
    pytestmark as _local_supabase,
)

actions = business.actions
users = business.users
world = routes.world
people = web
pytestmark = _local_supabase
TEXT = "Gasolina en la estación"
PURCHASE = {"amount": "500.00", "occurred_on": "2026-09-03"}
OTHER_SUPPLIER = "199990048"


def _typed(world, person=None, grant=None, key=None, **body):  # noqa: ANN001, ANN003, ANN202
    return world.client.post(
        f"{API}/business/captures",
        json={"text": TEXT, "purchase": PURCHASE, **body},
        headers={
            **_as(person or world.alice, grant),
            "Idempotency-Key": key or str(uuid4()),
        },
    )


def _money_rows(world) -> int:  # noqa: ANN001
    with Connection.connect(shared.DSN) as db:
        return db.execute(
            "select count(*) from public.financial_records where user_id=%s",
            (world.alice.id,),
        ).fetchone()[0]


def test_a_typed_purchase_holds_what_the_person_typed_and_nothing_else(world) -> None:  # noqa: ANN001
    answer = _typed(world)

    assert answer.status_code == 200, answer.text
    dossier = answer.json()
    facts = dossier["facts"]
    assert {name: fact["value"] for name, fact in facts.items() if name != "fiscal"} == {
        "kind": "expense",
        "amount": "500",
        "currency": "DOP",
        "occurred_on": "2026-09-03",
        "counterparty": TEXT,
        "funding": None,
        "business_share": None,
        "receipt_state": "no_receipt",
        "category_id": None,
    }
    assert facts["fiscal"] is None
    assert facts["amount"]["origin"] == "member_set"
    assert facts["receipt_state"]["origin"] == "member_set"
    assert facts["currency"]["origin"] == "default"
    assert dossier["dgii"] is None
    assert dossier["sin_comprobante"] is True
    assert dossier["blockers"] == []
    assert dossier["accounts"] == []
    assert dossier["approval_action"] == "record_expense"
    assert [source["text"] for source in dossier["sources"]] == [TEXT]
    assert _money_rows(world) == 0


def test_a_person_reviews_it_alone_and_the_bandeja_holds_it_until_then(world) -> None:  # noqa: ANN001
    dossier = _typed(world).json()
    draft = dossier["draft_id"]

    assert [
        item["draft_id"]
        for item in _get(world, "/business/captures", view="inbox").json()["items"]
    ] == [draft]
    assert _get(world, "/business/overview", **SPAN).json()["awaiting_review"] == 1
    many = _post(
        world,
        "/business/drafts/approve-listos",
        {"items": [{"draft_id": draft, "version": dossier["version"]}]},
        world.alice.headers,
    )
    assert many.status_code == 200, many.text
    assert [item["code"] for item in many.json()["results"]] == ["not_listo"]
    assert _money_rows(world) == 0

    assert _approve(world, draft, dossier["version"], "expense").status_code == 200
    assert _money_rows(world) == 1
    assert _get(world, "/business/captures", view="inbox").json()["items"] == []


def test_an_approved_typed_purchase_counts_and_stays_out_of_the_606(world) -> None:  # noqa: ANN001
    _fiscal_profile(world)
    declared, _ = _recorded(
        world,
        "expense",
        "B0100000041",
        id_type="1",
        category="02",
        services_amount="1000.00",
        payment_method="01",
    )
    dossier = _typed(world).json()
    recorded = _approve(world, dossier["draft_id"], dossier["version"], "expense")
    assert recorded.status_code == 200, recorded.text

    expenses = _get(world, "/business/expenses", **SPAN).json()["items"]
    assert TEXT in [item["merchant"] for item in expenses]
    month = _month(world)
    assert month["dgii_forms"]["606"] == "prepared_candidate"
    assert month["closed"] is True
    assert (month["missing_rnc"], month["missing_ncf"]) == ([], [])
    assert month["missing_payment_form"] == []
    block = _block(month)
    assert block["expense_before_itbis_minor"] == 150000
    report = {
        item["counterparty"]: item
        for item in world.client.post(
            f"{API}/business/reports/query", json={}, headers=world.alice.headers
        ).json()["items"]
    }
    assert report[TEXT]["fiscal_classification"] == "no_comprobante"

    manifest, rows, files = _export(world)
    assert TEXT in [row["Proveedor"] for row in rows]
    assert TEXT not in files["606"]
    assert len(files["606"].splitlines()) == 2
    typed = next(
        item
        for item in manifest["reconciliation"]
        if item["draft_id"] == dossier["draft_id"]
    )
    assert (typed["disposition"], typed["reason"]) == ("excluded", "no_fiscal_number")
    assert declared in [item["draft_id"] for item in manifest["reconciliation"]]


def test_a_retry_with_the_same_key_saves_one_draft(world) -> None:  # noqa: ANN001
    key = str(uuid4())
    first = _typed(world, key=key)
    again = _typed(world, key=key)
    changed = _typed(
        world, key=key, purchase={"amount": "600.00", "occurred_on": "2026-09-03"}
    )

    assert first.status_code == again.status_code == 200
    assert first.json()["draft_id"] == again.json()["draft_id"]
    assert changed.status_code == 409, changed.text


def test_someone_who_prepares_types_it_and_only_the_owner_approves(world) -> None:  # noqa: ANN001
    answer = _typed(world, world.bob, world.grant)
    assert answer.status_code == 200, answer.text
    dossier = answer.json()
    assert dossier["approval_action"] is None

    refused = world.client.post(
        f"{API}/business/drafts/{dossier['draft_id']}/approve",
        json={"version": dossier["version"], "action": "record_expense"},
        headers={**_as(world.bob, world.grant), "Idempotency-Key": str(uuid4())},
    )
    assert refused.status_code == 403, refused.text
    assert _money_rows(world) == 0


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"purchase": {**PURCHASE, "amount": "0"}}, "amount_positive_required"),
        ({"purchase": {**PURCHASE, "amount": "12.345"}}, "validation_error"),
        ({"purchase": {"amount": "500.00"}}, "validation_error"),
        ({"purchase": {"occurred_on": "2026-09-03"}}, "validation_error"),
        ({"purchase": {**PURCHASE, "account_id": str(uuid4())}}, "validation_error"),
        ({"text": "   "}, "validation_error"),
        ({"text": "x" * 201}, "validation_error"),
        ({"document_type": "venta"}, "validation_error"),
        (
            {"draft": {"draft_id": str(uuid4()), "version": 1}},
            "validation_error",
        ),
    ],
)
def test_a_typed_purchase_that_cannot_stand_is_refused_and_leaves_nothing(
    world,  # noqa: ANN001
    body: dict,
    code: str,
) -> None:
    answer = _typed(world, **body)

    assert answer.status_code == 422, answer.text
    assert answer.json()["code"] == code
    assert _get(world, "/business/captures").json()["items"] == []


def _purchase(  # noqa: ANN202
    world,  # noqa: ANN001
    person,  # noqa: ANN001
    ncf: str,
    rnc: str = BUYER_OR_SUPPLIER,
    grant=None,  # noqa: ANN001
    **declared,
):
    """A reviewed purchase with this supplier and comprobante."""

    note = _post(world, "/business/captures", {"text": ncf}, _as(person, grant))
    assert note.status_code == 200, note.text
    answer = _review(
        world,
        note.json()["draft_id"],
        {
            "version": note.json()["version"],
            "facts": _known(
                {
                    "kind": "expense",
                    "amount": "1180.00",
                    "currency": "DOP",
                    "occurred_on": "2026-09-03",
                    "counterparty": "Ferretería Prueba",
                }
            ),
            "dgii": {
                "fiscal": {"rnc": rnc, "ncf": ncf, "itbis": "180.00"},
                "declaration": _declaration("expense", **declared),
            },
        },
        _as(person, grant),
    )
    assert answer.status_code == 200, answer.text
    return answer.json()


def _chosen(world, ncf: str, category: str, rnc: str = BUYER_OR_SUPPLIER) -> dict:  # noqa: ANN001
    """A purchase approved with the type a person chose."""

    dossier = _purchase(world, world.alice, ncf, rnc, category=category)
    answer = _approve(world, dossier["draft_id"], dossier["version"], "expense")
    assert answer.status_code == 200, answer.text
    return answer.json()


def test_the_type_a_person_chose_for_an_rnc_comes_back_as_a_suggestion(world) -> None:  # noqa: ANN001
    assert _purchase(world, world.alice, "B0100000051")["expense_type_suggestion"] is None
    _chosen(world, "B0100000052", "02")

    dashed = f"{BUYER_OR_SUPPLIER[:3]}-{BUYER_OR_SUPPLIER[3:8]}-{BUYER_OR_SUPPLIER[8:]}"
    fresh = _purchase(world, world.alice, "B0100000053", dashed)
    assert fresh["expense_type_suggestion"] == "02"
    assert fresh["dgii"]["category"] is None
    assert (
        _purchase(world, world.alice, "B0100000054", OTHER_SUPPLIER)[
            "expense_type_suggestion"
        ]
        is None
    )


def test_a_suggestion_is_stored_only_when_a_person_keeps_it(world) -> None:  # noqa: ANN001
    _fiscal_profile(world)
    _chosen(world, "B0100000061", "02")
    dossier = _purchase(
        world,
        world.alice,
        "B0100000062",
        id_type="1",
        services_amount="1000.00",
        payment_method="01",
    )
    assert dossier["expense_type_suggestion"] == "02"

    answer = _approve(world, dossier["draft_id"], dossier["version"], "expense")
    assert answer.status_code == 200, answer.text
    recorded = answer.json()
    assert recorded["dgii"]["category"] is None
    assert recorded["expense_type_suggestion"] == "02"
    rows = {row["NCF"]: row for row in _export(world)[1]}
    assert rows["B0100000062"]["Tipo de gasto"] == ""
    assert _month(world)["dgii_forms"]["606"] == "needs_review"

    kept = _declare(world, dossier["draft_id"], category="02")
    assert kept["dgii"]["category"] == "02"
    assert kept["dgii"]["category_suggested"] is False
    assert kept["expense_type_suggestion"] is None
    assert _month(world)["dgii_forms"]["606"] == "prepared_candidate"


def test_a_type_nobody_confirmed_is_no_choice(world) -> None:  # noqa: ANN001
    dossier = _purchase(
        world, world.alice, "B0100000071", category="02", category_suggested=True
    )
    assert _approve(world, dossier["draft_id"], dossier["version"], "expense").is_success
    assert (
        _purchase(world, world.alice, "B0100000072")["expense_type_suggestion"] is None
    )


def test_a_draft_with_its_own_choice_or_a_sale_shows_no_suggestion(world) -> None:  # noqa: ANN001
    _chosen(world, "B0100000081", "02")

    own = _purchase(world, world.alice, "B0100000082", category="03")
    assert own["expense_type_suggestion"] is None
    _, sale = _reviewed(world, "income", "B0100000083")
    assert sale["expense_type_suggestion"] is None


def test_the_last_choice_wins_and_an_unrelated_edit_moves_nothing(world) -> None:  # noqa: ANN001
    first = _chosen(world, "B0100000091", "02")
    _chosen(world, "B0100000092", "03")
    assert (
        _purchase(world, world.alice, "B0100000093")["expense_type_suggestion"] == "03"
    )

    _declare(world, first["draft_id"], paid_on="2026-09-10")
    assert (
        _purchase(world, world.alice, "B0100000094")["expense_type_suggestion"] == "03"
    )
    _declare(world, first["draft_id"], category="07")
    assert (
        _purchase(world, world.alice, "B0100000095")["expense_type_suggestion"] == "07"
    )


def test_a_suggestion_never_crosses_businesses(people) -> None:  # noqa: ANN001
    alice = people.alice
    dossier = _purchase(people, alice, "B0100000101", category="02")
    assert _approve(people, dossier["draft_id"], dossier["version"], "expense").is_success
    assert (
        _purchase(people, alice, "B0100000102")["expense_type_suggestion"] == "02"
    )

    assert (
        _purchase(people, people.bob, "B0100000103")["expense_type_suggestion"] is None
    )
    assert (
        _purchase(people, people.bob, "B0100000104", grant=people.grant_c)[
            "expense_type_suggestion"
        ]
        is None
    )


def _split(world, draft: str, version: int, headers=None, **split):  # noqa: ANN001, ANN003, ANN202
    return _review(
        world,
        draft,
        {"version": version, "payment_split": split},
        headers or world.alice.headers,
    )


def _sale(world, ncf: str = "B0100000111") -> tuple[str, dict]:  # noqa: ANN001
    return _recorded(
        world, "income", ncf, id_type="1", income_type="1", billed_amount="1000.00"
    )


def _dossier(world, draft: str) -> dict:  # noqa: ANN001
    return _get(world, f"/business/drafts/{draft}/dossier").json()


def test_a_split_written_after_approval_ships_the_607_and_export_freezes_it(world) -> None:  # noqa: ANN001
    _fiscal_profile(world)
    draft, _ = _sale(world)
    before = _dossier(world, draft)
    assert before["review_state"] == "accepted"
    assert before["payment_split_editable"] is True
    assert before["declaration_editable"] is False
    assert _month(world)["dgii_forms"]["607"] == "needs_review"
    money = _money_rows(world)

    answer = _split(world, draft, before["version"], cash="1180.00")

    assert answer.status_code == 200, answer.text
    after = answer.json()
    assert after["dgii"]["cash"] == "1180.00"
    assert after["dgii"]["income_type"] == "1"
    assert after["dgii"]["billed_amount"] == "1000.00"
    assert after["version"] == before["version"] + 1
    assert after["facts"] == before["facts"]
    assert _money_rows(world) == money
    assert _month(world)["dgii_forms"]["607"] == "prepared_candidate"

    files = _export(world)[2]
    assert "|1180.00|" in files["607"]
    frozen = _dossier(world, draft)
    assert frozen["payment_split_editable"] is False
    refused = _split(world, draft, frozen["version"], cash="1000.00", card="180.00")
    assert refused.status_code == 422, refused.text
    assert refused.json()["code"] == "fiscal_declaration_exported"
    assert _dossier(world, draft)["dgii"]["card"] is None


def test_each_write_changes_only_the_buckets_it_names(world) -> None:  # noqa: ANN001
    _fiscal_profile(world)
    draft, _ = _sale(world, "B0100000112")
    version = _dossier(world, draft)["version"]

    first = _split(world, draft, version, cash="1000.00").json()
    assert _month(world)["dgii_forms"]["607"] == "needs_review"
    second = _split(world, draft, first["version"], credit="180.00").json()
    assert (second["dgii"]["cash"], second["dgii"]["credit"]) == ("1000.00", "180.00")
    assert _month(world)["dgii_forms"]["607"] == "prepared_candidate"
    third = _split(world, draft, second["version"], credit=None).json()
    assert (third["dgii"]["cash"], third["dgii"]["credit"]) == ("1000.00", None)


def test_a_sale_with_no_declaration_gets_the_split_and_nothing_else(world) -> None:  # noqa: ANN001
    note = _post(world, "/business/captures", {"text": "venta"}, world.alice.headers)
    draft = note.json()["draft_id"]
    reviewed = _review(
        world,
        draft,
        {
            "version": note.json()["version"],
            "facts": _known(
                {
                    "kind": "income",
                    "amount": "1180.00",
                    "currency": "DOP",
                    "occurred_on": "2026-09-03",
                }
            ),
        },
        world.alice.headers,
    ).json()
    assert _approve(world, draft, reviewed["version"], "income").is_success
    before = _dossier(world, draft)
    assert (before["review_state"], before["dgii"]) == ("accepted", None)

    answer = _split(world, draft, before["version"], bank="1180.00")

    assert answer.status_code == 200, answer.text
    declared = answer.json()["dgii"]
    assert declared["form"] == "607"
    assert declared["bank"] == "1180.00"
    assert {
        name: value
        for name, value in declared.items()
        if name not in {"form", "bank"} and value is not None
    } == {}
    assert _month(world)["dgii_forms"]["607"] == "needs_review"


def test_a_purchase_takes_no_split(world) -> None:  # noqa: ANN001
    draft, _ = _recorded(world, "expense", "B0100000114")
    before = _dossier(world, draft)
    assert before["payment_split_editable"] is False

    refused = _split(world, draft, before["version"], cash="1180.00")

    assert refused.status_code == 422, refused.text
    assert refused.json()["code"] == "fiscal_direction_unsupported"
    assert _dossier(world, draft)["version"] == before["version"]


def test_an_open_sale_takes_the_split_on_the_same_route(world) -> None:  # noqa: ANN001
    draft, dossier = _reviewed(world, "income", "B0100000115")
    assert dossier["payment_split_editable"] is True

    answer = _split(world, draft, dossier["version"], cash="1180.00")

    assert answer.status_code == 200, answer.text
    assert answer.json()["review_state"] == "open"
    assert answer.json()["dgii"]["cash"] == "1180.00"


def test_someone_who_prepares_writes_the_split_and_a_stale_write_is_refused(world) -> None:  # noqa: ANN001
    draft, _ = _sale(world, "B0100000116")
    version = _dossier(world, draft)["version"]

    written = _split(
        world, draft, version, _as(world.bob, world.grant), cash="1180.00"
    )
    assert written.status_code == 200, written.text
    stale = _split(world, draft, version, cash="1000.00")
    assert stale.status_code == 409, stale.text
    assert _dossier(world, draft)["dgii"]["cash"] == "1180.00"


def test_the_model_reads_neither_the_suggestion_nor_the_split(actions) -> None:  # noqa: ANN001
    from argus.domain.business.contracts.dgii import SalePaymentSplit

    service, context, _ = actions
    note = service.capture(context, CaptureNote(text="venta"), str(uuid4()))
    facts = BusinessFactPatch.model_validate(_known({"kind": "income"}))
    typed = service.review(
        context,
        note.draft_id,
        ReviewDraft(version=note.version, facts=facts),
        str(uuid4()),
    )
    assert typed.outcome == "applied", typed
    split = service.review(
        context,
        note.draft_id,
        ReviewDraft(
            version=typed.version, payment_split=SalePaymentSplit(cash="100.00")
        ),
        str(uuid4()),
    )
    assert split.outcome == "applied", split

    dossier = service.dossier(context, note.draft_id)
    assert dossier.payment_split_editable is True
    view = dossier.model_facing()
    assert not {"expense_type_suggestion", "payment_split_editable"} & set(view)
    assert all("payment_split" not in source.get("text", "") for source in view["sources"])
    assert any(source["kind"] == "web_action" for source in view["sources"])
