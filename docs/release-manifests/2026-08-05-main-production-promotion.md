# Main Production Promotion Manifest — 2026-08-05

## Candidate

- Candidate SHA: `7ef89a90fd28acdb9bab01b8f888f2bac5026e0a`
- Candidate branch: `main` (identical to `codex/private-alpha-next`)
- Validation status: founder-authorized promotion complete, with the browser-automation deviation recorded below
- Validation surface: production `argus-api`, `argus-app`, and `argus-backtests`
- Promotion target: `main`
- Release captain: Codex
- Approver: Founder
- Rollback target: the prior founder-approved production release; redeploy only after exact-SHA verification
- Decision record: founder authorized this manifest to record server-side journey evidence and the browser deviation in lieu of a green headless authoritative canary.

## Deploy Proof

- API service: `argus-api`
- API deploy status: `live`
- API deployed SHA: `7ef89a90fd28acdb9bab01b8f888f2bac5026e0a`
- Web service: `argus-app`
- Web deploy status: `live`
- Web deployed SHA: `7ef89a90fd28acdb9bab01b8f888f2bac5026e0a`
- Workflow service: `argus-backtests`, workflow version `wfv-d9p88253erlc73d3u8s0`, status `ready`, release commit `7ef89a90fd28acdb9bab01b8f888f2bac5026e0a`

## Database and Migration Proof

- Production project: `lgdhvepyrzbnscqssgqq`
- Applied once, in order: `20260731093703`, `20260801000000`, `20260802090000`, `20260803110000`
- The ten renumbered pre-July migration stamps were not re-applied.

## Environment Proof

- Expected mode: `real-workflow`
- Release profile hash: `ba770302fbad5432dcafbee20c0b2b6ef2da779c850e81da7bb3746aeb6b6631`
- api_web_env_fingerprint: `4585b426c9e1cf1562432a88e57c34e744de12ef30f29b690969c70297f7975a`
- workflow_env_fingerprint: `f27047f438bbf0cf8fef87f6af86667c2b6d4aabe0f95211778cf1ff7bb57d1e`
- workflow env/runtime: `ready`; effective provider mode `live_provider`; runtime proof `ready`
- workflow_task: `argus-backtests/workflow_proof`
- real_workflow_task: `argus-backtests/run_backtest_job`
- Backtest service mode: real workflow, live provider
- Env reconciliation: green. Required API variables were present without exposing values: `PERPLEXITY_API_KEY`, `POSTHOG_PROJECT_TOKEN`, `POSTHOG_REGION`, `ARGUS_ENABLE_EXECUTION_REALISM=true`, and `ARGUS_DISCOVERY_SEARCH_PROVIDER=perplexity_direct`.
- Security/configuration: `CUADRAO_VISITOR_KEY_SECRET` is non-default; support email is present; QA-only mock-auth variables are not enabled; founder confirmed the hosted OpenRouter key identity as `argus-prod`.
- CAPTCHA posture: exact production sitekey `0x4AAAAAAD-5dlnAEBKLlhui` changed from Managed to Non-interactive during promotion. Domain allowlist, clearance setting, bot-fight setting, and server-side CAPTCHA verification/enforcement were unchanged.

## Gate Evidence

- Local smoke: passed at `4b4f0fba`; subsequent candidate changes through `7ef89a90` were contract/runbook/docs only, with product code unchanged since `70ba33cc` (founder-confirmed carry-forward evidence).
- Warmup: passed with health/readiness, stale queued/running scan `0/0`, release-config audit green, and deployed workflow proof in `live_provider` mode.
- Fresh production journey verification:
  - Queried at `2026-08-05T03:33:58.397032Z`.
  - Conversation label: `c5914017fcdc`; job label: `5ee2c6c19c91`; run/result label: `83b02486600c`.
  - Requested shape: AAPL + MSFT, equal-weight, buy-and-hold, `2025-01-02` to `2026-06-05`, starting capital `$10,000`.
  - Job status: `succeeded`; run status: `completed`; execution kind/task: `run_backtest_job` / `argus-backtests/run_backtest_job`.
  - Workflow run label: `ee94bed5137a`; runtime version/stamp was verified separately as `wfv-d9p88253erlc73d3u8s0` at the candidate SHA.
  - Finalized evidence label: `7074cfddaa39`; idea label: `b399e047ca84`; idea-version label: `eba4666defcc`; result card exists.
  - Metrics: total return `+12.84%`; benchmark return `+26.14%`; benchmark lag `13.30` percentage points.
  - Cost ledger: one linked `cost_ledger_entries` row; total recorded cost `$0.00015585` USD.
- Requested-signup denial: green at the API layer. Founder-operated probe received HTTP `400` with problem code `auth_signup_failed`; denial occurred before CAPTCHA verification and created zero identities.
- Browser phase deviation: founder-operated real-Chrome journey witnessed. Headless browser automation remained blocked by Turnstile in every tested widget mode, so it is not treated as a green automated canary. Follow-up: issue `#383`.

## Release Decision

- Promotion complete at `7ef89a90fd28acdb9bab01b8f888f2bac5026e0a`, founder-authorized with the recorded browser-automation deviation.
- Public tester exposure: founder-controlled; this manifest does not itself send invitations.
- Known caveat: the scheduled first green canary at `14:30 UTC` remains the founder-owned closing gate. Report its `cost_ledger_entries` cost before setting future canary cadence.
- Rollback trigger: a production journey, real-workflow, security, or data-integrity regression.
- Rollback owner: Founder/operator.

## Privacy Notes

- No raw conversation, user, run, job, workflow-run, or Auth identifiers are recorded.
- Labels are SHA-256 prefixes used only for audit correlation.
- No secrets, tokens, cookies, headers, raw prompts, transcripts, route receipts, or service-role credentials are included.
