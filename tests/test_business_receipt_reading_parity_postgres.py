"""Bandeja, the dossier and delete agree on whether a receipt is being read."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from psycopg import Connection
from psycopg.types.json import Jsonb

from tests import test_business_listos_postgres as listos
from tests import test_financial_accounts_postgres as shared
from tests.test_business_dossier_standing_postgres import _dossier
from tests.test_business_reading_setting_postgres import _reading
from tests.test_business_scope_switch_routes_postgres import API

pytestmark = listos.pytestmark
people = listos.people
rig = listos.rig


@pytest.mark.parametrize(
    ("status", "consent", "lease_minutes", "reading"),
    [
        ("review_ready", "current", 30, True),
        ("review_ready", "current", -30, False),
        ("review_ready", "current", None, False),
        ("needs_attention", "current", None, False),
        ("saved", "none", None, False),
        ("dismissed", "none", None, False),
        ("preparing", "revoked", None, True),
        ("queued", "current", None, True),
        ("queued", "stale", None, False),
        ("queued", "none", None, False),
        ("queued", "revoked", None, False),
        ("queued", "revoked", 30, True),
    ],
)
def test_reading_agrees_across_the_receipt_and_dossier(
    rig,  # noqa: ANN001
    status: str,
    consent: str,
    lease_minutes: int | None,
    reading: bool,
) -> None:
    receipt = listos._read(rig)
    draft_id = listos._named_draft(rig, receipt)
    change = {"status": status, "consent": consent != "none"}
    if consent == "stale":
        change["business_reading_consent_id"] = str(uuid4())
    if consent == "revoked":
        assert _reading(rig, False).status_code == 200
    lease = (
        datetime.now(timezone.utc) + timedelta(minutes=lease_minutes)
        if lease_minutes is not None
        else None
    )
    with Connection.connect(shared.DSN) as db:
        db.execute(
            "update public.financial_document_extractions set draft=draft || %s"
            " where connection_id=%s",
            (Jsonb(change), receipt),
        )
        db.execute(
            "update public.financial_source_connections set lease_holder=%s, lease_until=%s"
            " where id=%s",
            (str(uuid4()) if lease else None, lease, receipt),
        )

    row = listos._row(rig, receipt)
    dossier = _dossier(rig, draft_id)
    assert row["read_pending"] is reading
    assert (row["bandeja_group"]["group"] == "reading") is reading
    assert (dossier["bandeja_group"]["group"] == "reading") is reading
    assert row["delete_available"] == dossier["delete_available"] == (not reading)
    answer = rig.client.post(
        f"{API}/business/drafts/{draft_id}/delete",
        json={},
        headers={**rig.alice.headers, "Idempotency-Key": str(uuid4())},
    )
    if reading:
        assert (answer.status_code, answer.json()["code"]) == (
            422,
            "business_document_reading",
        )
    else:
        assert answer.status_code == 200, answer.text


def test_a_draft_with_two_receipts_waits_while_either_is_being_read(rig) -> None:  # noqa: ANN001
    first, second = listos._read(rig), listos._read(rig)
    draft_id = listos._named_draft(rig, first)
    with Connection.connect(shared.DSN) as db:
        db.execute(
            "update public.business_draft_sources l set draft_id=%s"
            " from public.business_sources s where s.id=l.source_id and s.connection_id=%s",
            (draft_id, second),
        )
        db.execute(
            "update public.financial_source_connections set lease_holder=%s,"
            " lease_until=now()+ interval '30 minutes' where id=%s",
            (str(uuid4()), second),
        )
    dossier = _dossier(rig, draft_id)
    rows = [listos._row(rig, receipt) for receipt in (first, second)]
    idle_detail = listos._get(rig, f"/business/receipts/{first}")
    assert dossier["bandeja_group"]["group"] == "reading"
    for row in [*rows, idle_detail]:
        assert row["bandeja_group"]["group"] == dossier["bandeja_group"]["group"]
        assert row["delete_available"] == dossier["delete_available"] is False
    assert [row["read_pending"] for row in rows] == [False, True]
    assert [row["bandeja"]["leyendo"] for row in rows] == [False, True]
