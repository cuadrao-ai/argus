"""The closed analytics registry.

The product analytics sink receives only the Business pilot's events, each
under its own name, each with exactly its listed properties. Nothing else
reaches it.
"""

from __future__ import annotations

import json
import types
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal, Union, get_args, get_origin

import httpx
import pytest
from argus.api import state as api_state
from argus.api.guest_access import guest_account_context
from argus.api.guest_observability import emit_verified_guest_funnel_event
from argus.api.main import app
from argus.domain.business.analytics_events import (
    BUSINESS_EVENT_MODELS,
    BUSINESS_HASH_PATTERN,
    BusinessDocumentReceived,
    BusinessHash,
    FileType,
    RecordField,
    business_hash_for_id,
)
from argus.domain.business.contracts.facts import BusinessFacts, FiscalFacts
from argus.domain.guest_cleanup import cleanup_expired_guest_workspaces
from argus.domain.guest_workspaces import GuestWorkspace
from argus.domain.ingestion.documents.config import SOURCE_MEDIA_TYPES
from argus.observability.analytics_events import (
    ANALYTICS_EVENT_MODELS,
    TECHNICAL_PROPERTIES,
    AnalyticsEvent,
    build_analytics_envelope,
    capture_analytics_event,
)
from argus.observability.envelope import (
    SERVER_DISTINCT_ID,
    build_event_envelope,
    capture_event,
    exception_payload,
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

BUSINESS_HASH = business_hash_for_id("business-raw-id")
BUSINESS_EVENT_NAMES = {
    "business_document_received",
    "business_document_read",
    "business_document_needs_review",
    "business_record_approved",
    "business_record_recorded",
    "business_records_exported",
}

# One valid instance of every event, with every optional property set.
VALID_PROPERTIES: dict[str, dict[str, Any]] = {
    "business_document_received": {
        "business_hash": BUSINESS_HASH,
        "channel": "whatsapp",
        "file_type": "jpg",
        "page_count": 1,
        "size_bucket": "100kb_to_1mb",
    },
    "business_document_read": {
        "business_hash": BUSINESS_HASH,
        "result": "unsure",
        "failure_reason": "check_details",
        "latency_ms": 4200,
        "model_tier": "vision",
        "input_tokens": 1800,
        "output_tokens": 350,
        "cost_micro_usd": 223,
    },
    "business_document_needs_review": {
        "business_hash": BUSINESS_HASH,
        "reason_codes": ("missing_rnc", "missing_itbis"),
    },
    "business_record_approved": {
        "business_hash": BUSINESS_HASH,
        "filled_fields": ("amount",),
        "filled_count": 1,
        "corrected_fields": ("rnc",),
        "corrected_count": 1,
        "seconds_to_approve": 5400,
    },
    "business_record_recorded": {
        "business_hash": BUSINESS_HASH,
        "direction": "compra",
        "document_type": "recibo",
    },
    "business_records_exported": {
        "business_hash": BUSINESS_HASH,
        "format": "excel",
        "scope": "dgii",
        "row_count": 42,
    },
}
REGISTERED_EVENT_NAMES = BUSINESS_EVENT_NAMES

MONEY_FORMATTED_VALUES = ("RD$5,000", "US$5,000.00", "5000.00", "$5,000", 5000.0)


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


def _sample_event() -> BusinessDocumentReceived:
    return BusinessDocumentReceived(
        business_hash=BUSINESS_HASH,
        channel="upload",
    )


def test_registry_is_exactly_the_business_events() -> None:
    assert set(ANALYTICS_EVENT_MODELS) == REGISTERED_EVENT_NAMES
    assert set(VALID_PROPERTIES) == REGISTERED_EVENT_NAMES
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


def _unwrapped(field: FieldInfo) -> tuple[list[Any], list[Any]]:
    """The field's types without ``None`` or ``Annotated``, and every
    constraint, whether pydantic hoisted it or left it inside an optional."""
    parts, metadata = [], list(field.metadata)
    for part in _optional_parts(field.annotation):
        if get_origin(part) is Annotated:
            part, *extra = get_args(part)
            for item in extra:
                metadata.extend(item.metadata if isinstance(item, FieldInfo) else [item])
        parts.append(part)
    return parts, metadata


def _has_bounds(metadata: list[Any]) -> bool:
    lower = any(hasattr(item, "ge") or hasattr(item, "gt") for item in metadata)
    upper = any(hasattr(item, "le") or hasattr(item, "lt") for item in metadata)
    return lower and upper


def _literal_tuple(parts: list[Any], metadata: list[Any]) -> bool:
    """``tuple[Literal[...], ...]`` with a length bound."""
    if len(parts) != 1 or get_origin(parts[0]) is not tuple:
        return False
    item, ellipsis = get_args(parts[0])
    has_bound = any(getattr(meta, "max_length", None) for meta in metadata)
    return ellipsis is Ellipsis and _literal_values(item) is not None and has_bound


def test_every_property_is_literal_bool_or_bounded_int() -> None:
    """Nothing in any event can hold free text or an amount."""
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
            bare, metadata = _unwrapped(field)
            if parts == [bool]:
                continue
            if bare == [int] and _has_bounds(metadata):
                continue
            if field_name == "business_hash" and bare == [str] and [
                getattr(item, "pattern", None) for item in metadata
            ] == [BUSINESS_HASH_PATTERN]:
                continue
            if _literal_tuple(bare, metadata):
                continue
            offenders.append(where)
    assert offenders == []
    for model in BUSINESS_EVENT_MODELS:
        assert ANALYTICS_EVENT_MODELS[model.event_name] is model
        assert model.model_fields["business_hash"].is_required()
    base, *constraints = get_args(BusinessHash)
    assert base is str
    assert [getattr(item, "pattern", None) for item in constraints] == [
        BUSINESS_HASH_PATTERN
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
    personal = ("person@example.com", "Iris", "hola", True, "1", 1.0)
    business = ("101010101", "B0100000001", "RD$3,450.00", ("101010101",), [])
    for name, model in ANALYTICS_EVENT_MODELS.items():
        for field_name in model.model_fields:
            for value in personal + business:
                if VALID_PROPERTIES[name].get(field_name) == value:
                    continue
                with pytest.raises(ValidationError):
                    _event(name, **{field_name: value})


def test_bounded_ints_reject_out_of_range_values() -> None:
    with pytest.raises(ValidationError):
        _event("business_records_exported", row_count=-1)
    with pytest.raises(ValidationError):
        _event("business_records_exported", row_count=1_000_001)
    with pytest.raises(ValidationError):
        _event("business_document_read", latency_ms=-1)


def test_payload_has_only_technical_and_event_properties(
    posthog_posts: list[dict[str, Any]],
) -> None:
    for name in sorted(REGISTERED_EVENT_NAMES):
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
            assert properties[key] == (list(value) if isinstance(value, tuple) else value)
        assert "account-raw-id" not in json.dumps(body)


def test_unset_optional_properties_are_not_sent(
    posthog_posts: list[dict[str, Any]],
) -> None:
    capture_analytics_event(
        BusinessDocumentReceived(business_hash=BUSINESS_HASH, channel="note"),
        user_id="account-raw-id",
        internal_account=False,
    )

    [body] = posthog_posts
    assert set(body["properties"]) == TECHNICAL_PROPERTIES | {"business_hash", "channel"}


def test_no_registered_event_carries_a_guest_id_hash(
    posthog_posts: list[dict[str, Any]],
) -> None:
    for name in sorted(REGISTERED_EVENT_NAMES):
        with pytest.raises(ValueError):
            capture_analytics_event(
                _event(name),
                user_id="account-raw-id",
                guest_user_id="guest-raw-id",
                internal_account=False,
            )
    assert posthog_posts == []


def test_an_unregistered_event_model_is_refused(
    posthog_posts: list[dict[str, Any]],
) -> None:
    class Unlisted(AnalyticsEvent):
        event_name = "business_document_received"

    with pytest.raises(TypeError):
        capture_analytics_event(Unlisted(), user_id="account-raw-id", internal_account=False)
    with pytest.raises(ValueError):
        capture_analytics_event(
            _event("business_document_received"), user_id=" ", internal_account=False
        )
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
                "analytics_event": _sample_event(),
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
                "analytics_event": _sample_event(),
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
        _sample_event(),
        user_id="account-raw-id",
        internal_account=False,
    ).model_copy(
        update={"analytics_event": BusinessDocumentReceived.model_construct(
            business_hash=BUSINESS_HASH, channel="RD$5,000"
        )}
    )

    class Sneaky(BusinessDocumentReceived):
        amount: str = "RD$5,000"

    yield "subclass of a registered model", build_analytics_envelope(
        _sample_event(),
        user_id="account-raw-id",
        internal_account=False,
    ).model_copy(
        update={
            "analytics_event": Sneaky(business_hash=BUSINESS_HASH, channel="upload")
        }
    )
    yield "extra attribute next to a registered event", build_analytics_envelope(
        _sample_event(),
        user_id="account-raw-id",
        internal_account=False,
    ).model_copy(update={"attributes": {"amount": "RD$5,000"}})
    yield "guest hash on an event that does not carry one", build_analytics_envelope(
        _sample_event(),
        user_id="account-raw-id",
        internal_account=False,
    ).model_copy(update={"attributes": {"guest_id_hash": valid_actor}})
    registry_built = build_analytics_envelope(
        _sample_event(),
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
        _sample_event(),
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


def test_business_vocabularies_come_from_their_owners() -> None:
    """One owner each: the record fields are the facts' own fields, and the
    file types are the extensions the document intake accepts."""
    record_fields = set(get_args(RecordField))
    assert record_fields == (set(BusinessFacts.model_fields) - {"fiscal"}) | set(
        FiscalFacts.model_fields
    )
    assert set(get_args(FileType)) == set(SOURCE_MEDIA_TYPES.values())


def test_the_business_hash_is_stable_one_way_and_distinct_from_the_actor_hash() -> None:
    assert business_hash_for_id("space-1") == business_hash_for_id("space-1")
    assert business_hash_for_id("space-1") != business_hash_for_id("space-2")
    assert "space-1" not in business_hash_for_id("space-1")
    assert business_hash_for_id("space-1") != actor_hash_for_user("space-1")


EXCEPTION_PAYLOAD_KEYS = {"api_key", "event", "distinct_id", "properties"}
EXCEPTION_FRAME_KEYS = {"module", "function", "lineno"}


def _raise_with_a_customer_value() -> None:
    rnc = "101010101"  # a local variable holding a customer value
    raise ValueError(f"RNC {rnc}")


@pytest.mark.parametrize(
    ("where", "named"), [({"route": "/business/receipts"}, "route"), ({"job": "document_preparation"}, "job")]
)
def test_the_exception_payload_carries_only_its_allowed_fields(
    where: dict[str, str], named: str
) -> None:
    try:
        _raise_with_a_customer_value()
    except ValueError as error:
        payload = exception_payload(
            error,
            api_key="ph_project_token",
            actor_hash=actor_hash_for_user("account-raw-id"),
            **where,
        )

    assert set(payload) == EXCEPTION_PAYLOAD_KEYS
    assert payload["event"] == "$exception"
    assert payload["distinct_id"] == actor_hash_for_user("account-raw-id")
    properties = payload["properties"]
    assert set(properties) == {"$exception_list", named, "$process_person_profile"}
    assert properties[named] == where[named]
    assert properties["$process_person_profile"] is False
    [entry] = properties["$exception_list"]
    assert set(entry) == {"type", "stacktrace"}
    assert entry["type"] == "ValueError"
    assert set(entry["stacktrace"]) == {"type", "frames"}
    frames = entry["stacktrace"]["frames"]
    assert frames and all(set(frame) == EXCEPTION_FRAME_KEYS for frame in frames)
    assert frames[-1]["function"] == "_raise_with_a_customer_value"
    assert frames[-1]["module"] == __name__
    sent = json.dumps(payload)
    assert "101010101" not in sent
    assert "RNC" not in sent
    assert "account-raw-id" not in sent


def test_an_exception_with_no_actor_is_the_server_s() -> None:
    try:
        raise RuntimeError("boom")
    except RuntimeError as error:
        payload = exception_payload(error, api_key="k", job="document_read_pull")
    assert payload["distinct_id"] == SERVER_DISTINCT_ID
