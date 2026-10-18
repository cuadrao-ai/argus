set local lock_timeout = '5s';
set local statement_timeout = '60s';

create table public.business_sales (
    id uuid primary key default gen_random_uuid(),
    space_id uuid not null references public.spaces(id) on delete restrict,
    draft_id uuid not null,
    invoice_total numeric(18,2) not null,
    itbis_charged numeric(18,2) not null,
    customer_id_type text not null,
    customer_id_number text not null,
    ncf text not null,
    issued_on date not null,
    collection_status text not null,
    currency text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint business_sales_invoice_total_positive check (invoice_total > 0),
    constraint business_sales_itbis_bounded check (
        itbis_charged >= 0 and itbis_charged <= invoice_total
    ),
    constraint business_sales_currency_dop check (currency = 'DOP'),
    constraint business_sales_collection_status_check check (
        collection_status in ('cobrado', 'por_cobrar')
    ),
    constraint business_sales_customer_id_type_check check (
        customer_id_type in ('rnc', 'cedula')
    ),
    constraint business_sales_customer_id_shape_check check (
        customer_id_number ~ '^[0-9]+$'
        and customer_id_number ~ '[1-9]'
        and (
            (customer_id_type = 'rnc' and length(customer_id_number) = 9)
            or (customer_id_type = 'cedula' and length(customer_id_number) = 11)
        )
    ),
    constraint business_sales_ncf_check check (
        ncf ~ '^(B[0-9]{10}|E[0-9]{12})$'
    ),
    constraint business_sales_space_draft_key unique (space_id, draft_id),
    constraint business_sales_space_ncf_key unique (space_id, ncf),
    constraint business_sales_draft_space_fkey
        foreign key (draft_id, space_id)
        references public.financial_import_events(id, owner_space_id)
        on delete restrict
);

create index business_sales_space_issued_id_idx
    on public.business_sales (space_id, issued_on, id);
create index business_sales_space_collection_issued_idx
    on public.business_sales (space_id, collection_status, issued_on);
create index business_sales_draft_idx on public.business_sales (draft_id);

alter table public.business_sales enable row level security;
revoke all on public.business_sales from public, anon, authenticated;
grant select, insert, update on public.business_sales to service_role;
grant select on public.business_sales to authenticated;

create policy business_sales_authenticated_select
    on public.business_sales
    for select
    to authenticated
    using (
        exists (
            select 1
              from public.spaces s
             where s.id = business_sales.space_id
               and s.kind = 'business'
               and s.closed_at is null
               and (
                    s.created_by = (select auth.uid())
                    or exists (
                        select 1
                          from public.business_client_grants g
                         where g.space_id = s.id
                           and g.grantee_id = (select auth.uid())
                           and g.revoked_at is null
                           and (
                               g.expires_at is null
                               or g.expires_at > clock_timestamp()
                           )
                    )
               )
        )
    );

insert into argus_private.retention_policies (table_name, rule, basis)
values (
    'public.business_sales',
    'Retain for ten years from issued_on. This slice installs no purge.',
    'docs/contracts/business-venta.md'
);

alter table public.business_action_receipts
    drop constraint business_action_receipts_unplanned_command,
    drop constraint business_action_receipts_human_only_actions,
    add constraint business_action_receipts_unplanned_command check (
        turn_key is not null or
        (command->>'action' in ('review_draft', 'approve_expense', 'capture_note',
            'approve_income', 'prepare_attachment',
            'owner_grant', 'grant_access', 'invite_access', 'accept_invite', 'revoke_grant', 'revoke_invite',
            'rebind_attachment', 'settle_remainder',
            'access_seen', 'email_ai_consent_declined', 'mark_personal', 'decide_606',
            'receipt_upload', 'receipt_review', 'receipt_confirm',
            'mark_venta', 'set_venta_collection')) is true
    ),
    add constraint business_action_receipts_human_only_actions check (
        command->>'action' not in ('access_seen', 'email_ai_consent_declined', 'mark_personal', 'decide_606',
            'receipt_upload', 'receipt_review', 'receipt_confirm',
            'mark_venta', 'set_venta_collection')
        or (actor->>'actor_kind' = 'member' and turn_key is null and action_index is null) is true
    );
