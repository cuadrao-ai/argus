"""Bandeja learns from the server that a receipt waits for the read budget."""

from __future__ import annotations

import io

import pytest
from argus.api.documents import _minute, documents_service
from argus.domain.business.read_budget import InMemoryReadBudget, ReadBudgetSettings
from faker import Faker
from PIL import Image

from tests.business.test_business_api import Owner, alice  # noqa: F401

fake = Faker("es_MX")


def receipt_png() -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", (32, 32), fake.hex_color()).save(stream, format="PNG")
    return stream.getvalue()


@pytest.fixture
def one_read_a_day(biz) -> None:  # noqa: ANN001
    _minute.reset()
    documents_service().read_budget = InMemoryReadBudget(ReadBudgetSettings(per_day=1))


def test_the_receipt_over_budget_shows_its_reason_and_stays_preparable(
    alice: Owner,  # noqa: F811
    one_read_a_day: None,
):
    first = alice.upload(receipt_png(), name=fake.file_name(extension="png"))
    assert first.status_code == 200, first.text
    second = alice.upload(receipt_png(), name=fake.file_name(extension="png"))
    assert second.status_code == 200, second.text
    read = alice.detail(first.json()["id"])
    assert read["status"] == "review_ready"
    waiting = alice.detail(second.json()["id"])
    assert (waiting["status"], waiting["attention"], waiting["error_code"]) == (
        "needs_attention",
        "read_budget_day",
        "business_read_budget_day",
    )
    assert waiting["preparable"] is True
    assert waiting["read_pending"] is False
    listed = {item["id"]: item for item in alice.get("/receipts").json()["items"]}
    assert listed[second.json()["id"]]["attention"] == "read_budget_day"
