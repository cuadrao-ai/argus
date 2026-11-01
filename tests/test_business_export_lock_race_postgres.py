"""Over HTTP on the real app and Postgres: the export builds its TXT and
freezes the lines it carries under the Business's one owner lock, so a 606
write that runs at the same time either lands before the build, and the TXT
carries it, or waits for the build and is refused. Each interleaving is forced
with a pause at a seam, the same pause a slow export or a slow write gives.
All values are made up."""

from __future__ import annotations

import io
import threading
from unittest.mock import patch
from uuid import uuid4
from zipfile import ZipFile

from argus.domain.business import export as export_module
from argus.domain.business.actions import mutations
from argus.domain.business.contracts.dgii import PurchaseDeclaration
from argus.domain.ingestion.documents import store_postgres
from psycopg import Connection

from tests import test_financial_accounts_postgres as shared
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
TXT_606 = f"dgii/DGII_F_606_{FILER}_202609.TXT"


def recorded(world, ncf):  # noqa: ANN001, ANN201, F811
    """One approved purchase of September 2026 with its 606 data complete and
    Forma de Pago 01, on a Business whose RNC is set, so the next download
    ships a 606 TXT with this one line."""

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
        {"version": reviewed.json()["version"], "action": "record_expense"},
        alice.headers,
    )
    assert approved.status_code == 200, approved.text
    done = write(world, draft, approved.json()["version"], category="02", payment_method="01")
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
    """The Forma de Pago column of the one line the downloaded 606 TXT carries."""

    assert response.status_code == 200, response.text
    with ZipFile(io.BytesIO(response.content)) as archive:
        line = archive.read(TXT_606).split(b"\r\n")[1].decode()
    return line.split("|")[-1]


def lock_rows(world) -> int:  # noqa: ANN001, F811
    with Connection.connect(shared.DSN) as db:
        return db.execute(
            "select count(*) from public.business_dgii_export_lines where space_id=%s",
            (world.alice.space_id,),
        ).fetchone()[0]


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


def test_a_write_between_the_snapshot_and_the_build_is_in_the_txt(world):  # noqa: ANN001, F811
    """The export has read the period and is rebuilding images when a person
    saves Forma de Pago 03. The TXT ships 03, and the record is frozen on 03."""

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
    assert (view["dgii"]["payment_method"], view["declaration_editable"]) == ("03", False)
    assert lock_rows(world) == 1


def test_a_write_holding_the_owner_lock_lands_before_the_build(world):  # noqa: ANN001, F811
    """The write passed the exported check and is saving its revision when the
    export starts. The export builds after that write commits: the TXT ships
    03, and the record is frozen on 03."""

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
    assert (view["dgii"]["payment_method"], view["declaration_editable"]) == ("03", False)
    assert lock_rows(world) == 1


def test_a_write_arriving_during_the_build_is_refused(world):  # noqa: ANN001, F811
    """The export is building its TXT when a person saves Forma de Pago 03. The
    write waits for the export and is refused with the exported code: the TXT
    ships 01 and the record stays on 01."""

    draft, version = recorded(world, "B0100001003")
    reached, resume = threading.Event(), threading.Event()
    outcome = {}
    with patch.object(
        export_module, "build_export", paused(export_module.build_export, reached, resume)
    ):
        exporter = in_thread(outcome, "export", lambda: download(world))
        assert reached.wait(20)
        writer = in_thread(outcome, "write", lambda: write(world, draft, version))
        writer.join(5)
        resume.set()
        exporter.join(30)
        writer.join(30)
    refused = outcome["write"]
    assert (refused.status_code, refused.json().get("code")) == (
        422,
        "fiscal_declaration_exported",
    ), refused.text
    assert shipped_payment_form(outcome["export"]) == "01"
    view = dossier(world, draft)
    assert (view["dgii"]["payment_method"], view["declaration_editable"]) == ("01", False)
    assert lock_rows(world) == 1
