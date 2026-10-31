# Private Alpha Production Promotion, 2026-09-12

Status: The founder merged PR #603 as `3d98057c1e722317f0243fb96fb647771ddae484`. All seven approved migrations are applied and all three services are deployed at that merge. The remaining production acceptance checks passed after the founder classified the canary failures as pre-existing. Issue #614 records the verified `/me` HTTP 401 and manual-mode drift; native canary failures remain unchanged. The current resumed acceptance record is at the end of this manifest. Earlier checkpoints retain their original state and evidence.

## Candidate

- Candidate SHA: `4fd587bf24ce39b794c2228d61f94693826d0da2`
- Candidate branch: `codex/production-promotion-20260912`
- Validation status: Pre-merge acceptance and final review completed; founder merge and the approved deployment followed. Remaining production acceptance checks passed, with the founder-accepted pre-existing canary failures recorded in #614. The measured product head and scorecards below remain unchanged.
- Validation surface: separate local acceptance worktree, disposable Supabase, production web build, and deliberately constructed production-mode environment.
- Promotion target: `main`
- Release captain: Codex in the founder-supervised promotion task.
- Approver: founder, in this task.
- Rollback target: `ee9c3491fa6219502f1e94abc5d9e661a06839d9`, verified live on API and app; workflow ready version `ee9c349`. The theme column must be restored before deploying this old build after the approved drop, with separate approval.
- Decision record: founder instructions in this task, 2026-09-12; fixed-cut promotion approved as a one-time exception to full-roadmap completion.

## Production Migration Gate

- Gate command: `scripts/ops/production_migration_gate.py`
- Gate report durable attachment or committed path: `docs/reports/evidence/2026-09-12-main-promotion/production-migration-gate-before.json`
- Gate checked at: `2026-09-13T02:38:15.471757Z`
- Gate candidate SHA: `df7aee12955f667e31057464d62c72287fb12247`
- Gated candidate parents and intended landing method: pre-landing candidate `df7aee12`; founder-owned merge commit to main. All seven migration files remain unchanged at `4fd587bf`.
- Landed `origin/main` SHA: pending founder merge; no landing claimed.
- Gate-to-landed-SHA identity: pending the Step 8 gate rerun at the actual merge commit.
- Landed-ref verification: pending Step 8 using `--verify-landed-ref origin/main`.
- Sanitized production project and database host: recorded in the gate report under `production_target`; no candidate server used that target.
- Database transport: `sslmode=verify-full`, production CA, GSS disabled
- Candidate migrations, with version, name, file SHA-256, statement count, and
  statement-array SHA-256: complete per-file records in the gate report under `candidate_migrations` and `applied_migrations`, respectively.
- Applied production migrations, with version, name, statement count, and
  statement-array SHA-256: complete per-file records in the gate report under `candidate_migrations` and `applied_migrations`, respectively.
- Latest applied production migration: `20260905000000` at the recorded readback.
- Missing migrations: exactly the seven founder-approved migrations listed under the migration approval section below.
- Unexpected applied migrations: seven historical identities covered by the committed gate reconciliation; advisory, no new unexpected identity. See `historical_ledger_variance` in the gate report.
- Migration name drift: none.
- Migration content drift, including missing statement history: none outside the recorded historical reconciliation.
- Safety classifications and live requirements for every missing migration: per-migration `classification`, `classification_basis` and `live_requirement` records in the gate report; theme drop is destructive and requires coordinated application immediately before deploy.
- Classification basis and human live-schema review: gate classifications plus the founder approval of all seven, including theme drop without backup. Fresh live review remains part of Step 8.
- Gate result: expected `status=blocked`, sole stop reason `missing_candidate_migrations`, with exactly the seven listed versions in repository order. The theme drop is destructive. No new name or content drift; the historical ledger variance matches the gate's committed reconciliation and is advisory. `status=pass` remains required before deploy.
- Gate human-approval state: seven listed migrations approved in principle, including the destructive theme drop with no backup; application awaits the post-merge approval stop in this task.
- Gate apply result: `not_performed_by_gate`
- Gate ledger readback: read-only pre-application report linked above; no ledger row was written.
- Human apply performed: no.
- If applied, repository order and ledger before/after: not applied; pending Step 8.
- If applied, affected-object readback: not applied; pending Step 8.
- Confirm the gate never applies migrations: `database_access=read_only`, `migration_apply=never`, `apply_result=not_performed_by_gate`.

## Deploy Proof

- API service: `argus-api`
- API deploy status: candidate not deployed; baseline was live at the Step 2 readback.
- API deployed SHA: baseline `ee9c3491fa6219502f1e94abc5d9e661a06839d9`; candidate proof pending Step 8.
- Web service: `argus-app`
- Web deploy status: candidate not deployed; baseline was live at the Step 2 readback.
- Web deployed SHA: baseline `ee9c3491fa6219502f1e94abc5d9e661a06839d9`; candidate proof pending Step 8.
- Workflow service: `argus-backtests`
- Workflow version status: baseline ready; candidate not released.
- Workflow released SHA: baseline abbreviated `ee9c349`; candidate proof pending Step 8.
- Workflow version id: retained in `production-readback-before.json`; no candidate version exists from this task.
- Checked at: `2026-09-13T02:13:29.901315+00:00` for baseline readback; no post-deploy readback.

## Environment Proof

- Expected mode: Environment C uses the measured Render literals, production API mode, live providers, disposable local Supabase, and the production web build. The complete key record appears below.
- Release profile hash: `5e654e07047f40df2e28b9cc83291698bd9bf3b211e32edf2c80d2dbf493c2cc` for sharing off.
- Effective locales and capabilities: English and Spanish, guest and signed-in chat, historical backtests, research and decision notes; sharing disabled.
- api_web_env_fingerprint: Local key-by-key proof: `sharing-off/browser-completion/environment-proof.json`; hosted fingerprint pending Step 8.
- workflow_env_fingerprint: Pending Step 8 hosted proof; no workflow environment changed.
- workflow_env_status: Production baseline read back; candidate workflow not deployed.
- autodeploy_fingerprint: Read-only service values retained in `production-readback-before.json`.
- autodeploy_status: All three services were `off`; no Blueprint sync or trigger change.
- all three services use `checksPass`: not requested; founder requires manual mode on all three, verified `off` in `production-readback-before.json`.
- workflow_runtime_provider_mode: Baseline readback `live_provider`; candidate proof pending Step 8.
- workflow_runtime_proof: Pending Step 8 at the founder merge commit.
- env_fingerprint script output: No candidate hosted audit run; local literal and secret-presence records are linked in Current Browser Acceptance.
- workflow_task: Pending Step 8; local backtests ran in process.
- real_workflow_task: Pending Step 8; no production workflow task created.
- Backtest service mode: local in-process acceptance with production shadow rows enabled; production dispatch proof pending Step 8.
- Workflow service proof:
  - `argus-backtests` latest deploy/status: Baseline `ee9c349`, ready; recorded in the Step 2 readback.
  - workflow autodeploy verified: `off`.
  - workflow provider mode verified: `live_provider`
  - effective runtime provider mode verified: `live_provider`
  - effective runtime proof status: Candidate hosted proof pending Step 8.
  - required workflow secrets present with redacted proof: Candidate hosted secret-presence proof pending Step 8; no secret values changed.
  - active workflow task verified: Candidate hosted task pending Step 8.
  - real workflow task verified: Candidate hosted task pending Step 8.
- Feature flags: both receipt-sharing values are false. The complete service key records are in `sharing-off/browser-completion/environment-proof.json`.
- Guest staged mode:
  - `CUADRAO_GUEST_ACCESS_ENABLED`: Not declared in the service key record; production code default applies.
  - `CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED`: `true`, from the release literal key record.
  - `NEXT_PUBLIC_GUEST_ACCESS_ENABLED`: Not declared in the service key record; production code default applies.
  - permanent account allowlist verified: No allowlist change; local new-account signup and profile save verified.
- Anonymous Auth / abuse controls:
  - anonymous Auth enabled: Local disposable Auth used for the guest walk; hosted post-deploy check pending.
  - CAPTCHA posture: Local QA token with a localhost API; hosted Turnstile proof pending Step 8.
  - provider anonymous-user rate limit: Not changed or load-tested; local defaults retained.
  - Argus per-IP guest-attempt limit: Release contract and code defaults retained; no load-test claim.
- Guest cleanup:
  - operator-run command: Owned local stack stopped with `supabase stop --no-backup --workdir <scratch>`; no production cleanup.
  - explicit target: Only the disposable `argus-promotion-20260912` stack.
  - dry-run selected: Not applicable to disposable stack teardown; no production guest-cleanup selection.
  - real selected/deleted/preserved/failed: Owned stack removed; unrelated stacks preserved. See `sharing-off/browser-completion/cleanup-browser.json`.
  - cleanup lag: Not measured; no production cleanup claim.
- Render config audit command: Hosted audit pending Step 8. Local launchers proved literal parity, substitutions and absent undeclared keys.
- Secret rotation / least-privilege owner: Founder; no rotation or secret change authorized or performed.

## Gate Evidence

- Local smoke command: `.github/local-smoke.sh --expected-sha df7aee12955f667e31057464d62c72287fb12247`, in Environment A after one direct timed readiness request.
- Local smoke result: the one unchanged rerun passed. Evidence: `docs/reports/evidence/2026-09-12-main-promotion/local-smoke-rerun-status.json` and `local-smoke-rerun.log` in the same directory.
- Warmup command: No separate hosted warmup; unchanged Environment A smoke command recorded above.
- Warmup result: Local smoke `verification_status=ready`, `workflow_probe=ready`; hosted candidate proof pending Step 8.
- Canary evidence artifact: the local acceptance records below; no hosted candidate canary is claimed before Step 8.
- Authoritative Spanish release canary:
  - JSON evidence: Current Spanish acceptance: `sharing-off/browser-completion/verification.json` and both sharing-off `steps.json` files.
  - Exact candidate SHA verified: `4fd587bf24ce39b794c2228d61f94693826d0da2`; clean detached local worktree, no env files.
  - Finalized evidence/result labels: Spanish result and result-rail labels passed in the Current Browser Acceptance table.
  - Decision-note label and reload hydration: `Decisión: Observando` saved and survived reload; feedback stayed dismissed.
  - Omnisearch source identity: Not exercised by the founder-specified remaining walk; no additional claim.
- Browser signup/login proof: local synthetic signup, first profile save, reload persistence, home country and English Usage passed at the measured head. Evidence: `docs/reports/evidence/2026-09-12-main-promotion/local-acceptance/browser-free-checks.json`, `profile-readback.json`, and screenshots `browser/01-en-guest-greeting.png` through `browser/06-en-usage-labels.png` under that same directory. No paid chat turn is claimed by this free evidence.
- Guest exact-head browser evidence:
  - local candidate SHA: `4fd587bf24ce39b794c2228d61f94693826d0da2` for the sharing-off walk.
  - 20-check matrix result: No separate 20-check matrix run here; the founder-specified walk is recorded step by step below.
  - same-UUID new-account conversion: Not measured by this walk; no conversion-identity claim.
  - atomic existing-account claim: Not measured by this walk; no concurrency claim.
  - zero cross-owner results: No cross-owner matrix run in this walk; no new isolation claim.
  - usage/API/database agreement: Local saved result, decision and feedback counts verified; approved Usage labels checked in both languages.
  - chart-interaction zero-write ledger: Not measured by this walk.
  - console status: Known #605 receipt warning and expected local email warning recorded in `sharing-off/browser-completion/known-warning-summary.json`.
- Guest load calibration:
  - synthetic p50/p95 and sample size: Not run in this promotion; no load projection.
  - error rate: No load sample collected.
  - queue/backpressure result: No load sample collected.
  - anonymous-session creation volume: No load sample collected.
  - cleanup lag: Not measured; no production cleanup claim.
  - provider-reported cost per completed result: Not estimated from the browser sample; cumulative actual tracked cost and reserve are reported separately.
  - unsupported production projections: None made.
  - Failed-capture replay, if failed: Not applicable to load calibration. The separately approved historical acceptance replay is recorded below.
  - Exit status: Not applicable; no load job run.

## Release Decision

- Public tester exposure approved: no new exposure approval claimed; founder owns each stop.
- Known caveats: #604 excluded by sharing off; #605 and #606 are deferred P2 findings; #611 records a P2 Bitcoin follow-up identity mismatch; research delivery and source-grounding failures are retained below, with #599 tracking BTC delivery. No additional product fix was made.
- Rollback trigger: founder-directed response to a failed production gate or post-deploy check; no automatic rollback authorized.
- Rollback command or owner: founder. Restore the dropped theme column with separate approval before deploying the old baseline.
- Guest rollback order verified: not executed; schema compatibility must precede any baseline deploy.
- Follow-up owner: founder prioritizes #599, #604, #605, #606, #608 and #611; research retry on provider errors is the first research follow-up.

## Privacy Notes

- No raw conversation, user, run, or job ids.
- Canary labels are stable hashes for audit correlation only.
- The release profile contains no credentials, account ids, deploy ids, or
  candidate SHA; record its hash with the candidate evidence instead.
- Failed-capture artifacts are sanitized replay inputs, not raw transcripts.
- Service-role credentials, cookies, prompts, and route receipt payloads are not
  copied into this manifest.
- Guest evidence contains no Auth UUID, raw conversation/artifact/job/run ids,
  customer email, tokens, cookies, headers, screenshots of credentials, or
  customer transcript dumps. The local profile screenshots contain a synthetic
  reserved-domain QA email only. Historical guest replay reports contain only
  case and turn numbers, outcomes, refusal codes and named capabilities, with
  allowance counts recorded separately.



## Fixed Cut and Measurement Identity

- Integration cut: `3d379d3d9020027ccfd1f2a4c617626520af8a44`.
- Fetched integration at cut: `3d379d3d9020027ccfd1f2a4c617626520af8a44`.
- Fetched main at cut: `17a07497abbb2ff9159b9694832a6668421e0e88`.
- `git merge-base --is-ancestor origin/main 3d379d3d` exited 0 at the cut.
- Never merge integration into this branch again. Later integration work is excluded.
- Founder lands the promotion with a merge commit, never squash or rebase. Codex never merges.
- The first commit changes the two sharing flags in `render.yaml` and the release profile to `true`. Code defaults remain off. Existing contract tests derive the values; no separate false-valued pin was found.
- Measured head: `df7aee12955f667e31057464d62c72287fb12247`. The founder-approved template commit supersedes the first contract head before any paid measurement.
- Later evidence commits touch only `docs/` unless an approved finding round requires a product fix.
- Product-tree identity will compare `src/`, `web/app/`, `web/components/`, `web/lib/`, `web/public/`, `render.yaml`, and `supabase/` to the measured head, matching the prior promotion record. Also record all non-doc Git-tree changes, including `workflows/`, tests, lockfiles, and the release profile.

## Sharing-Off Decision and Initial Preflight, 2026-09-13 (Historical)

The founder chose to promote with sharing off after the live findings in [#604](https://github.com/lagarcess/argus/issues/604#issuecomment-5655111583). Only `CUADRAO_EVIDENCE_RECEIPT_SHARING_ENABLED` and `NEXT_PUBLIC_EVIDENCE_RECEIPT_SHARING_ENABLED` change from `true` to `false` in `render.yaml` and the release profile. Their existing contract tests derive and compare the profile and Blueprint values; no separate true-valued test pin exists. Code defaults, runtime code, eval fixtures and all seven migrations remain unchanged. The earlier sharing-on records below are historical evidence, not the intended release configuration.

The full native candidate scorecard remains measurement evidence for the unchanged code exercised in Environment B: that job uses its explicit env file and does not read `render.yaml` or exercise sharing. Its original bytes and recorded measured SHA remain unchanged. This does **not** yet establish that the release validator accepts the scorecard for the new product head. `tests/test_private_alpha_release_docs.py:546` requires the scorecard's `provenance.candidate_sha` to equal the manifest candidate SHA. `eval_measured_code_unchanged` at `tests/release_promotion_evidence_support.py:94` is used for the baseline comparison at lines 160-164; it is not an alternative to the earlier exact-SHA assertion.

The founder authorized a fresh ten-pair interleaved A/B at the sharing-off product head, both sides, retaining HTTP statuses and waiting 15 minutes after three consecutive research delivery failures. The combined $12.50 tracked-cost-plus-reserve cap remains cumulative. The unchanged A/B validator includes `render.yaml` in its product-tree comparison. No paid attempt has started under this decision. An exact-SHA preflight for the full scorecard is required before that spend.

The original measured head and scorecard bytes remain unchanged in their historical records. Sharing-off commit `4fd587bf24ce39b794c2228d61f94693826d0da2` is the new product head named above and is the intended head for the remaining browser walk and authorized A/B. The retained full scorecard still records its real measured head `df7aee12955f667e31057464d62c72287fb12247`; its provenance has not been rewritten. CI green, exact-head Codex review and zero unresolved threads are still required before Step 7. No Step 8 action is authorized.

### Sharing-Off Preflight Stop (Historical)

The approved sharing-off product commit is `4fd587bf24ce39b794c2228d61f94693826d0da2`. All 16 existing release-profile and Render-profile contract tests passed in 23.34 seconds. The native import-derived comparison reports no changed eval imports; runtime, frontend, workflows, tests and all seven migrations are byte-identical to the original measured head. The full scorecard remains measurement evidence for that unchanged runtime, but the unchanged release validator does not accept it at the new candidate SHA.

A temporary manifest naming the new product head reproduced `AssertionError` at `tests/test_private_alpha_release_docs.py:546`: `assert provenance.get("candidate_sha") == candidate_match.group(1)`. The same preflight reports `eval_imported_code_unchanged=true` and `same_product_tree=false`. No provider calls were made. Evidence: `docs/reports/evidence/2026-09-12-main-promotion/sharing-off/provenance-preflight.json`.

The requested issue is [#608](https://github.com/lagarcess/argus/issues/608), with the hand-listed A/B paths, import-derived baseline comparison and separate full-scorecard exact-SHA assertion recorded together. No validator fix was attempted. A fresh A/B alone cannot resolve the full-scorecard assertion. The remaining browser walk and paid A/B were not started after this blocking preflight. The old sharing-on demo was stopped as part of the rebuild preparation; its owned API/web processes, containers, volumes and ports were removed while unrelated stacks were preserved. Evidence: `docs/reports/evidence/2026-09-12-main-promotion/sharing-off/demo-cleanup.json`.

No new browser or eval spend occurred under this decision. Cumulative browser cost remains $0.67845263918 tracked plus $0.16 reserve, below $3. Eval cost remains $6.0129416335 tracked plus $1.16 reserve, below $12.50. `docs/reports/evidence/2026-09-12-main-promotion/sharing-off/browser-budget-at-stop.json` records the browser total. Fresh CI/review and Step 7 are not complete. No merge, live environment change, migration application or Step 8 action occurred.

## Sharing-Off Browser Stop Before Measurement, 2026-09-13 (Historical)

The founder subsequently approved one fresh full candidate run to satisfy the unchanged validator, followed by a fresh ten-pair interleaved A/B, with one live job at a time and the same cumulative $12.50 cap. The remaining browser walk had to finish first at the sharing-off product head, with an explicit instruction to stop before measuring if it found anything needing a product change. That later instruction governs this stop; the earlier provenance approval request above is historical.

Environment C was rebuilt from a clean detached worktree at `4fd587bf24ce39b794c2228d61f94693826d0da2`. Both sharing flags are false. Every environment assertion passed before the API and production web build started: no `.env` or `web/.env.local`, no production project or public production domain in any constructed value, every Render literal accounted for, and only the approved local substitutions. All seven migrations were retained and reset only in the owned disposable stack. The key-by-key record is `sharing-off/browser-walk/environment-proof.json`, with startup and rebuild records in the same directory. Local differences remain in-process backtests with shadow jobs enabled, localhost origins, no Turnstile widget, no PostHog and no real application emails.

**18 checks passed; one failed.** Both language headers have no sharing link. English fresh-chat clarification retained AAPL, $10,000 and the supplied dates. Spanish guest and signed-in greetings, signup, first profile save, country persistence, all four Usage labels, DCA confirmation, successive edits, result, Quick take, feedback acknowledgment and sourced Breakdown passed. The Spanish result follow-up stated the correct displayed gap, dollar costs and worst-drop dates, but repeated four prose next steps as four action buttons.

This is a Spanish reproduction of existing promotion finding [#606](https://github.com/lagarcess/argus/issues/606), still **P2**, not a new severity escalation or a claim that production was replayed. The result-conversation owner is new in the bundle, and its runtime bytes have not changed since the original English reproduction. The current founder instruction requires stopping before measurement for this product change. No fix round started and no model-facing text or routing changed. Evidence: `spanish-follow-up-finding.json`, `spanish-result-facts.json`, and `es-15-follow-up-duplicate-next-steps.png` / `.txt` in the directory below.

Spanish fresh-chat clarification, standalone forward-looking research, decision save/reload, feedback dismissal after reload and result-rail navigation remain unrun; `not-run.json` records them. The feedback ask was absent after the next reply, and a read-only local query counted one saved feedback row, but no reload claim is made. The sourced Breakdown succeeded without a research retry. Sharing-link creation, signed-out phone viewing and revocation are superseded by the sharing-off decision. The founder-provided existing English confirmation summary in Spanish is unchanged historical context; this run's confirmation card itself rendered Spanish.

**Cumulative spend:** browser $0.81513723918 tracked plus $0.20 reserve = $1.01513723918 of $3. The reserve is not spend. Eval remains $6.0129416335 tracked plus $1.16 reserve = $7.1729416335 of $12.50. Replay remains $1.70731696526 tracked plus $0.18 reserve = $1.88731696526 of $4. Neither the newly approved full candidate run nor the new A/B started. The prior full scorecard retains its original native SHA and evidence bytes; its unchanged-import applicability does not waive the separate exact-SHA release assertion.

**Cleanup:** the owned API, web and guard stopped; `supabase stop --no-backup --workdir <owned scratch>` passed, all owned ports closed, owned containers and volumes were removed, and unrelated stacks were preserved. Raw local API/web logs were deleted after retaining sanitized evidence. Historical guest replay inputs remained deleted. Evidence: `cleanup-browser.json`, `budget-final.json` and `cost-events.json`.

The last completed CI at `f0c4f2f69cd9a2800ba7a22b801ffa8d1e6e2efa` had exactly one failing test: `test_main_promotion_manifests_require_live_eval_scorecard_evidence`, at the exact-SHA assertion on line 546. The backend reported 7,861 passed and 585 skipped; frontend, ownership and guest-release checks passed. This is the test waiting for the new scorecard, not an additional product failure. Evidence: `ci-before-evidence.json`. A fresh final-head Codex review is still owed after acceptance and green CI.

The current evidence directory is `docs/reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/`. Each executed row below has a screenshot and visible text. `steps.json` binds each capture to the sharing-off product head. No Step 7 readiness, green final CI or final review is claimed; the current full-scorecard gate remains unsatisfied until the authorized measurement can run after the browser stop is resolved.

| Language / step | Expected | Visible text that matters | Result and reason | Evidence |
| --- | --- | --- | --- | --- |
| en-01-sharing-off-guest-greeting | The rebuilt guest chat opens in English with sharing off. | What should we look into? | PASS: English greeting and enabled composer are visible. | [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/en-01-sharing-off-guest-greeting.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/en-01-sharing-off-guest-greeting.txt) |
| en-02-header-sharing-absent | A signed-in conversation header has no sharing control. | New chat; Chat options; no Share conversation button | PASS: The header shows Chat options and no Share conversation button. | [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/en-02-header-sharing-absent.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/en-02-header-sharing-absent.txt) |
| en-03-fresh-clarification | A fresh Apple test with $10,000 asks for its missing date window. | What date window should I use for AAPL? | PASS: Argus asks only for the missing date window and names AAPL. | [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/en-03-fresh-clarification.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/en-03-fresh-clarification.txt) |
| en-04-clarification-keeps-facts | A date-only reply retains AAPL and the earlier $10,000 capital. | AAPL; Starting capital $10,000; Jan 2, 2024 → Dec 31, 2024 | PASS: The confirmation keeps AAPL and $10,000 with the supplied 2024 period. | [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/en-04-clarification-keeps-facts.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/en-04-clarification-keeps-facts.txt) |
| es-01-guest-greeting | The empty guest chat greets the user in Spanish. | ¿Qué te gustaría investigar?; Pregunta sobre cualquier empresa o idea | PASS: The greeting and composer are Spanish. | [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-01-guest-greeting.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-01-guest-greeting.txt) |
| es-02-signed-in-greeting | The new signed-in account sees an empty Spanish greeting. | ¿Qué te gustaría investigar?; Ajustes | PASS: Signup succeeds and the empty signed-in chat remains Spanish. | [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-02-signed-in-greeting.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-02-signed-in-greeting.txt) |
| es-03-first-profile-save | The first profile change on a new account saves successfully in Spanish. | ¿Cómo quieres que Argus te llame? Lucía; Idioma de la app es | PASS: The saved preferred name appears as Lucía without an error. | [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-03-first-profile-save.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-03-first-profile-save.txt) |
| es-04-home-country-save | Home country saves and remains visible in Spanish. | País Colombia; Moneda COP | PASS: The country selection updates to Colombia and the derived currency to COP. | [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-04-home-country-save.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-04-home-country-save.txt) |
| es-05-home-country-persistence | The saved home country survives a reload. | País Colombia; Moneda COP | PASS: Colombia and COP remain selected after reload. | [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-05-home-country-persistence.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-05-home-country-persistence.txt) |
| es-06-usage-labels | Usage uses all four founder-approved Spanish labels. | Uso; Conversación; Búsquedas con fuentes; Simulaciones | PASS: All four approved labels are present. | [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-06-usage-labels.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-06-usage-labels.txt) |
| es-07-sharing-header-absent | The populated Spanish chat header has no sharing link or action. | Compra recurrente de Coca-Cola; Opciones de chat; no Compartir control | PASS: The header exposes chat options and no sharing button. | [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-07-sharing-header-absent.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-07-sharing-header-absent.txt) |
| es-08-dca-confirmation | Spanish confirmation retains KO, the monthly $200 contribution, $5,000 initial capital and date range. | KO; Compras recurrentes; Aporte $200 cada mes; 3 ago 2020 → 31 dic 2024; Capital inicial $5,000 | PASS: All requested DCA facts appear in the confirmation card. | [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-08-dca-confirmation.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-08-dca-confirmation.txt) |
| es-09-first-card-edit | The first edit changes starting capital to $6,000 while preserving monthly contributions. | Capital inicial $6,000; Aporte $200 cada mes | PASS: The card now shows $6,000 and still shows $200 each month. | [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-09-first-card-edit.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-09-first-card-edit.txt) |
| es-10-second-edit-retains-first | Editing costs preserves the first capital edit and recurring contribution. | Capital inicial $6,000; Aporte $200 cada mes; comisión de 10 bps + deslizamiento de 5 bps | PASS: The card keeps $6,000 and $200 monthly while adding 10 bps fee and 5 bps slippage. | [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-10-second-edit-retains-first.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-10-second-edit-retains-first.txt) |
| es-11-result-quick-take-feedback | A Spanish result, Quick take and one feedback ask appear after the backtest. | Simulación completa; Valor final $19,361; 34.7 puntos porcentuales; Lectura rápida; ¿Qué tal lo está haciendo Argus? | PASS: The completed result and Lectura rápida are visible, followed by one feedback ask. | [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-11-result-quick-take-feedback.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-11-result-quick-take-feedback.txt) |
| es-12-feedback-rated | Answering the feedback ask saves once and shows an acknowledgment. | Gracias por contarnos.; Cuéntanos más | PASS: Bien changes the prompt to Gracias por contarnos. | [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-12-feedback-rated.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-12-feedback-rated.txt) |
| es-13-breakdown | Breakdown explains the holding experience in Spanish with grounded DCA facts and sources. | 53 compras y ninguna venta; $16,600 aportados; $19,361; 21 de abril de 2022 y 5 de octubre de 2023; 5 fuentes | PASS: The Breakdown preserves contributions, ending value and worst-drop dates and includes publisher links. | [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-13-breakdown.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-13-breakdown.txt) |
| es-14-breakdown-gap-sources | The lower Breakdown shows the numeric gap and sources. | KO quedó 34.7 puntos porcentuales por debajo; 5 fuentes | PASS: The Breakdown reports the 34.7-point gap and shows five sources. | [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-14-breakdown-gap-sources.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-14-breakdown-gap-sources.txt) |
| es-15-follow-up-duplicate-next-steps | The follow-up gives the gap, dollar costs, worst-drop dates and one next-steps list. | 34.7 puntos porcentuales; $16.58 comisiones; $8.29 deslizamiento; $24.87 total; 21 de abril de 2022 al 5 de octubre de 2023; four prose steps plus Qué probar después | FAIL: The facts match the run, but four prose next steps are repeated as four action buttons; this reproduces known P2 issue #606. | [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-15-follow-up-duplicate-next-steps.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-15-follow-up-duplicate-next-steps.txt) |

## Current Browser Acceptance: Sharing Off

The founder explicitly kept #606 as a deferred P2 and limited the pre-measurement product stop to **new P0 or P1 findings requiring a product change**. The remaining Spanish walk completed at `4fd587bf24ce39b794c2228d61f94693826d0da2`, with no new P0 or P1. Both sharing flags remain false, all seven migrations remain included, and no product fix was made.

The fresh Spanish clarification retained AAPL and $10,000 after a date-only reply. A new result accepted a decision, retained `Decisión: Observando` after reload, and kept the rated feedback ask dismissed. The forward-looking research attempt failed with HTTP 500; its only retry began after the required two-minute wait and published an answer with five sources, including SEC and Apple investor filings. A subsequent question returned to the saved worst-drop dates. Once the conversation reached the rail's normal transcript threshold, `Decisión guardada: AAPL · Comprar y Mantener` navigated to and focused the correct result. A read-only local query counted one saved feedback row and one decision.

All sharing rows below are **not applicable** with sharing off. No answer selection, preview, local link, signed-out phone viewing or revocation was attempted. The earlier sharing-on failures remain recorded as history in #604. #606 remains a deferred P2 in both languages. The already recorded #605 receipt-persistence warning appeared again; the process observer retained cost. Expected local feedback-email warnings are the documented no-email environment difference. The first follow-up remains research retry on provider errors. No research failure was relabeled as a candidate request defect.

**Walk spend, cumulative across every walk and founder demo:** $1.34063303874 tracked plus $0.24 reserve = $1.58063303874 of $3. The reserve is not spend. Startup and environment assertions passed; no environment files or production database values were present in the detached worktree. The owned API, web and budget guard stopped, and the owned Supabase stack was stopped with `--no-backup`; owned ports, containers and volumes were removed while unrelated stacks were preserved. Historical customer replay inputs remain deleted. The mocked harness passed all 259 checks in 11.54 seconds.

Evidence is under `docs/reports/evidence/2026-09-12-main-promotion/sharing-off/browser-completion/`: `verification.json`, `persistence-proof.json`, `research-attempt-1.json`, `research-retry-timing.json`, `not-applicable.json`, `budget-final.json`, `cost-events.json`, `cleanup-browser.json`, and `evidence-applicability.json`. Every current capture has its screenshot and visible text. Earlier non-sharing English captures remain applicable because runtime, frontend, migrations, tests and workflows are byte-identical; the two release sharing values do not affect those surfaces. Original artifact bytes and recorded heads remain unchanged.

The table below combines the applicable retained English evidence and both sharing-off capture sessions. Failed attempts remain failures with their disposition, even where a later approved retry passed. NA rows have no fabricated screenshot.

| Step | Expected | Visible text that matters | Result and disposition | Capture / evidence |
| --- | --- | --- | --- | --- |
| en-02-signed-in-greeting | A new local account reaches the empty signed-in English chat. | What should we look into?; Search; Settings | PASS: Signup reached the English chat with signed-in sidebar controls. | df7aee12; retained non-sharing code; [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-02-signed-in-greeting.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-02-signed-in-greeting.txt) |
| en-03-first-profile-save-country | First home-country save succeeds and derives USD. | Country United States; Currency USD | PASS: United States and USD are shown after the first country save. | df7aee12; retained non-sharing code; [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-03-first-profile-save-country.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-03-first-profile-save-country.txt) |
| en-04-profile-reload | Saved country and derived currency survive a reload. | Country United States; Currency USD | PASS: United States and USD persisted after reload. | df7aee12; retained non-sharing code; [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-04-profile-reload.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-04-profile-reload.txt) |
| en-05-usage | Usage labels read Usage, Conversation, Searches with sources, Simulations. | Usage; Conversation; Searches with sources; Simulations | PASS: All four approved English labels are visible. | df7aee12; retained non-sharing code; [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-05-usage.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-05-usage.txt) |
| en-06-confirmation | The DCA draft preserves starting capital and monthly contribution and discloses any date adjustment. | $200 monthly; $5,000; Jul 27, 2020 → Dec 31, 2024 | PASS: Card shows $5,000, $200 monthly and the disclosed available-data start. | df7aee12; retained non-sharing code; [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-06-confirmation.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-06-confirmation.txt) |
| en-07-first-card-edit | Changing starting capital preserves the recurring contribution. | $200 monthly; $6,000 | PASS: $6,000 starting capital is saved with $200 monthly unchanged. | df7aee12; retained non-sharing code; [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-07-first-card-edit.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-07-first-card-edit.txt) |
| en-08-second-card-edit | A costs edit preserves the earlier capital edit and monthly contribution. | $6,000; $200 monthly; 10 bps fee + 5 bps slippage | PASS: 10 bps fee and 5 bps slippage are saved with $6,000 and $200 monthly intact. | df7aee12; retained non-sharing code; [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-08-second-card-edit.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-08-second-card-edit.txt) |
| en-09-result-quick-take-feedback | A result, Quick take and one feedback ask appear after the backtest. | Simulation Complete; Quick take; How is Argus doing? | PASS: Result and Quick take are present with one How is Argus doing prompt. | df7aee12; retained non-sharing code; [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-09-result-quick-take-feedback.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-09-result-quick-take-feedback.txt) |
| en-10-feedback-rated | Rating the feedback ask saves and acknowledges it. | Thanks for telling us. | PASS: The prompt changed to Thanks for telling us after Good. | df7aee12; retained non-sharing code; [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-10-feedback-rated.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-10-feedback-rated.txt) |
| en-11-result-details | Expanded result details preserve contributions, assumptions and net costs. | $16,800; Starting capital $6,000; Contribution $200 monthly | PASS: Details show $16,800 contributed, $6,000 starting capital, $200 monthly and modeled costs. | df7aee12; retained non-sharing code; [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-11-result-details.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-11-result-details.txt) |
| en-12-breakdown | Breakdown gives a sourced holding experience grounded in the result. | Breakdown; 54 purchases and no sales; 3 sources | PASS: Breakdown preserved DCA amounts, 38.1-point gap and April 21, 2022 to October 5, 2023 worst-drop dates with three sources. | df7aee12; retained non-sharing code; [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-12-breakdown.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-12-breakdown.txt) |
| en-13-breakdown-dates | The lower Breakdown shows exact worst-drop dates and benchmark gap. | April 21, 2022; October 5, 2023; 38.1 percentage points | PASS: Dates and the 38.1-percentage-point gap are visible in the Breakdown. | df7aee12; retained non-sharing code; [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-13-breakdown-dates.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-13-breakdown-dates.txt) |
| en-14-result-follow-up | The follow-up states gap, dollar costs and worst-drop dates with one next-steps list. | $25.17 in total: $16.78 in fees and $8.39 in slippage; four prose steps plus Try next | FAIL: Facts are correct, but next steps appear twice: a prose list and the matching Try next controls. | df7aee12; retained non-sharing code; [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-14-result-follow-up.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-14-result-follow-up.txt) |
| en-15-decision-saved | A decision saves on the result. | Decision: Watching | PASS: The result now reads Decision: Watching. | df7aee12; retained non-sharing code; [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-15-decision-saved.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-15-decision-saved.txt) |
| en-16-feedback-and-decision-reload | After another reply and reload, feedback stays dismissed and decision and Breakdown persist. | Decision: Watching; Breakdown; feedback ask absent | PASS: No feedback ask returned; Decision: Watching and the finished Breakdown survived reload. | df7aee12; retained non-sharing code; [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-16-feedback-and-decision-reload.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-16-feedback-and-decision-reload.txt) |
| en-17-research-attempt-1 | The valuation and outlook question publishes research with sources. | I couldn't complete the data lookup just now, so I won't quote live figures. | FAIL: The turn disclosed that data lookup could not complete and published no live figures. | df7aee12; retained non-sharing code; [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-17-research-attempt-1.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-17-research-attempt-1.txt) |
| en-18-research-attempt-2 | One retry after two minutes publishes the requested research. | I couldn't complete the data lookup just now, so I won't quote live figures. | FAIL: The single retry timed out and again disclosed lookup unavailability. | df7aee12; retained non-sharing code; [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-18-research-attempt-2.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-18-research-attempt-2.txt) |
| en-19-result-rail | A long conversation shows a tick that navigates to its saved result. | Decision saved: KO · DCA Accumulation | PASS: The KO result appears as Decision saved after its decision was added, and the tick navigates to it. | df7aee12; retained non-sharing code; [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-19-result-rail.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-19-result-rail.txt) |
| en-01-sharing-off-guest-greeting | The rebuilt guest chat opens in English with sharing off. | What should we look into? | PASS: English greeting and enabled composer are visible. | 4fd587bf; [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/en-01-sharing-off-guest-greeting.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/en-01-sharing-off-guest-greeting.txt) |
| en-02-header-sharing-absent | A signed-in conversation header has no sharing control. | New chat; Chat options; no Share conversation button | PASS: The header shows Chat options and no Share conversation button. | 4fd587bf; [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/en-02-header-sharing-absent.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/en-02-header-sharing-absent.txt) |
| en-03-fresh-clarification | A fresh Apple test with $10,000 asks for its missing date window. | What date window should I use for AAPL? | PASS: Argus asks only for the missing date window and names AAPL. | 4fd587bf; [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/en-03-fresh-clarification.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/en-03-fresh-clarification.txt) |
| en-04-clarification-keeps-facts | A date-only reply retains AAPL and the earlier $10,000 capital. | AAPL; Starting capital $10,000; Jan 2, 2024 → Dec 31, 2024 | PASS: The confirmation keeps AAPL and $10,000 with the supplied 2024 period. | 4fd587bf; [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/en-04-clarification-keeps-facts.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/en-04-clarification-keeps-facts.txt) |
| es-01-guest-greeting | The empty guest chat greets the user in Spanish. | ¿Qué te gustaría investigar?; Pregunta sobre cualquier empresa o idea | PASS: The greeting and composer are Spanish. | 4fd587bf; [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-01-guest-greeting.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-01-guest-greeting.txt) |
| es-02-signed-in-greeting | The new signed-in account sees an empty Spanish greeting. | ¿Qué te gustaría investigar?; Ajustes | PASS: Signup succeeds and the empty signed-in chat remains Spanish. | 4fd587bf; [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-02-signed-in-greeting.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-02-signed-in-greeting.txt) |
| es-03-first-profile-save | The first profile change on a new account saves successfully in Spanish. | ¿Cómo quieres que Argus te llame? Lucía; Idioma de la app es | PASS: The saved preferred name appears as Lucía without an error. | 4fd587bf; [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-03-first-profile-save.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-03-first-profile-save.txt) |
| es-04-home-country-save | Home country saves and remains visible in Spanish. | País Colombia; Moneda COP | PASS: The country selection updates to Colombia and the derived currency to COP. | 4fd587bf; [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-04-home-country-save.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-04-home-country-save.txt) |
| es-05-home-country-persistence | The saved home country survives a reload. | País Colombia; Moneda COP | PASS: Colombia and COP remain selected after reload. | 4fd587bf; [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-05-home-country-persistence.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-05-home-country-persistence.txt) |
| es-06-usage-labels | Usage uses all four founder-approved Spanish labels. | Uso; Conversación; Búsquedas con fuentes; Simulaciones | PASS: All four approved labels are present. | 4fd587bf; [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-06-usage-labels.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-06-usage-labels.txt) |
| es-07-sharing-header-absent | The populated Spanish chat header has no sharing link or action. | Compra recurrente de Coca-Cola; Opciones de chat; no Compartir control | PASS: The header exposes chat options and no sharing button. | 4fd587bf; [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-07-sharing-header-absent.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-07-sharing-header-absent.txt) |
| es-08-dca-confirmation | Spanish confirmation retains KO, the monthly $200 contribution, $5,000 initial capital and date range. | KO; Compras recurrentes; Aporte $200 cada mes; 3 ago 2020 → 31 dic 2024; Capital inicial $5,000 | PASS: All requested DCA facts appear in the confirmation card. | 4fd587bf; [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-08-dca-confirmation.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-08-dca-confirmation.txt) |
| es-09-first-card-edit | The first edit changes starting capital to $6,000 while preserving monthly contributions. | Capital inicial $6,000; Aporte $200 cada mes | PASS: The card now shows $6,000 and still shows $200 each month. | 4fd587bf; [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-09-first-card-edit.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-09-first-card-edit.txt) |
| es-10-second-edit-retains-first | Editing costs preserves the first capital edit and recurring contribution. | Capital inicial $6,000; Aporte $200 cada mes; comisión de 10 bps + deslizamiento de 5 bps | PASS: The card keeps $6,000 and $200 monthly while adding 10 bps fee and 5 bps slippage. | 4fd587bf; [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-10-second-edit-retains-first.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-10-second-edit-retains-first.txt) |
| es-11-result-quick-take-feedback | A Spanish result, Quick take and one feedback ask appear after the backtest. | Simulación completa; Valor final $19,361; 34.7 puntos porcentuales; Lectura rápida; ¿Qué tal lo está haciendo Argus? | PASS: The completed result and Lectura rápida are visible, followed by one feedback ask. | 4fd587bf; [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-11-result-quick-take-feedback.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-11-result-quick-take-feedback.txt) |
| es-12-feedback-rated | Answering the feedback ask saves once and shows an acknowledgment. | Gracias por contarnos.; Cuéntanos más | PASS: Bien changes the prompt to Gracias por contarnos. | 4fd587bf; [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-12-feedback-rated.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-12-feedback-rated.txt) |
| es-13-breakdown | Breakdown explains the holding experience in Spanish with grounded DCA facts and sources. | 53 compras y ninguna venta; $16,600 aportados; $19,361; 21 de abril de 2022 y 5 de octubre de 2023; 5 fuentes | PASS: The Breakdown preserves contributions, ending value and worst-drop dates and includes publisher links. | 4fd587bf; [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-13-breakdown.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-13-breakdown.txt) |
| es-14-breakdown-gap-sources | The lower Breakdown shows the numeric gap and sources. | KO quedó 34.7 puntos porcentuales por debajo; 5 fuentes | PASS: The Breakdown reports the 34.7-point gap and shows five sources. | 4fd587bf; [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-14-breakdown-gap-sources.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-14-breakdown-gap-sources.txt) |
| es-15-follow-up-duplicate-next-steps | The follow-up gives the gap, dollar costs, worst-drop dates and one next-steps list. | 34.7 puntos porcentuales; $16.58 comisiones; $8.29 deslizamiento; $24.87 total; 21 de abril de 2022 al 5 de octubre de 2023; four prose steps plus Qué probar después | FAIL: The facts match the run, but four prose next steps are repeated as four action buttons; this reproduces known P2 issue #606. | 4fd587bf; [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-15-follow-up-duplicate-next-steps.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-walk/es-15-follow-up-duplicate-next-steps.txt) |
| es-16-fresh-clarification | A fresh Apple test asks for the missing period in Spanish. | ¿Qué periodo quieres usar para AAPL? | PASS: The reply asks for the period and keeps the earlier AAPL fact. | 4fd587bf; [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-completion/es-16-fresh-clarification.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-completion/es-16-fresh-clarification.txt) |
| es-17-clarification-keeps-facts | A date-only Spanish reply keeps AAPL and the original $10,000. | AAPL; Capital inicial $10,000; 2 ene 2024 → 31 dic 2024 | PASS: The confirmation retains AAPL and $10,000 and adds the requested 2024 dates. | 4fd587bf; [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-completion/es-17-clarification-keeps-facts.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-completion/es-17-clarification-keeps-facts.txt) |
| es-18-result-for-remaining-controls | The clarified test completes and exposes decision and feedback controls. | Simulación completa; Valor final $13,503; Agregar decisión; ¿Qué tal lo está haciendo Argus? | PASS: The AAPL result completes with one feedback ask and Agregar decisión. | 4fd587bf; [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-completion/es-18-result-for-remaining-controls.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-completion/es-18-result-for-remaining-controls.txt) |
| es-19-decision-saved | A Spanish decision saves on the completed result. | Decisión: Observando | PASS: The result now displays Decisión: Observando. | 4fd587bf; [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-completion/es-19-decision-saved.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-completion/es-19-decision-saved.txt) |
| es-20-feedback-decision-reload | The decision survives reload and the rated feedback ask does not return. | Decisión: Observando; no ¿Qué tal lo está haciendo Argus? prompt | PASS: Decisión: Observando persists and the feedback question and rating buttons are absent. | 4fd587bf; [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-completion/es-20-feedback-decision-reload.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-completion/es-20-feedback-decision-reload.txt) |
| es-21-research-attempt-1 | A forward-looking question about Apple publishes a Spanish research answer with sources. | No pude completar la búsqueda de datos en este momento, así que no voy a citar cifras en vivo. | FAIL: The reply discloses that the lookup could not complete and cites no live figures. | 4fd587bf; [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-completion/es-21-research-attempt-1.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-completion/es-21-research-attempt-1.txt) |
| es-22-research-attempt-2 | The single retry after two minutes publishes Spanish research with sources. | Los riesgos más claros para los ingresos de Apple durante los próximos doce meses; No significan que los ingresos necesariamente caerán; 5 fuentes | PASS: The retry explains revenue risks as possibilities and publishes five sources. | 4fd587bf; [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-completion/es-22-research-attempt-2.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-completion/es-22-research-attempt-2.txt) |
| es-23-research-sources | The Spanish research answer exposes its source list. | Fuentes que Argus consultó; www.sec.gov; investor.apple.com; five source links | PASS: The source panel lists five sources, including SEC and Apple investor filings. | 4fd587bf; [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-completion/es-23-research-sources.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-completion/es-23-research-sources.txt) |
| es-24-result-after-research | Returning from research to the saved result keeps its exact historical dates. | La peor caída de AAPL en la prueba de 2024 comenzó el 23 de enero de 2024 y terminó el 19 de abril de 2024. | PASS: The reply uses the saved January 23 to April 19 worst-drop window. | 4fd587bf; [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-completion/es-24-result-after-research.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-completion/es-24-result-after-research.txt) |
| es-25-result-rail | The Spanish rail exposes the saved result and its tick navigates back to that card. | Actividad de la conversación; Decisión guardada: AAPL · Comprar y Mantener; Decisión: Observando | PASS: The Decisión guardada tick scrolls to the AAPL card and focuses the result, which still shows Observando. | 4fd587bf; [image](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-completion/es-25-result-rail.png) / [text](../reports/evidence/2026-09-12-main-promotion/sharing-off/browser-completion/es-25-result-rail.txt) |
| en / Pick answers | Sharing off | Header sharing control absent | NOT APPLICABLE: founder release decision | No sharing capture required |
| en / Preview selected answers | Sharing off | Header sharing control absent | NOT APPLICABLE: founder release decision | No sharing capture required |
| en / Create a local share link | Sharing off | Header sharing control absent | NOT APPLICABLE: founder release decision | No sharing capture required |
| en / Open signed out at phone width | Sharing off | Header sharing control absent | NOT APPLICABLE: founder release decision | No sharing capture required |
| en / Revoke the link | Sharing off | Header sharing control absent | NOT APPLICABLE: founder release decision | No sharing capture required |
| en / Confirm a revoked link stops working | Sharing off | Header sharing control absent | NOT APPLICABLE: founder release decision | No sharing capture required |
| es-419 / Pick answers | Sharing off | Header sharing control absent | NOT APPLICABLE: founder release decision | No sharing capture required |
| es-419 / Preview selected answers | Sharing off | Header sharing control absent | NOT APPLICABLE: founder release decision | No sharing capture required |
| es-419 / Create a local share link | Sharing off | Header sharing control absent | NOT APPLICABLE: founder release decision | No sharing capture required |
| es-419 / Open signed out at phone width | Sharing off | Header sharing control absent | NOT APPLICABLE: founder release decision | No sharing capture required |
| es-419 / Revoke the link | Sharing off | Header sharing control absent | NOT APPLICABLE: founder release decision | No sharing capture required |
| es-419 / Confirm a revoked link stops working | Sharing off | Header sharing control absent | NOT APPLICABLE: founder release decision | No sharing capture required |

## Current Full Candidate Comparison: Sharing Off

- Live eval scorecard: `docs/reports/evidence/2026-09-12-main-promotion/sharing-off/eval/candidate-eval-scorecard-4fd587bf.json`
- Baseline eval scorecard: `docs/reports/evidence/2026-09-12-main-promotion/baseline-eval-scorecard-ee9c3491.json`
- Native candidate: 67 passed, four failed, zero infrastructure errors, all 71 cases and 84 user turns measured. The completed deployed baseline remains 59 passed, three failed, all 62 cases and 73 user turns measured.
- Provenance: clean detached worktree at `4fd587bf24ce39b794c2228d61f94693826d0da2`, both provider modes `live_provider`, Python 3.10.20, identical Environment B and unchanged real-env source hash. The native scorecards are preserved byte for byte. No product file or validator changed during the run.
- Fresh tracked cost: $1.951539972184. Cumulative eval subtotal at full-run completion: $7.964481605684 tracked plus $1.52 reserve, or $9.484481605684 guarded. The reserve is not spend. The sequential A/B uses the same cumulative ledger and $12.50 stop.
- Comparison: `docs/reports/evidence/2026-09-12-main-promotion/sharing-off/eval/approved-eval-comparison.json`.
- Per-case dispositions: `docs/reports/evidence/2026-09-12-main-promotion/sharing-off/eval/full-eval-case-dispositions.json`.
- Free unchanged-validator checks: 24 passed in 7.43 seconds after the new full scorecard and dispositions were recorded. Evidence: `docs/reports/evidence/2026-09-12-main-promotion/sharing-off/eval/release-docs-full-scorecard.log`. Modularity also passed with no violations; its adjacent `modularity-budget.log` applies to the would-be merged product tree because the read-back main SHA remains an ancestor of this candidate.
- Run, environment and cost evidence: `docs/reports/evidence/2026-09-12-main-promotion/sharing-off/eval/eval-run/sharing-off-full-candidate-status.json`, its adjacent log and controller, and `all-attempt-events.jsonl`. This ledger retains every previous paid attempt as well as the new full run.

| Failed native case | Deployed baseline | Sharing-off candidate | Classification and disposition |
| --- | --- | --- | --- |
| `action_chip_change_asset_changed_mind_capital_issue_188` | Passed | Failed coverage check | P2 availability-recovery observation. Assets, requested dates and edited $5,000 capital are preserved; `market_data_unavailable` prevents a launch and offers recovery. The underlying catalog, data-shape or transport cause was not retained, so it is not claimed as a confirmed provider fault or new edit defect. The fixture uses a legacy action which neither build emits on new cards. |
| `capability_honesty_future_performance_btc_regression` | Passed its future-limitation expectation | Failed research publication; prose judge passed | Provider-side research delivery failure, HTTP 500 in the captured case window. The answer disclosed lookup unavailability and quoted no live figure. This is the already known research-delivery caveat. Research retry on provider errors remains the first follow-up. |
| `dca_capital_semantics_prebaked_chip_spanish_pesos_reaches_ready_to_run` | Failed | Failed with identical checks | Shared failure, not new: both return `unsupported_dca_contribution_ceiling`, null capital and no launch. |
| `messy_spanish_future_performance_nvda_cruce_dorado` | Passed its future-limitation expectation | Failed stronger research expectations; prose judge passed | Both answers disclose the future-performance limitation and offer historical alternatives. The candidate response is no worse than the deployed response, but the native failure is retained. No research sidecar exists on this attempt, so it is not labeled a provider delivery failure. The authorized A/B measures the rate. |

All three candidate-only failures are named above. None has a failing prose judge in this new full run. No recorded-text judge replay, individual case retry or second full run was added. The founder's explicit ten-pair A/B is complete and is recorded in the final section below. Counts do not offset failed cases: the two baseline-only failures are `action_chip_change_asset_bare_ticker_append_issue_190` and `asset_discovery_not_result_followup_issue_244`; all nine candidate-only fixture cases passed.

Read-only source proof confirms identical `prepare_confirmation_launch` ASTs on the deployed and candidate builds and identical new-card secondary actions. Historical cards retain legacy action support; no production reachability count is asserted. Evidence: `docs/reports/evidence/2026-09-12-main-promotion/sharing-off/eval/legacy-change-asset-reachability.json` and the per-case disposition document. No fix round was started.

## Founder Scope and Approval Stops

- Promote only the fixed cut. Do not add unfinished board items.
- Acceptance replay is approved. User words stay in private scratch outside the repository and are deleted afterward. Reports contain only case and turn numbers, outcomes, refusal codes and named capabilities, plus separate allowance counts.
- Usage labels approved: Usage, Conversation, Searches with sources, Simulations; Uso, Conversación, Búsquedas con fuentes, Simulaciones.
- Current founder decision: promote with sharing off. Both release-contract flags are false. No live environment change or Blueprint sync is permitted without separate approval.
- Each post-merge operation needs founder approval here: migrations, live sharing values, three explicit deployments, and post-deploy checks. Production shared-link creation and revocation checks are not applicable while sharing stays off; no production link is authorized.
- Stop for any Supabase or Render access failure, unexpected production readback, migration or environment mismatch, spending stop, or blocking finding. Report the exact access error without a workaround.
- At most two small blocking fix rounds. Stop before model-facing text or routing changes and on any real blocking sharing finding.

## Approved Migration Order

Apply only after founder merge and the application approval stop, immediately before deployment. The gate reads only. Use its `_split_supabase_statements` for ledger rows, then rerun until `status=pass`.

1. `20260908120000_decision_notes_attach_to_computations`
2. `20260908205041_add_refusal_observations`
3. `20260909183646_share_answer_receipt_selections`
4. `20260909225701_retire_research_rail_ledger_status`
5. `20260910003000_lift_receipt_selection_cap`
6. `20260911120000_add_profile_home_country`
7. `20260911214608_drop_profiles_theme` (destructive)

The founder explicitly approved no backup, overriding PR #595's backup step. Between the theme drop and completed deployment, signups and profile saves on the old build fail. Rolling code back before #584 requires restoration of the theme column first, with separate approval; discarded preference values cannot be recovered from a backup in this promotion.

## Environment and Spending Ledger

| Job | Environment | Stop | Spent | Result |
| --- | --- | --- | --- | --- |
| Free gates | A: development setup with the explicit canonical-root override | Free | $0 | Smoke, mocked harness, modularity and parity passed; mocked harness passed 259 checks; unchanged release validator checked after A/B evidence |
| Candidate and production baseline eval | B: identical explicit eval env file and both provider modes live | $12.50 combined, tracked cost plus reserve | $9.556433710664 tracked + $1.64 reserve = $11.196433710664 guarded | Fresh full run and new ten-pair A/B complete; native A/B failures deployed 0/10 and candidate 5/10; founder merge disposition pending |
| Browser walk and local sharing demo, cumulative | C: clean detached worktrees, disposable Supabase, production builds | $3.00 | $1.34063303874 tracked + $0.24 reserve = $1.58063303874 guarded | Applicable walk complete; #606 deferred P2, Spanish research retry passed, sharing NA; no new P0/P1 |
| Historical guest replay | C: fresh guest per conversation, ordered user turns | $4.00 | $1.7073169653 tracked + $0.18 reserve = $1.8873169653 guarded | 38/38 assessed; 38 pass, 0 fail, 0 allowance |

Environment A's pre-existing root `.env` symlink resolves through the integration worktree to the exact founder-named real file. `web/.env.local` is absent. No environment file is written through or replaced.

Environment C has no `.env` or `web/.env.local`. API and web launched from empty environments with only declared Render keys, the approved substitutions, process basics, and the localhost QA captcha token. Before the production web build and server starts, both services passed the key-by-key literal, declared-key, forbidden-production-value, and absent-env-file checks. Evidence: `docs/reports/evidence/2026-09-12-main-promotion/local-acceptance/environment-proof.json`. The disposable stack was reset from the measured branch migrations; startup readiness passed with the runtime, Supabase, and live asset catalog ready. Evidence: `stack-proof.json` and `startup-health.json` in that directory.

Local differences to cover after deployment: in-process backtests instead of `argus-backtests`, no Turnstile widget, no PostHog, no emails, and localhost origins. The API retains production key routing and shadow job rows; only if jobs stay queued may shadow mode be turned off and recorded as another local difference.

## Historical Step 3 Budget Stop

- Promotion PR: https://github.com/lagarcess/argus/pull/603, targeting `main` with the fixed integration cut. This is a blocked promotion, not a terminal release audit.
- Baseline eval scorecard: `docs/reports/evidence/2026-09-12-main-promotion/baseline-eval-scorecard-ee9c3491.json`. Original bytes retained, SHA-256 `ec7e3301fbc796c38265313a61282a882d2564bcd761e7084ffcc05c91c7792a`.
- Baseline: 59 passed, 3 failed, no infrastructure errors, all 62 fixtures and 73 user turns. Both provider modes are `live_provider`; the native provenance confirms the production SHA, Python 3.10.20, clean worktree, and holiday-alignment probe.
- Candidate: 47 completed cases passed, 24 cases remain unmeasured or incomplete. The process stopped during `dca_capital_semantics_spanish_period_exceeds_window_issue_455` with exit code `-15`. No native candidate scorecard was written, and none was reconstructed or fabricated from partial events.
- Comparison: not accepted. The complete baseline has three failures: `action_chip_change_asset_bare_ticker_append_issue_190`, `asset_discovery_not_result_followup_issue_244`, and `dca_capital_semantics_prebaked_chip_spanish_pesos_reaches_ready_to_run`. Their checks remain in `baseline-summary.json`. Partial candidate successes cannot establish the complete comparison. No candidate failure triggered a judge replay or case rerun.
- Fixture relationship: 62 common cases, with 59 unchanged. Three forward-looking cases retain their inputs but change expected outcomes and the prose rubric to research with sources. The candidate adds nine cases and removes none. Evidence: `eval-fixture-comparison.json` in the same directory.
- Environment identity: each run used a separate clean detached worktree and the identical explicit process environment, real env-file path, and live provider modes. The env-file content hash remained unchanged after both processes stopped. Evidence: `eval-environment-source-provenance.json` and `eval-pair-process-record.json` in the same directory.
- Cost: baseline `$1.390784977984`; partial candidate `$1.344450851416`; combined tracked `$2.7352358294`. This includes OpenRouter usage receipts, validated Perplexity Agent usage, and `$0.05` of documented Perplexity Search request fees. It is not a complete provider invoice because 34 non-skipped receipts lack prices.
- Guard: `$0.10` for in-flight work plus `$0.02` per unpriced non-skipped receipt. Its final `$0.78` reserve is a conservative operational allowance, not an asserted provider charge. Tracked cost plus reserve reached `$3.5152358294` and terminated the candidate. The report does not claim that actual spend reached `$3.50`.
- Evidence: `docs/reports/evidence/2026-09-12-main-promotion/eval-budget-stop.json`, plus `eval-run/events.jsonl`, the unchanged observer and guardian source, and sanitized process logs under that evidence directory.
- Initial PR CI: frontend, guest-release-gates, ownership, and Supabase Preview checks passed. Backend reported 7,861 passed, 585 skipped, and one failure: the required durable candidate live scorecard is absent. That evidence requirement remains unmet; no validator was weakened. The aggregate `ci` check is not green.
- Stop-record validation: 23 release evidence checks passed; the one missing-candidate-scorecard requirement failed, as expected for this incomplete run. Evidence: `release-docs-budget-stop.log` in the same directory.
- Review: the initial Codex summary completed at PR head `2d99bcb4edc6c9e817a524fa295c8d67776ff549`, with no formal review or inline thread and no explicit `Reviewed commit` receipt. It does not satisfy the founder's exact-head review requirement. No terminal audit or clean-review claim is made.
- Local free acceptance: six screenshots, profile persistence readback, startup readiness, scratch migration reset, and all 85 environment keys are retained under `local-acceptance/`. Paid browser and replay spend are both `$0`. Customer message content was never pulled; the replay inventory selected aggregate counts only.
- Cleanup: owned API/web processes stopped, owned ports closed, and `supabase stop --no-backup --workdir <owned scratch>` succeeded. The unrelated running stack remained intact. Evidence: `local-acceptance/cleanup.json`.
- Superseded proposal: the stop report requested a `$6.50` combined eval cap. The founder instead approved `$7.50` on tracked cost plus reserve for exactly one fresh full candidate run, retaining the baseline and environment. Browser and replay caps remain `$3` and `$4`.

## Step 3 Approved Fresh Candidate Run (Historical Result)

The founder approved one fresh full candidate run after the stop record at `0e6227386ab76813fd55d0c838f896abe7e70e41`. The combined cap is `$7.50` on tracked cost plus reserve, including the original baseline and interrupted candidate costs. The reserve is not spend. If this guard stops the fresh run, stop and report; no further full run is authorized.

- Historical full candidate scorecard: `docs/reports/evidence/2026-09-12-main-promotion/candidate-eval-scorecard-df7aee12.json`
- Full candidate result: 70 passed, one failed, zero infrastructure errors as classified by the native harness. The native scorecard is retained unchanged.
- Candidate-only failed case: `messy_spanish_future_performance_nvda_cruce_dorado`. Research recorded `research_unavailable_timeout`, no publication and no sources. The assistant disclosed the unavailable data search. The native checks failed `research.published` and `prose_judge:scenario_framing`.
- Recorded-text judge replay: the exact retained answer and rendered context were passed to the candidate's `judge_prose_quality`; `scenario_framing` failed again. No user message was regenerated in that replay.
- One permitted case rerun: passed with no failed checks or infrastructure errors, published research, three rows and five sources, and a passing prose judge. No second full candidate run or further case rerun was started.
- The full scorecard's failure remains visible. Supplemental evidence is `docs/reports/evidence/2026-09-12-main-promotion/eval-run/recorded-judge-replay.json` and `docs/reports/evidence/2026-09-12-main-promotion/eval-run/single-case-rerun.json`.
- Release-doc validation: 23 passed, one failed in 11.11 seconds. The failing test is `test_main_promotion_manifests_require_live_eval_scorecard_evidence`, now because `tests/release_promotion_evidence_support.py:236` requires both sides of a targeted interleaved A/B, with at least ten attempts per side. This rule entered at `5d408acf` before main at the cut. It has not been changed or bypassed. Evidence: `docs/reports/evidence/2026-09-12-main-promotion/release-docs-completed-scorecard.log` and `docs/reports/evidence/2026-09-12-main-promotion/release-policy-stop.json`.
- Classification: release-policy conflict, not an established product regression. The research timeout did not recur in the one allowed case rerun. No ten-pair measurement, further full run, or extra case rerun was started. Fix rounds used: zero.
- Final cost including the original baseline, partial candidate, fresh full candidate, recorded judge and permitted case rerun: tracked `$4.88888657926`, reserve `$1.02`, guarded total `$5.90888657926` of `$7.50`. Fresh full candidate cost alone is `$1.8923231143`. The reserve is not spend. Evidence: `docs/reports/evidence/2026-09-12-main-promotion/approved-eval-comparison.json` and `eval-run/all-attempt-events.jsonl` in the same directory.
- Declined proposal: the founder declined a validator change and explicitly made the existing release rule authoritative. The later targeted A/B authorization and results below supersede this policy-conflict stop. The validator remains unchanged.

Preflight confirmed the measured head, all 71 fixtures and 84 user turns, a clean detached worktree, local module imports, unchanged observer bytes, and the identical process environment and env-file content hash. The completed baseline is retained byte-for-byte. The new guardian appends to the original cost ledger, records the starting event boundary to separate this attempt, and uses an exclusive launch marker to prevent a second launch.

The replay cohort was counted read-only before pricing using both date boundaries. The New York product day is `2026-08-12T04:00:00Z` through `2026-08-13T04:00:00Z`: 12 guest conversations from 12 people, with 25 user turns across their complete histories. The UTC day is midnight to midnight: 14 guest conversations from 14 people, with 35 full-history user turns. Canary and internal accounts are excluded. The initial plan selected New York alone; the founder later selected the deduplicated union of New York and UTC, recorded below; both counts were reported to the founder before any replay price estimate. Customer message text has not been selected. After reporting both counts, the higher completed-eval tracked cost per user turn (`$0.0225276561`) gives a rounded-up New York estimate of `$0.57`, or `$0.79` for the UTC comparison. These are tracked-cost estimates, excluding unknown receipt costs and the separate guard reserve; the replay stop remains `$4`. No replay has run. Evidence: `docs/reports/evidence/2026-09-12-main-promotion/replay-price-estimate.json`.

At head `0e622738`, PR #603's red CI is the single release-doc test waiting on the complete candidate scorecard. With that scorecard now present locally, the same test reaches the ten-pair policy requirement and fails there. The completed Codex review summary belongs to `2d99bcb4edc6c9e817a524fa295c8d67776ff549`. A fresh Codex review will be requested at the final head; the earlier summary does not satisfy that requirement.

The owned local stack restarted and reset from the measured migrations. Its initial port check encountered the old browser connection in `FIN_WAIT_2`, with no active listener. The scratch launcher now uses normal reusable-address bind semantics for this availability check; no product code, port, or other stack changed. The production web rebuild and empty-environment assertions passed, followed by API health, web health, and readiness. Paid browser turns remain pending the release-policy decision. After the stop, owned API/web/guard processes were stopped and `supabase stop --no-backup --workdir <owned scratch>` succeeded. All owned ports closed, no owned containers remain, and the unrelated stack remained intact. Evidence: `docs/reports/evidence/2026-09-12-main-promotion/local-acceptance/cleanup-release-gate.json`; restart and environment proofs are adjacent. No customer text was pulled.

## Step 3 Targeted Interleaved A/B (Historical Sharing-On Result)

Completed ten paired rounds in the identical Environment B, retaining the first four pairs and every native result. The founder superseded the earlier failure-gap stop and required completion under the unchanged `$12.50` cumulative cost-plus-reserve cap. The validator remains unchanged. No additional full eval run or single-case retry was started.

- Case: `messy_spanish_future_performance_nvda_cruce_dorado`.
- Deployed side: `ee9c3491fa6219502f1e94abc5d9e661a06839d9`; candidate side: `df7aee12955f667e31057464d62c72287fb12247`.
- Baseline A/B evidence: `docs/reports/evidence/2026-09-12-main-promotion/targeted-ab-baseline.json`.
- Candidate A/B evidence: `docs/reports/evidence/2026-09-12-main-promotion/targeted-ab-candidate.json`.
- Native whole-case failure rates: deployed `0/10 (0%)`; candidate `6/10 (60%)`. Research timeout counts: deployed `0`, candidate `1`. Timeouts count as failed attempts; no failure was discarded or rewritten.
- Each side records clean-worktree provenance, exact source SHA, fixture and case hashes, provider modes, Python version and live holiday-alignment probe. Inputs are identical; committed expectations differ. Production expects an honest future-performance limitation; candidate expects research with cited scenarios. These native rates do not imply identical rubrics.
- First-pair projected combined guard was `$6.4607520213`, checked before attempt three. Evidence: `docs/reports/evidence/2026-09-12-main-promotion/targeted-ab/first-pair-projection.json`. Its first candidate attempt failed cheaply with a provider HTTP error, so it was an uncertain forecast; the hard cumulative guard remained active.
- Historical stop: the first four pairs stopped at deployed `0/4`, candidate `3/4`. The founder then classified the finding and authorized the remaining six pairs. The historical record remains in `docs/reports/evidence/2026-09-12-main-promotion/targeted-ab/status.json` and `docs/reports/evidence/2026-09-12-main-promotion/targeted-ab-verification.json`; the completed record is `docs/reports/evidence/2026-09-12-main-promotion/targeted-ab/resume-status.json`.
- Finding and cause: forward-looking questions now depend on research. The provider-error path has no retry, so an error window immediately becomes a disclosed search-unavailable answer. Founder-provided evidence records other requests with `research_unavailable_http_error` at `06:27Z` and `06:30Z`, before the A/B, and confirms candidate attempts 1 and 3 occurred in the same broader provider-error window. Unchanged inputs also published research. These are **provider-side research delivery failures, not candidate request defects**. Their earlier HTTP status values were not retained and are not inferred. Candidate attempt 4 gave the same future-performance limitation production gives and passed its prose judge, so the founder classified it as **no worse than production**; its native typed failure remains visible.
- Continued attempts: candidate 6 recorded `research_unavailable_timeout` with no response status; candidate 9 recorded `research_unavailable_http_error` with HTTP **500**. Candidate 10 returned the same production-style future-performance limitation, with its prose judge passing. Comparing it with deployed attempt 10 supports the same no-worse category as attempt 4; native typed failures remain counted. Overall, candidate published research in 4/10 attempts, had three provider HTTP failures and one research timeout, and gave the production-style limitation in two attempts. No cooldown was required.
- **First follow-up: research retry on provider errors**, with usage/cost accounting preserved and disclosed unavailability if delivery still fails. No retry, routing or model-facing text change was made. The founder decides at the merge stop whether to promote with this follow-up pending. Evidence: `docs/reports/evidence/2026-09-12-main-promotion/founder-research-disposition.json` and `docs/reports/evidence/2026-09-12-main-promotion/targeted-ab-finding.json`.
- HTTP status capture on continued attempts uses a read-only native-client observer, identical on both sides, with no new environment keys or product changes. HTTP error responses after resumption: `[{"attempt":9,"http_errors":[{"kind":"research_http_error","attempt":9,"http_status":500,"method":"POST","time":1789284822.287584}]}]`. A timeout without an HTTP response has no HTTP status. The observer's free check covered HTTP 429 and 503 and did not enter the live cost ledger. Evidence: `docs/reports/evidence/2026-09-12-main-promotion/targeted-ab/http-observer-free-check.json`.
- The guardian enforces a 900-second pause before the next pair after three consecutive candidate research delivery failures. Recorded cooldowns: `0`. Full timestamps, if any, remain in the resumed status artifact.
- Combined eval tracked cost: `$6.0129416335`. Separate reserve: `$1.16`. Guarded total: `$7.1729416335` of `$12.50`. All previous baseline, partial candidate, full candidate, judge and permitted retry costs remain included. The reserve is not spend.
- Integrity proof: `docs/reports/evidence/2026-09-12-main-promotion/targeted-ab-completion-verification.json`. All 20 native attempt hashes, both native full-scorecard hashes, environment-source hash, alternating order, native clean worktrees, ledger totals and all non-doc Git paths verified. Fix rounds used: zero.
- Prior free mocked harness: 259 passed. At `fc2eaa99`, PR #603's only backend CI failure was the release-doc test waiting on ten attempts per side; 7,861 backend tests passed. Completion evidence is now present for the unchanged validator. All 24 release evidence checks passed in 28.07 seconds, recorded in `docs/reports/evidence/2026-09-12-main-promotion/release-docs-completed-ab.log`. Final acceptance-head CI and a fresh Codex review are still required; the earlier summary belongs to `2d99bcb`.

| Round | Deployed | Candidate |
| --- | --- | --- |
| 1 | pass | fail (`research_unavailable_http_error`) |
| 2 | pass | pass |
| 3 | pass | fail (`research_unavailable_http_error`) |
| 4 | pass | fail (no worse than production; prose passed) |
| 5 | pass | pass |
| 6 | pass | fail (`research_unavailable_timeout`) |
| 7 | pass | pass |
| 8 | pass | pass |
| 9 | pass | fail (`research_unavailable_http_error`); HTTP 500 |
| 10 | pass | fail (production-style limitation; prose passed) |

## Replay Union and Historical Browser Approval Stop

The cohort and price were reported before execution. New York has 12 guest conversations / 25 full-history user turns; UTC has 14 / 35. Their deduplicated union has 15 conversations from 15 people and 38 user turns, spanning `2026-08-12T00:00:00Z` through `2026-08-13T04:00:00Z`. Canary and internal accounts are excluded. Read-only extraction confirmed exactly 15 conversations and 38 user messages. Production identities were not serialized.

The higher completed full-eval tracked cost per turn (`$0.0225276561`) gave the reported rounded-up estimate of `$0.86`, excluding unpriced receipt costs and the separate reserve. Evidence: `docs/reports/evidence/2026-09-12-main-promotion/replay-union-counts.json` and `docs/reports/evidence/2026-09-12-main-promotion/replay-union-price-estimate.json`. Actual replay tracked cost was `$1.7073169653`, above that estimate; with `$0.18` reserve, the guard was `$1.8873169653` of `$4`. The reserve is not spend. The hard guard remained active throughout.

- Replay result: `completed`, **38 pass, 0 fail, 0 allowance**, across 38 assessed turns. Each input and user-visible response was privately read against the board's rule: no refusal naming a capability the person did not ask about. An allowance message would be counted separately. These outcomes assess that refusal rule; they do not replace browser acceptance of rendered controls.
- A separate research delivery failure occurred at case 12, turn 3: provider HTTP **429**, with disclosed search unavailability. It did not name an unrelated unavailable capability, so it passes the stated refusal rule. It is retained as a delivery failure, not an Argus user allowance. No retry was performed. Evidence: `docs/reports/evidence/2026-09-12-main-promotion/replay/replay-delivery-observations.json`. This also supports the already named first follow-up, research retry on provider errors.
- Every conversation received a fresh local guest. User messages ran in order in Environment C. Original interactive action payloads were not replayed; the authorized unit is the stored user message. No synthetic replacement questions or paid retry were added.
- The API and production web build used the measured Render literals and only the approved substitutions. Both `.env` and `web/.env.local` were absent. Readiness, API and web health passed before extraction. The initial local launcher used a wrong readiness URL and received HTTP 404 before extracting any customer text; the harness URL was corrected to the repository-owned `/internal/readiness`. No product code, environment value or timeout changed.
- Automatic approval review initially rejected the replay's provider authorization. Read-only checks confirmed the explicitly approved cohort, Environment C providers and private handling; re-review accepted the same authorized action. No alternate destination or execution workaround was used.
- Inputs and SSE frames remained in private scratch outside the repository. The owned API/web processes stopped, `supabase stop --no-backup --workdir <owned scratch>` succeeded, the disposable database and private inputs/frames/logs were removed, owned ports closed and unrelated stacks remained intact. Public evidence contains numbered verdicts and operational metadata only.
- Results and cost: `docs/reports/evidence/2026-09-12-main-promotion/replay/replay-results.json`; environment: `docs/reports/evidence/2026-09-12-main-promotion/replay/environment-proof.json`; startup: `docs/reports/evidence/2026-09-12-main-promotion/replay/replay-startup-health.json`; cleanup: `docs/reports/evidence/2026-09-12-main-promotion/replay/cleanup-replay.json`; research provider error statuses, without customer text: `docs/reports/evidence/2026-09-12-main-promotion/replay/replay-provider-error-statuses.json`.
- Free validation: all 259 mocked harness checks passed in 34.45 seconds. The unchanged release-evidence validator passed all 24 checks after receiving ten attempts on each A/B side. Evidence: `docs/reports/evidence/2026-09-12-main-promotion/mocked-completed-ab.log` and `docs/reports/evidence/2026-09-12-main-promotion/release-docs-completed-ab.log`.
- Final checkpoint verification: `docs/reports/evidence/2026-09-12-main-promotion/replay-completion-verification.json`. All 24 release-evidence checks passed again on the completed replay record in 27.68 seconds, with the native validator unchanged. Evidence: `docs/reports/evidence/2026-09-12-main-promotion/release-docs-replay-complete.log`.
- At this historical checkpoint, browser spend was `$0` of `$3`. The founder subsequently approved the unattended walk recorded below. Fresh Codex review remains required at the final acceptance head; the earlier summary is on `2d99bcb`. No terminal audit or merge-ready claim is made.

| Case | Turn | Outcome | Refusal code | Named capability |
| --- | --- | --- | --- | --- |
| 1 | 1 | pass | none | none |
| 1 | 2 | pass | none | none |
| 1 | 3 | pass | none | none |
| 2 | 1 | pass | none | none |
| 2 | 2 | pass | none | none |
| 2 | 3 | pass | none | none |
| 2 | 4 | pass | none | none |
| 2 | 5 | pass | none | none |
| 2 | 6 | pass | none | none |
| 2 | 7 | pass | none | none |
| 2 | 8 | pass | none | none |
| 2 | 9 | pass | none | none |
| 3 | 1 | pass | none | none |
| 4 | 1 | pass | none | none |
| 4 | 2 | pass | none | none |
| 5 | 1 | pass | none | none |
| 5 | 2 | pass | none | none |
| 5 | 3 | pass | none | none |
| 6 | 1 | pass | none | none |
| 7 | 1 | pass | none | none |
| 8 | 1 | pass | none | none |
| 9 | 1 | pass | none | none |
| 9 | 2 | pass | none | none |
| 10 | 1 | pass | none | none |
| 10 | 2 | pass | none | none |
| 10 | 3 | pass | none | none |
| 10 | 4 | pass | none | none |
| 11 | 1 | pass | none | none |
| 12 | 1 | pass | none | none |
| 12 | 2 | pass | none | none |
| 12 | 3 | pass | none | none |
| 12 | 4 | pass | none | none |
| 13 | 1 | pass | none | none |
| 14 | 1 | pass | none | none |
| 14 | 2 | pass | none | none |
| 15 | 1 | pass | none | none |
| 15 | 2 | pass | none | none |
| 15 | 3 | pass | none | none |

## Unattended Browser Walk: Sharing Stop, 2026-09-13

The founder approved the full English and Spanish walk unattended, with a $3 cap and no fix round. Environment C was rebuilt and started from the audited empty environment at the measured head. Its own Supabase stack was reset from the measured migrations. All environment assertions passed; shadow jobs stayed enabled and both observed jobs succeeded. The browser record is the acceptance evidence.

**P1, new blocking sharing finding:** the chat-header selector showed **0 of 0 selected**. The completed backtest was labeled not complete, while the sourced Breakdown was labeled unsafe. Native read-only reproduction shows both saved jobs pass the completion predicate and all result/artifact links match. Separately, `audit_text` rejects an ordinary public Coca-Cola publisher link as `unsafe_text`: its long URL path matches the secret-shaped text guard. This answer-selection path is absent at the deployed baseline. The full cause of the separate completed-result eligibility mismatch remains open. No fallback flag or product code was changed. Evidence: `browser-walk/en-20-sharing-selection.png`, its `.txt`, `sharing-diagnosis.json`, and the read-only reproduction `diagnose_browser_sharing.py`, under `docs/reports/evidence/2026-09-12-main-promotion/`.

The founder's Step 6 rule requires a stop for a real blocking sharing finding. Accordingly, local link creation, signed-out phone viewing, revocation, the remaining clarification check and the remaining Spanish walk were not executed. No link exists. The fallback decision is a sharing-off promotion, with the remaining acceptance still owed, or holding for a sharing fix. This record authorizes neither option and is not a Step 7 merge-ready audit.

Other findings and outcomes:

- **P2, non-blocking:** the English result follow-up repeated four next steps in prose and again under Try next. Its gap, cost dollars and worst-drop dates matched the saved run. The new follow-up owner is in this bundle; deployed occurrence was not replayed, so no baseline behavioral claim is made. No model-facing text was changed. Evidence: `duplicate-next-steps-finding.json`, `en-14-result-follow-up.png`, and `.txt`.
- **P2, new observability defect:** `result_summary` now uses the `readout` tier, but the database check still allows only utility, chat, structured and context. Native error: `new row for relation "route_receipts" violates check constraint "route_receipts_tier_check"`. The Quick take reached the user; its route receipt and downstream cost-ledger persistence failed. The separate process observer retained spend. Evidence: `readout-receipt-finding.json`.
- **Provider delivery:** English valuation research failed with HTTP 500. Its single approved retry began 132.374 seconds after the recorded failure and timed out without an HTTP response status. Both disclosed lookup unavailability and quoted no live figures. No second retry ran. This adds evidence to the already founder-classified research-delivery finding. **Research retry on provider errors remains the first follow-up**, subject to the founder's promotion decision.
- **Existing Spanish confirmation wording:** the founder confirmed that the English confirmation summary in Spanish conversations already exists on the deployed build. This stopped walk did not reach that surface, so it is recorded as founder-provided baseline evidence, not a new or newly reproduced finding.
- English signup, first country save, reload, Usage, two sequential card edits, a monthly-contribution backtest, Quick take, Breakdown, exact result facts, feedback save/dismissal, decision save/reload and the result's rail navigation passed. The rail appears after the transcript reaches its normal length threshold; a saved decision changes the result tick to Decision saved. Local persistence confirmed one profile, one feedback row, one completed run and one decision. Both guest greetings passed. A same-chat clarification setup inherited the prior period and did not ask a question; that did not satisfy the required clarification check, which remained owed at the sharing stop.

**Spend:** $0.1330577 tracked + $0.10 reserve = $0.2330577 guarded of $3. The reserve is not spend. The unchanged eval total remains $6.0129416335 tracked + $1.16 reserve = $7.1729416335 of $12.50; historical replay remains $1.70731696526 + $0.18 reserve = $1.88731696526 of $4. Evidence: `budget-final.json` and `cost-events.json` in the browser-walk directory.

**Environment and cleanup:** `environment-proof.json` carries the key-by-key record; `startup-proof.json` and `restart-proof.json` bind the build to the measured head. The approved differences remain in-process backtests, localhost origins, no Turnstile widget, no PostHog and no real application email. Feedback saved once; its expected local email warning is covered by that difference. Owned API/web processes stopped, `supabase stop --no-backup --workdir <owned scratch>` passed, all owned ports closed and owned containers/volumes were removed. Unrelated stacks were preserved. Raw API/web logs were deleted after retaining sanitized findings and cost evidence. See `cleanup-browser.json`. Historical replay inputs remained deleted throughout.

The table below is the full walk record at the stop. Every executed row has a screenshot and captured visible text. A not-run row has no fabricated screenshot or acceptance claim. Screenshot and text links resolve into the committed browser-walk directory. `steps.json` retains timestamps, exact expectations and dispositions; `not-run.json` enumerates the remaining scope.

| Language / step | Expected | Visible text that matters | Result and reason | Evidence |
| --- | --- | --- | --- | --- |
| en-01-guest-greeting | Empty guest chat shows an English greeting and enabled composer. | What should we look into? | PASS: English greeting and composer are visible. | [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-01-guest-greeting.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-01-guest-greeting.txt) |
| es-01-guest-greeting | Empty guest chat shows the Spanish greeting and composer. | ¿Qué te gustaría investigar? | PASS: Greeting, suggestions and composer are Spanish. | [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/es-01-guest-greeting.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/es-01-guest-greeting.txt) |
| en-02-signed-in-greeting | A new local account reaches the empty signed-in English chat. | What should we look into?; Search; Settings | PASS: Signup reached the English chat with signed-in sidebar controls. | [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-02-signed-in-greeting.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-02-signed-in-greeting.txt) |
| en-03-first-profile-save-country | First home-country save succeeds and derives USD. | Country United States; Currency USD | PASS: United States and USD are shown after the first country save. | [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-03-first-profile-save-country.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-03-first-profile-save-country.txt) |
| en-04-profile-reload | Saved country and derived currency survive a reload. | Country United States; Currency USD | PASS: United States and USD persisted after reload. | [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-04-profile-reload.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-04-profile-reload.txt) |
| en-05-usage | Usage labels read Usage, Conversation, Searches with sources, Simulations. | Usage; Conversation; Searches with sources; Simulations | PASS: All four approved English labels are visible. | [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-05-usage.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-05-usage.txt) |
| en-06-confirmation | The DCA draft preserves starting capital and monthly contribution and discloses any date adjustment. | $200 monthly; $5,000; Jul 27, 2020 → Dec 31, 2024 | PASS: Card shows $5,000, $200 monthly and the disclosed available-data start. | [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-06-confirmation.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-06-confirmation.txt) |
| en-07-first-card-edit | Changing starting capital preserves the recurring contribution. | $200 monthly; $6,000 | PASS: $6,000 starting capital is saved with $200 monthly unchanged. | [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-07-first-card-edit.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-07-first-card-edit.txt) |
| en-08-second-card-edit | A costs edit preserves the earlier capital edit and monthly contribution. | $6,000; $200 monthly; 10 bps fee + 5 bps slippage | PASS: 10 bps fee and 5 bps slippage are saved with $6,000 and $200 monthly intact. | [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-08-second-card-edit.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-08-second-card-edit.txt) |
| en-09-result-quick-take-feedback | A result, Quick take and one feedback ask appear after the backtest. | Simulation Complete; Quick take; How is Argus doing? | PASS: Result and Quick take are present with one How is Argus doing prompt. | [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-09-result-quick-take-feedback.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-09-result-quick-take-feedback.txt) |
| en-10-feedback-rated | Rating the feedback ask saves and acknowledges it. | Thanks for telling us. | PASS: The prompt changed to Thanks for telling us after Good. | [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-10-feedback-rated.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-10-feedback-rated.txt) |
| en-11-result-details | Expanded result details preserve contributions, assumptions and net costs. | $16,800; Starting capital $6,000; Contribution $200 monthly | PASS: Details show $16,800 contributed, $6,000 starting capital, $200 monthly and modeled costs. | [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-11-result-details.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-11-result-details.txt) |
| en-12-breakdown | Breakdown gives a sourced holding experience grounded in the result. | Breakdown; 54 purchases and no sales; 3 sources | PASS: Breakdown preserved DCA amounts, 38.1-point gap and April 21, 2022 to October 5, 2023 worst-drop dates with three sources. | [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-12-breakdown.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-12-breakdown.txt) |
| en-13-breakdown-dates | The lower Breakdown shows exact worst-drop dates and benchmark gap. | April 21, 2022; October 5, 2023; 38.1 percentage points | PASS: Dates and the 38.1-percentage-point gap are visible in the Breakdown. | [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-13-breakdown-dates.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-13-breakdown-dates.txt) |
| en-14-result-follow-up | The follow-up states gap, dollar costs and worst-drop dates with one next-steps list. | $25.17 in total: $16.78 in fees and $8.39 in slippage; four prose steps plus Try next | FAIL: Facts are correct, but next steps appear twice: a prose list and the matching Try next controls. | [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-14-result-follow-up.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-14-result-follow-up.txt) |
| en-15-decision-saved | A decision saves on the result. | Decision: Watching | PASS: The result now reads Decision: Watching. | [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-15-decision-saved.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-15-decision-saved.txt) |
| en-16-feedback-and-decision-reload | After another reply and reload, feedback stays dismissed and decision and Breakdown persist. | Decision: Watching; Breakdown; feedback ask absent | PASS: No feedback ask returned; Decision: Watching and the finished Breakdown survived reload. | [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-16-feedback-and-decision-reload.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-16-feedback-and-decision-reload.txt) |
| en-17-research-attempt-1 | The valuation and outlook question publishes research with sources. | I couldn't complete the data lookup just now, so I won't quote live figures. | FAIL: The turn disclosed that data lookup could not complete and published no live figures. | [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-17-research-attempt-1.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-17-research-attempt-1.txt) |
| en-18-research-attempt-2 | One retry after two minutes publishes the requested research. | I couldn't complete the data lookup just now, so I won't quote live figures. | FAIL: The single retry timed out and again disclosed lookup unavailability. | [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-18-research-attempt-2.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-18-research-attempt-2.txt) |
| en-19-result-rail | A long conversation shows a tick that navigates to its saved result. | Decision saved: KO · DCA Accumulation | PASS: The KO result appears as Decision saved after its decision was added, and the tick navigates to it. | [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-19-result-rail.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-19-result-rail.txt) |
| en-20-sharing-selection | Completed result and sourced answers can be selected in the chat-header sharing dialog. | 0 of 0 selected; This answer is not complete yet; The text contains private information or codes. | FAIL: The dialog shows 0 of 0 selected; every answer is disabled, including the completed result and sourced Breakdown. | [image](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-20-sharing-selection.png) / [text](../reports/evidence/2026-09-12-main-promotion/browser-walk/en-20-sharing-selection.txt) |
| en / Clarifying reply preserves an earlier fact | Clarifying reply preserves an earlier fact | Not observed | NOT RUN: The same-chat setup inherited the prior period and did not ask a question. A fresh-chat clarification was still owed when the sharing stop occurred. | No capture after the blocking stop |
| en / Sharing preview and local link creation | Sharing preview and local link creation | Not observed | NOT RUN: Stopped at the confirmed English sharing blocker under Step 6. | No capture after the blocking stop |
| en / Signed-out phone-width shared answer | Signed-out phone-width shared answer | Not observed | NOT RUN: Stopped at the confirmed English sharing blocker under Step 6. | No capture after the blocking stop |
| en / Revoke local link | Revoke local link | Not observed | NOT RUN: Stopped at the confirmed English sharing blocker under Step 6. | No capture after the blocking stop |
| en / Revoked link stops working | Revoked link stops working | Not observed | NOT RUN: Stopped at the confirmed English sharing blocker under Step 6. | No capture after the blocking stop |
| es-419 / Signed-in empty greeting | Signed-in empty greeting | Not observed | NOT RUN: Stopped at the confirmed English sharing blocker under Step 6. | No capture after the blocking stop |
| es-419 / New account first profile save | New account first profile save | Not observed | NOT RUN: Stopped at the confirmed English sharing blocker under Step 6. | No capture after the blocking stop |
| es-419 / Home country persistence | Home country persistence | Not observed | NOT RUN: Stopped at the confirmed English sharing blocker under Step 6. | No capture after the blocking stop |
| es-419 / Usage labels | Usage labels | Not observed | NOT RUN: Stopped at the confirmed English sharing blocker under Step 6. | No capture after the blocking stop |
| es-419 / Backtest confirmation | Backtest confirmation | Not observed | NOT RUN: Stopped at the confirmed English sharing blocker under Step 6. | No capture after the blocking stop |
| es-419 / First card edit | First card edit | Not observed | NOT RUN: Stopped at the confirmed English sharing blocker under Step 6. | No capture after the blocking stop |
| es-419 / Second edit retains first | Second edit retains first | Not observed | NOT RUN: Stopped at the confirmed English sharing blocker under Step 6. | No capture after the blocking stop |
| es-419 / Result and Quick take | Result and Quick take | Not observed | NOT RUN: Stopped at the confirmed English sharing blocker under Step 6. | No capture after the blocking stop |
| es-419 / Breakdown with sources | Breakdown with sources | Not observed | NOT RUN: Stopped at the confirmed English sharing blocker under Step 6. | No capture after the blocking stop |
| es-419 / Conversation after result: one next-step list, gap, dollar costs, worst-drop dates | Conversation after result: one next-step list, gap, dollar costs, worst-drop dates | Not observed | NOT RUN: Stopped at the confirmed English sharing blocker under Step 6. | No capture after the blocking stop |
| es-419 / Feedback ask once | Feedback ask once | Not observed | NOT RUN: Stopped at the confirmed English sharing blocker under Step 6. | No capture after the blocking stop |
| es-419 / Feedback rating and no return | Feedback rating and no return | Not observed | NOT RUN: Stopped at the confirmed English sharing blocker under Step 6. | No capture after the blocking stop |
| es-419 / Clarifying reply preserves an earlier fact | Clarifying reply preserves an earlier fact | Not observed | NOT RUN: Stopped at the confirmed English sharing blocker under Step 6. | No capture after the blocking stop |
| es-419 / Forward-looking or valuation research with sources | Forward-looking or valuation research with sources | Not observed | NOT RUN: Stopped at the confirmed English sharing blocker under Step 6. | No capture after the blocking stop |
| es-419 / Decision saved on result | Decision saved on result | Not observed | NOT RUN: Stopped at the confirmed English sharing blocker under Step 6. | No capture after the blocking stop |
| es-419 / Result rail tick | Result rail tick | Not observed | NOT RUN: Stopped at the confirmed English sharing blocker under Step 6. | No capture after the blocking stop |
| es-419 / Pick answers from chat header | Pick answers from chat header | Not observed | NOT RUN: Stopped at the confirmed English sharing blocker under Step 6. | No capture after the blocking stop |
| es-419 / Sharing preview and local link creation | Sharing preview and local link creation | Not observed | NOT RUN: Stopped at the confirmed English sharing blocker under Step 6. | No capture after the blocking stop |
| es-419 / Signed-out phone-width shared answer | Signed-out phone-width shared answer | Not observed | NOT RUN: Stopped at the confirmed English sharing blocker under Step 6. | No capture after the blocking stop |
| es-419 / Revoke local link | Revoke local link | Not observed | NOT RUN: Stopped at the confirmed English sharing blocker under Step 6. | No capture after the blocking stop |
| es-419 / Revoked link stops working | Revoked link stops working | Not observed | NOT RUN: Stopped at the confirmed English sharing blocker under Step 6. | No capture after the blocking stop |

Free checks on this stop record passed: 24 release-evidence tests in 22.30 seconds and 259 mocked harness checks in 34.93 seconds. Logs: `browser-walk/release-docs-tests.log` and `browser-walk/mocked-harness.log`. `browser-walk/verification.json` confirms no non-doc changes, measured-tree byte identity, absent acceptance env files, valid evidence paths and the secret scan.

CI and fresh exact-head review are checked on the docs-only evidence head after this record is committed. Their receipts belong to PR #603; the earlier review on `2d99bcb` is not proof for this head. A green CI or clean code-review result does not close this sharing blocker or the unexecuted acceptance scope.

## Historical Step 2 Stop Record (Superseded by Approved Resumption)

Evidence directory: `docs/reports/evidence/2026-09-12-main-promotion/`.

- `production-readback-before.json`: all three live triggers are `off`; API and app are `live` at `ee9c3491fa6219502f1e94abc5d9e661a06839d9`, workflow is `ready` at `ee9c349`. These values were read only.
- `main-branch-protection-before.json`: required context `ci`, strict checks and admin enforcement on, force pushes and branch deletion off. Nothing changed.
- `setup.log`: required setup completed with the explicit canonical-root override, Python 3.10.20, Poetry 2.1.3 and Bun 1.3.14.
- `mocked-eval.log`: 259 passed, exit 0, 41.93 seconds. Provider credentials blanked and synthetic data selected.
- `release-contract-tests.log`: 87 passed and one failed, exit 1. The new skeleton has no durable live eval scorecard because Step 3 has not run. This is an outstanding evidence requirement, not a product regression. No test was weakened or waived.
- `modularity.log`: no violations. Main is an ancestor, so the candidate is also the would-be merged product tree.
- `local-smoke.log`: exit 28 after API health and workflow probe passed. Exact error: `curl: (28) Operation timed out after 20010 milliseconds with 0 bytes received`. Product readiness did not complete. Cause is unclassified; no retry, timeout change or product fix has been made. The smoke processes exited and no listener remains on their ports 8126 or 3126.
- `environment-parity-before.json`: Render literals, release-profile keys and contract arrays agree for API and web. The template inventory found undocumented settings: `CUADRAO_STRUCTURED_REASONING_EFFORT`, `CUADRAO_CAPABILITY_REASONING_EFFORT`, `ARGUS_ENV`, `ARGUS_APP_ENV`, `ARGUS_RENDER_WORKFLOW_PROOF_TIMEOUT_SECONDS`, `ARGUS_RENDER_WORKFLOW_PROOF_POLL_SECONDS`, and `ARGUS_WORKFLOW_PROOF_USER_ID`. These are documentation gaps, not an established product regression. Their absence from the live release contract means the production defaults still apply. The initial static inventory is not exhaustive; dynamic task-timeout keys remain to be covered by the resumed full parity pass.
- `DATABASE_URL` is intentionally derived and documented; `MEM0_TELEMETRY` is forced off internally; `RENDER_TASK_RUN_ID` is platform-supplied. These are not requested configuration changes.
- `measured-tree-identity.json`: the product paths from the prior promotion and every non-doc Git path are unchanged from the measured head. This stop-record commit contains docs and evidence only.
- `preflight-status.json`: gate outcomes, zero spend, no live mutations and local cleanup record.

The founder's explicit stop rule for an unexpected environment check applies. The migration gate, promotion PR, Step 3 pair, founder browser walk and historical replay have not started. No production user text was extracted. Spend is $0 of $3.50 for the pair, $0 of $3 for the walk, and $0 of $4 for replay. No fix round has been used.

Requested decision: approve a bounded environment-template correction and resumption of Step 2, or accept the documented template gaps for this promotion. This does not authorize a migration, live setting change, deployment, merge, or production sharing link.


## Step 2 Approved Resumption

The founder approved the template correction and one unchanged smoke rerun in this task. Commit `df7aee12955f667e31057464d62c72287fb12247` adds 31 one-line setting descriptions to `.env.example`, including the original seven and the full parity findings. They are comments; parsed template values are unchanged. No real environment file was written. This commit defines the measured head before any paid measurement.

- `environment-parity-after.json`: full pass across 144 runtime/operator keys, including all 15 dynamic task timeout keys. No intended hosted setting is missing from the release contract. Optional undeclared settings retain production code defaults.
- `template-added-keys.json`: complete list of 31 additions and unchanged effective template values. The founder confirmed the original seven gaps predate this bundle.
- `direct-readiness.json`, `direct-readiness.log`, `direct-readiness-api.log`: the one direct timed request in the unchanged smoke environment returned HTTP 503 in 1.178 seconds. The runtime and synthetic asset check were ready; memory-mode Supabase degradation is expected by this smoke.
- `local-smoke-rerun-status.json`, `local-smoke-rerun.log`, `local-smoke-rerun-api.log`, `local-smoke-rerun-web.log`: the single approved rerun at the new measured head passed, exit 0, in 5.394 seconds. Neither timeout changed. Both timeout-owning files are byte-identical to main.
- `free-gates-df7aee12.log`: mocked and release checks totaled 346 passed, one failed in 34.18 seconds. The sole failure is the pending durable live scorecard requirement for this manifest. It must pass after Step 3; no test was weakened.
- `modularity-df7aee12.log`: passed. No newer integration work was included.
- `production-migration-gate-before.json`: expected seven-migration block, read only. Historical reconciliation matches; no additional stop reason. No schema application occurred.
- `measured-tree-identity.json`: product paths and every non-doc Git path match the new measured head. Later evidence commits touch only docs.

The initial stop record above is retained as history, not an outstanding approval request. Paid spend remains zero for each of the eval pair, browser walk and replay. No production conversation content has been extracted. No fix round has been used.

## Local Production Configuration Key Record

Captured before startup at the measured head. Secret-bearing keys record only presence. Every literal is set, and only the founder-approved substitutions differ. No value contains the production Supabase reference or production app domain. Process basics are PATH and HOME.

### argus-api

| Key | Local value or secret presence |
| --- | --- |
| `ALPACA_API_KEY` | `present` |
| `ALPACA_PAPER_TRADING` | `true` |
| `ALPACA_SECRET_KEY` | `present` |
| `APP_ENV` | `production` |
| `CUADRAO_APPROVAL_EMAIL_SMTP_PASSWORD` | `absent` |
| `ARGUS_APP_ORIGIN` | `http://localhost:3136` |
| `ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED` | `false` |
| `ARGUS_BACKTEST_JOBS_GLOBAL_QUEUED_LIMIT` | `10` |
| `ARGUS_BACKTEST_JOBS_GLOBAL_RUNNING_LIMIT` | `5` |
| `ARGUS_BACKTEST_JOBS_SHADOW_ENABLED` | `true` |
| `ARGUS_BACKTEST_JOBS_USER_QUEUED_LIMIT` | `2` |
| `ARGUS_BACKTEST_JOBS_USER_RUNNING_LIMIT` | `1` |
| `ARGUS_BACKTEST_REAL_WORKFLOW_TASK` | `argus-backtests/run_backtest_job` |
| `ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED` | `false` |
| `ARGUS_BACKTEST_WORKFLOW_TASK` | `argus-backtests/workflow_proof` |
| `CUADRAO_CHAT_FALLBACK_MODEL` | `qwen/qwen3.5-9b` |
| `CUADRAO_CHAT_MODEL` | `deepseek/deepseek-v4-flash` |
| `CUADRAO_CHECKPOINTER_MODE` | `postgres` |
| `CUADRAO_CONTEXT_FALLBACK_MODEL` | `deepseek/deepseek-v4-flash` |
| `CUADRAO_CONTEXT_MODEL` | `openai/gpt-oss-120b` |
| `ARGUS_CONTEXT_PACKETS_ENABLED` | `true` |
| `ARGUS_CONTEXT_PACKET_BUDGET_SECONDS` | `4` |
| `CUADRAO_CORS_ALLOW_ORIGINS` | `http://localhost:3136` |
| `ARGUS_DEV_MEMORY_FALLBACK` | `false` |
| `ARGUS_DISCOVERY_SEARCH_PROVIDER` | `perplexity_direct` |
| `ARGUS_ENABLE_EXECUTION_REALISM` | `true` |
| `ARGUS_ENABLE_MEMORY_SEMANTIC_RECALL` | `false` |
| `ARGUS_ENABLE_PERSONALIZATION_MEMORY` | `true` |
| `CUADRAO_EVIDENCE_RECEIPT_SHARING_ENABLED` | `true` |
| `CUADRAO_GUEST_ACCESS_OPENROUTER_API_KEY` | `present` |
| `ARGUS_IN_PLACE_CARD_EDITS_ENABLED` | `true` |
| `ARGUS_MARKET_DATA_PROVIDER_MODE` | `live_provider` |
| `ARGUS_MEMORY_EMBEDDING_DIMENSIONS` | `1024` |
| `ARGUS_MEMORY_EMBEDDING_MODEL` | `pplx-embed-v1-0.6b` |
| `ARGUS_MEMORY_EMBEDDING_TIMEOUT_SECONDS` | `8.0` |
| `ARGUS_MEMORY_VECTOR_COLLECTION` | `argus_memory_vectors` |
| `CUADRAO_MOCK_AUTH` | `false` |
| `CUADRAO_OPENROUTER_RESULT_SUMMARY_TIMEOUT_SECONDS` | `30` |
| `CUADRAO_OPS_TOKEN` | `present` |
| `CUADRAO_PERSISTENCE_MODE` | `supabase` |
| `CUADRAO_PROD_OPENROUTER_API_KEY` | `present` |
| `CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED` | `true` |
| `ARGUS_READINESS_ASSET_TIMEOUT_SECONDS` | `25` |
| `CUADRAO_READOUT_FALLBACK_MODEL` | `openai/gpt-5.6-luna` |
| `CUADRAO_READOUT_MODEL` | `openai/gpt-5.6-luna` |
| `ARGUS_RESEARCH_GLOBAL_DAILY_CEILING` | `5000` |
| `ARGUS_RESEARCH_RAIL_ENABLED` | `true` |
| `CUADRAO_RUNTIME_EVENT_KEEPALIVE_SECONDS` | `15` |
| `CUADRAO_RUNTIME_EVENT_TIMEOUT_SECONDS` | `180` |
| `CUADRAO_STRUCTURED_FALLBACK_MODEL` | `anthropic/claude-haiku-4.5` |
| `CUADRAO_STRUCTURED_MODEL` | `x-ai/grok-4.3` |
| `ARGUS_TITLE_AUTOGEN_ENABLED` | `true` |
| `ARGUS_TITLE_AUTOGEN_TIMEOUT_MS` | `250` |
| `CUADRAO_UTILITY_FALLBACK_MODEL` | `qwen/qwen3.5-9b` |
| `CUADRAO_UTILITY_MODEL` | `google/gemini-2.5-flash-lite` |
| `CUADRAO_VISITOR_KEY_SECRET` | `present` |
| `DATABASE_URL` | `present` |
| `HOME` | `/private/tmp/argus-promotion-20260912-supabase/home` |
| `MARKET_DATA_CACHE_TTL` | `43200` |
| `PATH` | `/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin` |
| `PERPLEXITY_API_KEY` | `present` |
| `POETRY_VERSION` | `2.1.3` |
| `POSTHOG_PROJECT_TOKEN` | `absent` |
| `POSTHOG_REGION` | `us` |
| `RENDER_API_KEY` | `absent` |
| `SUPABASE_ANON_KEY` | `present` |
| `SUPABASE_JWT_SECRET` | `present` |
| `SUPABASE_SERVICE_ROLE_KEY` | `present` |
| `SUPABASE_URL` | `http://127.0.0.1:56531` |

### argus-app

| Key | Local value or secret presence |
| --- | --- |
| `ARGUS_APP_ORIGIN` | `http://localhost:3136` |
| `HOME` | `/private/tmp/argus-promotion-20260912-supabase/home` |
| `[removed obsolete setting]` | `production` |
| `NEXT_PUBLIC_ARGUS_API_URL` | `http://localhost:8136/api/v1` |
| `NEXT_PUBLIC_ARGUS_LOCAL_QA_CAPTCHA_TOKEN` | `present` |
| `NEXT_PUBLIC_ARGUS_SUPPORT_EMAIL` | `support@get-argus.com` |
| `NEXT_PUBLIC_ARGUS_TURNSTILE_SITE_KEY` | `absent` |
| `NEXT_PUBLIC_ENABLE_SPANISH` | `true` |
| `NEXT_PUBLIC_EVIDENCE_RECEIPT_SHARING_ENABLED` | `true` |
| `NEXT_PUBLIC_MOCK_AUTH` | `false` |
| `NEXT_PUBLIC_OMNISEARCH_ENABLED` | `true` |
| `NEXT_PUBLIC_POSTHOG_KEY` | `absent` |
| `NEXT_PUBLIC_RESEARCH_RAIL_ENABLED` | `true` |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | `present` |
| `NEXT_PUBLIC_SUPABASE_URL` | `http://127.0.0.1:56531` |
| `PATH` | `/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin` |

## Current Targeted A/B and Step 7 Gate: Sharing Off

All ten paired rounds of `messy_spanish_future_performance_nvda_cruce_dorado` completed at deployed `ee9c3491fa6219502f1e94abc5d9e661a06839d9` and candidate `4fd587bf24ce39b794c2228d61f94693826d0da2`. Each round ran deployed first, then candidate, with exactly one live attempt at a time. Both sides used the unchanged Environment B. Every native attempt names the case and carries clean-worktree provenance. No native result or judge output was rewritten.

| Side | Native passes | Native failures | Research timeouts |
| --- | --- | --- | --- |
| Deployed | 10/10 (100%) | 0/10 (0%) | 0 |
| Candidate | 5/10 (50%) | 5/10 (50%) | 3 |

These are each build's native full-case expectations: deployed expects the future-performance limitation, while candidate expects sourced scenarios. Inputs are identical; expectations and prose rubrics remain those committed on each build. Neither the differing expectations nor safe refusals erase a native failure.

| Pair | Deployed native result | Deployed prose judge | Candidate native result | Candidate prose judge | Candidate research HTTP error status |
| --- | --- | --- | --- | --- | --- |
| 1 | PASS | PASS | FAIL: research timeout; no HTTP response | FAIL | No response |
| 2 | PASS | PASS | FAIL: cited scenario inputs absent; answer withheld | PASS | None captured |
| 3 | PASS | PASS | FAIL: research timeout; no HTTP response | PASS | No response |
| 4 | PASS | FAIL: empty criteria and notes | PASS: research published | PASS | None captured |
| 5 | PASS | PASS | FAIL: research timeout; no HTTP response | PASS | No response |
| 6 | PASS | PASS | PASS: research published | PASS | None captured |
| 7 | PASS | PASS | FAIL: future-performance limitation instead of research | FAIL | None captured |
| 8 | PASS | PASS | PASS: research published | PASS | None captured |
| 9 | PASS | PASS | PASS: research published | PASS | None captured |
| 10 | PASS | PASS | PASS: research published | PASS | None captured |

Deployed attempt 4 has a negative, unexplained judge result: `pass=false`, `failed_criteria=[]`, and empty notes. The deployed harness extends `failed_checks` only from the criteria list; the empty list adds no failure, so `_result_status` returns `passed` and the driver retains `measurement.failed=false`. The candidate harness already adds `prose_judge:failed_without_criteria` for that condition. This source difference explains the native counting inconsistency; it does not establish why the judge returned false or make that judge result pass. The native records and deployed 0/10 versus candidate 5/10 native failure rates remain unchanged.

For the founder's full-path comparison, raw negative judge results are deployed 1/10 and candidate 2/10. Counting an attempt when either its native measurement failed or its recorded judge returned false gives deployed 1/10 and candidate 5/10. These are supplemental counts derived from the existing records, not reruns or replacements for native results; the builds still have different committed expectations and rubrics. The confirmed P2 review finding was an omission in the manifest, corrected here without changing product code, the validator, or any scorecard. Source and all 20 judge results: `docs/reports/evidence/2026-09-12-main-promotion/sharing-off/eval/targeted-ab-judge-disclosure.json`.

The disclosure correction passed the unchanged release-document/evidence checks: 24 tests in 7.67 seconds, recorded in `docs/reports/evidence/2026-09-12-main-promotion/sharing-off/eval/release-docs-judge-disclosure.log`. Offline verification again confirmed all 20 native hashes, unchanged product files, cumulative cost and the absence of secrets. No paid measurement was repeated.

- Attempts 1, 3 and 5 timed out without an HTTP response. They count as failures; no HTTP status is invented.
- Attempt 2 retrieved five sources but no cited scenario-input row. The intended `scenario_inputs_uncited` guard withheld the calculation and explained why; its prose judge passed. This is a source-grounding refusal, not an HTTP error or a fabricated numerical answer.
- Attempt 7 took the production-style future-performance limitation path. It remains failed, including its failed candidate scenario-framing judge. No research sidecar was produced, so it is not counted as a provider delivery error.
- Attempts 4, 6, 8, 9 and 10 published research and passed their native checks. No HTTP error response was observed during this new A/B. The separate full BTC run and Spanish browser walk retain their actual HTTP 500 evidence.
- After candidate attempts 1 through 3 failed to publish research, the controller waited 900.11 seconds before pair 4, from `2026-09-13T20:52:28.579468Z` to `2026-09-13T21:07:28.690135Z`. No paid attempt ran during that wait. The next candidate attempt published successfully and reset the streak.
- The first pair projected a cumulative guarded total of $10.093789333684, below $12.50, before attempt three. Its timed-out research made that an optimistic projection. The hard cumulative guard remained active; final tracked cost is $9.556433710664 with $1.64 reserve, or $11.196433710664 guarded. The reserve is not spend. This new A/B added $1.59195210498 tracked and $0.12 reserve after the fresh full run.
- The founder removed the earlier failure-gap stop. No attempt was discarded, no result was relabeled as passing, and no extra live job or paid judge replay was added. Research retry on provider errors remains the first follow-up, with the founder deciding whether to merge with that caveat pending.

The source of the new native records is `docs/reports/evidence/2026-09-12-main-promotion/sharing-off/eval/targeted-ab/`. It contains all 20 native attempts, all 20 HTTP-observer documents, logs, the controller, the case driver, the final status, the first-pair projection and the exact event ledger. Verification: `docs/reports/evidence/2026-09-12-main-promotion/sharing-off/eval/sharing-off-completion-verification.json`. It checks native hashes and provenance, sequential order, identical inputs, the full cooldown, the unchanged environment source, cumulative cost, secret absence and all non-doc product paths.

### Additional nonblocking finding

[#611](https://github.com/lagarcess/argus/issues/611) records the full BTC case's follow-up label naming the Grayscale Bitcoin Mini Trust ETF although the authored question names Bitcoin. It is a P2 rendered-identity observation. No follow-up was clicked and no wrong-instrument execution or production frequency is claimed. `_resolved_subjects` passes the bare symbol to the resolver without using the available asset-class hint; its AST is identical on the deployed and candidate builds. The capture does not retain the query hint, so that value on this turn is not asserted. Evidence: `docs/reports/evidence/2026-09-12-main-promotion/sharing-off/eval/bitcoin-followup-identity.json`. No product fix was made and this issue is separate from #599's research-delivery failure.

### Product identity and terminal gate

The final unchanged-validator release-document and evidence checks passed: 24 tests in 7.57 seconds after all new A/B documents and final manifest references were present. Evidence: `docs/reports/evidence/2026-09-12-main-promotion/sharing-off/eval/release-docs-final.log`. The offline native-provenance, cost, product-identity and secret checks also passed after the final evidence files were added.

All non-doc Git paths remain byte-identical to the measured sharing-off product head. Main is still the original ancestor `17a07497abbb2ff9159b9694832a6668421e0e88`, so this is also the would-be merged product tree. The verification record binds the pre-evidence-commit head; the terminal PR audit must confirm the actual evidence commit, CI results, Codex's matching Reviewed commit and zero unresolved threads after review returns. No prior review or green check is substituted for that final-head proof. Codex does not merge. Step 8 remains unstarted and requires separate founder approval.

Authoritative new-head A/B documents, after all historical references above:

- Deployed A/B document: `docs/reports/evidence/2026-09-12-main-promotion/sharing-off/eval/targeted-ab-baseline.json`.
- Candidate A/B document: `docs/reports/evidence/2026-09-12-main-promotion/sharing-off/eval/targeted-ab-candidate.json`.

## Step 8: Deployment and Initial Acceptance Stop, 2026-09-13

The founder merged [PR #603](https://github.com/lagarcess/argus/pull/603) at 22:23:31Z as `3d98057c1e722317f0243fb96fb647771ddae484`. Its parents are main `17a07497abbb2ff9159b9694832a6668421e0e88` and reviewed promotion head `f1fa4f15e6e0f4604169d5d13a8811e43e8adbf6`; its tree matches that reviewed promotion. The [terminal audit](https://github.com/lagarcess/argus/pull/603#issuecomment-5656534529) records the final pre-merge checks. Codex performed no merge or integration reconciliation.

Paths below are relative to `docs/reports/evidence/2026-09-12-main-promotion/postdeploy/`. `verification-status.json` is the structured stop record. This section supersedes the earlier pending-deploy fields while retaining the pre-merge measurements unchanged.

### Approved environment preparation and smoke

The founder approved removal of only the setup-created link `/private/tmp/argus-promotion-20260913-landed/web/.env.local`. Before and after unlinking, the canonical file had size 1095 bytes and modification time `1785873439166244436` nanoseconds; device and inode also matched. Nothing wrote to the canonical file or through the link. The detached landed checkout retained only the approved root `.env` source. Evidence: `approved-env-link-cleanup.json`; the preceding setup stop remains in `environment-stop.json`.

The unchanged landed smoke first exited 28 on its known 20-second cold readiness timeout. Under the earlier approved recovery, one direct request used the same smoke configuration and took 1.201 seconds. It returned HTTP 503 with runtime and asset checks ready; `gateway_unavailable` was the expected Supabase state in this memory-mode smoke. The single unchanged smoke rerun passed in 5.14 seconds at the merge commit. No repository timeout or environment file changed. Evidence: `landed-local-smoke.log`, its API log and status JSON, `landed-direct-readiness.json`, and `landed-local-smoke-rerun.log` with its API log and status JSON.

### Hosted settings and migrations

The only environment writes were four per-key Render PUTs: `CUADRAO_READOUT_MODEL` and `CUADRAO_READOUT_FALLBACK_MODEL`, each `openai/gpt-5.6-luna`, on `argus-api` and `argus-backtests`. All three `autoDeployTrigger` values were `off` before, immediately before, after those writes, and after deployment. All unrelated environment values matched the pre-write readback. No Blueprint sync or `workflow-runtime` command ran. Sharing stayed off. Evidence: `hosted-settings-before.json`, `hosted-settings-immediately-before-write.json`, `hosted-settings-writes.json`, `hosted-settings-after.json`, and `hosted-settings-post-deploy.json`. The historical preapproval stop is retained in `workflow-settings-method-decision.json`; the final founder approval, its scope and completed execution are recorded separately in `workflow-settings-final-decision.json`.

Immediately before application, the read-only production gate verified `origin/main` at the merge commit and reported only the seven approved missing migrations. The founder approved all seven, including the theme drop, without backup. Each migration ran in one transaction with its ledger row. Execution and the ledger statement array used the gate's own `_split_supabase_statements`; the exact name and statement array were read back before each commit. The gate itself remained read-only.

| Repository order | Migration | Committed, UTC |
| --- | --- | --- |
| 1 | `20260908120000_decision_notes_attach_to_computations` | 22:51:41.322 |
| 2 | `20260908205041_add_refusal_observations` | 22:51:42.207 |
| 3 | `20260909183646_share_answer_receipt_selections` | 22:51:43.067 |
| 4 | `20260909225701_retire_research_rail_ledger_status` | 22:51:43.678 |
| 5 | `20260910003000_lift_receipt_selection_cap` | 22:51:43.966 |
| 6 | `20260911120000_add_profile_home_country` | 22:51:44.703 |
| 7 | `20260911214608_drop_profiles_theme` | 22:51:44.994 |

At 22:51:47.379992Z the gate passed: 77 applied ledger rows, 75 candidate files, zero missing migrations, zero current name/content drift, and the same approved historical ledger variance. Catalog readback confirmed `profiles.theme` absent. Connections used TLS verification with the production CA and GSS disabled. Evidence: `production-migration-gate-immediately-before-apply.json`, `production-migration-gate-after.json`, `migration-objects-before.json`, `migration-objects-after.json`, and the per-transaction hashes and ledger readbacks in `deployment-controller-status.json`. No customer rows were copied into these artifacts.

### Three-service deployment proof

All releases explicitly targeted the merge commit and ran serially. API and app used `render deploys create --commit <merge> --wait --confirm`; the workflow used `workflow-release <merge>`. No autodeploy setting changed.

| Service | Native terminal state | Commit proof | Live or ready proof, UTC |
| --- | --- | --- | --- |
| `argus-api` | `live` | `3d98057c1e722317f0243fb96fb647771ddae484` | Deploy finished 22:53:32.883509 |
| `argus-app` | `live` | `3d98057c1e722317f0243fb96fb647771ddae484` | Deploy finished 22:55:27.413133 |
| `argus-backtests` | `ready` | Version-owned commit prefix `3d98057` | Final readback 22:57:30.613566 |

Workflow version `wfv-dajijpbm8hqs738ed7i0` matches the merge under Render's version-owned prefix contract. `three-service-versions-final.json` records the joint readback, with individual command results in the three deploy logs. The controller finished verification at 22:57:31Z. The accepted theme-drop window began at 22:51:45Z; the old API remained live until 22:53:33Z. No signup attempt during that interval is claimed.

### Post-deploy checks and stop

| Check | Result and reason | Evidence |
| --- | --- | --- |
| Health, forced readiness, frontend | PASS | `postdeploy-warmup.log` |
| Stale queued/running jobs | PASS: zero scanned, stale, unresolved, reconciled or errors | `postdeploy-warmup.log` |
| Release configuration and workflow environment | Values match; native audit exits 1 solely for the three approved `autoDeployTrigger expected=checksPass actual=off` lines | `postdeploy-warmup.log`, `postdeploy-warmup-disposition.json` |
| Release-coherence canary | FAIL, accepted manual-mode exception: `warmup / warmup_probe_failed`; only the same three trigger mismatches | `canary-release/release-coherence.json`, `canary-release/audit-excerpt.txt` |
| Authenticated Spanish canary | FAIL, unexpected: `browser / rendered_golden_path_failed`, exact error `Rendered profile hydration failed` | `canary-browser/authenticated-browser.json`, `canary-browser/failure-excerpt.txt`, `canary-browser/page-at-failure.md` |
| Canary session cleanup | PASS: `canary_session_revocation=completed` | `canary-browser/failure-excerpt.txt` |
| New signup and profile save | NOT RUN after the unexpected canary stop | `verification-status.json` |
| English and Spanish Usage labels | NOT RUN in production after the stop; local acceptance remains unchanged | `verification-status.json` |
| One feedback rating and one support email | NOT RUN after the stop; no feedback email was requested | `verification-status.json` |
| Production sharing | NOT APPLICABLE: sharing is off; no production link created | `hosted-settings-post-deploy.json`, `postdeploy-warmup.log` |

Both canary surfaces ran once in [GitHub Actions run 34788336368](https://github.com/lagarcess/argus/actions/runs/34788336368), with harness, checkout and candidate all at the merge commit. The overall workflow is failed. The release-coherence stop prevented its standalone workflow proof, signup-denial and welcome-delivery phases from running; no success is claimed for skipped phases.

The browser failed at the first authenticated `GET /api/v1/me` response, before any chat turn, backtest, decision or canonical result receipt check. The unchanged harness only records that the response was non-success; it did not retain a numeric HTTP status. Its page snapshot shows Spanish guest settings and the sign-in control. This does not establish the cause or whether it is a candidate regression. The known #605 exception, `canonical result_summary route receipt is missing`, was not reached and does not cover this failure. The remaining journey test did not run. Redacted native captures are retained under `canary-browser-capture/` and `canary-release-capture/`.

This unexpected canary failure blocks completion of production acceptance under the founder's stop rule. No retry, product fix, further production browser action or rollback ran. The founder decision needed is whether to authorize read-only diagnosis of the profile-hydration failure before resuming acceptance. Rollback remains founder-owned; the old baseline `ee9c3491fa6219502f1e94abc5d9e661a06839d9` requires separately approved restoration of the theme column before deploying that old build.

No live eval was rerun and this canary reached zero chat turns. Retained budgets are unchanged: eval $9.556433710664 tracked plus $1.64 reserve, $11.196433710664 against $12.50; browser $1.34063303874 tracked plus $0.24 reserve, $1.58063303874 against $3; historical replay $1.70731696526 tracked plus $0.18 reserve, $1.88731696526 against $4. Reserve is not spend. Infrastructure deployment charges are outside these provider-turn ledgers.

The follow-up changes only `docs/`. It retains the native failed results, sanitized evidence and operator-script hashes; it changes no product, migration, release configuration or validator.

Documentation verification passed all 283 checks in 14.74 seconds: both release-document test files and the complete mocked harness command from `tests/evals/README.md`. The secret-value and UUID privacy scans passed; every non-doc Git path still matches the deployed merge commit. Evidence: `docs-and-mocked-tests.log` and `docs-verification.json`. These free checks do not change the failed production acceptance result.


## Current Step 8: Resumed Production Acceptance, 2026-09-14 UTC

The founder reported that production works normally while signed in, that 97 of the last 100 Private Alpha Canary runs failed, and that every run since 2026-08-18 failed. Those historical counts are founder-provided, not independently recomputed here. The founder classified the canary failure as pre-existing and authorized the remaining acceptance checks. This section supersedes the initial acceptance stop above; it does not relabel either native canary result as passing.

The requested narrow request-log readback found **`GET /api/v1/me` returned HTTP 401 at `2026-09-13T23:00:31.510440089Z`**, in the bounded window around the failed canary. Diagnosis stopped after that fact. [Issue #614](https://github.com/lagarcess/argus/issues/614) records the persistent canary failures, authenticated profile hydration stop and release-coherence drift against the founder's manual deploy mode. No cause beyond the observed response is asserted, and no fix or canary rerun was performed. Evidence: `docs/reports/evidence/2026-09-12-main-promotion/postdeploy/canary-me-request-status.json`. The known #605 receipt-check exception was not reached by that canary.

Paths in the following table are relative to `docs/reports/evidence/2026-09-12-main-promotion/postdeploy/acceptance-resumption/`. `verification.json` is the structured resumption record; `artifact-index.json` binds the captures by hash. All browser actions used a newly created controlled test account on production, separate from the canary and the founder's session.

| Check | What it should show | Visible text | Result and one-line reason | Evidence |
| --- | --- | --- | --- | --- |
| New signup, confirmation and login | An ordinary new account can confirm and sign in | Revisa tu correo; signed-in New chat, Search, Settings | PASS: Turnstile completed automatically, confirmation succeeded and ordinary password login worked | `browser/01-signup-confirmation.jpg`, `browser/02-new-account-signed-in.jpg`, `before.json` |
| Profile save and home country | The first profile changes survive reload | Production Check; Country United States; Currency USD | PASS: saved name survived reload; readback confirms the name and country US | `browser/12-country-persisted.jpg`, `after-feedback.json` |
| Spanish Usage | The four approved Spanish labels appear | Uso; Conversación; Búsquedas con fuentes; Simulaciones | PASS: all four matched the loaded production panel | `browser/06-es-usage.jpg` |
| English Usage | The four approved English labels appear | Usage; Conversation; Searches with sources; Simulations | PASS: all four matched the loaded production panel | `browser/07-en-usage.jpg` |
| Result for the feedback check | A confirmed DCA simulation completes and exposes the feedback ask | Simulation Complete; Quick take; How is Argus doing? | PASS with recovered submission warning: one workflow job and one result completed | `browser/09-backtest-confirmation.jpg`, `browser/10-simulation-complete.jpg`, `after-result.json` |
| One feedback rating | One response saves and acknowledges the user | Thanks for telling us. | PASS: one Good click persisted one positive `feedback_ask` row | `browser/13-feedback-saved.jpg`, `rating-action.json`, `after-feedback.json` |
| One support email | That rating sends exactly one support email | Provider delivery readback | PASS: one matching message to `support@get-argus.com` was delivered at `2026-09-14T00:11:31.061Z` | `feedback-email-proof.json` |
| Reload after feedback | The result remains and the answered ask stays dismissed | Simulation Complete; no Good rating button | PASS: the result hydrated and the exact rating-button count was zero | `browser/14-result-after-reload.jpg`, `feedback-reload.json` |
| Production sharing | Sharing remains disabled | Not applicable | NOT APPLICABLE: no production link was created | Prior `hosted-settings-post-deploy.json` |

The synthetic signup address bounced. Confirmation used the sent confirmation message for that same controlled account, followed by the ordinary login flow. This proves signup, confirmation and login, not delivery to the synthetic inbox. It did not require an admin-minted identity, a canary identity change, a CAPTCHA bypass or a hosted setting change. The separate feedback support email was delivered; its sanitized proof verifies the source, positive rating and match to the test conversation without retaining the body or raw identifiers. No manual founder rating is needed. The controlled test session was signed out after the checks.

The first conversation submission reported `Failed to start conversation before sending: Error: An unexpected error occurred. Please try again.` The draft remained visible, and a subsequent submission completed. Two conversation rows were recorded, followed by one confirmed DCA job and one completed backtest. This is retained as a recovered submission warning, not a silently discarded success-path error or a diagnosed cause. No product fix, extra backtest or redeploy was needed. Evidence: `submission-error.json`, `browser/08-conversation-start-blocked.jpg`, `after-submission.json` and `after-result.json`.

A fresh joint Render readback at `2026-09-14T00:15:49.708995+00:00` still showed API and app live at the full merge SHA and the workflow ready with version-owned commit prefix `3d98057`. Evidence: `three-service-versions.json`. No migrations, hosted settings, autodeploy values or deployments changed during this resumption. This follow-up changes only `docs/`; no merge or integration reconciliation was performed.

The resumed checks added $0.01801360 tracked cost. One ledger row was unpriced, so an additional $0.20 conservative reserve covers that row and readout accounting gaps instead of assuming zero cost. Browser totals are $1.35864663874 tracked plus $0.44 reserve, **$1.79864663874 against $3**. Eval remains $9.556433710664 tracked plus $1.64 reserve, **$11.196433710664 against $12.50**. Replay remains $1.70731696526 tracked plus $0.18 reserve, **$1.88731696526 against $4**. Reserves are not spend. No paid eval or replay was rerun.

Resumption documentation verification passed all 283 checks in 15.12 seconds: the release-document tests and complete documented mocked harness. Evidence: `acceptance-resumption/docs-and-mocked-tests.txt` and `acceptance-resumption/docs-verification.json`. Privacy scans and artifact hashes passed, and all non-doc Git paths still match the deployed merge. These free checks do not relabel the native canary failures.

The existing PR #613 P2 review finding at `discussion_r4001218073` was confirmed: the designated method-decision artifact still described the preapproval stop. That historical artifact remains intact. The manifest now links `postdeploy/workflow-settings-final-decision.json` for the founder approval, four approved writes and before/after evidence. It gives the known execution timestamps and states that the exact user-message approval timestamp was not retained. No new production mutation or product fix was made. The unchanged release-document and evidence tests passed all 24 checks in 7.56 seconds after this correction; evidence: `postdeploy/method-decision-release-docs-tests.txt`.
