"""An owner's accepted correction reaches the ledger, history, feed and exports."""

from decimal import Decimal
from uuid import uuid4

import pytest
from psycopg import Connection

from tests import test_business_actions_postgres as shared
from tests import test_business_approve_unpaid_postgres as approvals
from tests.test_business_approve_unpaid_postgres import (
    SPAN,
    _block,
    _export,
    _fiscal_profile,
    _get,
    _month,
    _recorded,
    _report,
    _settle,
)
from tests.test_business_fiscal_routes_postgres import dgii_file
from tests.test_business_scope_switch_routes_postgres import API, GRANT
from tests.test_business_scope_switch_routes_postgres import pytestmark as local_supabase
from tests.test_financial_accounts_postgres import DSN

pytestmark = [local_supabase, pytest.mark.usefixtures("typed_notes_on", "settlement_on")]
world = approvals.world
users = shared.users
actions = shared.actions
NCF = "B0100000071"


@pytest.fixture
def purchase(world):
    _fiscal_profile(world)
    draft, _ = _recorded(world, "expense", NCF, category="02", payment_method="01")
    return draft, _get(world, f"/business/drafts/{draft}/dossier").json()


def current_revision(activity):
    with Connection.connect(DSN) as db:
        return db.execute(
            "select current_revision from public.financial_activity_groups where id=%s",
            (activity,),
        ).fetchone()[0]


def review(world, draft, before, patch, *, key=None, headers=None):
    return world.client.patch(
        f"{API}/business/drafts/{draft}/review",
        json={"version": before["version"], **patch},
        headers={
            **(headers or world.alice.headers),
            "Idempotency-Key": key or str(uuid4()),
        },
    )


def fiscal(before, **changes):
    return {
        "dgii": {
            "fiscal": {
                "rnc": approvals.BUYER_OR_SUPPLIER,
                "ncf": NCF,
                "itbis": "180.00",
                **changes,
            },
            "declaration": before["dgii"],
        }
    }


@pytest.mark.parametrize(
    "field",
    ["amount", "occurred_on", "document_type", "counterparty", "ncf", "payment_method"],
)
def test_accepted_review_updates_one_activity_history_and_feed(world, purchase, field):
    draft, before = purchase
    activity = before["approval_result"]["activity_id"]
    revision = current_revision(activity)
    feed = _get(world, "/business/activity").json()["items"]
    changes = {
        "amount": {"facts": {"amount": {"state": "known", "value": "1380.00"}}},
        "occurred_on": {
            "facts": {"occurred_on": {"state": "known", "value": "2026-09-14"}}
        },
        "document_type": {
            "document_type": "venta",
            "dgii": {
                "fiscal": fiscal(before)["dgii"]["fiscal"],
                "declaration": approvals._declaration(
                    "income",
                    id_type="1",
                    income_type="1",
                    billed_amount="1000.00",
                    credit="1180.00",
                ),
            },
        },
        "ncf": fiscal(before, ncf="B0100000072"),
        "counterparty": {
            "facts": {"counterparty": {"state": "known", "value": "Colmado Prueba"}}
        },
        "payment_method": {"purchase": {"payment_method": "02"}},
    }
    key = str(uuid4())
    saved = review(world, draft, before, changes[field], key=key)
    assert saved.status_code == 200, saved.text
    replay = review(world, draft, before, changes[field], key=key)
    assert replay.status_code == 200 and replay.json() == saved.json()
    after = _get(world, f"/business/drafts/{draft}/dossier").json()
    assert after["review_state"] == "accepted"
    assert after["facts_editable"] and after["document_type_editable"]
    assert {"amount", "currency", "document_type", "occurred_on", "counterparty"} <= set(
        after["editable_fields"]
    )
    assert "reopen_available" not in after
    assert after["approval_result"] == before["approval_result"]
    assert after["version"] == before["version"] + 1
    changes_money = field in {"amount", "occurred_on", "document_type", "counterparty"}
    assert current_revision(activity) == revision + int(changes_money)
    assert after["history"][:-1] == before["history"]
    diff = after["history"][-1]
    assert diff["before"] == before["facts"] and diff["after"] == after["facts"]
    if field == "payment_method":
        assert (
            diff["before_dgii"]["payment_method"],
            diff["after_dgii"]["payment_method"],
        ) == ("01", "02")
    else:
        assert diff["before"] != diff["after"]
    latest = _get(world, "/business/activity").json()["items"]
    assert len(latest) == len(feed) + 1
    assert latest[0]["action"] == "review_draft"
    assert latest[0]["object"]["id"] == draft
    row = _report(world)
    manifest, records, _ = _export(world)
    [record] = records
    if field == "document_type":
        assert (diff["before_document_type"], diff["after_document_type"]) == (
            "recibo",
            "venta",
        )
        assert after["document_type"] == "venta"
        assert row["money_kind"] == "income"
        assert dgii_file(world, "purchase") == []
        [sale] = dgii_file(world, "sale")
        assert sale["Número Comprobante Fiscal"] == NCF
    else:
        assert manifest["dgii"]["issues"] == []
        [line] = dgii_file(world, "purchase")
        if field == "amount":
            assert Decimal(row["gross_amount"]) == Decimal(record["Total"]) == 1380
            assert _block(_month(world))["expense_before_itbis_minor"] == 120000
            assert (
                _get(world, "/business/overview", **SPAN).json()["totals"][0]["amount"]
                == "1380.00"
            )
            assert line["Total Monto Facturado"] == "1200.00"
        elif field == "occurred_on":
            assert row["report_date"] == "2026-09-14"
            assert (
                line["Fecha Comprobante (AAAAMM)"],
                line["Fecha Comprobante (DD)"],
            ) == ("202609", "14")
            assert line["Fecha Pago (DD)"] == "14"
        elif field == "counterparty":
            assert row["counterparty"] == record["Proveedor"] == "Colmado Prueba"
        elif field == "payment_method":
            assert line["Forma de Pago"].startswith("02")
        else:
            assert record["NCF"] == line["NCF"] == "B0100000072"


@pytest.mark.parametrize("field", ["amount", "currency", "occurred_on"])
def test_required_accepted_fact_cannot_be_cleared(world, purchase, field):
    draft, before = purchase
    activity = before["approval_result"]["activity_id"]
    revision = current_revision(activity)
    result = review(world, draft, before, {"facts": {field: {"state": "unknown"}}})
    assert (
        result.status_code == 422 and result.json()["code"] == "fact_required"
    ), result.text
    assert _get(world, f"/business/drafts/{draft}/dossier").json() == before
    assert current_revision(activity) == revision


@pytest.mark.parametrize("value", [None, "0.00"])
def test_optional_accepted_amounts_can_be_empty_or_zero(world, purchase, value):
    draft, before = purchase
    patch = fiscal(before, itbis=value)
    patch["montos"] = {
        "net_amount": {"state": "known" if value else "unknown", "value": value}
    }
    saved = review(world, draft, before, patch)
    assert saved.status_code == 200, saved.text
    facts = saved.json()["facts"]
    for saved_value in (facts["net_amount"]["value"], facts["fiscal"]["itbis"]["value"]):
        if value is None:
            assert saved_value is None
        else:
            assert Decimal(saved_value) == Decimal(value)


def test_linked_record_refuses_money_changes(world, purchase):
    draft, before = purchase
    activity = before["approval_result"]["activity_id"]
    _settle(world, activity, "pagado", "efectivo")
    before = _get(world, f"/business/drafts/{draft}/dossier").json()
    fields = set(before["editable_fields"])
    assert fields.isdisjoint({"amount", "currency", "occurred_on", "counterparty", "document_type"})
    assert {"rnc", "fiscal_number", "itbis"} <= fields
    assert not before["document_type_editable"]
    assert before["declaration_editable"]
    revision = current_revision(activity)
    saved = review(
        world,
        draft,
        before,
        {"facts": {"amount": {"state": "known", "value": "1800.00"}}},
    )
    assert (
        saved.status_code == 422 and saved.json()["code"] == "business_document_linked"
    ), saved.text
    assert _get(world, f"/business/drafts/{draft}/dossier").json() == before
    assert current_revision(activity) == revision


def test_prepare_grant_cannot_edit_accepted_record(world, purchase):
    draft, before = purchase
    headers = {**world.bob.headers, GRANT: world.grant}
    path = f"{API}/business/drafts/{draft}/dossier"
    guest = world.client.get(path, headers=headers).json()
    assert not guest["facts_editable"] and not guest["document_type_editable"]
    assert not guest["declaration_editable"]
    assert guest["editable_fields"] == []
    result = review(
        world, draft, before, {"purchase": {"category": "09"}}, headers=headers
    )
    assert result.status_code == 403, result.text
    assert _get(world, f"/business/drafts/{draft}/dossier").json() == before


def test_purchase_named_by_open_refund_refuses_an_amount_change(world, purchase):
    draft, before = purchase
    activity = before["approval_result"]["activity_id"]
    approvals._reviewed(
        world,
        "expense",
        "B0400000073",
        facts={"kind": {"state": "known", "value": "refund"}},
        actual_refund=True,
        purchase_activity_id=activity,
    )
    saved = review(
        world,
        draft,
        before,
        {"facts": {"amount": {"state": "known", "value": "1500.00"}}},
    )
    assert (
        saved.status_code == 422 and saved.json()["code"] == "business_document_linked"
    ), saved.text
    assert current_revision(activity) == 1


def test_fiscal_correction_cannot_take_another_accepted_number(world, purchase):
    draft, before = purchase
    other_ncf = "B0100000074"
    other, _ = _recorded(world, "expense", other_ncf)
    result = review(world, draft, before, fiscal(before, ncf=other_ncf))
    assert (
        result.status_code == 422 and result.json()["code"] == "duplicate_comprobante"
    ), result.text
    assert result.json()["context"]["existing_record_id"] == other
    assert current_revision(before["approval_result"]["activity_id"]) == 1
    assert _get(world, f"/business/drafts/{draft}/dossier").json() == before


def test_corrected_currency_must_be_supported(world, purchase):
    draft, before = purchase
    result = review(
        world, draft, before, {"facts": {"currency": {"state": "known", "value": "ZZZ"}}}
    )
    assert (
        result.status_code == 422 and result.json()["code"] == "currency_unsupported"
    ), result.text
    assert current_revision(before["approval_result"]["activity_id"]) == 1


@pytest.mark.owner_acts
@pytest.mark.parametrize("funded", [True, False], ids=["business-account", "owner-funds"])
def test_money_history_preserves_previous_posting(actions, users, funded):
    from argus.domain.business.contracts.actions import ReviewDraft

    from tests import test_business_declaration_after_approval_postgres as records

    service, owner, _ = actions
    funding = (
        records.account_funding(records.cash_account(service, owner))
        if funded
        else {"kind": "owner_funds"}
    )
    draft, version = records.captured(service, owner, NCF, funding)
    before = records.approved(service, owner, draft, version)
    activity = str(before.approval_result.activity_id)
    assert "amount" in before.editable_fields
    assert ("currency" in before.editable_fields) is not funded
    field, value = ("amount", "1280.00") if funded else ("currency", "USD")
    with service.authority.pool.connection() as db:
        db.execute(
            "insert into public.business_client_grants(space_id,grantee_id,issuer_id,business_role,capabilities)"
            " values (%s,%s,%s,'owner',array['read','prepare','approve'])",
            (owner.actor.space_id, users["other"], owner.owner_id),
        )
    editor = service.resolve_actor(
        shared.TrustedActor(
            actor_id=users["other"], actor_kind="member", space_id=owner.actor.space_id
        )
    )
    result = service.review(
        editor,
        draft,
        ReviewDraft(
            version=before.version, facts={field: {"state": "known", "value": value}}
        ),
        str(uuid4()),
    )
    assert result.outcome == "applied", result
    current, original = service.imports.money.history(
        user_id=owner.owner_id, activity_id=activity, scope=owner.scope
    )["items"]
    assert (current["revision"], original["revision"]) == (2, 1)
    assert (original["amount"], original["currency"]) == ("1180.00", "DOP")
    assert current[field] == value
    assert (current["recorded_by"], original["recorded_by"]) == (
        str(editor.actor.actor_id),
        owner.owner_id,
    )
    if funded:
        assert (
            current["legs"][0]["account_id"]
            == original["legs"][0]["account_id"]
            == funding["account_id"]
        )
    else:
        assert current["funding"] == original["funding"] == "owner_funds"


@pytest.mark.parametrize(
    "field,value", [("funding", {"kind": "owner_funds"}), ("category_id", "groceries")]
)
def test_accepted_posting_keeps_its_funding_and_ledger_category(
    world, purchase, field, value
):
    draft, before = purchase
    result = review(
        world, draft, before, {"facts": {field: {"state": "known", "value": value}}}
    )
    assert (
        result.status_code == 422
        and result.json()["code"] == "recorded_correction_unsupported"
    ), result.text
    assert _get(world, f"/business/drafts/{draft}/dossier").json() == before
    assert current_revision(before["approval_result"]["activity_id"]) == 1


def test_record_moves_to_corrected_month_and_keeps_manual_payment_date(world):
    _fiscal_profile(world)
    draft, before = _recorded(
        world, "expense", NCF, category="02", payment_method="01", paid_on="2026-10-18"
    )
    saved = review(
        world,
        draft,
        before,
        {"facts": {"occurred_on": {"state": "known", "value": "2026-10-14"}}},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["dgii"]["paid_on"] == "2026-10-18"
    assert _get(world, "/business/overview", **SPAN).json()["totals"] == []
    totals = _get(
        world, "/business/overview", **{"from": "2026-10-01", "to": "2026-10-31"}
    ).json()["totals"]
    assert totals == [{"currency": "DOP", "amount": "1180.00", "count": 1}]
    assert _export(world)[1] == []
    assert _report(world)["report_date"] == "2026-10-14"


def test_normalized_counterparty_uses_the_existing_posting(world, purchase):
    draft, before = purchase
    name = before["facts"]["counterparty"]["value"]
    activity = before["approval_result"]["activity_id"]
    saved = review(
        world,
        draft,
        before,
        {"facts": {"counterparty": {"state": "known", "value": name + " "}}},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["facts"]["counterparty"]["value"] == name + " "
    assert current_revision(activity) == 1


@pytest.mark.owner_acts
def test_date_moved_past_a_balance_check_no_longer_counts_as_included(actions):
    from argus.domain.business.contracts.actions import ReviewDraft
    from argus.domain.recording.loop_schemas import CheckRequest

    from tests import test_business_declaration_after_approval_postgres as records

    service, owner, _ = actions
    money = service.imports.money
    account = records.cash_account(service, owner)
    draft, version = records.captured(
        service, owner, NCF, records.account_funding(account)
    )
    before = records.approved(service, owner, draft, version)
    target = money.accounts.get(
        user_id=owner.owner_id, account_id=account, scope=owner.scope
    )
    check = CheckRequest(
        expected_version=target.account.version,
        amount="9000.00",
        as_of="2026-09-10T17:00:00Z",
    )
    money.repository.mutate(
        user_id=owner.owner_id,
        account_id=account,
        scope=owner.scope,
        idempotency_key=str(uuid4()),
        identity_hash=uuid4().hex,
        expected_version=target.account.version,
        planner=lambda stored: money.accounts.loop._check(stored, check)[0],
    )
    saved = service.review(
        owner,
        draft,
        ReviewDraft(
            version=before.version,
            facts={"occurred_on": {"state": "known", "value": "2026-09-11"}},
        ),
        str(uuid4()),
    )
    assert saved.outcome == "applied", saved
    current = money.accounts.get(
        user_id=owner.owner_id, account_id=account, scope=owner.scope
    )
    assert current.expenses[0].current.coverage_skips[-1][1] == "after_observation_day"
    assert current_revision(before.approval_result.activity_id) == 2
