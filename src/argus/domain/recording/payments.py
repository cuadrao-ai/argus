"""Lossless loan splits and real dated payment returns."""

from dataclasses import dataclass
from typing import Any, NoReturn
from zoneinfo import ZoneInfo

from argus.domain.recording.currency import parse_minor_units
from argus.domain.recording.errors import RecordingInputError
from argus.domain.recording.money_schemas import MoneyRequest

PAYMENT_KINDS = {"card_payment", "debt_payment"}


def fail(code: str, detail: str) -> NoReturn:
    raise RecordingInputError(code, detail)


def breakdown(legs: list[Any]) -> dict[str, int | None]:
    source = next((r for _, _, r in legs if r.role == "source"), None)
    destination = next((r for _, _, r in legs if r.role == "destination"), None)
    if source is None or destination is None or source.interest_minor is None:
        return {"principal_minor": None, "interest_minor": None, "fees_minor": None}
    return {
        "principal_minor": destination.amount_minor,
        "interest_minor": source.interest_minor,
        "fees_minor": source.amount_minor
        - destination.amount_minor
        - source.interest_minor,
    }


@dataclass(frozen=True)
class Payment:
    total: int
    principal: int
    interest: int | None
    reference: str | None = None
    reference_revision: int | None = None

    def leg(self, role: str | None) -> int:
        return self.principal if role == "destination" else self.total


def components(item: dict[str, Any]) -> tuple[int, ...]:
    if item["principal_minor"] is None:
        return (item["amount_minor"],)
    return tuple(item[key] for key in ("principal_minor", "interest_minor", "fees_minor"))


def shape(item: dict[str, Any]) -> set[tuple[str, str]]:
    return {(leg["role"], leg["account_id"]) for leg in item["legs"]}


def validate(
    request: MoneyRequest,
    currency: str,
    amount: int,
    old: dict[str, Any] | None,
    existing: list[dict[str, Any]],
    stamp: Any,
    targets: dict[str, str],
) -> Payment:
    by_id = {a["activity_id"]: a for a in existing}
    original = None
    if request.kind == "payment_reversal":
        original = by_id.get(request.reversal_of_activity_id)
        if original is None or original["kind"] not in PAYMENT_KINDS:
            fail("payment_reference_invalid", "Choose the original payment.")
        if old and old["reversal_of_activity_id"] != original["activity_id"]:
            fail(
                "payment_reference_immutable",
                "Correct the return for its original payment.",
            )
        if original["currency"] != currency or shape(original) != {
            (role, aid) for aid, role in targets.items()
        }:
            fail(
                "payment_return_mismatch",
                "Use the original payment accounts and currency.",
            )
        if (
            stamp.astimezone(ZoneInfo(request.time_zone)).date()
            < original["occurred_at"].astimezone(ZoneInfo(original["time_zone"])).date()
        ):
            fail("return_before_payment", "The return cannot precede its payment.")
    elif request.reversal_of_activity_id is not None:
        fail(
            "field_not_applicable", "A return reference applies only to payment returns."
        )
    loan = (
        request.kind == "debt_payment"
        or original is not None
        and original["kind"] == "debt_payment"
    )
    split = [request.principal, request.interest, request.fees]
    if loan:
        if any(value is None for value in split):
            fail(
                "payment_split_required",
                "Enter principal, interest and fees, including explicit zeros.",
            )
        values = [parse_minor_units(str(value), currency) for value in split]
        if any(value < 0 for value in values) or sum(values) != amount:
            fail(
                "payment_split_invalid",
                "Principal, interest and fees must be nonnegative and add up to the total.",
            )
        payment = Payment(amount, values[0], values[1])
        candidate_components = tuple(values)
    else:
        if any(value is not None for value in split):
            fail(
                "field_not_applicable",
                "A loan breakdown applies only to loan payments and their returns.",
            )
        payment = Payment(amount, amount, None)
        candidate_components = (amount,)
    if original:
        returns = [
            a
            for a in existing
            if a["reversal_of_activity_id"] == original["activity_id"]
            and (old is None or a["activity_id"] != old["activity_id"])
        ]
        totals = tuple(
            sum(components(a)[i] for a in returns) + value
            for i, value in enumerate(candidate_components)
        )
        if any(
            value > cap for value, cap in zip(totals, components(original), strict=True)
        ):
            fail(
                "payment_return_limit",
                "Returned components cannot exceed the original payment.",
            )
        return Payment(
            payment.total,
            payment.principal,
            payment.interest,
            original["activity_id"],
            original["revision"],
        )
    if old and request.kind in PAYMENT_KINDS:
        returns = [
            a for a in existing if a["reversal_of_activity_id"] == old["activity_id"]
        ]
        if returns:
            if (
                currency != old["currency"]
                or shape(old) != {(role, aid) for aid, role in targets.items()}
                or request.category_id != old["category_id"]
            ):
                fail(
                    "linked_payment_return",
                    "Correct linked returns before changing payment accounts, currency or category.",
                )
            if any(
                sum(components(a)[i] for a in returns) > value
                for i, value in enumerate(candidate_components)
            ):
                fail(
                    "payment_return_limit",
                    "The corrected payment cannot be less than its returned components.",
                )
            if any(
                stamp.astimezone(ZoneInfo(request.time_zone)).date()
                > a["occurred_at"].astimezone(ZoneInfo(a["time_zone"])).date()
                for a in returns
            ):
                fail(
                    "return_before_payment",
                    "Correct return dates before moving the payment after them.",
                )
    return payment


def net_total(item: dict[str, Any], activities: list[dict[str, Any]]) -> int:
    return int(item["amount_minor"]) - sum(
        int(a["amount_minor"])
        for a in activities
        if a["reversal_of_activity_id"] == item["activity_id"]
    )
