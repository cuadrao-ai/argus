"""The duplicate rule on its own store: only the newer event is marked, a
retried check of the original never marks it back, a bank-match warning is
never overwritten, and the legacy delivery path marks from the observations
the same way."""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import Mock
from uuid import uuid4

from argus.domain.business.contracts.facts import BusinessFacts, BusinessResolution
from argus.domain.business.duplicates import flag_receipt_duplicates
from argus.domain.ingestion.connections import InMemoryConnectionRepository
from argus.domain.ingestion.documents.service import DocumentsService
from argus.domain.ingestion.documents.store import InMemoryDocumentStore
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.reconcile.model import ImportEvent, Observation
from argus.domain.ingestion.reconcile.service import ReconciliationService
from argus.domain.ingestion.reconcile.store import InMemoryImportStore
from argus.domain.owner_scope import BusinessSpace

NOW = datetime(2026, 10, 12, 18, 0, tzinfo=timezone.utc)
OWNER = str(uuid4())
SCOPE = BusinessSpace(str(uuid4()))


def _facts(merchant: str = "Colmado La Esquina", amount: str = "250.50") -> BusinessFacts:
    source = [str(uuid4())]
    known = lambda value: {  # noqa: E731
        "state": "known",
        "value": value,
        "origin": "extracted",
        "verified": False,
        "source_ids": source,
    }
    return BusinessFacts.model_validate(
        {
            "kind": known("expense"),
            "amount": known(amount),
            "currency": known("DOP"),
            "occurred_on": known("2026-10-11"),
            "counterparty": known(merchant),
        }
    )


def _event(
    facts: BusinessFacts | None, *, attention: str | None = None, state: str = "open"
) -> ImportEvent:
    resolution = (
        {}
        if facts is None
        else {"business": BusinessResolution(facts=facts).model_dump(mode="json")}
    )
    return ImportEvent(
        id=str(uuid4()),
        user_id=OWNER,
        state=state,  # type: ignore[arg-type]
        evidence="transaction",
        anchor_on=date(2026, 10, 11),
        attention=attention,  # type: ignore[arg-type]
        attention_detail=None,
        possible_duplicates=(),
        resolution=resolution,
        activity_id=None,
        accept_key=None,
        created_at=NOW,
        updated_at=NOW,
        version=1,
    )


def _observation(event_id: str, connection_id: str, **candidate) -> Observation:  # noqa: ANN003
    return Observation(
        id=str(uuid4()),
        user_id=OWNER,
        event_id=event_id,
        connection_id=connection_id,
        source="statement",
        external_id=str(uuid4()),
        fingerprint=str(uuid4()),
        candidate={
            "merchant": "Colmado La Esquina",
            "occurred_on": "2026-10-11",
            "amount": "250.50",
            "currency": "DOP",
            **candidate,
        },
        live=True,
        revisions=1,
        first_seen_at=NOW,
        updated_at=NOW,
    )


def test_only_the_newer_event_is_marked_and_the_original_never_is():
    store = InMemoryImportStore()
    first, second = _event(_facts()), _event(_facts())
    with store.transaction(OWNER, scope=SCOPE) as tx:
        tx.put_event(first)
        tx.put_event(second)
        assert flag_receipt_duplicates(tx, second.id) == (first.id,)
        marked = tx.event(second.id)
        assert (marked.attention, marked.attention_detail["basis"]) == (
            "possible_duplicate",
            "read_facts",
        )
        # A retried check of the original sees that the second already names it.
        assert flag_receipt_duplicates(tx, first.id) == ()
        assert tx.event(first.id).attention is None
        assert tx.event(first.id).possible_duplicates == ()
        # Another merchant with the same amount is not a repeat.
        other = _event(_facts(merchant="Otra tienda"))
        tx.put_event(other)
        assert flag_receipt_duplicates(tx, other.id) == ()


def test_a_bank_match_warning_is_never_overwritten_by_the_repeat_mark():
    store = InMemoryImportStore()
    first, second = _event(_facts()), _event(_facts(), attention="ambiguous_match")
    with store.transaction(OWNER, scope=SCOPE) as tx:
        tx.put_event(first)
        tx.put_event(second)
        assert flag_receipt_duplicates(tx, second.id) == (first.id,)
        marked = tx.event(second.id)
        assert marked.attention == "ambiguous_match"
        assert marked.possible_duplicates == (first.id,)
        assert marked.attention_detail["basis"] == "read_facts"


def test_unknown_facts_never_match():
    store = InMemoryImportStore()
    partial = BusinessFacts.model_validate(
        {
            **_facts().model_dump(mode="json"),
            "occurred_on": {
                "state": "unknown",
                "value": None,
                "origin": "extracted",
                "verified": False,
                "source_ids": [],
            },
        }
    )
    first, second = _event(partial), _event(partial)
    with store.transaction(OWNER, scope=SCOPE) as tx:
        tx.put_event(first)
        tx.put_event(second)
        assert flag_receipt_duplicates(tx, second.id) == ()


def test_the_legacy_delivery_marks_from_the_observations_the_same_way():
    imports = InMemoryImportStore()
    repo = InMemoryConnectionRepository()
    sink = ReconciliationService(imports, Mock(), lambda: NOW)
    hub = IngestionHub(repo, box=None, sink=sink, clock=lambda: NOW)
    service = DocumentsService(hub, InMemoryDocumentStore(repo), Mock())
    first, second = _event(None), _event(None)
    cid1, cid2 = str(uuid4()), str(uuid4())
    with imports.transaction(OWNER, scope=SCOPE) as tx:
        tx.put_event(first)
        tx.put_event(second)
        tx.put_observation(_observation(first.id, cid1))
        tx.put_observation(_observation(second.id, cid2))
    service._flag_business_duplicates(OWNER, cid2, SCOPE)
    with imports.transaction(OWNER, scope=SCOPE) as tx:
        assert tx.event(second.id).attention == "possible_duplicate"
        assert tx.event(second.id).possible_duplicates == (first.id,)
        assert tx.event(first.id).attention is None
    # Delivered again for the original: it already names nothing new.
    service._flag_business_duplicates(OWNER, cid1, SCOPE)
    with imports.transaction(OWNER, scope=SCOPE) as tx:
        assert tx.event(first.id).attention is None
