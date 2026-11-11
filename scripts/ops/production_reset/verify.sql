BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '120s';
SET LOCAL search_path = pg_catalog;

DO $verify$
DECLARE expected_table text; actual bigint;
BEGIN
  IF current_database() <> 'postgres' OR current_user <> 'postgres' THEN
    RAISE EXCEPTION 'Verification requires database postgres and role postgres';
  END IF;
  IF (SELECT array_agg(version ORDER BY version) FROM supabase_migrations.schema_migrations)
      IS DISTINCT FROM ARRAY['20261110160000', '20261110160100']::text[] THEN
    RAISE EXCEPTION 'Migration ledger must contain exactly the two baseline versions';
  END IF;
  IF EXISTS (SELECT FROM auth.users) OR EXISTS (SELECT FROM auth.identities)
      OR EXISTS (SELECT FROM auth.sessions) OR EXISTS (SELECT FROM storage.objects) THEN
    RAISE EXCEPTION 'Authentication users, identities, sessions and storage objects must be empty';
  END IF;
  IF EXISTS (SELECT FROM pg_extension WHERE extname IN ('pg_cron', 'pg_net')) THEN
    RAISE EXCEPTION 'Removed job and network extensions remain installed';
  END IF;
  -- Generated from every ENABLE ROW LEVEL SECURITY declaration in the baseline.
  FOREACH expected_table IN ARRAY ARRAY[
    'argus_private.account_deletion_placeholders', 'argus_private.account_deletion_revocations', 'argus_private.account_deletion_runs',
    'argus_private.account_placeholders', 'argus_private.business_custody_changes', 'argus_private.business_custody_deferred_keys',
    'argus_private.business_custody_moves', 'argus_private.business_custody_objects', 'argus_private.business_custody_reservations',
    'argus_private.business_departure_aliases', 'argus_private.business_invitation_commands', 'argus_private.business_purge_objects',
    'argus_private.business_purge_runs', 'argus_private.business_report_view_commands', 'argus_private.business_saved_report_views',
    'argus_private.business_workspace_assets', 'argus_private.business_workspace_commands', 'argus_private.invite_code_digests',
    'public.apple_sign_in_credentials', 'public.argus_memory_vectors', 'public.backtest_jobs',
    'public.backtest_runs', 'public.beta_admissions', 'public.beta_invitations',
    'public.beta_invite_quota_grants', 'public.business_access_invites', 'public.business_action_receipts',
    'public.business_ai_consents', 'public.business_bank_accounts', 'public.business_bank_imports',
    'public.business_bank_line_outcomes', 'public.business_bank_lines', 'public.business_bank_suggestions',
    'public.business_client_grants', 'public.business_close_mail_outbox', 'public.business_consent_acceptances',
    'public.business_customers', 'public.business_dgii_export_lines', 'public.business_document_settlement_revisions',
    'public.business_document_settlements', 'public.business_draft_revisions', 'public.business_draft_sources',
    'public.business_email_address_events', 'public.business_email_daily_usage', 'public.business_email_deliveries',
    'public.business_email_parts', 'public.business_email_retired_aliases', 'public.business_email_routes',
    'public.business_email_senders', 'public.business_fiscal_observations', 'public.business_fiscal_operations',
    'public.business_guide_dismissals', 'public.business_invoice_commands', 'public.business_invoice_revisions',
    'public.business_invoices', 'public.business_lifecycle_commands', 'public.business_logos',
    'public.business_notifications', 'public.business_ownership_transfers', 'public.business_questions',
    'public.business_read_daily_usage', 'public.business_receipt_activity_baseline', 'public.business_receipt_consent_commands',
    'public.business_receipt_read_states', 'public.business_receipt_reading_consents', 'public.business_search_opens',
    'public.business_search_recents', 'public.business_sender_leases', 'public.business_sources',
    'public.business_transfer_mail_outbox', 'public.business_turns', 'public.business_whatsapp_ai_consents',
    'public.chat_turn_lifecycles', 'public.checkpoint_blobs', 'public.checkpoint_migrations',
    'public.checkpoint_writes', 'public.checkpoints', 'public.collection_strategies',
    'public.collections', 'public.context_packets', 'public.conversation_read_states',
    'public.conversations', 'public.cost_ledger_entries', 'public.decision_notes',
    'public.dgii_rnc', 'public.dgii_rnc_load', 'public.evidence_artifacts',
    'public.feedback', 'public.financial_account_idempotency', 'public.financial_accounts',
    'public.financial_activity_groups', 'public.financial_activity_memberships', 'public.financial_activity_receipts',
    'public.financial_activity_revisions', 'public.financial_asset_changes', 'public.financial_asset_details',
    'public.financial_budgets', 'public.financial_debt_plans', 'public.financial_document_extractions',
    'public.financial_expectations', 'public.financial_goal_allocation_revisions', 'public.financial_goal_allocations',
    'public.financial_goals', 'public.financial_import_account_links', 'public.financial_import_events',
    'public.financial_import_observations', 'public.financial_observation_coverage', 'public.financial_operation_receipts',
    'public.financial_plan_definition_revisions', 'public.financial_plan_links', 'public.financial_plan_receipts',
    'public.financial_plan_responsibilities', 'public.financial_plan_selections', 'public.financial_record_revisions',
    'public.financial_records', 'public.financial_shortcut_device_tokens', 'public.financial_source_connections',
    'public.financial_source_gmail_senders', 'public.guest_funnel_milestones', 'public.guest_workspace_handoffs',
    'public.guest_workspaces', 'public.household_account_grants', 'public.household_command_receipts',
    'public.household_deletion_events', 'public.household_invitations', 'public.household_members',
    'public.household_plan_archived_activities', 'public.household_plan_archived_allocations', 'public.household_plan_archived_claims',
    'public.household_plan_bindings', 'public.household_plan_participants', 'public.household_plan_receipts',
    'public.households', 'public.idea_versions', 'public.ideas',
    'public.invite_referrals', 'public.invite_sender_refs', 'public.memory_candidates',
    'public.memory_consent_actions', 'public.memory_prompt_history', 'public.memory_provenance',
    'public.memory_provider_cleanup', 'public.memory_provider_projections', 'public.memory_reconciliations',
    'public.memory_records', 'public.memory_settings', 'public.messages',
    'public.private_alpha_access_welcome_claims', 'public.private_alpha_access_welcome_deliveries', 'public.private_alpha_allowlist',
    'public.profile_photos', 'public.profiles', 'public.public_excerpt_snapshots',
    'public.route_receipts', 'public.run_context_packets', 'public.spaces',
    'public.strategies', 'public.usage_counters', 'public.visitor_usage_counters',
    'public.whatsapp_inbound_messages', 'public.whatsapp_link_codes', 'public.whatsapp_outbox',
    'public.whatsapp_reply_attempts', 'public.whatsapp_reply_days', 'public.whatsapp_reply_groups',
    'public.whatsapp_sender_links'
  ] LOOP
    IF NOT EXISTS (SELECT FROM pg_class WHERE oid = to_regclass(expected_table)
        AND relkind IN ('r', 'p') AND relrowsecurity) THEN
      RAISE EXCEPTION 'Expected table is missing or lacks RLS: %', expected_table;
    END IF;
  END LOOP;
  SELECT count(*) INTO actual FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public';
  IF actual <> 134 THEN RAISE EXCEPTION 'Expected 134 public policies, got %', actual; END IF;
  SELECT count(*) INTO actual FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'argus_private';
  IF actual <> 0 THEN RAISE EXCEPTION 'Expected zero private policies, got %', actual; END IF;
  SELECT count(*) INTO actual FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public' AND NOT EXISTS (
      SELECT FROM pg_depend d WHERE d.classid = 'pg_proc'::regclass AND d.objid = p.oid
        AND d.refclassid = 'pg_extension'::regclass AND d.deptype IN ('e', 'x'));
  IF actual <> 63 THEN RAISE EXCEPTION 'Expected 63 public functions, got %', actual; END IF;
  SELECT count(*) INTO actual FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'argus_private' AND NOT EXISTS (
      SELECT FROM pg_depend d WHERE d.classid = 'pg_proc'::regclass AND d.objid = p.oid
        AND d.refclassid = 'pg_extension'::regclass AND d.deptype IN ('e', 'x'));
  IF actual <> 99 THEN RAISE EXCEPTION 'Expected 99 private functions, got %', actual; END IF;
  IF EXISTS (
    SELECT id, name, public, file_size_limit, allowed_mime_types FROM storage.buckets
    EXCEPT SELECT * FROM (VALUES
      ('financial-document-sources'::text, 'financial-document-sources'::text, false, 10485760::bigint,
       ARRAY['application/pdf','image/jpeg','image/png','text/plain','text/csv',
         'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','application/xml',
         'text/xml','message/rfc822']::text[]),
      ('profile-images', 'profile-images', false, 1048576::bigint, ARRAY['image/webp']::text[])
    ) expected(id, name, public, file_size_limit, allowed_mime_types)
  ) OR (SELECT count(*) FROM storage.buckets) <> 2 THEN
    RAISE EXCEPTION 'Storage bucket definitions differ from the baseline';
  END IF;
END
$verify$;

SELECT version FROM supabase_migrations.schema_migrations ORDER BY version;
SELECT n.nspname AS schema_name, count(*) FILTER (WHERE c.relrowsecurity) AS rls_tables
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname IN ('public', 'argus_private') AND c.relkind IN ('r', 'p') GROUP BY 1 ORDER BY 1;
SELECT n.nspname AS schema_name, count(*) AS non_extension_functions
FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname IN ('public', 'argus_private') AND NOT EXISTS (
  SELECT FROM pg_depend d WHERE d.classid = 'pg_proc'::regclass AND d.objid = p.oid
    AND d.refclassid = 'pg_extension'::regclass AND d.deptype IN ('e', 'x'))
GROUP BY 1 ORDER BY 1;
SELECT 'PASS' AS result,
  (SELECT count(*) FROM supabase_migrations.schema_migrations) AS migration_versions,
  (SELECT count(*) FROM auth.users) AS auth_users,
  (SELECT count(*) FROM storage.objects) AS storage_objects,
  (SELECT count(*) FROM storage.buckets) AS storage_buckets,
  (SELECT count(*) FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname IN ('public', 'argus_private')) AS application_policies;
COMMIT;
