from types import SimpleNamespace
from urllib.parse import quote

import pytest
from argus.api.business import require_business_person, require_business_surface
from argus.api.business_annotations import router as annotations_router
from argus.api.business_drafts import DraftContext, require_drafts
from argus.api.business_reports import router as reports_router
from argus.api.documents import require_saved_documents
from argus.domain.business.reporting_preferences import ReportRecipeV2
from argus.domain.business.reporting_views import list_views
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests import test_business_actions_postgres as shared
from tests import test_registros_annotations_postgres as annotations
from tests.test_business_reporting_postgres import record_expense, viewer_context

documents = annotations.documents
users = shared.users
actions = shared.actions
pytestmark = [shared.pytestmark, pytest.mark.owner_acts]


@pytest.fixture
def client(actions, documents):
    service, context, _ = actions
    app = FastAPI()
    app.include_router(reports_router, prefix="/business")
    app.include_router(annotations_router, prefix="/business")
    selected = [context]

    @app.middleware("http")
    async def identify(request, call_next):
        request.state.request_id = "synthetic-registros"
        return await call_next(request)

    app.dependency_overrides[require_business_surface] = lambda: None
    app.dependency_overrides[require_drafts] = lambda: DraftContext(
        service,
        selected[0].actor.actor_id,
        str(selected[0].actor.space_id),
        selected[0].grant_id,
    )
    app.dependency_overrides[require_business_person] = lambda: SimpleNamespace(
        spaces=None
    )
    app.dependency_overrides[require_saved_documents] = lambda: documents[0]
    with TestClient(app) as http:
        yield http, selected


def test_v2_requires_explicit_version_and_private_preferences_restore(
    client, actions, users
):
    http, _ = client
    service, context, _ = actions
    assert (
        http.post("/business/reports/query", json={"sort": "name_asc"}).status_code == 422
    )
    assert (
        http.post(
            "/business/reports/query", json={"presentation": {"density": 56}}
        ).status_code
        == 422
    )
    recipe = ReportRecipeV2(
        sort="name_desc",
        page_size=100,
        presentation={"density": 56, "hidden": ["funding", "note"]},
    )
    response = http.post(
        "/business/report-views",
        json={"name": "My report", "recipe": recipe.model_dump(mode="json")},
        headers={"Idempotency-Key": "saved"},
    )
    assert response.status_code == 201, response.text
    reread = http.get("/business/report-views").json()[0]
    assert reread["recipe"] == recipe.model_dump(mode="json")
    viewer = viewer_context(service, context, users["other"])
    assert list_views(service.authority, viewer) == ()
    with service.authority.pool.connection() as db:
        for role in ("anon", "authenticated"):
            assert not db.execute(
                "select has_table_privilege(%s,%s,%s)",
                (
                    role,
                    "argus_private.business_saved_report_views",
                    "select,insert,update,delete",
                ),
            ).fetchone()[0]


def test_current_note_and_supporting_public_contract(client, actions):
    http, _ = client
    service, context, _ = actions
    draft, _ = record_expense(service, context)
    version = service.dossier(context, draft).version
    url = f"/business/drafts/{draft}"
    response = http.put(
        url + "/current-note",
        json={"expected_version": version, "note": "😀" * 500},
        headers={"Idempotency-Key": "note"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    saved = response.json()
    assert saved["dossier"]["current_note"] == "😀" * 500
    assert saved["dossier"]["history"][-1]["after_current_note"] == "😀" * 500
    assert (
        http.put(
            url + "/current-note",
            json={"expected_version": version, "note": "losing draft"},
            headers={"Idempotency-Key": "loser"},
        ).status_code
        == 409
    )
    assert (
        http.put(
            url + "/current-note",
            json={"expected_version": saved["result"]["version"], "note": "😀" * 501},
            headers={"Idempotency-Key": "too-long"},
        ).status_code
        == 422
    )
    headers = {
        "X-Draft-Version": str(saved["result"]["version"]),
        "X-Document-Filename": quote("José😀.txt"),
        "Content-Type": "text/plain",
        "Idempotency-Key": "file",
    }
    first = http.post(
        url + "/supporting-files", content=b"public synthetic", headers=headers
    )
    assert first.status_code == 200, first.text
    assert first.json()["result"]["outcome"] == "appended"
    assert first.json()["dossier"]["sources"][-1]["filename"] == "José😀.txt"
    replay = http.post(
        url + "/supporting-files", content=b"public synthetic", headers=headers
    )
    assert replay.status_code == 200
    assert replay.json()["result"] == first.json()["result"]
    assert len(replay.json()["dossier"]["history"]) == len(
        first.json()["dossier"]["history"]
    )
    assert (
        http.post(
            url + "/supporting-files", content=b"changed", headers=headers
        ).status_code
        == 409
    )
    assert (
        http.post(
            url + "/supporting-files",
            content=b"public synthetic",
            headers={**headers, "Content-Type": "application/unknown"},
        ).status_code
        == 415
    )
    query = http.post(
        "/business/reports/query", json={"schema_version": 2, "filters": {"q": "jose"}}
    ).json()
    assert (
        query["items"][0]["attachment_sources"][0]["receipt_id"]
        == first.json()["result"]["receipt_id"]
    )
    assert query["items"][0]["can_append_supporting"]


def test_v2_layout_does_not_change_export_fingerprint(client, actions):
    http, _ = client
    service, context, _ = actions
    for _ in range(26):
        shared.ready(service, context)
    request = {"schema_version": 2, "sort": "date_asc"}
    answer = http.post("/business/reports/query", json=request).json()
    changed = {
        **request,
        "page": 2,
        "page_size": 25,
        "columns": ["note"],
        "presentation": {"density": 40},
    }
    second = http.post("/business/reports/query", json=changed).json()
    assert answer["fingerprint"] == second["fingerprint"]
    assert second["matching_count"] == 26 and len(second["items"]) == 1
    response = http.post(
        "/business/reports/export",
        json={"report": changed, "expected_fingerprint": answer["fingerprint"]},
    )
    assert response.status_code == 200, response.text


def test_invalid_source_fails_without_history(client, actions):
    http, _ = client
    service, context, _ = actions
    draft = shared.ready(service, context)
    before = service.dossier(context, draft)
    response = http.post(
        f"/business/drafts/{draft}/supporting-files",
        content=b"not a pdf",
        headers={
            "X-Draft-Version": "1",
            "Content-Type": "application/pdf",
            "Idempotency-Key": "invalid",
        },
    )
    assert response.status_code == 422
    assert service.dossier(context, draft) == before


def test_changed_filename_conflicts_even_if_storage_display_normalizes_it(
    client, actions
):
    http, _ = client
    service, context, _ = actions
    draft = shared.ready(service, context)
    headers = {
        "X-Draft-Version": "1",
        "Content-Type": "text/plain",
        "Idempotency-Key": "filename",
        "X-Document-Filename": "same%00.txt",
    }
    url = f"/business/drafts/{draft}/supporting-files"
    first = http.post(url, content=b"file-name fixture", headers=headers)
    assert first.status_code == 200, first.text
    changed = http.post(
        url,
        content=b"file-name fixture",
        headers={**headers, "X-Document-Filename": "same.txt"},
    )
    assert changed.status_code == 409
