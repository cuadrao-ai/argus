# Cuadrao document preparation jobs

Status: implemented default-off on `claude/business-pilot-jobs` for #823. Not
enabled anywhere. No hosted service, flag or paid run changed.

## Problem

Preparation ran as a FastAPI background task; a dead task left the draft stuck
until an explicit `/prepare` or `/resume`, and nothing noticed while the API was up.

## Settings

`DocumentJobSettings` in `documents/config.py`, one name each, following the
`ARGUS_DOCUMENT_EXTRACTION_*` convention (shared true values, fails closed):
`ARGUS_DOCUMENT_JOBS_ENABLED` (default off), `ARGUS_DOCUMENT_JOBS_WORKFLOW_TASK`
and `ARGUS_DOCUMENT_JOBS_SWEEP_SECONDS` (default 30). Off, the routes
add `background_prepare` to FastAPI background tasks and a read marks an expired
attempt `needs_attention` (`document_preparation_interrupted`), exactly as before.
`test_flag_off_prepares_through_background_tasks_only` and the existing
`test_interrupted_attempt_needs_attention_without_automatic_retry` pin this.

## Dispatch

With the flag on, the route calls `PreparationJobs.start` before responding. It
records the attempt on the draft's checkpoint row, then hands it to a worker. A
closed client therefore cannot lose accepted intake: the draft and the attempt
are durable before the response, and a failed hand-off is re-dispatched by the
sweep. `start` does nothing while an attempt is in flight.

## Execution

- Hosted. A `prepare_document(connection_id, attempt_id)` task in the existing
  workflows service (`workflows/main.py`), dispatched through the existing
  `RenderWorkflowDispatcher` when `ARGUS_DOCUMENT_JOBS_WORKFLOW_TASK` (for
  example `argus-backtests/prepare_document`) is set in durable mode. The worker
  reads the owner from the stored row, never from the task input. Render retries
  are off: one task run is one attempt.
- Local. The same task under `render workflows dev` with `RENDER_USE_LOCAL_DEV`
  and `RENDER_LOCAL_DEV_URL`, as the backtest workflow already does. Without a
  task name (or in memory mode) the attempt runs as a task on the API's event
  loop. Both paths run the same `run_attempt`.

## Dead-worker detection

The reconciler sweep (`PreparationJobs.sweep`) runs inside the API process: once
at startup, then every `ARGUS_DOCUMENT_JOBS_SWEEP_SECONDS`. It does
not depend on a read, a restart, an operator or a cron. It reads drafts that are
`queued`, `preparing`, or `needs_attention` with a retry request, through a
partial index.

One oracle, `in_flight`, decides liveness:

- a live connection lease means a worker is running;
- a `queued` draft whose dispatch is younger than the window is waiting for a
  worker to claim it;
- anything else is dead.

The window is the existing connection lease (5 minutes). Extraction makes one
provider call with a 90 second timeout and no retries, so a live worker always
finishes or fails inside its lease. A dead worker is detected at most one window
plus one sweep interval after its last claim or dispatch. A worker that dies
after releasing its lease, such as a cancelled task, is detected on the next
sweep.

Documents reuse the backtest dispatch plumbing, not its read-driven cadence.

## Attempt and lease model

`financial_document_extractions.preparation_job` holds the current attempt:
`attempt`, `attempt_id`, `draft_version` (the queued draft it was dispatched
for), `dispatched_at`, `provider_call_started_at` and `retry`. One store call, `advance`, replaces it, and
optionally the draft, in one transaction. It refuses while a lease is live,
when the current attempt is not the expected one, or when the draft version
moved. A worker leases the connection and then checks that its `attempt_id`
is still current; a superseded attempt releases and exits before any provider
call. Because `advance` refuses a live lease, a reconciler cannot supersede an
attempt that has already claimed.

`advance` locks the connection row and compares the current `attempt_id`, so it
is the dispatch token: of several API instances sweeping at once, exactly one
supersedes an attempt and dispatches the next. The others' compare fails and
they dispatch nothing.

## Provider-call marker

After claiming and reading the source, and before calling the extractor, the
worker commits `provider_call_started_at` under its live lease and renews the
lease (`mark_provider_call`). No marker proves the provider was never reached.
An attempt may claim only the draft version it was dispatched for, and its
claim names it: the write that moves the draft to `preparing` also sets
`claimed` on that attempt's job. A flag-off writer's claim sets nothing.

## Retry and spend bounds

An expired attempt is never billed again automatically. The sweep decides:

- Dead and unclaimed, dead `preparing` whose claim names the current attempt
  (`claimed`, at `draft_version + 1`) with no marker, or a retryable failure
  reported before the marker: re-dispatch, at most `MAX_ATTEMPTS = 3` per
  explicit preparation. Past the bound: `document_preparation_interrupted`.
- Dead `preparing` with a saved preparation, whoever claimed it: re-dispatch,
  which replays delivery without a provider call or consent.
- Any other dead `preparing` draft (a marker, no job, or a claim that does not
  name the current attempt, such as a flag-off writer killed mid-call):
  `needs_attention` with `document_preparation_outcome_unknown`.
- After the sweep reads an attempt, a newer draft version refuses any re-dispatch;
  a marker refuses one except a saved-result replay (`unmarked=False`).
- A failure reported after the marker keeps its code and is not retried.

Automatic work never makes a second provider call for one explicit
preparation. Only a consented `/prepare` or `/resume` starts a new paid attempt
(document POST limits: 5 per minute, 30 per day).

## Stale-result rejection

Unchanged and reused. Saving a preparation, updating the draft and delivering
candidates all require the worker's own live lease. A worker whose lease expired
or was taken by a newer attempt cannot save, deliver or mark the draft. Saved
preparation is first-writer-wins, so a late result cannot replace it.

## Consumer compatibility

Routes, request headers, response bodies and statuses are unchanged. With the
flag on there is one new error code, `document_preparation_outcome_unknown`, and
an attempt that dies before the marker may return to `queued`. `/resume` on a dead
`preparing` draft answers 409 `document_busy` until the next sweep.

## Hosted cost (stated only, not activated)

- One Render Workflow task run per attempt, at most three per preparation, on
  the workflows service's default plan with a 240 second timeout.
- At most one vision call per explicit preparation through the existing
  OpenRouter key.
- One indexed query per API instance every 30 seconds. No new service.
- The workflows service would need `ARGUS_WORKFLOW_DATABASE_URL`,
  `ARGUS_DOCUMENT_EXTRACTION_ENABLED`, `ARGUS_VISION_MODEL`, the OpenRouter key,
  and `SUPABASE_URL` with `SUPABASE_SERVICE_ROLE_KEY` to read sources from the
  private Storage bucket (#778);
  the API would need `ARGUS_DOCUMENT_JOBS_WORKFLOW_TASK` and `RENDER_API_KEY`.

## Evidence

- `tests/ingestion/test_document_jobs_api.py`: a kill before the marker
  recovers inside the window with one provider call; a kill after the marker
  settles to `document_preparation_outcome_unknown` and only a consented retry
  makes the second call; late results refused; reported failures not retried;
  the bound; settings; flag off unchanged.
- `tests/test_document_jobs_postgres.py`: the same on real Postgres and
  Storage, two concurrent sweepers dispatching each attempt once, two running
  instances recovering a dead worker without restart, and the workflow worker.
