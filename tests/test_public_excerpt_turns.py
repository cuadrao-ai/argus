"""Selection receipts use the real owner service and one frozen public contract."""

from uuid import uuid4

import pytest
from argus.api import public_excerpts as service
from argus.api import state as api_state
from argus.api.schemas import Message
from argus.domain.public_excerpts import PublicExcerptSourceError
from pydantic import ValidationError

from tests.public_excerpt_factories import build_conversation, utc


@pytest.fixture
def owner(monkeypatch):
    monkeypatch.setattr(api_state, "supabase_gateway", None)
    api_state.store.reset()
    user = api_state.store.get_or_create_dev_user()
    conversation = build_conversation()
    api_state.store.conversations[conversation.id] = conversation
    api_state.store.conversation_owners[conversation.id] = user.id
    return user, conversation


def add_pair(
    owner,
    *,
    index=0,
    metadata=None,
    question="Why did AAPL rise?",
    answer="Revenue grew **ten percent**.",
):
    user, conversation = owner
    research = {
        "schema_version": "argus_research/v1",
        "shape": "balanced",
        "sources": [
            {
                "title": "Apple results",
                "domain": "apple.com",
                "url": "https://apple.com/newsroom/results",
                "source_date": "2026-08-06",
            }
        ],
        "retrieved_at": utc().isoformat(),
        "anchor_symbols": ["AAPL"],
        "asset_class": "equity",
    }
    common = dict(conversation_id=conversation.id)
    request = Message(
        id=str(uuid4()),
        role="user",
        content=question,
        created_at=utc(index * 2),
        **common,
    )
    response = Message(
        id=str(uuid4()),
        role="assistant",
        content=answer,
        created_at=utc(index * 2 + 1),
        metadata=metadata
        if metadata is not None
        else {
            "agent_runtime_turn": {"terminal": True, "status": "completed"},
            "research": research,
        },
        **common,
    )
    api_state.store.messages.setdefault(conversation.id, []).extend([request, response])
    return request, response


def preview(owner, messages, note=None):
    assert hasattr(
        service, "preview_receipt_for_messages"
    ), "shared message preview service is missing"
    user, conversation = owner
    return service.preview_receipt_for_messages(
        user=user,
        conversation_id=conversation.id,
        message_ids=[m.id for m in messages],
        owner_note=note,
    )


def create(owner, messages, document, note=None):
    user, conversation = owner
    return service.create_receipt_for_messages(
        user=user,
        conversation_id=conversation.id,
        message_ids=[m.id for m in messages],
        owner_note=note,
        expected_digest=document.payload_digest,
    )


def test_preview_is_exact_closed_frozen_document_without_side_effects(owner):
    _, answer = add_pair(owner, question="  Why\n did AAPL rise? ")
    result = preview(owner, [answer])
    assert result.payload.schema_version == 2
    assert result.payload.kind == "turns"
    leaf = result.payload.turns[0]
    assert leaf.question == "  Why\n did AAPL rise? "
    assert leaf.answer == answer.content
    assert set(leaf.model_dump()) == {
        "kind",
        "question",
        "answer",
        "sources",
        "retrieved_at",
        "anchor_symbols",
        "asset_class",
        "offered_next_step",
        "owner_note",
        "content_language",
        "framing",
        "provenance_mark",
    }
    assert not api_state.store.public_excerpt_snapshots
    snapshot, created = create(owner, [answer], result)
    assert created
    assert snapshot.payload == result.payload
    assert snapshot.payload_digest == result.payload_digest
    again, created = create(owner, [answer], result)
    assert not created and again.id == snapshot.id


@pytest.mark.parametrize("count", [0, 1, 4, 9])
def test_selection_bounds_and_canonical_order(owner, count):
    """A selection is one or more distinct eligible turns; nothing about its
    size is a rule, so nine turns freeze as readily as one."""
    answers = [add_pair(owner, index=i)[1] for i in range(count)]
    if count == 0:
        with pytest.raises(PublicExcerptSourceError):
            preview(owner, answers)
    else:
        result = preview(owner, answers[::-1])
        assert len(result.payload.turns) == count
        assert result.payload.turns[0].answer == answers[0].content
        snapshot, created = create(owner, answers, result)
        assert created and len(snapshot.payload.turns) == count


@pytest.mark.parametrize(
    "mutation,reason",
    [
        (lambda m: m["research"].update(shape="find"), "unsupported_shape"),
        (lambda m: m["research"].update(shape="personal_money"), "unsupported_shape"),
        (lambda m: m["agent_runtime_turn"].update(terminal=False), "not_completed"),
    ],
)
def test_refusal_refuses_whole_selection_and_candidates_name_reason(
    owner, mutation, reason
):
    _, eligible = add_pair(owner)
    _, other = add_pair(owner, index=1)
    mutation(other.metadata)
    with pytest.raises(PublicExcerptSourceError) as error:
        preview(owner, [eligible, other])
    assert error.value.reason == reason
    assert not api_state.store.public_excerpt_snapshots
    candidates = service.receipt_candidates(user=owner[0], conversation_id=owner[1].id)
    assert set(candidates.model_dump()) == {"items"}
    assert candidates.items[1].reason == reason
    assert not candidates.items[1].eligible


@pytest.mark.parametrize("shape", ["fast", "balanced", "thorough"])
def test_every_rail_shape_with_a_publisher_is_a_receipt(owner, shape):
    """All answer rail shapes share; sources are preserved when present."""
    _, answer = add_pair(
        owner, question="What is Apple at?", answer="Apple is at **$316.22**."
    )
    answer.metadata["research"]["shape"] = shape
    result = preview(owner, [answer])
    assert result.payload.turns[0].kind == "research_answer"
    assert result.payload.turns[0].answer == answer.content
    candidates = service.receipt_candidates(user=owner[0], conversation_id=owner[1].id)
    assert candidates.items[0].eligible
    answer.metadata["research"]["sources"] = []
    assert preview(owner, [answer]).payload.turns[0].sources == []


@pytest.mark.parametrize("field", ["question", "answer", "owner_note"])
def test_every_prose_field_rejects_exact_private_argus_identifiers(owner, field):
    unsafe = owner[1].id
    kwargs = {field: unsafe} if field != "owner_note" else {}
    _, answer = add_pair(owner, **kwargs)
    with pytest.raises(PublicExcerptSourceError) as error:
        preview(owner, [answer], unsafe if field == "owner_note" else None)
    assert error.value.field == field


@pytest.mark.parametrize("field,length", [("owner_note", 281)])
def test_field_bounds_refuse_without_truncation(owner, field, length):
    value = ("short " * length)[:length]
    _, answer = add_pair(owner, **({field: value} if field != "owner_note" else {}))
    with pytest.raises(PublicExcerptSourceError) as error:
        preview(owner, [answer], value if field == "owner_note" else None)
    assert error.value.field == field
    assert error.value.reason == "text_too_long"


@pytest.mark.parametrize(
    "answer",
    [
        "[source](https://evil.test/x)",
        "<https://evil.test/x>",
        "[source][ref]\n\n[ref]: https://evil.test/x",
        "![image](https://evil.test/x)",
        "<a href='https://evil.test/x'>x</a>",
        "Read https://evil.test/x",
    ],
)
def test_owner_preview_accepts_links_without_a_source_list_entry(owner, answer):
    _, message = add_pair(owner, answer=answer)
    assert preview(owner, [message]).payload.turns[0].answer == answer


def test_listed_markdown_link_preserved_and_next_step_reads_typed_symbols(owner):
    _, message = add_pair(owner, answer="[Apple](https://apple.com/newsroom/results)")
    message.metadata["next_experiments"] = {
        "rows": [
            {
                "kind": "research_test_single",
                "label": "wrong TSLA",
                "send_text": "MSFT",
                "label_parts": [{"type": "ticker", "value": "AAPL"}],
            }
        ]
    }
    leaf = preview(owner, [message]).payload.turns[0]
    assert leaf.answer == message.content
    assert leaf.offered_next_step.symbols == ["AAPL"]
    message.metadata["next_experiments"]["rows"][0]["kind"] = "unknown_future_kind"
    assert preview(owner, [message]).payload.turns[0].offered_next_step is None


def test_preview_drift_refuses_and_existing_live_preview_returns_stored_note(owner):
    _, message = add_pair(owner)
    first = preview(owner, [message], "First note")
    message.content = "Revenue grew twenty percent."
    with pytest.raises(PublicExcerptSourceError) as error:
        create(owner, [message], first, "First note")
    assert error.value.reason == "preview_changed"
    current = preview(owner, [message], "First note")
    snapshot, _ = create(owner, [message], current, "First note")
    existing = preview(owner, [message], "Another note")
    assert existing.payload == snapshot.payload
    assert existing.existing_receipt.id == snapshot.id


def test_closed_nested_models_reject_extra_source_fields(owner):
    _, message = add_pair(owner)
    result = preview(owner, [message])
    document = result.payload.model_dump(mode="json")
    document["turns"][0]["sources"][0]["message_id"] = "private"
    with pytest.raises(ValidationError):
        type(result.payload).model_validate(document)


def test_a_request_beyond_the_transport_bound_is_refused_before_any_work(owner):
    """Five hundred ids is a request-size bound no conversation reaches, never
    a product cap: one more is refused as an invalid selection before the
    conversation is read, and a client is never told the number."""
    from argus.api.public_excerpt_schemas import (
        PUBLIC_EXCERPT_SELECTION_REQUEST_LIMIT,
        PublicExcerptCandidates,
    )

    user, conversation = owner
    ids = [str(uuid4()) for _ in range(PUBLIC_EXCERPT_SELECTION_REQUEST_LIMIT + 1)]
    with pytest.raises(PublicExcerptSourceError) as error:
        service.preview_receipt_for_messages(
            user=user, conversation_id=conversation.id, message_ids=ids, owner_note=None
        )
    assert error.value.reason == "invalid_selection"
    assert "max_turns" not in PublicExcerptCandidates.model_fields


def test_duplicate_and_foreign_message_selection_refuses(owner):
    _, message = add_pair(owner)
    with pytest.raises(PublicExcerptSourceError):
        preview(owner, [message, message])
    foreign = message.model_copy(
        update={"id": str(uuid4()), "conversation_id": str(uuid4())}
    )
    with pytest.raises(PublicExcerptSourceError):
        preview(owner, [message, foreign])


def test_owner_candidate_preview_create_routes_and_drift(owner, monkeypatch):
    from argus.api.main import app
    from fastapi.testclient import TestClient

    monkeypatch.setenv("CUADRAO_EVIDENCE_RECEIPT_SHARING_ENABLED", "true")
    _, message = add_pair(owner)
    base = f"/api/v1/conversations/{owner[1].id}/public-excerpt"
    client = TestClient(app)
    candidates = client.get(base + "-candidates")
    assert candidates.status_code == 200, candidates.text
    assert set(candidates.json()) == {"items"}
    body = {"message_ids": [message.id]}
    preview_response = client.post(base + "-preview", json=body)
    assert preview_response.status_code == 200, preview_response.text
    created = client.post(
        base, json={**body, "payload_digest": preview_response.json()["payload_digest"]}
    )
    assert created.status_code == 200, created.text
    assert created.json()["receipt"]["kind"] == "research_answer"
    assert (
        client.get(
            "/api/v1/public/receipts/" + created.json()["receipt"]["public_id"]
        ).json()["payload"]
        == preview_response.json()["payload"]
    )


@pytest.mark.parametrize("suffix", ["", "-preview", "-candidates"])
def test_selection_routes_flag_off_byte_identity(owner, monkeypatch, suffix):
    from argus.api.main import app
    from fastapi.testclient import TestClient

    monkeypatch.setenv("CUADRAO_EVIDENCE_RECEIPT_SHARING_ENABLED", "false")
    client = TestClient(app)
    reference = client.get("/api/v1/absent-share-answer")
    response = client.post(
        f"/api/v1/conversations/bad-id/public-excerpt{suffix}", content="invalid json"
    )
    assert response.status_code == reference.status_code
    assert response.content == reference.content


def test_guest_handoff_share_pending_action_requires_canonical_message():
    from argus.api.schemas import GuestPendingAction

    common = {
        "reason": "share_result",
        "conversation_id": str(uuid4()),
        "action_id": str(uuid4()),
    }
    message_id = str(uuid4())
    action = GuestPendingAction.model_validate({**common, "message_id": message_id})
    assert action.message_id == message_id
    with pytest.raises(ValidationError):
        GuestPendingAction.model_validate(common)
    with pytest.raises(ValidationError):
        GuestPendingAction.model_validate(
            {**common, "reason": "keep_history", "message_id": message_id}
        )


@pytest.mark.parametrize("status", ["succeeded", "running", "failed"])
def test_background_research_uses_canonical_job_settlement_and_original_question(
    owner, status
):
    from argus.domain.job_settlement import RESEARCH_OPERATION_SCOPE

    request, response = add_pair(owner)
    response.metadata.pop("agent_runtime_turn")
    # Another user message between dispatch and answer cannot become its question.
    later_request, _ = add_pair(owner, index=1, question="A different question")
    response.created_at = utc(5)
    job_id = str(uuid4())
    api_state.store.backtest_jobs[job_id] = {
        "id": job_id,
        "user_id": owner[0].id,
        "conversation_id": owner[1].id,
        "operation_scope": RESEARCH_OPERATION_SCOPE,
        "status": status,
        "request_message_id": request.id,
        "execution_metadata": {"research_result_message_id": response.id},
    }
    if status == "succeeded":
        assert preview(owner, [response]).payload.turns[0].question == request.content
    else:
        with pytest.raises(PublicExcerptSourceError) as error:
            preview(owner, [response])
        assert error.value.reason == "not_completed"


def seed_backtest(owner):
    from tests.public_excerpt_factories import (
        build_artifact,
        build_run,
        seed_result_messages,
    )

    artifact, run = build_artifact(), build_run()
    store = api_state.store
    store.evidence_artifacts[artifact.id] = artifact
    store.evidence_artifact_owners[artifact.id] = owner[0].id
    store.backtest_runs[run.id] = run
    store.backtest_run_owners[run.id] = owner[0].id
    messages = seed_result_messages(store, run)
    return artifact, run, messages[-1]


def test_artifact_shortcut_turn_and_historical_v1_keep_one_lineage(owner):
    from argus.api.public_excerpt_schemas import PUBLIC_EXCERPT_DOCUMENT_ADAPTER
    from argus.domain.public_excerpts import (
        build_public_excerpt_payload,
        new_public_excerpt_id,
        payload_digest,
    )

    artifact, run, message = seed_backtest(owner)
    first = preview(owner, [message])
    snapshot, _ = service.create_receipt_for_artifact(
        user=owner[0], artifact_id=artifact.id, owner_note=None
    )
    assert create(owner, [message], first)[0].id == snapshot.id
    service.public_excerpt_repository().revoke_public_excerpt_snapshot(
        owner_id=owner[0].id, snapshot_id=snapshot.id
    )
    legacy = build_public_excerpt_payload(
        artifact=artifact,
        run_chart=run.chart,
        run_config_snapshot=run.config_snapshot,
        owner_note="Legacy",
        content_language="en",
    )
    raw = legacy.model_dump_json()
    assert PUBLIC_EXCERPT_DOCUMENT_ADAPTER.validate_json(raw).model_dump_json() == raw
    saved = snapshot.model_copy(
        update={
            "id": str(uuid4()),
            "public_id": new_public_excerpt_id(),
            "payload": legacy,
            "payload_digest": payload_digest(legacy),
            "selection_key": None,
            "source_message_ids": [],
        }
    )
    api_state.store.public_excerpt_snapshots[saved.id] = saved
    assert preview(owner, [message], "Different").payload.model_dump_json() == raw
    # Stored snapshots and the artifact's existing-live adapter remain readable
    # even if their historical source would no longer qualify for a new share.
    run.metrics = {"aggregate": {"performance": {"max_drawdown_pct": -6.2}}}
    assert (
        service.public_excerpt_reader()
        .read_public_excerpt_view(public_id=saved.public_id)
        .payload.model_dump_json()
        == raw
    )
    assert (
        service.create_receipt_for_artifact(
            user=owner[0], artifact_id=artifact.id, owner_note=None
        )[0].id
        == saved.id
    )


def assert_incomplete_backtest_refused(owner, monkeypatch, change_run):
    from argus.api.main import app
    from argus.api.routers.evidence_receipts import reset_receipt_create_limiter_for_tests
    from fastapi.testclient import TestClient

    monkeypatch.setenv("CUADRAO_EVIDENCE_RECEIPT_SHARING_ENABLED", "true")
    reset_receipt_create_limiter_for_tests()
    artifact, run, message = seed_backtest(owner)
    _, research = add_pair(owner, index=2)
    selections = ([message], [message, research])
    # A create attempted with a previously valid preview still rechecks every
    # selected source before it can write a receipt or return a drift error.
    previews = [preview(owner, selected) for selected in selections]
    change_run(run)
    base = f"/api/v1/conversations/{owner[1].id}/public-excerpt"
    with TestClient(app) as client:
        candidates = client.get(base + "-candidates")
        assert candidates.status_code == 200
        by_id = {item["message_id"]: item for item in candidates.json()["items"]}
        assert not by_id[message.id]["eligible"]
        assert by_id[message.id]["reason"] == "unsupported_backtest"
        assert by_id[research.id]["eligible"]
        for selected, prior in zip(selections, previews, strict=True):
            body = {"message_ids": [m.id for m in selected]}
            for response in (
                client.post(base + "-preview", json=body),
                client.post(base, json={**body, "payload_digest": prior.payload_digest}),
            ):
                assert response.status_code == 422, response.text
                assert response.json()["code"] == "receipt_source_unsupported"
                assert response.json()["context"]["reason"] == "unsupported_backtest"
        adapter = client.post(
            f"/api/v1/evidence-artifacts/{artifact.id}/public-excerpt", json={}
        )
        assert adapter.status_code == 422, adapter.text
        assert adapter.json()["code"] == "receipt_source_unsupported"
    assert not api_state.store.public_excerpt_snapshots


@pytest.mark.parametrize(
    "available", ["drawdown_only", "headline_only", "gross_net_only"]
)
def test_partial_figure_sets_refuse_all_new_receipt_paths(owner, monkeypatch, available):
    def change(run):
        performance = run.metrics["aggregate"]["performance"]
        if available == "headline_only":
            kept = {"total_return_pct": performance["total_return_pct"]}
        elif available == "gross_net_only":
            kept = {
                "execution_realism": {
                    "enabled": True,
                    "gross_total_return_pct": 2,
                    "net_total_return_pct": 1,
                }
            }
        else:
            kept = {"max_drawdown_pct": -6.2}
        run.metrics["aggregate"]["performance"] = kept

    assert_incomplete_backtest_refused(owner, monkeypatch, change)


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        (field, invalid)
        for field in (
            "total_return_pct",
            "benchmark_return_pct",
            "delta_vs_benchmark_pct",
        )
        for invalid in (None, "unavailable", True, float("nan"), float("inf"))
        # A run without its stored gap still states the gap of its shown returns.
        if (field, invalid) != ("delta_vs_benchmark_pct", None)
    ],
)
def test_missing_or_invalid_required_figures_refuse_publication(
    owner, monkeypatch, field, invalid
):
    def change(run):
        performance = run.metrics["aggregate"]["performance"]
        if invalid is None:
            performance.pop(field)
        else:
            performance[field] = invalid

    assert_incomplete_backtest_refused(owner, monkeypatch, change)


def test_a_run_without_its_stored_gap_publishes_the_gap_of_its_shown_returns(owner):
    from argus.domain.display_figure import display_difference

    _, run, message = seed_backtest(owner)
    performance = run.metrics["aggregate"]["performance"]
    del performance["delta_vs_benchmark_pct"]

    figures = preview(owner, [message]).payload.turns[0].fact_bank.figures

    assert figures.delta_vs_benchmark_pct == display_difference(
        performance["total_return_pct"], performance["benchmark_return_pct"]
    )
    assert figures.benchmark_comparison_claim == "beat_benchmark"


def set_benchmark_name(run, location):
    run.benchmark_symbol = ""
    for key in ("benchmark_symbol", "resolved_parameters", "parameters"):
        run.config_snapshot.pop(key, None)
    if location == "run":
        run.benchmark_symbol = "SPY"
    elif location == "config":
        run.config_snapshot["benchmark_symbol"] = "SPY"
    elif location is not None:
        run.config_snapshot[location] = {"benchmark_symbol": "SPY"}


@pytest.mark.parametrize("location", ["config", "resolved_parameters", "parameters"])
def test_a_benchmark_named_in_public_config_requires_evidence(
    owner, monkeypatch, location
):
    def change(run):
        set_benchmark_name(run, location)
        run.metrics["aggregate"]["performance"].pop("benchmark_return_pct")

    assert_incomplete_backtest_refused(owner, monkeypatch, change)


@pytest.mark.parametrize(
    "location", ["run", "config", "resolved_parameters", "parameters", None]
)
def test_complete_zero_returns_and_unnamed_benchmark_remain_shareable(owner, location):
    artifact, run, message = seed_backtest(owner)
    set_benchmark_name(run, location)
    performance = run.metrics["aggregate"]["performance"]
    for key in tuple(performance):
        if location is None and key != "total_return_pct":
            del performance[key]
        else:
            performance[key] = 0.0
    candidate = service.receipt_candidates(
        user=owner[0], conversation_id=owner[1].id
    ).items[0]
    assert candidate.eligible
    document = preview(owner, [message])
    figures = document.payload.turns[0].fact_bank.figures
    assert figures.total_return_pct == 0.0
    if location is not None:
        assert figures.benchmark_return_pct == 0.0
        assert figures.delta_vs_benchmark_pct == 0.0
        assert figures.benchmark_comparison_claim == "matched_benchmark"
    snapshot, created = create(owner, [message], document)
    assert created
    reused, created = service.create_receipt_for_artifact(
        user=owner[0], artifact_id=artifact.id, owner_note=None
    )
    assert not created and reused.id == snapshot.id
    assert len(api_state.store.public_excerpt_snapshots) == 1


def test_backtest_uses_shared_display_figures_and_closed_config(owner):
    from argus.domain.result_figures import result_display_figures

    artifact, run, message = seed_backtest(owner)
    run.metrics["aggregate"]["performance"].update(
        total_return_pct=18.451, delta_vs_benchmark_pct=0.045, benchmark_return_pct=18.406
    )
    leaf = preview(owner, [message]).payload.turns[0]
    assert leaf.fact_bank.figures.model_dump(exclude_none=True) == result_display_figures(
        run.metrics
    )
    assert "run_id" not in leaf.fact_bank.model_dump()
    assert "result_card" not in leaf.fact_bank.result_card.model_dump()
    run.config_snapshot["template"] = "future_unknown_strategy"
    with pytest.raises(PublicExcerptSourceError):
        preview(owner, [message])


def test_deleted_or_foreign_conversation_refuses(owner):
    from argus.api.public_excerpts import EvidenceReceiptSourceMissingError

    _, message = add_pair(owner)
    api_state.store.conversation_owners[owner[1].id] = str(uuid4())
    with pytest.raises(EvidenceReceiptSourceMissingError):
        preview(owner, [message])
    api_state.store.conversation_owners[owner[1].id] = owner[0].id
    api_state.store.conversations[owner[1].id] = owner[1].model_copy(
        update={"deleted_at": utc(8)}
    )
    with pytest.raises(EvidenceReceiptSourceMissingError):
        preview(owner, [message])


@pytest.mark.parametrize("template", ["dca_accumulation", "rsi_mean_reversion"])
def test_non_buy_and_hold_freezes_complete_typed_configuration(owner, template):
    from copy import deepcopy

    from tests.public_excerpt_factories import (
        GENERATED_CARD_CONFIG_SNAPSHOT,
        INDICATOR_CONFIG_SNAPSHOT,
    )

    _, run, message = seed_backtest(owner)
    config = deepcopy(
        GENERATED_CARD_CONFIG_SNAPSHOT
        if template == "dca_accumulation"
        else INDICATOR_CONFIG_SNAPSHOT
    )
    run.config_snapshot.update(config)
    run.config_snapshot["date_range"] = {
        "start": "2024-01-02",
        "end": "2024-03-01",
        "display": "private source prose",
    }
    leaf = preview(owner, [message]).payload.turns[0]
    if template == "dca_accumulation":
        assert (
            leaf.fact_bank.config_snapshot.resolved_parameters.recurring_contribution
            == config["resolved_parameters"]["recurring_contribution"]
        )
    else:
        assert (
            leaf.fact_bank.config_snapshot.resolved_parameters.indicator_period
            == config["resolved_parameters"]["indicator_period"]
        )
    assert "private source prose" not in leaf.model_dump_json()
    run.config_snapshot = {"template": template}
    with pytest.raises(PublicExcerptSourceError):
        preview(owner, [message])


@pytest.mark.parametrize("series", [{"kind": "price"}, {"kind": "indicator"}, True])
def test_closed_rule_bank_refuses_incomplete_series_or_boolean_figures(owner, series):
    _, _, message = seed_backtest(owner)
    result = preview(owner, [message]).payload
    document = result.model_dump(mode="json")
    document["turns"][0]["fact_bank"]["config_snapshot"]["parameters"] = {
        "rule_spec": {
            "entry": {"conditions": [{"left": series, "operator": "gt", "right": 1}]}
        }
    }
    with pytest.raises(ValidationError):
        type(result).model_validate(document)


def test_guest_pending_sql_is_derived_from_the_same_closed_contract():
    from pathlib import Path

    from argus.domain.guest_pending_action_contract import (
        render_guest_pending_action_validator,
    )

    migration = Path(
        "supabase/migrations/20260909183646_share_answer_receipt_selections.sql"
    ).read_text()
    assert render_guest_pending_action_validator() in migration


@pytest.mark.parametrize("suffix", ["", "-preview", "-candidates"])
def test_disabled_selection_routes_do_not_advertise_via_slash_redirect(
    owner, monkeypatch, suffix
):
    from argus.api.main import app
    from fastapi.testclient import TestClient

    monkeypatch.setenv("CUADRAO_EVIDENCE_RECEIPT_SHARING_ENABLED", "false")
    client = TestClient(app, follow_redirects=False)
    response = client.get(f"/api/v1/conversations/{owner[1].id}/public-excerpt{suffix}/")
    assert response.status_code == 404
    assert response.content == client.get("/api/v1/absent-share-answer").content


def test_markdown_parentheses_in_a_listed_destination_are_preserved(owner):
    _, message = add_pair(owner, answer="[Report](https://apple.com/report_(2026))")
    message.metadata["research"]["sources"][0]["url"] = "https://apple.com/report_(2026)"
    assert preview(owner, [message]).payload.turns[0].answer == message.content
