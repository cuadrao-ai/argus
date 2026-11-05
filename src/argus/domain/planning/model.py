"""Expectation editing and occurrence identity rules."""

from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid4, uuid5

from argus.domain.planning.recurrence import dates
from argus.domain.planning.schemas import (
    CASH_TYPES,
    ExpectationCreate,
    ExpectationEdit,
    Schedule,
)
from argus.domain.recording.currency import (
    currency_exponent,
    format_minor_units,
    normalize_currency,
    parse_minor_units,
)
from argus.domain.recording.errors import (
    AccountNotFound,
    RecordingInputError,
    StaleVersion,
)
from argus.domain.recording.repository import StoredAccount


class UnsafeCutover(RecordingInputError):
    def __init__(self, earliest: date) -> None:
        super().__init__(
            "plan_cutover_unsafe",
            "Keep previously recorded occurrences. Choose the earliest safe date or later.",
        )
        self.earliest_effective_date = earliest.isoformat()


def fail(code: str, detail: str) -> None:
    raise RecordingInputError(code, detail)


def cash_account(
    accounts: list[StoredAccount], account_id: str | None, currency: str | None = None
) -> None:
    if account_id is None:
        return
    account = next((s.account for s in accounts if s.account.id == account_id), None)
    if account is None:
        raise AccountNotFound()
    if account.type not in CASH_TYPES:
        fail("account_ineligible", "Choose cash, checking or savings.")
    if currency and account.currency != currency:
        fail("currency_mismatch", "Choose an account in the expectation currency.")


def positive(amount: str, currency: str) -> int:
    value = parse_minor_units(amount, currency)
    if value <= 0:
        fail("amount_positive_required", "Enter a positive amount.")
    return value


def create(body: ExpectationCreate, accounts: list[StoredAccount]) -> dict[str, Any]:
    currency = normalize_currency(body.currency)
    aid = str(body.account_id) if body.account_id else None
    cash_account(accounts, aid, currency)
    return {
        "id": str(uuid4()),
        "version": 1,
        "kind": body.kind,
        "title": body.title,
        "currency": currency,
        "amount_minor": positive(body.amount, currency),
        "archived": False,
        "segments": [
            {
                "id": str(uuid4()),
                "account_id": aid,
                "schedule": body.schedule.model_dump(mode="json"),
                "until": None,
            }
        ],
    }


def earliest(expectation: dict[str, Any], links: dict[str, Any], today: date) -> date:
    protected = [
        date.fromisoformat(link["snapshot"]["due_date"]) + timedelta(days=1)
        for link in links.values()
        if link.get("expectation_id") == expectation["id"]
    ]
    return max([today, *protected])


def edit(
    expectation: dict[str, Any],
    body: ExpectationEdit,
    accounts: list[StoredAccount],
    links: dict[str, Any],
    today: date,
) -> None:
    if body.expected_version != expectation["version"]:
        raise StaleVersion()
    if body.title is not None:
        if not body.title.strip():
            fail("title_invalid", "Enter a title.")
        expectation["title"] = body.title.strip()
    if body.amount is not None:
        expectation["amount_minor"] = positive(body.amount, expectation["currency"])
    if body.archived is not None:
        expectation["archived"] = body.archived
    structural = body.schedule is not None or "account_id" in body.model_fields_set
    if structural:
        cutover = body.effective_date or earliest(expectation, links, today)
        if cutover < earliest(expectation, links, today):
            raise UnsafeCutover(earliest(expectation, links, today))
        previous = expectation["segments"][-1]
        aid = str(body.account_id) if body.account_id else None
        if "account_id" not in body.model_fields_set:
            aid = previous["account_id"]
        cash_account(accounts, aid, expectation["currency"])
        schedule = body.schedule
        if schedule is None:
            old = Schedule.model_validate(previous["schedule"])
            upcoming = [
                d
                for d in dates(old, old.start_date + timedelta(days=3660))
                if d >= cutover
            ]
            if not upcoming:
                fail("schedule_finished", "Choose a new schedule for future occurrences.")
            schedule = old.model_copy(
                update={
                    "start_date": upcoming[0],
                    "month_days": old.month_days
                    or ([old.start_date.day] if old.cadence == "monthly" else []),
                }
            )
        if schedule.start_date < cutover:
            raise UnsafeCutover(cutover)
        for segment in expectation["segments"]:
            boundary = (cutover - timedelta(days=1)).isoformat()
            segment["until"] = (
                min(segment["until"], boundary) if segment["until"] else boundary
            )
        expectation["segments"].append(
            {
                "id": str(uuid4()),
                "account_id": aid,
                "schedule": schedule.model_dump(mode="json"),
                "until": None,
            }
        )
    expectation["version"] += 1


def expectation_response(
    item: dict[str, Any], links: dict[str, Any], today: date
) -> dict[str, Any]:
    return {
        k: item[k]
        for k in (
            "id",
            "version",
            "kind",
            "title",
            "currency",
            "amount_minor",
            "archived",
        )
    } | {
        "amount": format_minor_units(item["amount_minor"], item["currency"]),
        "currency_fraction_digits": currency_exponent(item["currency"]),
        "account_id": item["segments"][-1]["account_id"],
        "schedule": item["segments"][-1]["schedule"],
        "earliest_effective_date": earliest(item, links, today).isoformat(),
    }


def occurrences(state: dict[str, Any], until: date) -> dict[str, dict[str, Any]]:
    result = {}
    for item in state["expectations"].values():
        if item["archived"]:
            continue
        for segment in item["segments"]:
            end = (
                min(until, date.fromisoformat(segment["until"]))
                if segment["until"]
                else until
            )
            for due in dates(Schedule.model_validate(segment["schedule"]), end):
                oid = str(uuid5(UUID(item["id"]), segment["id"] + ":" + due.isoformat()))
                result[oid] = {
                    "id": oid,
                    "expectation_id": item["id"],
                    "expectation_version": item["version"],
                    "kind": item["kind"],
                    "title": item["title"],
                    "currency": item["currency"],
                    "currency_fraction_digits": currency_exponent(item["currency"]),
                    "amount_minor": item["amount_minor"],
                    "amount": format_minor_units(item["amount_minor"], item["currency"]),
                    "account_id": segment["account_id"],
                    "due_date": due.isoformat(),
                }
    from argus.domain.planning import claims

    for key, link in claims.protected_links(state).items():
        if not link.get("expectation_id"):
            continue
        oid = claims.occurrence_id(key, link)
        if oid is None:
            continue
        snapshot = dict(link["snapshot"])
        snapshot["expectation_version"] = state["expectations"][link["expectation_id"]][
            "version"
        ]
        result[oid] = snapshot
    return result


def find_occurrence(state: dict[str, Any], oid: str, today: date) -> dict[str, Any]:
    ends = [
        date.fromisoformat(s["schedule"]["start_date"]) + timedelta(days=3660)
        for e in state["expectations"].values()
        for s in e["segments"]
    ]
    found = occurrences(state, max([today + timedelta(days=366), *ends])).get(oid)
    if found is None:
        raise AccountNotFound()
    return found
