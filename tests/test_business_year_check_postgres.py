"""The year check through the API: a read whose year is not the upload year
stays out of Listos, the dossier says so, and a person's date ends it."""

from __future__ import annotations

from datetime import date, datetime, timezone

from argus.domain.business.ledger import business_day

from tests import test_business_listos_postgres as listos
from tests.test_business_listos_postgres import (
    _approve_many,
    _counts,
    _get,
    _group,
    _named,
    _read,
    _results,
    _review,
)

pytestmark = listos.pytestmark
people = listos.people
rig = listos.rig


def _dossier(rig, item: dict) -> dict:  # noqa: ANN001
    return _get(rig, f"/business/drafts/{item['draft_id']}/dossier")


def test_a_read_year_that_is_not_the_upload_year_waits_for_a_person(rig) -> None:  # noqa: ANN001
    uploaded = business_day(datetime.now(timezone.utc)).year
    receipt = _read(rig, {"occurred_on": date(uploaded - 2, 11, 4).isoformat()})

    assert _group(rig, receipt) == ("attention", "check_details")
    assert _counts(rig) == (0, 1)
    item = _named(rig, receipt)
    dossier = _dossier(rig, item)
    assert (dossier["upload_year"], dossier["year_to_check"]) == (uploaded, True)
    assert dossier["approval_available"] is True
    assert _results(_approve_many(rig, [item])) == [("refused", "not_listo")]

    stated = {"state": "known", "value": date(uploaded - 2, 11, 5).isoformat()}
    edited = _review(rig, item, {"facts": {"occurred_on": stated}})

    assert edited["facts"]["occurred_on"]["origin"] != "extracted"
    assert (edited["upload_year"], edited["year_to_check"]) == (uploaded, False)
    assert _group(rig, receipt) == ("listo", None)


def test_a_read_in_the_upload_year_has_no_year_to_check(rig) -> None:  # noqa: ANN001
    today = business_day(datetime.now(timezone.utc))
    receipt = _read(rig, {"occurred_on": today.isoformat()})

    dossier = _dossier(rig, _named(rig, receipt))
    assert (dossier["upload_year"], dossier["year_to_check"]) == (today.year, False)
    assert _group(rig, receipt) == ("listo", None)
