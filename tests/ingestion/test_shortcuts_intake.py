"""Shortcuts intake under failure: bad amounts, refused evidence, abuse limits."""

import threading
from datetime import datetime, timedelta, timezone

import pytest
from argus.api import shortcuts as shortcuts_api
from argus.api.ingestion import ingestion_hub
from argus.api.shortcuts import shortcuts_connector
from argus.domain.ingestion.contract import ImportCandidate
from argus.domain.ingestion.shortcuts import connector as connector_module
from argus.domain.ingestion.shortcuts.connector import DeviceLimitReached
from argus.domain.ingestion.sink import SubmitResult
from argus.domain.owner_scope import PERSONAL

from tests.ingestion.conftest import ALICE, bearer
from tests.ingestion.shortcuts_support import (
    BATCH,
    EVENTS,
    RecordingSink,
    enroll,
    tap,
)


@pytest.fixture
def sink(client) -> RecordingSink:  # noqa: ANN001
    recording = RecordingSink()
    ingestion_hub().sink = recording
    return recording


def _reject_event(bad_id: str, monkeypatch) -> None:  # noqa: ANN001
    real = connector_module.to_candidate

    def picky(event, *, connection_id):  # noqa: ANN001, ANN202
        if event.event_id == bad_id:
            return ImportCandidate.model_validate({"evidence": "nope"})
        return real(event, connection_id=connection_id)

    monkeypatch.setattr(connector_module, "to_candidate", picky)


def test_huge_amount_is_saved_unresolved_never_a_server_error(client, sink):
    token = enroll(client)["device_token"]
    response = client.post(
        EVENTS, json=tap(amount="RD$" + "9" * 40), headers=bearer(token)
    )
    assert response.status_code == 200
    [candidate] = sink.evidence.values()
    assert candidate.amount is None and "amount" in candidate.uncertain


def test_contract_refusal_rejects_only_that_event(client, sink, monkeypatch):
    token = enroll(client)["device_token"]
    _reject_event("bad", monkeypatch)
    events = [tap(event_id="bad"), tap(event_id="good")]
    body = client.post(BATCH, json={"events": events}, headers=bearer(token)).json()
    assert [r["outcome"] for r in body["receipts"]] == ["rejected", "recorded"]
    assert len(sink.evidence) == 1
    single = client.post(EVENTS, json=tap(event_id="bad"), headers=bearer(token))
    assert single.status_code == 422
    assert single.json()["code"] == "shortcuts_event_invalid"


def test_evidence_the_sink_ignores_is_never_reported_saved(client, sink):
    token = enroll(client)["device_token"]
    sink.submit = lambda **_kwargs: SubmitResult(0, 0, 0, ignored=1)
    single = client.post(EVENTS, json=tap(), headers=bearer(token))
    assert single.status_code == 503
    assert single.json()["code"] == "shortcuts_events_not_saved"
    assert "receipt_id" not in single.json()
    batch = client.post(BATCH, json={"events": [tap()]}, headers=bearer(token)).json()
    assert [r["outcome"] for r in batch["receipts"]] == ["not_saved"]


def test_connection_ended_mid_flight_answers_unauthorized(client, sink, identities):
    hub = ingestion_hub()
    for url, body in ((BATCH, {"events": [tap()]}), (EVENTS, tap())):
        enrolled = enroll(client, name=url[-5:])
        token = enrolled["device_token"]

        def ended(_id=enrolled["connection"]["id"], **_kwargs):  # noqa: ANN001, ANN003, ANN202
            hub.connections.disconnect(
                user_id=identities[ALICE]["id"],
                connection_id=_id,
                now=datetime.now(timezone.utc),
            )
            return SubmitResult(0, 0, 0, ignored=1)

        sink.submit = ended
        response = client.post(url, json=body, headers=bearer(token))
        assert response.status_code == 401
        assert response.json()["code"] == "shortcuts_device_unauthorized"


def test_partial_batch_failure_is_retryable_and_never_claims_nothing_saved(client, sink):
    token = enroll(client)["device_token"]
    real_submit = sink.submit
    calls = {"n": 0}

    def flaky(**kwargs):  # noqa: ANN003, ANN202
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("storage down")
        return real_submit(**kwargs)

    sink.submit = flaky
    events = [tap(event_id="f1"), tap(event_id="f2")]
    failed = client.post(BATCH, json={"events": events}, headers=bearer(token))
    assert failed.status_code == 503
    body = failed.json()
    assert body["code"] == "shortcuts_events_not_saved"
    assert body["context"] == {"retryable": True}
    assert "nothing" not in body["detail"].lower()
    retried = client.post(BATCH, json={"events": events}, headers=bearer(token)).json()
    assert [r["outcome"] for r in retried["receipts"]] == ["unchanged", "recorded"]
    assert len(sink.evidence) == 2


def test_daily_event_budget_bounds_batches(client, sink, monkeypatch):
    monkeypatch.setattr(shortcuts_api, "EVENTS_PER_DAY", 3)
    token = enroll(client)["device_token"]
    first = [tap(event_id="a"), tap(event_id="b")]
    ok = client.post(BATCH, json={"events": first}, headers=bearer(token))
    assert ok.status_code == 200
    second = [tap(event_id="c"), tap(event_id="d")]
    limited = client.post(BATCH, json={"events": second}, headers=bearer(token))
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) >= 1
    assert len(sink.evidence) == 2
    one_more = client.post(EVENTS, json=tap(event_id="c"), headers=bearer(token))
    assert one_more.status_code == 200
    assert (
        client.post(EVENTS, json=tap(event_id="e"), headers=bearer(token)).status_code
        == 429
    )


def test_failed_tokens_are_limited_per_address_before_authentication(
    client, sink, monkeypatch
):
    monkeypatch.setattr(shortcuts_api, "FAILED_AUTH_PER_ADDRESS", (3, 600))
    token = enroll(client)["device_token"]
    for _ in range(3):
        bad = client.post(EVENTS, json=tap(), headers=bearer("sct1.junk"))
        assert bad.status_code == 401
    blocked = client.post(EVENTS, json=tap(), headers=bearer("sct1.junk"))
    assert blocked.status_code == 429
    # The check runs before authentication, so the address is blocked outright.
    assert client.post(EVENTS, json=tap(), headers=bearer(token)).status_code == 429
    assert sink.evidence == {}


def test_each_request_window_has_its_own_limiter():
    limiters = [limiter for _limit, _window, limiter in shortcuts_api.REQUEST_LIMITS]
    assert len({id(limiter) for limiter in limiters}) == len(limiters) == 2
    windows = sorted(window for _limit, window, _limiter in shortcuts_api.REQUEST_LIMITS)
    assert windows == [60, 24 * 60 * 60]


def test_freshness_moves_only_when_an_event_was_accepted(client, sink, identities):
    token = enroll(client)["device_token"]
    stale = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    body = client.post(
        BATCH, json={"events": [tap(captured_at=stale)]}, headers=bearer(token)
    ).json()
    assert [r["outcome"] for r in body["receipts"]] == ["out_of_window"]
    [connection] = ingestion_hub().list(user_id=identities[ALICE]["id"], scope=PERSONAL)
    assert connection.last_success_at is None


def test_concurrent_enrollment_cannot_exceed_the_device_limit(client, identities):
    connector = shortcuts_connector()
    user_id = identities[ALICE]["id"]
    outcomes: list[str] = []
    gate = threading.Barrier(12)

    def attempt(index: int) -> None:
        gate.wait()
        try:
            connector.enroll(user_id=user_id, device_name=f"phone {index}")
            outcomes.append("ok")
        except DeviceLimitReached:
            outcomes.append("limit")

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert outcomes.count("ok") == 5 and outcomes.count("limit") == 7
    live = [
        r
        for r in ingestion_hub().list(user_id=user_id, scope=PERSONAL)
        if r.status == "active"
    ]
    assert len(live) == 5
