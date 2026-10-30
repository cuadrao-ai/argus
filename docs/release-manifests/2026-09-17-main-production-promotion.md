# 2026-09-17 production promotion

## Candidate

- Candidate SHA: `2523e3a3dcb64fc713d978cc0e503904373de307`
- Candidate branch: `codex/production-promotion-20260917`
- Approved integration cut / original fetched integration: `cfc1988dd80ca1a8007b8f336c107700dd57e009`.
- Last fetched integration: `cfc1988dd80ca1a8007b8f336c107700dd57e009`.
- Last fetched main: `3d189204c6a685b7f3bb1818b38e34a33d1f10de`.
- Reconciliation: none needed at preparation. The would-be merged tree is exactly the candidate tree, `ff4b5e46d3c39b8925c0c54c810227a77ca2ba8f`; modularity passes on that tree.
- Checkpoint semantics: this SHA pins the reviewed code-plus-evidence checkpoint, not the commit that subsequently publishes this manifest update. The native eval measured `3cecda6933399e53f6ea00edc8004a88d7eefad4`; only documentation/evidence changed between it and this checkpoint. No descendant is implicitly deploy-cleared. Before deployment, record and gate the exact landed `origin/main` SHA, then bind each service readback to that SHA.
- Scope: the whole approved roadmap cut, plus sharing configuration and promotion evidence. No product code or migration SQL changed in this task.
- Validation status: Live comparison complete; founder explicitly accepted both candidate-only typed failures after reviewing their concrete effects. Founder replaced hosted staging with the disposable Docker validation below and explicitly directed a stop before production schema changes. Local sharing follow-up failed; no production migration, main promotion, or deployment performed.
- Validation surface: local deterministic checks and native provider-backed evals. No separate hosted staging surface was found.
- Promotion target: `main`, through a PR with required `ci` green; all service deploys remain manual.
- Release captain: Codex. Approver: founder, explicit task instruction on 2026-09-17.
- Rollback target: `3d98057c1e722317f0243fb96fb647771ddae484`.

Founder decisions: sharing ON; all four pending migrations approved after backup, without a maintenance window; no spend cap on promotion runs; disable Private Alpha Canary and close #614 as not fixed; deploy all three services, then perform the signed-out sharing walk. Never git stash.

Latest founder direction: skip provisioning staging services, use disposable local Supabase in Docker, apply/read back the four migrations, run exact `cfc1988d` with sharing ON, perform one English sharing/follow-up walk and one Spanish page, skip step 13 canaries, then tear down and stop before production schema changes. This replaces the pending staging question for this task; it is not hosted deployment clearance. The PR-managed, data-free Supabase preview remains attached to PR #655 and was not used for this walk.

## Production authorization after local acceptance

Founder accepted the local walk and explicitly resumed production promotion on 2026-09-17 (America/Chicago):

- **Database backup waived for this promotion. No backup will be taken.** This explicitly replaces the earlier backup-before-SQL requirement for these four approved migrations.
- **Hosted staging services waived.** The completed disposable Docker rehearsal is accepted for this promotion; no staging services will be provisioned.
- **Shared-link follow-up misread accepted as a known gap, not a blocker.** The $450/month reply asking for investment assets remains unfixed; this waiver is additional to the two earlier accepted typed failures.
- Production migration gate/readback, four migration applications, landing the approved `cfc1988d` roadmap cut plus already-approved sharing configuration on main, and manual deployment of API, app and backtests are explicitly authorized. Preserve existing reviewed code/eval lineage; record the actual landed commit and re-gate it before deploying.
- Repeat one production money/share/signed-out/follow-up walk. Canaries stay skipped. No git stash.

Status: production promotion authorized and in progress. The local stop recorded below was the prior checkpoint and is superseded by this authorization. This authorization does not assert that migrations or deploys have completed.

## Disposable Docker Validation

- Exact clean app/API source: `cfc1988dd80ca1a8007b8f336c107700dd57e009`; both sharing flags enabled through environment overrides. Next.js production build passed. API/app ran locally against a fresh Docker Supabase database with real Auth/Postgres persistence. Workflow dispatch was disabled; no staging services provisioned.
- Four migrations applied once in repository order after initializing the earlier 75. Final readback **79/79**, no missing/unexpected migrations, name or content drift. Widened checks and SECURITY DEFINER/service-role-only claim/release permissions matched. See `docs/reports/evidence/2026-09-17-main-promotion/local-sharing-walk/migrations-after.json` and `objects-after.json`.
- Money question: starting at $1,200, saving $300 monthly without interest until $3,000. Correct answer: **six months**. Normal local signup preserved the guest answer and exposed the owner sharing control; preview and publication succeeded.
- Signed-out public link: separate browser session with **zero cookies and no auth-token storage keys** displayed the question, answer and calculation inputs. English and Spanish public pages passed; Spanish UI/calculation labels localized while immutable authored text stayed English.
- Follow-up: “What if I save $450 per month instead?” opened a distinct guest chat with the shared snapshot attached, but replied “Which asset or assets would you invest in monthly with that $450, and over what time period would you like to test it?” Expected four months. **Follow-up answer continuity failed.** No retry/fix was performed. This newly observed failure is not covered by the earlier two-case founder waiver.
- Console: public English/Spanish pages each had zero errors and a font preload warning. Initial signed-out chat logged four 401s; the reader's guest-chat transition logged three 401s before successful guest/fork/stream requests. Signed-in sharing had zero errors. Font preload warnings remained; no uncaught JS exception appeared.
- Evidence/report/screenshots: `docs/reports/evidence/2026-09-17-main-promotion/local-sharing-walk/README.md`. Two user questions, 13 provider receipts, **$0.04288399 reported**. No canary run.
- Cleanup: all three owned browser sessions closed; API/web listeners stopped; owned Supabase containers and data volumes removed. Exact-build worktree and local credential/status files removed after evidence preservation. No production change or git stash.


## Live Eval Evidence

- Live eval scorecard: `docs/reports/evidence/2026-09-17-main-promotion/candidate-scorecard-3cecda69.json`
- Live eval measured SHA: `3cecda6933399e53f6ea00edc8004a88d7eefad4`
- Candidate result: **70 passed, 3 failed**, zero expected failures, unexpected passes, skipped cases, or infrastructure errors. Native pytest exit 1 because of the three failures.
- Candidate fixture identity: 73 cases; SHA-256 `ca6ff99bf46bc1ea4a7f02088e54ed27fef685b1c02eb711f935456e47dcbe22`.
- Candidate usage: 381 route receipts; 359 with reported cost totaling **$1.575079614852**; 22 have no reported cost. This is not a complete billed-spend total.
- Candidate duration: native pytest **2379.17 seconds**.
- Baseline eval scorecard: `docs/reports/evidence/2026-09-17-main-promotion/baseline-scorecard-3d98057c.json`
- Baseline result: **68 passed, 3 failed**, zero other statuses; native pytest exit 1, **2203.35 seconds**. 363 route receipts, 342 reported costs totaling **$1.555157101776**, 21 costs unreported. Native schema-v2 original is retained unchanged as `docs/reports/evidence/2026-09-17-main-promotion/baseline-native-original-schema2.json`.
- Full case comparison: `docs/reports/evidence/2026-09-17-main-promotion/full-suite-comparison.json`.
- Baseline measured SHA: `3d98057c1e722317f0243fb96fb647771ddae484`; 71 native fixtures, digest `a48b14730a14578639e41dd27a15f27e3981208298fa7e68e477da7b159bcf6b`.
- Candidate-only additions are the English and Spanish explicit-end-date/year-qualifier cases; both passed. Existing fixture differences are only a DCA comment, not changed assertions.
- Targeted A/B baseline: `docs/reports/evidence/2026-09-17-main-promotion/spanish-scenario-ab-baseline.json`, measured SHA `3d98057c1e722317f0243fb96fb647771ddae484`; empty-table defect **0/10 (0%)**.
- Targeted A/B candidate: `docs/reports/evidence/2026-09-17-main-promotion/spanish-scenario-ab-candidate.json`, measured SHA `3cecda6933399e53f6ea00edc8004a88d7eefad4`; empty-table defect **0/10 (0%)**.
- A/B order: `docs/reports/evidence/2026-09-17-main-promotion/targeted-execution-order.json`; ten serial rounds, baseline then candidate, no manual retries. All 20 native attempts, original judge output, and text-based defect reviews are embedded in the side documents.
- The baseline published research in 4/10 attempts, had 5 research-publication failures and 1 routing refusal. The candidate published in 5/10, had 3 publication failures and 2 routing refusals. Among published answers the specific defect was also 0/4 baseline and 0/5 candidate. This small sample does not prove equivalence or general reliability.
- A/B reported receipt cost: baseline **$0.08631723848** (2 unreported), candidate **$0.18516206244** (7 unreported); sum of native case durations **2177.61 seconds**. All promotion live measurements total **$3.401716017548 reported**, 827 route receipts with 52 unreported costs. Provider billing may include costs not represented here.
- Candidate A/B attempt 7's judge alleges English fallback and a raw recovery code, but the retained answer is Spanish and contains no such code. These allegations are not confirmed defects; its research publication did fail.

Candidate failures and current comparison:

| Case | Observation | Disposition |
| --- | --- | --- |
| `compound_benchmark_start_date_preserves_confirmation_issue_339` | The requested April 1 start remained March 2, including the launch payload. | Baseline passed; candidate-only typed failure. Founder explicitly accepted this failure for the pinned cut on 2026-09-17; retained as unresolved product debt. |
| `dca_capital_semantics_only_have_amount_is_ceiling_issue_455` | Expected `capital_amount` in missing fields; actual list empty. Both builds stop for unsupported-budget clarification, with no launch payload; candidate alone records $5,000 as supplied capital. | Baseline passed; candidate-only typed failure. Founder explicitly accepted this failure for the pinned cut on 2026-09-17; retained as unresolved product debt. |
| `messy_spanish_future_performance_nvda_cruce_dorado` | `scenario_framing` failed: prose promised a scenario table but left it empty; the card did carry low/base/high values. | Baseline also fails the case, but on routing: it declines a future scenario and offers historical tests. Baseline prose passes. Ten paired attempts found the original empty-table defect 0/10 on each side. No measured increase established for that specific prose defect; research/routing failures retained separately. |

Baseline-only failures: `capability_honesty_future_performance_btc_regression` and `capability_honesty_future_performance_nvda_golden_cross` both expected published research but received `published=false`; the candidate passed both. Research-answer publication owns the existing failures; no recurrence rate is inferred from one run.

Typed side-by-side facts: `docs/reports/evidence/2026-09-17-main-promotion/typed-failure-comparison.json`. These are observed failures, not a root-cause diagnosis or a claimed recurrence rate. Founder answer after reviewing both failures: "Explicitly accept both failures". This overrides the runbook's default no-promotion rule for these two cases only; it does not claim a fix. Runtime interpretation/edit and DCA contract owners need founder-assigned follow-up; historical #339 and #455 remain closed and were not reopened.

The native driver and configuration observer are retained under the evidence directory. Both trees passed offline checks for native imports, SHA, fixture inventory and actual resolved model/flag parity before measurement. The older baseline lacks configuration-bearing scorecards, so the external observer preserves its original artifact and records actual configuration before/after; it does not insert desired profile values as evidence.

Literal candidate invocation (from the candidate root):

```bash
.venv/bin/python /private/tmp/argus-promotion-observer-7e84/native_driver.py \
  --tree /Users/garces/.codex/worktrees/7e84/private-alpha-next \
  --expected-sha 3cecda6933399e53f6ea00edc8004a88d7eefad4
```

The driver invokes the native `tests/evals/test_measurement_eval_live.py` with `--confcutdir=tests/evals -q --no-cov -s`. This excludes the general mocked fixture that would force release flags to other values. Both sides use `APP_ENV=development` for a native local run, explicit live market/asset providers, and their own release-profile models/booleans. No production database credential is supplied to these evals. Before the paid run, an initial startup attempt stopped on hosted traffic-class routing before any LLM request; its first typed action case and startup failure are retained locally. No paid suite retry was performed.

## Production Migration Gate

Required order: complete acceptance, take the backup before applying SQL, run the production ledger gate, apply only approved missing migrations in repository order, read back ledger and affected objects, require a passing gate, promote main, rerun with `--verify-landed-ref origin/main`, then deploy API, app, workflow in that order.

- Production gate: **not run**, stopped before production schema changes by latest founder direction; the founder explicitly accepted both typed failures. Gate apply behavior remains `never`.
- Production backup: **explicitly waived by founder after local acceptance; not taken**. The previously prepared backup procedure will not run for this promotion.
- Production SQL applied: **none**. Current production ledger parity and drift are not claimed.
- Production project from the configured target: `lgdhvepyrzbnscqssgqq`.
- Approved file hashes: `docs/reports/evidence/2026-09-17-main-promotion/approved-migration-files.json`.
- Local before/after ledger evidence and affected-object readback are retained in the evidence directory; they are explicitly not production clearance.

| Repository order | Migration | Classification | Approved handling |
| --- | --- | --- | --- |
| 1 | `20260912190000_share_calculation_receipts.sql` | destructive | Widen excerpt kind check; backup, no maintenance window. |
| 2 | `20260913213100_admit_readout_route_receipt_tier.sql` | destructive | Widen receipt tier check to readout; backup, no maintenance window. |
| 3 | `20260913230000_release_research_guest_claim.sql` | contract-replacing | Preserve claim signature, add guest-refund function, retain service-role-only execution. |
| 4 | `20260914120000_share_plain_answer_receipts.sql` | destructive | Widen excerpt kind check to answer; backup, no maintenance window. |

Local readback: 79/79 migrations match with no missing, unexpected, name or content drift. Both widened constraints are present. Claim/release functions are SECURITY DEFINER and executable by service_role, not anon/authenticated. Rollback retains widened checks and compatible functions; do not narrow checks after new-kind rows exist.

## Deploy Proof

Correction 2026-09-25: Head of Engineering verified the production Render
deploy in the Render dashboard. `argus-api` is live at
`a9286b21886eb03df7a21f2f4b7d5e79af570679`. It was deployed 2026-09-17
8:54 PM CT (2026-09-18 01:54Z). The previous `argus-api` deploy was
`3d98057c1e722317f0243fb96fb647771ddae484`. `argus-app` and
`argus-backtests` were not independently verified on 2026-09-25. This
repo does not record a verified SHA for either of those two services
after this promotion.

Pre-deploy readback remains in
`docs/reports/evidence/2026-09-17-main-promotion/deploy-before.json`
and `docs/reports/evidence/2026-09-17-main-promotion/final-hosted-readback.json`
(2026-09-17 23:10 UTC). Those files still showed all three services at
`3d98057c` before this deploy.

| Service | Observed deployed commit | Status |
| --- | --- | --- |
| `argus-api` | `a9286b21886eb03df7a21f2f4b7d5e79af570679` | live. Deployed 2026-09-17 8:54 PM CT (2026-09-18 01:54Z). Previous deploy `3d98057c1e722317f0243fb96fb647771ddae484`. Verified in Render by Head of Engineering on 2026-09-25. |
| `argus-app` | not independently verified on 2026-09-25 | The repo does not record a verified `argus-app` SHA for this deploy. |
| `argus-backtests` | not independently verified on 2026-09-25 | The repo does not record a verified workflow SHA for this deploy. |

Render MCP was reached through the repository-configured endpoint and credential during the original promotion write-up. It exposes API/app deployment tools but no Workflow operations; the repository's Workflow release command uses Render's Workflow API through its CLI. That capability gap is unchanged.

## Environment Proof

- Expected mode: `real-workflow`.
- Release profile hash: `71659a53a4c39b129c62ab0cb42068205be3a78d60c229f95898fe64353f3733`.
- `CUADRAO_EVIDENCE_RECEIPT_SHARING_ENABLED=true` and `NEXT_PUBLIC_EVIDENCE_RECEIPT_SHARING_ENABLED=true` agree in Blueprint, release profile and declared environment example on `origin/main`. Correction 2026-09-25: production `render.yaml` on `main` has both flags `true`. The integration Blueprint still has both `false`.
- API/app were observed with `autoDeployTrigger=off`; the profile retains manual mode for all three services.
- Hosted environment fingerprints, workflow effective-provider proof, warmup, guest controls/cleanup and post-deploy audit remain pending. No existing identity or guest workspace was modified for QA.

## Gate Evidence

Evidence summary: `docs/reports/evidence/2026-09-17-main-promotion/verification.txt`.

| Gate | Result |
| --- | --- |
| Required setup | Passed, Python 3.10.20, Poetry/Bun pinned by setup. |
| Ownership | No branch-specific policy; explicit skip. |
| Ruff / modularity | Passed; would-be merged tree equals candidate tree. |
| Full backend | 8,958 passed, 614 opt-in skips; one failure because the new manifest had no live evidence yet. Final focused document/evidence gates passed: 162 tests, zero skips. The actual new manifest and both A/B identities/configurations also passed direct validation. |
| Mocked evals | 272 passed. |
| Frontend lint / tests / build | Passed; 2,061 tests. |
| Browser storage disclosure | 2 passed. |
| Full local smoke | `verification_status=ready`; workflow dispatch stays off. |
| Real migration gate tests | 49 passed, zero skips. |
| Real PostgreSQL matrix | 395 passed, zero skips. |
| Real anonymous Auth matrix | 12 passed, zero skips. |
| Local Docker replacement / hosted acceptance | Local migrations and sharing views passed; follow-up answer continuity failed. Hosted staging and production acceptance not performed. |
| Required hosted CI / final review | PR #655: all real CI jobs passed at `2523e3a3`; draft-event jobs skipped. Final scoped Codex review is clean at that SHA, with zero unresolved threads. Links and exact proof are in the preproduction checkpoint. |

Resolved setup failures: the initial SciPy 1.15.3 macOS wheel could not import `scipy.linalg`; the official macosx_12_0_arm64 wheel at the same locked version fixed both imports. Supabase CLI 2.117.0 created broader local grants and caused four permission-test failures (391 other cases passed). Rebuilding only the disposable stack with CI-pinned 2.109.0 restored expected grants and the full matrix passed. The first browser-storage attempt collided with local port 3100; a separate port passed. No product code was changed for these setup failures.

Canary: workflow 298408697 was read back `disabled_manually`; issue #614 was closed with `state_reason=not_planned` on 2026-09-17. **Not fixed.** The founder retired the canary for this release. No canary success or scheduled follow-up is claimed.

## Release Decision

- Decision: **PRODUCTION PROMOTION AUTHORIZED; IN PROGRESS**. Founder accepted the two earlier candidate-only typed failures, then requested Docker validation and an explicit stop. The new follow-up failure remains unresolved and is now explicitly accepted as a known gap.
- Correction 2026-09-25: `origin/main` is `a9286b21886eb03df7a21f2f4b7d5e79af570679` (`feat(release): promote the approved private alpha roadmap`). `argus-api` is live at that SHA. `argus-app` and `argus-backtests` were not independently verified.
- The original write-up recorded that production backup/migrations/gate, main landing, and the three-service deploy had not been performed, and that PR #655 was still draft. That was the pre-deploy checkpoint. The 2026-09-25 correction above records the `argus-api` deploy that followed.
- Signed-out sharing walk: completed locally at exact `cfc1988d` with screenshots/console evidence; link publication and viewing passed, follow-up navigation passed, follow-up calculation intent failed. Production walk and revocation acceptance were not performed.
- Tester invitations/public exposure changes: none.
- Rollback owner: founder/Codex within the explicit promotion authority; restore the prior code and sharing posture while retaining compatible widened schema.
- Cleanup: original workspace dotenv link restored; both temporary native-eval worktrees removed; owned local Supabase stack stopped without retaining its disposable database. The PR-managed, data-free Supabase preview remains attached to open PR #655. No git stash was used.

Preproduction checkpoint, written after final review returned: `docs/reports/evidence/2026-09-17-main-promotion/preproduction-checkpoint.json`. It binds the reviewed/CI-tested checkpoint, retained evidence, founder acceptance, and cleanup. The only new publication changes are this status record and its artifact.

## Privacy Notes

No production conversation, user, run or job rows were read. No production
backup or browser transcript has been published. The disposable local sharing
walk retains privacy-safe aggregates and redacted screenshots only — not full
guest transcript dumps, accessibility-tree YAML captures, Auth UUIDs, or raw
receipt slugs (see
`docs/reports/evidence/2026-09-17-main-promotion/local-sharing-walk/`). Native
eval evidence contains authored fixture scenarios and the harness's
retained/redacted output, not customer conversations. Credentials remain in
ignored local files; the evidence directory was scanned against operator
credential values with zero matches. Backup contents, tokens, cookies and auth
storage must never be committed.
