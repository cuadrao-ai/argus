-- Generated from OpenRouterModelTier for document extraction receipts.
-- The statement below is render_tier_check_constraint() from
-- argus.observability.route_receipt_tiers, pinned by
-- tests/test_route_receipt_tiers_migration.py.
-- NOT VALID skips the row scan under ACCESS EXCLUSIVE. Commit releases that
-- lock before VALIDATE CONSTRAINT scans under SHARE UPDATE EXCLUSIVE.
-- Drop if exists keeps a re-run from failing when the check is already present.
alter table public.route_receipts
  drop constraint if exists route_receipts_tier_check,
  add constraint route_receipts_tier_check
    check (tier in ('utility', 'chat', 'structured', 'context', 'readout', 'vision')) not valid;
commit;
alter table public.route_receipts
  validate constraint route_receipts_tier_check;
