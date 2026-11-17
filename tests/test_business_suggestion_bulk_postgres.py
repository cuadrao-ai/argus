"""Over HTTP, on the real app, Auth and Postgres: approving a list of Listos
receipts saves the server's own suggestion, read at approval time, into each
blank 606 answer with its source, and never over an answer a person gave."""

from __future__ import annotations

from tests import test_business_listos_postgres as listos

pytestmark = listos.pytestmark
people = listos.people
rig = listos.rig


def _dossier(rig, item: dict) -> dict:  # noqa: ANN001
    return listos._get(rig, f"/business/drafts/{item['draft_id']}/dossier")


def _answered(rig, **purchase) -> None:  # noqa: ANN001, ANN003
    """A person answered for this supplier on an earlier receipt."""

    earlier = listos._named(rig, listos._read(rig))
    listos._review(rig, earlier, {"purchase": purchase})


def _saved(dossier: dict) -> tuple:
    declared = dossier["dgii"] or {}
    return (
        declared.get("category"),
        declared.get("payment_method"),
        declared.get("suggestion_sources", {}),
    )


def test_a_list_approval_fills_blank_answers_and_keeps_a_typed_one(rig) -> None:  # noqa: ANN001
    _answered(rig, category="02", payment_method="03")
    receipt = listos._read(rig)
    typed = listos._review(
        rig, listos._named(rig, receipt), {"purchase": {"payment_method": "01"}}
    )
    assert typed["declaration_suggestions"] == {
        "category": {"value": "02", "source": "last_choice"},
        "payment_method": None,
    }
    item = listos._named(rig, receipt)

    assert listos._results(listos._approve_many(rig, [item])) == [("applied", None)]

    approved = _dossier(rig, item)
    assert _saved(approved) == ("02", "01", {"category": "last_choice"})
    assert approved["declaration_suggestions"] == {
        "category": None,
        "payment_method": None,
    }


def test_a_list_approval_saves_what_the_server_suggests_at_approval_time(rig) -> None:  # noqa: ANN001
    receipt = listos._read(rig)
    item = listos._named(rig, receipt)
    assert _dossier(rig, item)["declaration_suggestions"]["category"] is None
    _answered(rig, category="05")

    assert listos._results(listos._approve_many(rig, [item])) == [("applied", None)]

    assert _saved(_dossier(rig, item)) == ("05", None, {"category": "last_choice"})


def test_a_list_approval_with_nothing_to_suggest_leaves_the_answers_blank(rig) -> None:  # noqa: ANN001
    item = listos._named(rig, listos._read(rig))

    assert listos._results(listos._approve_many(rig, [item])) == [("applied", None)]

    assert _saved(_dossier(rig, item)) == (None, None, {})
