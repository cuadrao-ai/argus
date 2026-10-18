BEGIN READ ONLY;

WITH expected_targets(relname) AS (
    VALUES
        ('backtest_jobs'), ('backtest_runs'), ('strategies'), ('collections'),
        ('collection_strategies'), ('context_packets'), ('run_context_packets'),
        ('route_receipts'), ('ideas'), ('idea_versions'), ('decision_notes'),
        ('evidence_artifacts'), ('public_excerpt_snapshots'), ('cost_ledger_entries')
),
targets AS (
    SELECT c.oid, c.reltype, c.relname, c.relrowsecurity
    FROM pg_catalog.pg_class AS c
    JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relkind IN ('r', 'p')
      AND (
          c.relname ~ '^backtest_'
          OR c.relname IN (SELECT relname FROM expected_targets)
      )
),
function_matches AS (
    SELECT p.oid, p.oid::regprocedure::text AS function_name,
           jsonb_agg(t.relname ORDER BY t.relname) AS matched_targets
    FROM pg_catalog.pg_proc AS p
    JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
    JOIN targets AS t ON (
        p.prosrc ~ ('\m' || t.relname || '\M')
        OR t.reltype = ANY(p.proargtypes::oid[])
        OR t.reltype = p.prorettype
    )
    WHERE n.nspname IN ('public', 'argus_private')
    GROUP BY p.oid
)
SELECT jsonb_build_object(
    'captured_at', CURRENT_TIMESTAMP,
    'database', current_database(),
    'read_only', current_setting('transaction_read_only'),
    'missing_targets', (
        SELECT coalesce(jsonb_agg(e.relname ORDER BY e.relname), '[]'::jsonb)
        FROM expected_targets AS e
        WHERE NOT EXISTS (SELECT 1 FROM targets AS t WHERE t.relname = e.relname)
    ),
    'tables', (
        SELECT coalesce(jsonb_agg(
            jsonb_build_object('table', relname, 'rls_enabled', relrowsecurity)
            ORDER BY relname
        ), '[]'::jsonb)
        FROM targets
    ),
    'foreign_keys', (
        SELECT coalesce(jsonb_agg(jsonb_build_object(
            'name', c.conname,
            'source', c.conrelid::regclass::text,
            'target', c.confrelid::regclass::text,
            'definition', pg_get_constraintdef(c.oid)
        ) ORDER BY c.conrelid::regclass::text, c.conname), '[]'::jsonb)
        FROM pg_catalog.pg_constraint AS c
        WHERE c.contype = 'f'
          AND (
              c.conrelid IN (SELECT oid FROM targets)
              OR c.confrelid IN (SELECT oid FROM targets)
          )
    ),
    'views', (
        SELECT coalesce(jsonb_agg(DISTINCT jsonb_build_object(
            'view', v.oid::regclass::text, 'target', t.relname
        )), '[]'::jsonb)
        FROM pg_catalog.pg_depend AS d
        JOIN pg_catalog.pg_rewrite AS r ON r.oid = d.objid
        JOIN pg_catalog.pg_class AS v ON v.oid = r.ev_class
        JOIN targets AS t ON t.oid = d.refobjid
        WHERE d.classid = 'pg_rewrite'::regclass
          AND d.refclassid = 'pg_class'::regclass
          AND v.relkind IN ('v', 'm')
    ),
    'triggers', (
        SELECT coalesce(jsonb_agg(jsonb_build_object(
            'table', t.tgrelid::regclass::text,
            'name', t.tgname,
            'function', t.tgfoid::regprocedure::text,
            'definition', pg_get_triggerdef(t.oid)
        ) ORDER BY t.tgrelid::regclass::text, t.tgname), '[]'::jsonb)
        FROM pg_catalog.pg_trigger AS t
        WHERE NOT t.tgisinternal
          AND (
              t.tgrelid IN (SELECT oid FROM targets)
              OR t.tgfoid IN (SELECT oid FROM function_matches)
          )
    ),
    'functions', (
        SELECT coalesce(jsonb_agg(jsonb_build_object(
            'function', function_name, 'matched_targets', matched_targets
        ) ORDER BY function_name), '[]'::jsonb)
        FROM function_matches
    )
) AS census;

ROLLBACK;
