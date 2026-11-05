"""Over HTTP on the real app, Auth and Postgres: a forwarded email's original
is the email, not a receipt, so Business search leaves it out before a page
is cut and a page holds ``limit`` attachments."""

from __future__ import annotations

import asyncio
import json
from email.message import EmailMessage
from uuid import uuid4

from tests.business.test_business_api import RECEIPT
from tests.business.test_business_email_api import WEBHOOK, signed
from tests.test_business_reading_setting_postgres import (  # noqa: F401
    API,
    _email_runtime,
    pytestmark,
    web,  # noqa: ANN001, F811
)


def _message(n: int) -> bytes:
    message = EmailMessage()
    message["From"] = "proveedor@example.test"
    message["Subject"] = f"Factura {n}"
    message.set_content("Adjunto la factura.")
    message.add_attachment(
        RECEIPT + bytes([n]),
        maintype="image",
        subtype="png",
        filename=f"forwarded-{n}.png",
    )
    return message.as_bytes()


def test_a_page_holds_limit_attachments_and_never_an_email_original(
    web,  # noqa: ANN001, F811
    monkeypatch,  # noqa: ANN001
) -> None:
    for n in (1, 2):
        runtime, route = _email_runtime(web, monkeypatch, _message(n))
        body = json.dumps(
            {
                "type": "email.received",
                "data": {"email_id": str(uuid4()), "to": [route.recipient]},
            }
        ).encode()
        received = web.client.post(WEBHOOK, content=body, headers=signed(body))
        assert received.status_code == 202, received.text
        assert asyncio.run(runtime.next())

    receipts = web.client.get(
        f"{API}/business/receipts", params={"view": "all"}, headers=web.alice.headers
    ).json()["items"]
    attachments = {r["id"] for r in receipts if not r["email_original"]}
    assert len(attachments) == 2 and len(receipts) == 4

    page = web.client.get(
        f"{API}/business/search",
        params={"q": "forwarded", "limit": 2},
        headers=web.alice.headers,
    )
    assert page.status_code == 200, page.text
    assert {r["id"] for r in page.json()["receipts"]} == attachments
    assert page.json()["next_cursors"]["receipts"] is None
