# Personless analytics deletion, October 5, 2026

Integration base is `875de09ac2115acec42e09060b92878aa5f18eff`.
This slice implements #806 behind the existing default-off activation flag.
It does not close the provider acceptance or activation gate.

## Provider contract

Sources checked October 5, 2026, are PostHog's official implementation:

- [API and serializers](https://github.com/PostHog/posthog/blob/master/posthog/api/data_deletion_request.py).
- [Submission deduplication](https://github.com/PostHog/posthog/blob/master/posthog/data_deletion.py).
- [Workflow statuses](https://github.com/PostHog/posthog/blob/master/posthog/models/data_deletion_request.py).

The project-scoped `data_deletion_requests` API selects event UUIDs using HogQL.
It is alpha-gated and requires approval. It is not a generally available
person deletion endpoint. The adapter never calls `persons/bulk_delete`.

The existing durable deletion run UUID is the submission UUID, available
before any network call. Retrying after a lost POST response sends the same
query, variables and submission UUID. PostHog also binds deduplication to the
submitting user, so changing personal-key owners can cause a conflict.
Once a request UUID is stored, retries poll that request.
Only a separate GET showing matching request and submission UUIDs and
`completed` closes the step. Submission acceptance, zero selected events and
`persons_found: 0` never establish completion.

The run stores only UUIDs, parsed status, selected-event count, HTTP status
and local outcome. It does not store provider bodies, queries, distinct IDs,
keys or provider exception messages in its new evidence.
A selected-event count is not a claimed independently measured deletion count.
Pending, failed and operator-needed outcomes keep the account locked and
allow the existing user retry and manual recovery path to resume.
A 403 identifies operator-needed alpha or permission acceptance.
A 409 remains pending because it can mean either an active-request limit or
submission conflict. Existing seven-day escalation remains authoritative.

## Configuration and external gates

`ARGUS_ANALYTICS_DELETION_ENABLED` remains false in the example configuration.
Explicit activation requires dedicated `ARGUS_POSTHOG_DELETION_HOST`,
`ARGUS_POSTHOG_DELETION_PROJECT_ID` and `ARGUS_POSTHOG_DELETION_API_KEY`.
The event-capture project token does not substitute for this credential.
The host must be HTTPS and the project ID numeric.

Before activation, the founder must authorize synthetic provider acceptance,
confirm the capture project and deletion project match, confirm alpha API
availability and credential scopes, establish request approval handling, and
observe an independently completed request and provider event readback.
No provider API call, customer data access, hosted deletion, hosted
configuration change or physical-phone check occurred in this slice.
The account-deletion activation gates in #805, #806 and #800 remain open.

## Local verification

The initial capability test failed during collection with
`ModuleNotFoundError: No module named 'argus.observability.posthog_deletion'`.
This proves the missing adapter, not a provider defect reproduction.

The first new PostgreSQL run passed both assertions but hit one fixture
teardown foreign-key error because an intentionally pending run remained.
The test now completes its synthetic run through the explicitly local fake
only after proving alpha denial has no auth deletion side effect.

The final command uses a stripped environment, this worktree's `src`, and
`ARGUS_DISPOSABLE_DATABASE_URL` pointing to the run-owned local PostgreSQL.
It runs `tests/test_analytics_deletion_adapter.py`,
`tests/test_analytics_deletion_postgres.py`,
`tests/test_account_deletion_third_parties_postgres.py` and
`tests/test_account_deletion_postgres.py` with `--override-ini addopts=''`.
Final test counts are recorded in `verification.txt`.
The HTTP boundary uses synthetic `httpx.MockTransport` responses matching the
provider contract. Real PostgreSQL proves durable state, relaunch polling,
retry identity, account locking and delayed auth deletion. HTTP mocks do not
prove actual PostHog deletion or tenant availability.

Model the Domain selected one immutable provider result and one adapter.
Make Operations Idempotent reused the durable run UUID instead of a new store.
Sequence Work into Verifiable Units kept this adapter separate from identity,
consent, balance semantics and operator recovery changes.
