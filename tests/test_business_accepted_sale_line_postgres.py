"""Read an accepted record whose draft and revisions have no saved fiscal line."""

import pytest
from psycopg import Connection

from tests import test_business_actions_postgres as business
from tests import test_business_approve_unpaid_postgres as http
from tests import test_business_dgii_postgres as fiscal
from tests.test_financial_accounts_postgres import DSN

world = http.world
actions = fiscal.actions
shared_actions = business.actions
users = business.users
pytestmark = [business.pytestmark, pytest.mark.usefixtures("typed_notes_on"), pytest.mark.owner_acts]


def remove_saved_line(draft) -> None:  # noqa: ANN001
    with Connection.connect(DSN) as db:
        db.execute("set local session_replication_role=replica")
        assert db.execute(
            "update public.financial_import_events set resolution=resolution #- '{business,dgii}'"
            " where id=%s and state='accepted'", (draft,),
        ).rowcount == 1
        assert db.execute(
            "update public.business_draft_revisions set before_dgii=null,after_dgii=null where draft_id=%s",
            (draft,),
        ).rowcount > 0


def stored_lines(draft) -> tuple:  # noqa: ANN001
    with Connection.connect(DSN) as db:
        return db.execute(
            "select e.resolution->'business'->'dgii', count(r.version), count(r.after_dgii),"
            " (select count(*) from public.business_dgii_export_lines where activity_id=e.activity_id)"
            " from public.financial_import_events e join public.business_draft_revisions r on r.draft_id=e.id"
            " where e.id=%s group by e.id",
            (draft,),
        ).fetchone()


@http.pytestmark
def test_accepted_sale_dossier_and_export_read_amounts_and_report_unanswered_fields(world, faker) -> None:  # noqa: ANN001
    http._fiscal_profile(world)
    ncf = faker.numerify("B01########")
    draft, _ = http._recorded(world, "income", ncf)
    remove_saved_line(draft)
    before = stored_lines(draft)
    assert before[0] is None and before[1] > 0 and before[2:] == (0, 0)

    dossier = http._get(world, f"/business/drafts/{draft}/dossier").json()
    manifest, _, forms = http._export(world)

    assert stored_lines(draft) == before
    assert dossier["review_state"] == "accepted"
    line = dossier["dgii"]
    assert line is not None
    assert (line["form"], line["billed_amount"], line["itbis"]) == ("607", "1000.00", "180.00")
    assert line["id_type"] is None and line["income_type"] is None
    assert dossier["sale_payment"]["form"] is None
    assert forms["607"] == "needs_review"
    assert {(issue["code"], issue["field"]) for issue in manifest["dgii"]["issues"]} == {
        ("fiscal_fact_required", "id_type"),
        ("fiscal_fact_required", "income_type"),
        ("fiscal_payment_total_conflict", "cash"),
    }

    corrected = http._review(
        world, draft,
        {
            "version": dossier["version"],
            "dgii": {
                "fiscal": {"rnc": http.BUYER_OR_SUPPLIER, "ncf": ncf, "itbis": line["itbis"]},
                "declaration": {**line, "id_type": "1", "income_type": "1", "bank": "1180.00"},
            },
        },
        world.alice.headers,
    )
    assert corrected.status_code == 200, corrected.text
    manifest, _, forms = http._export(world)
    assert forms["607"] == "prepared_candidate"
    assert manifest["dgii"]["issues"] == []


def test_purchase_refund_needs_its_original_purchase_and_gets_no_sale_line(actions) -> None:  # noqa: ANN001
    service, context, _ = actions
    account = fiscal.cash_account(service, context)
    purchase = fiscal.reviewed(service, context, account)
    approved = fiscal.approve(service, context, purchase)
    assert approved.outcome == "applied"
    refund = fiscal.reviewed(service, context, account, 3, purchase=approved.activity_id)
    assert fiscal.approve(service, context, refund).outcome == "applied"
    remove_saved_line(refund[0])

    dossier = service.dossier(context, refund[0])
    assert dossier.facts.kind.value == "refund"
    assert dossier.dgii is None
