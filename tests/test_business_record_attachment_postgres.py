from types import SimpleNamespace

from argus.api.documents import documents_service
from faker import Faker
from psycopg import Connection

from tests import test_business_document_type_postgres as flow
from tests.test_financial_accounts_postgres import DSN

pytestmark = flow.pytestmark
web = flow.web


def test_attachment_presence_agrees_with_opening_the_original(
    web: SimpleNamespace, faker: Faker
) -> None:
    account = flow._account(web)
    receipt = flow._upload(web, flow.SUPPLIER_RNC)
    receipt_id, draft_id = receipt["id"], receipt["draft_id"]
    facts = flow._facts("expense", "1180.00", "2026-09-03", account)
    facts["counterparty"]["value"] = faker.company()
    reviewed = flow._review(web, draft_id, {"facts": facts, "dgii": flow.PURCHASE_606})
    assert reviewed.status_code == 200, reviewed.text
    flow._approve(web, draft_id, "record_expense")

    def check_presence(expected: bool) -> None:
        opened = web.client.get(
            f"{flow.API}/business/receipts/{receipt_id}/source", headers=web.alice.headers
        )
        dossier = flow._dossier(web, draft_id)
        [record] = flow._report(web)
        [attachment] = record["attachment_sources"]
        assert opened.status_code == (200 if expected else 422)
        if not expected:
            assert opened.json()["code"] == "document_source_unavailable"
        assert (dossier["original_connection_id"] == receipt_id) is expected
        assert (attachment["source_id"] in dossier["retained_source_ids"]) is expected
        assert record["has_document"] is expected
        assert record["attachment_count"] == int(expected)
        assert attachment["download_available"] is expected

    check_presence(True)
    with Connection.connect(DSN) as db:
        paths = db.execute(
            "select source_path,rebuilt_path from public.financial_document_extractions"
            " where connection_id=%s",
            (receipt_id,),
        ).fetchone()
        objects = documents_service().store.objects
        for path in paths:
            if path:
                objects.remove(path)
    check_presence(False)
