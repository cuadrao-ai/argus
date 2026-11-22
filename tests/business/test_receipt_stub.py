"""The shared read stays acceptable as the upload clock crosses years."""

from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from argus.domain.business.accepted_dates import reader_date_reason
from argus.domain.business.bandeja_group import upload_year, year_to_check
from argus.domain.business.contracts.facts import BusinessFacts, Known
from argus.domain.clock import new_york_now
from argus.domain.ingestion.email_intake.budget import business_day

from tests.business.receipt_stub import ReceiptStub


@pytest.mark.parametrize(
    "instant",
    [
        "2027-01-02T12:00:00+00:00",
        "2027-01-01T03:59:59+00:00",
        "2027-01-01T04:00:00+00:00",
        "2028-02-29T12:00:00+00:00",
        "2037-01-02T12:00:00+00:00",
    ],
)
def test_shared_read_uses_the_upload_business_day(instant, freeze_new_york_clock):  # noqa: ANN001
    freeze_new_york_clock(datetime.fromisoformat(instant))
    uploaded_at = new_york_now().astimezone(timezone.utc)
    stub = ReceiptStub()
    issued = date.fromisoformat(stub.rows[0]["occurred_on"])
    facts = BusinessFacts(
        occurred_on=Known(
            value=issued,
            origin="extracted",
            source_ids=(uuid4(),),
        )
    )
    assert not year_to_check(facts, upload_year(uploaded_at))
    assert reader_date_reason(issued) is None
    assert issued == business_day(uploaded_at)
    assert stub.details["occurred_on"] == issued.isoformat()
