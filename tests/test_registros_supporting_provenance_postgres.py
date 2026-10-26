"""Inert evidence must not select the financial basis of a report or export."""

import csv
import json
from datetime import datetime, timezone
from io import BytesIO, StringIO
from uuid import UUID, uuid4
from zipfile import ZipFile

import pytest
from argus.domain.business.contracts.actions import ApproveExpense
from argus.domain.business.contracts.dossier import AttachmentSource
from argus.domain.business.reporting_store import read_recorded
from argus.domain.recording.money_schemas import MoneyRequest

from tests import test_business_actions_postgres as shared
from tests import test_registros_api_postgres as api
from tests.test_business_reporting_postgres import viewer_context

users = api.users
actions = api.actions
documents = api.documents
client = api.client
pytestmark = [shared.pytestmark, pytest.mark.owner_acts]
FINANCIAL_FIELDS = (
    "gross_amount",
    "currency",
    "report_date",
    "date_basis",
    "recorded_amount",
    "money_effect",
    "family",
    "stage",
    "technical_state",
    "workflow_blockers",
    "document_kind",
    "fiscal_classification",
    "settlement_status",
)


def report(http, **filters):
    response = http.post(
        "/business/reports/query", json={"schema_version": 2, "filters": filters}
    )
    assert response.status_code == 200, response.text
    return response.json()


def append(http, draft, version, *, key="support", content=b"inert supporting text"):
    return http.post(
        f"/business/drafts/{draft}/supporting-files",
        content=content,
        headers={
            "X-Draft-Version": str(version),
            "Idempotency-Key": key,
            "X-Document-Filename": "Jos%C3%A9.txt",
            "Content-Type": "text/plain",
        },
    )


def correct_money(service, context, activity_id):
    [original] = read_recorded(service.authority, context).records
    activity = json.loads(original.activity_json)
    command = MoneyRequest(
        kind="expense",
        account_id=activity["legs"][0]["account_id"],
        amount="25.00",
        occurred_at=datetime(2026, 10, 15, 12, tzinfo=timezone.utc),
        expected_revision=activity["revision"],
        reason="Synthetic supporting provenance regression",
    )
    preview = service.imports.money.preview(
        user_id=context.owner_id,
        request=command,
        scope=context.scope,
        activity_id=activity_id,
    )
    command = command.model_copy(
        update={
            "expected_versions": preview["expected_versions"],
            "preview_token": preview["preview_token"],
        }
    )
    service.imports.money.write(
        user_id=context.owner_id,
        request=command,
        idempotency_key=str(uuid4()),
        scope=context.scope,
        activity_id=activity_id,
    )


@pytest.mark.parametrize(
    "timing", ["before_approval", "after_approval", "after_correction"]
)
def test_supporting_file_preserves_manual_financial_basis(client, actions, timing):
    http, _ = client
    service, context, _ = actions
    draft = shared.ready(service, context)

    def attach_unchanged():
        before = report(http)
        version = service.dossier(context, draft).version
        response = append(http, draft, version)
        assert response.status_code == 200, response.text
        after = report(http)
        assert {key: after["items"][0][key] for key in FINANCIAL_FIELDS} == {
            key: before["items"][0][key] for key in FINANCIAL_FIELDS
        }
        assert after["totals"] == before["totals"]
        assert after["overview"] == before["overview"]
        assert after["items"][0]["has_document"] is True
        assert after["items"][0]["attachment_sources"][0]["download_available"] is True
        assert report(http, q="jose")["matching_count"] == 1
        assert report(http, q="inert supporting text")["matching_count"] == 0
        assert append(http, draft, version).json()["result"] == response.json()["result"]

    if timing == "before_approval":
        attach_unchanged()
    approval = service.approve(
        context,
        draft,
        ApproveExpense(
            version=service.dossier(context, draft).version, action="record_expense"
        ),
        "approve",
    )
    assert approval.outcome == "applied"
    if timing == "after_approval":
        attach_unchanged()
    correct_money(service, context, str(approval.activity_id))
    if timing == "after_correction":
        attach_unchanged()
    current = report(http)
    row = current["items"][0]
    assert (
        row["gross_amount"],
        row["recorded_amount"],
        row["report_date"],
        row["date_basis"],
    ) == ("25.00", "25.00", "2026-10-15", "activity_effective")
    filters = {
        "period": {"kind": "custom", "from_date": "2026-10-15", "to_date": "2026-10-15"},
        "currencies": ["DOP"],
        "amount_min": "25.00",
        "amount_max": "25.00",
    }
    matching = report(http, **filters)
    assert matching["matching_count"] == 1
    assert (
        report(
            http,
            period={"kind": "custom", "from_date": "2026-10-01", "to_date": "2026-10-01"},
        )["matching_count"]
        == 0
    )
    exported = http.post(
        "/business/reports/export",
        json={
            "report": {
                "schema_version": 2,
                "filters": filters,
                "columns": ["date", "gross_amount", "currency"],
            },
            "expected_fingerprint": matching["fingerprint"],
        },
    )
    assert exported.status_code == 200, exported.text
    with ZipFile(BytesIO(exported.content)) as archive:
        [exported_row] = list(
            csv.DictReader(StringIO(archive.read("records.csv").decode("utf-8-sig")))
        )
    assert exported_row["report_date"] == "2026-10-15"
    assert exported_row["gross_amount"] == "25.00"
    assert exported_row["currency"] == "DOP"


@pytest.mark.parametrize(
    "source_identity", ["original", "wrong_connection", "extra_suffix"]
)
def test_original_document_duplicate_and_new_support_preserve_document_basis(
    client, actions, documents, monkeypatch, source_identity
):
    http, _ = client
    service, context, _ = actions
    docs, _ = documents
    content = b"original financial document"
    original = docs._upload(
        user_id=context.owner_id,
        content=content,
        filename="original.txt",
        media_type="text/plain",
        consent=False,
        proposal=None,
        source_text=None,
        scope=context.scope,
        on_capture=None,
    )
    source_key = {
        "original": "original-financial-document",
        "wrong_connection": f"supporting:{uuid4()}",
        "extra_suffix": f"supporting:{original.connection_id}:original",
    }[source_identity]
    source_id = service.record_source(
        context,
        source_key,
        AttachmentSource(
            id=uuid4(),
            channel="web",
            received_at=datetime.now(timezone.utc),
            connection_id=UUID(original.connection_id),
            filename="original.txt",
            media_type="text/plain",
        ),
    )
    monkeypatch.setattr(shared, "source", lambda *_args, **_kwargs: source_id)
    draft = shared.ready(service, context)
    approval = service.approve(
        context, draft, ApproveExpense(version=1, action="record_expense"), "approve"
    )
    assert approval.outcome == "applied"
    correct_money(service, context, str(approval.activity_id))
    before = report(http)
    duplicate = append(
        http,
        draft,
        service.dossier(context, draft).version,
        key="duplicate-original",
        content=content,
    )
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["result"]["outcome"] == "duplicate"
    added = append(http, draft, service.dossier(context, draft).version)
    assert added.status_code == 200, added.text
    after = report(http)
    assert {key: after["items"][0][key] for key in FINANCIAL_FIELDS} == {
        key: before["items"][0][key] for key in FINANCIAL_FIELDS
    }
    assert after["totals"] == before["totals"]
    row = after["items"][0]
    assert (
        row["gross_amount"],
        row["recorded_amount"],
        row["report_date"],
        row["date_basis"],
    ) == ("850", "25.00", "2026-10-01", "document_issue")


@pytest.mark.parametrize("kind", ["note", "file"])
def test_viewer_current_version_annotation_is_denied(client, actions, users, kind):
    http, selected = client
    service, owner, _ = actions
    draft = shared.ready(service, owner)
    before = service.dossier(owner, draft)
    selected[0] = viewer_context(service, owner, users["other"])
    if kind == "note":
        response = http.put(
            f"/business/drafts/{draft}/current-note",
            json={"expected_version": before.version, "note": "viewer"},
            headers={"Idempotency-Key": "viewer-current"},
        )
    else:
        response = append(http, draft, before.version, key="viewer-current")
    assert response.status_code == 403, response.text
    assert service.dossier(owner, draft) == before
