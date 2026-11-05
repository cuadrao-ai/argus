"""Over HTTP on the real app and Postgres: a download is not final. A record
stays open to 606 data, the Personal mark and the 606 answer after an export,
and the next export carries the change. Every download adds its own rows to
business_dgii_export_lines. All values are made up."""

from __future__ import annotations

import io
from zipfile import ZipFile

from argus.domain.business.dgii_columns import PURCHASE_COLUMNS
from faker import Faker
from psycopg import Connection

from tests import test_financial_accounts_postgres as shared
from tests.test_business_export_lock_race_postgres import (
    TXT_606,
    dossier,
    download,
    recorded,
    write,
)
from tests.test_business_fiscal_routes_postgres import (  # noqa: F401
    _as,
    _post,
    world,
)
from tests.test_business_scope_switch_routes_postgres import (
    pytestmark as _local_supabase,
)

pytestmark = _local_supabase
fake = Faker()
COLUMNS = [name for name, _ in PURCHASE_COLUMNS]


def fresh_ncf() -> str:
    return f"B01{fake.numerify('########')}"


def lines_606(response) -> list[dict[str, str]]:  # noqa: ANN001
    """The lines of the downloaded 606 TXT by column name, empty when the
    archive ships no 606 TXT."""

    assert response.status_code == 200, response.text
    with ZipFile(io.BytesIO(response.content)) as archive:
        if TXT_606 not in archive.namelist():
            return []
        rows = archive.read(TXT_606).decode().split("\r\n")[1:]
    return [dict(zip(COLUMNS, row.split("|"), strict=True)) for row in rows if row]


def export_rows(world) -> list[tuple[str, str]]:  # noqa: ANN001, F811
    with Connection.connect(shared.DSN) as db:
        rows = db.execute(
            "select form,period from public.business_dgii_export_lines"
            " where space_id=%s order by exported_at,id",
            (world.alice.space_id,),
        ).fetchall()
    return [tuple(row) for row in rows]


def test_an_edit_after_an_export_is_in_the_next_export(world) -> None:  # noqa: ANN001, F811
    """Export, edit, export again: the second file carries the edit, and each
    download keeps its own record of the line."""

    ncf = fresh_ncf()
    draft, _ = recorded(world, ncf)

    [first] = lines_606(download(world))
    assert (first["ncf"], first["category"], first["payment_method"]) == (ncf, "02", "01")
    assert export_rows(world) == [("606", "202609")]

    version = dossier(world, draft)["version"]
    edited = write(world, draft, version, category="03", payment_method="04")
    assert edited.status_code == 200, edited.text
    saved = edited.json()
    assert (saved["dgii"]["category"], saved["dgii"]["payment_method"]) == ("03", "04")
    assert saved["declaration_editable"] is True

    [second] = lines_606(download(world))
    assert (second["ncf"], second["category"], second["payment_method"]) == (
        ncf,
        "03",
        "04",
    )
    assert export_rows(world) == [("606", "202609"), ("606", "202609")]
    assert dossier(world, draft)["declaration_editable"] is True


def test_the_personal_mark_and_the_606_answer_reach_the_next_export(world) -> None:  # noqa: ANN001, F811
    """A line already downloaded can leave the next file as Personal and come
    back on the accountant's yes. A download that leaves it out records no row
    for it, and the earlier row stays."""

    ncf = fresh_ncf()
    draft, _ = recorded(world, ncf)
    assert [line["ncf"] for line in lines_606(download(world))] == [ncf]

    marked = _post(
        world,
        f"/business/drafts/{draft}/personal",
        {"version": dossier(world, draft)["version"], "personal": True},
        world.alice.headers,
    )
    assert marked.status_code == 200, marked.text
    assert marked.json()["personal"] is True
    assert lines_606(download(world)) == []
    assert export_rows(world) == [("606", "202609")]

    answered = _post(
        world,
        f"/business/drafts/{draft}/fiscal-inclusion",
        {"version": marked.json()["version"], "include": True},
        _as(world.bob, world.grant),
    )
    assert answered.status_code == 200, answered.text
    assert answered.json()["include_606"] is True
    assert [line["ncf"] for line in lines_606(download(world))] == [ncf]
    assert export_rows(world) == [("606", "202609"), ("606", "202609")]
