"""Stored arrival and title across the Business routes that expose the same record."""

from datetime import datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from argus.domain.business.ledger import business_day
from faker import Faker
from psycopg import Connection

from tests import test_business_listos_postgres as listos
from tests.business.test_business_api import RECEIPT
from tests.test_business_approve_unpaid_postgres import _export, _report
from tests.test_business_receipt_uploader_routes_postgres import _emailed
from tests.test_financial_accounts_postgres import DSN

pytestmark = listos.pytestmark
people = listos.people
rig = listos.rig


def test_first_message_arrival_survives_later_file_processing(
    rig, faker: Faker, monkeypatch: pytest.MonkeyPatch  # noqa: ANN001
) -> None:
    _emailed(rig, monkeypatch, RECEIPT + faker.binary(length=16))
    [file] = [
        row
        for row in listos._get(rig, "/business/receipts", view="all")["items"]
        if row["media_type"] == "image/png"
    ]
    [delivery_id] = file["email_delivery_ids"]
    with Connection.connect(DSN) as db:
        [arrived] = db.execute(
            "update public.business_email_deliveries set received_at=received_at-interval '1 day'"
            " where id=%s returning received_at",
            (delivery_id,),
        ).fetchone()
        [saved, linked] = db.execute(
            "select (d.draft->>'created_at')::timestamptz,s.received_at"
            " from public.financial_document_extractions d join public.business_sources s"
            " on s.connection_id=d.connection_id where d.connection_id=%s and s.kind='attachment'"
            " order by s.received_at limit 1",
            (file["id"],),
        ).fetchone()
    assert arrived < min(saved, linked)
    item = listos._row(rig, file["id"])
    detail = listos._get(rig, f"/business/receipts/{file['id']}")
    dossier = listos._get(rig, f"/business/drafts/{detail['draft_id']}/dossier")
    overview = listos._get(rig, "/business/overview", **listos.PERIOD)
    arrivals = {
        "Bandeja": item["received_at"],
        "receipt": detail["received_at"],
        "dossier": dossier["origin"]["received_at"],
        "Inicio": overview["last_received_at"],
    }
    assert {
        surface: datetime.fromisoformat(at.replace("Z", "+00:00"))
        for surface, at in arrivals.items()
    } == dict.fromkeys(arrivals, arrived)


def test_an_earlier_message_sets_the_record_date_and_keeps_the_file_identity(
    rig, faker: Faker  # noqa: ANN001
) -> None:
    receipt = listos._read(rig)
    item = listos._named(rig, receipt)
    file_time = listos._row(rig, receipt)["received_at"]
    earlier = datetime.fromisoformat(file_time.replace("Z", "+00:00")) - timedelta(days=366)
    with patch("argus.domain.business.actions.captures.datetime", wraps=datetime) as clock:
        clock.now.return_value = earlier
        response = rig.client.post(
            f"{listos.API}/business/captures",
            json={"draft": item, "text": faker.sentence()},
            headers={**rig.alice.headers, "Idempotency-Key": str(uuid4())},
        )
    assert response.status_code == 200, response.text
    dossier = listos._get(rig, f"/business/drafts/{item['draft_id']}/dossier")
    detail = listos._get(rig, f"/business/receipts/{receipt}")
    listed = listos._row(rig, receipt)
    assert dossier["original_connection_id"] == receipt
    assert dossier["origin"]["filename"] == detail["filename"] == listed["filename"]
    assert dossier["origin"]["received_at"] == detail["received_at"] == listed["received_at"]
    assert datetime.fromisoformat(detail["received_at"].replace("Z", "+00:00")) == earlier
    assert dossier["upload_year"] == business_day(earlier).year
    assert dossier["year_to_check"] and listed["bandeja_group"]["reason"] == "check_details"


def test_full_reviewed_title_survives_approval_and_finds_the_saved_record(
    rig, faker: Faker  # noqa: ANN001
) -> None:
    receipt = listos._read(rig)
    item = listos._named(rig, receipt)
    suffix = faker.lexify(text="????????????")
    counterparty = f"{faker.pystr(min_chars=201, max_chars=201)} {suffix}"
    reviewed = listos._review(
        rig, item, {"facts": {"counterparty": {"state": "known", "value": counterparty}}}
    )
    pending = listos._get(rig, "/business/search", q=suffix)["receipts"]
    detail = listos._get(rig, f"/business/receipts/{receipt}")
    assert (detail["merchant"], detail["title"]) == (counterparty, counterparty)
    assert [hit["title"] for hit in pending] == [reviewed["title"]] == [counterparty]
    approved = listos._approve_alone(rig, {**item, "version": reviewed["version"]})
    assert approved.status_code == 200, approved.text
    activity = approved.json()["approval_result"]["activity_id"]
    dossier = listos._get(rig, f"/business/drafts/{item['draft_id']}/dossier")
    day = dossier["facts"]["occurred_on"]["value"]
    [listed] = listos._get(rig, "/business/expenses", **{"from": day, "to": day})["items"]
    detail = listos._get(rig, f"/business/expenses/{activity}")
    hits = listos._get(rig, "/business/search", q=suffix)
    titles = {
        "Bandeja": listos._row(rig, receipt)["title"],
        "dossier": dossier["title"],
        "Registros": _report(rig)["counterparty"],
        "saved list": listed["merchant"],
        "saved detail": detail["merchant"],
        "saved search": next(
            (row["merchant"] for row in hits["expenses"] if row["id"] == activity), None
        ),
    }
    assert titles == dict.fromkeys(titles, counterparty)


def test_registros_names_a_file_without_making_it_the_supplier(rig) -> None:  # noqa: ANN001
    receipt = listos._read(rig, {"occurred_on": "2026-09-03"})
    item = listos._named(rig, receipt)
    reviewed = listos._review(
        rig, item, {"facts": {"counterparty": {"state": "unknown"}}}
    )
    filename = reviewed["origin"]["filename"]
    assert reviewed["title"] == filename
    approved = listos._approve_alone(rig, {**item, "version": reviewed["version"]})
    assert approved.status_code == 200, approved.text
    report = _report(rig)
    assert report["counterparty"] is None
    assert report.get("title") == filename
    _, [exported], _ = _export(rig)
    assert exported["Proveedor"] == ""
