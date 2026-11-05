# Private Alpha Release Manifest Template

Use one manifest per validated candidate checkpoint or promoted candidate.
Start it before promotion, record the production migration gate before any
deploy-capable action, and finish it after the release gate passes and before
sending tester links. A validated private-alpha checkpoint records technical
evidence only; it does not itself authorize a `main` merge, production
deployment, automatic production deployment, tester invitation, or tester
exposure. Do not include raw conversation, user, run, or job ids; use the
privacy-safe labels from canary evidence.

## Candidate

- Candidate SHA:
- Candidate branch:
- Validation status:
- Validation surface:
- Promotion target: `main`
- Release captain:
- Approver:
- Rollback target:
- Decision record:

## Live Eval Evidence

Evidence stands for the build it names only when nothing the measurement can
reach changed between them (`tests/promotion_evidence_identity.py`). Name the
measured SHA beside each piece of evidence whenever it differs from that build.
New promotions require schema-v3 measurement scorecards with
`provenance.release_configuration`: the API service's model IDs and explicit
`true`/`false` flags as the eval environment had them. Baseline and targeted A/B
documents must carry the same field. The shared gate compares each side with
its build's committed release profile; missing or different values fail. Other
environment settings and other services are out of scope. Historical manifests
remain unchanged under the fixed compatibility list.

- Live eval scorecard:
- Live eval measured SHA:
- Baseline eval scorecard:
- Baseline measured SHA:
- Targeted A/B documents, each side's measured SHA and rate:

## Production Migration Gate

- Gate command: `scripts/ops/production_migration_gate.py`
- Gate report durable attachment or committed path:
- Gate checked at:
- Gate candidate SHA:
- Gated candidate parents and intended landing method:
- Landed `origin/main` SHA:
- Gate-to-landed-SHA identity: exact / invalidated and rerun
- Landed-ref verification: `--verify-landed-ref origin/main`, status and SHA
- Sanitized production project and database host:
- Database transport: `sslmode=verify-full`, production CA, GSS disabled
- Candidate migrations, with version, name, file SHA-256, statement count, and
  statement-array SHA-256:
- Applied production migrations, with version, name, statement count, and
  statement-array SHA-256:
- Latest applied production migration:
- Missing migrations:
- Unexpected applied migrations:
- Migration name drift:
- Migration content drift, including missing statement history:
- Safety classifications and live requirements for every missing migration:
- Classification basis and human live-schema review:
- Gate result: `status=pass` required before service deploy
- Gate human-approval state:
- Gate apply result: `not_performed_by_gate`
- Gate ledger readback:
- Human apply performed: no / yes, by:
- If applied, repository order and ledger before/after:
- If applied, affected-object readback:
- Confirm the gate never applies migrations:

## Deploy Proof

- API service: `argus-api`
- API deploy status:
- API deployed SHA:
- Web service: `argus-app`
- Web deploy status:
- Web deployed SHA:
- Workflow service: `argus-backtests`
- Workflow version status:
- Workflow released SHA:
- Workflow version id:
- Checked at:

## Environment Proof

- Expected mode:
- Release profile hash:
- Effective locales and capabilities:
- api_web_env_fingerprint:
- workflow_env_fingerprint:
- workflow_env_status:
- autodeploy_fingerprint:
- autodeploy_status:
- all three services use the release profile's trigger, `off` (manual deploys):
- workflow_runtime_provider_mode:
- workflow_runtime_proof:
- env_fingerprint script output:
- workflow_task:
- real_workflow_task:
- Backtest service mode:
- Workflow service proof:
  - `argus-backtests` latest deploy/status:
  - workflow autodeploy verified: `off`
  - workflow provider mode verified: `live_provider`
  - effective runtime provider mode verified: `live_provider`
  - effective runtime proof status:
  - required workflow secrets present with redacted proof:
  - active workflow task verified:
  - real workflow task verified:
- Feature flags:
- Guest staged mode:
  - `CUADRAO_GUEST_ACCESS_ENABLED`:
  - `CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED`:
  - `NEXT_PUBLIC_GUEST_ACCESS_ENABLED`:
  - permanent account allowlist verified:
- Anonymous Auth / abuse controls:
  - anonymous Auth enabled:
  - CAPTCHA posture:
  - provider anonymous-user rate limit:
  - Argus per-IP guest-attempt limit:
- Guest cleanup:
  - operator-run command:
  - explicit target:
  - dry-run selected:
  - real selected/deleted/preserved/failed:
  - cleanup lag:
- Render config audit command:
- Secret rotation / least-privilege owner:

## Gate Evidence

- Local smoke command:
- Local smoke result:
- Warmup command:
- Warmup result:
- Canary evidence artifacts: `private-alpha-release-coherence-evidence` and
  `private-alpha-authenticated-browser-evidence`
- Canary checks, each with its status from the evidence:
  - `services_same_commit`:
  - `signed_in_chat_answer`, with `sign_in_attempts`:
  - `backtest_completes`, with the backtest job and run labels:
  - `research_answer_with_sources`:
  - Release guards (release config, disabled signup denial, welcome email):
  - Exact candidate SHA verified:
  - Failed check or guard and reason, if red:
- Browser signup/login proof:
- Guest exact-head browser evidence:
  - local candidate SHA:
  - 20-check matrix result:
  - same-UUID new-account conversion:
  - atomic existing-account claim:
  - zero cross-owner results:
  - usage/API/database agreement:
  - chart-interaction zero-write ledger:
  - console status:
- Guest load calibration:
  - synthetic p50/p95 and sample size:
  - error rate:
  - queue/backpressure result:
  - anonymous-session creation volume:
  - cleanup lag:
  - provider-reported cost per completed result:
  - unsupported production projections:
  - Failed-capture replay, if failed:
  - Exit status:

## Release Decision

- Public tester exposure approved:
- Known caveats:
- Rollback trigger:
- Rollback command or owner:
- Guest rollback order verified:
- Follow-up owner:

## Privacy Notes

- No raw conversation, user, run, or job ids.
- Canary labels are stable hashes for audit correlation only.
- The release profile contains no credentials, account ids, deploy ids, or
  candidate SHA; record its hash with the candidate evidence instead.
- Failed-capture artifacts are sanitized replay inputs, not raw transcripts.
- Service-role credentials, cookies, prompts, and route receipt payloads are not
  copied into this manifest.
- Guest evidence contains no Auth UUID, raw conversation/artifact/job/run ids,
  email, tokens, cookies, headers, screenshots of credentials, or transcript
  dumps. Store only privacy-safe hashes and aggregate/count facts.
