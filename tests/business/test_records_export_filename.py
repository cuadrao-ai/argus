"""The export preview names each file the way the export answers it, so the
web can offer that name before the file exists."""

from __future__ import annotations

import re
from datetime import date
from types import SimpleNamespace
from urllib.parse import unquote
from uuid import uuid4

import pytest
from argus.api import business_receipt_activity, business_reports
from argus.api.business import require_business_person, require_business_surface
from argus.api.business_drafts import require_drafts
from argus.domain.business import reporting_file
from faker import Faker
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.business.test_records_file import books, row, source

BUSINESS = "Café Unión"
#: Each name ends with the minute the records were read, in the Business calendar.
MINUTE = r"\d{4}-\d{2}-\d{2} \d{4}"


def one_stem(filenames: dict[str, str]) -> str:
    """The stem an offered Excel and CSV name share, without its read minute.
    Two reads can fall in different minutes, so callers compare this stem."""
    assert set(filenames) == {"xlsx", "csv"}
    stem = filenames["csv"].removesuffix(".csv")
    assert filenames == {"xlsx": f"{stem}.xlsx", "csv": f"{stem}.csv"}
    named = re.fullmatch(rf"(.+) - {MINUTE}", stem)
    assert named, stem
    return named[1]


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    fake = Faker("es")
    fake.seed_instance(2202)
    month = books()
    unbounded = source(
        row(fake, report_date=date(2026, 9, 7)),
        row(fake, report_date=date(2026, 4, 1), currency="USD"),
        *month.records,
        approved=month.approved,
    )
    monkeypatch.setattr(reporting_file, "read_export_source", lambda *args: unbounded)
    monkeypatch.setattr(reporting_file, "require_export", lambda *args: None)
    actor = SimpleNamespace(actor=SimpleNamespace(space_id=uuid4(), actor_id=uuid4()))
    app = FastAPI()
    app.include_router(business_reports.router)
    app.dependency_overrides[require_business_surface] = lambda: None
    monkeypatch.setattr(business_reports, "grant_reader", lambda *args: None)
    monkeypatch.setattr(business_receipt_activity, "bandeja_days", lambda context: [])
    app.dependency_overrides[require_drafts] = lambda: SimpleNamespace(
        service=SimpleNamespace(authority=None),
        for_space=lambda request, spaces: actor,
    )
    named = SimpleNamespace(name=BUSINESS)
    app.dependency_overrides[require_business_person] = lambda: SimpleNamespace(
        person_id=str(actor.actor.actor_id),
        spaces=SimpleNamespace(
            get=lambda space_id: named if space_id == str(actor.actor.space_id) else None
        ),
    )
    return TestClient(app)


def _disposition_name(header: str) -> str:
    return unquote(header.split("filename*=UTF-8''", 1)[1])


@pytest.mark.parametrize("language", ["es-419", "en"])
@pytest.mark.parametrize("period", [{"kind": "all"}, {"kind": "latest_month"}])
@pytest.mark.parametrize("fmt", ["xlsx", "csv"])
@pytest.mark.parametrize(
    ("mode", "currencies"), [("table", "current"), ("table", "all"), ("dgii", None)]
)
def test_the_preview_names_each_file_as_its_export_does(
    client: TestClient, language, period, fmt, mode, currencies
):
    report = {
        "schema_version": 2,
        "filters": {
            "period": period,
            "record_families": ["purchase"],
            "currencies": ["DOP"],
        },
    }
    headers = {"Accept-Language": language}
    preview = client.post(
        "/reports/export/preview", json={"report": report}, headers=headers
    )
    assert preview.status_code == 200, preview.text
    answer = preview.json()
    if mode == "dgii":
        offered = answer["dgii"]["filenames"][fmt]
        choice = {"mode": "dgii", "format": fmt}
    else:
        offered = answer["table"][currencies]["filenames"][fmt]
        choice = {
            "mode": "table",
            "format": fmt,
            "columns": ["counterparty"],
            "currencies": currencies,
        }

    exported = client.post(
        "/reports/export", json={"report": report, **choice}, headers=headers
    )

    assert exported.status_code == 200, exported.text
    assert offered == _disposition_name(exported.headers["Content-Disposition"])
    assert offered.startswith(f"{BUSINESS} - ")
    assert offered.endswith(f".{fmt}")
