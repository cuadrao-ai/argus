# 135 conversations spin forever on a succeeded backtest job, 2026-09-04

The founder found 135 conversations in the sidebar with a permanent working
spinner. In production, 266 `backtest_jobs` rows have `status = 'succeeded'`
and `argus_private.backtest_job_result_hydrateable(j) = false`, all with
`operation_scope = 'chat.run_backtest'`, created between 2026-06-06 and
2026-09-04. The deployed rule maps "succeeded and not hydrateable" to
`operation.status = 'checking'` (`src/argus/domain/conversation_activity.py:166`),
and the client treats `checking` as a working lock.

This is the same defect class as #532, which added the `chat.research` branch
to the settle predicate. This report answers what breaks the run-and-evidence
chain for backtest jobs, whether it is one cause or several, why new rows
still land today, and what heals the existing ones.

All production reads were made read-only through the session pooler
(`default_transaction_read_only = on`), grouped and hashed; no user data left
the database.

## The chain, and where it breaks

The predicate needs `j.result_run_id` to name a `completed` run owned by the
job's user in the job's conversation, whose `conversation_result_card` carries
`evidence_artifact_id`, `idea_id`, `idea_version_id`, each matching a real
`evidence_artifacts` row for that run. Every one of the 266 rows breaks the
chain at exactly one of two links, and the link is read off
`execution_metadata` and `launch_payload` alone:

| Cause | Rows | Conversations | Created | Link that breaks |
|---|---|---|---|---|
| A. Run linked, never finalized | 119 | 117 | 2026-06-06 to 2026-07-12 | Run exists, `completed`, in the right conversation, card has title and rows, but **no idea / idea version / evidence artifact exists and the card has no identity keys** |
| B. Workflow proof row in a conversation | 147 | 18 | 2026-06-06 to 2026-09-04 | **`result_run_id` is null**; the row is the Render workflow runtime proof (`launch_payload.kind = render_workflow_proof`) |

No row breaks anywhere else: no user or conversation mismatch, no run in a
non-completed status, no artifact under a different id, no partial identity.
The 119 Cause A rows and the 147 Cause B rows are disjoint and add to 266.

### Cause A: the worker linked runs before the finalizer existed

The Render worker of #94 (`2cd3d9ad`, 2026-06-08) inserted `backtest_runs`
directly and marked the job succeeded through `link_backtest_job_result`.
The evidence spine landed 2026-06-19 and the shared finalizer,
`public.finalize_backtest_completion`, only with #201 (`e82382cd`,
2026-07-13, promoted 2026-07-14). Until that deploy every workflow-completed
chat run was a run without evidence.

Production agrees to the day: the last Cause A row was created 2026-07-12,
the first hydrateable `chat.run_backtest` job 2026-07-13, and none since
(69 succeeded chat jobs since then, all hydrateable). Cause A is closed at
the source and produces nothing new.

Ownership: 114 rows on the two admin accounts (109 conversations on the
automated-QA admin, June source `codex_validation`; 4 on the founder's
admin), 5 rows on two real users (3 in two live conversations from
2026-07-12, 2 in deleted conversations). 91 of the admin conversations and
2 real-user conversations are live and visible in a sidebar.

### Cause B: the workflow proof inherits the chat scope

`workflows/proof.py` seeds a proof job without an `operation_scope`, so the
column default `'chat.run_backtest'` applies, and the proof task then flips
the row `queued -> running -> succeeded` with no run, by design. To every
activity reader that is a finished chat backtest whose result cannot be
hydrated, so the conversation projects `checking` for as long as the row
exists. The seeder always sets `launch_payload.created_by = 'workflows.proof_cli'`
(148 rows: 143 succeeded, 5 failed on 2026-06-23).

**This is the only cause still producing rows.** `.github/canary-render.sh`
runs `warmup-render.sh`, which in `real-workflow` mode seeds one proof job and
dispatches `workflow_proof` on every run; the scheduled canary fires daily.
The newest row is from 2026-09-04 00:34Z (`nonce = warmup-1788482046-8781`,
`runtime_facts.provider_mode = live_provider`), in the stable proof
principal's conversation, which now holds 130 of them.

Nobody signs in as the proof principal (`example.invalid`), so those 130 rows
spin in no human sidebar. The 13 single-row proof conversations belong to
throwaway proof users (12 from the 2026-06-23 canary hardening, #125, and 1
from 2026-06-06), and the 4
proof-kind rows on the founder's admin account are from the 2026-06-06
proof-shadow configuration, where the API dispatched real chat jobs to the
proof task and the in-process run linked the result (`marked_succeeded = false`).
Those 4 conversations are deleted; 3 of the 4 rows link a run and heal with
Cause A, 1 has no run.

The tell, per AGENTS.md: the codebase already knows a proof is not a
backtest, in three places, all by `launch_payload.kind`
(`_assert_real_job` in the worker refuses it, `_is_undispatched_workflow_job`
and `fail_job_without_task_run` special-case it). The settle rule, the fourth
reader, could not see the kind and read the scope instead.

## Answer 1: why new rows still land

The canary's workflow proof, once per run. Not real chat runs: the worker
has finalized every chat run through the shared finalizer since 2026-07-14.

## The fix

The settle rule does not change. `JOB_RESULT_HYDRATEABLE` in
`argus.domain.job_settlement` is right for every row here: a succeeded chat
job without a readable run is not settled, and that reading is the alarm that
found this defect. What was wrong is that a proof row claimed to be a chat job
in a conversation. Loosening the rule to "a completed run exists" would make
every future half-finalized job settle silently, the failure #532's rule
exists to surface, and `docs/DATA_MODEL.md` already says an incomplete
finalization is not eligible for reload, history, or search.

So the proof stops being a conversation job:

- `workflows/proof.py` owns `PROOF_OPERATION_SCOPE = "workflows.proof"` and
  writes it explicitly, with no conversation. `ensure_proof_conversation`,
  `create_proof_conversation`, `DEFAULT_PROOF_CONVERSATION_ID`,
  `[removed obsolete setting]`, and `seed --conversation-id` are
  gone; the seed output carries `operation_scope` instead of a conversation.
  Every activity reader joins jobs to a conversation, so a proof row is
  unrepresentable as activity rather than filtered out of it; there is no
  scope list anywhere to keep in step.
- Migration `20260905000000_workflow_proof_jobs_leave_conversations.sql`
  admits the scope in `backtest_jobs_operation_scope_check` and reclassifies
  the seeder's rows by its own signature
  (`launch_payload ->> 'created_by' = 'workflows.proof_cli'`): scope
  `workflows.proof`, `conversation_id = null`. It touches scope and
  conversation only, never status or the result link, and replays as a
  no-op. Chat jobs a proof-shadow deployment sent to the proof task carry no
  seeder signature and keep their scope and conversation.
- Every scope value now has one owner, `argus.domain.backtest_job_scopes`;
  the writers that stamp a scope import it from there, and the migration's
  check constraint is rendered from its tuple.
  `tests/test_workflow_proof_jobs_migration.py` pins the migration's
  constraint to that rendering and the reclassification to the seeder's
  signature, and asserts the migration does not restate the settle function. `tests/test_backtest_job_write_invariant.py` classifies the
  migration as a writer that cannot attach a result or change status.
- `tests/test_workflow_proof_jobs_postgres.py` (disposable stack): a seeded
  proof job walked to `succeeded` never appears in
  `read_conversation_activity_sources`; a legacy-shaped proof row projects
  `checking`, the migration's statement as checked in moves it, the
  conversation projects `idle`, and a replay moves nothing; a proof-shadow
  chat row is left alone.

## Answer 2: what heals the existing rows

Two different answers, because the two causes break different links.

**Cause B (147 succeeded + 5 failed proof rows): the migration heals them.**
Reclassification makes the fact true, the way #532's migration did, without
touching the rule. After it, no proof row is in any conversation. The 19
empty "Render Workflow Proof" conversations remain as rows; deleting them is
a separate, destructive call.

**Cause A (119 rows, plus the 3 proof-shadow rows with a run): no predicate
change can heal them; a backfill is needed.** These runs have no evidence
identity to read. #532's heal worked because the research answer already
existed and only the rule could not see it; here the tuple does not exist.
The honest heal is to give each run the tuple it is owed through the same
finalizer every live path uses:
`scripts/ops/backfill_backtest_evidence.py`.

- Candidates are selected with the owner predicate itself
  (`not argus_private.backtest_job_result_hydrateable(j)`), narrowed to a
  linked, completed run in the job's conversation with no artifact.
- Each is finalized through `argus.domain.backtest_finalization.
  finalize_backtest_completion` with the stored run and card, which calls
  `public.finalize_backtest_completion` the way the worker calls it (the
  script's gateway extends `workflows.backtest_job.PostgresBacktestJobGateway`):
  it inserts the idea, idea version, and evidence artifact, enriches the card
  with the identity, and replays an existing tuple rather than duplicating
  one. The RPC's identity check replays the stored row field by field;
  `chart` and `trades` are plain JSON on every candidate, and no idea or
  artifact exists for any of them, so no unique constraint can collide.
- One coordinate: selection, the run read, the finalization, and the
  settlement re-check all run on the one `DATABASE_URL` connection, so no
  second URL can name a different project.
- After each write the same owner predicate is re-read; a tuple the rule
  still rejects is reported as `unsettled`, never hidden.
- Dry run by default, `--apply` writes, fail-closed target resolution like
  the other ops scripts (`DATABASE_URL` set explicitly in the process, host
  validated and announced, no dotenv discovery), idempotent on rerun.
- `tests/test_backtest_evidence_backfill_postgres.py` seeds a June-shaped job
  and run on the disposable stack, with generated values over two materially
  different run shapes (a chart-and-trades equity run; a crypto run with
  neither, a quick take, non-integer timestamps, tiny and negative metrics,
  and non-ASCII text), proves the predicate rejects it and the projection
  reads `checking`, runs the script's selection and finalization on one
  connection against the real RPC, and proves the predicate accepts it, the
  artifact and card identities agree, the stored payload replayed unchanged,
  the evidence title and digest derive from the card, the projection reads
  `result_hydrateable = true`, and a second pass finds nothing.

What the backfill changes for users: 122 runs become evidence (idea, idea
version, artifact) and appear in history, dossiers, and search for their
owners. 114 of them belong to the two admin accounts, 5 to two real users,
3 to deleted admin conversations. It writes user-visible evidence rows, so
running it is the founder's call; nothing in this branch runs it. The
alternative for the admin QA conversations is deletion, also a founder call.

One row has no heal: the proof-shadow row from 2026-06-06 with no run at
all, in a deleted conversation on the founder's admin account. It is
invisible and will stay `succeeded` without a result.

## What stays open

- `scripts/ops/alpha_readiness_metrics.py` counts recent `backtest_jobs`
  without a scope filter, so it has been counting the daily proof among
  backtests. Not changed here.
- In the proof-shadow configuration (`ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED`
  off with dispatch on), a real chat job is still sent to the proof task with
  the proof kind, and its settlement rides the in-process link. If that link
  never lands, the job reads `checking`, which is the correct alarm for a
  result that was never persisted durably. Production runs real workflow
  execution and has not taken this path since 2026-06-06.
- Migration classification: the constraint swap will label the migration
  `contract-replacing` in the production gate. The data statement is the
  healing step for Cause B and is safe on the deployed build, since the
  deployed activity readers already join jobs to conversations.

## Production facts (read-only, 2026-09-04)

| Query | Result |
|---|---|
| succeeded, not hydrateable, by scope | `chat.run_backtest`: 266 rows, 135 conversations, 2026-06-06 to 2026-09-04; `chat.research`: 0 of 7 |
| all succeeded `chat.run_backtest` | 335 rows, 69 hydrateable, first hydrateable 2026-07-13 |
| Cause A signature | `result_run_id` set, run `completed`, run user and conversation match, card lacks all three identity keys, no `idea_versions` or `evidence_artifacts` row for the run; `execution_metadata.workflow_backtest.kind = run_backtest_job` |
| Cause A runs | 119 of 119 have `config_snapshot`, `metrics`, `symbols`, card `title`, `rows`, `actions`; `chart` object and `trades` array on all; `strategy_id` null on all; 116 conversations hold an assistant message naming the job |
| Cause B signature | `result_run_id` null, `launch_payload.kind = render_workflow_proof`, `execution_metadata.workflow_proof` present; 148 rows carry `created_by = workflows.proof_cli` |
| proof rows by conversation | 130 in the stable principal's conversation (2026-06-23 to 2026-09-04), 13 single-row proof users (12 from 2026-06-23, 1 from 2026-06-06), 4 on the founder's admin account from 2026-06-06 (deleted conversations); 5 more failed proof rows from 2026-06-23 sit outside the succeeded set |
| human-visible | admin accounts: 91 live and 22 deleted Cause A conversations; real users: 2 live and 2 deleted |
| constraints | `backtest_jobs_operation_scope_check` lists three scopes; `operation_scope` default `'chat.run_backtest'`; reservation index is partial on non-null keys (2 of 152 proof rows carry a key, no collision on rescope) |
