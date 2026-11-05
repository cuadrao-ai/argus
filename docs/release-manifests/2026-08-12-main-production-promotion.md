# Main Production Promotion Manifest - 2026-08-12

## Candidate

- Candidate SHA: `c3a9aca181ea43770a81c13ec2fb5f02f85af293`
- Candidate branch: `codex/private-alpha-next`, validated from a detached HEAD
  pinned to the exact candidate SHA
- Candidate description: `docs(backtesting): publish math audit and invariants`
- Promotion size: 69 commits after production
  `d67cef92102ea147546c86d92773d810939b768d`
- Validation status: founder-authorized production promotion complete. The
  migration, config payload, three-service deploy, runtime proof, bilingual
  production checks, and in-place drawer lifecycle all passed. The automated
  canary stopped at the accepted Turnstile control in issue `#452`.
- Validation surface: production `argus-api`, `argus-app`, `argus-backtests`,
  production Supabase, and the Guest browser path at `https://arguschat.ai`
- Promotion target: `main`
- Main promotion SHA: `b8e26691db0afb101aafca56cd73b019eef4f2b4`
- Promotion PR: `#473`
- Merge lineage: normal merge with parents
  `d67cef92102ea147546c86d92773d810939b768d` and exact candidate
  `c3a9aca181ea43770a81c13ec2fb5f02f85af293`. The merge tree
  `209e3a7a306da7a9aabeee2dd0cddf0520eaefc2` equals the exact candidate
  tree.
- Release captain: Codex
- Approver: Founder
- Rollback target: `d67cef92102ea147546c86d92773d810939b768d`,
  the production release immediately before this promotion
- Decision record: the founder approved setting
  `ARGUS_IN_PLACE_CARD_EDITS_ENABLED=true` and deploying main SHA
  `b8e26691db0afb101aafca56cd73b019eef4f2b4` in order to `argus-api`,
  `argus-app`, and `argus-backtests`. Blueprint sync and autodeploy remained
  prohibited.

## Deploy Proof

All deploy evidence below promotes exact candidate
`c3a9aca181ea43770a81c13ec2fb5f02f85af293` through main merge
`b8e26691db0afb101aafca56cd73b019eef4f2b4`.

- API service: `argus-api`
- Initial ordered API deploy id: `dep-d9ua1mjncjis73arhfs0`
- Latest API deploy id: `dep-d9uaakajnfac73ci05q0`
- API deploy status: `live`
- API deployed SHA: `b8e26691db0afb101aafca56cd73b019eef4f2b4`
- Initial ordered API deploy finished at: `2026-08-12T16:37:09.462831Z`
- Latest API deploy finished at: `2026-08-12T16:55:35.093981Z`
- Web service: `argus-app`
- Web deploy id: `dep-d9ua2grm8hqs73eu2oh0`
- Web deploy status: `live`
- Web deployed SHA: `b8e26691db0afb101aafca56cd73b019eef4f2b4`
- Web finished at: `2026-08-12T16:39:21.654130Z`
- Workflow service: `argus-backtests`
- Workflow version id: `wfv-d9ua3kugekts73a68gag`
- Workflow status: `ready`
- Workflow release commit:
  `b8e26691db0afb101aafca56cd73b019eef4f2b4`
- Workflow created at: `2026-08-12T16:39:47.941135Z`
- Deployment order: API reached `live`, then web reached `live`, then the
  workflow version reached `ready`.
- After the ordered deploy and browser proof, Render completed one
  `service_updated` API rollout at the same exact SHA. It did not change the
  deployed commit, feature-flag readback, or manual autodeploy posture. No
  one-off redeploy loop or rollback was started.
- Cron service: `argus-maintenance`
- Cron deploy status: `absent`, as required
- Cron deployed SHA: `<absent>`
- Autodeploy readback:
  - `argus-api`: `off`
  - `argus-app`: `off`
  - `argus-backtests`: `off`
- Blueprint sync: not run
- Checked at: `2026-08-12T16:58:03Z`

## Database and Migration Proof

The schema gate was executed against exact candidate
`c3a9aca181ea43770a81c13ec2fb5f02f85af293` before the service deploy.

- Production project: `lgdhvepyrzbnscqssgqq`
- Candidate migration:
  `20260811210000_delete_withheld_backtest_result.sql`
- Classification: additive schema change. It adds an explicitly invoked
  deletion function; the migration itself does not sweep or delete rows.
- Candidate migration SHA-256:
  `1c99c9d94cbaf9c450aa138cdab4c48af546c30179436752509cc65ff5f62eec`
- Ledger before apply: `20260810150000`
- Apply method: one transaction with an advisory lock, in repository order,
  followed by a ledger insert and readback
- Ledger after apply: `20260811210000`, name
  `delete_withheld_backtest_result`
- Ledger statement readback matched the pinned candidate file and hash.
- Function readback:
  - name: `delete_withheld_backtest_result`
  - arguments: `(uuid, uuid)`
  - return type: `boolean`
  - security: `SECURITY DEFINER`
  - search path: `public`
  - execute grant: `service_role=true`
  - public, anonymous, and authenticated execute grants: `false`
- No migration runner, retention job, stale-job cleanup, or data repair script
  was invoked during the production incident capture.
- Process follow-up: issue `#449` owns the missing automatic migration gate.

## Pre-deploy Production Incident Capture

This evidence was captured read-only while production still ran
`d67cef92102ea147546c86d92773d810939b768d`, before deploying exact candidate
`c3a9aca181ea43770a81c13ec2fb5f02f85af293`. The full internal evidence and
raw identifiers are in issue `#474`; this manifest keeps only privacy-safe
labels.

- Conversation label: `conversation_a9edc48458ef`
- Job label: `job_c5f3f1a10b38`
- Job state:
  - status: `failed`
  - failure code: `approved_data_window_unavailable`
  - failure detail: `approved_data_window_unavailable`
  - retryable: `false`
  - result run: absent
  - created and queued: `2026-08-12T15:56:05.111612+00:00`
  - started: `2026-08-12T15:56:15.085901+00:00`
  - finished: `2026-08-12T15:56:21.708821+00:00`
- No `backtest_runs` tuple existed for the conversation and the linked-result
  count was zero.
- Render reported the workflow task itself as completed without a platform
  error. The Argus result inside that task was the non-retryable failure above.
- Relevant `argus-backtests` sequence:
  - `15:56:20.975Z`: KO lookup started
  - `15:56:21.134Z`: KO lookup completed
  - `15:56:21.135Z`: SPY lookup started
  - `15:56:21.180Z`: SPY lookup completed
  - `15:56:21.708Z`: KO exact lookup cache hit immediately before failure
- Fleet snapshot at capture:
  - two same-code failures in the preceding 24 hours
  - 18 failed jobs total
  - zero jobs past the 15-minute stranded threshold
  - zero active queued/running backlog
- Disposition: repeated narrow data-window pattern, not a broad workflow
  outage and not a stranded-job pattern
- Untested hypothesis handed off for confirmation or refutation: a request
  ending on the current date may reach the approved window before the current
  day's bar exists, leaving the right edge empty. A card observed earlier on
  `2026-08-12` requested `2025-08-12` through `2026-08-12` on system date
  `2026-08-12`.
- Handoff: full detail posted to the backtest health task and new issue `#474`.
- No retry, fix, cleanup, or production-row mutation was performed.

## Environment Proof

All environment evidence below is tied to exact candidate
`c3a9aca181ea43770a81c13ec2fb5f02f85af293` and deployed main SHA
`b8e26691db0afb101aafca56cd73b019eef4f2b4`.

- Expected mode: `real-workflow`
- Release profile hash:
  `03b9697a0647fdcc88823ef77d0b0fc0fdf9104374664c08f62b2b202669e313`
- Effective locales and capabilities: `en`, `es-419`, Omnisearch on, research
  rail on, in-place confirmation-card editing on, and real workflow execution
  on
- Pre-deploy config audit: exactly three expected drift lines:
  - `argus-api:ARGUS_APP_ORIGIN`, repo stale and live custom domain correct
  - `argus-app:ARGUS_APP_ORIGIN`, repo stale and live custom domain correct
  - `argus-api:ARGUS_IN_PLACE_CARD_EDITS_ENABLED`, candidate payload not yet
    applied
- Post-deploy api/web env fingerprint:
  `b558223e4625c0d313396dfdbe69bd9c5f62e84fb4145cc4d4b0bdb52973269b`
- Workflow env fingerprint:
  `f27047f438bbf0cf8fef87f6af86667c2b6d4aabe0f95211778cf1ff7bb57d1e`
- Workflow env status: `ready`
- Cron env fingerprint: `<absent>`
- Cron env status: `absent`
- Workflow runtime provider mode: `live_provider`
- Workflow runtime proof: `ready`
- Workflow task: `argus-backtests/workflow_proof`
- Real workflow task: `argus-backtests/run_backtest_job`
- Backtest service mode: real workflow with live provider
- Render config audit command:
  `.github/render-env-sync.sh release-config-audit --expect-mode real-workflow`
- Post-deploy config-audit result: exactly two accepted drift lines and no
  others:
  - `argus-api:ARGUS_APP_ORIGIN expected=https://argus-app-suz5.onrender.com actual=https://arguschat.ai`
  - `argus-app:ARGUS_APP_ORIGIN expected=https://argus-app-suz5.onrender.com actual=https://arguschat.ai`
- `ARGUS_IN_PLACE_CARD_EDITS_ENABLED=true` read back as `ok`; its pre-deploy
  drift line is gone.
- The two domain lines remain until PR `#470` lands. No blueprint sync was run
  because it would restore the stale hostname declaration.
- Required dashboard-owned secrets were present with redacted proof. No secret
  value was printed, copied, or moved. Neither `.env` nor `web/.env.local` was
  written.

### Feature and release-control table

| Surface | Key | Effective value | Intent |
| --- | --- | --- | --- |
| API | `ARGUS_IN_PLACE_CARD_EDITS_ENABLED` | `true` | Render capital, date, and cost drawers on an unconsumed confirmation card and persist edits without spending a chat turn. |
| API | `ARGUS_ENABLE_EXECUTION_REALISM` | `true` | Include supported modeled execution costs in simulation truth. |
| API | `ARGUS_RESEARCH_RAIL_ENABLED` | `true` | Keep the production research path available. |
| API | `ARGUS_RESEARCH_GLOBAL_DAILY_CEILING` | `5000` | Bound total daily research-provider spend. |
| API | `ARGUS_ENABLE_PERSONALIZATION_MEMORY` | `false` | Keep personalization memory off. |
| API | `ARGUS_ENABLE_MEMORY_SEMANTIC_RECALL` | `false` | Keep semantic memory recall off. |
| API | `CUADRAO_EVIDENCE_RECEIPT_SHARING_ENABLED` | `false` | Keep public evidence receipts unavailable. |
| API | `CUADRAO_MOCK_AUTH` | `false` | Require real production authentication. |
| API | `ARGUS_BACKTEST_JOBS_SHADOW_ENABLED` | `true` | Preserve job-path observation in real-workflow mode. |
| API | `ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED` | `true` | Allow hosted backtest dispatch. |
| API | `ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED` | `true` | Execute real hosted workflow jobs. |
| API | `ARGUS_CONTEXT_PACKETS_ENABLED` | `true` | Keep typed context-packet retrieval on. |
| API | `ARGUS_TITLE_AUTOGEN_ENABLED` | `true` | Keep bounded conversation-title generation on. |
| API | `ALPACA_PAPER_TRADING` | `true` | Keep provider access in paper mode with no real-money execution. |
| Web | `NEXT_PUBLIC_MOCK_AUTH` | `false` | Render the real production auth flow. |
| Web | `NEXT_PUBLIC_ENABLE_SPANISH` | `true` | Expose the supported Spanish UI. |
| Web | `NEXT_PUBLIC_OMNISEARCH_ENABLED` | `true` | Expose Omnisearch. |
| Web | `NEXT_PUBLIC_RESEARCH_RAIL_ENABLED` | `true` | Render research progress and evidence surfaces. |
| Web | `NEXT_PUBLIC_EVIDENCE_RECEIPT_SHARING_ENABLED` | `false` | Hide public evidence-receipt controls. |
| Workflow | `ENABLE_MARKET_DATA_CACHE` | `false` | Avoid stale workflow-local market-data cache state. |
| Workflow | `ALPACA_PAPER_TRADING` | `true` | Keep workflow provider access in paper mode. |
| Deploy | `argus-api.autoDeployTrigger` | `off` | Preserve founder-directed manual API deploys. |
| Deploy | `argus-app.autoDeployTrigger` | `off` | Preserve founder-directed manual web deploys. |
| Deploy | `argus-backtests.autoDeployTrigger` | `off` | Preserve founder-directed manual workflow releases. |

## Gate Evidence

Every gate below cites exact candidate
`c3a9aca181ea43770a81c13ec2fb5f02f85af293` and deployed main SHA
`b8e26691db0afb101aafca56cd73b019eef4f2b4`.

- Local smoke command:
  `.github/local-smoke.sh --expected-sha c3a9aca181ea43770a81c13ec2fb5f02f85af293`
- Local smoke result: `verification_status=ready` on Python `3.10.20`;
  candidate SHA matched exactly
- Promotion PR `#473`: required CI green before the normal merge
- Runtime warmup evidence:
  - API health: `healthy`
  - product readiness: `ready`
  - `agent_runtime_workflow`: `ready`
  - `supabase`: `ready`
  - `asset_universe`: `ready`
  - Render app origin HTTP status: `200`
  - `https://arguschat.ai` HTTP status: `200`
  - workflow runtime provider mode: `live_provider`
  - workflow runtime proof: `ready`
- Warmup safety note: the monolithic
  `.github/warmup-render.sh --expect-mode real-workflow` command was not run
  because it invokes the stale-job reconciliation script when local verifier
  credentials are present, while the incident capture had an explicit
  no-cleanup boundary. Its health, readiness, frontend, config-audit, and
  workflow-proof components were run separately. The config audit was recorded
  with the two founder-accepted domain drifts instead of being relabeled
  `status=ready`.
- English production finance check:
  - Guest KO buy-and-hold request reached one confirmation card.
  - Initial card showed `$10,000`, `2024-01-02` through `2025-12-31`, 10 bps
    fee, 5 bps slippage, and SPY benchmark.
  - The real workflow completed and rendered one result.
- In-place drawer acceptance:
  - `Edit capital`, `Edit dates`, and `Edit costs` rendered together.
  - Capital changed from `$10,000` to `$12,500` in place.
  - User-message count remained one and confirmation-card count remained one,
    proving no chat turn or replacement card was created.
  - Pressing `Run backtest` changed the same card to running and immediately
    removed all three edit controls.
  - The completed consumed card retained `$12,500` and all edit-control counts
    remained zero.
- Spanish production finance check:
  - Workspace language changed to `es-419`.
  - A Netflix business-model and financial-risk question returned one
    substantive Spanish answer through the live research path.
- Browser console errors across the accepted drawer and bilingual journey: `0`
- Automated canary browser-auth component:
  - exit status: `1`
  - terminal stage: `browser_auth`
  - reason: `captcha_challenge_timeout`
  - disposition: accepted non-gate, issue `#452`
  - no CAPTCHA bypass, retry loop, timeout increase, redeploy, or rollback was
    attempted
- Full canary wrapper note: it was not used because its bundled warmup would
  run the prohibited stale-job reconciliation and would stop on the two
  founder-accepted PR `#470` domain drifts before reaching Turnstile. The
  browser-auth component was run directly after separate exact-SHA deploy,
  config, readiness, and workflow proofs.

## Release Decision

- Promotion complete at main SHA
  `b8e26691db0afb101aafca56cd73b019eef4f2b4`, carrying exact candidate
  `c3a9aca181ea43770a81c13ec2fb5f02f85af293`.
- The only user-visible change is in-place editing on unconsumed confirmation
  cards. The consumed-card lock was verified in production.
- Public tester exposure remains founder-controlled; this manifest sends no
  invitations and changes no allowlist.
- Known caveats:
  - the two `ARGUS_APP_ORIGIN` audit lines remain until PR `#470` lands;
  - automated browser auth remains blocked by Turnstile as designed in `#452`;
  - the pre-deploy guest failure is under diagnosis in `#474`.
- Rollback trigger: a production workflow, drawer-consumption, security,
  data-integrity, or schema-compatibility regression other than the accepted
  findings above
- Rollback owner: Founder/operator. Redeploy
  `d67cef92102ea147546c86d92773d810939b768d` to API, web, and workflow in
  order, review the additive function's compatibility, and restore the drawer
  flag to `false` only with founder authorization.
- Autodeploy remained `off` on all three services.
- No blueprint sync was run.

## Privacy Notes

- No raw conversation, user, product run, job, hosted-workflow-run, or Auth
  identifiers are recorded in this manifest.
- Production incident labels are SHA-256 prefixes used only for audit
  correlation. Full internal identifiers remain in issue `#474`.
- No secrets, tokens, cookies, headers, raw prompts, transcripts, route
  receipts, screenshots of credentials, or service-role credentials are
  included.
- The browser journey stores no transcript or credential artifact in this
  manifest.
- Neither `.env` nor `web/.env.local` was written.
