"""An approval response names the activity that its own command recorded."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest
from argus.domain.business.actions import approval
from argus.domain.ingestion.reconcile.service import ReconciliationService

from tests.test_business_approve_unpaid_postgres import (
    KINDS,
    SPAN,
    _approve,
    _counts,
    _get,
    _reviewed,
    world,  # noqa: F401
)
from tests.test_business_scope_switch_routes_postgres import API
from tests.test_business_scope_switch_routes_postgres import (
    pytestmark as _local_supabase,
)

pytestmark = _local_supabase


@pytest.fixture(autouse=True)
def _typed_notes(typed_notes_on: None) -> None:
    """These flows start a draft by typing a note: typed notes on."""


@pytest.fixture(autouse=True)
def _settlement(settlement_on: None) -> None:
    """Keep the unpaid approval fixture's settlement setting."""


@pytest.mark.parametrize("kind", KINDS)
def test_same_key_loser_reports_unsettled_until_winner_records(
    world,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:  # noqa: ANN001
    draft, dossier = _reviewed(world, kind, "B0100000071")
    version, key = dossier["version"], str(uuid4())
    loser_at_review, release_loser = Event(), Event()
    winner_at_write, release_winner = Event(), Event()
    reviewed_request = approval.reviewed_request
    write = ReconciliationService._write

    def paused_review(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        if not loser_at_review.is_set():
            loser_at_review.set()
            assert release_loser.wait(timeout=15), "losing approval was not released"
        return reviewed_request(*args, **kwargs)

    def paused_write(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        winner_at_write.set()
        assert release_winner.wait(timeout=15), "winning approval was not released"
        return write(*args, **kwargs)

    monkeypatch.setattr(approval, "reviewed_request", paused_review)
    monkeypatch.setattr(ReconciliationService, "_write", paused_write)
    with ThreadPoolExecutor(max_workers=2) as pool:
        loser = pool.submit(_approve, world, draft, version, kind, key)
        try:
            assert loser_at_review.wait(timeout=15), "loser did not reach review"
            winner = pool.submit(_approve, world, draft, version, kind, key)
            assert winner_at_write.wait(timeout=15), "winner did not commit its claim"
            release_loser.set()
            losing_answer = loser.result(timeout=15)
            assert losing_answer.status_code == 409, (key, losing_answer.text)
            assert losing_answer.json()["code"] == "business_recording_unsettled"
            assert losing_answer.headers["cache-control"] == "no-store"
            assert _counts(world) == (0, 0, 0)
        finally:
            release_loser.set()
            release_winner.set()
        winning_answer = winner.result(timeout=15)
    assert winning_answer.status_code == 200, winning_answer.text
    activity = winning_answer.json()["approval_result"]["activity_id"]
    replay = _approve(world, draft, version, kind, key)
    assert replay.status_code == 200, replay.text
    assert replay.json()["approval_result"]["activity_id"] == activity
    assert _counts(world) == (1, 0, 0)
    assert len(_get(world, "/business/expenses", kind=kind, **SPAN).json()["items"]) == 1


@pytest.mark.parametrize("kind", KINDS)
def test_historical_approval_replay_follows_the_original_record_through_delete_and_restore(
    world,  # noqa: F811
    kind: str,
) -> None:  # noqa: ANN001
    draft, dossier = _reviewed(world, kind, "B0100000072")
    version, key = dossier["version"], str(uuid4())
    first = _approve(world, draft, version, kind, key)
    assert first.status_code == 200, first.text
    activity = first.json()["approval_result"]["activity_id"]

    def change(action: str):
        return world.client.post(
            f"{API}/business/drafts/{draft}/{action}",
            headers={**world.alice.headers, "Idempotency-Key": str(uuid4())},
        )

    deleted = change("delete")
    assert deleted.status_code == 200, deleted.text
    path = f"/business/drafts/{draft}/dossier"
    current = _get(world, path).json()
    assert current["review_state"] == "dismissed"
    assert current["approval_result"] is None

    before = _counts(world)
    replay = _approve(world, draft, version, kind, key)
    assert replay.status_code == 409, (key, replay.text)
    assert replay.json()["code"] == "stale_version"
    assert replay.headers["cache-control"] == "no-store"
    assert _counts(world) == before
    assert _get(world, path).json() == current

    restored = change("restore")
    assert restored.status_code == 200, restored.text
    replay = _approve(world, draft, version, kind, key)
    assert replay.status_code == 200, replay.text
    assert replay.json()["approval_result"]["activity_id"] == activity
    assert _counts(world) == before == (1, 0, 0)
