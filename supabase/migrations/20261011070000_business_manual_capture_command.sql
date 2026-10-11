alter table public.business_action_receipts
    drop constraint business_action_receipts_check1,
    add constraint business_action_receipts_unplanned_command check (
        turn_key is not null or
        (command->>'action' in ('review_draft', 'approve_expense', 'capture_note')) is true
    ),
    add constraint business_action_receipts_capture_human check (
        command->>'action' is distinct from 'capture_note'
        or (actor->>'actor_kind' = 'member' and turn_key is null and action_index is null) is true
    );
