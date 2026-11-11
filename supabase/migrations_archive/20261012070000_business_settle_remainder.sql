-- A person settles the read purchases a recorded draft does not cover. That
-- is a turn-less ledger row by a member, so the receipts check grows by one
-- action. The list is the union with the rebind action so the two migrations
-- apply in either order.

alter table public.business_action_receipts
    drop constraint business_action_receipts_unplanned_command,
    add constraint business_action_receipts_unplanned_command check (
        turn_key is not null or
        (command->>'action' in ('review_draft', 'approve_expense', 'capture_note',
            'approve_income', 'prepare_attachment',
            'owner_grant', 'grant_access', 'invite_access', 'accept_invite', 'revoke_grant', 'revoke_invite',
            'rebind_attachment', 'settle_remainder')) is true
    ),
    add constraint business_action_receipts_settle_human check (
        command->>'action' is distinct from 'settle_remainder'
        or (actor->>'actor_kind' = 'member' and turn_key is null and action_index is null) is true
    );
