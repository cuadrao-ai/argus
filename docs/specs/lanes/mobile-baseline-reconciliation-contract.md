# Mobile Baseline Reconciliation Development Lane Contract

## Verdict

- Mode: wait
- Confidence: medium
- Readiness: ready_for_lane_contract
- Execution authority: none

This is a coordination handoff and four prepared continuation prompts. It does
not authorize implementation, branch changes, commits, pushes, PR changes,
merges, deployment, provider calls or database writes. It does not cancel any
separately authorized lane work. No messages were sent to the agents.

## Goal

Reconcile the four existing lane outputs with the September 28 mobile baseline,
preserve accepted evidence, and identify the smallest next assignment for each.
Public growth sharing is parked by the founder pending evidence of what users
want to share. Household invitations remain approved. Importing a statement via
the device share sheet is ingestion, not public growth sharing.

## Evidence Audit

- Base ref: codex/private-alpha-next, as returned by the three PR reads
- Base SHA: 3b9313f3dcf80e3ff9eddfcce8818a829a081225
- Comparison ref: not applicable to this new coordination artifact; donor PRs are inventoried below, not reconciled here
- Comparison SHA: not applicable to this coordination artifact
- Merge base: not computed for donors; merge-agent handoff and fresh execution-time comparison required before continuation
- Divergence: not computed for donors; no integration readiness claim
- Changed paths: this contract only; preserve pre-existing mobile documentation and evidence changes
- Remote freshness: PR states and heads read through GitHub connector September 28; independent branch-tip freshness unverified because shell GitHub access failed and branch URL was unsupported
- Shared surfaces: auth/session owner; financial-record owner; API_CONTRACT and DATA_MODEL; local unpublished MVEE/DESIGN amendments
- Semantic overlap: new UI decisions materially overlap recording categories, balance checks, refunds, spaces and lifecycle; provider feasibility does not own those decisions
- Authority read method: remote_api_at_base_sha
- Implementation surfaces: no production edits assigned; proposed follow-ups below name bounded ownership
- Acceptance anchor: published current canon plus the approved mobile-2026-09-28 archive and local documented founder decisions

Base MVEE was read remotely at the exact SHA. The local working copy contains
additional approved decisions; these are explicitly unpublished inputs, not
assumed merged canon. The recording proposal's sections 13 and 16 were read at
its exact PR head. PR descriptions were read live; reported test results were
not rerun or independently certified in this intake.

| Input | Verified remote state | Head / evidence boundary |
| --- | --- | --- |
| Native auth #726 | Open; A14 server isolation landed via #728 (`4e024a4e`) | de61fd3e… historical probe head; A14 production fix is on integration — validate rather than re-implement; Android uncompiled |
| Asset listing #723 | Open draft | 7b91278526bb880629cc1a395dd5ae581fc50a20; synthetic checks reproducible, deleted real sample cannot be replayed |
| Recording #724 | Open draft | 720aad3fdee1357e3dbe5c928176a6e458b01b0d; 105 focused tests reported, reference model only, production contracts unapproved |
| Bank-data report | User-supplied narrative only | No PR/head/evidence index supplied; bank-format and mail-permission claims not independently reverified here |
| Message-contract agent #722 | Merged into `codex/private-alpha-next` as `b65f2f08` | published `docs/message-and-stream-shapes.md` + API_CONTRACT pointer; use landed contract for native message/stream work |

## Mode Decision

- Why this mode: no safe code lane exists for a blanket four-lane production launch from these reports alone. Individual work can be separated; auth defect repair is the first candidate for a normal feature branch once current ownership is checked.
- Why not the others: no shared execution assignment, exposure flag or validated complete record contract exists. Repository rules prohibit incubation branches; a flag cannot resolve undecided persistence or permissions.
- Safe preparatory work: publication delta, bounded report corrections, contract reconciliation and synthetic test planning; proposed prompts follow.
- Blocking decision owner: founder for native recovery destination; guest access is now locked in the MVEE. The release captain owns publication, merge overlap and assignment ownership.

## Scope

### Allowed

- Prepare the four prompts below and reconcile existing decisions without reopening them.
- Identify missing evidence and concrete decisions; retain valid prior findings.

### Forbidden

- Treat drafts, skipped CI or environment failures as green release gates.
- Start scraping, inbox access, real-bank access, provider calls or public sharing.
- Invent FX, a guest persistence policy, new auth bypasses or universal bank support.

### No-touch surfaces

- Production runtime, model instructions, migrations, hosted auth, unrelated local stacks and the frozen HTML archive.
- Other agents' branches, open reviews and deployment work.
- #722 owns `scripts/publish_message_stream_shapes.py`, its tests and generated
  message/stream documentation. Do not hand-copy its frame lists or change its
  parser-only ownership during these follow-ups.

## Prepared continuation prompts

These are proposed bounded assignments, ready for the founder to forward or
authorize. Each agent first reads the published mobile handoff (or receives its
exact local files if still unpublished). Do not rely only on the older #714
snapshot. Preserve published history; merge current integration one way, never
rebase it. Return final SHA, evidence, remaining limits and cleanup inventory.
The agents are not alone in the repository: do not revert others' work.

### 1. Native auth: isolate the server session defect

Continue from #726's findings. First check the current integration and merge
agent's work for an existing fix of A14. If already fixed, validate that delta
and report it rather than duplicate it. Otherwise prepare the smallest separate
production fix for the server auth client retaining/auto-refreshing user sessions.
Own only the auth-client configuration/factory in
`src/argus/domain/supabase_gateway.py` and its directly relevant tests, subject to
current code mapping. Write the failing regression first. Preserve Argus sign-in,
signup, guest claim, attempt limits, CAPTCHA, web cookies and public API shapes.

Use A14 as the local acceptance anchor. Also prove sequential/concurrent users
cannot inherit identity and native/web clients retain control of their refresh
tokens. Turning off a timer is insufficient if mutable session or Authorization
state can still cross requests. Start with pinned SDK behavior, not assumptions
about option names. Retain no secrets in evidence. I11 remains a separate SDK
logging risk: no SDK logger and no session-object logging; do not claim the SDK
itself is fixed. No SDK fork is assigned.

Keep guest header transport and native-session API specification as a separate
follow-up. Do not silently promote the synthetic adapter to a real endpoint.
Android remains unverified until SDK/JDK setup and an actual compile/test run.
Do not choose an email-confirmation/recovery destination on the founder's behalf.
Custom-scheme prompt observations remain qualified. No hosted settings, merge
or deployment. Preserve unaffected simulator evidence; rerun only affected checks.

### 2. Financial recording: reconcile the contract before schema work

Update #724's proposal against the final MVEE, DESIGN, mobile handoff and
`argus-account-balance-reconciliation-handoff.md`. Own the proposed recording
contract, isolated reference proof and its evidence. Return a decision delta,
not another list asking for already approved experience.

- F1: durable confirmed financial records are already the MVEE's direction.
  Clarify the exact historical Decision 8 supersession in the publication delta;
  do not broaden it into personalization-memory storage. Existing conversation
  messages already retain their figures; do not invent a new chat-deletion rule.
- F2: the approved setup/editing experience supports a balance date. Define how
  the proposed create slice reaches that editable date and represents as-of time;
  do not assert that creation time eliminates historical-date/timezone questions.
- F3: the approved question covers relevant activity on or before a prior check,
  with potentially separate answers per account leg. Same-day-only wording is
  insufficient. Preserve source evidence and each observation's ordering.
- F4: unexplained differences remain account-level and outside income/spending.
  Show how derived residuals coexist with durable confirmation-time history.
- F5: the publication pass verified that archived account balances, history and
  obligations remain in totals. Correct the proposal that archive removes them
  from totals. See the [decision response](financial-recording-decision-response.md).
- F6: preserve approved asset ownership shares and no double-counting. Do not
  infer household access from ownership or silently extend asset rules to every
  joint-account permission case.
- F7/F8: preserve separate currencies and no invented FX. Cross-currency posting
  policy is unresolved; distinguish that from already-approved unlinked refunds
  using the actual received amount/currency.
- F9/F10: map held batch rows and stale confirmations to the approved review
  journey. Refresh shows the changed effects and requires renewed confirmation.
- F11: a fixed-only catalog conflicts with optional user-entered Business
  categories. Recommend a single category owner with stable identifiers and
  localized defaults plus permitted custom labels. Account-only creation has no
  category input; do not make a full catalog a false dependency of that slice.
- F12: follow the [founder-locked guest access boundary](../argus-minimum-viable-ecosystem-experience.md#guest-access-and-registration).
  Registered-account access is settled. Define the enforcement contract and
  acceptance criteria for a later, separately authorized runtime lane, preserving
  existing guest-chat capabilities and quotas. This assignment updates the
  proposal and isolated proof only; it does not implement server enforcement.

Audit missing scenarios for 200-character notes across record types, partial and
unlinked refunds, cross-account returns, credit balances, linked refund limits,
correction/recovery, archived-account edits, spaces/account moves, and plan
occurrences counted once. Mark household authorization and link migration as
unproved rather than inventing RLS from the sketch. Extend only confirmed gaps.

Return a revised smallest create/reopen/edit slice with exact dependencies and
owned contracts. Explain when reference rules are replaced by production rules
without discarding independent expected outcomes. No migrations/API/runtime in
this reconciliation assignment. Do not repeat a broad suite already shown to be
broken by the local environment; preserve that evidence and use the proper CI
gate when authorized.

### 3. Asset listing: close the publication gap, retain manual assets

Continue #723 as report reconciliation only. Read the published vehicle/property
approval from the final MVEE and replace the missing-publication statement once
the release captain supplies the publication SHA. Preserve the original audit's
dated findings; do not rewrite historical evidence as a new capture.

Manual value or unknown, estimate provenance/date, ownership share and separately
linked debt are already approved. They do not depend on a listing feed. Keep
licensed access and asking-price ranges as unresolved optional enrichment; do
not use an untested minimum ad count as reliability evidence. This lane concerns
vehicle/property listings, not stock-watchlist symbol discovery.

No new scraping, outreach, market-value claims, raw cache reconstruction or
force-push. Preserve the disclosure about public listing IDs in earlier history.
Run only affected docs/fixture checks. Return the bounded closeout and any actual
blocking decision. If no authorized follow-up remains, close out the lane rather
than manufacture more research.

### 4. Bank data: define the selected-file import proof

First provide the report/PR/head and evidence index so the delivery lead can
verify provenance. Separate publicly documented statement availability from
observed attachment formats. Replace “works with every bank/provider” and “one
tap” with a testable supported-file/device statement. A login-only email link
is not an importable statement; cancellation and password-protected files need
honest recovery. SSO does not imply mailbox access.

Prepare a synthetic acceptance matrix for user-selected PDF/CSV/image input via
file picker and future native share extension, through review into recording.
Cover unsupported/encrypted documents, uncertain rows, duplicates, destination
account/space, source-file visibility, cancellation and retry. Reuse the existing
ingestion kit and the recording contract's confirmed draft boundary; do not
build a second ledger or automatically post emailed data.

Email forwarding and mailbox add-ons remain possible later experiments. No
inbox permissions, inbound-email service, bank credentials, real statement
collection, passwords stored, browser bank automation or production extension
implementation is assigned. A real-bank format test requires separately supplied
authorized input. Return a bounded import proof proposal and its dependencies;
bank integration does not block manual account value.

## Environment and Evidence Tier

- Evidence tier: read-only repository/remote document review; no runtime experiments
- Proof provided: three remote PR states/heads, exact-head proposal sections, base MVEE versus local approved decision delta
- Proof ceiling: no independent reproduction, final #722 review outcome, hosted behavior, Android build, RLS or production readiness
- Unrelated Docker policy: inspect ownership first; leave unrelated containers, networks, volumes, images and caches untouched
- Docker inventory: not applicable; no container operations
- Lane project ID: not applicable; no runtime stack
- Port block: not applicable; no listeners started
- Cleanup target: not applicable; only this documentation file created

## Verification

Validate this contract with the lane-planner validator and run `git diff --check`.
Before execution, each lane must obtain current base/head, merge-base and both
divergence counts, inspect changed paths and semantic overlap, and bind evidence
to the resulting SHA. This intake is not a substitute for that audit.

## Reconciliation

Publication belongs to the release captain: mobile lock, vehicle/property/share
decisions, reconciliation handoff, voice/chart direction. #722 is merged into
`codex/private-alpha-next` as `b65f2f08`; use the published
`docs/message-and-stream-shapes.md` and the API_CONTRACT pointer there for
native message/stream work. Serialize further shared API/data doc edits against
that landed contract. Keep other inspected PRs unchanged during this intake.
Auth A14 diagnosis and recording-domain reconciliation need not wait on the
message-contract documentation lane unless new overlap is found.

## Promotion

No READY claim or automatic promotion. Documents/probes can be reviewed on their
own merits; their merger does not approve every proposed product decision.
Production work requires its bounded assignment and real gates. Founder retains
merge/deployment authority; skipped draft CI is not evidence of a passing suite.

## Rollback

Remove or supersede this planning file if the merge handoff changes disposition.
No runtime or hosted rollback is needed because none was changed.

## Caveats

Native recovery destination remains an outstanding decision; guest access is
settled in the MVEE. Account archive-total behavior is now published; the custom-category
contract needs reconciliation, not guesses. The bank narrative is not a full evidence
handoff. Claimed local environment failures do not establish remote CI results.

## Stop Conditions

Stop dependent work for a competing owner, a changed acceptance surface, absent
production contract or any request to touch hosted resources without assignment.
Continue independent preparation; do not re-ask settled mobile decisions.

## Sources

### Argus authority

- [Documentation authority](../../DOCUMENTATION_AUTHORITY.md), [MVEE](../argus-minimum-viable-ecosystem-experience.md), [decision log](../argus-decision-log.md).
- [Mobile handoff](../../reports/mobile-design-lock-2026-09-28.md), [balance reconciliation](../argus-account-balance-reconciliation-handoff.md).
- [Auth #726](https://github.com/lagarcess/argus/pull/726), [recording #724](https://github.com/lagarcess/argus/pull/724), [listings #723](https://github.com/lagarcess/argus/pull/723), read September 28.
- [Message/stream contract #722](https://github.com/lagarcess/argus/pull/722), merged as `b65f2f08`; published shapes in `docs/message-and-stream-shapes.md`.
- Base MVEE read from GitHub at the exact base SHA above; local unpublished additions separately inspected.

### External guidance

- [Supabase Python initialization](https://supabase.com/docs/reference/python/initializing), checked September 28: client options configure auth behavior. This supports examining the factory; it does not independently prove A14 or its fix.

### Inference

- Auth repair and recording reconciliation are the shortest path toward a real
  native account journey. Listings and bank automation are not prerequisites.
- F11 is not a dependency for a slice with no category input. Its fixed-only
  proposal must nevertheless be reconciled before activity implementation.
