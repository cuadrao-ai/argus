-- Route receipts admit every model tier the runtime declares. The readout tier
-- was missing, so result_summary receipts and their cost-ledger rows failed to
-- persist (#605). No row is rewritten: every stored tier stays admitted.
-- The statement is render_tier_check_constraint() from
-- argus.observability.route_receipt_tiers, pinned to it by
-- tests/test_route_receipt_tiers_migration.py. OpenRouterModelTier owns the tiers.
-- DROP CONSTRAINT is classified destructive by the promotion gate. The founder
-- applies this migration at promotion.
-- Rollback: keep this check. The narrower one cannot return once readout
-- receipts exist.
alter table public.route_receipts
  drop constraint route_receipts_tier_check,
  add constraint route_receipts_tier_check
    check (tier in ('utility', 'chat', 'structured', 'context', 'readout'));
