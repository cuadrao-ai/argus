"""Send the Business pilot's analytics events, after the work they describe.

Every sender returns at once. Unless the envelope says capture is on (a project
token and a region), it does nothing, not even a database read; with capture
on, the event is built and sent off the caller's thread, and any failure is
logged once and dropped, so analytics never delays or fails a request or a read.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, get_args
from uuid import UUID

from argus.domain.business.analytics_events import (
    BusinessDocumentNeedsReview,
    BusinessDocumentRead,
    BusinessDocumentReceived,
    BusinessEvent,
    BusinessRecordApproved,
    BusinessRecordRecorded,
    BusinessRecordsExported,
    FiscalField,
    ReceivedChannel,
    RecordField,
    business_hash_for_id,
)
from argus.domain.business.bandeja_group import BandejaReason
from argus.domain.business.contracts.facts import Amount, BusinessFacts, FiscalFacts
from argus.domain.business.document_type import DocumentType, direction
from argus.domain.business.receipts import READ_REFUSAL_ATTENTION, failure_attention
from argus.domain.ingestion.documents.config import SOURCE_MEDIA_TYPES
from argus.observability.analytics_events import capture_analytics_event
from argus.observability.envelope import live_analytics_sink_enabled, send_later

if TYPE_CHECKING:
    from argus.domain.business.actions.service import BusinessActions
    from argus.domain.business.authority import ActionContext

# No Business account is marked internal yet; staging is the pilot's project.
INTERNAL_ACCOUNT = False
RECORD_FIELDS: tuple[RecordField, ...] = get_args(RecordField)
FISCAL_FIELDS: frozenset[str] = frozenset(get_args(FiscalField))
#: The record fields the facts model types as an ``Amount``: the only ones
#: whose written form may differ while the value is the same.
MONEY_FIELDS: frozenset[str] = frozenset(
    name
    for model in (BusinessFacts, FiscalFacts)
    for name, field in model.model_fields.items()
    if get_args(field.annotation) == (Amount,)
)
_SINGLE_PAGE = frozenset({"image/png", "image/jpeg"})
_SIZE_BUCKETS = (
    (100_000, "under_100kb"),
    (1_000_000, "100kb_to_1mb"),
    (5_000_000, "1mb_to_5mb"),
)
_MICRO = Decimal(1_000_000)


def _emit(user_id: str, build: Callable[[], Iterable[BusinessEvent]]) -> None:
    if not live_analytics_sink_enabled():
        return

    def send() -> None:
        for event in build():
            capture_analytics_event(
                event, user_id=user_id, internal_account=INTERNAL_ACCOUNT
            )

    send_later(send)


def size_bucket(size_bytes: int) -> str:
    return next(
        (name for limit, name in _SIZE_BUCKETS if size_bytes < limit), "5mb_or_more"
    )


def document_received(
    *,
    channel: ReceivedChannel,
    business_id: str,
    user_id: str,
    media_type: str | None = None,
    size_bytes: int | None = None,
) -> None:
    """A new document reached the Business. A typed note has no file."""

    def build() -> list[BusinessEvent]:
        return [
            BusinessDocumentReceived(
                business_hash=business_hash_for_id(business_id),
                channel=channel,
                file_type=SOURCE_MEDIA_TYPES.get(media_type or ""),
                page_count=1 if media_type in _SINGLE_PAGE else None,
                size_bucket=size_bucket(size_bytes) if size_bytes is not None else None,
            )
        ]

    _emit(user_id, build)


def read_usage(metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Tier, tokens and cost of one read, summed exactly from its route
    receipts. Tokens or cost are absent when any receipt lacks them."""

    receipts = [
        receipt
        for receipt in metadata.get("route_receipts") or ()
        if isinstance(receipt, Mapping)
    ]
    if not receipts:
        return {}
    usage: dict[str, Any] = {"model_tier": receipts[-1].get("tier")}
    tokens = [receipt.get("token_usage") for receipt in receipts]
    if all(isinstance(item, Mapping) for item in tokens):
        for key, name in (
            ("prompt_tokens", "input_tokens"),
            ("completion_tokens", "output_tokens"),
        ):
            counts = [item.get(key) for item in tokens]
            if all(
                isinstance(count, int) and not isinstance(count, bool) for count in counts
            ):
                usage[name] = sum(counts)
    costs = [receipt.get("usage_cost_usd") for receipt in receipts]
    if all(
        isinstance(cost, int | float) and not isinstance(cost, bool) for cost in costs
    ):
        try:
            total = sum((Decimal(str(cost)) for cost in costs), Decimal(0))
        except InvalidOperation:
            return usage
        usage["cost_micro_usd"] = int(
            (total * _MICRO).to_integral_value(rounding=ROUND_HALF_EVEN)
        )
    return usage


def read_outcome(code: str | None, issue_code: str | None) -> tuple[str, str | None]:
    """The read's result and, unless it read cleanly, the owner's reason."""

    if code is None:
        if issue_code is None:
            return "read", None
        return "unsure", failure_attention(issue_code) or "check_details"
    if code in READ_REFUSAL_ATTENTION:
        return "unsure", failure_attention(code)
    return "failed", failure_attention(code) or "other"


def document_read(
    *,
    business_id: str,
    user_id: str,
    metadata: Mapping[str, Any],
    latency_ms: int,
    code: str | None = None,
    issue_code: str | None = None,
) -> None:
    """One read that reached the model, however it ended."""

    def build() -> list[BusinessEvent]:
        result, reason = read_outcome(code, issue_code)
        events: list[BusinessEvent] = [
            BusinessDocumentRead(
                business_hash=business_hash_for_id(business_id),
                result=result,
                failure_reason=reason,
                latency_ms=latency_ms,
                **read_usage(metadata),
            )
        ]
        if result == "unsure" and code is not None and reason is not None:
            events.append(
                BusinessDocumentNeedsReview(
                    business_hash=business_hash_for_id(business_id),
                    reason_codes=(reason,),
                )
            )
        return events

    _emit(user_id, build)


def document_needs_review(
    *,
    business_id: str,
    user_id: str,
    reasons: Callable[[], Sequence[BandejaReason]],
) -> None:
    """A read became a draft a person must finish; ``reasons`` reads why."""

    def build() -> list[BusinessEvent]:
        found = tuple(reasons())
        if not found:
            return []
        return [
            BusinessDocumentNeedsReview(
                business_hash=business_hash_for_id(business_id), reason_codes=found
            )
        ]

    _emit(user_id, build)


def _fact(name: str, raw: object) -> tuple[object, object]:
    if not isinstance(raw, Mapping):
        return ("unknown", None)
    value = raw.get("value")
    if name in MONEY_FIELDS and isinstance(value, str):
        try:
            number = Decimal(value)
        except InvalidOperation:
            number = None
        if number is not None and number.is_finite():
            value = number
    return (raw.get("state", "unknown"), value)


def approval_field_edits(
    read: Mapping[str, Any], approved: Mapping[str, Any]
) -> tuple[tuple[RecordField, ...], tuple[RecordField, ...]]:
    """Return the names of fields filled and fields corrected, in that order."""

    def fact(facts: Mapping[str, Any], name: str) -> tuple[object, object]:
        holder = (facts.get("fiscal") or {}) if name in FISCAL_FIELDS else facts
        return _fact(name, holder.get(name))

    filled: list[RecordField] = []
    corrected: list[RecordField] = []
    for name in RECORD_FIELDS:
        before = fact(read, name)
        after = fact(approved, name)
        if before[0] == "known":
            if before != after:
                corrected.append(name)
        elif after[0] == "known":
            filled.append(name)
    return tuple(filled), tuple(corrected)


@dataclass(frozen=True)
class ApprovalFacts:
    read_facts: Mapping[str, Any] | None
    received_at: datetime | None
    document_type: DocumentType


def read_approval(
    service: BusinessActions, context: ActionContext, draft_id: UUID, version: int
) -> tuple[ApprovalFacts, Mapping[str, Any]]:
    """The read's facts, the approved version's facts, the first arrival and
    the draft's type, read after the approval committed."""

    from argus.domain.business.transactions import transaction

    with transaction(service.authority, context) as tx:
        revisions = tx.rows(
            "select actor->>'actor_kind' as actor_kind,after_facts"
            " from public.business_draft_revisions"
            " where space_id=%s and draft_id=%s and version<=%s order by version",
            (context.actor.space_id, draft_id, version),
        )
        arrived = tx.rows(
            "select min(s.received_at) as received_at from public.business_draft_sources l"
            " join public.business_sources s on s.id=l.source_id and s.space_id=l.space_id"
            " where l.draft_id=%s and l.space_id=%s",
            (draft_id, context.actor.space_id),
        )
        event = tx.imports.event(str(draft_id))
    reads = [row["after_facts"] for row in revisions if row["actor_kind"] == "extractor"]
    business = event.resolution.get("business") or {}
    facts = ApprovalFacts(
        read_facts=reads[-1] if reads else None,
        received_at=arrived[0]["received_at"] if arrived else None,
        document_type=business.get("document_type") or "recibo",
    )
    return facts, revisions[-1]["after_facts"] if revisions else {}


def approval_events(
    business_id: str,
    facts: ApprovalFacts,
    approved: Mapping[str, Any],
    approved_at: datetime,
) -> list[BusinessEvent]:
    business_hash = business_hash_for_id(business_id)
    filled, corrected = (
        approval_field_edits(facts.read_facts, approved)
        if facts.read_facts is not None
        else (None, None)
    )
    seconds = (
        max(0, int((approved_at - facts.received_at).total_seconds()))
        if facts.received_at is not None
        else None
    )
    family = direction(facts.document_type)
    return [
        BusinessRecordApproved(
            business_hash=business_hash,
            filled_fields=filled,
            filled_count=len(filled) if filled is not None else None,
            corrected_fields=corrected,
            corrected_count=len(corrected) if corrected is not None else None,
            seconds_to_approve=seconds,
        ),
        BusinessRecordRecorded(
            business_hash=business_hash,
            direction="venta"
            if family is not None and family.family == "sale"
            else "compra",
            document_type=facts.document_type,
        ),
    ]


def record_approved(
    service: BusinessActions,
    context: ActionContext,
    draft_id: UUID,
    version: int,
    approved_at: datetime,
) -> None:
    """A person's approval recorded the draft; called after it committed, by
    the one request that settled its receipt."""

    business_id = str(context.actor.space_id)

    def build() -> list[BusinessEvent]:
        facts, approved = read_approval(service, context, draft_id, version)
        return approval_events(business_id, facts, approved, approved_at)

    _emit(str(context.actor.actor_id), build)


def records_exported(
    *, business_id: str, user_id: str, file_format: str, mode: str, row_count: int
) -> None:
    def build() -> list[BusinessEvent]:
        return [
            BusinessRecordsExported(
                business_hash=business_hash_for_id(business_id),
                format="csv" if file_format == "csv" else "excel",
                scope="dgii" if mode == "dgii" else "lo_que_ves",
                row_count=row_count,
            )
        ]

    _emit(user_id, build)
