"""Bulk approval reports each receipt's saved read group after human review."""

from tests import test_business_listos_postgres as listos
from tests.test_business_analytics_postgres import _events, sent  # noqa: F401

pytestmark = listos.pytestmark
people = listos.people
rig = listos.rig


def test_bulk_approval_keeps_each_items_original_read_group(rig, sent) -> None:  # noqa: ANN001, F811
    clean = listos._read(rig)
    corrected = listos._read(rig, {"ncf": None})
    listos._fiscal(rig, listos._named(rig, corrected), ncf="B0100099999")
    assert listos._group(rig, corrected) == ("listo", None)
    sent.clear()

    assert listos._results(listos._approve_many(rig, [listos._named(rig, clean), listos._named(rig, corrected)])) == [
        ("applied", None), ("applied", None),
    ]

    assert [event["bandeja_group_at_read"] for event in _events(sent, "business_record_approved")] == [
        "listo", "attention",
    ]

