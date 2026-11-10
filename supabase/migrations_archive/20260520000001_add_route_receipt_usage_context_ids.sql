-- Add launch-gate receipt observability fields without rewriting receipt history.

alter table public.route_receipts
  add column if not exists token_usage jsonb,
  add column if not exists context_packet_ids text[] not null default '{}'::text[];
