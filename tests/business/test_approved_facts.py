"""A record's evidence is every document its approved facts name, and the
606 holds a record whose approved facts name none."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from argus.domain.business.approved_facts import evidence
from argus.domain.business.contracts.dgii import PurchaseDeclaration
from argus.domain.business.contracts.facts import (
    BusinessFacts,
    FiscalFacts,
    Known,
    Unknown,
)
from argus.domain.business.dgii_validation import FiscalRecord, record_issues

READ, TYPED = uuid4(), uuid4()


def _known(value, *sources):  # noqa: ANN001, ANN002, ANN202
    return Known(value=value, origin="extracted", source_ids=sources)


def test_evidence_is_every_document_the_facts_name_once() -> None:
    facts = BusinessFacts(
        kind=_known("expense", READ),
        amount=_known("1180.00", READ),
        currency=Known(value="DOP", origin="default", source_ids=()),
        occurred_on=_known(date(2026, 9, 5), READ),
        counterparty=Unknown(origin="extracted", source_ids=(TYPED,)),
        fiscal=FiscalFacts(ncf=_known("B0100000001", READ, TYPED)),
    )

    assert evidence(facts) == (str(READ), str(TYPED))


def test_a_record_whose_approved_facts_name_no_document_is_held() -> None:
    facts = BusinessFacts(currency=Known(value="DOP", origin="default", source_ids=()))
    declaration = PurchaseDeclaration.model_validate(
        {
            **{name: None for name in PurchaseDeclaration.model_fields},
            "form": "606",
            "actual_refund": False,
            "category_suggested": False,
        }
    )
    record = FiscalRecord(
        activity_id=str(uuid4()),
        activity_revision=1,
        draft_id=str(uuid4()),
        approved_revision=2,
        occurred_on=date(2026, 9, 5),
        amount="1180.00",
        currency="DOP",
        kind="expense",
        document_type="recibo",
        facts=facts,
        declaration=declaration,
        source_ids=evidence(facts),
    )

    assert evidence(facts) == ()
    assert {
        "code": "fiscal_approval_evidence_missing",
        "activity_id": record.activity_id,
        "field": "approved_revision",
    } in record_issues(record, {}, filer_identity=None)
