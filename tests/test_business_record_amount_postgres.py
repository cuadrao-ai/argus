"""The receipt read, the facts in review and the last approved facts can differ."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from faker import Faker

from tests import test_business_document_type_postgres as uploads
from tests.test_business_approve_unpaid_postgres import _get, _report
from tests.test_business_fiscal_routes_postgres import _known, table_file
from tests.test_business_search_routes_postgres import _search

web = uploads.web
pytestmark = uploads.pytestmark


def test_clearing_amount_and_currency_hides_the_read_in_lists(
    web: SimpleNamespace, faker: Faker
) -> None:
    read_total = f"{faker.random_int(1200, 9000)}.00"
    receipt = uploads._upload(web, uploads.SUPPLIER_RNC, total=read_total)
    draft = receipt["draft_id"]
    cleared = uploads._review(
        web, draft, {"facts": dict.fromkeys(("amount", "currency"), {"state": "unknown"})}
    )
    assert cleared.status_code == 200, cleared.text
    detail = uploads._receipt(web, receipt["id"])
    evidence = detail["evidence"]
    assert (Decimal(evidence["total"]), evidence["currency"]) == (
        Decimal(read_total),
        "DOP",
    )
    facts = uploads._dossier(web, draft)["facts"]
    [listed] = _get(web, "/business/receipts", view="inbox").json()["items"]
    [found] = _search(web, "B0100000001")["receipts"]
    assert (facts["amount"]["value"], facts["currency"]["value"]) == (None, None)
    for row in (listed, found, detail):
        assert (row["id"], row["amount"], row["currency"]) == (receipt["id"], None, None)
    assert _search(web, read_total)["receipts"] == []


def test_owner_edit_after_accept_changes_report_and_download(
    web: SimpleNamespace, faker: Faker
) -> None:
    receipt = uploads._upload(
        web, uploads.CLIENT_RNC, "venta", occurred_on="2026-09-03", total="2360.00"
    )
    draft = receipt["draft_id"]
    account = uploads._account(web)
    reviewed = uploads._review(
        web,
        draft,
        {
            "facts": uploads._facts("income", "2360.00", "2026-09-03", account),
            "dgii": uploads.SALE_607,
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    uploads._approve(web, draft, "record_income")
    total = Decimal(faker.random_int(2400, 9000))
    day = date(2026, 9, faker.random_int(4, 28))
    corrected = uploads._review(
        web,
        draft,
        {"facts": _known({"amount": str(total), "occurred_on": day.isoformat()})},
    )
    assert corrected.status_code == 200, corrected.text
    evidence = uploads._receipt(web, receipt["id"])["evidence"]
    assert (Decimal(evidence["total"]), evidence["occurred_on"]) == (2360, "2026-09-03")
    dossier = uploads._dossier(web, draft)["facts"]
    row = _report(web)
    [line] = table_file(web, "sale")
    assert (Decimal(dossier["amount"]["value"]), dossier["occurred_on"]["value"]) == (
        total,
        day.isoformat(),
    )
    assert (Decimal(row["gross_amount"]), row["report_date"]) == (total, day.isoformat())
    assert (Decimal(line["Total"]), line["Fecha"]) == (total, day.strftime("%d/%m/%Y"))
