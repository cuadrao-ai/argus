"""Actual canonical services, isolated UUID records and reviewed shared commands."""

from argus.domain.household import planning_schemas as wire
from argus.domain.household.planning import SharedPlanningService
from argus.domain.owner_scope import PERSONAL
from argus.domain.recording.money_schemas import MoneyRequest
from argus.domain.recording.money_service import MoneyService
from argus.domain.recording.service import FinancialAccountService

from tests.household.financial_fixtures import NOW, account, key, setup


def scene(lane):
    households, records, (a, b, c) = lane
    hid, bmid, _ = setup(lane)
    return dict(
        households=households,
        records=records,
        a=a,
        b=b,
        c=c,
        hid=hid,
        bmid=bmid,
        amid=households.get(user_id=a, household_id=hid).membership_id,
        plans=SharedPlanningService(households),
        aa=account(records, a),
        ad=account(records, a),
        ba=account(records, b),
        bd=account(records, b),
        loan=account(records, a, amount=1000, kind="other_debt"),
    )


def scope(s, actor, version=None):
    h = s["households"].get(user_id=actor, household_id=s["hid"])
    value = dict(membership_id=h.membership_id, expected_authorization_version=h.version)
    if version is not None:
        value["expected_plan_version"] = version
    return value


def create(s, kind, actor=None, **changes):
    actor = actor or s["a"]
    schedule = dict(cadence="once", start_date=NOW.date().isoformat())
    definitions = dict(
        budget=dict(
            kind="budget",
            name="Shared groceries",
            limit="100",
            currency="DOP",
            month=NOW.strftime("%Y-%m"),
            account_ids=[s["aa"]],
            category_ids=[],
            include_uncategorized=True,
        ),
        bill=dict(
            kind="bill",
            title="Shared bill",
            amount="100",
            currency="DOP",
            account_id=s["aa"],
            schedule=schedule,
        ),
        goal=dict(
            kind="goal",
            name="Shared savings",
            target="100",
            currency="DOP",
            destination_account_id=s["ad"],
            contribution_plan=dict(
                source_account_id=s["aa"], amount="100", schedule=schedule
            ),
        ),
        debt=dict(
            kind="debt",
            name="Shared debt",
            debt_account_id=s["loan"],
            source_account_id=s["aa"],
            amount="100",
            schedule=schedule,
        ),
    )
    definitions[kind].update(changes)
    return s["plans"].create(
        actor,
        s["hid"],
        kind,
        wire.CreatePlan(
            **scope(s, actor),
            definition=definitions[kind],
            participants=[dict(membership_id=s["bmid"])],
            responsibilities=[
                dict(
                    membership_id=s["amid"],
                    amount="70",
                    **(
                        {"period": NOW.strftime("%Y-%m")}
                        if kind == "budget"
                        else {"agreed_date": NOW.date()}
                    ),
                ),
                dict(
                    membership_id=s["bmid"],
                    amount="30",
                    **(
                        {"period": NOW.strftime("%Y-%m")}
                        if kind == "budget"
                        else {"agreed_date": NOW.date()}
                    ),
                ),
            ],
        ),
        key(),
    )["plan"]


def get(s, actor, p):
    return s["plans"].get(actor, s["hid"], p["ref"]["kind"], str(p["ref"]["id"]))


def command(s, actor, p, cls=wire.PlanCommand, **fields):
    return cls(**scope(s, actor, get(s, actor, p)["version"]), **fields)


def money(s, actor, p, request, purpose, oid=None, k=None):
    values = dict(activity=request, purpose=purpose, occurrence_id=oid)
    body = command(s, actor, p, wire.ContributionRecord, **values)
    args = (actor, s["hid"], p["ref"]["kind"], str(p["ref"]["id"]))
    preview = s["plans"].money(*args, body)
    assert preview["money"]["ready"]
    values["activity"] = MoneyRequest.model_validate(
        preview["money"]["reviewed_request"]
        | {"preview_token": preview["money"]["preview_token"]}
    )
    reviewed = command(s, actor, p, wire.ContributionRecord, **values)
    return s["plans"].money(*args, reviewed, key=k or key()), reviewed


def request(kind, source, amount="20", destination=None, **fields):
    return MoneyRequest(
        kind=kind,
        amount=amount,
        occurred_at=NOW,
        time_zone="UTC",
        **(
            dict(source_account_id=source, destination_account_id=destination)
            if destination
            else dict(account_id=source)
        ),
        **fields,
    )


def personal(s, actor, body):
    service = MoneyService(FinancialAccountService(s["records"], clock=lambda: NOW))
    preview = service.preview(user_id=actor, request=body, scope=PERSONAL)
    assert preview["ready"]
    return service.write(
        user_id=actor,
        request=MoneyRequest.model_validate(
            preview["reviewed_request"] | {"preview_token": preview["preview_token"]}
        ),
        idempotency_key=key(),
        scope=PERSONAL,
    )


def link(s, actor, p, receipt, purpose, oid=None, treatment="add", k=None):
    actual = receipt["activity"]
    body = command(
        s,
        actor,
        p,
        wire.ContributionLink,
        activity_id=actual["activity_id"],
        activity_revision=actual["revision"],
        purpose=purpose,
        occurrence_id=oid,
        treatment=treatment,
        expected_account_versions={a.id: a.version for a in receipt["accounts"]},
    )
    return s["plans"].link(
        actor, s["hid"], p["ref"]["kind"], str(p["ref"]["id"]), body, k or key()
    )
