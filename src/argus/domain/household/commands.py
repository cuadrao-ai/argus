"""Atomic retry receipts for the canonical Household lifecycle."""

from argus.domain.idempotency import canonical_hash
from argus.domain.recording.errors import IdempotencyConflict, StaleVersion

from .errors import AdminRequired, HouseholdNotFound
from .schemas import AcceptanceResult, CommandResult, InvitationCreated


def execute(repository, *, actor, operation, key, body, household_id, action):
    identity = canonical_hash(body)
    with repository.connection() as c, c.transaction():
        # Serialize same-actor creates; all scoped commands then use household first.
        c.execute(
            "select pg_advisory_xact_lock(hashtextextended(%s,0))",
            (actor + ":household-command",),
        )
        h = None
        if household_id:
            h = c.execute(
                "select version from public.households where id=%s for update",
                (household_id,),
            ).fetchone()
            if h is None:
                raise HouseholdNotFound()
        receipt = c.execute(
            "select identity_hash,household_id,membership_id,invitation_id from public.household_command_receipts where actor_id=%s and operation=%s and idempotency_key=%s",
            (actor, operation, key),
        ).fetchone()
        if receipt:
            if receipt[0] != identity:
                raise IdempotencyConflict()
            return result(
                repository,
                c,
                actor,
                str(receipt[1]),
                str(receipt[2]) if receipt[2] else None,
                True,
                str(receipt[3]) if receipt[3] else None,
            )
        if h:
            repository._require_member_row(c, user_id=actor, household_id=household_id)
        if h and body.get("expected_version") != h[0]:
            raise StaleVersion()
        value = action()
        hid = household_id or (
            value.household_id if isinstance(value, AcceptanceResult) else value.id
        )
        member = c.execute(
            "select id from public.household_members where household_id=%s and user_id=%s order by joined_at desc limit 1",
            (hid, actor),
        ).fetchone()
        mid = (
            value.membership_id
            if isinstance(value, AcceptanceResult)
            else str(member[0])
            if member
            else None
        )
        invite = value if isinstance(value, InvitationCreated) else None
        if household_id or isinstance(value, AcceptanceResult):
            c.execute(
                "update public.households set version=version+1 where id=%s", (hid,)
            )
        c.execute(
            "insert into public.household_command_receipts(actor_id,operation,idempotency_key,identity_hash,household_id,membership_id,invitation_id) values(%s,%s,%s,%s,%s,%s,%s)",
            (actor, operation, key, identity, hid, mid, invite.id if invite else None),
        )
        reply = result(repository, c, actor, hid, mid, False)
        return reply.model_copy(update={"invitation": invite})


def result(repository, c, actor, hid, mid, replayed, invitation_id=None):
    row = c.execute(
        "select h.status,h.admin_user_id,m.left_at,m.id from public.households h left join public.household_members m on m.id=%s and m.household_id=h.id and m.user_id=%s where h.id=%s",
        (mid, actor, hid),
    ).fetchone()
    live = (
        mid is not None
        and row is not None
        and row[0] == "active"
        and row[2] is None
        and row[3] is not None
    )
    invitation = None
    if invitation_id:
        if not live or str(row[1]) != actor:
            raise AdminRequired()
        invite = next(
            (i for i in repository._invitations(c, hid) if i.id == invitation_id), None
        )
        if invite:
            invitation = InvitationCreated(
                id=invite.id,
                household_id=hid,
                expires_at=invite.expires_at,
                token=None,
                state=invite.state,
            )
    return CommandResult(
        household_id=hid,
        membership_id=mid,
        state="active" if live else "departed",
        replayed=replayed,
        invitation=invitation,
    )
