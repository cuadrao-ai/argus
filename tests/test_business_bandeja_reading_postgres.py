"""Over HTTP, on the real app, Auth and Postgres: a receipt still being read is
in neither Bandeja tab and no tab count, and a failed read needs attention."""

from __future__ import annotations

from tests.business.test_business_api import RECEIPT
from tests.document_reads_support import leave_reads_waiting
from tests.test_business_listos_postgres import (  # noqa: F401
    _counts,
    _get,
    _group,
    _row,
    people,
    pytestmark,
    rig,
)
from tests.test_business_reading_setting_postgres import _upload


def test_a_receipt_still_reading_is_in_no_tab_and_a_failed_read_stays(
    rig,  # noqa: ANN001, F811
    monkeypatch,  # noqa: ANN001
) -> None:
    rig.stub.failure = "encrypted_document"
    failed = _upload(rig, RECEIPT + b"\xa5").json()["id"]
    leave_reads_waiting(monkeypatch)
    reading = _upload(rig, RECEIPT + b"\xa6").json()["id"]

    assert _group(rig, reading) == ("reading", "reading")
    assert _group(rig, failed) == ("attention", "unreadable")
    assert _row(rig, reading)["bandeja"]["leyendo"] is True
    assert _counts(rig) == (0, 1)
    assert _get(rig, "/business/receipt-activity")["pending_review_count"] == 2
