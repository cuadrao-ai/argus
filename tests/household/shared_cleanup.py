"""Delete only synthetic test identities' protected history after assertions."""


def cleanup(c, users, hids=()):
    ids = list(users)
    bindings = [
        r[0]
        for r in c.execute(
            "select id from public.household_plan_bindings where owner_user_id=any(%s::uuid[]) or household_id=any(%s::uuid[])",
            (ids, list(hids)),
        ).fetchall()
    ]
    c.execute(
        "delete from public.household_plan_receipts where actor_id=any(%s::uuid[]) or binding_id=any(%s::uuid[])",
        (ids, bindings),
    )
    for table in (
        "household_plan_archived_claims",
        "household_plan_archived_allocations",
        "household_plan_archived_activities",
    ):
        c.execute(
            f"delete from public.{table} where binding_id=any(%s::uuid[])", (bindings,)
        )
    c.execute(
        "delete from public.financial_plan_links where user_id=any(%s::uuid[]) or activity_owner_id=any(%s::uuid[]) or binding_id=any(%s::uuid[])",
        (ids, ids, bindings),
    )
    c.execute(
        "delete from public.financial_goal_allocation_revisions where goal_owner_id=any(%s::uuid[]) or account_owner_id=any(%s::uuid[])",
        (ids, ids),
    )
    c.execute(
        "delete from public.financial_goal_allocations where goal_owner_id=any(%s::uuid[]) or account_owner_id=any(%s::uuid[])",
        (ids, ids),
    )
    c.execute(
        "delete from public.financial_plan_responsibilities where owner_id=any(%s::uuid[])",
        (ids,),
    )
    c.execute(
        "delete from public.household_plan_participants where binding_id=any(%s::uuid[])",
        (bindings,),
    )
    c.execute(
        "delete from public.household_plan_bindings where id=any(%s::uuid[])", (bindings,)
    )
    c.execute(
        "delete from public.financial_plan_definition_revisions where owner_id=any(%s::uuid[])",
        (ids,),
    )
    unexpected = c.execute(
        "select 1 from public.financial_activity_memberships where user_id=any(%s::uuid[]) and not(record_owner_id=any(%s::uuid[]))",
        (ids, ids),
    ).fetchone()
    assert not unexpected, "Synthetic cleanup must not remove another identity's history"
    c.execute(
        "delete from public.financial_activity_memberships where user_id=any(%s::uuid[])",
        (ids,),
    )
