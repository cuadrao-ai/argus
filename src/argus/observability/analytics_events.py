from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import ConfigDict, ValidationError

from argus.domain.business.analytics_events import BUSINESS_EVENT_MODELS
from argus.observability.analytics_event_base import AnalyticsEvent
from argus.observability.envelope import (
    ArgusEventEnvelope,
    EventCaptureResult,
    _default_environment,
    capture_event,
)
from argus.observability.product_events import actor_hash_for_user

ANALYTICS_SCHEMA_VERSION = "argus_analytics_event/v1"

# ``distinct_id`` is always ``actor_hash_for_user()``.
_ACTOR_HASH = re.compile(r"^argus_actor_[0-9a-f]{32}$")

# An analytics envelope is sent right after it is built. Its timestamp is the
# build time, so one far from now was not stamped by the registry.
_MAX_ENVELOPE_AGE = timedelta(minutes=5)
_MAX_CLOCK_SKEW = timedelta(seconds=5)

ANALYTICS_EVENT_MODELS: dict[str, type[AnalyticsEvent]] = {
    model.event_name: model for model in BUSINESS_EVENT_MODELS
}

# Sent with every event besides the model's own fields (SPEC 0, 0.5).
TECHNICAL_PROPERTIES: frozenset[str] = frozenset(
    {
        "$process_person_profile",
        "environment",
        "internal_account",
        "schema_version",
        "event_id",
    }
)


class AnalyticsEnvelope(ArgusEventEnvelope):
    """The only envelope type that can carry an analytics event.

    The generic ``ArgusEventEnvelope`` forbids extra fields, so it cannot hold
    ``analytics_event`` at all. This type is built only by
    ``build_analytics_envelope()`` and is frozen, and the sink accepts no other
    type.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    analytics_event: AnalyticsEvent
    internal_account: bool


def build_analytics_envelope(
    event: AnalyticsEvent,
    *,
    user_id: str,
    internal_account: bool,
) -> ArgusEventEnvelope:
    if ANALYTICS_EVENT_MODELS.get(event.event_name) is not type(event):
        raise TypeError(f"{type(event).__name__} is not a registered analytics event")
    actor_hash = actor_hash_for_user(user_id)
    if actor_hash is None:
        raise ValueError("an analytics event needs the user id it is about")
    return AnalyticsEnvelope(
        schema_version=ANALYTICS_SCHEMA_VERSION,
        event_type="analytics",
        event_action="completed",
        feature_area="product_analytics",
        analytics_event=event,
        internal_account=internal_account,
        actor_hash=actor_hash,
        attributes={},
    )


# Envelope fields ``build_analytics_envelope()`` sets. Every other envelope
# field must still hold its default on an analytics envelope.
_REGISTRY_SET_FIELDS = frozenset(
    {
        "schema_version",
        "event_id",
        "occurred_at",
        "environment",
        "event_type",
        "event_action",
        "feature_area",
        "actor_hash",
        "attributes",
        "analytics_event",
        "internal_account",
    }
)


def _is_uuid(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(uuid.UUID(value)) == value
    except ValueError:
        return False


def _has_registry_shape(envelope: AnalyticsEnvelope) -> bool:
    """Every technical field is exactly what ``build_analytics_envelope()`` sets.

    Technical properties are sent next to the event's own, so a free-text
    ``schema_version``, ``event_id`` or ``environment`` would leave the app as
    surely as a free-text event property.
    """
    if (
        envelope.schema_version != ANALYTICS_SCHEMA_VERSION
        or envelope.event_type != "analytics"
        or envelope.event_action != "completed"
        or envelope.feature_area != "product_analytics"
        or envelope.environment != _default_environment()
        or not _is_uuid(envelope.event_id)
        or not isinstance(envelope.internal_account, bool)
        or not _ACTOR_HASH.fullmatch(envelope.actor_hash or "")
    ):
        return False
    if not _stamped_now(envelope.occurred_at):
        return False
    return all(
        getattr(envelope, name) == field.get_default(call_default_factory=False)
        for name, field in ArgusEventEnvelope.model_fields.items()
        if name not in _REGISTRY_SET_FIELDS
    )


def _stamped_now(occurred_at: object) -> bool:
    """An aware UTC build time, not backdated and not in the future."""
    if not isinstance(occurred_at, datetime) or occurred_at.utcoffset() != timedelta(0):
        return False
    now = datetime.now(timezone.utc)
    return now - _MAX_ENVELOPE_AGE <= occurred_at <= now + _MAX_CLOCK_SKEW


def registered_payload(
    envelope: ArgusEventEnvelope,
) -> tuple[str, dict[str, Any]] | None:
    """The PostHog name and properties, only for a registry-built event.

    The sink calls this for every envelope and sends nothing when it returns
    None. The envelope must be an ``AnalyticsEnvelope`` with exactly the shape
    ``build_analytics_envelope()`` gives it, technical fields and timestamp
    included, and carry an instance of exactly one registered model. That instance is validated again, because
    ``model_construct()`` or a subclass could otherwise smuggle unchecked values
    past the model. ``distinct_id`` must be an actor hash, and the envelope
    carries no extra attributes.
    """
    if type(envelope) is not AnalyticsEnvelope or not _has_registry_shape(envelope):
        return None
    event = envelope.analytics_event
    if not isinstance(event, AnalyticsEvent):
        return None
    model = ANALYTICS_EVENT_MODELS.get(event.event_name)
    if model is None or type(event) is not model:
        return None
    try:
        checked = model.model_validate(
            {name: getattr(event, name, None) for name in model.model_fields}
        )
    except ValidationError:
        return None
    properties = checked.model_dump(mode="json", exclude_none=True)
    if envelope.attributes:
        return None
    return model.event_name, properties


def capture_analytics_event(
    event: AnalyticsEvent,
    *,
    user_id: str,
    internal_account: bool,
) -> EventCaptureResult:
    """Send one registered event under its own name."""
    return capture_event(
        build_analytics_envelope(
            event,
            user_id=user_id,
            internal_account=internal_account,
        )
    )
