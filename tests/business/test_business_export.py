import csv
import hashlib
import io
import json
from datetime import date, datetime, timezone
from uuid import UUID
from xml.etree import ElementTree
from zipfile import ZipFile

import pytest
from argus.domain.business import export

ACTIVITY = UUID(int=1)
DRAFT = UUID(int=2)
SOURCE = UUID(int=3)
ACCOUNT = UUID(int=4)
NOW = datetime(2026, 10, 11, 12, tzinfo=timezone.utc)


def activity(**updates):
    return {
        "activity_id": str(ACTIVITY),
        "revision": 1,
        "kind": "expense",
        "occurred_at": NOW,
        "time_zone": "America/Santo_Domingo",
        "recorded_at": NOW,
        "amount": "850.00",
        "amount_minor": 85000,
        "currency": "DOP",
        "funding": "owner_funds",
        "legs": [],
        "note": "SYNTHETIC — compra de prueba",
        "category_id": None,
        **updates,
    }


def snapshot(**updates):
    return export.ExportSnapshot(
        **{
            "period": export.ExportPeriod(date(2026, 10, 1), date(2026, 10, 31)),
            "activities": (activity(),),
            "sources": (
                export.ExportSource(
                    SOURCE,
                    (DRAFT,),
                    (ACTIVITY,),
                    "message",
                    text="  Original synthetic note\n",
                ),
            ),
            "unresolved": (),
            "captured_at": NOW,
            **updates,
        }
    )


def unpack(value):
    with ZipFile(io.BytesIO(value)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def sheet_rows(content, sheet=1):
    files = unpack(content)
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    strings = [
        "".join(node.itertext())
        for node in ElementTree.fromstring(files["xl/sharedStrings.xml"]).findall(
            "m:si", ns
        )
    ]
    root = ElementTree.fromstring(files[f"xl/worksheets/sheet{sheet}.xml"])
    assert not root.findall(".//m:f", ns)
    assert not root.findall(".//m:hyperlink", ns)
    return [
        [strings[int(cell.find("m:v", ns).text)] for cell in row]
        for row in root.findall("m:sheetData/m:row", ns)
    ]


def test_csv_xlsx_and_manifest_share_canonical_money():
    files = unpack(export.build_archive(snapshot(), lambda _: None))
    rows = list(csv.reader(io.StringIO(files["records.csv"].decode("utf-8-sig"))))
    assert sheet_rows(files["records.xlsx"]) == rows
    manifest = json.loads(files["manifest.json"])
    assert manifest["records"][0]["amount_minor"] == "85000"
    assert manifest["records"][0]["funding"] == "owner_funds"
    assert manifest["records"][0]["account_ids"] == ""
    assert manifest["records"][0]["draft_ids"] == str(DRAFT)
    original = files[manifest["sources"][0]["file"]]
    assert original == b"  Original synthetic note\n"
    assert manifest["sources"][0]["sha256"] == hashlib.sha256(original).hexdigest()
    assert (
        manifest["files"]["records.xlsx"]
        == hashlib.sha256(files["records.xlsx"]).hexdigest()
    )


@pytest.mark.parametrize(
    "note",
    [
        "=SUM(1,2)",
        "+1",
        "-1",
        "@SUM(1)",
        " \t=1",
        "\nhttp://evil.test",
        "https://example.test",
    ],
)
def test_untrusted_cells_never_become_formulas_or_hyperlinks(note):
    files = unpack(
        export.build_archive(snapshot(activities=(activity(note=note),)), lambda _: None)
    )
    rows = list(csv.reader(io.StringIO(files["records.csv"].decode("utf-8-sig"))))
    assert rows == sheet_rows(files["records.xlsx"])
    exported = rows[1][rows[0].index("note")]
    assert exported == (note if note.startswith("https:") else "'" + note)
    assert json.loads(files["manifest.json"])["records"][0]["note"] == note


def test_canonical_kind_currency_and_receiving_account_remain_explicit():
    income = activity(
        activity_id=str(UUID(int=9)),
        kind="income",
        currency="USD",
        amount="7.12",
        amount_minor=712,
        funding=None,
        legs=[{"account_id": str(ACCOUNT)}],
    )
    rows = export.record_rows(snapshot(activities=(activity(), income)))
    assert {(r["kind"], r["currency"], r["funding"], r["amount"]) for r in rows} == {
        ("expense", "DOP", "owner_funds", "850.00"),
        ("income", "USD", "business_account", "7.12"),
    }


def test_dates_use_canonical_timezone_and_do_not_invent_missing_dates():
    item = activity(occurred_at=datetime(2026, 10, 1, 1, tzinfo=timezone.utc))
    assert export.record_rows(snapshot(activities=(item,))) == []
    with pytest.raises((TypeError, AttributeError)):
        export.record_rows(snapshot(activities=(activity(occurred_at=None),)))


def test_undated_drafts_are_separate_from_money():
    unresolved = (
        {
            "draft_id": str(DRAFT),
            "version": 1,
            "review_state": "open",
            "occurred_on": None,
            "reason": "date_unknown",
        },
    )
    files = unpack(
        export.build_archive(
            snapshot(activities=(), unresolved=unresolved), lambda _: None
        )
    )
    manifest = json.loads(files["manifest.json"])
    assert manifest["records"] == []
    assert manifest["unresolved_drafts"] == list(unresolved)
    assert manifest["unresolved_in_money_totals"] is False
    assert len(sheet_rows(files["records.xlsx"], 2)) == 2
    assert b"Original synthetic note" in files[f"originals/{SOURCE}.txt"]


def test_attachment_bytes_path_and_individual_failure():
    content = b"%PDF-1.7\x00\xff synthetic bytes"
    sources = tuple(
        export.ExportSource(
            UUID(int=i),
            (DRAFT,),
            (ACTIVITY,),
            "attachment",
            filename="../../secret.pdf",
            media_type="application/pdf",
        )
        for i in (10, 11, 12)
    )

    def read(source):
        if source.source_id.int == 11:
            raise OSError("synthetic unavailable")
        return content if source.source_id.int == 10 else None

    files = unpack(export.build_archive(snapshot(sources=sources), read))
    manifest = json.loads(files["manifest.json"])
    assert [s["availability"] for s in manifest["sources"]] == [
        "included",
        "unavailable",
        "unavailable",
    ]
    assert not manifest["evidence_complete"]
    assert all(".." not in path for path in files)
    assert files[manifest["sources"][0]["file"]] == content
    assert manifest["sources"][0]["original_filename"] == "../../secret.pdf"


def test_hash_mismatch_and_size_limits_are_not_complete_evidence(monkeypatch):
    source = export.ExportSource(
        SOURCE, (DRAFT,), (ACTIVITY,), "attachment", expected_sha256="0" * 64
    )
    files = unpack(
        export.build_archive(snapshot(sources=(source,)), lambda _: b"altered")
    )
    assert (
        json.loads(files["manifest.json"])["sources"][0]["availability"]
        == "hash_mismatch"
    )
    monkeypatch.setattr(export, "MAX_SOURCE_BYTES", 1)
    files = unpack(export.build_archive(snapshot(), lambda _: None))
    assert (
        json.loads(files["manifest.json"])["sources"][0]["availability"] == "size_limit"
    )


def test_unknown_funding_stays_unknown_and_exact_large_amount_is_text():
    item = activity(
        funding=None, amount_minor=9007199254740993, amount="90071992547409.93"
    )
    files = unpack(export.build_archive(snapshot(activities=(item,)), lambda _: None))
    rows = sheet_rows(files["records.xlsx"])
    assert rows[1][rows[0].index("amount_minor")] == "9007199254740993"
    assert rows[1][rows[0].index("funding")] == "unknown"


def test_range_rows_sources_and_cell_limits_fail_explicitly(monkeypatch):
    with pytest.raises(ValueError):
        export.ExportPeriod(date(2025, 1, 1), date(2026, 10, 1))
    with pytest.raises(ValueError):
        export.ExportPeriod(date(2026, 10, 2), date(2026, 10, 1))
    with pytest.raises(export.ExportLimit):
        export.record_rows(snapshot(activities=(activity(note="x" * 32768),)))
    with pytest.raises(ValueError, match="duplicate_canonical_activity"):
        export.record_rows(snapshot(activities=(activity(), activity())))
    monkeypatch.setattr(export, "MAX_ROWS", 0)
    with pytest.raises(export.ExportLimit):
        export.record_rows(snapshot())


def test_outside_period_originals_are_not_loaded():
    seen = []
    excluded = activity(occurred_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
    files = unpack(
        export.build_archive(
            snapshot(activities=(excluded,)), lambda source: seen.append(source)
        )
    )
    assert seen == []
    assert json.loads(files["manifest.json"])["sources"] == []


def test_missing_source_links_are_explicit_not_complete_evidence():
    pending = {
        "draft_id": str(DRAFT),
        "version": 1,
        "review_state": "open",
        "occurred_on": None,
        "reason": "draft_not_prepared",
    }
    files = unpack(
        export.build_archive(snapshot(sources=(), unresolved=(pending,)), lambda _: None)
    )
    manifest = json.loads(files["manifest.json"])
    assert not manifest["evidence_complete"]
    assert manifest["activities_without_linked_sources"] == [str(ACTIVITY)]
    assert manifest["drafts_without_linked_sources"] == [str(DRAFT)]


def test_individual_total_byte_budget_preserves_successful_siblings(monkeypatch):
    sources = tuple(
        export.ExportSource(UUID(int=i), (DRAFT,), (ACTIVITY,), "message", text="abc")
        for i in (10, 11)
    )
    monkeypatch.setattr(export, "MAX_TOTAL_BYTES", 4)
    files = unpack(export.build_archive(snapshot(sources=sources), lambda _: None))
    manifest = json.loads(files["manifest.json"])
    assert [s["availability"] for s in manifest["sources"]] == ["included", "size_limit"]
    assert files[manifest["sources"][0]["file"]] == b"abc"
    assert manifest["sources"][1]["file"] is None


@pytest.fixture
def export_client(monkeypatch):
    from types import SimpleNamespace
    from uuid import uuid4

    from argus.api.business import BusinessPerson, require_business_person
    from argus.api.business_drafts import DraftContext, require_drafts
    from argus.api.documents import require_saved_documents
    from argus.api.routers import business_export
    from argus.domain.business.spaces import Space
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    calls = []
    actor_id, space_id = uuid4(), uuid4()
    resolved = SimpleNamespace(
        actor=SimpleNamespace(actor_id=actor_id, space_id=space_id), owner_id=actor_id
    )

    class Service:
        authority = object()

        def resolve_actor(self, actor, **_pin):
            calls.append(("owner", actor))
            return resolved

        def context_for_draft(self, actor, draft, **_pin):
            calls.append(("draft", actor, draft))
            resolved.owner_id = uuid4()
            return resolved

    class Spaces:
        value = Space(str(space_id), "Synthetic Business")

        def get(self, space):
            return self.value if self.value and self.value.id == space else None

        def open_space(self, person):
            calls.append(("space", person))
            return self.value

    service, spaces = Service(), Spaces()
    app = FastAPI()

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = "export-test"
        return await call_next(request)

    app.include_router(business_export.router)
    app.dependency_overrides[require_drafts] = lambda: DraftContext(service, actor_id)
    app.dependency_overrides[require_business_person] = lambda: BusinessPerson(
        str(actor_id), spaces
    )
    app.dependency_overrides[require_saved_documents] = lambda: SimpleNamespace(
        store=SimpleNamespace(objects=object())
    )

    def package(authority, context, period, objects):
        assert authority is service.authority and context is resolved
        calls.append(("export", period))
        return build_fixture_zip

    build_fixture_zip = export.build_archive(snapshot(), lambda _: None)
    monkeypatch.setattr(business_export, "export_package", package)
    with TestClient(app) as client:
        yield client, calls, service, spaces, actor_id, build_fixture_zip


def test_export_api_owner_snapshot_and_safe_binary_headers(export_client):
    client, calls, _, _, actor, content = export_client
    response = client.get("/business/exports?start=2026-10-01&end=2026-10-31")
    assert response.status_code == 200 and response.content == content
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="business-export-2026-10-01-2026-10-31.zip"'
    )
    assert calls[0] == ("space", str(actor))
    assert calls[1][1].actor_id == actor


def test_export_api_accountant_anchor_never_reads_own_space(export_client):
    client, calls, _, spaces, actor, _ = export_client
    spaces.value = None
    response = client.get(
        f"/business/exports?start=2026-10-01&end=2026-10-31&draft_id={DRAFT}"
    )
    assert response.status_code == 200
    assert calls[0] == ("draft", actor, DRAFT)
    assert not any(call[0] == "space" for call in calls)


def test_export_api_foreign_anchor_never_falls_back(export_client):
    from argus.domain.business.authority import ActionError

    client, calls, service, _, _, _ = export_client

    def refuse(*_, **__):
        raise ActionError("not_found", "business_record_not_found")

    service.context_for_draft = refuse
    response = client.get(
        f"/business/exports?start=2026-10-01&end=2026-10-31&draft_id={DRAFT}"
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "business_record_not_found"
    assert response.headers["cache-control"] == "no-store"
    assert not calls


def test_export_api_missing_own_space_does_not_create_one(export_client):
    client, calls, _, spaces, _, _ = export_client
    spaces.value = None
    response = client.get("/business/exports?start=2026-10-01&end=2026-10-31")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "business_space_missing"
    assert response.headers["cache-control"] == "no-store"
    assert len(calls) == 1


@pytest.mark.parametrize(
    "query",
    [
        "",
        "start=2026-10-01",
        "start=2026-10-01&end=2026-09-30",
        "start=2025-01-01&end=2026-01-02",
        "start=0&end=2026-10-01",
        "start=20261001&end=2026-10-01",
        "start=2026-02-30&end=2026-10-01",
        "start=2026-10-01&end=2026-10-31&draft_id=bad",
        "start=2026-10-01&end=2026-10-31&space_id=bad",
        "start=2026-10-01&start=2026-10-02&end=2026-10-31",
    ],
)
def test_export_api_rejects_invalid_dates_and_authority_parameters(export_client, query):
    client, calls, _, _, _, _ = export_client
    response = client.get("/business/exports?" + query)
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    assert not calls


@pytest.mark.parametrize("end", ["2026-01-01", "2027-01-01"])
def test_export_api_inclusive_one_and_366_day_bounds(export_client, end):
    client, _, _, _, _, _ = export_client
    assert client.get(f"/business/exports?start=2026-01-01&end={end}").status_code == 200


@pytest.mark.parametrize(
    "error,status,code",
    [
        (export.ExportLimit("export_archive_limit"), 413, "export_archive_limit"),
        (export.ExportLimit("export_history_limit"), 413, "export_history_limit"),
    ],
)
def test_export_api_limit_failure_is_problem_not_partial_zip(
    export_client, monkeypatch, error, status, code
):
    from argus.api.routers import business_export

    client, _, _, _, _, _ = export_client

    def refuse(*_, **__):
        raise error

    monkeypatch.setattr(business_export, "export_package", refuse)
    response = client.get("/business/exports?start=2026-10-01&end=2026-10-31")
    assert response.status_code == status
    assert response.json()["detail"]["code"] == code
    assert response.headers["cache-control"] == "no-store"
    assert not response.content.startswith(b"PK")


def test_export_api_final_authorization_or_database_failure_emits_no_archive(
    export_client, monkeypatch
):
    from argus.api.routers import business_export
    from argus.domain.business.authority import ActionError
    from psycopg import OperationalError

    client, _, _, _, _, _ = export_client
    for error, status in [
        (ActionError("not_found", "business_record_not_found"), 404),
        (OperationalError("synthetic DB loss"), 503),
    ]:

        def refuse(*_, failure=error, **__):
            raise failure

        monkeypatch.setattr(business_export, "export_package", refuse)
        response = client.get("/business/exports?start=2026-10-01&end=2026-10-31")
        assert response.status_code == status
        assert response.headers["cache-control"] == "no-store"
        assert not response.content.startswith(b"PK")


def test_noncanonical_source_identifier_cannot_form_archive_path():
    source = export.ExportSource(
        "../../outside", (DRAFT,), (ACTIVITY,), "message", text="unchanged"
    )
    with pytest.raises(ValueError):
        export.build_archive(snapshot(sources=(source,)), lambda _: None)


@pytest.mark.parametrize(
    "instant",
    [
        datetime(2026, 9, 10, 0, 17, tzinfo=timezone.utc),
        datetime(2026, 1, 1, 1, 17, tzinfo=timezone.utc),
    ],
)
def test_package_capture_is_canonical_utc_instant_not_record_date(monkeypatch, instant):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from argus.domain import store
    from argus.domain.business import authority
    from argus.domain.recording import canonical_groups

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz)

    monkeypatch.setattr(store, "datetime", Frozen)
    context = SimpleNamespace(
        owner_id="owner",
        actor=SimpleNamespace(space_id="space"),
        grant_id="grant",
        scope=object(),
    )
    authorized = SimpleNamespace(context=context, require=lambda capability: None)
    monkeypatch.setattr(authority, "authorize", lambda *args: authorized)
    monkeypatch.setattr(
        canonical_groups,
        "load",
        lambda *args, **kwargs: canonical_groups.ResolvedGroups([], {}, {}, {}),
    )
    pool = MagicMock()
    cursor = pool.connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = {"count": 0}
    cursor.fetchall.side_effect = [
        [
            {
                "id": DRAFT,
                "version": 1,
                "state": "open",
                "activity_id": None,
                "resolution": {},
            }
        ],
        [],
    ]
    period = export.ExportPeriod(date(2025, 12, 1), date(2025, 12, 31))

    files = unpack(
        export.export_package(SimpleNamespace(pool=pool), context, period, None)
    )
    manifest = json.loads(files["manifest.json"])

    assert manifest["captured_at"] == instant.isoformat()
    assert manifest["period"]["start"] == "2025-12-01"
    assert manifest["period"]["end"] == "2025-12-31"
    assert manifest["records"] == []
    assert manifest["unresolved_drafts"][0]["occurred_on"] is None
