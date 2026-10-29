# Main Production Promotion Manifest - 2026-08-12 - Candidate 716221f

## Candidate

- Candidate SHA: `716221f07ca50c3fdb1ad8de5314b07072bfe815`
- Candidate branch: `codex/private-alpha-next`, validated from a detached HEAD
  pinned to the exact candidate SHA
- Candidate description:
  `Merge pull request #477 from lagarcess/claude/475-coverage-end-clamp`
- Promotion size: 12 commits after production
  `b8e26691db0afb101aafca56cd73b019eef4f2b4`
- User-visible payload:
  - issue `#477`: backtests whose window ends today no longer fail during US
    market hours
  - issue `#472`: self-serve password reset works
- All other promoted changes are documentation, tests, and release evidence.
- Validation status: founder-authorized production promotion complete. The
  exact-SHA smoke and CI gates passed, all three live services were deployed in
  order, and the available post-deploy checks passed. Issue `#477` shipped
  without live market-hours verification for the reason recorded below.
- Validation surface: production `argus-api`, `argus-app`, `argus-backtests`,
  production Supabase Auth logs, and an authenticated browser session at
  `https://arguschat.ai`
- Promotion target: `main`
- Promotion PR: `#478`
- Promotion PR head: `7c13d9673f72d5fc02f78a9cb250e56faa449cb6`
- Main promotion SHA: `5d8ba7a5f259f0ae65a4477d2952ad6c09096c1e`
- Merge lineage:
  - PR head `7c13d9673f72d5fc02f78a9cb250e56faa449cb6` is a normal merge
    with parents `b8e26691db0afb101aafca56cd73b019eef4f2b4` and exact candidate
    `716221f07ca50c3fdb1ad8de5314b07072bfe815`.
  - Main SHA `5d8ba7a5f259f0ae65a4477d2952ad6c09096c1e` is a normal merge
    with parents `b8e26691db0afb101aafca56cd73b019eef4f2b4` and PR head
    `7c13d9673f72d5fc02f78a9cb250e56faa449cb6`.
  - Main, the PR head, and the exact candidate share tree
    `1cd65e4e16ad9e0dacd18527c1e9b1dad31ccd0b`. No squash or rebase was
    used.
- Release captain: Codex
- Approver: Founder
- Rollback target: `b8e26691db0afb101aafca56cd73b019eef4f2b4`,
  the production release immediately before this promotion
- Decision record: the founder approved the normal merge and immediate manual
  deployment of `argus-api`, then `argus-app`, then `argus-backtests`.
  Blueprint sync, autodeploy changes, and deployment of `argus-maintenance`
  remained prohibited.

## Deploy Proof

All deploy evidence below carries exact candidate
`716221f07ca50c3fdb1ad8de5314b07072bfe815` through main merge
`5d8ba7a5f259f0ae65a4477d2952ad6c09096c1e`.

- API service: `argus-api`
- API deploy id: `dep-d9udb0gn74is73dgcge0`
- API deploy status: `live`
- API deployed SHA: `5d8ba7a5f259f0ae65a4477d2952ad6c09096c1e`
- API created at: `2026-08-12T20:20:18.179814Z`
- API finished at: `2026-08-12T20:21:49.807217Z`
- Web service: `argus-app`
- Web deploy id: `dep-d9udbron74is73dgeqpg`
- Web deploy status: `live`
- Web deployed SHA: `5d8ba7a5f259f0ae65a4477d2952ad6c09096c1e`
- Web created at: `2026-08-12T20:22:07.108303Z`
- Web finished at: `2026-08-12T20:23:56.067361Z`
- Workflow service: `argus-backtests`
- Workflow id: `wfl-d8hpsmuq1p3s73duv3q0`
- Workflow version id: `wfv-d9udcqijobas73eamh00`
- Workflow status: `ready`
- Workflow release commit:
  `5d8ba7a5f259f0ae65a4477d2952ad6c09096c1e`
- Workflow created at: `2026-08-12T20:24:10.637719Z`
- Deployment order: API reached `live`, then web reached `live`, then the
  workflow version reached `ready`.
- Cron service: `argus-maintenance`
- Cron deploy status: `absent`, confirmed by a successful Render inventory
  lookup rather than treating a failed lookup as proof
- Cron deployed SHA: `<absent>`
- Autodeploy readback:
  - `argus-api`: `off`
  - `argus-app`: `off`
  - `argus-backtests`: `off`
- Blueprint sync: not run
- Checked at: `2026-08-12T20:52:02Z`

## Database and Migration Proof

- Production project: `lgdhvepyrzbnscqssgqq`
- New migrations since production: none
- Verification method:
  `git diff --name-status b8e26691db0afb101aafca56cd73b019eef4f2b4 716221f07ca50c3fdb1ad8de5314b07072bfe815 -- supabase/migrations`
- Verification result: empty diff
- Promotion action: no migration was applied because the verified promotion
  payload contains no migration.
- This was verified by diff and was not assumed from a release note or prior
  operator statement.

## Environment Proof

All environment evidence below is tied to exact candidate
`716221f07ca50c3fdb1ad8de5314b07072bfe815` and deployed main SHA
`5d8ba7a5f259f0ae65a4477d2952ad6c09096c1e`.

- Environment keys added by this promotion: none
- Environment keys removed by this promotion: none
- Environment values changed by this promotion: none
- Verification method: the production-to-candidate diff was empty across
  `.env.example`, `web/.env.local.example`, `render.yaml`,
  `.github/argus-env.sh`, `.github/private-alpha-release-profile.json`, and
  `.github/render-env-sync.sh`.
- Promotion action: no environment value or checked-in config contract was
  changed. This was verified by diff and was not assumed.
- Expected mode: `real-workflow`
- Release profile hash:
  `03b9697a0647fdcc88823ef77d0b0fc0fdf9104374664c08f62b2b202669e313`
- Post-deploy API/web env fingerprint:
  `6f8d900e1c2268d0c2e2e9f52305cc2114051ca94e15638c3c31e9005fec52fd`
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
- Post-deploy audit result: only the following three founder-accepted keys were
  non-`ok`; no other key was reported:
  - `argus-api:ARGUS_APP_ORIGIN`: the repository still declares the Render
    hostname while live production correctly uses `https://arguschat.ai`.
    This remains accepted until PR `#470` lands.
  - `argus-app:ARGUS_APP_ORIGIN`: the repository still declares the Render
    hostname while live production correctly uses `https://arguschat.ai`.
    This remains accepted until PR `#470` lands.
  - `argus-api:CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED`: the founder enabled this
    live on Render to open public account creation. Its declaration is in
    unmerged PR `#470`, so the current contract correctly reports it as
    `unexpected_live_env`.
- `ARGUS_IN_PLACE_CARD_EDITS_ENABLED=true` read back as `ok`.
- The audit remained nonzero because these accepted differences are still real
  differences. They were not relabeled as a green contract match.
- No blueprint sync was run, because it would revert the production domain and
  alter the live manual-deploy posture.
- The shared `.env` symlink was sourced only. Neither checkout's `.env` nor
  `web/.env.local` was written.

## Gate Evidence

Every gate below cites exact candidate
`716221f07ca50c3fdb1ad8de5314b07072bfe815` and deployed main SHA
`5d8ba7a5f259f0ae65a4477d2952ad6c09096c1e`.

- Local smoke command:
  `.github/local-smoke.sh --expected-sha 716221f07ca50c3fdb1ad8de5314b07072bfe815`
- Local smoke result: `verification_status=ready`; the detached checkout
  matched the exact candidate SHA.
- Promotion PR `#478`: all required CI checks passed at exact PR head
  `7c13d9673f72d5fc02f78a9cb250e56faa449cb6` before the normal merge.
- Runtime warmup evidence:
  - API health: `healthy`
  - product readiness: `ready`
  - stale-job scan: `ready`, with zero scanned, stale, reconciled, or errored
    jobs
  - Render app origin HTTP status: `200`
  - `https://arguschat.ai` HTTP status: `200`
  - workflow runtime provider mode: `live_provider`
  - workflow runtime proof: `ready`
- Warmup command disposition: the health, readiness, stale-job, and frontend
  components passed. The wrapper then stopped at the config audit because the
  three accepted differences remain visible. The workflow proof was run
  separately and passed. The wrapper was not falsely recorded as green.
- Self-serve password recovery acceptance:
  - initiated from the production site's forgot-password page, not an admin
    panel
  - Supabase Auth log action: `user_recovery_requested`
  - method and path: `POST /recover`
  - status: `200`
  - observed at: `2026-08-12T20:30:07Z`
  - disposition: issue `#472` verified in production
- Historical-window workflow smoke:
  - authenticated Spanish request for an equal-weight AAPL/MSFT buy-and-hold
    run from `2025-01-02` through `2026-06-05` with `$10,000`
  - the production workflow completed and rendered one result card
  - this is a general workflow smoke check only; it is not verification of
    issue `#477`
- In-place drawer regression check:
  - capital, date, and cost edit drawers all rendered on the unconsumed
    confirmation card
  - pressing Run immediately removed all three edit controls
  - the workflow completed with the consumed card still locked
  - browser console errors: `0`
- Issue `#477` market-hours verification:
  - not performed
  - the US market closed at `16:00 ET` before the production verification could
    run
  - after the close, the broken path and fixed path behave identically, so a
    historical-window run or an after-hours today-ending run is not equivalent
  - the fix therefore shipped unverified in production
  - the first real production verification will run tomorrow, `2026-08-13`,
    after `09:30 ET`, using a backtest whose window ends that day and requiring
    a completed result card
- Automated canary browser-auth component:
  - invoked once against production after the exact-SHA deploy and separate
    config, readiness, and workflow proofs
  - terminal stage: `browser_auth`
  - reason: `captcha_challenge_timeout`
  - Supabase Auth logs showed no login request during the canary window,
    consistent with the rendered client stopping before Auth
  - disposition: accepted non-gate, issue `#452`; Turnstile is working as the
    automated-browser control
  - no CAPTCHA bypass, retry, timeout increase, redeploy, or rollback was
    attempted
- Full canary wrapper note: it was not used because its bundled config audit
  would stop on the three founder-accepted differences before reaching the
  browser component.

## Release Decision

- Promotion complete at main SHA
  `5d8ba7a5f259f0ae65a4477d2952ad6c09096c1e`, carrying exact candidate
  `716221f07ca50c3fdb1ad8de5314b07072bfe815`.
- Issue `#472` is verified in production through the site-originated request
  and Supabase Auth `POST /recover` status `200`.
- Issue `#477` is deployed but remains unverified in production until the first
  valid market-hours check after `09:30 ET` on `2026-08-13`.
- The historical backtest passed only as workflow smoke and is not presented as
  equivalent evidence for issue `#477`.
- This promotion carried no migrations and no environment changes. Both facts
  were verified by production-to-candidate diffs rather than assumed.
- Known accepted config differences:
  - `argus-api:ARGUS_APP_ORIGIN`
  - `argus-app:ARGUS_APP_ORIGIN`
  - `argus-api:CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED`
- Automated browser auth remains bounded by Turnstile as recorded in issue
  `#452`.
- Public account access was already founder-enabled live and was not changed by
  this promotion. This manifest sends no invitation and changes no allowlist.
- Rollback trigger: a production workflow, recovery, drawer-consumption,
  security, or data-integrity regression other than the accepted findings
  above
- Rollback owner: Founder/operator. Redeploy
  `b8e26691db0afb101aafca56cd73b019eef4f2b4` to API, web, and workflow in
  that order.
- Autodeploy remained `off` on all three services.
- No blueprint sync was run.
- `argus-maintenance` remained absent.

## Privacy Notes

- No raw conversation, user, product run, job, hosted-workflow-run, or Auth
  identifiers are recorded in this manifest.
- No email address, IP address, access token, cookie, secret, header, raw
  transcript, or service-role credential is included.
- The Auth-log assertion records only the action, method, path, status, and
  timestamp needed for release proof.
- Neither `.env` nor `web/.env.local` was written.
