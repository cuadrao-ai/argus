"""Current financial records, read through their canonical owners."""

import base64
import hashlib
import json
import unicodedata
from collections.abc import Sequence
from datetime import timedelta
from typing import Annotated, Literal, TypeVar

from pydantic import BaseModel, Field

from argus.domain.owner_scope import PERSONAL, OwnerScope
from argus.domain.planning import claims, debt_projection, goal_projection, storage
from argus.domain.planning.budget_schemas import BudgetDefinition
from argus.domain.planning.budgets import definition
from argus.domain.planning.debt_schemas import DebtProgress
from argus.domain.planning.goal_schemas import GoalProgress
from argus.domain.planning.model import expectation_response
from argus.domain.planning.responses import Expectation
from argus.domain.planning.service import PlanService
from argus.domain.recording.money_reads import current_activities
from argus.domain.recording.money_responses import MoneyActivityResponse
from argus.domain.recording.schemas import FinancialAccountResponse, account_response
from argus.domain.recording.service import FinancialAccountService
from argus.domain.search_text import normalize_search_text

Kind = Literal["account", "activity", "expectation", "budget", "goal", "debt"]
T = TypeVar("T")


class AccountHit(BaseModel):
    kind: Literal["account"] = "account"
    account: FinancialAccountResponse


class ActivityHit(BaseModel):
    kind: Literal["activity"] = "activity"
    activity: MoneyActivityResponse
    archived: bool


class ExpectationHit(BaseModel):
    kind: Literal["expectation"] = "expectation"
    expectation: Expectation


class BudgetHit(BaseModel):
    kind: Literal["budget"] = "budget"
    budget: BudgetDefinition


class GoalHit(BaseModel):
    kind: Literal["goal"] = "goal"
    goal: GoalProgress


class DebtHit(BaseModel):
    kind: Literal["debt"] = "debt"
    debt: DebtProgress


Hit = Annotated[
    AccountHit | ActivityHit | ExpectationHit | BudgetHit | GoalHit | DebtHit,
    Field(discriminator="kind"),
]


class SearchPage(BaseModel):
    items: list[Hit]
    next_cursor: str | None


class InvalidCursor(Exception):
    pass


class StaleCursor(Exception):
    pass


def fold(value: str) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(c)
    )


def matches(query: str, text: str) -> bool:
    if not query:
        return True
    text = fold(text)
    # Query punctuation is literal rather than a wildcard or an empty browse.
    if any(not c.isalnum() and not c.isspace() for c in query):
        return query in text
    return all(
        token in normalize_search_text(text)
        for token in normalize_search_text(query).split()
    )


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def query_text(q: str) -> str:
    return " ".join(fold(q).split())


def hits(
    service: FinancialAccountService,
    owner: str,
    *,
    scope: OwnerScope,
    query: str,
    kind: Kind | None = None,
    currency: str | None = None,
) -> list[Hit]:
    """Every record in ``scope`` that ``query`` (from ``query_text``) matches, in
    Search order. Plans belong to Personal, so a Business space has none."""

    if scope == PERSONAL:
        state, accounts = storage.read(service._repository, owner)
    else:
        state = storage.empty()
        accounts = service.list_accounts(user_id=owner, scope=scope)
    archived = {s.account.id: s.account.archived for s in accounts}
    rows: list[tuple[str, str, str, Hit]] = []

    def add(hit: Hit, title: str, identifier: str, denomination: str) -> None:
        if (kind is None or hit.kind == kind) and (
            currency is None or currency == denomination
        ):
            if matches(query, title):
                rows.append((hit.kind, fold(title), identifier, hit))

    for stored in accounts:
        item = account_response(stored)
        add(
            AccountHit(account=item),
            " ".join(filter(None, [item.nickname, item.type, item.currency])),
            item.id,
            item.currency,
        )
    for item in current_activities(accounts):
        activity = MoneyActivityResponse.model_validate(item)
        title = " ".join(
            filter(
                None,
                [activity.note, activity.kind, activity.category_id, activity.source_id],
            )
        )
        add(
            ActivityHit(
                activity=activity,
                archived=any(archived[leg.account_id] for leg in activity.legs),
            ),
            title,
            activity.activity_id,
            activity.currency,
        )
    today = PlanService(service).today(state)
    for item in state["expectations"].values():
        expectation = Expectation.model_validate(
            expectation_response(item, claims.protected_links(state), today)
        )
        add(
            ExpectationHit(expectation=expectation),
            expectation.title,
            expectation.id,
            expectation.currency,
        )
    for item in state["budgets"].values():
        budget = BudgetDefinition.model_validate(definition(item))
        add(BudgetHit(budget=budget), budget.name, budget.id, budget.currency)
    for goal in goal_projection.project(
        state, accounts, today, today + timedelta(days=30)
    )[0]:
        item = GoalProgress.model_validate(goal)
        add(GoalHit(goal=item), item.goal.name, item.goal.id, item.goal.currency)
    for debt in debt_projection.project(
        state, accounts, today, today + timedelta(days=30)
    ):
        item = DebtProgress.model_validate(debt)
        add(DebtHit(debt=item), item.debt.name, item.debt.id, item.debt.currency)
    rows.sort(key=lambda row: row[:3])
    return [row[3] for row in rows]


def search(
    service: FinancialAccountService,
    owner: str,
    *,
    q: str = "",
    kind: Kind | None = None,
    currency: str | None = None,
    limit: int = 20,
    cursor: str | None = None,
) -> SearchPage:
    """The person's Personal records, a page at a time."""

    query = query_text(q)
    items = hits(
        service, owner, scope=PERSONAL, query=query, kind=kind, currency=currency
    )
    scope = digest([owner, query, kind, currency])
    snapshot = digest([item.model_dump(mode="json") for item in items])
    shown, next_cursor = page(
        items, scope=scope, snapshot=snapshot, limit=limit, cursor=cursor
    )
    return SearchPage(items=shown, next_cursor=next_cursor)


def page(
    items: Sequence[T], *, scope: str, snapshot: str, limit: int, cursor: str | None
) -> tuple[list[T], str | None]:
    """One page of ``items`` and the cursor to the next, if any. A cursor holds
    the ``scope`` it was issued for and the ``snapshot`` of the items then:
    another scope is invalid, a changed snapshot is stale."""

    offset = 0
    if cursor:
        try:
            token = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
            if set(token) != {"scope", "snapshot", "offset"} or token["scope"] != scope:
                raise InvalidCursor()
            offset = token["offset"]
            if not isinstance(offset, int) or isinstance(offset, bool) or offset < 1:
                raise InvalidCursor()
            if token["snapshot"] != snapshot:
                raise StaleCursor()
            if offset >= len(items):
                raise InvalidCursor()
        except (ValueError, TypeError, KeyError):
            raise InvalidCursor() from None
    end = offset + limit
    next_cursor = None
    if end < len(items):
        next_cursor = base64.urlsafe_b64encode(
            json.dumps({"scope": scope, "snapshot": snapshot, "offset": end}).encode()
        ).decode()
    return list(items[offset:end]), next_cursor
