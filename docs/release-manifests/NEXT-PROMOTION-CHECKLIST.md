# Next promotion: run the gates in this order

The ordered Cuadrao staging-to-production checklist is the launch runbook
section
[Cuadrao production promotion](../PRIVATE_LAUNCH_RUNBOOK.md#cuadrao-production-promotion).

- On promotion day, confirm `ARGUS_PUBLIC_ACCOUNT_ACCESS_ENABLED` is `true`
  on dashboard `cuadrao-api`. The check is the name and on/off only. Never set
  or change it on production without the founder's explicit approval. See
  [Dashboard checks (founder, at promotion)](../PRIVATE_LAUNCH_RUNBOOK.md#dashboard-checks-founder-at-promotion).
- Must-fix before `CUADRAO_AUTH_EMAIL_HOOK_ENABLED` is turned on in any
  environment. Do not change production from this item. The same steps are in
  [Auth email hook](../PRIVATE_LAUNCH_RUNBOOK.md#4-auth-email-hook).

  1. Leave the flag off. The Send Email hook schema in
     `web/server/emails/auth-actions.tsx` does not accept `invite` on
     `email_action_type`. With the hook enabled, Supabase hands every auth
     email to the hook, so an invite fails and nobody gets one.
  2. Before enabling, add `invite` to the hook schema and renderer. Use
     `/auth/confirm?token_hash=...&type=invite`. Add a test.
  3. Confirm that PR #1267 has landed, so the hook's signup and magic-link
     mails are code only.
  4. Read back that Supabase Authentication, Hooks, Send Email stays disabled
     until steps 2 and 3 are done.

This file remains the historical preparation checklist for eval identity,
local rehearsal, and spending records.

This is a preparation checklist, not a promotion manifest or permission to deploy.
The rehearsal report is [promotion-readiness](../reports/evidence/promotion-readiness/README.md).
Create the actual candidate record from [TEMPLATE.md](TEMPLATE.md).

## Decisions to settle before measuring

The founder owns these decisions. Record their answers in the candidate manifest.

1. **The release cut and landing method.** The active board's whole-roadmap rule
   still applies unless the founder grants another explicit exception. PR #603's
   exception and spending approvals do not carry forward. Name the exact proposed
   main commit, its parents, rollback build, release captain and approver.
2. **Sharing.** Choose both `ARGUS_EVIDENCE_RECEIPT_SHARING_ENABLED` and
   `NEXT_PUBLIC_EVIDENCE_RECEIPT_SHARING_ENABLED`. Both are `false` in the audited
   release profile and Blueprint. PR #632 landed with sharing still off. Enabling
   it needs an approved contract change and an enabled-surface browser walk.
   Freeze the choice before the live eval: code identity survives a profile-only
   edit, but measured flag identity does not. This lane changes neither file.
3. **Paid runs and separate caps.** Approve the required runs below, the target
   environment, a cap including unpriced-call reserve, and a stop rule. A reserve
   is not actual spend. No automatic paid retry, second full suite or judge replay.
4. **Migration handling.** Approve the exact SQL, maintenance and backup/readback
   plan for the three destructive classifications, and an expand/contract plan
   or maintenance window for the function replacement. Approve production access
   separately. The executable gate never applies SQL.
5. **Production operations and exposure.** Separately authorize production reads,
   migration application, main landing, three-service deployment and tester
   exposure. Keep all three deploy triggers manual. A green preparation PR does
   not authorize any of these operations.

### Required live work and budget inputs

These are historical planning estimates, not current price quotes or spending
authorization. Model mix, fixture count, research and retries change the bill.
Re-estimate from the first retained measurements before spending beyond the cap.

| Run | When required | Expected cost / budget input | Evidence and decision |
| --- | --- | --- | --- |
| Native full candidate eval | Every main candidate unless existing schema-v3 evidence passes both shared identity checks | Runbook measured $1.33 for 60 cases; current fixtures must be counted afresh. Budget roughly $1–3 for one run, not a guarantee. | Complete native scorecard, provider probe, actual configuration, clean measured SHA. Captain validates; founder owns disposition. |
| Native full deployed-build baseline | Candidate has any `failed` result | Another roughly $1–3; use its own native fixtures and matching provider modes. | Bind to the verified deployed rollback SHA, not merely today's `origin/main`. Compare case identities, not totals. |
| Targeted interleaved A/B | Each candidate-only failure whose prose judge has `pass=false` | At least 10 baseline/candidate pairs per case. Older gate estimate: $0.20; PR #603's research-heavy pair set added **$1.59195210498** tracked plus $0.12 reserve. Plan up to roughly $2 per such set before a separate cap. | Both native product paths, one live attempt at a time, same case, all attempts retained; actual defect counts and rates, per-side SHA/configuration. No judge-only substitute. |
| Feature browser walk | Candidate feature acceptance; include EN/es-419, mobile, reload and a non-buy-and-hold strategy where applicable | Prior promotion's initial/completion walk: $1.34063303874 tracked plus $0.24 reserve, under a separate $3 cap. New cut may cost more. | Visible expected/observed results and durable screenshots at the evidenced head. Founder-overseen acceptance is stronger than the eval. |
| Release-coherence canary | Exact deployed validation candidate, then production acceptance | Warmup dispatches paid workflow proof; welcome-email delivery also runs. Workflow compute and email costs are outside the LLM estimate; establish a separate limit. | Same service commit, config, effective workflow proof, disabled-signup denial and fresh welcome receipt. |
| Authenticated-browser canary | Exact deployed validation candidate, then production acceptance | Ordinary chat + backtest + sourced research; reserve roughly $0.25–1 for provider calls per journey, plus workflow compute. This is a planning allowance, not a measured canary price. | Dedicated least-privilege identity, sign-in attempts, three product checks, revocation and cleanup. |
| Historical acceptance replay / extra artifact-safety probes | Only if explicitly included in the founder's acceptance scope or required by changed controls | PR #603 replay: $1.70732 tracked plus $0.18 reserve, under $4. The two deliberate redaction probes incur their own canary work. | Historical approval does not authorize repeats. Record applicability, approval and cost separately. |

Sources: [runbook costs and A/B](../PRIVATE_LAUNCH_RUNBOOK.md#what-the-run-costs-measured),
[PR #603 final A/B and walk](2026-09-12-main-production-promotion.md#current-targeted-ab-and-step-7-gate-sharing-off).

## Ordered checklist

Commands below run from the candidate root unless they explicitly enter `web`.
`$CANDIDATE_SHA`, `$ROLLBACK_SHA`, `$MANIFEST`, `$SCORECARD` and `$MEASURED_SHA`
are operator-supplied values verified from Git and retained evidence. Use full
40-character SHAs. Do not source a production dotenv file for free checks.

| Order | Action and command | Evidence needed | Owner and failure condition |
| ---: | --- | --- | --- |
| 1 | Fetch `git fetch origin codex/private-alpha-next main`; inspect `git status --short`, `git log -1`, `git diff origin/main...origin/codex/private-alpha-next -- supabase/migrations render.yaml .github/private-alpha-release-profile.json`. | Approved cut, original/current integration SHAs, intervening semantic overlap and rollout scope. | Captain prepares; founder selects cut. Stop on unowned changes, missing lanes or an unapproved exception. |
| 2 | Resolve the exact would-be main commit using the approved landing method; `git show -s --format='%H %P' "$CANDIDATE_SHA"`; `git status --porcelain`. Start `$MANIFEST` from TEMPLATE. | Candidate SHA/parents, intended landing, rollback SHA, approved sharing values, spending limits. | Captain pins; founder approves. Dirty measurement tree, mutable ref or unidentified rollback blocks. |
| 3 | Prepare a **sibling checkout without `.env` or `web/.env.local`**. Verify `poetry run python --version`, `poetry --version`, `bun --version`; install locked dependencies as in `.github/setup.sh` if needed. | Python 3.10.20, Poetry 2.1.3, Bun 1.3.14; locked dependencies; no inherited live credentials. | Captain. Wrong interpreter, unpinned install or dotenv contamination invalidates local results. The installed python-dotenv may not honor `PYTHON_DOTENV_DISABLED`; file absence is the reliable boundary. |
| 4 | Run **Free commands** below: ownership, lint, merged-tree modularity, full backend, frontend lint/tests/build, storage-disclosure browser check, mocked evals, release/profile/canary contracts and prompt freeze. | Exit codes, counts/skips, exact checkout SHA, required CI results. | Captain. Any real failure blocks; classify harness/environment versus product. Do not fix product code in this preparation lane. |
| 5 | Rehearse all candidate migrations on disposable local Supabase with **Local database commands** below. Run the real PostgreSQL and anonymous-Auth matrices and their zero-skip guards. | Before/after reports, exact SQL/statement hashes, object readback, local-only target and cleanup. | Captain. Missing/name/content/unexpected drift blocks, even for additive SQL. Local pass is not production ledger or TLS proof. |
| 6 | `.github/local-smoke.sh --expected-sha "$CANDIDATE_SHA"` in the env-free checkout, with blank providers and dispatch off. | Health, readiness, starter prompts, web and workflow probe; env fingerprint. | Captain. Wrong SHA, startup failure, unexpected degraded check or enabled real workflow dispatch blocks. `--contract-only` is not the full smoke. |
| 7 | Run **Evidence identity preflight** below against every proposed candidate/baseline/A/B artifact. Read `.agent/interpreter_prompt_fingerprint.json`, but do not treat its frozen scorecard as current promotion evidence. | Schema v3 for candidate; recorded release configuration on every side; measured/build SHAs; fixture identity. | Captain. Missing configuration, wrong model/flag, changed reachable file, wrong fixture, dirty measurement or unrecorded measured SHA requires new evidence. Historical exemptions never apply to the new manifest. |
| 8 | Prepare and dry-test the native live driver, configuration recorder and cost monitor on both pinned trees before enabling providers. The current candidate command is under **Paid commands**. | Both sides can emit measured configuration before/after a run; the A/B driver accepts these SHAs and case; all Argus imports resolve inside the correct tree. | Captain. **The deployed pre-#629 harness emits no configuration.** Copying today's capture module into it changes measurement reach and its new embedding resolver is absent there. Prepare an external, ignored native-run observer, verify it offline, and retain its source/hash. Never backfill desired profile values into old evidence. |
| 9 | **Authorization boundary:** obtain explicit approval for the paid scope and target, then run one full candidate eval. Commit the native artifact under `docs/reports/evidence/`. | All cases exactly once, matching fixture digest, live holiday probe, actual models/flags, measured SHA, cost ledger. | Captain runs; founder approves spend. Missing measurements (`skipped`, `infrastructure_error`), unexpected passes or invalid provenance block. Preserve failures for comparison. |
| 10 | If candidate has failures, run the native baseline at `$ROLLBACK_SHA`; disposition every candidate-only failure. For each candidate-only prose failure run ten interleaved pairs and link both side documents. | Case-level comparison; typed defects with owners; measured defect rates and all attempt records for prose cases. | Captain explains; founder decides unresolved product regressions. Aggregate improvements, a case name alone or fewer than ten attempts cannot settle prose failures. Existing historical A/B drivers are hardcoded to PR #603 and must not be run unchanged. |
| 11 | Validate the **actual new manifest**, not only historical docs: `MANIFEST="$MANIFEST" poetry run python -c 'import os; from pathlib import Path; from tests.release_promotion_evidence_support import assert_main_promotion_live_eval_evidence; assert_main_promotion_live_eval_evidence(Path(os.environ["MANIFEST"]))'`; rerun release-doc tests. | Durable candidate/baseline/A/B paths, measured SHAs, rates and dispositions. | Captain. Any assertion blocks. Green historical manifests alone prove nothing about this candidate. The helper validates evidence structure; human review still owns whether a disclosed regression is acceptable. |
| 12 | Prepare an approved **isolated staging database**, apply the candidate schema there, and deploy the exact candidate to the branch-deployed staging/private-alpha services. Then complete the approved feature browser walk on that surface. Use its cut-specific script/matrix; retain EN/es-419, mobile, reload and strategy-shape evidence. `cd web && bun run test:e2e e2e/chat-action-recovery.spec.ts --project=chromium` where applicable. | Durable screenshots, visible text, failures, console status, cost and tested flags. Revalidate if head changes. | Founder-overseen acceptance. If staging shares the production database, stop and obtain an isolated validation target before applying SQL. Green mocked browser tests do not substitute for this real-API work. Sharing off means the off-surface checks; sharing on requires the full share/create/revoke/public-read walk. |
| 13 | On the staging deployment accepted in step 12, run both canary surfaces below **before any production read or schema mutation**. | All three service SHAs, API/web/workflow env fingerprints, workflow ready-version proof, local smoke, warmup and both canary JSON/exit files. | Captain/operator with founder deployment authority. Never silently use production URLs as staging; target must be explicit. Any service mismatch, red guard, missing check, failed revocation or cleanup blocks. |
| 14 | **Production-read boundary:** after explicit approval, run the production migration CLI below before any production deploy-capable operation. | Exact candidate, verified production project/TLS, full ledger comparison, safety classification, historical reconciliation fingerprints. | Operator reads; founder approves handling. Nonzero exit stops promotion. No production Blueprint sync, env sync or service deploy first. |
| 15 | Human applies only approved missing files in repository order, under the approved maintenance/compatibility plan; read back ledger and affected objects; rerun the same gate. | Before/after statement arrays and hashes, classification decision, backup/readback and rollback plan. | Founder/operator. Gate must return `status=pass`; no production code deployment while a required function/check is missing. Do not narrow receipt checks after new-kind/readout rows exist. |
| 16 | Refresh integration; reconcile one way, inspect overlap and run modularity against the would-be merged tree. Get all required CI green and a clean Codex review at the final head, with zero unresolved threads. | Original/current integration SHA, reconciliation SHA, retained/invalidated evidence, exact PR head, terminal checks/review link. | Captain. Do not rebase published evidence or re-request unchanged-head reviews. This preparation lane stops here, without merging. |
| 17 | For the later authorized promotion only: founder lands the pinned candidate; rerun migration gate with `--verify-landed-ref origin/main`. | Gate proves exact landed SHA and repeats production ledger parity. | Founder/operator. Any new merge/squash/rebase/conflict edit or concurrent main movement invalidates the prior exact-SHA migration report. Regate the landed commit before deploy. Eval carry-forward remains the separate shared identity decision. |
| 18 | Only after schema pass: reconcile approved config if necessary, deploy `argus-api`, then `argus-app`, then `argus-backtests`; run status, audit, warmup and both canaries again for production. | Exact service commits/ready workflow version, manual triggers, effective live-provider proof, sanitized artifacts. | Founder/operator. No partial-service success; branch-harness dispatch against old production is not candidate deployment proof. |
| 19 | Finish every TEMPLATE section and the post-deploy decision; preserve failures and cleanup proof. Check the first scheduled canary after promotion for #614. | Candidate, live eval, migration, deploy, environment, gate, release decision and privacy fields; tester-exposure approval. | Founder gives go/no-go. Missing acceptance or a red scheduled follow-up remains owned; no automatic tester invitation. |

## Free commands

Run these in the sibling checkout with no dotenv files. Empty all provider keys;
keep the synthetic market-data mode. The full backend run includes the mocked
eval list in `tests/evals/README.md`, prompt-freeze and the release-doc tests.
The explicit focused command is useful first so release failures appear early.

```bash
export OPENROUTER_API_KEY= ARGUS_PROD_OPENROUTER_API_KEY=
export ARGUS_GUEST_ACCESS_OPENROUTER_API_KEY= PERPLEXITY_API_KEY=
export ALPACA_API_KEY= ALPACA_SECRET_KEY= ARGUS_APPROVAL_EMAIL_SMTP_PASSWORD=
export ARGUS_RUN_LIVE_EVALS=0 ARGUS_MARKET_DATA_PROVIDER_MODE=synthetic_unit_fixture
poetry run python .agent/scripts/ownership/verify_branch_ownership.py
poetry run ruff check src tests workflows scripts
poetry run python scripts/check_modularity_budget.py
poetry run python .github/private-alpha-release-profile.py validate
poetry run python .github/private-alpha-release-profile.py hash
poetry run pytest tests/test_private_alpha_release_docs.py \
  tests/test_promotion_evidence_identity.py tests/test_promotion_evidence_configuration.py \
  tests/test_release_promotion_evidence_support.py \
  tests/test_private_alpha_release_profile.py tests/test_render_release_profile_contract.py \
  tests/test_interpreter_prompt_freeze.py tests/test_local_smoke_contract.py \
  tests/test_canary*.py tests/test_private_alpha_canary_split.py \
  tests/test_render_canary_script.py scripts/ops/tests/test_production_migration_gate.py \
  -q --no-cov
poetry run pytest tests -q --no-cov
(cd web && bun run lint && bun test && bun run build)
(cd web && bunx playwright test e2e/browser-storage-disclosure.spec.ts)
```

The ordinary suite deliberately skips opt-in live/DB tests. This is acceptable
only alongside the separate required local matrices below. Never set live-eval
flags just to remove these skips. CI's required `ci` rollup includes ownership,
backend, frontend and guest-release-gates; also inspect the runtime-regression,
local-smoke and any other required checks returned by `gh pr checks "$PR"`.

## Local database commands

Use a new sibling directory containing only the candidate's `supabase/` tree;
give it a unique `project_id` and unused ports in its **local copy** of
`config.toml`. Do not copy `.temp/project-ref`. Never use `--linked` or a hosted
`--db-url`. Confirm ownership before resetting or stopping anything.

```bash
supabase --workdir "$LOCAL_STACK" start
supabase --workdir "$LOCAL_STACK" db reset --local --version 20260911214608 --no-seed
# Export only the disposable loopback DSN from this stack's local status.
PYTHONPATH=. poetry run python docs/reports/evidence/promotion-readiness/rehearse_migrations.py \
  --candidate-sha "$CANDIDATE_SHA" --output temp/release-evidence/local-before.json
supabase --workdir "$LOCAL_STACK" db reset --local --no-seed
PYTHONPATH=. poetry run python docs/reports/evidence/promotion-readiness/rehearse_migrations.py \
  --candidate-sha "$CANDIDATE_SHA" --output temp/release-evidence/local-after.json
poetry run pytest scripts/ops/tests/test_production_migration_gate.py -q --no-cov
poetry run pytest tests/test_*_postgres.py -q --no-cov --junitxml=temp/postgres.xml
poetry run python scripts/qa/assert_pytest_gate.py temp/postgres.xml
poetry run pytest tests/test_guest_auth_local_supabase.py -q --no-cov --junitxml=temp/auth.xml
poetry run python scripts/qa/assert_pytest_gate.py temp/auth.xml
supabase --workdir "$LOCAL_STACK" stop --no-backup
```

The rehearsal adapter requires `ARGUS_DISPOSABLE_DATABASE_URL` with an IP-literal
loopback host. It calls the production gate's reader and comparator, replacing
TLS only in its explicitly local connection adapter; it never calls the
production CLI. A fresh local ledger has different historical fingerprints from
the reconciled production ledger, so it cannot certify that production check.
The CLI itself intentionally has no local-target bypass.

For the CI matrices also export `ARGUS_LOCAL_SUPABASE_URL`,
`ARGUS_LOCAL_SUPABASE_ANON_KEY` and `ARGUS_LOCAL_SUPABASE_SERVICE_ROLE_KEY` from
that stack's status, as `.github/workflows/ci.yml` does. Keep pytest and the
zero-skip guard chained with `&&` in automation: the guard checks collection and
skips, while pytest's exit code owns failed assertions.

### Migration inventory since the recorded PR #603 deployment

This is a repository delta, not a current production ledger read. All four are
now landed. Re-enumerate at the final cut; an earlier cutoff is only a rehearsal.

| Migration | Gate classification / requirement | Why and what to inspect |
| --- | --- | --- |
| `20260912190000_share_calculation_receipts.sql` | `destructive`; `maintenance_backup_and_founder_approval_required` | Drops/recreates `public_excerpt_snapshots_kind_check`, admitting calculation. The comment says additive, but the gate sees `DROP`. Review existing kinds and lock/rollback behavior. |
| `20260913213100_admit_readout_route_receipt_tier.sql` | `destructive`; same requirement | Drops/recreates `route_receipts_tier_check`, admitting readout. Preserve the wider check on old-code rollback once readout rows exist. |
| `20260913230000_release_research_guest_claim.sql` | `contract-replacing`; `expand_contract_or_maintenance_required` | Replaces `claim_research_usage`, adds/replaces `release_research_usage` and resets grants. Check signatures, service-role-only EXECUTE, guest refund behavior and retained global charge. Function bodies are not top-level destructive SQL. |
| `20260914120000_share_plain_answer_receipts.sql` | `destructive`; same requirement | PR #632, merge `c8e05b4f459c2f305016f595d8f4a7540bf06046`. Drops/recreates the same excerpt kind check to admit plain `answer`; follows the calculation migration. Sharing remains off until separately approved. |

Do not rewrite SQL or weaken classification to get an additive label. Human
review distinguishes widening a constraint from deleting customer data, while
the gate's required approval and maintenance path still applies.

## Evidence identity preflight

This code uses the canonical owners; do not maintain a second product-path list.
Run it for candidate scorecard → candidate, baseline → rollback, and each A/B
side → its build. Supply the corresponding JSON as `$SCORECARD` each time.

```bash
export SCORECARD MEASURED_SHA CANDIDATE_SHA
poetry run python - <<'PY'
import json, os
from pathlib import Path
from tests.promotion_evidence_identity import assert_measurement_stands_for
root = Path.cwd()
document = json.loads(Path(os.environ['SCORECARD']).read_text())
measured = document['provenance']['candidate_sha']
assert measured == os.environ['MEASURED_SHA']
assert_measurement_stands_for(
    measured, Path('next-candidate.md'), evidence=os.environ['SCORECARD'],
    measured_sha=measured, shipped_sha=os.environ['CANDIDATE_SHA'],
    repository_root=root,
    release_configuration=document['provenance'].get('release_configuration'),
)
PY
```

The API service of the committed profile owns the key set: all `_MODEL` keys
and all explicit boolean-string values. Measurement records actual resolved
models and explicit flags, not desired values. Web/workflow values and other
API settings still require release-config/canary proof. The same SHA cannot
waive configuration mismatch. Evidence scripts under docs may be carried
forward, but importing new Python under tests/src/scripts changes reach.

## Paid commands: later approval required

Unset the free-run overrides in a separate clean process. Supply an ignored,
untracked env file whose entire path avoids tracked symlinks. Export the reviewed
configuration before import; do not rely on dotenv to override existing values.

```bash
ARGUS_RUN_LIVE_EVALS=1 ARGUS_EVAL_ENV_FILE="$LIVE_ENV_FILE" \
ARGUS_MARKET_DATA_PROVIDER_MODE=live_provider ARGUS_ASSET_PROVIDER_MODE=live_provider \
poetry run pytest tests/evals/test_measurement_eval_live.py -q --no-cov
```

Use that native command in each side's pinned checkout for full suites. A
pre-#629 baseline additionally needs the independently prepared configuration
observer from step 8. There is no generic, current ten-pair CLI in the repo:
the retained PR #603 scripts pin old SHAs, paths, fixture counts and budgets.
Before paid approval, prepare the case-specific external driver, record its
literal invocation in the manifest and pass step 8. This is a preparation
dependency, not permission to improvise a paid run mid-promotion.

## Production commands: outside this preparation lane

After explicit authorization, use the operator's existing session-pooler URL
and an absolute readable production CA. Do not print credentials or pass the
DSN on the command line. Keep the exact candidate checked out and tracked-clean.

```bash
poetry run python scripts/ops/production_migration_gate.py \
  --candidate-sha "$CANDIDATE_SHA" --output temp/release-evidence/migration-gate.json
# After the founder lands that exact commit:
poetry run python scripts/ops/production_migration_gate.py \
  --candidate-sha "$CANDIDATE_SHA" --verify-landed-ref origin/main \
  --output temp/release-evidence/migration-gate-landed.json
```

Required environment: `ARGUS_PRODUCTION_DATABASE_URL` and
`ARGUS_PRODUCTION_DATABASE_SSL_ROOT_CERT`. Exit 0 means comparison passed;
exit 1 means parity blocked; exit 2 means execution/evidence-write failure.
All are read-only, verified TLS, no migration application. Preserve each report.

After approved deployment, use:

```bash
.github/render-env-sync.sh api-deploy-status
.github/render-env-sync.sh web-deploy-status
.github/render-env-sync.sh workflow-version-status
.github/render-env-sync.sh release-config-audit --expect-mode real-workflow
.github/warmup-render.sh --expect-mode real-workflow
ARGUS_CANARY_SURFACE=release-coherence ARGUS_CANARY_SHA="$CANDIDATE_SHA" \
ARGUS_CANARY_HARNESS_SHA="$CANDIDATE_SHA" \
ARGUS_CANARY_LOCAL_RUN_NONCE="$(poetry run python -c 'import secrets; print(secrets.token_hex(12))')" \
ARGUS_CANARY_EVIDENCE_PATH=temp/release-evidence/release-coherence.json \
ARGUS_CANARY_CAPTURE_PATH=temp/release-evidence/release-coherence-capture.json \
.github/canary-render.sh
ARGUS_CANARY_SURFACE=authenticated-browser-journey ARGUS_CANARY_SHA="$CANDIDATE_SHA" \
ARGUS_CANARY_HARNESS_SHA="$CANDIDATE_SHA" \
ARGUS_CANARY_EVIDENCE_PATH=temp/release-evidence/authenticated-browser.json \
ARGUS_CANARY_CAPTURE_PATH=temp/release-evidence/authenticated-browser-capture.json \
.github/canary-render.sh
```

Local nonce mode requires GitHub run identity variables to be absent. For a
validation deployment set explicit approved app/API targets and operator secrets;
the script defaults otherwise point at production. Read the canary's per-check
statuses and both exit codes. Preserve sanitized captures on failure and replay
locally with `poetry run python scripts/ops/canary_capture_replay.py "$CAPTURE"`
only when the capture contains a final response. Do not spend a second journey
to obtain evidence the first run should already have retained.

Authority: [runbook](../PRIVATE_LAUNCH_RUNBOOK.md),
[release discipline](../specs/private-alpha-ci-cd-sota.md),
[active board](../specs/argus-answers-that-stay-true-roadmap.md),
[manifest template](TEMPLATE.md), `.github/workflows/ci.yml`,
`.github/workflows/private-alpha-smoke.yml`, `.github/workflows/private-alpha-canary.yml`,
`tests/promotion_evidence_identity.py`, `tests/promotion_evidence_configuration.py`,
`tests/release_promotion_evidence_support.py`, and `scripts/ops/production_migration_gate.py`.
