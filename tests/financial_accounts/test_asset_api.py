from datetime import datetime, timezone
from uuid import uuid4

from .conftest import ALICE, BOB, GUEST


def test_asset_api_journey_and_access(client, alice):
    created = alice.create(
        {
            "type": "property",
            "currency": "DOP",
            "amount": "8000000",
            "ownership_share_bps": 5000,
        },
        key=str(uuid4()),
    ).json()
    path = "/api/v1/financial-accounts/" + created["id"]
    headers = {"Authorization": f"Bearer {ALICE}"}
    body = {
        "expected_version": 1,
        "amount": "9000000",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "time_zone": "America/Santo_Domingo",
        "estimate_basis": "My estimate",
    }
    preview = client.post(path + "/asset-estimates/preview", json=body, headers=headers)
    assert preview.status_code == 200, preview.text
    assert preview.json()["account"]["asset"]["personal_position_minor"] == 450000000
    body["preview_token"] = preview.json()["preview_token"]
    headers["Idempotency-Key"] = str(uuid4())
    saved = client.post(path + "/asset-estimates", json=body, headers=headers)
    assert saved.status_code == 200, saved.text
    assert client.post(path + "/asset-estimates", json=body, headers=headers).json()[
        "replayed"
    ]
    details = {
        "expected_version": 2,
        "ownership_share_bps": 7500,
        "related_debt_account_id": None,
    }
    result = client.put(path + "/asset-details", json=details, headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["account"]["asset"]["personal_position_minor"] == 675000000
    assert (
        client.put(
            path + "/asset-details",
            json=details,
            headers={**headers, "Authorization": f"Bearer {BOB}"},
        ).status_code
        == 404
    )
    assert (
        client.put(
            path + "/asset-details",
            json=details,
            headers={**headers, "Authorization": f"Bearer {GUEST}"},
        ).status_code
        == 403
    )
    assert (
        client.put(
            path + "/asset-details",
            json=details,
            headers={"Authorization": f"Bearer {ALICE}"},
        ).status_code
        == 400
    )
