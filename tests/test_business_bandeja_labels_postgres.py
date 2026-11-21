"""Over HTTP, on the real app, Auth and Postgres: the label and group of the
Bandeja rows the list pass changed. A read the read limit holds waits as
reading, a legacy dismissed receipt is not listed, a row being approved is
ready and is not approved twice, and a clean sale, Personal receipt or foreign
currency receipt is Listos and the list approves it."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from psycopg import Connection

from tests import test_business_listos_postgres as listos
from tests import test_financial_accounts_postgres as shared
from tests.business.test_business_api import RECEIPT
from tests.test_business_listos_postgres import (
    _approve_many,
    _counts,
    _get,
    _group,
    _label,
    _ledger,
    _mark_personal,
    _money,
    _named,
    _read,
    _results,
    _review,
    _row,
    _state,
)
from tests.test_business_reading_setting_postgres import _reading, _upload
from tests.test_business_scope_switch_routes_postgres import _note

pytestmark = listos.pytestmark
people = listos.people
rig = listos.rig


class _SpentBudget:
    def charge(self, business_id: str, now: datetime) -> str:
        return "business_read_budget_day"


def test_a_read_the_limit_holds_waits_as_reading_in_neither_tab(rig, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(rig.documents, "read_budget", _SpentBudget())
    held = _upload(rig, RECEIPT + b"\xb1").json()["id"]

    row = _row(rig, held)
    assert (row["status"], row["attention"]) == ("needs_attention", "read_budget_day")
    assert _group(rig, held) == ("reading", "reading")
    assert _label(rig, held) == "reading"
    assert row["delete_available"] is True
    assert _counts(rig) == (0, 0)
    activity = _get(rig, "/business/receipt-activity")
    assert activity["pending_review_count"] == 1
    assert (activity["reading_count"], activity["presentation"]) == (0, "none")
    assert "needs_attention_count" not in activity


def test_a_receipt_dismissed_with_no_deleted_mark_is_not_listed(rig) -> None:  # noqa: ANN001
    assert _reading(rig, False).status_code == 200
    kept = _upload(rig, RECEIPT + b"\xb2").json()["id"]
    legacy = _upload(rig, RECEIPT + b"\xb3").json()["id"]
    with Connection.connect(shared.DSN) as db:
        db.execute(
            "update public.financial_document_extractions"
            " set draft=jsonb_set(draft,'{status}','\"dismissed\"') where connection_id=%s",
            (legacy,),
        )

    for view in ("all", "inbox"):
        page = _get(rig, "/business/receipts", view=view)
        assert [row["id"] for row in page["items"]] == [kept]
        assert page["activity"]["dismissed_count"] == 1
    assert _counts(rig) == (0, 1)


def _accepting(draft_id: str) -> None:
    with Connection.connect(shared.DSN) as db:
        db.execute(
            "update public.financial_import_events set state='accepting',"
            " accept_key='in-flight' where id=%s",
            (draft_id,),
        )


def test_an_approval_in_flight_is_ready_and_is_not_approved_twice(rig) -> None:  # noqa: ANN001
    receipt = _read(rig)
    item = _named(rig, receipt)
    _accepting(item["draft_id"])

    row = _row(rig, receipt)
    assert row["bandeja_group"] == {
        "group": "listo",
        "reason": None,
        "label": "ready",
        "draft_id": None,
        "version": None,
    }
    assert row["delete_available"] is False
    assert _counts(rig) == (1, 0)
    assert _results(_approve_many(rig, [item])) == [
        ("refused", "business_draft_not_open")
    ]
    assert _state(item)[0] == "accepting"
    assert _money(rig) == 0


def _notes(rig) -> list[dict]:  # noqa: ANN001
    return _get(rig, "/business/captures", view="inbox")["items"]


def test_a_note_carries_the_label_and_one_being_approved_is_ready(rig) -> None:  # noqa: ANN001
    note = _note(rig, rig.alice, "Pagué 850 en Ferretería Prueba").json()
    item = {"draft_id": note["draft_id"], "version": note["version"]}

    [listed] = _notes(rig)
    assert listed["bandeja_group"] == {
        "group": "attention",
        "reason": "not_read",
        "label": "needs_attention",
        **item,
    }
    assert _counts(rig) == (0, 1)

    _accepting(item["draft_id"])
    [listed] = _notes(rig)
    assert listed["bandeja_group"] == {
        "group": "listo",
        "reason": None,
        "label": "ready",
        "draft_id": None,
        "version": None,
    }
    assert listed["delete_available"] is False
    assert _counts(rig) == (1, 0)
    assert _results(_approve_many(rig, [item])) == [
        ("refused", "business_draft_not_open")
    ]
    assert _money(rig) == 0


def _income_ledger(rig) -> list[str]:  # noqa: ANN001
    with Connection.connect(shared.DSN) as db:
        return [
            row[0]
            for row in db.execute(
                "select command->>'draft_id' from public.business_action_receipts"
                " where space_id=%s and command->>'action'='approve_income'",
                (rig.alice.space_id,),
            ).fetchall()
        ]


def test_a_clean_sale_is_listo_and_the_list_approves_it_as_a_sale(rig) -> None:  # noqa: ANN001
    sale = _read(rig)
    _review(rig, _named(rig, sale), {"document_type": "venta"})
    assert _group(rig, sale) == ("listo", None)
    assert _label(rig, sale) == "ready"
    assert _counts(rig) == (1, 0)

    item = _named(rig, sale)
    key = str(uuid4())
    first = _approve_many(rig, [item], key)
    assert _results(first) == [("applied", None)]
    assert _approve_many(rig, [item], key).json() == first.json()
    assert _money(rig) == 1
    assert _income_ledger(rig) == [item["draft_id"]]
    assert _ledger(rig) == []
    assert _label(rig, sale) == "accepted"


def test_a_replay_answers_the_same_after_the_draft_became_a_sale(rig) -> None:  # noqa: ANN001
    item = _named(rig, _read(rig, {"ncf": None}))
    key = str(uuid4())
    assert _results(_approve_many(rig, [item], key)) == [("refused", "not_listo")]

    _review(rig, item, {"document_type": "venta"})
    assert _results(_approve_many(rig, [item], key)) == [("refused", "not_listo")]
    assert _money(rig) == 0


def test_a_clean_foreign_currency_receipt_is_listo_and_the_list_approves_it(rig) -> None:  # noqa: ANN001
    usd = _read(rig, {"currency": "USD"})
    assert _row(rig, usd)["currency"] == "USD"
    assert _group(rig, usd) == ("listo", None)

    assert _results(_approve_many(rig, [_named(rig, usd)])) == [("applied", None)]
    assert _money(rig) == 1
    assert _label(rig, usd) == "accepted"


def test_a_clean_receipt_marked_personal_is_listo_and_the_list_approves_it(rig) -> None:  # noqa: ANN001
    receipt = _read(rig)
    item = _named(rig, receipt)
    marked = _mark_personal(rig, item, True)

    assert _row(rig, receipt)["personal"] is True
    assert _group(rig, receipt) == ("listo", None)
    assert _label(rig, receipt) == "ready"
    listed = {"draft_id": item["draft_id"], "version": marked["version"]}
    assert _named(rig, receipt) == listed
    assert _results(_approve_many(rig, [listed])) == [("applied", None)]
    assert _money(rig) == 1
    assert _label(rig, receipt) == "accepted"
