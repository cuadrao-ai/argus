"""The chat refusal advertises the actual configured quota's UTC reset."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from argus.api.chat import guest_compute_ceiling, registered_compute_ceiling
from argus.domain.usage_limits import align_usage_period

from tests.test_allowance_accounting import client, mock_gateway
from tests.test_guest_compute_ceiling import GUEST_HEADERS, TURN, _guest
from tests.test_registered_compute_ceiling import REGISTERED_HEADERS, _registered

__all__ = ["mock_gateway"]


@pytest.mark.parametrize("account", ["guest", "registered"])
@pytest.mark.parametrize("limit", [2, 17])
@pytest.mark.parametrize("clock", ["00:00:00", "18:17:32.700000", "23:59:59.700000"])
def test_chat_reset_header_matches_quota_window(
    mock_gateway, monkeypatch: pytest.MonkeyPatch, account: str, limit: int, clock: str
) -> None:
    received_at = datetime.fromisoformat(f"2026-09-26T{clock}+00:00")
    owner = guest_compute_ceiling if account == "guest" else registered_compute_ceiling
    monkeypatch.setattr(owner, "datetime", SimpleNamespace(now=lambda _tz: received_at))
    if account == "guest":
        monkeypatch.setenv("CUADRAO_GUEST_SESSION_DAILY_TURN_CEILING", str(limit))
        claim = _guest(mock_gateway, monkeypatch, turns_today=0, session_used=limit)
        headers = GUEST_HEADERS
    else:
        monkeypatch.setenv("CUADRAO_REGISTERED_DAILY_TURN_CEILING", str(limit))
        claim = _registered(mock_gateway, monkeypatch, turns_today=limit)
        headers = REGISTERED_HEADERS

    response = client.post("/api/v1/chat/stream", json=TURN, headers=headers)

    assert response.status_code == 429
    assert response.json()["code"] == "too_many_requests"
    _, quota_end = align_usage_period(received_at, "day")
    delay = int(response.headers["Retry-After"])
    assert delay == max(int((quota_end - received_at).total_seconds()), 1)
    # The web rounds the response-derived instant to the displayed minute.
    advertised = received_at + timedelta(seconds=delay)
    rounded = datetime.fromtimestamp(round(advertised.timestamp() / 60) * 60, timezone.utc)
    assert rounded == quota_end
    assert claim.claims == 0
    mock_gateway.create_message.assert_not_called()
