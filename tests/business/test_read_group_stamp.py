"""Read completion fences the evidence before persisting the group's value."""

import subprocess
import sys
from contextlib import nullcontext
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest
from argus.domain.business.actions import listos
from argus.domain.business.actions import service as actions_module
from argus.domain.business.actions.mutations import new_candidate
from argus.domain.business.contracts.actions import Applied, ExistingDraft
from argus.domain.business.contracts.facts import BusinessResolution
from argus.domain.ingestion.documents.models import DocumentDraft

from tests.business.test_amount_due_review import _prepare, _row, _stored
from tests.business.test_bandeja_group import LISTO
from tests.test_business_attachment_preparation import checked  # noqa: F401


@pytest.mark.parametrize("module", ["bandeja_group", "contracts.deletion", "receipts"])
def test_group_contracts_import_without_api_startup(module):  # noqa: ANN001, ANN201
    result = subprocess.run(
        [sys.executable, "-c", f"import argus.domain.business.{module}"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.fixture
def completion(faker, monkeypatch):  # noqa: ANN001, ANN201
    now = datetime.now(timezone.utc)
    event = new_candidate(faker.uuid4(), now)
    saved = {event.id: event}
    imports = SimpleNamespace(
        event=lambda draft_id: saved[draft_id],
        put_event=lambda updated: saved.update({updated.id: updated}),
    )
    tx = SimpleNamespace(imports=imports)
    row = {
        "draft": {"version": 5, "status": "review_ready"},
        "lease_holder": faker.uuid4(),
        "lease_until": now + timedelta(minutes=1),
        "checked_at": now,
        "preparation_job": {"attempt_id": faker.uuid4()},
    }
    service = actions_module.BusinessActions(None, None)
    monkeypatch.setattr(service, "_attachment_context", lambda *args: (None, None))
    monkeypatch.setattr(service, "_attachment_row", lambda *args: row)
    monkeypatch.setattr(actions_module, "transaction", lambda *args: nullcontext(tx))
    standings = {event.id: replace(LISTO, draft_id=event.id, version=event.version)}
    monkeypatch.setattr(listos, "draft_standings", lambda *args: standings)
    arguments = {
        "user_id": event.user_id,
        "connection_id": faker.uuid4(),
        "scope": None,
        "holder": row["lease_holder"],
        "attempt_id": row["preparation_job"]["attempt_id"],
        "document_version": row["draft"]["version"],
        "prepared": Applied(outcome="applied", draft_id=event.id, version=event.version),
    }
    return SimpleNamespace(
        service=service, row=row, saved=saved, event=event,
        standings=standings, arguments=arguments,
    )


@pytest.mark.parametrize("repeated,expected", [(False, "listo"), (True, "attention")])
def test_completion_persists_the_group_after_duplicate_checks(completion, repeated, expected):  # noqa: ANN001, ANN201
    rig = completion
    rig.standings[rig.event.id] = replace(rig.standings[rig.event.id], repeated=repeated)

    rig.service.complete_attachment_read(**rig.arguments)

    assert rig.saved[rig.event.id].resolution["read_group"] == expected
    assert rig.saved[rig.event.id].version == rig.event.version


@pytest.mark.parametrize(
    "race", ["edit", "approved", "document_version", "reading", "holder", "expired", "attempt"]
)
def test_stale_completion_cannot_stamp_later_facts(completion, race):  # noqa: ANN001, ANN201
    rig = completion
    if race == "edit":
        rig.saved[rig.event.id] = replace(rig.event, version=rig.event.version + 1)
    elif race == "approved":
        rig.saved[rig.event.id] = replace(rig.event, state="accepted")
    elif race == "document_version":
        rig.row["draft"]["version"] += 1
    elif race == "reading":
        rig.row["draft"]["status"] = "preparing"
    elif race == "holder":
        rig.row["lease_holder"] = None
    elif race == "expired":
        rig.row["lease_until"] = rig.row["checked_at"]
    else:
        rig.row["preparation_job"]["attempt_id"] = str(UUID(int=0))

    rig.service.complete_attachment_read(**rig.arguments)

    assert "read_group" not in rig.saved[rig.event.id].resolution


def test_replayed_completion_keeps_the_original_group(completion):  # noqa: ANN001, ANN201
    rig = completion
    rig.service.complete_attachment_read(**rig.arguments)
    rig.standings[rig.event.id] = replace(rig.standings[rig.event.id], repeated=True)

    rig.service.complete_attachment_read(**rig.arguments)

    assert rig.saved[rig.event.id].resolution["read_group"] == "listo"


def test_old_completion_cannot_replace_a_newer_read_stamp(completion):  # noqa: ANN001, ANN201
    rig = completion
    rig.saved[rig.event.id] = replace(
        rig.event, version=rig.event.version + 1, resolution={"read_group": "attention"}
    )

    rig.service.complete_attachment_read(**rig.arguments)

    assert rig.saved[rig.event.id].resolution["read_group"] == "attention"


@pytest.mark.parametrize("revision", ["read", "human"])
def test_only_a_new_read_clears_the_previous_stamp(checked, monkeypatch, revision):  # noqa: ANN001, ANN201, F811
    from argus.domain.business.actions import mutations

    _, tx, binding, row = checked
    draft = DocumentDraft.model_validate(row["draft"])
    batch = _stored(
        draft, [_row("118.00", currency="DOP", evidence="transaction", row=1)],
        receipt=None,
    )
    _, _, event = _prepare(checked, monkeypatch, batch, draft)
    event = replace(event, resolution={**event.resolution, "read_group": "attention"})
    tx.imports.event.return_value = event
    if revision == "read":
        mutations.prepare_attachment(
            tx, ExistingDraft(draft_id=event.id, version=event.version),
            batch, draft, binding.actor,
        )
    else:
        facts = BusinessResolution.model_validate(event.resolution["business"]).facts
        mutations.save_revision(tx, event, facts, facts, (), binding.actor, None)

    saved = tx.imports.put_event.call_args.args[0]
    assert saved.resolution.get("read_group") == (None if revision == "read" else "attention")
