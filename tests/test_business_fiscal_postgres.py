"""On real Postgres: the owner or anyone holding prepare marks a receipt as
personal and takes it back, on an open or an approved draft, each a revision
and a ledger row naming the actor, the grant used and its issuer; a read-only
grant is refused; the owner can take back anyone's mark; approval stays the
owner's; the accountant alone answers whether a personal receipt with a fiscal
number goes into the 606; a personal receipt is approved and left out of the
totals."""

from __future__ import annotations

from uuid import UUID, uuid4

import psycopg
import pytest
from argus.api.business_drafts import linked_records
from argus.domain.business.contracts.actions import (
    ApproveExpense,
    DecideFiscalInclusion,
    MarkPersonal,
)
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.contracts.facts import (
    fiscal_inclusion,
    fiscal_value,
    is_personal,
)
from argus.domain.business.transactions import transaction
from psycopg.types.json import Jsonb

from tests import test_business_actions_postgres as shared
from tests import test_financial_accounts_postgres as accounts
from tests.test_business_actions_postgres import ready

actions = shared.actions
users = shared.users
pytestmark = shared.pytestmark


def _owner(service, context, users):  # noqa: ANN001, ANN201
    """The owner's own context, with the owner grant healed as the space routes do."""

    with service.authority.pool.connection() as db:
        db.execute(
            "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities)"
            " select %s,%s,%s,ARRAY['read','prepare','approve'] where not exists"
            " (select 1 from public.business_client_grants where space_id=%s and grantee_id=%s"
            " and revoked_at is null)",
            (
                context.actor.space_id,
                users["owner"],
                users["owner"],
                context.actor.space_id,
                users["owner"],
            ),
        )
    return service.resolve_actor(
        TrustedActor(
            actor_id=UUID(users["owner"]),
            actor_kind="member",
            space_id=context.actor.space_id,
        )
    )


def _with_ncf(service, draft_id):  # noqa: ANN001
    """The draft carries a printed NCF, as a read would leave it."""

    with service.authority.pool.connection() as db:
        db.execute(
            "update public.financial_import_events set resolution ="
            " jsonb_set(resolution, '{business,facts,fiscal}', %s) where id=%s",
            (
                Jsonb(
                    {
                        "rnc": {"state": "unknown"},
                        "ncf": {
                            "state": "known",
                            "value": "B0100000001",
                            "origin": "extracted",
                            "verified": False,
                            "source_ids": [str(uuid4())],
                        },
                        "ecf": {"state": "unknown"},
                        "itbis": {"state": "unknown"},
                        "include_606": {"state": "unknown"},
                    }
                ),
                str(draft_id),
            ),
        )


def _ledger(service, space_id, action):  # noqa: ANN001, ANN201
    """Applied rows only: a refused attempt leaves its own row saying so."""

    with service.authority.pool.connection() as db:
        return db.execute(
            "select actor->>'actor_id', actor->>'grant_id', actor->>'issuer_id',"
            " command->'request'->>'personal'"
            " from public.business_action_receipts"
            " where space_id=%s and turn_key is null and command->>'action'=%s"
            " and outcome->>'outcome'='applied' order by created_at",
            (space_id, action),
        ).fetchall()


@pytest.fixture
def reader(actions, users):  # noqa: ANN001, ANN201
    """A third person the owner gave read alone, in the same Business."""

    service, accountant, _ = actions
    with psycopg.connect(accounts.DSN) as db:
        ids = accounts._create_users(db, ("reader", False))
        db.execute(
            "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities)"
            " values (%s,%s,%s,ARRAY['read'])",
            (accountant.actor.space_id, ids["reader"], users["owner"]),
        )
        db.commit()
    try:
        yield service.resolve_actor(
            TrustedActor(
                actor_id=UUID(ids["reader"]),
                actor_kind="member",
                space_id=accountant.actor.space_id,
            )
        )
    finally:
        with psycopg.connect(accounts.DSN) as db:
            db.execute(
                "delete from public.business_client_grants where grantee_id=%s",
                (ids["reader"],),
            )
            db.commit()
            accounts._delete_users(db, ids)


def test_the_owner_marks_personal_and_back_each_a_revision_and_a_ledger_row(
    actions, users
):  # noqa: ANN001
    service, accountant, _ = actions
    owner = _owner(service, accountant, users)
    draft = ready(service, accountant)
    before = service.dossier(owner, draft)
    marked = service.mark_personal(
        owner, draft, MarkPersonal(version=before.version, personal=True), "own-mark"
    )
    assert marked.outcome == "applied", marked
    assert (
        service.mark_personal(
            owner, draft, MarkPersonal(version=before.version, personal=True), "own-mark"
        )
        == marked
    )
    view = service.dossier(owner, draft)
    assert is_personal(view.facts) and view.facts.business_share.origin == "owner_stated"
    assert (
        view.version == before.version + 1
        and len(view.history) == len(before.history) + 1
    )
    assert view.history[-1].actor.actor_id == owner.actor.actor_id
    assert [
        row[0] for row in _ledger(service, accountant.actor.space_id, "mark_personal")
    ] == [users["owner"]]
    # Approval admits a personal receipt; the money is recorded as today.
    approved = service.approve(
        owner,
        draft,
        ApproveExpense(version=view.version, action="record_expense"),
        "approve",
    )
    assert approved.outcome == "applied", approved
    # The owner's own mark names nobody else.
    with transaction(service.authority, owner) as tx:
        marks = linked_records(tx, [str(approved.activity_id)])
    assert marks[str(approved.activity_id)]["personal_marked_by"] is None
    # Taking the mark back on the approved draft: a new revision, the ledger grows by one.
    recorded = service.dossier(owner, draft).version
    back = service.mark_personal(
        owner, draft, MarkPersonal(version=recorded, personal=False), "own-unmark"
    )
    assert back.outcome == "applied", back
    after = service.dossier(owner, draft)
    assert not is_personal(after.facts) and after.facts.business_share.value.kind == "all"
    assert len(_ledger(service, accountant.actor.space_id, "mark_personal")) == 2
    assert after.history[-1].actor.grant_id == owner.grant_id


def test_a_prepare_grantee_marks_personal_the_ledger_names_them_and_the_owner_undoes_it(
    actions, users
):  # noqa: ANN001
    service, accountant, grant = actions
    owner = _owner(service, accountant, users)
    draft = ready(service, accountant)
    version = service.dossier(owner, draft).version
    marked = service.mark_personal(
        accountant, draft, MarkPersonal(version=version, personal=True), "acct-mark"
    )
    assert marked.outcome == "applied", marked
    view = service.dossier(owner, draft)
    assert is_personal(view.facts) and view.facts.business_share.origin == "member_set"
    marker = view.history[-1].actor
    assert marker.actor_id == accountant.actor.actor_id
    assert marker.grant_id == grant and str(marker.issuer_id) == users["owner"]
    assert _ledger(service, accountant.actor.space_id, "mark_personal") == [
        (users["other"], str(grant), users["owner"], "true")
    ]
    # Approval stays the owner's: the grantee is refused, the owner approves.
    refused = service.approve(
        accountant,
        draft,
        ApproveExpense(version=view.version, action="record_expense"),
        "acct-approve",
    )
    assert (refused.outcome, refused.code) == (
        "permission_denied",
        "business_permission_denied",
    )
    approved = service.approve(
        owner,
        draft,
        ApproveExpense(version=view.version, action="record_expense"),
        "approve",
    )
    assert approved.outcome == "applied", approved
    # Every view names who marked it, since it was not the owner.
    with transaction(service.authority, owner) as tx:
        marks = linked_records(tx, [str(approved.activity_id)])
    assert marks[str(approved.activity_id)]["personal"] is True
    assert marks[str(approved.activity_id)]["personal_marked_by"] == marker.display_name
    assert service.dossier(owner, draft).personal_marked_by == marker.display_name
    # The owner takes the accountant's mark back in one action, the same unmark.
    recorded = service.dossier(owner, draft).version
    back = service.mark_personal(
        owner, draft, MarkPersonal(version=recorded, personal=False), "own-unmark"
    )
    assert back.outcome == "applied", back
    assert not is_personal(service.dossier(owner, draft).facts)
    assert _ledger(service, accountant.actor.space_id, "mark_personal") == [
        (users["other"], str(grant), users["owner"], "true"),
        (users["owner"], str(owner.grant_id), users["owner"], "false"),
    ]
    with transaction(service.authority, owner) as tx:
        marks = linked_records(tx, [str(approved.activity_id)])
    assert marks[str(approved.activity_id)]["personal"] is False
    assert marks[str(approved.activity_id)]["personal_marked_by"] is None


def test_a_read_only_grantee_is_refused_and_leaves_no_mark(actions, users, reader):  # noqa: ANN001
    service, accountant, _ = actions
    owner = _owner(service, accountant, users)
    draft = ready(service, accountant)
    version = service.dossier(owner, draft).version
    for personal in (True, False):
        refused = service.mark_personal(
            reader,
            draft,
            MarkPersonal(version=version, personal=personal),
            f"read-{personal}",
        )
        assert (refused.outcome, refused.code) == (
            "permission_denied",
            "business_permission_denied",
        )
    view = service.dossier(owner, draft)
    assert view.version == version and not is_personal(view.facts)
    assert _ledger(service, accountant.actor.space_id, "mark_personal") == []


def test_a_personal_receipt_is_left_out_of_the_totals_but_kept_with_its_mark(
    actions, users
):  # noqa: ANN001
    service, accountant, _ = actions
    owner = _owner(service, accountant, users)
    draft = ready(service, accountant)
    _with_ncf(service, draft)
    version = service.dossier(owner, draft).version
    assert (
        service.mark_personal(
            owner, draft, MarkPersonal(version=version, personal=True), "mark"
        ).outcome
        == "applied"
    )
    approved = service.approve(
        owner,
        draft,
        ApproveExpense(version=version + 1, action="record_expense"),
        "approve",
    )
    assert approved.outcome == "applied", approved
    with transaction(service.authority, owner) as tx:
        marks = linked_records(tx, [str(approved.activity_id)])
    assert marks[str(approved.activity_id)]["personal"] is True
    assert marks[str(approved.activity_id)]["fiscal_value"] == "ncf"
    assert marks[str(approved.activity_id)]["include_606"] is None


def test_the_606_answer_is_the_accountants_only_on_a_personal_receipt_with_a_fiscal_number(
    actions, users
):  # noqa: ANN001
    service, accountant, _ = actions
    owner = _owner(service, accountant, users)
    draft = ready(service, accountant)
    version = service.dossier(owner, draft).version
    # Not personal yet: nothing to decide.
    early = service.decide_606(
        accountant, draft, DecideFiscalInclusion(version=version, include=True), "early"
    )
    assert (early.outcome, early.code) == ("invalid_input", "business_606_not_applicable")
    assert (
        service.mark_personal(
            owner, draft, MarkPersonal(version=version, personal=True), "mark"
        ).outcome
        == "applied"
    )
    # Personal but without a fiscal number: still nothing to decide.
    none = service.decide_606(
        accountant,
        draft,
        DecideFiscalInclusion(version=version + 1, include=True),
        "none",
    )
    assert none.code == "business_606_not_applicable"
    _with_ncf(service, draft)
    view = service.dossier(owner, draft)
    assert fiscal_value(view.facts) == "ncf" and fiscal_inclusion(view.facts) is None
    # The owner acting as owner is refused; the app never decides.
    refused = service.decide_606(
        owner, draft, DecideFiscalInclusion(version=view.version, include=True), "own"
    )
    assert (refused.outcome, refused.code) == (
        "permission_denied",
        "business_permission_denied",
    )
    decided = service.decide_606(
        accountant,
        draft,
        DecideFiscalInclusion(version=view.version, include=False),
        "acct",
    )
    assert decided.outcome == "applied", decided
    answered = service.dossier(owner, draft)
    assert fiscal_inclusion(answered.facts) is False
    assert answered.facts.fiscal.include_606.origin == "member_set"
    assert answered.history[-1].actor.actor_id == accountant.actor.actor_id
    assert [
        row[1] for row in _ledger(service, accountant.actor.space_id, "decide_606")
    ] == [str(accountant.grant_id)]
    # Taking the Personal mark back leaves the answer in the facts but inapplicable.
    assert (
        service.mark_personal(
            owner, draft, MarkPersonal(version=answered.version, personal=False), "unmark"
        ).outcome
        == "applied"
    )
    assert fiscal_inclusion(service.dossier(owner, draft).facts) is None


def test_the_list_row_and_the_record_read_the_same_marks(actions, users):  # noqa: ANN001
    """One owner supplies the marks: the expense row and the record agree after
    a grantee's mark, after the owner's unmark and after the owner's own mark."""

    service, accountant, _ = actions
    owner = _owner(service, accountant, users)
    draft = ready(service, accountant)
    version = service.dossier(owner, draft).version
    assert (
        service.mark_personal(
            accountant, draft, MarkPersonal(version=version, personal=True), "acct"
        ).outcome
        == "applied"
    )
    approved = service.approve(
        owner,
        draft,
        ApproveExpense(version=version + 1, action="record_expense"),
        "approve",
    )
    assert approved.outcome == "applied", approved
    activity = str(approved.activity_id)

    def both():  # noqa: ANN202
        record = service.dossier(owner, draft)
        with transaction(service.authority, owner) as tx:
            row = linked_records(tx, [activity])[activity]
        keys = ("personal", "personal_marked_by", "fiscal_value", "include_606")
        assert {key: row[key] for key in keys} == {
            key: getattr(record, key) for key in keys
        }
        return record

    grantee = both()
    assert grantee.personal is True
    assert grantee.personal_marked_by == next(
        revision.actor.display_name
        for revision in reversed(grantee.history)
        if revision.actor.actor_id == accountant.actor.actor_id
    )
    unmarked = service.mark_personal(
        owner,
        draft,
        MarkPersonal(version=grantee.version, personal=False),
        "unmark",
    )
    assert unmarked.outcome == "applied", unmarked
    after = both()
    assert (after.personal, after.personal_marked_by) == (False, None)
    remarked = service.mark_personal(
        owner, draft, MarkPersonal(version=after.version, personal=True), "mark"
    )
    assert remarked.outcome == "applied", remarked
    own = both()
    assert (own.personal, own.personal_marked_by) == (True, None)


def test_the_606_answer_names_the_accountant_after_the_owner_edits_something_else(
    actions, users
):  # noqa: ANN001
    from argus.domain.business.contracts.actions import ReviewDraft
    from argus.domain.business.contracts.facts import BusinessFactPatch

    service, accountant, _ = actions
    owner = _owner(service, accountant, users)
    draft = ready(service, accountant)
    version = service.dossier(owner, draft).version
    assert (
        service.mark_personal(
            owner, draft, MarkPersonal(version=version, personal=True), "mark"
        ).outcome
        == "applied"
    )
    _with_ncf(service, draft)
    view = service.dossier(owner, draft)
    assert view.fiscal_known is True and view.include_606_by is None
    decided = service.decide_606(
        accountant,
        draft,
        DecideFiscalInclusion(version=view.version, include=True),
        "acct",
    )
    assert decided.outcome == "applied", decided
    edited = service.review(
        owner,
        draft,
        ReviewDraft(
            version=service.dossier(owner, draft).version,
            facts=BusinessFactPatch(category_id={"state": "known", "value": "transport"}),
        ),
        "own-edit",
    )
    assert edited.outcome == "applied", edited
    after = service.dossier(owner, draft)
    assert after.history[-1].actor.actor_id == owner.actor.actor_id
    accountant_name = next(
        revision.actor.display_name
        for revision in after.history
        if revision.actor.actor_id == accountant.actor.actor_id
        and revision.after.fiscal is not None
        and revision.after.fiscal.include_606
        != (
            revision.before.fiscal.include_606
            if revision.before and revision.before.fiscal
            else None
        )
    )
    assert (after.include_606, after.include_606_by) == (True, accountant_name)


def test_one_expense_has_one_draft_so_its_marks_have_one_source(actions, users):  # noqa: ANN001
    """The database admits one import event per recorded activity: a second
    draft cannot claim an expense, so the expense's marks come from exactly one
    draft and linked_records, ordered by the latest revision, is deterministic."""

    service, accountant, _ = actions
    owner = _owner(service, accountant, users)
    first = ready(service, accountant)
    approved = service.approve(
        owner,
        first,
        ApproveExpense(
            version=service.dossier(owner, first).version, action="record_expense"
        ),
        "approve",
    )
    assert approved.outcome == "applied", approved
    second = ready(service, accountant)
    with pytest.raises(psycopg.errors.UniqueViolation):
        with service.authority.pool.connection() as db:
            db.execute(
                "update public.financial_import_events set state='accepted', activity_id=%s"
                " where id=%s",
                (approved.activity_id, str(second)),
            )
    activity = str(approved.activity_id)
    with transaction(service.authority, owner) as tx:
        once = linked_records(tx, [activity])[activity]
        again = linked_records(tx, [activity])[activity]
    assert once == again and once["draft_id"] == str(first)
