"""Plan atomic activity revisions over the shared financial projection."""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any, NoReturn
from uuid import uuid4
from zoneinfo import ZoneInfo

from argus.domain.backtest_admission import canonical_hash
from argus.domain.recording.currency import (
    currency_exponent,
    format_minor_units,
    parse_minor_units,
)
from argus.domain.recording.errors import (
    AccountNotFound,
    RecordingInputError,
    StaleVersion,
)
from argus.domain.recording.loop import (
    Coverage,
    ExpenseRecord,
    ExpenseRevision,
    coverage_skip,
    observations,
    residuals,
    validate_monotonic,
)
from argus.domain.recording.loop_schemas import CATEGORY_IDS
from argus.domain.recording.loop_service import _stamp, _view
from argus.domain.recording.loop_storage import Mutation, apply
from argus.domain.recording.money_reads import activity, current_activities
from argus.domain.recording.money_schemas import (
    DESTINATION_ELIGIBILITY,
    ELIGIBILITY,
    SOURCE_IDS,
    MoneyRequest,
)
from argus.domain.recording.money_transfers import transfer_amounts
from argus.domain.recording.records import _normalize_reason
from argus.domain.recording.repository import StoredAccount


@dataclass(frozen=True)
class MoneyPlan:
    activity_id: str
    revision: int
    mutations: dict[str, Mutation]
    affected: tuple[str, ...]
    preview: dict[str, Any]


def problem(code: str, text: str) -> NoReturn:
    raise RecordingInputError(code, text)


def identity(request: MoneyRequest, activity_id: str | None) -> str:
    return canonical_hash(
        {
            "activity_id": activity_id,
            "request": request.model_dump(mode="json", exclude={"preview_token"}),
        }
    )


def request_identity(request: MoneyRequest, activity_id: str | None) -> str:
    value = identity(request, activity_id)
    if (
        activity_id
        and request.kind == "refund"
        and "purchase_activity_id" not in request.model_fields_set
    ):
        return canonical_hash({"identity": value, "purchase_link_omitted": True})
    return value


def selected(request: MoneyRequest) -> dict[str, str]:
    pair = request.kind in DESTINATION_ELIGIBILITY
    if pair:
        if (
            request.account_id
            or not request.source_account_id
            or not request.destination_account_id
            or request.source_account_id == request.destination_account_id
        ):
            problem("accounts_invalid", "Choose two distinct accounts.")
        return {
            request.source_account_id: "source",
            request.destination_account_id: "destination",
        }
    if (
        not request.account_id
        or request.source_account_id
        or request.destination_account_id
    ):
        problem("accounts_invalid", "Choose one account for this activity.")
    return {request.account_id: "single"}


def plan(
    accounts: list[StoredAccount],
    request: MoneyRequest,
    activity_id: str | None,
    now: datetime,
    *,
    legacy: bool = False,
    actor_id: str | None = None,
    confirming: bool = False,
) -> MoneyPlan:
    by_id = {s.account.id: s for s in accounts}
    old = activity(accounts, activity_id) if activity_id else None
    if (
        old
        and old["kind"] == "refund"
        and "purchase_activity_id" not in request.model_fields_set
    ):
        request = request.model_copy(
            update={"purchase_activity_id": old["purchase_activity_id"]}
        )
    if request.expected_revision != (old["revision"] if old else None):
        raise StaleVersion()
    if old and old["kind"] != request.kind:
        problem(
            "kind_immutable",
            "Correct the existing activity type without changing its kind.",
        )
    reason = _normalize_reason(request.reason, required=old is not None)
    stamp = _stamp(request.occurred_at, request.time_zone, now)
    today = now.astimezone(ZoneInfo(request.time_zone)).date()
    # The server decides the entry day; only a confirm carries back the previewed day.
    entered_on = (request.entered_on if confirming else None) or today
    if entered_on not in (today, today - timedelta(days=1)):
        problem("preview_required", "Review the proposed change before saving it.")
    targets = selected(request)
    existing = current_activities(accounts)
    return_original = next(
        (a for a in existing if a["activity_id"] == request.reversal_of_activity_id), None
    )
    for aid, selected_role in targets.items():
        if aid not in by_id:
            raise AccountNotFound()
        allowed = (
            (
                ("credit_card",)
                if request.kind == "card_payment"
                or return_original
                and return_original["kind"] == "card_payment"
                else ("other_debt",)
            )
            if request.kind in {"card_payment", "debt_payment", "payment_reversal"}
            and selected_role == "destination"
            else ELIGIBILITY[request.kind]
        )
        if by_id[aid].account.type not in allowed and not (
            legacy and request.kind == "expense"
        ):
            problem(
                "account_ineligible", "Choose an account that supports this activity."
            )
    currency = by_id[next(iter(targets))].account.currency
    if request.kind != "transfer" and any(
        by_id[aid].account.currency != currency for aid in targets
    ):
        problem("currency_mismatch", "Choose accounts with the same currency.")
    if request.kind != "transfer" and request.destination_amount is not None:
        problem("field_not_applicable", "A destination amount applies only to transfers.")
    pair = (
        transfer_amounts(
            request,
            by_id[request.source_account_id].account.currency,
            by_id[request.destination_account_id].account.currency,
        )
        if request.kind == "transfer"
        else None
    )
    amount = pair.source_minor if pair else parse_minor_units(request.amount, currency)
    if amount <= 0:
        problem("amount_positive_required", "Enter a positive amount.")
    from argus.domain.recording.payments import validate as payment_validate

    if request.kind == "debt_payment" and request.category_id is None:
        request = request.model_copy(update={"category_id": "interest_fees"})
    if return_original and request.category_id is None:
        request = request.model_copy(
            update={"category_id": return_original["category_id"]}
        )
    payment = payment_validate(request, currency, amount, old, existing, stamp, targets)
    if return_original:
        if (
            request.category_id is not None
            and request.category_id != return_original["category_id"]
        ):
            problem(
                "payment_return_category",
                "A payment return uses the original cost category.",
            )
        request = request.model_copy(
            update={"category_id": return_original["category_id"]}
        )
    if request.category_id is not None and request.category_id not in CATEGORY_IDS:
        problem("category_unknown", "Choose an available category.")
    if request.source_id is not None and request.source_id not in SOURCE_IDS:
        problem("source_unknown", "Choose an available income source.")
    if (
        request.kind not in {"expense", "refund", "debt_payment", "payment_reversal"}
        and request.category_id is not None
        or request.kind != "income"
        and request.source_id is not None
        or request.kind != "refund"
        and request.purchase_activity_id is not None
    ):
        problem(
            "field_not_applicable", "This field does not apply to the selected activity."
        )
    affected = set(targets)
    if old:
        affected.update(leg["account_id"] for leg in old["legs"])
    category, purchase_revision = request.category_id, None
    for purchase_id in {
        request.purchase_activity_id,
        old.get("purchase_activity_id") if old else None,
    } - {None}:
        assert purchase_id is not None
        purchase = activity(accounts, purchase_id)
        affected.update(leg["account_id"] for leg in purchase["legs"])
    for reference in {
        request.reversal_of_activity_id,
        old.get("reversal_of_activity_id") if old else None,
    } - {None}:
        original = activity(accounts, reference)
        affected.update(leg["account_id"] for leg in original["legs"])
    if request.purchase_activity_id:
        purchase = activity(accounts, request.purchase_activity_id)
        if purchase["kind"] != "expense" or purchase["currency"] != currency:
            problem("purchase_invalid", "Choose a purchase in the same currency.")
        if (
            stamp.astimezone(ZoneInfo(request.time_zone)).date()
            < purchase["occurred_at"].astimezone(ZoneInfo(purchase["time_zone"])).date()
        ):
            problem("refund_before_purchase", "The refund cannot precede its purchase.")
        if category is not None and category != purchase["category_id"]:
            problem(
                "refund_category_conflict", "A linked refund uses its purchase category."
            )
        category, purchase_revision = purchase["category_id"], purchase["revision"]
        refunded = sum(
            a["amount_minor"]
            for a in existing
            if a["purchase_activity_id"] == request.purchase_activity_id
            and a["activity_id"] != activity_id
        )
        if refunded + amount > purchase["amount_minor"]:
            problem(
                "refund_limit",
                "Linked refunds cannot exceed the purchase. Correct the amount or purchase link explicitly.",
            )
    if old and old["kind"] == "expense":
        refunds = [a for a in existing if a["purchase_activity_id"] == activity_id]
        if refunds and currency != old["currency"]:
            problem(
                "linked_refund_currency",
                "Unlink or correct linked refunds before changing purchase currency.",
            )
        if sum(r["amount_minor"] for r in refunds) > amount:
            problem(
                "refund_limit", "The purchase cannot be less than its linked refunds."
            )
        if refunds and category != old["category_id"]:
            problem(
                "linked_refund_category",
                "Correct or unlink linked refunds before changing the purchase category, then relink if needed.",
            )
        if any(
            stamp.astimezone(ZoneInfo(request.time_zone)).date()
            > r["occurred_at"].astimezone(ZoneInfo(r["time_zone"])).date()
            for r in refunds
        ):
            problem(
                "refund_before_purchase",
                "Correct linked refund dates before moving the purchase after them.",
            )
    for aid, version in request.expected_versions.items():
        if aid not in by_id or by_id[aid].account.version != version:
            raise StaleVersion()
    versions = {aid: by_id[aid].account.version for aid in sorted(affected)}
    reviewed = request.model_copy(
        update={
            "category_id": category,
            "expected_versions": versions,
            "preview_token": None,
            "note": (request.note or "").strip() or None,
            "reason": reason,
            "entered_on": entered_on,
        }
    )
    answers = {}
    for answer in request.coverage:
        key = (answer.account_id, answer.observation_id)
        if key in answers:
            problem("coverage_duplicate", "Answer each balance question once.")
        answers[key] = answer.included
    group_id = activity_id or str(uuid4())
    number = old["revision"] + 1 if old else 1
    mutations, effects, valid_answers = {}, [], set()
    ready = True
    for aid in sorted(affected):
        stored = by_id[aid]
        current = (
            next(
                (
                    e
                    for e in stored.expenses
                    if (e.current.activity_id or e.id) == activity_id and e.current.active
                ),
                None,
            )
            if old
            else None
        )
        role = targets.get(aid)
        questions = []
        skipped: list[dict[str, str]] = []
        candidate: StoredAccount | None = stored
        if role or current:
            rid = (
                current.id
                if current
                else (group_id if len(targets) == 1 and not old else str(uuid4()))
            )
            leg_amount = payment.leg(role) if role else 0
            if pair and role:
                leg_amount = (
                    pair.destination_minor if role == "destination" else pair.source_minor
                )
            revision = ExpenseRevision(
                (current.current.revision if current else 0) + 1,
                leg_amount,
                stamp,
                request.time_zone,
                reviewed.note,
                category,
                reason,
                actor_id if actor_id is not None else stored.account.user_id,
                now,
                request.kind,
                role if role else current.current.role if current else "single",
                bool(role),
                group_id,
                number,
                request.source_id,
                request.purchase_activity_id,
                purchase_revision,
                payment.interest if role == "source" else None,
                payment.reference,
                payment.reference_revision,
            )
            revision = replace(revision, entered_on=entered_on)
            links = []
            for anchor in observations(stored.opening, stored.checks):
                skip = coverage_skip(revision, anchor)
                if skip is not None:
                    if role:
                        skipped.append({"observation_id": anchor.id, "reason": skip})
                    continue
                key = (aid, anchor.id)
                choice = answers.get(key) if role else False
                if role:
                    valid_answers.add(key)
                    questions.append(
                        {
                            "observation_id": anchor.id,
                            "kind": anchor.kind,
                            "as_of": anchor.as_of,
                            "time_zone": anchor.time_zone,
                            "amount_minor": anchor.amount_minor,
                            "amount": format_minor_units(
                                anchor.amount_minor, stored.account.currency
                            ),
                            "included": choice,
                        }
                    )
                if choice is None:
                    ready = False
                else:
                    links.append(
                        Coverage(
                            anchor.id, anchor.revision, rid, revision.revision, choice
                        )
                    )
            revision = replace(
                revision,
                coverage_skips=tuple((i["observation_id"], i["reason"]) for i in skipped),
            )
            record = ExpenseRecord(
                rid, aid, (*current.revisions, revision) if current else (revision,)
            )
            mutation = Mutation(record, tuple(links), request.kind)
            mutations[aid] = mutation
            if all(q["included"] is not None for q in questions):
                candidate = apply(stored, mutation, now)
                if role:
                    validate_monotonic(
                        record,
                        observations(stored.opening, stored.checks),
                        candidate.coverage,
                    )
            else:
                candidate = None
        effects.append(
            {
                "account_id": aid,
                "currency": stored.account.currency,
                "currency_fraction_digits": currency_exponent(stored.account.currency),
                "before": _view(stored),
                "after": _view(candidate) if candidate else None,
                "observations": questions,
                "skipped_observations": skipped,
                "unexplained_before": residuals(
                    stored.opening, stored.checks, stored.expenses, stored.coverage
                ),
                "unexplained_after": residuals(
                    candidate.opening,
                    candidate.checks,
                    candidate.expenses,
                    candidate.coverage,
                )
                if candidate
                else None,
            }
        )
    if set(answers) - valid_answers:
        problem(
            "coverage_invalid",
            "The selected account balance does not cover this activity date.",
        )
    preview = {
        "ready": ready,
        "expected_versions": versions,
        "affected_accounts": effects,
        "reviewed_request": reviewed.model_dump(mode="json") if ready else None,
        "preview_token": identity(reviewed, activity_id) if ready else None,
    }
    return MoneyPlan(group_id, number, mutations, tuple(sorted(affected)), preview)
