# Main Production Promotion Manifest — 2026-08-11

## Candidate

- Candidate SHA: `d67cef92102ea147546c86d92773d810939b768d`
- Candidate branch: `main` (normal merge of PR `#441` from `codex/private-alpha-next`)
- Validation status: founder-authorized production promotion complete, with the
  remediated schema gap and the two accepted non-blocking findings recorded
  below
- Validation surface: production `argus-api`, `argus-app`, `argus-backtests`,
  production Supabase, and an allowlisted browser session
- Promotion target: `main`
- Release captain: Codex
- Approver: Founder
- Rollback target: `7ef89a90fd28acdb9bab01b8f888f2bac5026e0a`,
  the previous recorded production checkpoint; any rollback requires founder
  authorization, exact three-service version selection, and a schema
  compatibility review
- Decision record: the founder authorized completion after accepting the
  Turnstile browser-canary failure and the fast-classification citation defect
  as non-blockers. Automatic deploy remains unchanged and outside this lane.

## Deploy Proof

- API service: `argus-api`
- API deploy status: `live`
- API deployed SHA: `d67cef92102ea147546c86d92773d810939b768d`
- Web service: `argus-app`
- Web deploy status: `live`
- Web deployed SHA: `d67cef92102ea147546c86d92773d810939b768d`
- Workflow service: `argus-backtests`, workflow version
  `wfv-d9tm83ajobas73dbk97g`, status `ready`, release commit
  `d67cef92102ea147546c86d92773d810939b768d`
- Cron service: `argus-maintenance`
- Cron deploy status: `absent`, as required because the blueprint has never
  been applied
- Cron deployed SHA: `<absent>`
- Checked at: `2026-08-11T18:08:03Z` by the deployed-release canary resolver
- A Render CLI `read: connection reset by peer` occurred only while polling the
  web deploy. Subsequent status reads and the canary resolver confirmed the
  deploy itself was `live` at the candidate SHA; no redeploy or rollback was
  performed.

## Database and Migration Proof

- Production project: `lgdhvepyrzbnscqssgqq`
- Gap found after deploy: production stopped at `20260803110000`; nine
  repository migrations were missing even though the service deploys, config
  audit, and warmup were green.
- Founder-authorized remediation applied these data-preserving migrations one
  at a time in repository order, stopping on no failures:
  - `20260727230000_add_visitor_usage_counters`
  - `20260805120000_enforce_memory_candidate_sensitivity_flags_require_restricted`
  - `20260807000001_add_research_operation_scope`
  - `20260807120000_add_memory_semantic_recall_index`
  - `20260807170000_allow_unproven_memory_projection`
  - `20260807190000_add_public_excerpt_snapshots`
  - `20260808120000_add_guest_funnel_milestones`
  - `20260809140000_add_preferred_name`
  - `20260810150000_serialize_message_artifact_update`
- Trigger-bearing migration inspection: the public-excerpt migration attaches
  only revocation triggers to existing tables. `conversations` fires after a
  `deleted_at` update and before delete; `backtest_runs` and
  `evidence_artifacts` fire before delete. None fires on ordinary message,
  conversation, research, or backtest activity.
- Readback proof: the applied list ends at repository tip `20260810150000`.
- Contract proof: production now accepts `chat.research` in the backtest-jobs
  operation-scope constraint.
- User impact before remediation: the research rail was fail-closed and inert
  for roughly two hours, and a preferred-name save failure was consistent with
  the missing schema. The rail engaged immediately after remediation.
- Follow-up: issue `#449` records why schema compatibility and migration apply
  must become a pre-deploy promotion gate.

## Environment Proof

- Expected mode: `real-workflow`
- Release profile hash:
  `e5d68bcd5dc317f7a91d9596dae60c6e29264f02b600d99c940f72ec8c257a28`
- Effective locales and capabilities: `en`, `es-419`, Omnisearch on, research
  rail on, and real workflow execution on
- api_web_env_fingerprint:
  `9875334cdf3317ac8031d36fb6ffd5dea0f2021bf6811521e674dbd51e62faa0`
- workflow_env_fingerprint:
  `f27047f438bbf0cf8fef87f6af86667c2b6d4aabe0f95211778cf1ff7bb57d1e`
- workflow_env_status: `ready`
- cron_env_fingerprint: `<absent>`
- cron_env_status: `absent`
- workflow_runtime_provider_mode: `live_provider`
- workflow_runtime_proof: `ready`
- workflow_task: `argus-backtests/workflow_proof`
- real_workflow_task: `argus-backtests/run_backtest_job`
- Backtest service mode: real workflow, live provider
- Render config audit command:
  `.github/render-env-sync.sh release-config-audit --expect-mode real-workflow`
- Config-audit result: `status=ready`, zero drift
- Web build-time proof: `NEXT_PUBLIC_RESEARCH_RAIL_ENABLED=true` was present for
  the deployed web build, the served product rendered research progress, and
  the bundle was not relying on a later runtime-only change.
- Required dashboard-owned secrets were present with redacted proof. No secret
  value was read, printed, copied, or moved, and neither `.env` nor
  `web/.env.local` was written.

### Full feature and release-control table

| Surface | Key | Effective value | Intent |
| --- | --- | --- | --- |
| API | `ARGUS_DEV_MEMORY_FALLBACK` | `false` | Fail closed instead of silently using process memory in production. |
| API | `ARGUS_ENABLE_EXECUTION_REALISM` | `true` | Include supported modeled execution costs in simulation truth. |
| API | `ARGUS_ENABLE_PERSONALIZATION_MEMORY` | `false` | Keep personalization memory off for this release. |
| API | `ARGUS_RESEARCH_RAIL_ENABLED` | `true` | Enable the production research path. |
| API | `ARGUS_RESEARCH_GLOBAL_DAILY_CEILING` | `5000` | Bound total daily research-provider spend. |
| API | `ARGUS_ENABLE_MEMORY_SEMANTIC_RECALL` | `false` | Keep semantic memory recall off. |
| API | `CUADRAO_EVIDENCE_RECEIPT_SHARING_ENABLED` | `false` | Keep public evidence receipts unavailable. |
| API | `ARGUS_IN_PLACE_CARD_EDITS_ENABLED` | `false` | Keep capital/date drawer editing disabled. |
| API | `ARGUS_MEMORY_EMBEDDING_MODEL` | `pplx-embed-v1-0.6b` | Pin the dormant semantic-memory embedding contract. |
| API | `ARGUS_MEMORY_EMBEDDING_DIMENSIONS` | `1024` | Match the dormant vector schema to the pinned model. |
| API | `ARGUS_MEMORY_EMBEDDING_TIMEOUT_SECONDS` | `8.0` | Bound dormant embedding-provider calls if later enabled. |
| API | `ARGUS_MEMORY_VECTOR_COLLECTION` | `argus_memory_vectors` | Name the dormant memory vector collection. |
| API | `ARGUS_DISCOVERY_SEARCH_PROVIDER` | `perplexity_direct` | Use the production discovery/research provider boundary. |
| API | `CUADRAO_MOCK_AUTH` | `false` | Require real production authentication. |
| API | `ARGUS_BACKTEST_JOBS_SHADOW_ENABLED` | `true` | Preserve job-path observation during real-workflow operation. |
| API | `ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED` | `true` | Allow the API to dispatch hosted backtest work. |
| API | `ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED` | `true` | Execute the real hosted workflow instead of proof-shadow only. |
| API | `ARGUS_CONTEXT_PACKETS_ENABLED` | `true` | Enable typed context-packet retrieval. |
| API | `ARGUS_TITLE_AUTOGEN_ENABLED` | `true` | Enable bounded conversation-title generation. |
| API | `ALPACA_PAPER_TRADING` | `true` | Keep provider access in paper mode; no real-money execution. |
| Web | `NEXT_PUBLIC_MOCK_AUTH` | `false` | Render the real production auth flow. |
| Web | `NEXT_PUBLIC_ENABLE_SPANISH` | `true` | Expose the supported Spanish UI. |
| Web | `NEXT_PUBLIC_OMNISEARCH_ENABLED` | `true` | Expose Omnisearch. |
| Web | `NEXT_PUBLIC_RESEARCH_RAIL_ENABLED` | `true` | Render research progress and evidence surfaces. |
| Web | `NEXT_PUBLIC_EVIDENCE_RECEIPT_SHARING_ENABLED` | `false` | Hide public evidence-receipt controls. |
| Workflow | `ENABLE_MARKET_DATA_CACHE` | `false` | Avoid stale workflow-local market-data cache state. |
| Workflow | `ALPACA_PAPER_TRADING` | `true` | Keep workflow provider access in paper mode. |
| Removed | `[removed obsolete setting]` | `<absent>` | Remove the obsolete legacy strategy-surface gate. |
| Removed | `[removed obsolete setting]` | `<absent>` | Remove the obsolete web strategy-surface gate. |
| Removed | `[removed obsolete setting]` | `<absent>` | Remove the obsolete current Collections surface gate. |
| Removed | `[removed obsolete setting]` | `<absent>` | Remove the obsolete exploratory-suggestions gate. |

## Gate Evidence

- Reconciled canary test matrix: `127 passed` at PR `#441` head
  `fa6435c76f66c7dae7686ae6557565225310e7e0`, covering both main's deployed-SHA,
  Turnstile, redaction, and fail-red behavior and integration's cron release
  surface.
- Confirmation smoke: the card exposed `Run backtest`,
  `Change/edit assumptions`, and `Cancel`. The stale `Change dates` and
  `Change asset` actions were absent. Capital and dates drawers did not render
  while `ARGUS_IN_PLACE_CARD_EDITS_ENABLED=false`.
- Local smoke: passed inside the deployed-release canary job.
- Warmup command: `.github/warmup-render.sh --expect-mode real-workflow`
- Warmup result: passed health/readiness, zero stale queued/running jobs,
  release-config audit, and live-provider workflow proof.
- Deployed-release canary: scheduled 2026-08-11 execution; human-safe evidence,
  failure capture, and redacted browser-context artifacts uploaded. The durable
  GitHub Actions link is recorded in issue `#452`.
- Canary stages that passed: exact deployed-release checkout; Spanish static
  assertions; local smoke; config and SHA coherence; live-provider workflow
  proof; API-layer requested-signup denial (`400 auth_signup_failed`);
  redaction gate; sanitized artifact upload.
- Canary terminal result: **failed**, not green. It stopped at `browser_auth`
  on `captcha_challenge_timeout` while a headless browser waited for the
  Turnstile-protected signup request. Turnstile correctly rejected automation;
  this is not a product defect. No retry, bypass, timeout increase, redeploy, or
  rollback was performed. The Spanish golden path and browser-owned real
  backtest were not reached. Follow-up: issue `#452`.
- English-input finance check: production label `ec11f641e3c6`; the allowlisted
  session received a substantive workspace-language answer, research progress
  rendered, and no capability refusal occurred.
- Spanish-input finance check: production label `0f4b847f3212`; the allowlisted
  session received a substantive Spanish answer, research progress rendered,
  and no capability refusal occurred.
- Citation result for both finance checks: no source-link rail. This is the
  accepted non-blocking defect in issue `#451`: the narrative question was
  classified `fast`, whose only tool is `finance_search`, and provider-host
  filtering removes its `perplexity.ai` finance URLs. The provider call and
  answer succeeded; the structural citation path did not.
- Language result: correct. Input language is independent from response
  language; prose followed the workspace language setting.

## Release Decision

- Promotion complete at `d67cef92102ea147546c86d92773d810939b768d`.
- Public tester exposure remains founder-controlled; this manifest sends no
  invitations and changes no allowlist.
- The nine-migration production gap was a real release incident and was fully
  remediated during the promotion. It remains open as process work in `#449`.
- Known caveats: the canary remains red at the structurally inverted Turnstile
  browser-auth leg (`#452`), and fast-classified research answers can omit all
  citations (`#451`). Both were founder-accepted as non-blockers for this
  no-user release.
- Rollback trigger: a production journey, workflow, security, data-integrity,
  or schema-compatibility regression other than the accepted findings above.
- Rollback owner: Founder/operator. A rollback would require selecting and
  redeploying compatible prior versions across API, web, and workflow; the
  additive migrations are not reversed automatically.
- `autoDeploy` was not enabled or changed.

## Privacy Notes

- No raw conversation, user, product run, job, hosted-workflow-run, or Auth
  identifiers are recorded.
- Production conversation labels are SHA-256 prefixes used only for audit
  correlation.
- No secrets, tokens, cookies, headers, raw prompts, transcripts, route
  receipts, screenshots of credentials, or service-role credentials are
  included.
- Canary artifacts passed the redaction gate before upload; failed captures are
  sanitized evidence, not raw user data.
