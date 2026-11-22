"""Over HTTP, on the real app, Auth and Postgres: a single accept follows the
Listos rule. A record with a gap is refused with every gap named, is accepted
only when a person may accept over each gap and the accept names every one, and
is never accepted in a list."""

from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

import pytest
from argus.domain.business.bandeja_group import RULE
from argus.domain.business.contracts.facts import Unknown
from psycopg import Connection
from psycopg.types.json import Jsonb

from tests import test_business_listos_postgres as listos
from tests import test_business_scope_switch_routes_postgres as scope
from tests import test_financial_accounts_postgres as shared
from tests.business.test_bandeja_group import ACCEPTED_OVER
from tests.business.test_business_api import RECEIPT
from tests.test_business_approve_unpaid_postgres import _declaration
from tests.test_business_fiscal_routes_postgres import _known
from tests.test_business_listos_postgres import (
    BAD_CHECK_DIGIT,
    ECF,
    SUPPLIER,
    _approve_many,
    _checked,
    _delivered,
    _get,
    _money,
    _named,
    _read,
    _results,
    _review,
    _state,
)
from tests.test_business_scope_switch_routes_postgres import API, _note

pytestmark = [scope.pytestmark, pytest.mark.usefixtures("typed_notes_on")]
people = scope.web
rig = listos.rig


def _resolution(item: dict, path: str, value: object) -> None:
    with Connection.connect(shared.DSN) as db:
        db.execute(
            "update public.financial_import_events"
            " set resolution=jsonb_set(resolution,%s,%s) where id=%s",
            (path, Jsonb(value), item["draft_id"]),
        )


def _typed(rig, monkeypatch) -> dict:  # noqa: ANN001
    """A note a person typed and then filled in: every fact, and no document."""

    note = _note(rig, rig.alice, "Pagué 1180 en Ferretería Prueba").json()
    item = {"draft_id": note["draft_id"]}
    item["version"] = _dossier(rig, item)["version"]
    facts = {
        "kind": "expense",
        "amount": "1180.00",
        "currency": "DOP",
        "occurred_on": "2026-10-06",
        "counterparty": "Ferretería Prueba",
    }
    fiscal = {"rnc": SUPPLIER, "ncf": "B0100000096", "itbis": "18.00"}
    declared = {"fiscal": fiscal, "declaration": _declaration("expense")}
    saved = _review(rig, item, {"facts": _known(facts), "dgii": declared})
    return {**item, "version": saved["version"]}


def _read_with_an_issue(rig, monkeypatch) -> dict:  # noqa: ANN001
    receipt = _read(rig)
    with Connection.connect(shared.DSN) as db:
        db.execute(
            "update public.financial_document_extractions"
            " set draft=jsonb_set(jsonb_set(draft,'{status}','\"needs_attention\"'),"
            " '{error_code}','\"incomplete_extraction\"') where connection_id=%s",
            (receipt,),
        )
    return _named(rig, receipt)


def _several(rig, monkeypatch) -> dict:  # noqa: ANN001
    item = _named(rig, _read(rig))
    purchases = [{"index": 1, "amount": "100.00"}, {"index": 2, "amount": "200.00"}]
    _resolution(item, "{business,read_purchases}", purchases)
    return item


def _no_amount(read_total: str | None) -> Callable:
    def build(rig, monkeypatch) -> dict:  # noqa: ANN001
        item = _named(rig, _read(rig))
        _resolution(item, "{business,facts,amount}", Unknown().model_dump(mode="json"))
        if read_total:
            _resolution(item, "{business,read_total}", read_total)
        return item

    return build


def _same_comprobante(rig, monkeypatch) -> dict:  # noqa: ANN001
    _read(rig, {"ncf": "B0100000093"})
    return _named(rig, _read(rig, {"ncf": "B0100000093"}))


def _no_comprobante(rig, monkeypatch) -> dict:  # noqa: ANN001
    item = _named(rig, _read(rig, {"ncf": None}))
    stated = {"state": "known", "value": "no_receipt"}
    saved = _review(rig, item, {"facts": {"receipt_state": stated}})
    return {"draft_id": item["draft_id"], "version": saved["version"]}


def _failed_check(rig, monkeypatch) -> dict:  # noqa: ANN001
    item = _named(rig, _read(rig, {"ncf": None, "ecf": ECF}))
    _checked(rig, item, "failed", ECF)
    return item


def _open_question(rig, monkeypatch) -> dict:  # noqa: ANN001
    item = _named(rig, _read(rig))
    with Connection.connect(shared.DSN) as db:
        db.execute(
            "insert into public.business_questions"
            " (space_id,draft_id,field,asked_of,channel,state,prompt,allowed_answers)"
            " values (%s,%s,'funding','owner','web','open','¿Cómo se pagó?',"
            " array['known','owner_does_not_know'])",
            (rig.alice.space_id, item["draft_id"]),
        )
    return item


def _sender_removed(rig, monkeypatch) -> dict:  # noqa: ANN001
    runtime, receipt, _ = _delivered(rig, monkeypatch, RECEIPT + b"\xb1")
    item = _named(rig, receipt)
    [rule] = runtime.store.list_senders(rig.alice.space_id)
    runtime.store.remove_sender(rig.alice.space_id, rule.id)
    return item


def _reads(read: dict) -> Callable:
    return lambda rig, monkeypatch: _named(rig, _read(rig, read))


#: One open draft per reason of the rule, built the way a person meets it.
BUILD: dict[str, Callable] = {
    "not_read": _typed,
    "check_details": _read_with_an_issue,
    "several_purchases": _several,
    "no_purchase_found": _no_amount("340.00"),
    "duplicate": _same_comprobante,
    "credit_note": _reads({"ncf": "B0400000002"}),
    "missing_merchant": _reads({"merchant": None}),
    "missing_date": _reads({"occurred_on": None}),
    "missing_amount": _no_amount(None),
    "missing_currency": _reads({"currency": None, "ncf": None}),
    "sin_comprobante": _no_comprobante,
    "missing_rnc": _reads({"rnc": None}),
    "invalid_rnc": _reads({"rnc": BAD_CHECK_DIGIT}),
    "missing_ncf": _reads({"ncf": None}),
    "invalid_ncf": _reads({"ncf": "B01000008"}),
    "ecf_check_failed": _failed_check,
    "missing_itbis": _reads({"itbis": None}),
    "review_flag": _reads({"itbis": "900.00"}),
    "blocked": _open_question,
    "unverified_sender": _sender_removed,
}
#: A credit note asks which purchase it refunds before it can be recorded, so
#: its draft here is also blocked. ``test_business_fiscal_links_postgres``
#: records one over its ``credit_note`` gap.
BLOCKED_TOO = {"credit_note"}


def _dossier(rig, item: dict) -> dict:  # noqa: ANN001
    return _get(rig, f"/business/drafts/{item['draft_id']}/dossier")


def _accept(rig, item: dict, over: tuple[str, ...] = ()):  # noqa: ANN001, ANN202
    body = {"version": item["version"], "action": _dossier(rig, item)["approval_action"]}
    return rig.client.post(
        f"{API}/business/drafts/{item['draft_id']}/approve",
        json={**body, "accept_gaps": list(over)} if over else body,
        headers={**rig.alice.headers, "Idempotency-Key": str(uuid4())},
    )


def _stored_request(rig, item: dict) -> dict:  # noqa: ANN001
    with Connection.connect(shared.DSN) as db:
        return db.execute(
            "select command->'request' from public.business_action_receipts"
            " where space_id=%s and command->>'draft_id'=%s"
            " and command->>'action' like 'approve_%%'"
            " and outcome->>'outcome'='applied'",
            (rig.alice.space_id, item["draft_id"]),
        ).fetchone()[0]


def test_the_table_builds_every_reason_of_the_rule() -> None:
    assert set(BUILD) == {gap.reason for gap in RULE} == set(ACCEPTED_OVER)


@pytest.mark.parametrize("reason", BUILD)
def test_a_single_accept_follows_the_listo_rule(rig, monkeypatch, reason: str) -> None:  # noqa: ANN001, F811
    item = BUILD[reason](rig, monkeypatch)
    dossier = _dossier(rig, item)
    gaps = tuple(dossier["listo_gaps"])
    assert dossier["confirmable"] == [gap for gap in gaps if ACCEPTED_OVER[gap]]
    accepted_over = all(ACCEPTED_OVER[gap] for gap in gaps)
    assert reason in gaps
    assert accepted_over == ACCEPTED_OVER[reason] or reason in BLOCKED_TOO, gaps

    assert _results(_approve_many(rig, [item]))[0][0] == "refused"
    plain = _accept(rig, item)
    assert plain.status_code in (403, 422), plain.text
    if plain.json()["code"] == "not_listo":
        assert plain.json()["context"] == {
            "gaps": list(gaps),
            "confirmable": [gap for gap in gaps if ACCEPTED_OVER[gap]],
        }
    assert _state(item)[0] == "open"
    assert _money(rig) == 0

    named = _accept(rig, item, gaps)

    if accepted_over:
        assert named.status_code == 200, named.text
        assert named.json()["bandeja_group"]["label"] == "accepted"
        assert _stored_request(rig, item)["accept_gaps"] == list(gaps)
        assert _money(rig) == 1
    else:
        assert named.status_code in (403, 422), named.text
        assert _state(item)[0] == "open"
        assert _money(rig) == 0


def test_an_accept_that_names_only_some_gaps_is_refused_with_them_all(rig) -> None:  # noqa: ANN001, F811
    item = _named(rig, _read(rig, {"rnc": None, "itbis": None}))
    gaps = ["missing_rnc", "missing_itbis"]
    assert _dossier(rig, item)["listo_gaps"] == gaps

    refused = _accept(rig, item, ("missing_rnc",))

    assert (refused.status_code, refused.json()["code"]) == (422, "not_listo")
    assert refused.json()["context"] == {"gaps": gaps, "confirmable": gaps}
    assert _state(item)[0] == "open"
    assert _accept(rig, item, tuple(gaps)).status_code == 200
    assert _money(rig) == 1


@pytest.mark.parametrize(
    ("field", "gap"),
    [("occurred_on", "missing_date"), ("amount", "missing_amount"), ("currency", "missing_currency")],
)
def test_one_missing_fact_has_one_gap(rig, field: str, gap: str) -> None:  # noqa: ANN001, F811
    item = _named(rig, _read(rig))
    _resolution(item, "{business,facts," + field + "}", Unknown().model_dump(mode="json"))

    dossier = _dossier(rig, item)
    assert dossier["listo_gaps"] == [gap]
    assert dossier["confirmable"] == []


def test_unclear_read_and_year_name_check_details_once(rig, monkeypatch) -> None:  # noqa: ANN001, F811
    item = _read_with_an_issue(rig, monkeypatch)
    year = _dossier(rig, item)["upload_year"] - 1
    _resolution(item, "{business,facts,occurred_on,value}", f"{year}-01-15")

    dossier = _dossier(rig, item)
    assert dossier["year_to_check"]
    assert dossier["listo_gaps"] == ["check_details"]


def test_a_gap_that_went_away_may_still_be_named(rig) -> None:  # noqa: ANN001, F811
    item = _named(rig, _read(rig, {"itbis": None}))

    accepted = _accept(rig, item, ("missing_itbis", "missing_rnc"))

    assert accepted.status_code == 200, accepted.text


def test_a_listos_record_is_accepted_with_nothing_named(rig) -> None:  # noqa: ANN001, F811
    item = _named(rig, _read(rig))

    accepted = _accept(rig, item)

    assert accepted.status_code == 200, accepted.text
    assert "accept_gaps" not in _stored_request(rig, item)


def test_a_sale_follows_the_same_rule(rig) -> None:  # noqa: ANN001, F811
    item = _named(rig, _read(rig, {"itbis": None}))
    saved = _review(rig, item, {"document_type": "venta"})
    sale = {"draft_id": item["draft_id"], "version": saved["version"]}
    assert _dossier(rig, sale)["approval_action"] == "record_income"
    gaps = tuple(_dossier(rig, sale)["listo_gaps"])
    assert gaps

    refused = _accept(rig, sale)

    assert (refused.status_code, refused.json()["code"]) == (422, "not_listo")
    assert _accept(rig, sale, gaps).status_code == 200


def test_a_list_takes_no_names_and_no_gapped_record(rig) -> None:  # noqa: ANN001, F811
    item = _named(rig, _read(rig, {"itbis": None}))

    named = rig.client.post(
        f"{API}/business/drafts/approve-listos",
        json={"items": [{**item, "accept_gaps": ["missing_itbis"]}]},
        headers={**rig.alice.headers, "Idempotency-Key": str(uuid4())},
    )

    assert named.status_code == 422, named.text
    assert _results(_approve_many(rig, [item])) == [("refused", "not_listo")]
    assert _state(item)[0] == "open"
    assert _money(rig) == 0
