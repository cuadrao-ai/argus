"""End-to-end API behaviour for public evidence receipts.

Covers the flag gate, the rate limit, revocation following deletion, and the
construction guard on the public route module.
"""

from __future__ import annotations

import ast
import base64
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
from argus.api import state as api_state
from argus.api.main import app
from argus.api.routers import evidence_receipts
from argus.domain.public_excerpts import PUBLIC_EXCERPT_PATH_PREFIX
from fastapi.testclient import TestClient

from tests.public_excerpt_factories import (
    ARTIFACT_ID,
    CONVERSATION_ID,
    build_artifact,
    build_conversation,
    build_run,
    seed_result_messages,
    stable_uuid,
)

CREATE_PATH = f"/api/v1/evidence-artifacts/{ARTIFACT_ID}/public-excerpt"
LIST_PATH = "/api/v1/public-excerpts"


@pytest.fixture(autouse=True)
def _memory_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_state, "supabase_gateway", None)
    evidence_receipts.reset_receipt_create_limiter_for_tests()


@pytest.fixture
def sharing_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUADRAO_EVIDENCE_RECEIPT_SHARING_ENABLED", "true")


@pytest.fixture
def sharing_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CUADRAO_EVIDENCE_RECEIPT_SHARING_ENABLED", raising=False)


def _client() -> TestClient:
    client = TestClient(app)
    api_state.store.reset()
    return client


def _seed(client: TestClient) -> str:
    user_id = api_state.store.get_or_create_dev_user().id
    conversation = build_conversation()
    artifact = build_artifact()
    run = build_run()
    api_state.store.conversations[conversation.id] = conversation
    api_state.store.conversation_owners[conversation.id] = user_id
    api_state.store.evidence_artifacts[artifact.id] = artifact
    api_state.store.evidence_artifact_owners[artifact.id] = user_id
    api_state.store.backtest_runs[run.id] = run
    api_state.store.backtest_run_owners[run.id] = user_id
    seed_result_messages(api_state.store, run)
    return user_id


def _create(client: TestClient, note: str | None = None) -> dict[str, Any]:
    response = client.post(CREATE_PATH, json={"owner_note": note})
    assert response.status_code == 200, response.text
    return response.json()["receipt"]


_FLAG_OFF_PROBES = (
    ("POST", CREATE_PATH, {}),
    ("GET", LIST_PATH, None),
    ("GET", f"{LIST_PATH}?limit=5", None),
    ("DELETE", f"{LIST_PATH}/anything", None),
    ("GET", "/api/v1/public/receipts/abcdefghijklmnopqrstuvwx", None),
    ("POST", "/api/v1/public/receipt-funnel", {"stage": "try_argus"}),
    ("PATCH", LIST_PATH, None),
)


# ── The default-off flag ──────────────────────────────────────────────────────


def test_every_receipt_route_is_absent_while_the_flag_is_off(
    sharing_off: None,
) -> None:
    client = _client()
    _seed(client)
    assert client.post(CREATE_PATH, json={}).status_code == 404
    assert client.get(LIST_PATH).status_code == 404
    assert client.delete(f"{LIST_PATH}/anything").status_code == 404
    assert client.get("/api/v1/public/receipts/abcdefghijklmnopqrstuvwx").status_code == (
        404
    )
    assert (
        client.post(
            "/api/v1/public/receipt-funnel", json={"stage": "try_argus"}
        ).status_code
        == 404
    )


def test_flag_off_leaves_no_receipt_state_behind(sharing_off: None) -> None:
    client = _client()
    _seed(client)
    client.post(CREATE_PATH, json={"owner_note": "hello"})
    assert api_state.store.public_excerpt_snapshots == {}


def test_flag_off_responses_are_byte_identical_to_a_route_that_never_existed(
    sharing_off: None,
) -> None:
    """Pins the flag-off byte identity so it cannot drift back.

    A distinctive problem body would answer 404 and still advertise that receipt
    code is deployed. The reference is a path that genuinely does not exist.
    """
    client = _client()
    _seed(client)
    reference = client.get("/api/v1/definitely-not-a-route")
    assert reference.status_code == 404

    for method, path, body in _FLAG_OFF_PROBES:
        response = client.request(method, path, json=body)
        assert response.status_code == reference.status_code, path
        assert response.content == reference.content, path
        assert sorted(response.headers) == sorted(reference.headers), path


# ── The happy path ────────────────────────────────────────────────────────────


def test_created_receipt_is_readable_anonymously_and_carries_only_the_payload(
    sharing_on: None,
) -> None:
    client = _client()
    _seed(client)
    receipt = _create(client, note="Surprised by the drawdown.")

    assert receipt["path"] == f"{PUBLIC_EXCERPT_PATH_PREFIX}{receipt['public_id']}"
    view = client.get(f"/api/v1/public/receipts/{receipt['public_id']}")
    assert view.status_code == 200
    body = view.json()
    assert body["status"] == "available"
    assert body["indexing"] == "noindex, nofollow"
    assert body["payload"]["turns"][0]["owner_note"] == "Surprised by the drawdown."
    assert set(body) == {
        "public_id",
        "status",
        "kind",
        "indexing",
        "created_at",
        "payload",
    }


def test_public_read_response_contains_no_private_identifier(sharing_on: None) -> None:
    client = _client()
    user_id = _seed(client)
    receipt = _create(client)
    raw = client.get(f"/api/v1/public/receipts/{receipt['public_id']}").text
    for private_id in (user_id, CONVERSATION_ID, ARTIFACT_ID, build_run().id):
        assert private_id not in raw


def test_owner_list_shows_the_receipt_without_a_source_reference(
    sharing_on: None,
) -> None:
    client = _client()
    _seed(client)
    receipt = _create(client)
    listed = client.get(LIST_PATH).json()["items"]
    assert [item["id"] for item in listed] == [receipt["id"]]
    assert set(listed[0]) == {
        "id",
        "public_id",
        "path",
        "title",
        "symbols",
        "date_range",
        "kind",
        "created_at",
        "revoked_at",
        "revocation_reason",
    }


# ── Revocation ────────────────────────────────────────────────────────────────


def test_owner_revocation_takes_effect_on_the_next_read(sharing_on: None) -> None:
    client = _client()
    _seed(client)
    receipt = _create(client)

    revoked = client.delete(f"{LIST_PATH}/{receipt['id']}")
    assert revoked.status_code == 200
    assert revoked.json()["receipt"]["revocation_reason"] == "owner_revoked"

    view = client.get(f"/api/v1/public/receipts/{receipt['public_id']}").json()
    assert view["status"] == "revoked"
    assert view["payload"] is None


def test_deleting_the_conversation_revokes_its_receipt(sharing_on: None) -> None:
    client = _client()
    _seed(client)
    receipt = _create(client)

    deleted = client.delete(f"/api/v1/conversations/{CONVERSATION_ID}")
    assert deleted.status_code == 200

    view = client.get(f"/api/v1/public/receipts/{receipt['public_id']}").json()
    assert view["status"] == "revoked"
    listed = client.get(LIST_PATH).json()["items"]
    assert listed[0]["revocation_reason"] == "source_deleted"


def test_deleting_all_conversations_revokes_every_receipt(sharing_on: None) -> None:
    client = _client()
    _seed(client)
    receipt = _create(client)

    assert client.delete("/api/v1/conversations").status_code == 200

    view = client.get(f"/api/v1/public/receipts/{receipt['public_id']}").json()
    assert view["status"] == "revoked"


def test_a_revoked_link_answers_a_tombstone_not_a_not_found(sharing_on: None) -> None:
    client = _client()
    _seed(client)
    receipt = _create(client)
    client.delete(f"{LIST_PATH}/{receipt['id']}")

    response = client.get(f"/api/v1/public/receipts/{receipt['public_id']}")
    assert response.status_code == 200
    assert response.json()["status"] == "revoked"


def test_an_unknown_link_is_indistinguishable_from_a_revoked_one(
    sharing_on: None,
) -> None:
    client = _client()
    _seed(client)
    known = _create(client)
    client.delete(f"{LIST_PATH}/{known['id']}")

    revoked = client.get(f"/api/v1/public/receipts/{known['public_id']}").json()
    unknown = client.get("/api/v1/public/receipts/zzzzzzzzzzzzzzzzzzzzzzzz").json()
    assert revoked["status"] == unknown["status"] == "revoked"
    assert revoked["payload"] is unknown["payload"] is None


def test_revoking_twice_is_not_an_error_and_does_not_reverse(sharing_on: None) -> None:
    client = _client()
    _seed(client)
    receipt = _create(client)
    first = client.delete(f"{LIST_PATH}/{receipt['id']}").json()["receipt"]
    second = client.delete(f"{LIST_PATH}/{receipt['id']}").json()["receipt"]
    assert first["revoked_at"] == second["revoked_at"]


def test_a_revoked_result_can_be_shared_again_as_a_new_link(sharing_on: None) -> None:
    client = _client()
    _seed(client)
    first = _create(client)
    client.delete(f"{LIST_PATH}/{first['id']}")

    second = _create(client)
    assert second["public_id"] != first["public_id"]
    assert (
        client.get(f"/api/v1/public/receipts/{first['public_id']}").json()["status"]
        == "revoked"
    )
    assert (
        client.get(f"/api/v1/public/receipts/{second['public_id']}").json()["status"]
        == "available"
    )


# ── Abuse posture ─────────────────────────────────────────────────────────────


def test_receipt_creation_is_rate_limited(sharing_on: None) -> None:
    client = _client()
    user_id = _seed(client)
    # The mock developer is an admin and admins bypass the limiter by contract.
    user = api_state.store.get_or_create_dev_user()
    api_state.store.users[user_id] = user.model_copy(update={"is_admin": False})
    # Each new artifact is a distinct receipt, so the limit is what stops the run.
    for index in range(evidence_receipts.RECEIPT_CREATE_LIMIT):
        artifact = build_artifact(artifact_id=stable_uuid(index, prefix=4))
        api_state.store.evidence_artifacts[artifact.id] = artifact
        api_state.store.evidence_artifact_owners[artifact.id] = user_id
        response = client.post(
            f"/api/v1/evidence-artifacts/{artifact.id}/public-excerpt", json={}
        )
        assert response.status_code == 200, response.text

    blocked = build_artifact(artifact_id=stable_uuid(1, prefix=5))
    api_state.store.evidence_artifacts[blocked.id] = blocked
    api_state.store.evidence_artifact_owners[blocked.id] = user_id
    refused = client.post(
        f"/api/v1/evidence-artifacts/{blocked.id}/public-excerpt", json={}
    )
    assert refused.status_code == 429
    assert refused.headers["Retry-After"]


def test_a_note_with_credential_shaped_text_is_previewed_and_shared(
    sharing_on: None,
) -> None:
    client = _client()
    _seed(client)
    response = client.post(
        CREATE_PATH, json={"owner_note": "token EXAMPLENOTAREALCREDENTIALTOKEN"}
    )
    assert response.status_code == 200
    assert api_state.store.public_excerpt_snapshots


def test_a_note_longer_than_the_bound_is_refused_by_the_schema(
    sharing_on: None,
) -> None:
    client = _client()
    _seed(client)
    response = client.post(CREATE_PATH, json={"owner_note": "word " * 200})
    assert response.status_code == 422


def test_an_unowned_artifact_cannot_be_shared(sharing_on: None) -> None:
    client = _client()
    _seed(client)
    artifact = build_artifact(artifact_id=stable_uuid(3, prefix=5))
    api_state.store.evidence_artifacts[artifact.id] = artifact
    api_state.store.evidence_artifact_owners[artifact.id] = "another-user"
    response = client.post(
        f"/api/v1/evidence-artifacts/{artifact.id}/public-excerpt", json={}
    )
    assert response.status_code == 404


def test_the_funnel_endpoint_stores_nothing_and_accepts_only_known_stages(
    sharing_on: None,
) -> None:
    client = _client()
    for stage in ("viewed", "try_argus"):
        assert (
            client.post(
                "/api/v1/public/receipt-funnel", json={"stage": stage}
            ).status_code
            == 204
        ), stage
    for rejected in ("receipt_viewed", "anything", ""):
        assert (
            client.post(
                "/api/v1/public/receipt-funnel", json={"stage": rejected}
            ).status_code
            == 422
        ), rejected
    assert api_state.store.public_excerpt_snapshots == {}


def test_reading_a_receipt_never_counts_a_view(
    sharing_on: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The read endpoint answers metadata passes and preview images too, and the
    funnel endpoint is a no-op in wave 1: neither reaches PostHog."""
    posts: list[object] = []
    monkeypatch.setenv("POSTHOG_PROJECT_TOKEN", "ph_project_token")
    monkeypatch.setenv("POSTHOG_REGION", "us")
    monkeypatch.setattr(
        "argus.observability.envelope.httpx.post",
        lambda *args, **kwargs: posts.append((args, kwargs)),
    )
    client = _client()
    _seed(client)
    receipt = _create(client)
    posts.clear()

    for _ in range(3):
        assert (
            client.get(f"/api/v1/public/receipts/{receipt['public_id']}").status_code
            == 200
        )
    for stage in ("viewed", "try_argus", "followed_up", "signed_up"):
        assert (
            client.post(
                "/api/v1/public/receipt-funnel", json={"stage": stage}
            ).status_code
            == 204
        )
    assert posts == []


def test_an_admin_is_not_rate_limited_on_creation(sharing_on: None) -> None:
    """docs/API_CONTRACT.md bypasses quota and rate limits for is_admin.

    The mock developer account is an admin, so an unconditional limiter also blocked
    internal QA of this surface.
    """
    client = _client()
    user_id = _seed(client)
    assert api_state.store.get_or_create_dev_user().is_admin is True
    for index in range(evidence_receipts.RECEIPT_CREATE_LIMIT + 3):
        artifact = build_artifact(artifact_id=stable_uuid(index, prefix=2))
        api_state.store.evidence_artifacts[artifact.id] = artifact
        api_state.store.evidence_artifact_owners[artifact.id] = user_id
        response = client.post(
            f"/api/v1/evidence-artifacts/{artifact.id}/public-excerpt", json={}
        )
        assert response.status_code == 200, (index, response.text)


def test_an_ordinary_account_is_still_rate_limited(sharing_on: None) -> None:
    client = _client()
    user_id = _seed(client)
    user = api_state.store.get_or_create_dev_user()
    api_state.store.users[user_id] = user.model_copy(update={"is_admin": False})
    for index in range(evidence_receipts.RECEIPT_CREATE_LIMIT):
        artifact = build_artifact(artifact_id=stable_uuid(index, prefix=3))
        api_state.store.evidence_artifacts[artifact.id] = artifact
        api_state.store.evidence_artifact_owners[artifact.id] = user_id
        assert (
            client.post(
                f"/api/v1/evidence-artifacts/{artifact.id}/public-excerpt", json={}
            ).status_code
            == 200
        )
    blocked = build_artifact(artifact_id=stable_uuid(2, prefix=5))
    api_state.store.evidence_artifacts[blocked.id] = blocked
    api_state.store.evidence_artifact_owners[blocked.id] = user_id
    refused = client.post(
        f"/api/v1/evidence-artifacts/{blocked.id}/public-excerpt", json={}
    )
    assert refused.status_code == 429


# ── Construction guard on the public route module ─────────────────────────────

PUBLIC_ROUTER_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "argus"
    / "api"
    / "routers"
    / "public_receipts.py"
)

FORBIDDEN_IDENTIFIER_FRAGMENTS = (
    "conversation",
    "message",
    "backtest",
    "evidence_artifact",
    "idea",
    "decision",
    "memory",
    "supabase_gateway",
    "current_user",
    "store",
)


def test_the_public_route_module_names_nothing_private() -> None:
    """The public read cannot reach private data because it cannot name it.

    A behavioural proof lives in test_public_excerpt_receipts.py; this is the
    cheap structural guard that stops a private read being added here later.
    """
    tree = ast.parse(PUBLIC_ROUTER_SOURCE.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.alias):
            names.add(node.asname or node.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    offenders = {
        name
        for name in names
        for fragment in FORBIDDEN_IDENTIFIER_FRAGMENTS
        if fragment in name.lower()
    }
    assert offenders == set(), f"public route module names private data: {offenders}"


def test_the_public_route_module_holds_only_the_reader_and_the_funnel() -> None:
    tree = ast.parse(PUBLIC_ROUTER_SOURCE.read_text(encoding="utf-8"))
    functions = [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    ]
    assert functions == [
        "read_public_receipt",
        "record_receipt_funnel_stage",
    ]


# ── Review follow-ups: pagination, insert race, funnel accuracy ───────────────


def _seed_extra_artifacts(user_id: str, count: int) -> None:
    for index in range(count):
        artifact = build_artifact(artifact_id=stable_uuid(index, prefix=1))
        api_state.store.evidence_artifacts[artifact.id] = artifact
        api_state.store.evidence_artifact_owners[artifact.id] = user_id
        run = build_run(run_id=stable_uuid(index, prefix=8))
        api_state.store.backtest_runs[run.id] = run
        api_state.store.backtest_run_owners[run.id] = user_id
        api_state.store.evidence_artifacts[artifact.id] = artifact.model_copy(
            update={"source_run_id": run.id}
        )
        seed_result_messages(api_state.store, run, offset=index + 1)


def test_the_receipt_list_pages_instead_of_hiding_older_live_links(
    sharing_on: None,
) -> None:
    """No live receipt may be unreachable.

    Data Controls is the only place an owner can find a snapshot id, so a row that
    falls off the list is a public page they cannot take down.
    """
    client = _client()
    user_id = _seed(client)
    _seed_extra_artifacts(user_id, 5)
    created: list[str] = []
    for index in range(5):
        response = client.post(
            f"/api/v1/evidence-artifacts/{stable_uuid(index, prefix=1)}/public-excerpt",
            json={},
        )
        assert response.status_code == 200, response.text
        created.append(response.json()["receipt"]["id"])

    seen: list[str] = []
    cursor: str | None = None
    pages = 0
    while True:
        query = f"{LIST_PATH}?limit=2" + (f"&cursor={cursor}" if cursor else "")
        body = client.get(query).json()
        assert len(body["items"]) <= 2
        seen.extend(item["id"] for item in body["items"])
        pages += 1
        cursor = body["next_cursor"]
        if not cursor:
            break
        assert pages < 20, "pagination did not terminate"

    # Every receipt is reachable exactly once, in newest-first order.
    assert len(seen) == len(set(seen))
    assert set(created).issubset(set(seen))
    assert pages > 1


def test_a_stale_or_malformed_cursor_is_rejected(sharing_on: None) -> None:
    client = _client()
    _seed(client)
    _create(client)
    assert client.get(f"{LIST_PATH}?cursor=not-base64").status_code == 400
    assert client.get(f"{LIST_PATH}?limit=0").status_code == 422
    assert client.get(f"{LIST_PATH}?limit=99999").status_code == 422


def test_resharing_a_result_does_not_count_as_a_new_receipt(
    sharing_on: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The funnel's creation stage must not count retries and reloads."""
    events: list[str] = []
    monkeypatch.setattr(
        evidence_receipts,
        "capture_product_event",
        lambda kind, **kwargs: events.append(kind),
    )
    client = _client()
    _seed(client)
    first = _create(client)
    second = _create(client)

    assert first["public_id"] == second["public_id"]
    assert events == ["receipt_created"]


def test_an_insert_race_returns_the_existing_receipt_rather_than_failing(
    sharing_on: None,
) -> None:
    """The loser of a concurrent create reads the winner's row.

    Both requests can pass the pre-check; the partial unique index lets one in.
    The contract says re-sharing returns the existing link, so a 500 would break it.
    """
    from argus.domain.supabase_public_excerpts import SupabasePublicExcerptMixin

    winner: dict[str, Any] = {}

    class _RacingGateway(SupabasePublicExcerptMixin):
        def __init__(self) -> None:
            self.client = None

        def get_live_public_excerpt_for_selection(self, **kwargs):
            return winner.get("snapshot")

        def get_live_public_excerpt_for_artifact(
            self, *, owner_id: str, evidence_artifact_id: str | None
        ):
            # Empty before the insert, populated after, exactly as the loser of a
            # race would observe it.
            return winner.get("snapshot")

    gateway = _RacingGateway()

    class _FailingTable:
        def insert(self, payload: dict[str, Any]) -> _FailingTable:
            return self

        def execute(self) -> Any:
            raise RuntimeError("duplicate key value violates unique constraint")

    gateway.client = type("C", (), {"table": lambda self, name: _FailingTable()})()

    client = _client()
    user_id = _seed(client)
    seed_response = _create(client)
    live = api_state.store.public_excerpt_snapshots[seed_response["id"]]
    winner["snapshot"] = None

    # First call: no existing row and the insert fails, so the error surfaces.
    with pytest.raises(RuntimeError):
        gateway.create_public_excerpt_snapshot(snapshot=live)

    # Now the winner's row exists, so the loser returns it and reports no creation.
    winner["snapshot"] = live
    snapshot, created = gateway.create_public_excerpt_snapshot(snapshot=live)
    assert snapshot.id == live.id
    assert created is False
    assert live.owner_id == user_id


def test_flag_off_is_identical_for_an_unauthenticated_production_client(
    sharing_off: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The gap the first version of this lane had.

    A flag check inside the route runs after FastAPI resolves ``current_user`` and
    parses the body, so with real auth an unauthenticated caller got 401 (or 500
    where Supabase is absent) and a malformed body got 422. Each of those tells an
    observer that receipt code is deployed. The gate now runs before routing, and
    this covers the path the mock-auth tests above cannot reach.
    """
    monkeypatch.delenv("NEXT_PUBLIC_MOCK_AUTH", raising=False)
    monkeypatch.delenv("CUADRAO_MOCK_AUTH", raising=False)
    client = _client()
    reference = client.get("/api/v1/definitely-not-a-route")
    assert reference.status_code == 404

    for method, path, body in _FLAG_OFF_PROBES:
        response = client.request(method, path, json=body)
        assert response.status_code == reference.status_code, path
        assert response.content == reference.content, path
        assert sorted(response.headers) == sorted(reference.headers), path

    malformed = client.post(
        CREATE_PATH,
        content=b"{not json",
        headers={"Content-Type": "application/json"},
    )
    assert malformed.status_code == reference.status_code
    assert malformed.content == reference.content


# ── Review round 3: no publishing a deleted source, honest revocation counts ──


def test_a_deleted_conversation_cannot_be_shared_afterwards(sharing_on: None) -> None:
    """The trap from the other side.

    Revocation-on-delete only revokes receipts that exist when the delete happens,
    so a stale result card in an open tab could otherwise publish a page for a chat
    the owner had already removed.
    """
    client = _client()
    _seed(client)
    assert client.delete(f"/api/v1/conversations/{CONVERSATION_ID}").status_code == 200

    refused = client.post(CREATE_PATH, json={})
    assert refused.status_code == 404
    assert api_state.store.public_excerpt_snapshots == {}


def test_deleting_all_conversations_also_blocks_later_sharing(
    sharing_on: None,
) -> None:
    client = _client()
    _seed(client)
    assert client.delete("/api/v1/conversations").status_code == 200
    assert client.post(CREATE_PATH, json={}).status_code == 404


def test_an_artifact_whose_conversation_is_gone_is_not_shareable(
    sharing_on: None,
) -> None:
    client = _client()
    user_id = _seed(client)
    # An artifact outlives its conversation, so ownership alone is not enough.
    api_state.store.conversations.pop(CONVERSATION_ID)
    api_state.store.conversation_owners.pop(CONVERSATION_ID)
    assert api_state.store.evidence_artifact_owners[ARTIFACT_ID] == user_id
    assert client.post(CREATE_PATH, json={}).status_code == 404


def test_a_source_deleted_mid_request_is_refused_by_the_database(
    sharing_on: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The race the application check cannot catch.

    The pre-check passes and the delete commits before the insert lands. The insert
    trigger refuses, and that refusal has to read as the ordinary not-available
    answer rather than a 500.
    """
    from argus.api import public_excerpts as service

    client = _client()
    _seed(client)

    real_create = service.public_excerpt_repository().create_public_excerpt_snapshot

    def _raise_source_deleted(**kwargs: Any) -> Any:
        raise RuntimeError(
            'new row violates ... raise exception "public_excerpt_source_deleted"'
        )

    monkeypatch.setattr(
        service.MemoryPublicExcerptRepository,
        "create_public_excerpt_snapshot",
        lambda self, **kwargs: _raise_source_deleted(**kwargs),
    )
    response = client.post(CREATE_PATH, json={})
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert real_create is not None


def test_an_unrelated_insert_failure_is_not_masked_as_not_available(
    sharing_on: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api import public_excerpts as service

    client = _client()
    _seed(client)
    monkeypatch.setattr(
        service.MemoryPublicExcerptRepository,
        "create_public_excerpt_snapshot",
        lambda self, **kwargs: (_ for _ in ()).throw(RuntimeError("disk on fire")),
    )
    # A genuine failure must surface as a failure, not be reshaped into the
    # not-available answer reserved for a deleted source.
    response = client.post(CREATE_PATH, json={})
    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"


def test_revoking_twice_reports_one_revocation_and_emits_nothing(
    sharing_on: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    posts: list[object] = []
    monkeypatch.setenv("POSTHOG_PROJECT_TOKEN", "ph_project_token")
    monkeypatch.setenv("POSTHOG_REGION", "us")
    monkeypatch.setattr(
        "argus.observability.envelope.httpx.post",
        lambda *args, **kwargs: posts.append((args, kwargs)),
    )
    client = _client()
    _seed(client)
    receipt = _create(client)

    first = client.delete(f"{LIST_PATH}/{receipt['id']}")
    second = client.delete(f"{LIST_PATH}/{receipt['id']}")

    assert first.status_code == second.status_code == 200
    assert (
        first.json()["receipt"]["revoked_at"] == (second.json()["receipt"]["revoked_at"])
    )
    assert posts == []


# ── Review round 4: frozen means frozen, transient never reads as permanent ────


def test_changing_your_language_does_not_relabel_an_older_result(
    sharing_on: None,
) -> None:
    """A snapshot may only capture what belongs to the artifact.

    The owner's profile language is mutable, so reading it at share time tagged an
    English result Spanish once the owner switched the app over. The anchor is the
    conversation the artifact came from, which records its language at creation and
    is not patchable.
    """
    client = _client()
    user_id = _seed(client)
    # The result was produced in an English conversation.
    assert api_state.store.conversations[CONVERSATION_ID].language == "en"
    # The owner has since switched the app to Spanish.
    owner = api_state.store.get_or_create_dev_user()
    api_state.store.users[user_id] = owner.model_copy(update={"language": "es-419"})

    receipt = _create(client)
    view = client.get(f"/api/v1/public/receipts/{receipt['public_id']}").json()
    assert view["payload"]["turns"][0]["content_language"] == "en"


def test_a_spanish_conversation_produces_a_spanish_receipt(sharing_on: None) -> None:
    client = _client()
    user_id = _seed(client)
    api_state.store.conversations[CONVERSATION_ID] = build_conversation(language="es-419")
    api_state.store.conversation_owners[CONVERSATION_ID] = user_id
    owner = api_state.store.get_or_create_dev_user()
    # Owner profile in English, conversation in Spanish: the conversation wins.
    api_state.store.users[user_id] = owner.model_copy(update={"language": "en"})

    receipt = _create(client)
    view = client.get(f"/api/v1/public/receipts/{receipt['public_id']}").json()
    assert view["payload"]["turns"][0]["content_language"] == "es-419"


def test_the_snapshot_captures_nothing_mutable_beyond_the_owner_note() -> None:
    """The audit for this class, kept as a test so it cannot silently regress.

    Every payload field must come from the artifact, the immutable run behind it, a
    constant, or the note the owner writes at share time. Reading anything else that
    can change later would make a frozen receipt tell a different story over time.
    """
    from argus.api.public_excerpt_schemas import PublicExcerptPayload

    artifact_derived = {
        "idea_title",
        "asset_class",
        "symbols",
        "strategy_facts",
        "assumptions",
        "date_range",
        "metrics",
        "benchmark_symbol",
        "visual",
    }
    constants = {"schema_version", "framing", "provenance_mark"}
    # Written by the owner at share time, which is what it is for.
    share_time_input = {"owner_note"}
    # Read from the conversation the artifact came from, not from the profile.
    source_derived = {"content_language"}
    assert set(PublicExcerptPayload.model_fields) == (
        artifact_derived | constants | share_time_input | source_derived
    )


@pytest.mark.parametrize(
    ("cursor", "expected_status"),
    [
        ("not-base64", 400),
        # Valid base64 and a valid timestamp, but the item id is not a uuid. This
        # reached an id.lt filter on a uuid column before it was validated.
        (
            base64.urlsafe_b64encode(b"2026-08-07T12:00:00+00:00|not-a-uuid").decode(),
            400,
        ),
        # Filter punctuation in the id half, which is interpolated into a PostgREST
        # filter string.
        (
            base64.urlsafe_b64encode(
                b"2026-08-07T12:00:00+00:00|x),or(owner_id.neq.null"
            ).decode(),
            400,
        ),
        (base64.urlsafe_b64encode(b"not-a-timestamp|" + b"0" * 8).decode(), 400),
        (base64.urlsafe_b64encode(b"2026-08-07T12:00:00+00:00|").decode(), 400),
        (base64.urlsafe_b64encode(b"no-separator").decode(), 400),
    ],
)
def test_a_malformed_cursor_is_rejected_before_any_query(
    sharing_on: None,
    cursor: str,
    expected_status: int,
) -> None:
    client = _client()
    _seed(client)
    _create(client)
    response = client.get(f"{LIST_PATH}?cursor={quote(cursor, safe='')}")
    assert response.status_code == expected_status, response.text


def test_a_valid_cursor_still_pages(sharing_on: None) -> None:
    client = _client()
    user_id = _seed(client)
    for index in range(3):
        artifact = build_artifact(artifact_id=stable_uuid(index, prefix=7))
        api_state.store.evidence_artifacts[artifact.id] = artifact
        api_state.store.evidence_artifact_owners[artifact.id] = user_id
        run = build_run(run_id=stable_uuid(index, prefix=9))
        api_state.store.backtest_runs[run.id] = run
        api_state.store.backtest_run_owners[run.id] = user_id
        api_state.store.evidence_artifacts[artifact.id] = artifact.model_copy(
            update={"source_run_id": run.id}
        )
        seed_result_messages(api_state.store, run, offset=index + 1)
        assert (
            client.post(
                f"/api/v1/evidence-artifacts/{artifact.id}/public-excerpt", json={}
            ).status_code
            == 200
        )
    first = client.get(f"{LIST_PATH}?limit=2").json()
    assert first["next_cursor"]
    second = client.get(
        f"{LIST_PATH}?limit=2&cursor={quote(first['next_cursor'], safe='')}"
    )
    assert second.status_code == 200
    assert second.json()["items"]


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/evidence-artifacts/not-a-uuid/public-excerpt",
        "/api/v1/public-excerpts/not-a-uuid",
    ],
)
def test_a_non_uuid_id_answers_not_found_rather_than_failing(
    sharing_on: None,
    path: str,
) -> None:
    """These ids reach filters on uuid columns, where a cast error is a 500."""
    client = _client()
    _seed(client)
    method = "POST" if path.endswith("public-excerpt") else "DELETE"
    response = client.request(method, path, json={} if method == "POST" else None)
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_an_undescribable_strategy_is_refused_with_a_readable_reason(
    sharing_on: None,
) -> None:
    """Fail closed at the API boundary, not just in the projection.

    A run whose strategy cannot be described completely must not produce a receipt at
    all, and the owner has to be told why in words they can act on.
    """
    client = _client()
    user_id = api_state.store.get_or_create_dev_user().id
    conversation = build_conversation()
    artifact = build_artifact()
    run = build_run().model_copy(
        update={
            "config_snapshot": {
                "template": "signal_strategy",
                "parameters": {
                    "rule_spec": {
                        "entry": {
                            "conditions": [
                                {
                                    "left": {
                                        "kind": "indicator",
                                        "key": "ema",
                                        "period": 9,
                                    },
                                    "operator": "cross_above",
                                    "right": {
                                        "kind": "indicator",
                                        "key": "ema",
                                        "period": 21,
                                    },
                                }
                            ]
                        },
                        "exit": {
                            "conditions": [
                                {
                                    "left": {
                                        "kind": "indicator",
                                        "key": "rsi",
                                        "period": 14,
                                    },
                                    "operator": "gte",
                                    "right": 65,
                                }
                            ]
                        },
                    }
                },
            }
        }
    )
    api_state.store.conversations[conversation.id] = conversation
    api_state.store.conversation_owners[conversation.id] = user_id
    api_state.store.evidence_artifacts[artifact.id] = artifact
    api_state.store.evidence_artifact_owners[artifact.id] = user_id
    api_state.store.backtest_runs[run.id] = run
    api_state.store.backtest_run_owners[run.id] = user_id

    response = client.post(CREATE_PATH, json={})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "receipt_source_unsupported"
    assert "cannot be shared" in body["detail"]
    # Nothing was persisted, so no half-described receipt exists to be read later.
    assert api_state.store.public_excerpt_snapshots == {}


def test_an_unreadable_stored_payload_answers_retryable_not_a_crash(
    sharing_on: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The public read is the one Argus page strangers arrive at from a message.

    A stored payload this build cannot parse is a deployment state, so it answers
    503 with Retry-After, which the page reads as temporarily unavailable. An
    uncaught validation error would answer 500, and the tombstone would tell a
    viewer their live link is gone for good.
    """
    from argus.api import public_excerpts as receipts_module
    from argus.domain.public_excerpts import PublicExcerptUnreadableError

    class _UnreadableReader:
        def read_public_excerpt_view(self, *, public_id: str) -> None:
            raise PublicExcerptUnreadableError("That receipt could not be read.")

    monkeypatch.setattr(
        receipts_module, "public_excerpt_repository", lambda: _UnreadableReader()
    )
    client = _client()
    response = client.get("/api/v1/public/receipts/abcdefghijklmnopqrstuvwx")

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "120"
    body = response.json()
    assert body["code"] == "receipt_unavailable"
    # Never a tombstone: the frontend reads "revoked" as permanent.
    assert "revoked" not in response.text
