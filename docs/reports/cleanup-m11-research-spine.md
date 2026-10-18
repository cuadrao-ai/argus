# M11 research spine dependency audit

M11 table retirement is BLOCKED by the chat, memory, and guest features that the
founder explicitly keeps. The safe drop subset is empty. This PR supplies a
repeatable census and its evidence. It contains no retirement migration.

## Scope and authority

The October 17, 2026 cleanup instruction overrides the older proposal to remove
chat and memory. Chat, all memory, guest workspaces, authentication, access,
Business, Consumer, and receipt intake, extraction, review, and export remain
protected.

The supplied October 15 audit and October 16 squaring plan are research inputs.
Their age-based "alpha leftover" label does not establish dead code. Their M11
proposal depends on removing readers first. Removing a reader of a kept feature
would violate the current instruction.

The reviewed integration base is
`651870a54be4e5506dbb38f3902fef1a97eef8df`.
The branch is `codex/cleanup-m11-research-spine`.

## Staging evidence

The [catalog snapshot](evidence/cleanup-m11-research-spine/staging-census.json)
comes from staging project `skedzwocnmrhfigiwyzi` through Supabase MCP.
The catalog query ran at `2026-10-18T02:47:01.299883Z`.
Exact row counts came from a separate read-only transaction just after
`2026-10-18T02:44:15Z`. The two observations are not one atomic snapshot.

Both queries used `BEGIN READ ONLY` and `ROLLBACK`.
The catalog reported `transaction_read_only = on`.

| Observation | Result |
| --- | --- |
| Target tables present | 14 |
| Missing named targets | 0 |
| Exact rows in each target | 0 |
| Incoming or outgoing foreign keys | 50 |
| Direct target or row-type function matches | 19 |
| Relevant noninternal triggers | 12 |
| Dependent catalog views | 0 |

Nine triggers belong to target tables. Three additional triggers belong to kept
`conversations` and `messages` tables. Those triggers revoke public excerpts
when a conversation is purged, soft-deleted, or a message is deleted.

The complete foreign keys, signatures, and trigger definitions are in the
snapshot. Zero rows describe staging traffic. They do not prove that a reader is
dead or that a table can be removed.

## Reachable kept readers and writers

[API registration](../../src/argus/api/main.py) mounts the agent, backtest,
history, search, evidence, decisions, memory, sharing, and guest/authentication
routers. The paths below are present at the reviewed base. They establish code
reachability, not a claim that every hosted feature flag is enabled.

| Target | Current dependency | Disposition |
| --- | --- | --- |
| `backtest_jobs` | The mounted backtest and agent routers use durable job admission. `SupabaseGateway.create_backtest_job`, `admit_backtest_job`, and job hydration access this table. Conversation activity also reads jobs. | Blocked |
| `backtest_runs` | `persist_runtime_backtest_run` finalizes the run. History, search, result hydration, and source-sharing checks read it. | Blocked |
| `strategies` | `GET /history` reads legacy strategies. The direct backtest compatibility route calls `SupabaseGateway.get_strategy`. Current CRUD writers are retired, but these readers remain live. | Blocked |
| `collections` | `GET /history` calls `list_history_rows`. The Postgres history reader includes collections. | Blocked |
| `collection_strategies` | The Postgres history reader counts collection members. Guest handoff and replacement functions also reference this table. | Blocked |
| `context_packets` | Run persistence calls `persist_context_packet_records`, which calls the gateway writer and its owner check. Collection has a feature gate, but guest lifecycle functions also require the table. | Blocked |
| `run_context_packets` | The same persistence function calls `attach_context_packet_to_run`, which inserts the run attachment. Guest lifecycle functions also require the table. | Blocked |
| `route_receipts` | Agent settlement and title finalization call `persist_route_receipts`. Its gateway writer inserts the provider receipt. | Blocked |
| `cost_ledger_entries` | That receipt path calls `persist_openrouter_cost_ledger_entries`. Research and discovery evidence paths also call the gateway writer. | Blocked |
| `ideas` | Backtest evidence capture creates ideas. Search reads them. Memory confirmation verifies source ownership in `_confirmed_provenance` and `_source_is_owned`. | Blocked |
| `idea_versions` | Evidence capture writes versions. Memory confirmation checks the source version against the linked idea. | Blocked |
| `evidence_artifacts` | Mounted evidence/decision routes and completed-run finalization use artifacts. Memory confirmation locks and verifies their canonical provenance. | Blocked |
| `decision_notes` | Mounted decision routes save/read decisions. The saved-decision memory proposal and confirmation paths require them. | Blocked |
| `public_excerpt_snapshots` | Mounted evidence-receipt, public-receipt, and receipt-fork routes use the Postgres repository. It inserts snapshots and reads selected answers of several kinds. Kept conversation/message delete triggers revoke them. | Blocked |

The principal code owners for this map are:

- [Run persistence](../../src/argus/api/chat/persistence.py),
  [context persistence](../../src/argus/api/chat/context_packets.py), and
  [the Supabase gateway](../../src/argus/domain/supabase_gateway.py).
- [History route](../../src/argus/api/routers/history.py) and
  [Postgres history reader](../../src/argus/domain/postgres_history_reader.py).
- [Agent route](../../src/argus/api/routers/agent.py),
  [route receipt persistence](../../src/argus/api/chat/route_receipts.py), and
  [cost ledger](../../src/argus/observability/cost_ledger.py).
- [Memory confirmation route](../../src/argus/api/routers/personalization_memory.py),
  [memory service](../../src/argus/memory/service.py), and
  [Postgres provenance checks](../../src/argus/memory/postgres_store.py).
- [Sharing repository](../../src/argus/domain/supabase_public_excerpts.py) and
  [fork persistence](../../src/argus/domain/postgres_public_excerpt_forks.py).

### Guest functions also prevent a partial drop

`claim_expired_guest_workspaces(integer,boolean)` directly names 13 targets.
Its list excludes `public_excerpt_snapshots`.
`argus_private.claim_guest_workspace_handoff(uuid,text,uuid)` and
`replace_guest_conversation(uuid,text,text,text)` each name 11 targets.

The [guest gateway](../../src/argus/domain/supabase_guest_accounts.py) calls the
cleanup and replacement RPCs. Its handoff wrapper calls
`claim_guest_workspace_handoff_by_email`, which delegates to the private
handoff function. The mounted
[auth router](../../src/argus/api/routers/auth.py) invokes this handoff during
registration or account conversion. [Guest cleanup](../../src/argus/domain/guest_cleanup.py)
calls the cleanup RPC.

A table drop can therefore break a kept guest operation even when the ordinary
research route is idle. PL/pgSQL text references need not create catalog-level
relation dependencies. A successful `DROP TABLE RESTRICT` would not prove safety.

M2 was informed that all these tables and functions must remain. M11 edits no
shared API, gateway, memory method, or SQL function definition.

## Reproduce the census

Run [research_spine_census.sql](../../scripts/ops/research_spine_census.sql)
through the authorized staging SQL connector. It emits only catalog metadata.
It discovers any additional `backtest_*` tables, excludes indexes, and reports
missing named tables. The file wraps its query in a read-only transaction.

The function list includes body identifier matches and argument/return row-type
references. Body matches are conservative evidence. They can include comments
or string literals. Constructed dynamic identifiers and indirect function calls
require separate code inspection. The census does not certify an unreferenced
table as safe to drop.

[The local tests](../../tests/test_research_spine_cleanup.py) use an empty,
explicitly named local database. They verify dependencies on zero-row tables,
a kept-table foreign key, a kept-chat view and trigger, row-type-only function
arguments, missing targets, and index exclusion. They also inject an accidental
write and prove that PostgreSQL rejects it inside the read-only transaction.

```sh
ARGUS_RESEARCH_CENSUS_TEST_DSN='<isolated local DSN>' \
  python -m unittest tests.test_research_spine_cleanup -v
```

The test requires a loopback host and a database name beginning with
`cleanup_m11_`. It refuses an occupied public schema. It creates and removes
only synthetic fixture objects, without `CASCADE`.

## Archive and restore gate

Archive is NOT RUN. Scratch restore is NOT RUN. No paid scratch database was
created. No provider-side backup, storage manifest, or off-box copy was obtained.
There is no eligible drop candidate, so an archive does not unblock this PR's
retirement decision.

If a later authorized design removes the real kept dependencies, its operator
must complete the backup gate before any destructive merge or apply:

1. Verify the staging project and direct PostgreSQL connection in memory.
   A session-pooler export is not proof of the plan's direct-connection backup.
2. Set `umask 077`. Write a custom-format `pg_dump` outside Git with file mode
   `0600`. Include `public`, `argus_private`, `auth`, `storage`, and
   `supabase_migrations`. Record size and SHA-256. Export required roles and
   permissions separately, and check the archive's contents.
3. Record the provider backup or PITR timestamp. Copy storage file bytes
   separately from the database metadata, with a count, size, and hash manifest.
   Obtain explicit scope before any off-box upload.
4. Obtain the current scratch cost and Lucas's approval before a paid scratch
   branch or project is created. This report grants no such approval.
5. Restore into the approved scratch target. Require zero restore errors,
   matching counts, key-table checksums, schemas, constraints, indexes, RLS,
   functions, migration history, and storage file hashes. Record any warning.
6. Keep the founder's three-receipt acceptance gate closed until its independent
   evidence passes. Root alone controls merges and staging actions.
7. Use a new forward migration with explicit dependencies and bounded locks.
   Do not edit applied migrations or use blind `DROP CASCADE`.

Production remains outside this work's authority, including reads. The original
plan's production log check belongs to its authorized production operator.

## Verification and delivery

The local synthetic database run passed all four census tests on Python
`3.10.20`. The actual staging query completed in read-only mode.
No runtime behavior, prompt, migration, or environment file changed.

The Build the Lever principle produced the reusable SQL census. The test proves
that this census reports dependencies that an empty-row shortcut would miss.

Independent exact-head Eval and terminal PR CI are separate delivery gates.
This evidence PR does not mark M11 retirement READY. All 14 targets remain
excluded from any destructive migration.
