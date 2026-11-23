"""Over HTTP on the real app and Postgres: the handover download builds its
records sheet under the Business's one owner lock, so a 606 write that runs at
the same time either lands before the build, and the sheet carries it, or
waits for the build, lands after it, and the next download carries it. Each
interleaving is forced with a pause at a seam, the same pause a slow export or
a slow write gives. All values are made up."""

from __future__ import annotations

import csv
import io
import json
import threading
from unittest.mock import patch
from uuid import uuid4
from zipfile import ZipFile

import pytest
from argus.domain.business import export as export_module
from argus.domain.business.actions import mutations
from argus.domain.business.contracts.dgii import PurchaseDeclaration
from argus.domain.ingestion.documents import store_postgres

from tests.business_accept_support import accepting
from tests.test_business_fiscal_routes_postgres import (  # noqa: F401
    API,
    _known,
    _note,
    _post,
    _review,
    world,
)
from tests.test_business_scope_switch_routes_postgres import (
    pytestmark as _local_supabase,
)

pytestmark = _local_supabase
FILER = "199990013"
SUPPLIER = "199990021"


@pytest.fixture(autouse=True)
def _typed_notes(typed_notes_on: None) -> None:
    """These flows start a draft by typing a note: typed notes on."""


@pytest.fixture(autouse=True)
def _configured_filer(world) -> None:  # noqa: ANN001, F811
    alice = world.alice
    profile = world.client.patch(
        f"{API}/business/fiscal-profile",
        json={
            "name": "Ferretería Prueba",
            "previous_name": "Ferretería Prueba",
            "tax_id": {"type": "rnc", "value": FILER},
            "previous_tax_id": None,
        },
        headers={**alice.headers, "Idempotency-Key": str(uuid4())},
    )
    assert profile.status_code == 200, profile.text


def recorded(world, ncf):  # noqa: ANN001, ANN201, F811
    """One approved purchase of September 2026 with its 606 data complete and
    Forma de Pago 01, on a Business whose RNC is set."""

    alice = world.alice
    note = _note(world, alice, f"Compra {ncf}")
    assert note.status_code == 200, note.text
    draft = note.json()["draft_id"]
    version = dossier(world, draft)["version"]
    reviewed = _review(
        world,
        draft,
        {
            "version": version,
            "facts": _known(
                {
                    "kind": "expense",
                    "amount": "1180.00",
                    "currency": "DOP",
                    "occurred_on": "2026-09-03",
                    "counterparty": "Ferretería Prueba",
                    "funding": {"kind": "owner_funds"},
                    "business_share": {"kind": "all"},
                }
            ),
            "dgii": {
                "fiscal": {"rnc": SUPPLIER, "ncf": ncf, "itbis": "180.00"},
                "declaration": {
                    **{name: None for name in PurchaseDeclaration.model_fields},
                    "form": "606",
                    "actual_refund": False,
                    "category_suggested": False,
                },
            },
        },
        alice.headers,
    )
    assert reviewed.status_code == 200, reviewed.text
    approved = _post(
        world,
        f"/business/drafts/{draft}/approve",
        accepting(reviewed.json(), "record_expense"),
        alice.headers,
    )
    assert approved.status_code == 200, approved.text
    done = write(
        world, draft, approved.json()["version"], category="02", payment_method="01"
    )
    assert done.status_code == 200, done.text
    return draft, done.json()["version"]


def write(world, draft, version, **purchase):  # noqa: ANN001, ANN201, F811
    return _review(
        world,
        draft,
        {"version": version, "purchase": purchase or {"payment_method": "03"}},
        world.alice.headers,
    )


def dossier(world, draft):  # noqa: ANN001, ANN201, F811
    found = world.client.get(
        f"{API}/business/drafts/{draft}/dossier", headers=world.alice.headers
    )
    assert found.status_code == 200, found.text
    return found.json()


def download(world):  # noqa: ANN001, ANN201, F811
    return world.client.get(
        f"{API}/business/exports",
        params={"start": "2026-09-01", "end": "2026-09-30"},
        headers=world.alice.headers,
    )


def shipped_payment_form(response) -> str:  # noqa: ANN001
    """The Forma de pago of the one row the downloaded records sheet carries."""

    assert response.status_code == 200, response.text
    with ZipFile(io.BytesIO(response.content)) as archive:
        text = archive.read("records.csv").decode("utf-8-sig")
    [row] = csv.DictReader(io.StringIO(text))
    return row["Forma de pago"]


def paused(target, reached, resume):  # noqa: ANN001, ANN201
    """The seam, wrapped: it signals that it was reached and waits to go on."""

    def wrapper(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        reached.set()
        assert resume.wait(20)
        return target(*args, **kwargs)

    return wrapper


def in_thread(outcome, name, call):  # noqa: ANN001, ANN201
    thread = threading.Thread(target=lambda: outcome.__setitem__(name, call()))
    thread.start()
    return thread


def test_a_write_between_the_snapshot_and_the_build_is_in_the_sheet(world):  # noqa: ANN001, F811
    """The export has read the period and is rebuilding images when a person
    saves Forma de Pago 03. The sheet ships 03."""

    draft, version = recorded(world, "B0100001001")
    reached, resume = threading.Event(), threading.Event()
    outcome = {}
    with patch.object(
        store_postgres,
        "PostgresDocumentStore",
        paused(store_postgres.PostgresDocumentStore, reached, resume),
    ):
        exporter = in_thread(outcome, "export", lambda: download(world))
        assert reached.wait(20)
        changed = write(world, draft, version)
        resume.set()
        exporter.join(30)
    assert changed.status_code == 200, changed.text
    assert shipped_payment_form(outcome["export"]) == "03"
    view = dossier(world, draft)
    assert (view["dgii"]["payment_method"], view["declaration_editable"]) == ("03", True)


def test_an_accepted_delete_between_the_snapshot_and_the_build_is_excluded(world):  # noqa: ANN001, F811
    draft, _ = recorded(world, "B0100001004")
    kept_draft, _ = recorded(world, "B0100001005")
    before = download(world)
    assert before.status_code == 200, before.text
    with ZipFile(io.BytesIO(before.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert len(manifest["records"]) == 2
        reconciled = {
            entry["draft_id"]: entry for entry in manifest["dgii"]["reconciliation"]
        }
        assert {
            draft_id: entry["disposition"] for draft_id, entry in reconciled.items()
        } == {
            draft: "606",
            kept_draft: "606",
        }
        removed_originals = {
            item["file"] for item in manifest["sources"] if draft in item["draft_ids"]
        }
        assert b"Compra B0100001004" in [archive.read(name) for name in removed_originals]

    reached, resume = threading.Event(), threading.Event()
    outcome = {}
    with patch.object(
        store_postgres,
        "PostgresDocumentStore",
        paused(store_postgres.PostgresDocumentStore, reached, resume),
    ):
        exporter = in_thread(outcome, "export", lambda: download(world))
        try:
            assert reached.wait(20)
            deleted = _post(
                world,
                f"/business/drafts/{draft}/delete",
                {},
                world.alice.headers,
            )
            assert deleted.status_code == 200, deleted.text
        finally:
            resume.set()
            exporter.join(30)

    after = outcome["export"]
    assert after.status_code == 200, after.text
    with ZipFile(io.BytesIO(after.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        rows = list(
            csv.DictReader(io.StringIO(archive.read("records.csv").decode("utf-8-sig")))
        )
        assert [row["NCF"] for row in rows] == ["B0100001005"]
        assert [row["activity_id"] for row in manifest["records"]] == [
            reconciled[kept_draft]["activity_id"]
        ]
        assert [entry["draft_id"] for entry in manifest["dgii"]["reconciliation"]] == [
            kept_draft
        ]
        assert all(item["draft_ids"] == [kept_draft] for item in manifest["sources"])
        assert b"Compra B0100001005" in [
            archive.read(item["file"]) for item in manifest["sources"]
        ]
        assert not removed_originals.intersection(archive.namelist())


def test_a_write_holding_the_owner_lock_lands_before_the_build(world):  # noqa: ANN001, F811
    """The write is saving its revision when the export starts. The export
    builds after that write commits: the sheet ships 03."""

    draft, version = recorded(world, "B0100001002")
    reached, resume = threading.Event(), threading.Event()
    outcome = {}
    with patch.object(
        mutations, "save_revision", paused(mutations.save_revision, reached, resume)
    ):
        writer = in_thread(outcome, "write", lambda: write(world, draft, version))
        assert reached.wait(20)
        exporter = in_thread(outcome, "export", lambda: download(world))
        exporter.join(5)
        resume.set()
        writer.join(30)
        exporter.join(30)
    assert outcome["write"].status_code == 200, outcome["write"].text
    assert shipped_payment_form(outcome["export"]) == "03"
    view = dossier(world, draft)
    assert (view["dgii"]["payment_method"], view["declaration_editable"]) == ("03", True)


def test_a_write_arriving_during_the_build_lands_after_it(world):  # noqa: ANN001, F811
    """The export is building its archive when a person saves Forma de Pago 03.
    The write waits for the export and lands: the sheet ships 01, the record
    holds 03, and the next download ships 03."""

    draft, version = recorded(world, "B0100001003")
    reached, resume = threading.Event(), threading.Event()
    outcome = {}
    with patch.object(
        export_module,
        "build_archive",
        paused(export_module.build_archive, reached, resume),
    ):
        exporter = in_thread(outcome, "export", lambda: download(world))
        assert reached.wait(20)
        writer = in_thread(outcome, "write", lambda: write(world, draft, version))
        writer.join(5)
        resume.set()
        exporter.join(30)
        writer.join(30)
    assert outcome["write"].status_code == 200, outcome["write"].text
    assert shipped_payment_form(outcome["export"]) == "01"
    view = dossier(world, draft)
    assert (view["dgii"]["payment_method"], view["declaration_editable"]) == ("03", True)
    assert shipped_payment_form(download(world)) == "03"


@pytest.mark.parametrize("field", ["amount", "ncf"])
def test_an_accepted_edit_during_export_updates_the_whole_package(world, field):  # noqa: F811
    draft, version = recorded(world, "B0100001006")
    reached, resume = threading.Event(), threading.Event()
    outcome = {}
    with patch.object(
        store_postgres,
        "PostgresDocumentStore",
        paused(store_postgres.PostgresDocumentStore, reached, resume),
    ):
        exporter = in_thread(outcome, "export", lambda: download(world))
        try:
            assert reached.wait(20)
            edit = {"facts": _known({"amount": "1380.00"})} if field == "amount" else {
                "dgii": {
                    "fiscal": {"rnc": SUPPLIER, "ncf": "B0100001007", "itbis": "180.00"},
                    "declaration": dossier(world, draft)["dgii"],
                }
            }
            changed = _review(
                world, draft, {"version": version, **edit},
                world.alice.headers,
            )
            assert changed.status_code == 200, changed.text
        finally:
            resume.set()
            exporter.join(30)
    response = outcome["export"]
    assert response.status_code == 200, response.text
    with ZipFile(io.BytesIO(response.content)) as archive:
        [row] = csv.DictReader(io.StringIO(archive.read("records.csv").decode("utf-8-sig")))
        manifest = json.loads(archive.read("manifest.json"))
    if field == "amount":
        assert (row["Total"], row["Subtotal"]) == ("1380.00", "1200.00")
    else:
        assert row["NCF"] == "B0100001007"
        assert manifest["records"][0]["activity_revision"] == "1"
    assert manifest["dgii"]["issues"] == []
    source_ids = {item["source_id"] for item in manifest["sources"]}
    [reconciled] = manifest["dgii"]["reconciliation"]
    assert set(reconciled["source_ids"]) <= source_ids
