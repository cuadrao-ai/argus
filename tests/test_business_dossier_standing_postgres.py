"""Over HTTP, on the real app, Auth and Postgres: the dossier of a record says
where it stands in the Bandeja exactly as its row in the receipt list does,
names every gap the rule finds, and carries what the DGII register says of the
supplier RNC."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from argus.domain.business.rnc_registry import INACTIVE_BY_RAW, RegistryStatus
from faker import Faker
from psycopg import Connection

from tests import test_business_actions_postgres as actions_support
from tests import test_business_listos_postgres as listos
from tests import test_financial_accounts_postgres as shared
from tests.business.receipt_stub import receipt_purchase
from tests.business.test_business_api import RECEIPT
from tests.test_business_bandeja_labels_postgres import _accepting
from tests.test_business_listos_postgres import (
    OTHER_SUPPLIER,
    SUPPLIER,
    _approve_alone,
    _get,
    _named,
    _read,
    _row,
)
from tests.test_business_reading_setting_postgres import _upload
from tests.test_business_scope_switch_routes_postgres import API

pytestmark = listos.pytestmark
people = listos.people
rig = listos.rig
actions = actions_support.actions
users = actions_support.users

LISTED = "101999996"
fake = Faker()


def _dossier(rig, draft_id: str) -> dict:  # noqa: ANN001
    return _get(rig, f"/business/drafts/{draft_id}/dossier")


def _same_as_the_list(rig, receipt: str, draft_id: str | None = None) -> dict:  # noqa: ANN001
    """The dossier of the receipt's draft, once its standing equals the row's."""

    row = _row(rig, receipt)["bandeja_group"]
    dossier = _dossier(rig, draft_id or row["draft_id"])
    assert dossier["bandeja_group"] == {
        name: row[name] for name in ("group", "reason", "label")
    }
    return dossier


@pytest.mark.parametrize(
    ("read", "gaps"),
    [
        pytest.param({}, [], id="a clean read"),
        pytest.param({"merchant": None}, ["missing_merchant"], id="no supplier"),
        pytest.param({"occurred_on": None}, ["missing_date"], id="no date"),
        pytest.param({"rnc": None}, ["missing_rnc"], id="no RNC"),
        pytest.param(
            {"rnc": "12345"}, ["invalid_rnc"], id="an RNC of the wrong length"
        ),
        pytest.param({"ncf": None}, ["missing_ncf"], id="no NCF"),
        pytest.param({"itbis": None}, ["missing_itbis"], id="no ITBIS"),
        pytest.param({"itbis": "900.00"}, ["review_flag"], id="ITBIS above the rate"),
        pytest.param(
            {"rnc": None, "ncf": None, "itbis": None},
            ["missing_rnc", "missing_ncf", "missing_itbis"],
            id="three gaps in the rule's order",
        ),
        pytest.param(
            {"rnc": listos.BAD_CHECK_DIGIT, "ncf": "B01000008"},
            ["invalid_rnc", "invalid_ncf"],
            id="two flagged values",
        ),
    ],
)
def test_the_dossier_stands_where_the_list_puts_the_row(rig, read: dict, gaps) -> None:  # noqa: ANN001
    dossier = _same_as_the_list(rig, _read(rig, read))

    assert dossier["listo_gaps"] == gaps
    assert dossier["bandeja_group"]["reason"] == (gaps[0] if gaps else None)
    assert dossier["bandeja_group"]["label"] == (
        "needs_attention" if gaps else "ready"
    )


def test_an_accepted_record_is_labeled_accepted_and_names_no_gap(rig) -> None:  # noqa: ANN001
    receipt = _read(rig, {"ncf": None})
    item = _named(rig, receipt)
    assert _dossier(rig, item["draft_id"])["listo_gaps"] == ["missing_ncf"]

    assert _approve_alone(rig, item).status_code == 200
    dossier = _same_as_the_list(rig, receipt, item["draft_id"])

    assert dossier["review_state"] == "accepted"
    assert dossier["bandeja_group"] == {
        "group": None,
        "reason": None,
        "label": "accepted",
    }
    assert dossier["listo_gaps"] == []


def test_a_record_being_approved_is_ready(rig) -> None:  # noqa: ANN001
    receipt = _read(rig)
    draft_id = _named(rig, receipt)["draft_id"]
    _accepting(draft_id)

    dossier = _same_as_the_list(rig, receipt, draft_id)

    assert dossier["bandeja_group"]["label"] == "ready"
    assert dossier["listo_gaps"] == []


def test_a_deleted_record_stands_in_eliminados_and_returns_as_it_was(rig) -> None:  # noqa: ANN001
    receipt = _read(rig, {"itbis": None})
    draft_id = _named(rig, receipt)["draft_id"]

    for action, group, gaps in (
        ("delete", "eliminados", []),
        ("restore", "attention", ["missing_itbis"]),
    ):
        answer = rig.client.post(
            f"{API}/business/drafts/{receipt}/{action}",
            json={},
            headers={**rig.alice.headers, "Idempotency-Key": str(uuid4())},
        )
        assert answer.status_code == 200, answer.text
        dossier = _same_as_the_list(rig, receipt, draft_id)
        assert dossier["bandeja_group"]["group"] == group
        assert dossier["listo_gaps"] == gaps


def test_a_record_whose_receipt_is_being_read_again_waits(rig) -> None:  # noqa: ANN001
    receipt = _read(rig, {"ncf": None})
    draft_id = _named(rig, receipt)["draft_id"]
    with Connection.connect(shared.DSN) as db:
        db.execute(
            "update public.financial_document_extractions"
            " set draft=jsonb_set(draft,'{status}','\"preparing\"') where connection_id=%s",
            (receipt,),
        )

    dossier = _same_as_the_list(rig, receipt, draft_id)

    assert dossier["bandeja_group"] == {
        "group": "reading",
        "reason": "reading",
        "label": "reading",
    }
    assert dossier["listo_gaps"] == []


def test_a_read_with_an_issue_says_check_details_first(rig) -> None:  # noqa: ANN001
    receipt = _read(rig, {"itbis": None})
    with Connection.connect(shared.DSN) as db:
        db.execute(
            "update public.financial_document_extractions"
            " set draft=jsonb_set(jsonb_set(draft,'{status}','\"needs_attention\"'),"
            " '{error_code}','\"incomplete_extraction\"') where connection_id=%s",
            (receipt,),
        )

    dossier = _same_as_the_list(rig, receipt)

    assert dossier["listo_gaps"] == ["check_details", "missing_itbis"]


#: What a supporting file changes on its record's dossier: one more version
#: with its history entry, the file as a source, and the file in its own list.
SUPPORTING_FILE_FIELDS = {"version", "history", "sources", "supporting_files", "retained_source_ids"}


def _append_supporting_file(rig, draft_id: str, version: int) -> str:  # noqa: ANN001
    answer = rig.client.post(
        f"{API}/business/drafts/{draft_id}/supporting-files",
        content=fake.paragraph().encode(),
        headers={
            **rig.alice.headers,
            "X-Draft-Version": str(version),
            "X-Document-Filename": fake.file_name(extension="txt"),
            "Content-Type": "text/plain",
            "Idempotency-Key": str(uuid4()),
        },
    )
    assert answer.status_code == 200, answer.text
    return answer.json()["result"]["source_id"]


def test_a_supporting_file_leaves_a_clean_record_in_listos(rig) -> None:  # noqa: ANN001
    receipt = _read(rig)
    before = _same_as_the_list(rig, receipt)
    assert before["listo_gaps"] == []
    counts = listos._counts(rig)

    added = _append_supporting_file(rig, _named(rig, receipt)["draft_id"], before["version"])
    after = _same_as_the_list(rig, receipt)

    assert after["listo_gaps"] == []
    assert after["bandeja_group"]["label"] == "ready"
    assert {
        name for name in after if after[name] != before[name]
    } == SUPPORTING_FILE_FIELDS
    assert set(after["retained_source_ids"]) == {*before["retained_source_ids"], added}
    assert added not in before["retained_source_ids"]
    assert listos._counts(rig) == counts


def test_a_repeat_says_so_on_the_dossier_as_on_the_row(rig) -> None:  # noqa: ANN001
    first = _read(rig)
    rig.stub.details = {**rig.stub.details, "ncf": "B0100000092"}
    repeat = _upload(rig, RECEIPT + b"\xd6").json()["id"]

    assert _same_as_the_list(rig, first)["listo_gaps"] == []
    dossier = _same_as_the_list(rig, repeat)

    assert dossier["bandeja_group"]["reason"] == "duplicate"
    assert "duplicate" in dossier["listo_gaps"]


def test_one_comprobante_on_two_receipts_is_a_repeat_on_both_dossiers(rig) -> None:  # noqa: ANN001
    first = _read(rig, {"ncf": "B0100000093"})
    second = _read(rig, {"ncf": "B0100000093"})
    other_supplier = _read(rig, {"ncf": "B0100000093", "rnc": OTHER_SUPPLIER})

    for receipt in (first, second):
        assert _same_as_the_list(rig, receipt)["listo_gaps"] == ["duplicate"]
    assert _same_as_the_list(rig, other_supplier)["listo_gaps"] == []


def test_a_read_of_several_purchases_says_so_on_the_dossier(rig) -> None:  # noqa: ANN001
    listos._set_read(rig, next(rig.reads), {})
    rig.stub.rows = [
        {**receipt_purchase(), "amount": "100.00"},
        {**receipt_purchase(), "amount": "200.00"},
    ]
    many = _upload(rig, RECEIPT + b"\xd5").json()["id"]
    draft_id = _get(rig, f"/business/receipts/{many}")["draft_id"]

    dossier = _same_as_the_list(rig, many, draft_id)

    assert dossier["bandeja_group"]["reason"] == "several_purchases"
    assert "several_purchases" in dossier["listo_gaps"]


def test_an_open_question_blocks_on_the_dossier_as_on_the_row(rig) -> None:  # noqa: ANN001
    receipt = _read(rig)
    with Connection.connect(shared.DSN) as db:
        db.execute(
            "insert into public.business_questions"
            " (space_id,draft_id,field,asked_of,channel,state,prompt,allowed_answers)"
            " values (%s,%s,'funding','owner','web','open','¿Cómo se pagó?',"
            " array['known','owner_does_not_know'])",
            (rig.alice.space_id, _named(rig, receipt)["draft_id"]),
        )

    assert _same_as_the_list(rig, receipt)["listo_gaps"] == ["blocked"]


def test_an_unverified_sender_stays_among_the_gaps_behind_another(
    rig,  # noqa: ANN001
    monkeypatch,  # noqa: ANN001
) -> None:
    set_read = listos._set_read
    monkeypatch.setattr(
        listos, "_set_read", lambda rig, index, read: set_read(rig, index, {"ncf": None})
    )
    runtime, receipt, _ = listos._delivered(rig, monkeypatch, RECEIPT + b"\xd7")
    assert _same_as_the_list(rig, receipt)["listo_gaps"] == ["missing_ncf"]

    [rule] = runtime.store.list_senders(rig.alice.space_id)
    runtime.store.remove_sender(rig.alice.space_id, rule.id)
    dossier = _same_as_the_list(rig, receipt)

    assert dossier["bandeja_group"]["reason"] == "missing_ncf"
    assert dossier["listo_gaps"] == ["missing_ncf", "unverified_sender"]


#: The publisher text behind each status; ``desconocido`` is text no row maps.
RAW_BY_STATUS = {
    RegistryStatus.VERIFICADO: "ACTIVO",
    **{info.status: raw for raw, info in INACTIVE_BY_RAW.items()},
    RegistryStatus.DESCONOCIDO: "EN TRAMITE",
}


@pytest.fixture
def register():  # noqa: ANN201
    """Lists RNCs on the DGII register for one test, and unlists them after."""

    listed: list[str] = []

    def add(rnc: str, status: str) -> None:
        listed.append(rnc)
        with Connection.connect(shared.DSN) as db:
            db.execute(
                "insert into public.dgii_rnc (rnc, name, trade_name, status, file_date)"
                " values (%s, 'FERRETERIA REGISTRADA', null, %s, %s)",
                (rnc, status, date(2026, 10, 17)),
            )

    yield add
    with Connection.connect(shared.DSN) as db:
        db.execute("delete from public.dgii_rnc where rnc=any(%s)", (listed,))


@pytest.mark.parametrize("status", list(RegistryStatus), ids=lambda status: status.value)
def test_the_dossier_carries_the_registers_status_of_the_rnc(
    rig,  # noqa: ANN001
    register,  # noqa: ANN001
    status: RegistryStatus,
) -> None:
    register(SUPPLIER, RAW_BY_STATUS[status])

    dossier = _same_as_the_list(rig, _read(rig))

    assert dossier["rnc_registry_status"] == status.value


def test_an_rnc_the_register_does_not_list_is_not_found(rig, register) -> None:  # noqa: ANN001
    register(LISTED, "ACTIVO")

    dossier = _same_as_the_list(rig, _read(rig))

    assert dossier["rnc_registry_status"] == "not_found"


def test_a_record_with_no_rnc_carries_no_register_status(rig, register) -> None:  # noqa: ANN001
    register(LISTED, "ACTIVO")

    dossier = _same_as_the_list(rig, _read(rig, {"rnc": None}))

    assert dossier["rnc_registry_status"] is None


def test_one_dossier_computes_its_standing_inputs_once(actions) -> None:
    from cProfile import Profile

    from argus.domain.business.actions import dossier

    service, context, _ = actions
    draft_id = actions_support.ready(service, context)
    with Profile() as calls:
        view = service.dossier(context, draft_id)

    assert view.review_state == "open"
    inputs = (
        dossier.record_context, dossier.review_questions, dossier.workflow_blockers,
        dossier.review_flags, dossier.repeated_comprobantes,
    )
    counts = {entry.code: entry.callcount for entry in calls.getstats()}
    assert {read.__name__: counts.get(read.__code__, 0) for read in inputs} == {
        read.__name__: 1 for read in inputs
    }
