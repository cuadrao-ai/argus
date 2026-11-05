"""The closed analytics registry (SPEC 0, package 0C-1, acceptance check A4).

PostHog receives only Iris's wave 1 events, each under its own name, each with
exactly its listed properties. Nothing else reaches PostHog.
"""

from __future__ import annotations

import json
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any, Literal, Union, get_args, get_origin

import httpx
import pytest
from argus.api import state as api_state
from argus.api.guest_access import guest_account_context
from argus.api.guest_observability import emit_verified_guest_funnel_event
from argus.api.main import app
from argus.domain.calculations import get_calculation_declarations
from argus.domain.guest_cleanup import cleanup_expired_guest_workspaces
from argus.domain.guest_workspaces import GuestWorkspace
from argus.observability.analytics_events import (
    ANALYTICS_EVENT_MODELS,
    INVITE_COHORT_PATTERN,
    TECHNICAL_PROPERTIES,
    AnalyticsEvent,
    CardSaved,
    ClosedVocabulary,
    InviteCohort,
    SignedIn,
    build_analytics_envelope,
    capture_analytics_event,
    registered_calculation_names,
)
from argus.observability.envelope import (
    build_event_envelope,
    capture_event,
    posthog_event_payload,
)
from argus.observability.guest_funnel import (
    GUEST_FUNNEL_EVENT_MAP,
    capture_guest_funnel_event,
)
from argus.observability.product_events import (
    _PRODUCT_EVENT_MAP,
    actor_hash_for_user,
    capture_product_event,
)
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pydantic.fields import FieldInfo

IRIS_EVENT_NAMES = {
    "first_answer_shown",
    "signed_in",
    "card_saved",
    "goal_created",
    "checklist_step_completed",
    "reminders_opted_in",
    "reminders_opted_out",
    "session_started",
    "installed_app_opened",
    "landing_viewed",
    "receipt_shared",
}

# One valid instance of every event, with every optional property set.
VALID_PROPERTIES: dict[str, dict[str, Any]] = {
    "first_answer_shown": {
        "account_kind": "guest",
        "chip_audience": "none",
        "language": "es-419",
        "cohort": "piloto-7kq2",
    },
    "signed_in": {"signup": "new", "trigger": "save", "cohort": "piloto-7kq2"},
    "card_saved": {"calculator": "time_value"},
    "goal_created": {"goal_type": "savings"},
    "checklist_step_completed": {"step": 2},
    "reminders_opted_in": {"channel": "email"},
    "reminders_opted_out": {"channel": "push"},
    "session_started": {"days_since_signup": 9, "cohort": "piloto-7kq2"},
    "installed_app_opened": {},
    "landing_viewed": {"language": "en", "cohort": "piloto-7kq2"},
    "receipt_shared": {"calculator": "multiple"},
}

MONEY_FORMATTED_VALUES = ("RD$5,000", "US$5,000.00", "5000.00", "$5,000", 5000.0)

FIXTURES = Path(__file__).parent / "fixtures"


def _event(name: str, **overrides: Any) -> AnalyticsEvent:
    return ANALYTICS_EVENT_MODELS[name](**{**VALID_PROPERTIES[name], **overrides})


@pytest.fixture
def posthog_posts(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """A configured PostHog sink whose network call records the body instead."""
    posts: list[dict[str, Any]] = []

    def fake_post(url: str, *, json: dict[str, Any], timeout: float) -> httpx.Response:
        posts.append(json)
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setenv("POSTHOG_PROJECT_TOKEN", "ph_project_token")
    monkeypatch.setenv("POSTHOG_REGION", "us")
    monkeypatch.setenv("APP_ENV", "private-alpha")
    monkeypatch.setattr("argus.observability.envelope.httpx.post", fake_post)
    return posts


def test_registry_is_exactly_irises_events() -> None:
    assert set(ANALYTICS_EVENT_MODELS) == IRIS_EVENT_NAMES
    assert set(VALID_PROPERTIES) == IRIS_EVENT_NAMES
    for name, model in ANALYTICS_EVENT_MODELS.items():
        assert model.event_name == name


def _optional_parts(annotation: Any) -> list[Any]:
    if get_origin(annotation) in (Union, types.UnionType):
        return [part for part in get_args(annotation) if part is not type(None)]
    return [annotation]


def _literal_values(annotation: Any) -> list[Any] | None:
    values: list[Any] = []
    for part in _optional_parts(annotation):
        if get_origin(part) is not Literal:
            return None
        values.extend(get_args(part))
    return values


def _has_bounds(field: FieldInfo) -> bool:
    lower = any(hasattr(item, "ge") or hasattr(item, "gt") for item in field.metadata)
    upper = any(hasattr(item, "le") or hasattr(item, "lt") for item in field.metadata)
    return lower and upper


def test_every_property_is_literal_bool_or_bounded_int() -> None:
    """The A4 lint: nothing in any event can hold free text or an amount."""
    cohort_parts = [InviteCohort]
    offenders: list[str] = []
    for name, model in ANALYTICS_EVENT_MODELS.items():
        assert model.model_config.get("extra") == "forbid", name
        assert model.model_config.get("strict") is True, name
        for field_name, field in model.model_fields.items():
            where = f"{name}.{field_name}"
            literal_values = _literal_values(field.annotation)
            if literal_values is not None:
                if not all(
                    isinstance(value, str | int) and not isinstance(value, float)
                    for value in literal_values
                ):
                    offenders.append(where)
                continue
            parts = _optional_parts(field.annotation)
            if parts == [bool]:
                continue
            if parts == [int] and _has_bounds(field):
                continue
            # A string checked against a list another owner keeps (the
            # calculation catalog) is as closed as a literal.
            if parts == [str] and any(
                isinstance(item, ClosedVocabulary) for item in field.metadata
            ):
                continue
            # The one constrained string: the invite cohort, pattern-anchored.
            if field_name == "cohort" and parts == cohort_parts:
                continue
            offenders.append(where)
    assert offenders == []
    assert get_origin(InviteCohort) is Annotated
    base, *constraints = get_args(InviteCohort)
    assert base is str
    assert [getattr(item, "pattern", None) for item in constraints] == [
        INVITE_COHORT_PATTERN
    ]


def test_money_formatted_value_is_rejected() -> None:
    for name, model in ANALYTICS_EVENT_MODELS.items():
        for field_name in model.model_fields:
            for value in MONEY_FORMATTED_VALUES:
                with pytest.raises(ValidationError):
                    _event(name, **{field_name: value})
        # A property outside Iris's list cannot be added either.
        with pytest.raises(ValidationError):
            _event(name, amount="RD$5,000")
        with pytest.raises(ValidationError):
            _event(name, question="How much is RD$5,000 at 12%?")


def test_free_text_and_personal_data_are_rejected_in_every_field() -> None:
    for name, model in ANALYTICS_EVENT_MODELS.items():
        for field_name in model.model_fields:
            for value in ("person@example.com", "Iris", "hola", True, "1", 1.0):
                if VALID_PROPERTIES[name].get(field_name) == value:
                    continue
                with pytest.raises(ValidationError):
                    _event(name, **{field_name: value})


def test_bounded_ints_reject_out_of_range_values() -> None:
    with pytest.raises(ValidationError):
        _event("session_started", days_since_signup=-1)
    with pytest.raises(ValidationError):
        _event("session_started", days_since_signup=10**9)
    for step in (0, 4):
        with pytest.raises(ValidationError):
            _event("checklist_step_completed", step=step)


def test_cohort_accepts_only_the_invite_code_format() -> None:
    for code in ("piloto-7kq2", "qa-t7k2", "ab-abcd1234", "abcdefghijkl-0000"):
        assert _event("landing_viewed", cohort=code).model_dump()["cohort"] == code
    for code in (
        "piloto-1",
        "Piloto-7kq2",
        "piloto_7kq2",
        "piloto-7kq2-x",
        "piloto 7kq2",
        "",
        "a-7kq2",
        "piloto-7kq2abcde",
        "abcdefghijklm-7kq2",
    ):
        with pytest.raises(ValidationError):
            _event("landing_viewed", cohort=code)


def test_calculator_values_come_from_the_calculation_catalog() -> None:
    catalog = {declaration.name for declaration in get_calculation_declarations()}
    assert registered_calculation_names() == catalog
    for name in sorted(catalog | {"backtest"}):
        assert CardSaved(calculator=name).calculator == name
    receipt_shared = ANALYTICS_EVENT_MODELS["receipt_shared"]
    for name in sorted(catalog | {"backtest", "multiple", "none"}):
        assert receipt_shared(calculator=name).calculator == name
    for model, name in (
        (CardSaved, "multiple"),
        (CardSaved, "none"),
        (CardSaved, "loan_payoff"),
        (receipt_shared, "loan_payoff"),
    ):
        with pytest.raises(ValidationError):
            model(calculator=name)


def test_a_new_catalog_calculation_is_accepted_without_editing_the_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One owner: adding a calculation to the catalog is the whole change."""
    import argus.domain.calculations as calculations

    original = calculations.get_calculation_declarations
    monkeypatch.setattr(
        calculations,
        "get_calculation_declarations",
        lambda: (*original(), types.SimpleNamespace(name="loan_payoff")),
    )
    registered_calculation_names.cache_clear()
    try:
        assert CardSaved(calculator="loan_payoff").calculator == "loan_payoff"
        assert ANALYTICS_EVENT_MODELS["receipt_shared"](calculator="loan_payoff")
    finally:
        monkeypatch.undo()
        registered_calculation_names.cache_clear()
    with pytest.raises(ValidationError):
        CardSaved(calculator="loan_payoff")


def test_payload_has_only_technical_and_event_properties(
    posthog_posts: list[dict[str, Any]],
) -> None:
    for name in sorted(IRIS_EVENT_NAMES):
        posthog_posts.clear()
        event = _event(name)

        result = capture_analytics_event(
            event,
            user_id="account-raw-id",
            internal_account=False,
        )

        assert result.status == "captured", name
        [body] = posthog_posts
        assert set(body) == {"api_key", "event", "distinct_id", "timestamp", "properties"}
        assert body["event"] == name
        assert body["distinct_id"] == actor_hash_for_user("account-raw-id")
        properties = body["properties"]
        assert set(properties) == TECHNICAL_PROPERTIES | set(VALID_PROPERTIES[name]), name
        assert properties["$process_person_profile"] is False
        assert properties["internal_account"] is False
        assert properties["environment"] == "private-alpha"
        assert properties["schema_version"] == "argus_analytics_event/v1"
        for key, value in VALID_PROPERTIES[name].items():
            assert properties[key] == value
        assert "account-raw-id" not in json.dumps(body)


def test_unset_optional_properties_are_not_sent(
    posthog_posts: list[dict[str, Any]],
) -> None:
    capture_analytics_event(
        ANALYTICS_EVENT_MODELS["landing_viewed"](language="en"),
        user_id="guest-raw-id",
        internal_account=False,
    )

    [body] = posthog_posts
    assert set(body["properties"]) == TECHNICAL_PROPERTIES | {"language"}


def test_only_signed_in_carries_the_guest_id_hash(
    posthog_posts: list[dict[str, Any]],
) -> None:
    capture_analytics_event(
        SignedIn(signup="new", trigger="other"),
        user_id="account-raw-id",
        guest_user_id="guest-raw-id",
        internal_account=False,
    )

    [body] = posthog_posts
    assert body["properties"]["guest_id_hash"] == actor_hash_for_user("guest-raw-id")
    assert "guest-raw-id" not in json.dumps(body)
    for name in sorted(IRIS_EVENT_NAMES - {"signed_in"}):
        with pytest.raises(ValueError):
            capture_analytics_event(
                _event(name),
                user_id="account-raw-id",
                guest_user_id="guest-raw-id",
                internal_account=False,
            )


def test_an_unregistered_event_model_is_refused(
    posthog_posts: list[dict[str, Any]],
) -> None:
    class Unlisted(AnalyticsEvent):
        event_name = "card_saved"

    with pytest.raises(TypeError):
        capture_analytics_event(Unlisted(), user_id="account-raw-id", internal_account=False)
    with pytest.raises(ValueError):
        capture_analytics_event(_event("card_saved"), user_id=" ", internal_account=False)
    assert posthog_posts == []


# ── The sink trusts only what the registry built and re-validates ─────────────


def _generic_envelope_kwargs() -> list[tuple[str, dict[str, Any]]]:
    valid_actor = actor_hash_for_user("account-raw-id")
    return [
        (
            "arbitrary name and attributes",
            {
                "event_type": "analytics",
                "event_action": "completed",
                "feature_area": "product_analytics",
                "analytics_event": "anything_at_all",
                "internal_account": False,
                "actor_hash": valid_actor,
                "attributes": {"amount": "RD$5,000", "question": "How much do I owe?"},
            },
        ),
        (
            "registered name as a string",
            {
                "event_type": "analytics",
                "event_action": "completed",
                "feature_area": "product_analytics",
                "analytics_event": "card_saved",
                "internal_account": False,
                "actor_hash": valid_actor,
                "attributes": {"calculator": "time_value"},
            },
        ),
        (
            "real model with free-text technical fields",
            {
                "event_type": "system",
                "event_action": "failed",
                "feature_area": "storage",
                "analytics_event": CardSaved(calculator="backtest"),
                "schema_version": "person@example.com",
                "event_id": "secret free text",
                "environment": "question text",
                "internal_account": False,
                "actor_hash": valid_actor,
            },
        ),
        (
            "real model with the registry literals and a backdated timestamp",
            {
                "schema_version": "argus_analytics_event/v1",
                "event_type": "analytics",
                "event_action": "completed",
                "feature_area": "product_analytics",
                "analytics_event": CardSaved(calculator="backtest"),
                "occurred_at": datetime(2020, 1, 1, tzinfo=timezone.utc),
                "internal_account": False,
                "actor_hash": valid_actor,
            },
        ),
    ]


@pytest.mark.parametrize(
    ("case", "kwargs"),
    _generic_envelope_kwargs(),
    ids=[case for case, _ in _generic_envelope_kwargs()],
)
def test_a_generic_envelope_cannot_carry_an_analytics_event(
    case: str,
    kwargs: dict[str, Any],
) -> None:
    """Only ``AnalyticsEnvelope`` has the field, and only the registry builds it."""
    with pytest.raises(ValidationError):
        build_event_envelope(**kwargs)


def _forged_envelopes():
    valid_actor = actor_hash_for_user("account-raw-id")
    yield "generic envelope with the registry literals", build_event_envelope(
        schema_version="argus_analytics_event/v1",
        event_type="analytics",
        event_action="completed",
        feature_area="product_analytics",
        actor_hash=valid_actor,
    )
    yield "model_construct skips validation", build_analytics_envelope(
        CardSaved(calculator="time_value"),
        user_id="account-raw-id",
        internal_account=False,
    ).model_copy(
        update={"analytics_event": CardSaved.model_construct(calculator="RD$5,000")}
    )

    class Sneaky(CardSaved):
        amount: str = "RD$5,000"

    yield "subclass of a registered model", build_analytics_envelope(
        CardSaved(calculator="time_value"),
        user_id="account-raw-id",
        internal_account=False,
    ).model_copy(update={"analytics_event": Sneaky(calculator="time_value")})
    yield "extra attribute next to a registered event", build_analytics_envelope(
        CardSaved(calculator="time_value"),
        user_id="account-raw-id",
        internal_account=False,
    ).model_copy(update={"attributes": {"amount": "RD$5,000"}})
    yield "guest hash on an event that does not carry one", build_analytics_envelope(
        CardSaved(calculator="time_value"),
        user_id="account-raw-id",
        internal_account=False,
    ).model_copy(update={"attributes": {"guest_id_hash": valid_actor}})
    yield "free text as the guest hash", build_analytics_envelope(
        SignedIn(signup="new", trigger="save"),
        user_id="account-raw-id",
        internal_account=False,
    ).model_copy(update={"attributes": {"guest_id_hash": "person@example.com"}})
    registry_built = build_analytics_envelope(
        CardSaved(calculator="backtest"),
        user_id="account-raw-id",
        internal_account=False,
    )
    for label, field, value in (
        ("free-text schema_version", "schema_version", "person@example.com"),
        ("free-text event_id", "event_id", "secret free text"),
        ("free-text environment", "environment", "question text"),
        ("generic event_type", "event_type", "system"),
        ("generic feature_area", "feature_area", "storage"),
        ("missing internal_account", "internal_account", None),
        ("conversation id set", "conversation_id", "conversation-raw-id"),
        ("amount as status", "status", "RD$5,000"),
        ("amount in usage", "usage", {"amount": "RD$5,000"}),
        ("backdated timestamp", "occurred_at", datetime(2020, 1, 1, tzinfo=timezone.utc)),
        (
            "future timestamp",
            "occurred_at",
            datetime.now(timezone.utc) + timedelta(days=1),
        ),
        ("naive timestamp", "occurred_at", datetime.now()),
        (
            "non-UTC timestamp",
            "occurred_at",
            datetime.now(timezone(timedelta(hours=-4))),
        ),
    ):
        yield label, registry_built.model_copy(update={field: value})
    yield "free text as the distinct id", build_analytics_envelope(
        CardSaved(calculator="time_value"),
        user_id="account-raw-id",
        internal_account=False,
    ).model_copy(update={"actor_hash": "person@example.com"})


@pytest.mark.parametrize(
    ("case", "envelope"),
    list(_forged_envelopes()),
    ids=[case for case, _ in _forged_envelopes()],
)
def test_an_envelope_the_registry_did_not_build_is_suppressed(
    posthog_posts: list[dict[str, Any]],
    case: str,
    envelope,
) -> None:
    result = capture_event(envelope)

    assert result.status == "suppressed", case
    assert result.reason == "not_an_analytics_event"
    assert posthog_posts == []
    with pytest.raises(ValueError):
        posthog_event_payload(envelope, api_key="ph_project_token")


# ── Clean break: every old emit path now stops before PostHog ────────────────


def _guest_context():
    now = datetime.now(timezone.utc)
    return guest_account_context(
        GuestWorkspace(
            user_id="00000000-0000-0000-0000-000000000091",
            conversation_id="conversation-1",
            status="active",
            created_at=now,
            expires_at=now + timedelta(days=7),
            claimed_by=None,
            claimed_at=None,
            updated_at=now,
        ),
        visitor_key="visitor-1",
    )


def _drive_retired_registries() -> None:
    for kind in _PRODUCT_EVENT_MAP:
        capture_product_event(kind, user_id="account-raw-id", status="completed")
    for kind in GUEST_FUNNEL_EVENT_MAP:
        capture_guest_funnel_event(kind, user_id="guest-raw-id")
        emit_verified_guest_funnel_event(
            kind, user_id="guest-raw-id", visitor_key=f"visitor-{kind}"
        )


def _drive_guest_cleanup() -> None:
    class _Gateway:
        def claim_expired_guest_workspaces(self, *, limit: int, dry_run: bool):
            return [
                {
                    "user_id": "guest-raw-id",
                    "auth_deleted": True,
                    "cleanup_reason": "expired_workspace",
                }
            ]

        def purge_expired_visitor_usage(self, *, before=None) -> int:
            return 0

        def purge_expired_guest_funnel_milestones(self, *, before=None) -> int:
            return 0

    cleanup_expired_guest_workspaces(_Gateway(), limit=10, dry_run=False)


def _drive_http_surfaces(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setattr(api_state, "supabase_gateway", None)
    monkeypatch.setenv("CUADRAO_EVIDENCE_RECEIPT_SHARING_ENABLED", "true")
    with TestClient(app) as client:
        for stage in ("viewed", "try_argus"):
            response = client.post("/api/v1/public/receipt-funnel", json={"stage": stage})
            assert response.status_code == 204
        retired = client.post(
            "/api/v1/analytics/guest-events",
            json={
                "event": "conversion_prompt_shown",
                "language": "en",
                "surface": "conversion_modal",
                "conversion_reason": "save_decision",
                "terminal_outcome": "shown",
            },
        )
        assert retired.status_code in (404, 405)
        feedback = client.post(
            "/api/v1/feedback",
            json={"type": "general", "message": "Clean break check"},
        )
        assert feedback.status_code == 200, feedback.text
        assert client.get("/api/v1/search", params={"q": "AAPL"}).status_code == 200


@pytest.mark.parametrize(
    "drive",
    [
        _drive_retired_registries,
        _drive_guest_cleanup,
        _drive_http_surfaces,
    ],
    ids=lambda drive: drive.__name__.removeprefix("_drive_"),
)
def test_removed_events_do_not_reach_posthog(
    posthog_posts: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    drive,
) -> None:
    if drive is _drive_http_surfaces:
        drive(monkeypatch)
    else:
        drive()

    assert posthog_posts == []


def test_shared_cohort_fixture_matches_when_present() -> None:
    """0C-9 adds the shared fixture; once it exists it must agree with this type."""
    fixture = FIXTURES / "invite_cohort_codes.json"
    if not fixture.exists():
        pytest.skip("invite cohort fixture arrives with SPEC 0 package 0C-9")
    codes = json.loads(fixture.read_text(encoding="utf-8"))
    for code in codes["accepted"]:
        _event("landing_viewed", cohort=code)
    for code in codes["rejected"]:
        with pytest.raises(ValidationError):
            _event("landing_viewed", cohort=code)
