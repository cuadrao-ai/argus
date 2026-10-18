# Transfer email successor, October 18, 2026

This is a tested WIP delivery in PR #1222. It does not establish hosted email,
inbox delivery, full account deletion or customer readiness. The receipt gate,
independent final Eval and Rafael permission retest remain required.

## Source and boundaries

The successor starts at `d365b4f61182c851936e6ac3f0da9289b4ae500b`.
The recorded and refreshed integration base is
`651870a54be4e5506dbb38f3902fef1a97eef8df`. Integration did not advance, so
no integration merge was needed. No branch was rebased.

The coordinator's consolidated successor brief supplies Iris's approved copy
and the seven-day expiry lock. The source copy was read in place and was not
committed. The exact request line is `La solicitud vence el {fecha_vence}.`
Dates and times use Spanish and `America/Santo_Domingo`.

These committed dependencies were imported after their owners completed them.

| Source | Imported commit | Result |
| --- | --- | --- |
| `7a0d7d58d` | `345ae0412` | Shared account layout and generated close bridge |
| `f57455dc7` | `279f5f58e` | Approved shared footer |
| `d8299d635` | `0a5d1ab30` | Approved preheaders, titles and security copy |
| `c418c5462` | `453365e6a` | Approved Cuadrao sender and reply-to |
| `8812aa070` | `6c6bba1ce` | Retained Business custody graph |
| `eba4e8506` | `ae488fc58` | Required configured postal address and stable time copy |

Only the branch ownership JSON conflicted during the first layout import. Both
owners' entries were preserved. Transfer methods are separate from the invite
writer's methods. No invite patch or uncommitted graph work was integrated.

## Implemented result

Four events have five canonical templates. Request goes to the target, decline
to the original owner, withdrawal to the target, and acceptance has distinct
messages for each person. The TS templates use the canonical shared layout.
The generator produces adjacent package data; Python performs one escaped
substitution over each original template. Names containing template tokens
remain literal. Plain text preserves names without HTML encoding.

The actual command path commits a per-event/recipient outbox row with the
transfer, then uses `send_resend_email`. The sender is
`Cuadrao <no-responder@mail.cuadrao.ai>` and reply-to is `hola@cuadrao.ai`.
The existing server credential remains the only provider setting. Its value was
not inspected. Resend documents that its SMTP password is an API key and its
`Resend-Idempotency-Key` header supports deduplication. Keys expire after 24 hours,
so a durable first-attempt reservation stops automatic retries after 23 hours.
A frozen payload preserves content across retries and provider ambiguity.

Provider documentation was checked on October 18.

- [Resend SMTP contract](https://resend.com/docs/send-with-smtp)
- [Resend idempotency retention](https://resend.com/docs/dashboard/emails/idempotency-keys)

Missing provider, app origin or postal configuration leaves mail unsent.
`MARKETING_POSTAL_ADDRESS` is required, with one company prefix and no multiline
content. Asset and app origins must be safe HTTPS origins. No real configuration
was changed and no real email was sent.

Requests expire exactly 168 hours after creation. Acceptance at or after expiry
is rejected. A new valid request closes an expired pending row and creates a
new command. Expiry creates no notification. GET projects expiry without changing
saved state. Accepted transfers have no undo action.

The email link preserves its transfer UUID through sign-in and loads the
authorized screen. Discovery calls the shared permission owner on every read,
returns the current actor's live grant, and selects the intended Business even
when another grant was selected. GET never accepts a transfer or creates access.
The original readiness denial and unmounted router remain in place.

The approved empty-member, expired-owner, reopen and per-Business account
deletion text is available in the bounded UI components. The deletion warning
renders one paragraph and two separate links for each Business. The warning and
reopen controls remain unmounted with the unfinished close orchestration.

## Verification

- 178 focused backend tests passed, without skips. They use real local Postgres
  plus fake SMTP, Storage and Auth. They include concurrent request and terminal
  races, provider response loss/retry, deadline crossing before send, expiry,
  re-request, no GET mutation, recipient mapping, live permission checks and
  retained history with transport PII removed.
- 47 focused frontend tests passed and cover the dialog, link resolver, sign-in return,
  intended Business selection, nonmember refusal, multiple-Business warnings,
  canonical template bridge, HTML/plain snapshots and light/dark AA contrast.
- The application-only TypeScript check passed. The broad test-inclusive check
  hits the repository's existing Bun declaration conflicts, including missing
  `afterEach` and non-callable `Expectation` types. It is not reported as green.
- All three shared layout, close and transfer generator checks passed. Ruff,
  whitespace and the modularity budget passed. A local wheel contains
  `argus/domain/business/business_transfer_email.generated.json`.
- The synthetic `/biz?transfer=<id>` browser run passed at 1280x900 and 390x900.
  It rendered Cuadrao, had no page errors or framework overlay, performed only
  GET on entry, and dismissed without a command. Screenshots and the result JSON
  are in the coordinator's external `cuadrao-sprint/transfer-qa` ledger. This is
  local synthetic browser proof, not hosted or inbox proof.

The disposable `business_transfer_mail_testdb` was cloned from the parked lane's
synthetic database. New migrations 080005 and 080006 were replayed in order.
The baseline `postgres` database was read only. No provider/model calls ran.

The fixture was created using `CREATE DATABASE business_transfer_mail_testdb
TEMPLATE business_close_testdb`, then psycopg executed the checked-in 080005 and
080006 SQL files in lexical order with autocommit. The main fixture already
contained migrations 080000 through 080004. The successor did not change it.
The final test command was run from the repository root.

```sh
ARGUS_DISPOSABLE_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:59432/business_transfer_mail_testdb \
OPENROUTER_API_KEY= ARGUS_PROD_OPENROUTER_API_KEY= \
ARGUS_GUEST_ACCESS_OPENROUTER_API_KEY= ARGUS_APPROVAL_EMAIL_SMTP_PASSWORD= \
/private/tmp/cuadrao-lane6c-parsers-deps/.venv/bin/python3.10 -m pytest \
-o addopts= --disable-warnings -q \
tests/test_business_transfer_mail.py tests/test_business_transfer_mail_postgres.py \
tests/test_business_transfer_postgres.py tests/test_business_transfer_routes.py \
tests/test_business_custody_graph_postgres.py tests/test_business_lifecycle_postgres.py \
tests/test_business_lifecycle_routes.py tests/test_business_access_postgres.py \
tests/test_access_approval_email.py

bun scripts/emails/sync-business-transfer.ts --check
bun scripts/emails/sync-business-closed.ts --check
bun scripts/emails/sync-layout.mjs --check
```

## Required continuation

The transfer outbox is personal transport, so graph detachment deletes it before
canonical transfer actors become anonymous. Its independent actor columns and
Auth deletion guard prevent silent PII survival. Complete account deletion must
also remove outgoing-member outbox rows when that person is not a custodian.
That wider orchestration remains pending with the coordinator.

The next assigned writer must complete these connected steps before readiness.

1. Connect custody preparation and graph detachment to the claimed account
   deletion run before the current person's Business rows can cascade away.
   Cover every closed owned Business and every active transferred Business whose
   stable record custodian is departing. Preserve verified originals before any
   old-prefix erase. The real Auth account must not remain as a shortcut.
2. Remove personal transfer outbox rows for departing members/targets who have
   no custody move. Check `retained_dependencies` before Storage or Auth erasure.
   Keep the run claim live through all guarded graph operations.
3. After verified Auth absence, call `complete_identity_cleanup` for each move
   before settling the global deletion run. Preserve the original close deadline,
   anonymous historical attribution and durable deletion receipts.
4. Complete the retry-safe day-30 deletion sweep for the entire closed Business
   graph and originals, including ownerless retention. Prove failed-copy retry,
   failed-purge retry, history/hash preservation and no cross-Business deletion.
5. Wire the account warning to actual owned-Business discovery and working close
   and request-transfer controls. Wire closed-Business listing/reopen and the
   approved close-member email path. Keep every control behind the unchanged
   readiness denial until the complete result is verified.
6. Run the three receipt cases, independent final Eval and Rafael's permission
   retest on the final reconciled head. Only the coordinator may then consider
   integration or staging actions under the separate grants.

Approved transfer mail/expiry and conditional link wiring are implemented here.
Whole-graph account deletion, mounted close/reopen/deletion controls, day-30
purge completion and the final permission/Eval gates remain PENDING. This PR
must remain WIP until those owners close their work. No merge, deployment,
hosted migration, global deletion activation or real email was performed.

The Model the Domain principle kept the event variants and terminal states
explicit. Make Operations Idempotent led to the durable reservation and provider
retry deadline. Assigned helper model was GPT-6.1-sol with high reasoning.
