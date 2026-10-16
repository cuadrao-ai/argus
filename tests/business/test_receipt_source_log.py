"""The source route says in the message text what it served or why it did
not, so a hosted log (default format, keyword fields dropped) still shows it."""

from __future__ import annotations

from loguru import logger

from tests.business.test_business_api import Owner, alice  # noqa: F401


def _messages(records: list) -> list[str]:  # noqa: ANN001
    return [r["message"] for r in records if r["message"].startswith("receipt_source_")]


def test_the_source_route_names_the_outcome_in_the_message_text(alice: Owner) -> None:  # noqa: F811
    records: list = []
    sink = logger.add(lambda message: records.append(message.record), level="INFO")
    try:
        uploaded = alice.upload(consent=False, name="recibo.png")
        assert uploaded.status_code == 200, uploaded.text
        receipt_id = uploaded.json()["id"]
        served = alice.get(f"/receipts/{receipt_id}/source")
        assert served.status_code == 200
        missing = alice.get("/receipts/00000000-0000-4000-8000-000000000000/source")
        assert missing.status_code == 404
    finally:
        logger.remove(sink)
    assert _messages(records) == [
        f"receipt_source_served receipt_id={receipt_id} media_type=image/jpeg"
        f" size_bytes={len(served.content)}",
        "receipt_source_failed receipt_id=00000000-0000-4000-8000-000000000000"
        " code=receipt_not_found status=404",
    ]
