from datetime import datetime, timedelta, timezone
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from argus.domain.business.actions import BusinessActions
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.actions import AttachmentPreparationBinding
from argus.domain.business.contracts.authority import ActorProvenance
from argus.domain.ingestion.documents.models import DocumentDraft


@pytest.fixture
def checked():
    now = datetime.now(timezone.utc)
    data = b"synthetic receipt"
    digest = sha256(data).hexdigest()
    actor = ActorProvenance(
        actor_id=uuid4(),
        actor_kind="extractor",
        display_name="Test",
        grant_id=uuid4(),
        issuer_id=uuid4(),
        issuer_display_name="Test owner",
    )
    binding = AttachmentPreparationBinding(
        binding_id=uuid4(),
        space_id=uuid4(),
        owner_id=uuid4(),
        connection_id=uuid4(),
        source_sha256=digest,
        actor=actor,
        target=None,
        consent=True,
        captured_at=now,
    )
    draft = DocumentDraft(
        connection_id=str(binding.connection_id),
        filename="receipt.txt",
        media_type="text/plain",
        sha256=digest,
        size_bytes=len(data),
        consent=True,
        created_at=now,
        updated_at=now,
    )
    row = dict(
        draft=draft.model_dump(mode="json"),
        preparation_binding=binding.model_dump(mode="json"),
        source_path=None,
        source_bytes=data,
        source_sha256=None,
        lease_holder="holder",
        lease_until=now + timedelta(minutes=1),
        checked_at=now,
        preparation_job=None,
    )
    service = object.__new__(BusinessActions)
    service._attachment_row = Mock(return_value=row)
    tx = SimpleNamespace(authorization=SimpleNamespace(provenance=actor))
    return service, tx, binding, row


def test_original_bytes_authority_and_lease_pass(checked):
    service, tx, binding, row = checked
    actual, _ = service._checked_attachment(tx, binding, "holder", None)
    assert actual is row


@pytest.mark.parametrize("changed", ["actor_id", "grant_id", "issuer_id", "actor_kind"])
def test_changed_authority_refused(checked, changed):
    service, tx, binding, _ = checked
    tx.authorization.provenance = binding.actor.model_copy(
        update={changed: "member" if changed == "actor_kind" else uuid4()}
    )
    with pytest.raises(ActionError, match="business_preparation_authority_changed"):
        service._checked_attachment(tx, binding, "holder", None)


@pytest.mark.parametrize(
    "changed",
    ["bytes", "missing", "digest", "consent", "available", "lease", "holder", "attempt"],
)
def test_changed_evidence_or_attempt_refused(checked, changed):
    service, tx, binding, row = checked
    if changed == "bytes":
        row["source_bytes"] = b"other receipt"
    elif changed == "missing":
        row["source_bytes"] = None
    elif changed == "digest":
        row["source_sha256"] = "f" * 64
    elif changed == "consent":
        row["draft"]["consent"] = False
    elif changed == "available":
        row["draft"]["source_available"] = False
    elif changed == "lease":
        row["lease_until"] = row["checked_at"]
    elif changed == "holder":
        row["lease_holder"] = "other"
    else:
        row["preparation_job"] = {"attempt_id": "other"}
    with pytest.raises(ActionError):
        service._checked_attachment(tx, binding, "holder", None)


def test_receipt_projection_keeps_unknown_fiscal_and_verified_values(
    checked, monkeypatch
):
    from argus.domain.business.actions import mutations, sources
    from argus.domain.business.contracts.actions import ExistingDraft
    from argus.domain.business.contracts.facts import BusinessFacts
    from argus.domain.ingestion.contract import ImportCandidate, SourceRef
    from argus.domain.ingestion.documents.models import ExtractionBatch, ReceiptDetails

    _, tx, binding, row = checked
    source_id = uuid4()
    draft = DocumentDraft.model_validate(row["draft"])
    candidate = ImportCandidate(
        source=SourceRef(
            source="statement",
            connection_id=draft.connection_id,
            external_id=draft.sha256,
            observed_at=draft.created_at,
        ),
        evidence="transaction",
        direction="outflow",
        amount="250.50",
        currency="DOP",
        kind_hint="expense",
        merchant="Owner named shop",
    )
    batch = ExtractionBatch(
        complete=True,
        readable=True,
        candidates=(candidate,),
        receipt=ReceiptDetails(total="250.50", currency="DOP"),
    )
    event = mutations.new_candidate(str(binding.owner_id), draft.created_at)
    prior = BusinessFacts.model_validate(
        {
            "counterparty": {
                "state": "known",
                "value": "Owner named shop",
                "origin": "owner_stated",
                "source_ids": [str(uuid4())],
            }
        }
    )
    monkeypatch.setattr(sources, "record_source", lambda *args: source_id)
    monkeypatch.setattr(mutations, "event_at", lambda *args: event)
    monkeypatch.setattr(mutations, "facts_of", lambda *args: prior)
    save = Mock(return_value="saved")
    monkeypatch.setattr(mutations, "save_revision", save)
    assert (
        mutations.prepare_attachment(
            tx, ExistingDraft(draft_id=event.id, version=1), batch, draft, binding.actor
        )
        == "saved"
    )
    after = save.call_args.args[3]
    assert after.counterparty == prior.counterparty
    assert after.amount.verified is False
    assert after.amount.source_ids == (source_id,)
    assert after.fiscal.rnc.state == "unknown"
    assert after.fiscal.itbis.state == "unknown"


@pytest.mark.parametrize("field", ["amount", "fiscal"])
@pytest.mark.parametrize("origin", ["extracted", "matched", "owner_stated", "member_set"])
@pytest.mark.parametrize("incoming", ["absent", "equal", "conflict"])
def test_existing_receipt_facts_are_never_silently_replaced(
    checked, monkeypatch, field, origin, incoming
):
    from argus.domain.business.actions import mutations, sources
    from argus.domain.business.contracts.actions import ExistingDraft
    from argus.domain.business.contracts.facts import BusinessFacts
    from argus.domain.ingestion.contract import ImportCandidate, SourceRef
    from argus.domain.ingestion.documents.models import ExtractionBatch, ReceiptDetails

    _, tx, binding, row = checked
    draft = DocumentDraft.model_validate(row["draft"])
    prior_fact = {
        "state": "known",
        "value": "250.5",
        "origin": origin,
        "verified": False,
        "source_ids": [str(uuid4())],
    }
    prior = BusinessFacts.model_validate(
        {"amount": prior_fact} if field == "amount" else {"fiscal": {"itbis": prior_fact}}
    )
    value = None if incoming == "absent" else "250.50" if incoming == "equal" else "300"
    candidate = ImportCandidate(
        source=SourceRef(
            source="statement",
            connection_id=draft.connection_id,
            external_id=draft.sha256,
            observed_at=draft.created_at,
        ),
        evidence="transaction",
        direction="outflow",
        amount=value if field == "amount" else "1000",
        currency="DOP",
    )
    batch = ExtractionBatch(
        complete=True,
        readable=True,
        candidates=(candidate,),
        receipt=ReceiptDetails(itbis=value if field == "fiscal" else None),
    )
    event = mutations.new_candidate(str(binding.owner_id), draft.created_at)
    monkeypatch.setattr(sources, "record_source", lambda *args: uuid4())
    monkeypatch.setattr(mutations, "event_at", lambda *args: event)
    monkeypatch.setattr(mutations, "facts_of", lambda *args: prior)
    save = Mock()
    monkeypatch.setattr(mutations, "save_revision", save)
    target = ExistingDraft(draft_id=event.id, version=1)
    if incoming == "conflict":
        with pytest.raises(ActionError, match="receipt_requires_review"):
            mutations.prepare_attachment(tx, target, batch, draft, binding.actor)
        save.assert_not_called()
    else:
        mutations.prepare_attachment(tx, target, batch, draft, binding.actor)
        after = save.call_args.args[3]
        assert (after.amount if field == "amount" else after.fiscal.itbis) == (
            prior.amount if field == "amount" else prior.fiscal.itbis
        )
