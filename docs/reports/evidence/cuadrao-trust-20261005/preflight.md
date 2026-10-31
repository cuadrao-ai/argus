# Cuadrao Trust, Privacy and Operations preflight

Checked October 5, 2026 against fetched integration `875de09ac2115acec42e09060b92878aa5f18eff`. Original checkout remains untouched. Clean sibling `/private/tmp/cuadrao-trust-20261005` owns coordinator evidence.

## Authority and ownership

The founder authorized implementation, independent review and guarded merges to `codex/private-alpha-next`. Available Codex models were explicitly authorized in this chat after the initial Fable-only restriction was surfaced. No hosted mutations, provider calls, production promotion, legal publication or device distribution are authorized. Confirmation that the preceding coordinator relinquished shared branches remains pending. PR #843 is merged and records the overnight landing. PR #781 remains the legal-draft owner. No new implementation duplicates #811/#837.

GitHub API reports pull, push, triage, maintain and admin permissions. Branch protection enforces PRs, linear history, no force pushes or deletion, and resolved conversations. It requires zero approvals and has no status-check context requirement. This run nevertheless requires an independent verdict, terminal exact-head CI, modularity against the combined tree and immediate `--match-head-commit` merging. No automatic merge or protection bypass is permitted. Read access is exercised; worker publication will exercise push and review access. Merge access has not been exercised by preflight.

## Local proof

Python runtime 3.10.20. Docker 29.8.1. Supabase CLI 2.118.0. Xcode 27.0 build 27A266a. Simulator inventory includes iOS 26.5 and 27.0; no booted device at inventory time. Disk has 123 GiB available. Existing worktrees and stacks were inspected and preserved. Existing ports include multiple auth/account stacks from 54331 through 59754 and an API on 59905. Their ownership is not inferred; this run does not reuse or stop them.

New isolated Supabase project `cuadrao-trust-20261005` started with independent ports 60330 through 60339 and all fetched baseline migrations. Synthetic local API runs on 60340 with model credentials empty and generated invite/encryption secrets. API health returned 200, unauthenticated Household access returned 401 and disabled account deletion returned 404. Readback is in `api-preflight.json`.

Baseline operator suites `test_resume_account_deletions.py` and `test_force_account_deletion_step.py` ran 10 tests, all passed. Baseline `test_apple_sign_in_credentials_postgres.py` and `test_account_deletion_guards_postgres.py` ran 23 real-Postgres tests, all passed, zero skips and zero failures, with 7 warnings. `preflight-postgres.txt` retains the latter output. These establish local synthetic code behavior, not actual Apple authorization or provider deletion.

## Configuration and permitted use

Apple team/key/private-key/bundle settings and native Google client settings were not found locally. PostHog capture key was found but its dedicated personal deletion credential was not. OpenRouter and Perplexity credentials are present in existing root configuration but prohibited for workers. Supabase hosted credentials are present but are not copied to this stack. Availability means name-level detection only, not credential validity. No values are retained in evidence.

Local workers use `ARGUS_DISPOSABLE_DATABASE_URL`, local `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, generated `ARGUS_INGESTION_SECRET_KEY` and `CUADRAO_INVITE_CODE_SECRET`. Activation flags remain off. PostHog adapter names require an explicit reviewed placeholder contract.

## Work and gates

| Workstream | Settled work | Missing contract or input | External acceptance |
| --- | --- | --- | --- |
| Identity #800/#803/#798 | Release safeguards, Google depends on Apple, native error/appearance tests, fill-only name persistence and revoked-session checks | #798 allowlist-orphan and Hide My Email linking policy; shared deletion recovery coordination | Actual Apple/Google authorization, phone journeys and distributed activation |
| Deletion #805/#806/#807 | Safely disabled documented PostHog adapter, explicit pending/retry outcomes and local operator recovery | #805 canonical amount/provenance/settlement owner; operator identity not assigned | PostHog feature access and completion proof, hosted migration/readback and phone |
| Consent #828 | Data-flow audit, existing document guard and denied-dispatch preparation | Persisted transmission version/scoping rule and first-release jobs, memory/voice inclusion in #818/#826 | Approved policy, connected phone and hosted acceptance |
| Privacy/ops #831/#832 | Reachability/SDK/permission inventory and bounded reproduced fixes | Legal entity/contact/retention/counsel facts, #781 ownership for any draft edit | Signed manifest aggregation, hosted facts, policy approval/publication |

Whole-lane readiness is NOT READY. Independent isolated identity safeguards, disabled analytics work, recovery proof and privacy evidence are authorized to proceed without another go. Shared integration merge/housekeeping waits for ownership confirmation.

## Delivery sequence

Sequence Work into Verifiable Units selects one independently reviewed PR per bounded change. Configuration safeguards come first. Provider request persistence and recovery proofs remain separate. Shared auth, deletion and consent have one writer each. The coordinator alone schedules Mac and simulator work. No parent issue closes for a partial slice. Landed, locally verified, device verified and enabled stay separate.


Ownership gate resolved on October 5. The preceding coordinator's final end_turn at 2026-10-05T16:05:22.420Z confirms its slices landed and its owned workers, simulator and stacks were cleaned up. The matching final remote integration was 875de09. ownership-handoff.json preserves sanitized provenance. Available Codex models are explicitly authorized by the founder. Full-lane product contracts remain pending; the bounded independent scope stays green.

The founder expanded this lane to Shared Foundations #818–#820. foundation-contract-map-proposed.md names the accountable role for each shared contract and distinguishes locked currency rules from proposed space/consent/obligation semantics. No proposed semantics were activated.

Quota readback at 2026-10-05T17:49:22.082005+00:00 reports ordinary usage allowed, no spend-control or rate-limit block, and 46 percent used in the seven-day Codex window. No reset, credit purchase or paid provider call was performed. Available session model families are Codex gpt-6.1-sol, gpt-6-astra, gpt-6-sol and gpt-6-luna plus older configured models. The founder explicitly authorized available Codex models after Fable was unavailable. Strong judgment/review roles use gpt-6-astra; this is within that override.

## Expanded Shared Foundations readiness

| Workstream | Ready work | Missing input | Local proof | External gate |
| --- | --- | --- | --- | --- |
| #818 release scope | Existing consumer authority mapped; one captain | Finite included chat jobs, memory/voice inclusion | Read-only reachability/owner map, no new runtime claim | Founder scope lock and named release acceptance |
| #819 spaces/permissions | Existing membership, grants and generation retained | Root ownership migration choice | Existing contracts traced; no new migration applied | Hosted migration/readback and full phone permissions journey |
| #820 currency | Profile persistence, paired backend and consumer briefs | Onboarding placement and full release chart inclusion remain design gates | Independently reviewed local code; new CI fixes pending; broad local currency matrix is 625 pass/3 fail | Connected native pairing, phone and hosted activation |
| Trust independent scope | Release guards and recovery proof landed; disabled provider adapter, manifest and binding reviewed | #798 policy, #805 obligation, #828 processing decisions, #803 provider race acceptance | Counts and exact heads in per-PR evidence; CI still pending for unlanded slices | Provider credentials/proof, device, operator and hosted acceptance |

NOT READY for the full expanded lane. GREENLIGHT for the explicitly assigned independent slices and current-contract consumer preparation only. No unanswered recommendation becomes an accepted contract.
