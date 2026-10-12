-- The owner may move a receipt's preparation binding from a grant that is no
-- longer live to their current grant. That move is a turn-less ledger row by a
-- member, so the receipts check grows by one action.

alter table public.business_action_receipts
    drop constraint business_action_receipts_unplanned_command,
    add constraint business_action_receipts_unplanned_command check (
        turn_key is not null or
        (command->>'action' in ('review_draft', 'approve_expense', 'capture_note',
            'approve_income', 'prepare_attachment',
            'owner_grant', 'grant_access', 'invite_access', 'accept_invite', 'revoke_grant', 'revoke_invite',
            'rebind_attachment')) is true
    ),
    add constraint business_action_receipts_rebind_human check (
        command->>'action' is distinct from 'rebind_attachment'
        or (actor->>'actor_kind' = 'member' and turn_key is null and action_index is null
            and command->'binding'->>'space_id' = space_id::text) is true
    );
