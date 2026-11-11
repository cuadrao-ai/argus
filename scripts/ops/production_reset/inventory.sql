BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '120s';

SELECT current_database() AS database_name, current_user AS database_role;
SELECT 'auth.users' AS relation, count(*) AS row_count FROM auth.users
UNION ALL SELECT 'auth.identities', count(*) FROM auth.identities
UNION ALL SELECT 'auth.sessions', count(*) FROM auth.sessions
UNION ALL SELECT 'storage.buckets', count(*) FROM storage.buckets
UNION ALL SELECT 'storage.objects', count(*) FROM storage.objects
UNION ALL SELECT 'supabase_migrations.schema_migrations', count(*)
FROM supabase_migrations.schema_migrations;
SELECT 'cron.job' AS relation, to_regclass('cron.job') IS NOT NULL AS installed,
       CASE WHEN to_regclass('cron.job') IS NOT NULL THEN
         (xpath('/row/row_count/text()', query_to_xml(
           'SELECT count(*) AS row_count FROM cron.job', false, true, '')))[1]::text::bigint
       END AS row_count;

SELECT n.nspname AS schema_name, c.relname AS relation_name, c.relkind,
       (xpath('/row/row_count/text()', query_to_xml(
         format('SELECT count(*) AS row_count FROM %I.%I', n.nspname, c.relname),
         false, true, '')))[1]::text::bigint AS row_count
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname IN ('public', 'argus_private') AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
ORDER BY n.nspname, c.relname;

SELECT e.extname, e.extversion, n.nspname AS extension_schema
FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace ORDER BY e.extname;
SELECT version, name FROM supabase_migrations.schema_migrations ORDER BY version;
SELECT b.id AS bucket_id, count(o.id) AS object_count
FROM storage.buckets b LEFT JOIN storage.objects o ON o.bucket_id = b.id
GROUP BY b.id ORDER BY b.id;
SELECT n.nspname AS schema_name, p.oid::regprocedure::text AS function_identity
FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname IN ('public', 'argus_private') AND NOT EXISTS (
  SELECT FROM pg_depend d WHERE d.classid = 'pg_proc'::regclass AND d.objid = p.oid
    AND d.refclassid = 'pg_extension'::regclass AND d.deptype IN ('e', 'x'))
ORDER BY 1, 2;

SELECT n.nspname AS table_schema, c.relname AS table_name, t.tgname AS trigger_name,
       t.oid AS trigger_oid, t.tgisinternal AS internal_trigger,
       con.oid AS constraint_oid, con.conname AS logical_constraint_name,
       fn.nspname AS function_schema, p.oid::regprocedure::text AS function_identity,
       CASE
         WHEN n.nspname IN ('public', 'argus_private') THEN 'drop with app object'
         WHEN t.tgrelid = 'auth.users'::regclass AND t.tgisinternal
           AND con.contype = 'f' AND sn.nspname IN ('public', 'argus_private')
           AND con.confrelid = 'auth.users'::regclass THEN 'drop with app foreign key'
         WHEN t.tgrelid = 'auth.users'::regclass AND NOT t.tgisinternal
           AND fn.nspname IN ('public', 'argus_private') AND p.proname = t.tgname AND p.pronargs = 0
           AND t.tgname = ANY(ARRAY['bind_guest_signup_handoff', 'business_auth_retention_guard',
             'business_fiscal_actor_retained', 'business_invitation_auth_retention',
             'finalize_linked_guest_identity', 'refuse_placeholder_email']) THEN 'drop approved app trigger'
         WHEN t.tgrelid = 'auth.users'::regclass AND fn.nspname NOT IN ('public', 'argus_private')
           THEN 'retain platform trigger; review unexpected definitions'
         ELSE 'STOP: unapproved external dependency'
       END AS reset_action
FROM pg_trigger t
JOIN pg_class c ON c.oid = t.tgrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_proc p ON p.oid = t.tgfoid
JOIN pg_namespace fn ON fn.oid = p.pronamespace
LEFT JOIN pg_constraint con ON con.oid = t.tgconstraint
LEFT JOIN pg_class source ON source.oid = con.conrelid
LEFT JOIN pg_namespace sn ON sn.oid = source.relnamespace
LEFT JOIN pg_class referenced ON referenced.oid = con.confrelid
LEFT JOIN pg_namespace rn ON rn.oid = referenced.relnamespace
WHERE n.nspname IN ('public', 'argus_private')
   OR t.tgrelid = 'auth.users'::regclass
   OR fn.nspname IN ('public', 'argus_private')
   OR sn.nspname IN ('public', 'argus_private')
   OR rn.nspname IN ('public', 'argus_private')
ORDER BY n.nspname, c.relname, t.tgname;

SELECT e.evtname AS event_trigger, e.evtevent, e.evtenabled,
       e.evtfoid::regprocedure::text AS function_identity
FROM pg_event_trigger e ORDER BY e.evtname;
COMMIT;
