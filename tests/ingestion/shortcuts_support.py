"""Shared helpers for the Shortcuts API tests: a recording sink and requests."""

from collections.abc import Sequence
from datetime import datetime, timezone

from argus.domain.ingestion.contract import ImportCandidate
from argus.domain.ingestion.sink import SubmitResult
from argus.domain.owner_scope import PERSONAL, OwnerScope

from tests.ingestion.conftest import ALICE, bearer

DEVICES = "/api/v1/financial-connections/shortcuts/devices"
EVENTS = "/api/v1/ingestion/shortcuts/events"
BATCH = "/api/v1/ingestion/shortcuts/events/batch"


class RecordingSink:
    """Idempotent by key like the real sink: same fingerprint is unchanged."""

    def __init__(self) -> None:
        self.evidence: dict[tuple[str, str, str], ImportCandidate] = {}
        self.calls = 0

    def submit(
        self,
        *,
        user_id: str,
        connection_id: str,
        candidates: Sequence[ImportCandidate],
        scope: OwnerScope,
    ) -> SubmitResult:
        assert scope == PERSONAL
        self.calls += 1
        recorded = unchanged = 0
        for candidate in candidates:
            assert candidate.source.connection_id == connection_id
            known = self.evidence.get(candidate.key)
            if known is not None and known.fingerprint() == candidate.fingerprint():
                unchanged += 1
                continue
            self.evidence[candidate.key] = candidate
            recorded += 1
        return SubmitResult(recorded=recorded, unchanged=unchanged, withdrawn=0)

    def forget_connection(
        self, *, user_id: str, connection_id: str, scope: OwnerScope
    ) -> int:
        assert scope == PERSONAL
        doomed = [k for k in self.evidence if k[1] == connection_id]
        for key in doomed:
            del self.evidence[key]
        return len(doomed)


def enroll(client, token: str = ALICE, name: str = "iPhone de Ana"):  # noqa: ANN001
    response = client.post(DEVICES, json={"device_name": name}, headers=bearer(token))
    assert response.status_code == 201, response.text
    return response.json()


def tap(**overrides) -> dict:
    body = {
        "event_id": "evt-1",
        "kind": "transaction",
        "source_app": "wallet",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "amount": "RD$1,250.00",
        "merchant": "Supermercado Nacional",
        "card": "Visa Popular",
    }
    body.update(overrides)
    return {k: v for k, v in body.items() if v is not None}
