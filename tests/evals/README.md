# Business Eval Harness

This folder contains the Business eval harness. Cases live as data fixtures,
and the harness asserts typed runtime outcomes instead of exact assistant phrasing.

## Business E1 fixture gate

The separate Business corpus is in `business_cases/case_first_flow.yaml`.
Run `PYTHONPATH=src:web poetry run pytest tests/evals/test_business_eval.py -q --no-cov`
for free fixture validation and mutation checks. This command makes no model,
WhatsApp, or database calls. Its green result shows that the assertions detect
altered synthetic observations. It is not runtime or hosted evidence.

Each scripted step names its trusted actor, channel, source or command key,
owner message or human web command, and expected saved projection. The projection
checks draft count, revision, facts and fact source links, open questions,
durable action outcomes with actor, grant and issuer, visible sources, money
record count, bank and Personal balance deltas, and account versions. The adapter
must map generated database IDs to the fixture aliases. Human review writes a
`web_action` source and factual revision. Human approval writes an immutable
action receipt and approval result, without changing factual source history.

The Business capture adapter takes a case's ordered steps and trusted sender scope,
runs owner messages through the real LangGraph turn and declared Business
executor, and submits human web commands through BusinessActions. It uses an
isolated database namespace, then reads back the persisted dossier, action
receipts, MoneyService records and balances after each step. It must obtain
Business data through a current grant-scoped service projection. Direct
DataAPI reads cannot supply Business rows. It must also return OpenRouter route
receipts, exact candidate revision, model IDs, cost and latency. No fixture
expectation can serve as its observed state. The live E1 gate remains unavailable
until the Postgres capture passes and the root coordinator authorizes its call budget.
Owner-turn scorecards require the adapter's capture ID, database namespace,
actual LangGraph run ID, and matching candidate SHA before they can report a
pass. The human-only revoked-grant case requires its real scoped database
capture and zero model receipts; it has no LangGraph run or judge verdict. The
adapter reads actor, grant and issuer from scoped `business_action_receipts`
and reads bank balances and versions through the canonical MoneyService.

`business_runtime_capture.py` accepts an explicit loopback disposable Postgres
DSN and an injected interpreter factory. The separate scripted plans exercise
the real graph, executor, service, SQL receipts and MoneyService without provider
calls; they do not test model interpretation. With the current T1 and Actions
branches integrated and migrations applied, set `ARGUS_DISPOSABLE_DATABASE_URL`
and run `pytest tests/test_business_runtime_capture_postgres.py -q --no-cov`.
The test provisions and deletes only its own synthetic identities. A missing DSN
skips this integration test and supplies no runtime pass. Root owns any later
model-backed run and its call receipts, cost, latency and judge calibration.
The adapter pins a loopback Postgres host address and checks every fact field,
its source links, submitted source text, channel and kind, and factual revision
before/after state. Case inputs and earlier expected states define these checks;
runtime observations never fill expected values.
Approval persists an accepting version and then an accepted version, so an
approved draft moves from reviewed version N to current version N+2 while the
approval result still names N. Replay returns the original persisted `applied`
outcome. The capture compares SQL receipt identity and outcome, sources, factual
revisions, drafts, questions, and MoneyService readback before and after each
replay to prove that this returned outcome did not cause a second mutation.

Business fixture reconciliation (2026-10-11): the prior seven-case corpus digest
was `9509203afbe0ff9332d21ea9de8b548f31259a79af9acaa15e07aab0b61bdf4f`.
The current digest is `ae7f52c30847dde3587bbd2ac34a23089368150698f52de31714ac7293cef959`.
The approved clear-business-purpose rule already made A1's “para el negocio”
an owner-sourced all-business share. B1's “for our shop” now has the same
`message_b1`-sourced share; only its later missing-share blockers were removed.
Funding correction, missing date, mixed use and all Money assertions remain.
Intended-current human approvals read the authorized dossier version immediately
before submission; their authored expected versions 3 and 2 are still checked.
The deliberately stale version 1 stays literal, and an approval replay reuses
its original submitted version and command key without another dossier read.
The failed, unscored Luna capture on candidate `c938fea9dca33a20b7523adc76e83ee5ec66b32a`
retains the old fixture digest and is not retroactively measured against this one.

`business_eval.py` holds the deterministic comparator and a structured reply
rubric through the existing OpenRouter adapter. The fixed first judge is
`x-ai/grok-4.3`. `rubric_calibration.yaml` supplies known-good and known-bad
Spanish and English examples. Missing or skipped runtime and judge receipts
remain unavailable in the Business scorecard; fixture checks never produce a
live pass. The approved runtime candidates are `anthropic/claude-haiku-5.5`,
`openai/gpt-6-luna-pro`, and `deepseek/deepseek-v4.1-flash`. Catalog availability
does not measure their latency or reliability.
The judge-only stretch candidate is `anthropic/claude-sonnet-5.5`. It is
not a Business runtime candidate and must pass the same eight-case strict
calibration before it can judge a live Business scorecard.

For an authorized live run, keep a small `business_e1_request_settings_v1`
sidecar beside its scorecard. Record the executed candidate SHA, fixture digest,
rubric version, selected runtime and judge model IDs, and the actual redacted
outgoing request settings captured by the existing OpenRouter request guard for
each role. Include the returned model identifier only if the provider supplied
one, plus the route receipts and measured usage, cost, and latency. Do not infer
an internal model revision from the catalog ID or fill missing response fields.
Changing the judge requires the same unchanged calibration examples and strict
criterion comparison before a judge-backed scorecard can pass.

Calibration packet clarification (2026-10-11): the prior eight-example packet
has SHA-256 `a75f486ffd6b6adfff35e616dec70ec378d73dfba076a742b7fe1dd7034735e7`.
Its failed Grok, Haiku and Luna verdicts remain historical failures. The
revised fictional packets state a committed, source-linked draft revision and
successful dossier read explicitly; a version number alone never proves a
save. The unknown-amount example states a current direct grant for the named
accountant and an evidence-dependent human edit, without treating that edit as
approval. The fabricated-spend reply explicitly claims a canonical money
posting. The eight expected labels and rubric remain unchanged. Recalibration
must use the revised packet digest and cannot reuse any prior verdict.
The subsequent fictional-packet revision retains the failed packet with SHA-256
`75e990c6357335edb3dd69676dfcfa93dc5dd8dffe40457b072317601f724136`.
It changes only the final jargon example's reply to conditional accounting
questions, removing a presupposition that an accrual was authorized. Its
expected criteria and all prior failed Luna verdicts remain unchanged.

`business_acceptance.py` is the scoped initial Business measurement entry for
the same seven cases and 20 steps. It accepts an injected real interpreter,
an explicit loopback disposable Postgres DSN, the executed clean candidate SHA,
and a committed calibration report for the selected judge. Without passing
calibration it returns seven unavailable cases before any runtime or provider
call. A run captures each actual owner-step interpretation and reply route
receipt, including zero receipts on replay and human commands, and judges each
fresh saved reply. Its `business_acceptance_v1` report carries only Business
totals and the exact two Business prompt surface hashes. The companion
`business_e1_request_settings_v1` sidecar keeps redacted request parameters,
per-step receipts, graph IDs, saved states, SQL projections, and judge evidence.
These artifacts must retain the actual executed commit and observed usage;
they do not update or stand in for the legacy global measurement.

## Test Tiers

- **Mocked harness - every change (free, no API calls):**
  Run the single [Mocked Run command](#mocked-run) below. It validates Business
  fixtures, mutation detection, acceptance, invariants, runtime capture and variety.
  Fixture validation is not a live runtime scorecard.
- **Live eval - only the 3 sanctioned moments:**
  1. Pre-merge on a PR that changes runtime behavior.
  2. Main promotion candidate.
  3. After any model/provider change.
  These gates apply to the retained Business harness described above. They require
  explicit spend authorization; a mocked pass cannot substitute for a live result.
- **Browser QA is also real-API:** every turn spends tokens. Use it at gates, not
  per hypothesis.

## Mocked Run

```bash
PYTHONPATH=src:web OPENROUTER_API_KEY= poetry run pytest \
  tests/evals/test_business*.py -q --no-cov
```

This run is free. It does not call a model provider or a database. The separate
Business capture Postgres checks and their disposable-database requirement are
listed above. Keep the Business prompt-freeze checks in
`tests/test_interpreter_prompt_freeze.py` alongside runtime changes.

## Kept for the release-settings checks

The investing runtime evals are retired. `measurement_eval_scorecard.py`, its
`measurement_cases/` fixtures and `test_measurement_eval_scorecard.py` remain only
because the release-settings checks still exercise their configuration capture
and refusal behavior. They are not an investing eval tier or a runnable live
investing gate. The release-evidence support chain remains until those checks
are rewired to the existing release-configuration owner in a separate change.
