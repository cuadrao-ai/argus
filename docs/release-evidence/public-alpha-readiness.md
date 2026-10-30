# Public Alpha Readiness Evidence

This file is the durable evidence index for the public-alpha candidate. Local
checks recorded here do not claim a hosted launch. Exact-SHA Render canary and
founder approval remain required before tester exposure.

## Live Render capacity and cost

The locked load envelope passed against the real Render API, Render Workflow,
and production Supabase project on candidate
`17098b8173d845aa5033036244a71cdcc3283ddb`. The measured task window ran from
2026-07-31 13:19:39 UTC through 13:33:04 UTC. All temporary identities were
deleted afterward: 15/15 Auth users and 15/15 allowlist rows, with zero cleanup
failures and zero matching identities on the final readback.

| Case | Observed peak | Terminal result | Wall p50 / p95 | Queue p50 / p95 | Run p50 / p95 |
| --- | --- | --- | --- | --- | --- |
| Idle job | 1 running / 0 queued | 1 succeeded | 39.756s / 39.756s | 5.096s / 5.096s | 32.673s / 32.673s |
| Five users | 5 running / 0 queued | 5 succeeded | 50.004s / 63.904s | 5.147s / 5.708s | 38.881s / 50.875s |
| Three jobs, one user | 1 running / 2 queued | 3 succeeded | 68.657s / 101.652s | 36.436s / 66.800s | 32.588s / 37.540s |
| Fifteen users | 5 running / 10 queued | 15 succeeded | 68.914s / 103.037s | 29.006s / 67.518s | 28.249s / 53.177s |
| Invalid envelope | 1 running / 0 queued | 1 failed, `invalid_job_contract`, one retry | 10.018s / 10.018s | 4.292s / 4.292s | 4.803s / 4.803s |
| Transient upstream | 1 running / 0 queued | 1 succeeded after `failed_upstream`, one retry | 43.221s / 43.221s | 4.283s / 4.283s | 38.217s / 38.217s |

The run used 26 task runs and 28 attempts. Render reported 1,466 seconds
(0.407222 hours) of Standard Workflow compute. At Render's current
[$0.20/hour Standard rate](https://render.com/docs/workflows-limits), the
measured compute cost was $0.081444, before Render's Workflow monthly minimum.

### Web-service resource headroom

The fifteen-user case ran from 2026-07-31 13:30:14 UTC through 13:32:12 UTC.
Render's 30-second service metrics for `argus-api` reported the following
peaks inside that exact window:

| Resource | Peak | Live Free-instance limit | Utilization | Remaining headroom |
| --- | --- | --- | --- | --- |
| CPU | 0.15 CPU | 0.15 CPU | 100% | 0 CPU |
| Memory | 450,351,100 bytes (450.35 MB / 429.49 MiB) | 536,870,900 bytes (536.87 MB / 512 MiB) | 83.88% | 86,519,800 bytes (86.52 MB / 82.51 MiB) |

The CPU series reached the reported limit for the final two 30-second buckets.
The observed CPU limit was 0.15 even though Render's public instance table
currently labels Free as 0.1 CPU; both values are retained here instead of
silently normalizing the live control-plane evidence. Memory remained near its
loaded high-water mark after the test: the last post-load sample at 13:47 UTC
was 432,001,020 bytes (411.99 MiB), or 80.47% of the same limit.

These are `argus-api` web-service metrics. The five concurrently running
backtests executed on separate Standard Workflow task instances (2 GB RAM and
1 CPU each), so their compute ceiling must not be mistaken for API-process
headroom. `argus-app` returned no CPU or memory samples for this window because
the capacity harness exercised the API and Workflow path, not the web UI.

The evidence therefore supports Standard for `argus-api`: Starter would reduce
the observed CPU peak to 30% of its 0.5-CPU allowance, but it would preserve the
same 512-MiB RAM ceiling and leave only 82.51 MiB of measured peak headroom.
Starter remains the proportional choice for `argus-app` because the paid-tier
requirement there is no spin-down, and no load evidence supports buying four
times the RAM. This would produce a $32/month fixed service floor ($25 API + $7
app), plus metered Workflow compute and any overage. The founder selected this
tier split in Render on 2026-07-31. Render applies instance-type changes on the
next successful deploy, so the dashboard selection was not treated as proof.
The post-deploy control-plane and metrics readbacks are recorded below.

## Hosted exact-SHA release proof

The final public-alpha runtime candidate
`2330ec42d52d912b6cdb1be5e74aa343a5d5abe0` reached all three hosted surfaces:

| Surface | Render identifier | Terminal evidence |
| --- | --- | --- |
| `argus-api` | `dep-d9miovnqj5pc73d3utrg` | `live`, exact commit, finished 2026-07-31 23:16:52 UTC |
| `argus-app` | `dep-d9miovnavr4c73eg6agg` | `live`, exact commit, finished 2026-07-31 23:16:43 UTC |
| `argus-backtests` Workflow | `wfv-d9miovjm8hqs73cebpeg` | `ready`, version name `2330ec4`, exact commit |

Before deployment, the release-config audit found the live API missing the
declared non-secret `ARGUS_APP_ORIGIN`. It was synced to
`https://argus-app-suz5.onrender.com`; the repeated audit returned `ready` with
fingerprint
`73aaf1690d4aa2d030878a6a251160a84e9a03d7a5e6c774fcbdd5b9b3392387`.

After the successful deploys, Render's service readback showed `argus-api` on
`standard` and `argus-app` on `starter`. The service-metrics limits confirmed
that these were active runtime shapes, not pending dashboard selections:

- API CPU limit: `1 CPU`.
- API memory limit: `2,147,483,600 bytes` (approximately 2 GiB).
- app CPU limit: `0.5 CPU`.
- app memory limit: `536,870,900 bytes` (approximately 512 MiB).

The resulting fixed service floor is $32/month: $25/month for the Standard API
plus $7/month for the Starter app, before Workflow compute or overage.

### Paid maintenance and private-health controls

Render accepted maintenance mode on the paid API and the control plane read
back `maintenanceMode.enabled=true`. The only configured public API domain,
`https://argus-ohr5.onrender.com`, returned HTTP `503` with the default
`Under Maintenance` page and body SHA-256
`af51f998b76af7e25f45b40bc730c0acd965285ecb9a427655fdecb7193f365d`.
The service had no configured custom domains.

While the public surface was closed, the paid app service reached
`http://argus-ohr5:10000/health` through Render's private network. The
final exact-SHA probe job `job-d9miqe3m8hqs73cee9h0` succeeded with log marker
`private_health_final_sha status=200`.

Maintenance was disabled only after the migration and hosted probes below.
The control plane then read back `maintenanceMode.enabled=false`; public
`/health` returned HTTP `200` with body SHA-256
`311fc3f1eed2fa039ba185510cc96adcbfabd1d89d3c6ac13a57a16dd1ae0b41`.

### Requested-role migration and hosted endpoint

The exact file
`supabase/migrations/20260731080154_add_requested_private_alpha_access.sql`
(SHA-256
`917772c9a654727c8f69720bd3b591b02156ed2bcc979c4b758866928810897e`)
was applied to production project `lgdhvepyrzbnscqssgqq` in one explicit
transaction under a transaction-scoped advisory lock. Two earlier CLI wrapper
attempts failed before execution, so neither changed schema or ledger state.

Independent readback confirmed the exact migration ledger hash; the required
`language` default and EN/es-419 check; the `requested` role constraint; RLS
enabled; no anonymous or authenticated DML; and service-role DML retained.
The endpoint was then exercised privately on the exact deployed API by job
`job-d9mic0navr4c73efapb0`, which logged
`access_request_probe status=202 accepted=true`. Its temporary row was deleted
and the separate cleanup readback returned zero.

### Approval email delivery

The exact deployed protected approval route was exercised by API job
`job-d9midlfavr4c73efe2pg`, which logged
`approval_email_probe status=200`. The single-purpose stdlib SMTP helper sent
to Resend's test inbox without creating an Auth user. Resend recorded:

- email ID `14c92439-e50f-4e3f-846c-228196808349`;
- recipient `delivered@resend.dev`;
- sender `"Argus" <noreply@get-argus.com>`;
- subject `Your Argus access is approved`;
- status `delivered` at 2026-07-31 22:51:27 UTC;
- existing signup-form link
  `https://argus-app-suz5.onrender.com/?auth=signup`;
- provider message ID
  `<0100019fba60171c-666a1d47-1241-49e5-aced-54eec5daec1e-000000@email.amazonses.com>`.

The captured, secret-free Resend readback is attached as
[public-alpha-approval-email-delivery.json](artifacts/public-alpha-approval-email-delivery.json).

Database readback showed the approval changed the allowlist role to `user`,
retained the requested language, and created zero Auth users. The test row was
then deleted. Final cleanup returned zero temporary allowlist rows and zero
temporary Auth users.

### Hosted localized UI evidence

The exact hosted app completed real request submissions in English and
es-419. Both response states were visually inspected after their transitions
settled, with zero browser console errors and zero warnings:

- [English request form](screenshots/public-alpha-readiness/hosted-en-desktop-request-access.png)
- [English request received](screenshots/public-alpha-readiness/hosted-en-desktop-request-accepted.png)
- [Spanish request form](screenshots/public-alpha-readiness/hosted-es-419-desktop-request-access.png)
- [Spanish request received](screenshots/public-alpha-readiness/hosted-es-419-desktop-request-accepted.png)

All screenshot-probe addresses were removed afterward. Independent cleanup
readback found zero temporary allowlist rows and zero temporary Auth users.

The sessionless confirmed-signup state was also exercised deterministically in
the exact frontend component flow at desktop and mobile sizes. It stayed on the
auth surface and rendered the localized confirmation instruction instead of
falling through to `/chat`:

- [English check-email desktop](screenshots/public-alpha-readiness/en-desktop-check-email.png)
- [English check-email mobile](screenshots/public-alpha-readiness/en-mobile-check-email.png)
- [Spanish check-email desktop](screenshots/public-alpha-readiness/es-419-desktop-check-email.png)
- [Spanish check-email mobile](screenshots/public-alpha-readiness/es-419-mobile-check-email.png)

## Production migration lineage repair

The production Supabase project was confirmed as
`lgdhvepyrzbnscqssgqq` (the main Argus project, not a preview branch). Its
schema already matched the current application surface, but its migration
ledger stopped before 29 checked-in legacy files. Before touching production,
the exact gap was reproduced on a disposable stack mirroring that starting
state; all 124 database tests passed there.

The founder explicitly waived a backup prerequisite for this repair because
the project held no real users or customer data. All 29 files were then applied
in lexical order under one session advisory lock. Each file ran in its own
transaction with its matching ledger insert, and the runner stopped on the
first error; no file failed. The final ledger read-back matched the repository
through `20260728120000_visitor_keyed_guest_settlement`. Function signatures,
RLS enablement and policies, RPC grants, and relevant table grants were read
back after the batch. One hosted temporary-user probe passed and its Auth user
and allowlist row were deleted, with a zero-match cleanup read-back.

The later requested-role migration was deliberately excluded from this legacy
repair and applied only after the separate paid-control proof documented above.

### Post-batch Omnisearch migrations

After the integration branch advanced, three additional checked-in Omnisearch
migrations were found absent from both the production ledger and live schema.
The founder authorized them separately from the legacy 29-file repair. On
2026-07-31 they were applied in timestamp order under one session advisory
lock, with one top-level transaction and matching exact ledger insert per file:

| Version | Migration | Checked-in SQL SHA-256 |
| --- | --- | --- |
| `20260729221458` | `add_message_recall_index` | `4f051fc867a1ff3bf43bb1381d3299c70b1220ab8b30e25e8e789b0a146dd933` |
| `20260730042500` | `add_decision_recall_index` | `cbd22dd513bc21e2eb21607facccf264e56736ac7331135fc57d5da976cd5669` |
| `20260730070000` | `add_asset_symbol_prefix_indexes` | `dfd2c16ca9b776dbb022c12a0cd805d4a63a4dfae80d7d8b32e6a81a010b2540` |

All three files committed with zero database failures. Independent read-back
confirmed the three ledger rows, the two GIN recall indexes, all five btree
symbol-prefix indexes, and `argus_search_symbol_casefold(text)`. Every index
was valid and ready; the casefold function was immutable, strict,
parallel-safe, and not security-definer. RLS remained enabled on `messages`,
`decision_notes`, `backtest_runs`, and `private_alpha_allowlist`; the
user-data policies retained their `auth.uid()` ownership predicates.

One hosted temporary-user lifecycle probe then passed with a real Supabase
magic-link session: `GET /me` returned 200, conversation creation returned
200, message insertion returned 201, and the owner-scoped conversation-message
read returned exactly the seeded message with HTTP 200. Cleanup deleted the
Auth user and allowlist entry, and independent read-back found zero matching
Auth, profile, allowlist, conversation, or message rows. The final exact-SHA
deploy recorded above includes the merged Omnisearch reader.

The checked-in Blueprint declares `argus-api` as `plan: standard` and
`argus-app` as `plan: starter`, matching the founder's selected tier split.
Supabase stays on its free tier for this lane: there are no real users or
customer data to protect yet, and the 2026-07-31 spec correction explicitly
defers a Pro decision until that changes.

## Approval SMTP secret

`CUADRAO_APPROVAL_EMAIL_SMTP_PASSWORD` is present on the live `argus-api` Render
service. The value was copied from the locally resolved Resend credential only
after verifying that interpolation produced an actual `re_...` credential, not
the literal `${RESEND_API_KEY}` reference. A redacted Render control-plane
read-back matched the local credential exactly. Setting the secret did not
itself trigger a deploy. The later exact-candidate deploy loaded it
successfully, and the backend-originated delivery proof is recorded above.

## Waitlist paid-control precondition (completed)

The checked-in Render Blueprint declares `argus-api` as `plan: standard` and
`argus-app` as `plan: starter`. A checked-in plan or dashboard selection is not
proof of the live instance type, so the following gate was enforced before the
requested-role migration or waitlist exposure. Render documents that
[maintenance mode is available only on paid web
services](https://render.com/docs/maintenance-mode), [Free web services cannot
receive private-network traffic](https://render.com/docs/private-network), and
[Free web services do not support shell or SSH
access](https://render.com/docs/ssh). Render's [Free instance
limitations](https://render.com/docs/free) confirm the same operational gaps.

The gating rule was: Do not apply
`supabase/migrations/20260731080154_add_requested_private_alpha_access.sql` or
accept access-request traffic until the paid-control readbacks below are
complete. Rollback below `061ba50e` remains forbidden until verified
maintenance, worker quiescence, and private route-absence proof are available.

Before applying that migration or exposing the route, the release captain had
to complete these steps in order:

1. Use an out-of-band service readback to read back a paid API instance type
   from Render's control plane for `argus-api`. Record the returned plan and
   require `serviceDetails.plan != free`.
2. With access-request traffic still unexposed, prove maintenance mode is
   available and can be enabled. Enable it, read back
   `serviceDetails.maintenanceMode.enabled=true`, and require the exact HTTP
   `503` plus configured maintenance-page marker or fingerprint on every public
   API domain.
3. Verify actual private-network, SSH, or local-loopback verification
   capability. Either require HTTP `200` from `/health` through the paid
   service's internal hostname, or open an authenticated Render shell/SSH
   session and require HTTP `200` from the service's local `/health` endpoint.
   Record the successful surface; a documented entitlement without a working
   probe is not proof.

The selected API tier satisfies the planned paid-instance transition only if
these capability checks also pass. If any paid capability is absent, stop: do
not apply the migration and do not expose the route. Only after every paid-control
check passes may the requested-role migration be applied and access-request
traffic be exposed. Those checks passed, and the resulting live evidence is
recorded in "Hosted exact-SHA release proof" above.

## Waitlist rollback floor

Commit `061ba50e` is the fail-closed behavior and minimum safe rollback floor
while the deployed schema can contain `requested` access rows. Prefer a forward fix.

Before any authorized rollback of application code below `061ba50e`, use this
exact sequence:

Render documents that [maintenance mode returns HTTP 503 and the configured
maintenance page on every public request](https://render.com/docs/maintenance-mode),
while the service remains reachable over its private network and SSH. Render
also documents that a [restart keeps the same commit and configuration, and a
zero-downtime deploy completes only after the old instance is shut
down](https://render.com/docs/deploys#zero-downtime-deploys). The control-plane
checks below use Render's documented [restart
endpoint](https://api-docs.render.com/reference/restart-service), [instance
inventory](https://api-docs.render.com/reference/list-instances), and [service
and deploy fields](https://api-docs.render.com/openapi/render-public-api-1.json).

If no private verification surface is available through the private network,
SSH, or local loopback, rollback below `061ba50e` is forbidden. Stop and
forward-fix before changing maintenance state or data.

1. Enable Render maintenance mode. Use an out-of-band Render control-plane
   readback—not the application—to record
   `serviceDetails.maintenanceMode.enabled=true`, the configured maintenance
   page URI, and every configured custom API domain.
2. Derive and record the expected configured maintenance page marker or
   SHA-256 fingerprint. Probe `/api/v1/auth/access-requests` on every
   configured custom API domain (for example
   `https://api.arguschat.ai/api/v1/auth/access-requests`). Every maintenance
   probe response must have the exact HTTP `503` maintenance-mode status and
   the configured marker or fingerprint. An arbitrary `403`, `429`, or `503`
   is not maintenance proof. After `argus-api`'s
   `renderSubdomainPolicy: disabled` is applied,
   `https://argus-ohr5.onrender.com` must return HTTP `404` and is not a
   maintenance probe surface; do not require `503` from that hostname. If the
   control-plane state or expected response signature cannot be verified,
   stop and forward-fix.
3. Keep maintenance enabled. Capture the current live commit and all current
   instance IDs, then trigger a same-SHA Render service restart. Wait until the
   restart deploy is terminal with `status=live`, has a non-empty `finishedAt`,
   and its `commit.id` still equals the captured SHA. Re-read the instance
   inventory and require the set of pre-restart instance IDs to be absent.
   Together with the completed restart deploy, this is the required Render
   evidence that old-instance shutdown/drain is complete and no pre-maintenance
   API worker remains, so pre-block in-flight inserts cannot complete after
   cleanup. If any part cannot be verified, stop and forward-fix; do not clean
   rows.
4. Only after verified worker replacement, keep maintenance enabled and run
   the cleanup transaction below. The table lock does not drain a worker paused
   before its insert. Quiescence comes from maintenance plus the completed
   same-SHA restart. The lock only serializes the cleanup with later database
   work.

```sql
begin;

lock table public.private_alpha_allowlist in access exclusive mode;

update public.private_alpha_allowlist
set
  disabled_at = coalesce(disabled_at, now()),
  updated_at = now()
where role = 'requested'
  and disabled_at is null;

select count(*) as active_requested_rows
from public.private_alpha_allowlist
where role = 'requested'
  and disabled_at is null;

do $$
begin
  if exists (
    select 1
    from public.private_alpha_allowlist
    where role = 'requested'
      and disabled_at is null
  ) then
    raise exception 'active requested access rows remain';
  end if;
end
$$;

commit;
```

5. Capture the `active_requested_rows` readback and assertion. Both must be
   zero before commit. If either fails, stop; do not weaken the gate or
   continue the rollback.
6. After commit, keep maintenance enabled and deploy the rollback of
   application code below `061ba50e`. Read Render deploy metadata and require
   that the exact rollback SHA is live in Render deploy metadata with
   `status=live` and a non-empty `finishedAt`.
7. With maintenance still enabled, use the service's private network, SSH, or
   local loopback surface to send a non-mutating invalid-body probe
   (`POST {}` with `Content-Type: application/json`) to
   `/api/v1/auth/access-requests` and require HTTP `404` route absence. A
   present route, including HTTP `422` or any other application response,
   stops the rollback: keep maintenance enabled, clean up the failed rollback
   state, and forward-fix.
8. Before changing public traffic, re-read the maintenance configuration and
   response signature exactly as in steps 1 and 2. Require
   `serviceDetails.maintenanceMode.enabled=true`, exact HTTP `503`, and the
   same configured page marker or fingerprint on every configured custom API
   domain. Keep requiring HTTP `404` from `https://argus-ohr5.onrender.com`;
   that hostname remains excluded from the maintenance fingerprint surface.
9. Disable maintenance last. Then perform a public invalid-body readback on
   every configured custom API domain and require HTTP `404` route absence.
   `https://argus-ohr5.onrender.com` must still return HTTP `404` and is not
   an application route-absence probe surface. If any custom-domain surface
   returns another status, immediately re-enable maintenance, stop, clean up
   the failed rollback state, and forward-fix.

Do not execute this SQL as part of repository verification. It is a
production-state change reserved for an explicitly authorized rollback.
