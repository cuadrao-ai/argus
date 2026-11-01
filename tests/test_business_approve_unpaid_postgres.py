"""Over HTTP, on the real app, Auth and Postgres, in a new Business with no
account: a purchase and a sale are approved with no payment answer, the row
stores no account and no funding, every read carries it, payment is a later
step that writes only its settlement, and Forma de Pago stays blank until a
person sets it."""

from __future__ import annotations

import csv
import io
import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from zipfile import ZipFile

import pytest
from argus.domain.business.contracts.actions import (
    ApproveExpense,
    ApproveIncome,
    ProposeActivity,
)
from argus.domain.business.contracts.dgii import PurchaseDeclaration, SalesDeclaration
from argus.domain.business.contracts.facts import BusinessFactPatch
from argus.domain.business.dgii_columns import PURCHASE_COLUMNS
from psycopg import Connection

from tests import test_business_actions_postgres as business
from tests import test_business_fiscal_routes_postgres as routes
from tests import test_financial_accounts_postgres as shared
from tests.test_business_fiscal_routes_postgres import _known, _review
from tests.test_business_scope_switch_routes_postgres import API, _note
from tests.test_business_scope_switch_routes_postgres import (
    pytestmark as _local_supabase,
)

actions = business.actions
users = business.users
world = routes.world
pytestmark = _local_supabase
FILER = "199990013"
BUYER_OR_SUPPLIER = "199990021"
MONTH = "2026-09"
SPAN = {"from": "2026-09-01", "to": "2026-09-30"}
EXPORT = {"start": "2026-09-01", "end": "2026-09-30"}
ACTION = {"expense": "record_expense", "income": "record_income"}
FORM = {"expense": "606", "income": "607"}
KINDS = sorted(ACTION)


def _get(world, path: str, **params):  # noqa: ANN001, ANN202
    answer = world.client.get(f"{API}{path}", params=params, headers=world.alice.headers)
    assert answer.status_code == 200, (path, answer.text)
    return answer


def _declaration(kind: str, **chosen) -> dict:
    model = PurchaseDeclaration if kind == "expense" else SalesDeclaration
    blank = dict.fromkeys(model.model_fields)
    if kind == "expense":
        blank.update(actual_refund=False, category_suggested=False)
    return {**blank, "form": FORM[kind], **chosen}


def _reviewed(  # noqa: ANN202
    world,  # noqa: ANN001
    kind: str,
    ncf: str,
    facts: dict | None = None,
    **declared,
):
    """A draft with its read facts and nothing on how it was paid or whose it is."""

    note = _note(world, world.alice, f"Documento {ncf}")
    assert note.status_code == 200, note.text
    draft = note.json()["draft_id"]
    version = _get(world, f"/business/drafts/{draft}/dossier").json()["version"]
    answer = _review(
        world,
        draft,
        {
            "version": version,
            "facts": {
                **_known(
                    {
                        "kind": kind,
                        "amount": "1180.00",
                        "currency": "DOP",
                        "occurred_on": "2026-09-03",
                        "counterparty": "Ferretería Prueba",
                    }
                ),
                **(facts or {}),
            },
            "dgii": {
                "fiscal": {
                    "rnc": BUYER_OR_SUPPLIER,
                    "ncf": ncf,
                    "itbis": "180.00",
                },
                "declaration": _declaration(kind, **declared),
            },
        },
        world.alice.headers,
    )
    assert answer.status_code == 200, answer.text
    return draft, answer.json()


def _approve(world, draft: str, version: int, kind: str, key: str | None = None):  # noqa: ANN001, ANN202
    return world.client.post(
        f"{API}/business/drafts/{draft}/approve",
        json={"version": version, "action": ACTION[kind]},
        headers={**world.alice.headers, "Idempotency-Key": key or str(uuid4())},
    )


def _recorded(world, kind: str, ncf: str, **declared) -> tuple[str, dict]:  # noqa: ANN001
    draft, dossier = _reviewed(world, kind, ncf, **declared)
    answer = _approve(world, draft, dossier["version"], kind)
    assert answer.status_code == 200, answer.text
    return draft, answer.json()


def _ledger(activity: str) -> list[tuple]:
    with Connection.connect(shared.DSN) as db:
        return db.execute(
            "select r.account_id,r.funding,r.record_kind,g.kind,r.currency,v.amount_minor"
            " from public.financial_activity_memberships m"
            " join public.financial_activity_groups g on g.id=m.activity_id"
            " join public.financial_records r on r.id=m.record_id"
            " join public.financial_record_revisions v on v.record_id=r.id"
            " where m.activity_id=%s",
            (activity,),
        ).fetchall()


def _counts(world) -> tuple[int, int, int]:  # noqa: ANN001
    """The Business's records, accounts and stored settlements."""

    with Connection.connect(shared.DSN) as db:
        space = world.alice.space_id
        return (
            db.execute(
                "select count(*) from public.financial_records where owner_space_id=%s",
                (space,),
            ).fetchone()[0],
            db.execute(
                "select count(*) from public.financial_accounts where owner_space_id=%s",
                (space,),
            ).fetchone()[0],
            db.execute(
                "select count(*) from public.business_document_settlements where space_id=%s",
                (space,),
            ).fetchone()[0],
        )


def _fiscal_profile(world) -> None:  # noqa: ANN001
    answer = world.client.patch(
        f"{API}/business/fiscal-profile",
        json={
            "name": "Ferretería Prueba",
            "previous_name": "Ferretería Prueba",
            "tax_id": {"type": "rnc", "value": FILER},
            "previous_tax_id": None,
        },
        headers={**world.alice.headers, "Idempotency-Key": str(uuid4())},
    )
    assert answer.status_code == 200, answer.text


def _month(world) -> dict:  # noqa: ANN001
    return _get(world, "/business/month-close", month=MONTH).json()


def _block(month: dict, currency: str = "DOP") -> dict:
    return next(item for item in month["currencies"] if item["currency"] == currency)


def _ids(lines: list[dict]) -> list[str]:
    return [line["activity_id"] for line in lines]


def _report(world) -> dict:  # noqa: ANN001
    answer = world.client.post(
        f"{API}/business/reports/query", json={}, headers=world.alice.headers
    )
    assert answer.status_code == 200, answer.text
    [row] = answer.json()["items"]
    return row


def _export(world) -> tuple[dict, list[dict], dict[str, str]]:  # noqa: ANN001
    """The package's manifest, records.csv rows and DGII TXT files by form."""

    with ZipFile(
        io.BytesIO(_get(world, "/business/exports", **EXPORT).content)
    ) as zipped:
        rows = list(
            csv.DictReader(io.StringIO(zipped.read("records.csv").decode("utf-8-sig")))
        )
        files = {
            form: zipped.read(name).decode()
            for form in FORM.values()
            if (name := f"dgii/DGII_F_{form}_{FILER}_202609.TXT") in zipped.namelist()
        }
        return json.loads(zipped.read("manifest.json")), rows, files


def _settle(world, activity: str, status: str, method: str) -> dict:  # noqa: ANN001
    answer = world.client.patch(
        f"{API}/business/month-close/documents/{activity}",
        json={"status": status, "settled_on": "2026-09-20", "payment_method": method},
        headers={**world.alice.headers, "Idempotency-Key": str(uuid4())},
    )
    assert answer.status_code == 200, answer.text
    return answer.json()


def _declare(world, draft: str, **purchase) -> dict:  # noqa: ANN001
    version = _get(world, f"/business/drafts/{draft}/dossier").json()["version"]
    answer = _review(
        world, draft, {"version": version, "purchase": purchase}, world.alice.headers
    )
    assert answer.status_code == 200, answer.text
    return answer.json()


@pytest.mark.parametrize("kind", KINDS)
def test_approval_needs_no_account_and_no_payment_answer(world, kind: str) -> None:  # noqa: ANN001
    assert _get(world, "/business/workspace").json()["accounts"] == []
    draft, dossier = _reviewed(world, kind, "B0100000011")
    assert dossier["facts"]["funding"]["state"] == "unknown"
    assert dossier["facts"]["business_share"]["state"] == "unknown"
    assert dossier["blockers"] == []
    assert dossier["approval_available"] is True
    assert dossier["approval_action"] == ACTION[kind]

    answer = _approve(world, draft, dossier["version"], kind)
    assert answer.status_code == 200, answer.text
    activity = answer.json()["approval_result"]["activity_id"]
    assert _ledger(activity) == [(None, None, kind, kind, "DOP", 118000)]
    assert _counts(world) == (1, 0, 0)
    assert answer.json()["review_state"] == "accepted"


@pytest.mark.parametrize("kind", KINDS)
def test_a_person_who_does_not_know_how_it_was_paid_approves_the_same_way(
    world,  # noqa: ANN001
    kind: str,
) -> None:
    draft, dossier = _reviewed(
        world,
        kind,
        "B0100000012",
        {"funding": {"state": "owner_does_not_know", "value": None}},
    )
    assert dossier["facts"]["funding"]["state"] == "owner_does_not_know"
    assert dossier["blockers"] == []
    answer = _approve(world, draft, dossier["version"], kind)
    assert answer.status_code == 200, answer.text
    activity = answer.json()["approval_result"]["activity_id"]
    assert _ledger(activity) == [(None, None, kind, kind, "DOP", 118000)]


@pytest.mark.parametrize("kind", KINDS)
def test_replay_and_concurrent_approvals_record_one_row(world, kind: str) -> None:  # noqa: ANN001
    draft, dossier = _reviewed(world, kind, "B0100000013")
    version = dossier["version"]
    keys = ["one-key", "one-key", str(uuid4()), str(uuid4())]
    with ThreadPoolExecutor(max_workers=len(keys)) as pool:
        answers = list(
            pool.map(lambda key: _approve(world, draft, version, kind, key), keys)
        )
    won = {
        answer.json()["approval_result"]["activity_id"]
        for answer in answers
        if answer.status_code == 200
    }
    assert len(won) == 1, [answer.text for answer in answers]
    assert _counts(world) == (1, 0, 0)

    first = next(answer for answer in answers if answer.status_code == 200)
    winning_key = keys[answers.index(first)]
    replay = _approve(world, draft, version, kind, winning_key)
    assert replay.status_code == 200, replay.text
    assert replay.json()["approval_result"]["activity_id"] in won
    assert _counts(world) == (1, 0, 0)
    assert len(_get(world, "/business/expenses", kind=kind, **SPAN).json()["items"]) == 1


@pytest.mark.owner_acts
@pytest.mark.parametrize(
    ("kind", "command", "approve"),
    [
        ("expense", ApproveExpense(version=1, action="record_expense"), "approve"),
        ("income", ApproveIncome(version=1, action="record_income"), "approve_income"),
    ],
)
def test_a_lost_acknowledgement_reuses_the_one_row(
    actions,  # noqa: ANN001
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    command,  # noqa: ANN001
    approve: str,
) -> None:
    service, context, _ = actions
    evidence = business.source(service, context, "Documento sin cuenta")
    facts = BusinessFactPatch.model_validate(
        _known(
            {
                "kind": kind,
                "amount": "500",
                "currency": "DOP",
                "occurred_on": "2026-10-09",
            }
        )
    )
    key, lease = business.prepare(
        service, context, [ProposeActivity(facts=facts, source_ids=(evidence,))]
    )
    draft = service.execute(context, key, 0, lease=lease).draft_id
    original = service.imports._write

    def interrupted(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        original(*args, **kwargs)
        raise ConnectionError("Synthetic lost acknowledgement after the money commit")

    run = getattr(service, approve)
    monkeypatch.setattr(service.imports, "_write", interrupted)
    assert run(context, draft, command, "lost").outcome == "outcome_unknown"
    monkeypatch.setattr(service.imports, "_write", original)
    recovered = run(context, draft, command, "lost")
    assert recovered.outcome == "applied"
    assert run(context, draft, command, "lost") == recovered
    assert _ledger(str(recovered.activity_id)) == [(None, None, kind, kind, "DOP", 50000)]
    with service.authority.pool.connection() as db:
        assert (
            db.execute(
                "select count(*) from public.financial_records where owner_space_id=%s",
                (context.actor.space_id,),
            ).fetchone()[0]
            == 1
        )


def test_an_unpaid_purchase_reads_everywhere_and_forma_de_pago_stays_blank(world) -> None:  # noqa: ANN001
    _fiscal_profile(world)
    draft, recorded = _recorded(world, "expense", "B0100000021")
    activity = recorded["approval_result"]["activity_id"]
    assert recorded["dgii"]["id_type"] == "1"
    assert recorded["dgii"]["payment_method"] is None

    month = _month(world)
    block = _block(month)
    assert block["expense_before_itbis_minor"] == 100000
    assert block["itbis_paid_minor"] == 18000
    assert block["net_result_minor"] == -100000
    assert block["cuentas_por_pagar_minor"] == 118000
    assert block["net_result_final"] is False
    assert month["dgii_forms"]["606"] == "needs_review"
    assert _ids(month["cuentas_por_pagar"]) == [activity]
    assert _ids(month["missing_payment_form"]) == [activity]
    assert month["missing_payment_form"][0]["payment_form"] is None

    opened = _get(world, "/business/open-items").json()["cuentas_por_pagar"]
    assert opened["count"] == 1
    assert opened["totals"][0]["total_minor"] == 118000
    assert [item["payment_form"] for item in opened["items"]] == [None]

    [expense] = _get(world, "/business/expenses", **SPAN).json()["items"]
    assert expense["id"] == activity and expense["account_id"] is None
    assert "funding" not in expense
    detail = _get(world, f"/business/expenses/{activity}").json()
    assert detail["account_id"] is None and detail.get("funding") is None
    overview = _get(world, "/business/overview", **SPAN).json()
    assert overview["totals"] == [{"currency": "DOP", "amount": "1180.00", "count": 1}]
    feed = _get(world, "/business/activity").text
    assert draft in feed or activity in feed
    assert activity in _get(world, "/business/search", q="Ferretería").text

    row = _report(world)
    assert row["stage"] == "needs_fiscal_data"
    assert row["funding_key"] is None
    assert row["gross_amount"] == "1180"
    assert row["export_missing"] == "expense_type_missing"
    assert row["export_missing_several"] is True

    manifest, rows, files = _export(world)
    assert [(item["Forma de pago"], item["Pago"]) for item in rows] == [("", "pendiente")]
    [canonical] = manifest["records"]
    assert canonical["funding"] == "unknown"
    assert canonical["account_ids"] == ""
    assert files == {}

    _declare(world, draft, category="02")
    assert _report(world)["export_missing"] == "payment_method_missing"
    assert _report(world)["export_missing_several"] is False
    assert _month(world)["dgii_forms"]["606"] == "needs_review"
    assert _ids(_month(world)["missing_payment_form"]) == [activity]
    assert _export(world)[2] == {}

    settled = _settle(world, activity, "pagado", "efectivo")
    assert settled["status"] == "pagado"
    assert _counts(world) == (1, 0, 1)
    assert _ledger(activity) == [(None, None, "expense", "expense", "DOP", 118000)]
    month = _month(world)
    assert _block(month)["cuentas_por_pagar_minor"] == 0
    assert _block(month)["net_result_final"] is True
    assert _get(world, "/business/open-items").json()["cuentas_por_pagar"]["count"] == 0
    assert (
        _get(world, f"/business/drafts/{draft}/dossier").json()["dgii"]["payment_method"]
        is None
    )
    assert _ids(month["missing_payment_form"]) == [activity]
    assert [item["Pago"] for item in _export(world)[1]] == ["pagado"]

    _declare(world, draft, payment_method="01")
    month = _month(world)
    assert month["dgii_forms"]["606"] == "prepared_candidate"
    assert month["missing_payment_form"] == []
    _, rows, files = _export(world)
    assert [item["Forma de pago"] for item in rows] == ["01"]
    header, line = files["606"].strip().split("\r\n")
    columns = dict(
        zip((name for name, _ in PURCHASE_COLUMNS), line.split("|"), strict=True)
    )
    assert header.startswith("606|")
    assert columns["payment_method"] == "01"
    assert columns["ncf"] == "B0100000021"


def test_month_close_lists_no_form_for_a_purchase_the_606_leaves_out(world) -> None:  # noqa: ANN001
    _fiscal_profile(world)
    _recorded(world, "expense", "B0200000022")
    month = _month(world)
    assert month["dgii_forms"]["606"] in {"no_aplica", "no_operations", "summary_only"}
    assert month["missing_payment_form"] == []


def test_an_unpaid_sale_reads_everywhere_and_is_collected(world) -> None:  # noqa: ANN001
    _fiscal_profile(world)
    _, recorded = _recorded(
        world,
        "income",
        "B0100000031",
        id_type="1",
        income_type="1",
        billed_amount="1000.00",
        credit="1180.00",
    )
    activity = recorded["approval_result"]["activity_id"]

    month = _month(world)
    block = _block(month)
    assert block["income_before_itbis_minor"] == 100000
    assert block["itbis_charged_minor"] == 18000
    assert block["itbis_cobrado_minor"] == 0
    assert block["cuentas_por_cobrar_minor"] == 118000
    assert block["net_result_final"] is False
    assert month["dgii_forms"]["607"] == "prepared_candidate"
    assert month["missing_payment_form"] == []
    opened = _get(world, "/business/open-items").json()["cuentas_por_cobrar"]
    assert opened["count"] == 1 and opened["items"][0]["activity_id"] == activity

    [sale] = _get(world, "/business/expenses", kind="income", **SPAN).json()["items"]
    assert sale["id"] == activity and sale["account_id"] is None
    assert _get(world, "/business/expenses", **SPAN).json()["items"] == []
    assert _get(world, "/business/overview", **SPAN).status_code == 200
    assert _get(world, "/business/activity").status_code == 200
    assert activity in _get(world, "/business/search", q="Ferretería").text
    row = _report(world)
    assert row["money_kind"] == "income" and row["funding_key"] is None

    manifest, rows, files = _export(world)
    assert [item["Pago"] for item in rows] == ["pendiente"]
    assert manifest["records"][0]["funding"] == "unknown"
    assert "B0100000031" in files["607"]

    settled = _settle(world, activity, "cobrado", "transferencia")
    assert (settled["document_kind"], settled["status"]) == ("invoice", "cobrado")
    assert _ledger(activity) == [(None, None, "income", "income", "DOP", 118000)]
    assert _counts(world) == (1, 0, 1)
    block = _block(_month(world))
    assert block["itbis_cobrado_minor"] == 18000
    assert block["cuentas_por_cobrar_minor"] == 0
    assert block["net_result_final"] is True


def test_a_sale_with_no_payment_split_holds_the_607_with_nothing_invented(world) -> None:  # noqa: ANN001
    _fiscal_profile(world)
    draft, _ = _recorded(
        world,
        "income",
        "B0100000032",
        id_type="1",
        income_type="1",
        billed_amount="1000.00",
    )
    dossier = _get(world, f"/business/drafts/{draft}/dossier").json()
    assert all(
        dossier["dgii"][name] is None
        for name in ("cash", "bank", "card", "credit", "gift", "barter", "other_payment")
    )
    assert _month(world)["dgii_forms"]["607"] == "needs_review"
    assert _export(world)[2] == {}


def test_a_purchase_in_dollars_keeps_its_currency_with_no_account(world) -> None:  # noqa: ANN001
    draft, dossier = _reviewed(
        world, "expense", "B0100000023", _known({"currency": "USD"})
    )
    assert dossier["blockers"] == []
    answer = _approve(world, draft, dossier["version"], "expense")
    assert answer.status_code == 200, answer.text
    assert _ledger(answer.json()["approval_result"]["activity_id"]) == [
        (None, None, "expense", "expense", "USD", 118000)
    ]
    assert _block(_month(world), "USD")["net_result_final"] is False


def test_a_personal_mark_with_no_funding_stays_out_of_the_totals(world) -> None:  # noqa: ANN001
    draft, dossier = _reviewed(
        world,
        "expense",
        "B0100000041",
        _known({"business_share": {"kind": "none"}}),
    )
    assert dossier["blockers"] == []
    answer = _approve(world, draft, dossier["version"], "expense")
    assert answer.status_code == 200, answer.text
    assert _ledger(answer.json()["approval_result"]["activity_id"]) == [
        (None, None, "expense", "expense", "DOP", 118000)
    ]
    month = _month(world)
    assert month["currencies"] == [] or _block(month)["expense_before_itbis_minor"] == 0
    assert month["missing_payment_form"] == []


def test_a_refund_stays_account_only_and_refunds_no_record_without_one(world) -> None:  # noqa: ANN001
    _recorded(world, "expense", "B0100000051")
    note = _note(world, world.alice, "Nota de crédito")
    assert note.status_code == 200, note.text
    draft = note.json()["draft_id"]
    version = _get(world, f"/business/drafts/{draft}/dossier").json()["version"]
    answer = _review(
        world,
        draft,
        {
            "version": version,
            "facts": _known(
                {
                    "kind": "refund",
                    "amount": "100.00",
                    "currency": "DOP",
                    "occurred_on": "2026-09-05",
                    "counterparty": "Ferretería Prueba",
                }
            ),
        },
        world.alice.headers,
    )
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["blockers"] == [{"code": "fact_required", "field": "funding"}]
    assert body["approval_available"] is False
    assert body["refund_candidates"] == []


@pytest.mark.parametrize("ncf", ["B0400000052", "E340000000053"])
@pytest.mark.parametrize("kind", KINDS)
def test_a_credit_number_read_as_a_purchase_or_a_sale_stays_account_only(
    world,  # noqa: ANN001
    kind: str,
    ncf: str,
) -> None:
    draft, dossier = _reviewed(world, kind, ncf)
    assert dossier["blockers"] == [{"code": "fact_required", "field": "funding"}]
    refused = _approve(world, draft, dossier["version"], kind)
    assert refused.status_code == 422, refused.text
    assert refused.json()["code"] == "fact_required"
    assert _counts(world) == (0, 0, 0)


def test_income_stays_refused_on_the_owners_money(world) -> None:  # noqa: ANN001
    draft, dossier = _reviewed(
        world,
        "income",
        "B0100000061",
        _known({"funding": {"kind": "owner_funds"}}),
    )
    assert dossier["blockers"] == [
        {"code": "business_funding_unsupported", "field": "funding"}
    ]
    refused = _approve(world, draft, dossier["version"], "income")
    assert refused.status_code == 422, refused.text
    assert refused.json()["code"] == "business_funding_unsupported"
    assert _counts(world) == (0, 0, 0)
