import json
from dataclasses import replace
from datetime import date
from types import SimpleNamespace

from argus.domain.business.contracts.facts import BusinessFacts
from argus.domain.business.reporting import ReportRow
from argus.domain.business.reporting_projection import DraftState, project
from argus.domain.business.reporting_store import RecordedRecord
from faker import Faker

from tests.dgii.test_606_review_and_rnc import purchase

fake = Faker("es_MX")


def recorded(note, approved=None):
    approved = replace(approved or purchase(), activity_id="activity")
    return RecordedRecord(
        row=ReportRow(
            activity_id="activity",
            revision=1,
            occurred_on=date(2026, 10, 1),
            kind="expense",
            currency="DOP",
            amount_minor=10000,
            effect="known",
            dependency_fingerprints=(),
        ),
        activity_json=json.dumps(
            {"kind": "expense", "amount": "100.00", "note": note, "source_id": None}
        ),
        approved=approved,
        settlement=None,
        sources=(),
    )


def draft(*, resolution):
    return DraftState(
        event=SimpleNamespace(
            id="draft",
            version=1,
            state="accepted",
            accept_key="key",
            activity_id="activity",
            resolution={"business": {}, **resolution},
        ),
        facts=purchase().facts,
        fiscal=purchase(),
        blockers=(),
        technical_state=None,
        sources=(),
        dependency_fingerprint="dependency",
    )


def row(source, state):
    return project(source, state, {}, None)


def test_an_approved_record_keeps_the_merchant_out_of_notas():
    merchant = fake.company()
    state = draft(resolution={"note": merchant})
    assert row(recorded(merchant), state).note is None


def test_a_record_shows_the_note_a_person_saved():
    merchant, written = fake.company(), fake.sentence()
    state = draft(resolution={"note": merchant, "current_note": written})
    assert row(recorded(merchant), state).note == written


def test_an_activity_with_no_draft_shows_its_merchant_as_the_counterparty():
    merchant = fake.company()
    bare = replace(purchase(), facts=BusinessFacts())
    result = row(recorded(merchant, bare), None)
    assert (result.counterparty, result.note) == (merchant, None)
