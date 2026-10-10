# Argus Decision Log

This log records locked product decisions and links to their detailed owner.
The September 26 entries record direct founder approval in the MVEE design
conversation and the subsequent request to publish a docs-only reconciliation.
See [documentation authority](../DOCUMENTATION_AUTHORITY.md) for scope and
supersession rules. These decisions do not assert implementation completion.

## Locked

| Date | Decision | Locked by |
| --- | --- | --- |
| 2026-09-14 | Sharing is shareable by default; refuse only what is private. The privacy boundary is owner selection of turns, an exact preview, and no Argus ids or account enrichment. Earlier refusals for memory use, degraded answers, missing sources, unlisted URLs, credential-shape and value-marker scanning, and length caps were removed in [#632](https://github.com/lagarcess/argus/pull/632) (commit `6054acba`, merge `c8e05b4f`). That reversed the 2026-09-09 filter built in [#574](https://github.com/lagarcess/argus/pull/574) after [#604](https://github.com/lagarcess/argus/issues/604), whose promotion walk found zero selectable answers. A Codex P1 review comment on #632 asking to restore value-marker scanning was declined because it would re-block public company names and URLs. See [conversation-sharing.md](conversation-sharing.md). | Lucas |
| 2026-09-14 | Receiver fork: a person who opens a shared `/r/<id>` link and sends a follow-up gets the frozen shared turns copied into their own new chat. The copy carries no owner note, memory, or profile. Decision commit `675c1f94` reversed the earlier no-fork stance. Built in [#643](https://github.com/lagarcess/argus/pull/643), merged at `0044d79a` on 2026-09-15. See [conversation-sharing.md](conversation-sharing.md). | Lucas |
| 2026-09-24 | The first user is people living in the Dominican Republic, not the diaspora. | Lucas |
| 2026-09-24 | Argus keeps all its existing grounded chat and calculation capability. The pivot adds features around it so Argus isn't just an AI chat, building toward an ecosystem. | Lucas |
| 2026-09-26 | Approve one connected minimum viable ecosystem carrying forward existing Argus capabilities. The earlier one-product-versus-two question is resolved for this experience. Detailed owner: [MVEE sections 1–3 and 7](argus-minimum-viable-ecosystem-experience.md). | Lucas |
| 2026-09-26 | Lock the initial audience and near-term financial emphasis, shared planning picture, and low-effort recording/return loop. Detailed owner: [MVEE section 1.1](argus-minimum-viable-ecosystem-experience.md#11-locked-audience-and-experience-emphasis). | Lucas |
| 2026-09-26 | Approve ingestion experience and its confirmation, correction, provenance, and freshness boundaries; experimental access paths are not provider commitments. Detailed owner: [MVEE sections 4–5](argus-minimum-viable-ecosystem-experience.md#4-information-ingestion-one-destination-several-entry-methods). | Lucas |
| 2026-09-26 | Preserve Argus visual identity and existing chat detail; approve ecosystem navigation and native iOS/Android plus web intent. Detailed owner: [MVEE section 2](argus-minimum-viable-ecosystem-experience.md#2-product-character-and-platforms). | Lucas |
| 2026-09-26 | Include partner invitations and personal/household views in the minimum ecosystem, superseding the earlier deferral. Detailed owner: [MVEE section 12](argus-minimum-viable-ecosystem-experience.md#12-household-collaboration-approved-minimum-capacity). | Lucas |
| 2026-09-26 | Publish approved experience and reconcile older document pointers in a docs-only PR; defer new technical design and implementation sequencing. Owner: [documentation authority](../DOCUMENTATION_AUTHORITY.md). | Lucas |
| 2026-09-26 | Carry production behavior and gates forward unless explicitly changed; distinguish current availability from approved future experience. Owner: [PRODUCT.md availability and transitions](../PRODUCT.md#current-production-availability-and-planned-changes). | Lucas |
| 2026-09-26 | Lock platform-native mobile interfaces and retain the existing web/PWA stack, sharing one Argus backend and canonical financial truth. Accept separate interface maintenance with coordinated agents and platform-specific verification. Detailed stack owner: [ARCHITECTURE.md platform decision](../ARCHITECTURE.md#approved-platform-direction). Client contracts and rollout remain to be defined. | Lucas |
| 2026-09-27 | Approve quick type-specific account setup, optional nicknames and unknown balances, and optional property, vehicle and other asset tracking. Lock the estimate, ownership and linked-debt boundaries; listing-based valuation remains a future candidate capability. Detailed owner: [MVEE quick setup and assets](argus-minimum-viable-ecosystem-experience.md#quick-account-setup-and-optional-assets). | Lucas |
| 2026-09-27 | Accept the simplified account-entry sketch and consistent money-entry treatment as the current design baseline; stop further visual refinement for this pass. Experience owner: [MVEE quick setup](argus-minimum-viable-ecosystem-experience.md#quick-account-setup-and-optional-assets). Interaction owner: [DESIGN money entry](../../.agent/designs/argus/DESIGN.md#money-entry-in-the-ecosystem-sketch). Device verification and production contracts remain separate work. | Lucas |
| 2026-09-27 | Lock distinct account setup, new activity and balance-check actions; require an explicit discrepancy review and traceable adjustment without invented income/spending. Reuse the existing destructive confirmation for removal. Experience owner: [MVEE balance checks](argus-minimum-viable-ecosystem-experience.md#account-activity-and-balance-checks); technical follow-up: [backend handoff](argus-account-balance-reconciliation-handoff.md). | Lucas |
| 2026-09-27 | Lock simplified populated Home, bounded account previews, and inherited Recents/Omnisearch growing-list behavior. Preserve currency-separated net worth; combined conversion remains undefined. Owners: [MVEE Home summary](argus-minimum-viable-ecosystem-experience.md#populated-home-summary-and-list-boundary) and [DESIGN growing lists](../../.agent/designs/argus/DESIGN.md#growing-lists-across-ecosystem-surfaces). | Lucas |
| 2026-09-27 | Lock copy-link household invitations, user-shared WhatsApp links, do-blitz as the short-link integration direction, and Resend email delivery; no incentives. Detailed owner: [MVEE invitation delivery](argus-minimum-viable-ecosystem-experience.md#invitation-delivery-founder-locked-september-27-2026). Contact discovery and implementation contracts are not implied. Narrowed on 2026-10-02: do-blitz no longer handles invite links; see [October 2 lane locks](#october-2-2026-cuadrao-lane-locks). | Lucas |
| 2026-09-28, clarified 2026-09-29 | Revenue, pricing, paywalls and billing remain deferred; existing usage and cost safeguards remain. The current user-trial boundary permits founder dogfooding and physical-phone demonstrations. Detailed owner: [documentation authority — founder deferral](../DOCUMENTATION_AUTHORITY.md#founder-deferral). | Lucas |
| 2026-09-29 | The [private iPhone delivery and execution lock](#september-29-2026-private-iphone-delivery-and-execution-lock) owns the current delivery decision and supersedes the batch instructions below. | Lucas |
| 2026-10-01 | Lock Household permission policy: creator administers invitations/membership and may transfer administration or close before departure; members see the member list and may leave; shared accounts start view-only with editing only via explicit grant; edit grants do not confer ownership, membership administration or resharing; leave/removal revokes membership and that member's account grants while owners retain records/history; invitations are revocable, single-use, seven-day links with safe same-recipient acceptance retries; create ≠ invite ≠ share account and acceptance is membership only. MVEE consent and financial-meaning boundaries remain. Owners: [execution board Household lane](argus-execution-board.md#connected-spaces-and-household-lane), [MVEE section 12](argus-minimum-viable-ecosystem-experience.md#12-household-collaboration-approved-minimum-capacity), [lane contract](lanes/household-permission-policy.md). Narrowed on 2026-10-02: rule 5's departure behavior, and rule 1's admin handoff when the admin deletes their account, now follow the [October 2 lane locks](#october-2-2026-cuadrao-lane-locks). | Lucas (Project orchestrator recorded) |
| 2026-10-02 | Lock the invitation (beta versus household invites, 10 beta invites per user, and a founder group link as the one exception to single-use codes), TestFlight beta-gate, Home comparison, Updates, plan-export, account-move and account-deletion-in-a-household rules for the five Cuadrao lanes, including what happens to a deleted person's part in shared plans (8:53 PM CT). Detailed record: [October 2 lane locks](#october-2-2026-cuadrao-lane-locks). | Lucas |
| 2026-10-04 | Lock the Cuadrao launch shape: consumer iPhone app with personal and household only, a short invite-only TestFlight then a public launch; Cuadrao for Business as a full web service with a thin in-app business space for the first business testers only; cuadrao.ai promoting the whole suite with waitlists; Resend, Render and Supabase kept. Also partner first for live e-invoicing, Plaid kept, market-data providers parked for the pilot, Dominicans in the US added as a consumer segment, and no currency conversion or blended totals. Detailed record: [October 4 Cuadrao launch shape](#october-4-2026-cuadrao-launch-shape). | Lucas |
| 2026-10-04 | Lock the AI providers (2:20 PM CT): OpenRouter for the chat models (GPT and Grok) and vision extraction, Grok voice for the planned chat voice-call feature, and Perplexity for finance search. All three stay behind the server and never write saved balances. Detailed record: [October 4 AI providers](#ai-providers). | Lucas |
| 2026-10-04 | Lock the space-model timing (2:21 PM CT): the space-model change lands before TestFlight. The model itself still needs its own lock. Detailed record: [October 4 space model timing](#space-model-timing). | Lucas |
| 2026-10-07 | Approve the connected Business workflow and offline E0 plan with task-by-task independent review. Counsel may publish and land the docs-only PR; Lucas coordinates Business implementation. Detailed record: [Business connected flow and E0](#october-7-2026-business-connected-flow-and-offline-e0-plan). | Lucas |
| 2026-10-10 | Approve the Business agent direction. One agent in the existing runtime talks only to the owner in WhatsApp and completes each record through Business tools. The accountant works in the web view. Reuse the runtime and services; no second loop, extractor, ledger or vendor. Contract first, then parallel streams; the "Pagué 850" journey is the first proof; evals gate merges. Cuadrao branches from `codex/private-alpha-next`. Detailed record: [Business agent direction](#october-10-2026-business-agent-direction). | Lucas |
| 2026-10-10 | Clarify the first Business outcome as a working hosted internet system and an invite-only web beta. Authorize the bounded build, clean integration merges and staging only. Preserve varied natural-language flows and the existing runtime. Detailed record: [Hosted Business beta and build grant](#october-10-2026-hosted-business-beta-and-build-grant). | Lucas, relayed by the root coordinator |

## October 7, 2026 Business connected flow and offline E0 plan

Lucas approved the [connected-flow specification](cuadrao-business-connected-flow-spec.md)
and [E0 implementation plan](cuadrao-business-e0-implementation-plan.md), including
task-by-task independent review. The approval was relayed from the roadmap-alignment
conversation with his exact instruction:

> Yes i approved this plan and the counsel can open a docs pr and land it when it's clean then i ill coordinate a claude worker to pick it up. it willl be the business agent that we have been working on with.

Counsel may publish and merge this documentation-only change when review and
checks are clean. This is the explicit exception to the standing no-docs-only-PR
rule. Lucas coordinates implementation with the existing Business agent.
The grant does not dispatch an implementation agent or authorize credentials,
provider calls, migrations, deployment or a lane-priority change.

Cuadrao owns its engine with replaceable signing and transport. E0 is synthetic,
offline and unsigned. It preserves input evidence, exact arithmetic and actual
validation results. P0 requires official schema bytes, dependencies, hashes and
profile rules before Type 31 implementation. The specification owns the detailed
resolve-first, immutable-artifact and independent-state requirements.

The October 4 partner-first record remains historical live-route context.
It is not a prerequisite for approved offline E0 development. Supplier discussions
stay open. No vendor is selected or cancelled, and no direct live issuance route,
certificate-custody permission or issuer eligibility is established here.
Consumer and Marketing retain their milestones. Business retains space isolation
and the connected owner flow; Consumer coordinates shared migration order.

The approved inputs were checked before import. Repository edits update approval
status and navigation only; the substantive design and task criteria are retained.
The source documents' October 8 research dates remain as supplied. Publication
uses October 7 in America/Chicago and does not re-verify those research claims.

| Approved source | Library provenance | SHA-256 before repository edits |
| --- | --- | --- |
| `cuadrao-business-connected-flow-spec.md` | `libfile_74ecaa0fb4348191828248df60a54cc4`, version 2 | `c447bfe2a985c915424cde23d1a45abd6afb1114e9db16aed592cdbbf1ed0bba` |
| `cuadrao-business-e0-implementation-plan.md` | `libfile_e68336b17ce481919c7a797c806f4c28`, version 1 | `691dacd42e72199a49189c1e237e0555adf12f08b2a744e09519f63f03a3b8bd` |

## Superseded coordination instructions (historical only)

These entries record prior assignments, not active instructions. Their replacement
is the [September 29 delivery lock](#september-29-2026-private-iphone-delivery-and-execution-lock).

| Date | Historical decision | Disposition |
| --- | --- | --- |
| 2026-09-28 | The Project delivery lead and VM serial captain were assigned the three-interface account journey, with named exclusive writers for the surfaces and research/proof PRs. Source: [PR #727 handoff](https://github.com/lagarcess/argus/pull/727#issuecomment-5878051744). | Superseded by the September 29 delivery lock; this row assigns no current owners or work. |
| 2026-09-28 | User trials were parked while core journeys became functional. | Clarified by the [current founder deferral](../DOCUMENTATION_AUTHORITY.md#founder-deferral); this historical pause does not block founder dogfooding or physical-phone demonstrations. |
| 2026-09-28 | [#725](https://github.com/lagarcess/argus/pull/725) landing was held for a narrowed research / selected-file-import scope. | Superseded by the September 29 delivery lock; the old hold is not a pending landing assignment. |

## Wave 1 package-era constraints (not current locks)

These are dated shipping assumptions from the Wave 1 package. They do not
override later MVEE or PRODUCT owners.

| Date | Constraint | Note |
| --- | --- | --- |
| 2026-09-25 | Three-step setup checklist: get a first answer; save a card or create a goal (sign-in at that step); then turn on reminders. | Wave 1 package-era onboarding sketch. [MVEE](argus-minimum-viable-ecosystem-experience.md) leaves account onboarding and exact guest-to-account conversion undecided; [PRODUCT.md](../PRODUCT.md#current-production-availability-and-planned-changes) owns current availability. Do not invent conversion timing from this row. |

## Open (not locked)

Voice and chart direction was subsequently locked on September 28; see the
dated entry below. Sharing growth concepts remain recommendations, not an
approved expansion of the frozen mobile baseline.

The canonical list is [MVEE section 9](argus-minimum-viable-ecosystem-experience.md#9-decisions-deliberately-left-open).
The authority map identifies technical areas still requiring contracts before
implementation. Earlier documents' open-question lists are dated history;
do not treat them as reopening the decisions above.

## September 28, 2026 — UI completion checkpoint

The founder requested closing the Home, connected-plan, household contributor/
permission and financial-recovery experience gaps, including refunds and account
adjustments. The MVEE now owns those behaviors and the private Business-space
boundary. DESIGN owns quiet space navigation versus underlined section tabs.
The account reconciliation handoff records the unresolved posting, matching and
recovery contracts. This freezes a disposable UI reference; it does not authorize
backend implementation, change production contracts or establish release readiness.

## September 28, 2026 — account space reassignment

The founder approved the bounded Manage account journey: move between private
spaces, share separately with Household, preserve financial history, and review
linked records before confirmation. Detailed behavior is owned by the MVEE's
Reassigning accounts between spaces section. Production atomicity and permissions
remain contract work; this approval implements only the disposable UI sketch.


## September 28, 2026 — complete mobile design lock

Founder: “do a full sweep and lock the design for mobile, including your html
reports of full ecosystem … lock it in.” The local template and all six current
reports are frozen as one dated reference. The MVEE now records the final
Settings ownership and single Temporary-chat experience; DESIGN owns its stable
header and composer transitions. The [handoff](../reports/mobile-design-lock-2026-09-28.md)
links the source/evidence archive, checksum and implementation boundary.
This is design acceptance, not release readiness or an assignment to implement
all visible provider-dependent concepts. No backend, API, model prompt, deployment
or production data was changed.

## September 28, 2026 — voice and chart direction

Founder: “Yes, lock it,” approving full voice with xAI and the native chart
shortlist. Detailed technical owner: [architecture direction](../ARCHITECTURE.md#voice-and-chart-direction).
The [MVEE voice experience](argus-minimum-viable-ecosystem-experience.md#43-speak-to-argus)
now explicitly includes full spoken conversation. Vico remains subject to a
representative prototype, and integrated speech-to-speech orchestration remains
subject to preserving Argus's single runtime owner. This does not modify the
frozen HTML archive or authorize provider calls, implementation or deployment.

The founder also requested applying *Contagious* to ecosystem sharing. The
[research note](../research/2026-09-28-ecosystem-sharing.md) records source-backed
principles and a proposed bounded first experience. Specific growth surfaces,
metrics and mechanics in that note are not locked product requirements.

## September 28, 2026 — publication and recording reconciliation

The founder authorized pushing this branch and opening its publication PR, with
continuation prompts to be handed back for the other lanes. The MVEE clarifies
the already-approved confirmed-record exception to historical Decision 8 and
the final template's archive behavior: archived account balances and obligations
remain in the financial picture. Unconfirmed figures in chat retain their
existing conversation policy; no personalization-memory expansion is approved.
The [recording decision response](lanes/financial-recording-decision-response.md)
separates settled experience from remaining recommendations.

The founder parked public growth sharing until there is evidence of what users
want to share. Household invitations and file ingestion remain in scope.

## September 28, 2026 — guest access and ecosystem runtime sequence

The founder locked [guest access](argus-minimum-viable-ecosystem-experience.md#guest-access-and-registration):
guests can see the app and use existing finance chat within current limits;
other ecosystem features require registration across native and web interfaces.
This settles the recording lane's guest-persistence question without changing
existing guest-chat quotas or authorizing a production auth change here.

The founder also confirmed [agentic ecosystem direction and sequence](argus-minimum-viable-ecosystem-experience.md#agentic-ecosystem-direction-and-sequence).
Manual UI and future conversational actions must share the same canonical
operations. The ecosystem runtime lane follows definition of the core workflows
and UI. This is not permission to replace the existing runtime, change its
model-facing instructions, or remove research and historical simulations now.

## September 29, 2026: private iPhone delivery and execution lock

The founder requested publication of the complete discussion in the MVEE and a
single execution manifest. The [MVEE delivery lock](argus-minimum-viable-ecosystem-experience.md#12-private-iphone-delivery-the-immediate-finish-line)
owns the real physical-iPhone/internet outcome, full scope, agent-first direction
with explicit runtime deferral, tester feedback, current Supabase-project/plan
reuse, modular backend and web-remake freeze. These are founder decisions from
this delivery conversation, not claims that the capabilities are implemented.

The [execution manifest](argus-execution-board.md) is the single delivery map,
with dependencies, required ownership, acceptance, evidence and restart rules.
[Documentation authority](../DOCUMENTATION_AUTHORITY.md) points agents to it and
marks the earlier three-interface batch historical. This entry supersedes the
September 28 active-batch and #725 landing-hold instructions: all implementation
is stopped, #723/#724/#725/#726 are closed unmerged, and no prior coordination
instruction restarts them. The founder authorized this documentation PR only.
The manifest's proposed work order is the delivery lead's plan, not an already
accepted technical contract or a new implementation/deployment grant.

## October 2, 2026: Cuadrao lane locks

The founder approved these in the Docs Alignment room while scoping the five
lanes (Home data, Household invitations, Updates, Search, Spaces). Product
Lead (Iris) drafted the recommendations and the founder said yes; Head of
Engineering (Yelena) recorded them for the lane handoff. Two details were
approved by the founder's reaction rather than a written yes; each is marked
below with its time. These are decisions, not claims that anything is built.
Delivery order and review steps are the Head of Engineering's plan in the lane
handoff, not founder locks. The lane handoff links here instead of restating
them.

### Invitations

- An invitation produces a share link, an invite code and a QR code.
  Household email invitations are not in this pass. A Resend adapter
  already exists, sending from the get-argus.com address; what is missing is a
  Cuadrao sending domain.
- The invite link is a universal link on cuadrao.ai that opens the app. The
  current `argus-household://` scheme and the design branch's placeholder
  domain are not the target.
- do-blitz is replaced for invites. Invite links go straight to cuadrao.ai,
  because a redirect through a shortener usually opens Safari instead of the
  app. do-blitz stays an option for marketing and ad links later. This narrows
  the September 27 invitation-delivery lock; its Resend and WhatsApp parts are
  unchanged. (Founder approval by reaction, 5:58 PM CT.)
- Each code works once, except the founder's group link (see the TestFlight
  beta gate below), and records who sent it, so the who-invited-whom
  record exists. This builds on the October 1 single-use, seven-day rule.
- When an account is deleted, an anonymous record that an invite was sent and
  accepted is kept, with no name or identifier. Deleting an account still
  removes the person. (Iris's detail, approved by the founder's reaction at
  5:33 PM CT.)
- The inviter gets an "invitation accepted" entry in Updates. There is no
  "invitation received" entry, because the invitee already has the link or
  code and an invitation has no named recipient before acceptance.

### TestFlight beta gate

This gate and the three network numbers are the founder's October 2 lift of
the [founder deferral](../DOCUMENTATION_AUTHORITY.md#founder-deferral) (no broad
user trials, no new growth analytics), scoped to invites only.

- The cuadrao.ai landing page collects a waitlist, and the founder rolls access
  out personally. He onboards the first users himself.
- There are two kinds of invitation. Any user can send a beta invite; each
  user has 10 for TestFlight, and the founder can add more. Only the household
  admin sends household invites. These don't use any of the 10, and they also
  let the invitee into the beta. This keeps October 1 rule 1: only the
  household admin administers household invitations. (Founder lock, 8:04 PM
  CT; the split is Iris's proposal, with the quota raised from 3 to 10.)
- The founder, and only the founder, can create a group link that many people
  can use. He sets a cap (for example 50) and an expiry date. Redemption is
  atomic, so a burst of taps can't go past the cap. Once the cap is reached,
  anyone who taps the link lands on the cuadrao.ai waitlist and is told so on
  screen. Each group link is its own source in the network numbers, and the
  who-invited-whom record shows the link as the inviter. This is an exception
  to the single-use rule. The group link is beta-only: redeeming it never
  grants household membership. The link can be forwarded beyond the chat it was
  posted in; the cap and the expiry date limit that spread. (Iris's proposal,
  Yelena's build note, founder lock at 8:06 PM CT.)
- A TestFlight public link only installs the app. The in-app invite code is the
  real gate. Anyone without a code is sent to the cuadrao.ai waitlist.
- Three network numbers are tracked from the start: invites sent per user, the
  share of invites accepted, and the share of invitees who go on to invite
  someone. Household invites are counted separately from beta invites.
- Apple's first beta review must be scheduled before the first outside
  distribution.

### Sign-in for TestFlight

- Sign-in for TestFlight is Apple, Google and email. Email works with any
  address and has an in-app confirmation step. The founder added Google because
  people will likely want to sign up with their Gmail address. (Founder
  decision, 10:06 to 10:07 PM CT.)
- Engineering (Yelena) builds Apple and Google sign-in behind default-off flags.
  They stay off until the founder supplies the keys: for Apple, Sign in with
  Apple enabled on the app ID, a Services ID and a .p8 key; for Google, a
  sign-in client.
- Because the app offers Sign in with Apple, deleting an account also revokes
  the person's Apple tokens. Deletion also revokes every Google token Argus
  holds, Gmail source tokens included (Yelena's call, October 2). Native Google
  sign-in exchanges an ID token and stores no Google refresh token, so there is
  nothing to revoke for it. The steps are in the
  [lane handoff](lanes/mvee-five-lane-handoff.md#lane-6-account-deletion).

### Home comparisons

- A month with confirmed complete coverage and no spending is a known zero. It
  shows 0, and the comparison still shows. When the earlier period is zero, the
  difference is shown as an amount (for example "RD$4,500 more than last
  month"), not a percent.
- "Sin datos" (no data) shows only when coverage for the period is missing.
- (Founder clarification, 10:18 PM CT. This restores the wording of design
  commit `fc7650ea`. It replaces the reading in #787 that tied no data to a
  period with no records and called a zero a period whose records add up to
  zero.)

### Updates

- Everything Cuadrao notifies about lands in Updates. Home's Próximamente
  section keeps showing upcoming bills for the Space in focus.
- A bill gets an Updates entry 3 days before its due date and again on the day.
- During TestFlight, Updates uses the in-app inbox plus push for people who
  turn push on. Push never includes amounts; amounts appear only inside the
  app. Updates are not sent by email yet.

### Joint plans

- Exporting joint plans is deferred until after TestFlight. The read-only
  archive from [#773](https://github.com/lagarcess/argus/pull/773) stays until
  its owner deletes it. If the owner deletes their account, the archive passes
  to the plan's longest-standing participant instead (see the section on
  deleting an account below).

### Leaving a household and moving accounts

- When a member leaves, the accounts they own go with them and the household
  loses access right away. Members who had a grant at the cut-off keep that
  account's history up to the move date, greyed out and read-only, with the
  state at the move recorded. Shared plans that relied on it are archived
  read-only for the remaining members. This narrows October 1 rule 5 (leave or
  removal revokes the member's grants and owners retain history).
- Moving an account between Spaces never rewrites past balances or
  settlements. A move is recorded as an event, replaying it changes nothing, and
  access rules block creating, editing or deleting the locked history. Home is
  recomputed from history.

### Deleting an account in a household

- When an owner deletes their account, the household's locked copy of that
  owner's account history is deleted too, and the other members see a short
  note that it was removed. This is the one exception to members keeping
  history after a departure (see the section on leaving a household above).
- When the household admin deletes their account, the admin role passes
  automatically to the longest-standing remaining member. If no one is left,
  the household closes. This narrows October 1 rule 1, where the admin
  transfers administration or closes the household before leaving: account
  deletion does not wait for a manual transfer.
- Both are founder locks (8:04 PM CT) of Iris's proposals.
- Deleting any account also clears that person's email from saved feedback
  and deletes the person in PostHog by distinct id, including their events.
  (Yelena's recommendation, founder lock at 8:04 PM CT. The PostHog wording
  was clarified Oct 2 via #782.)
- When a person deletes their account, in plans other people own their
  amounts keep their values and dates under a nameless placeholder:
  "Exmiembro" in Spanish and "Former member" in English, numbered
  ("Exmiembro 1", "Exmiembro 2") when more than one person leaves a plan. The
  placeholder has no user id, name, avatar or email. Their receipts, photos
  and free-text notes are deleted; amount, date and category stay. Open
  balances with them are frozen: not marked settled and not forgiven. They
  come out of the active totals and show as a closed line, and a member can
  later mark it settled, which is recorded as a new event. Their future
  responsibilities go back to the plan's owner, who gets an Update to reassign
  or re-split them. Past legs stay as they are. Shared plans they owned, and
  the #773 archive, pass to the plan's longest-standing participant; if nobody
  else is in the plan, it is deleted. The plan name stays. The confirmation,
  member-note and new-owner wording in Spanish and English is Iris's, and lives
  in the [lane handoff copy](lanes/mvee-five-lane-handoff.md#copy-founder-locked-iriss-wording).
  This replaces the Head of Engineering's draft to anonymise or delete those
  rows. (Iris's proposal, founder lock at 8:53 PM CT.)
- Implementation note, not a new decision: "no user id" above is implemented
  as "no id tied to the person". The foreign keys require a real `auth.users`
  row, so account deletion creates one nameless, banned placeholder user per
  household or [standalone shared group](lanes/account-deletion-fk-census.md#sharing-scopes-and-the-standalone-shared-group) and departed person (Yelena's call,
  October 2). A household is one scope: every plan and membership-keyed row in
  it re-keys to that household's single placeholder, because its members
  already knew it was one person. Every shared plan sits in a household,
  because `household_plan_bindings.household_id` is `not null`. A placeholder owns
  rows in one household or group only; under decision (c) (Lucas, Oct 3, in
  the [lane handoff](lanes/mvee-five-lane-handoff.md#steps-in-order)), another
  household's claims on an activity can name it as a reference without it
  owning anything there. The "Exmiembro" numbering stays per
  plan, because it is only a label. The steps are in the
  [lane handoff](lanes/mvee-five-lane-handoff.md#lane-6-account-deletion).
- A shared debt plan whose owner deletes their account is not handed over,
  because nobody can own another person's debt account. It is archived
  read-only under the placeholder of the plan's household. Contributions keep
  their values and dates under "Exmiembro" / "Former member", and open
  balances show as a closed line. Participants see Iris's banner on the
  archived plan and get the usual member note. This is the Head of
  Engineering's (Yelena's) call on October 2, not a founder lock. It follows
  decision 17 and Iris's frozen-balance rule. Yelena confirmed it as the one
  exception to the plan handover in the bullet above.

### Outside services

- The universal link and push are not built yet. Each will be built behind a
  default-off flag with a fake and stay off until the founder connects the real
  service, so turning one on later is configuration only. Household email
  invitations and update email are not in this pass, so nothing is built for
  email. The domain, keys and links the founder will supply are not recorded
  here.

## October 3, 2026: avatar editing in release

- Founder decision. Hide the connected avatar-editing entry in release until
  selections survive relaunch. Keep the full editor, including photos, in
  DEBUG. Keep the existing profile display and default icon. One shared
  availability rule across connected and preview entry points. No this-device
  copy for session-only state.

## October 4, 2026: Cuadrao launch shape

The founder set these in the room on October 4. Head of Engineering (Yelena)
recorded the launch shape at 12:30 PM CT and the fiscal route correction at
12:39 PM CT in her engineering notes. Product Lead (Iris) relayed the
connector and segment calls at about 12:44 PM CT and the currency rule at
about 12:45 PM CT. Yelena relayed the AI provider lock at 2:20 PM CT, and Iris
relayed the space-model timing at 2:21 PM CT. The docs seat (Maya)
recorded them here with the [Cuadrao master plan](cuadrao-master-plan.md),
which is a planning roadmap, not a lock. These are decisions, not claims that
anything is built. Everything else in the master plan, including the space
model, the roles matrix and founder calls F1 to F5, stays open until locked.
The source documents are recorded as the
[go to market vision](../research/2026-10-04-cuadrao-gtm-vision-source.md) and
the [product and business architecture](../research/2026-10-04-cuadrao-product-business-architecture-source.md).

### Launch shape

- The consumer iPhone app launches with personal and household spaces only.
  It goes to a short invite-only TestFlight under the October 2 invite rules,
  then to a public launch with fast iteration.
- Cuadrao for Business is a full service on the web. The business space in
  the iPhone app stays thin: capture, quick approvals and where money stands.
  It goes only to the first business testers on TestFlight, and public
  consumers never see it. How to keep it out of the public build is the Head
  of Engineering's call, not a founder lock.
- cuadrao.ai promotes the whole suite and carries the waitlists.
- The stack stays on Resend, Render and Supabase.

### Fiscal route

- Partner first. Connecting to a DGII-certified provider is the route to live
  e-invoicing through Cuadrao. Cuadrao's own DGII backend is the parallel
  track while the founder handles the DGII paperwork. The pilot starts by
  tracking the invoices owners already issue, then issues through Cuadrao
  once the provider connection is live. The founder chooses the provider; no
  provider is chosen yet.

### Connectors, data providers and segments

- Plaid is kept. The Plaid sandbox with generated test data is how financial
  data is stress-tested. Real Plaid serves Dominicans in the US and
  Dominicans with accounts abroad, and manual entry stays available for
  anything Plaid doesn't cover. Production Plaid access goes through Plaid's
  own review on the founder's partner track.
- Dominicans in the US is a named consumer segment. It is added next to the
  September 24 lock that the first user is people living in the Dominican
  Republic; that lock is not replaced.
- Market-data providers (Alpaca, Kraken, BCRD and the others) are parked for
  the pilot, not deleted. BCRD is fully parked. Their keys come out of the
  live setup and the code stays. Perplexity covers general finance questions
  in chat.
- The Gmail import is still an open decision.

### Currency

Cuadrao never converts currencies, because converting would blur the numbers
and make Cuadrao responsible for their accuracy. This decides the September 27
note that combined conversion "remains undefined". The founder's design lane
owns the final screens.

- Every account stays in its own currency. Cuadrao never shows a blended
  total.
- Home shows one total per currency on separate lines, for example
  "RD$ 85,400" and "US$ 1,250". The person's primary currency comes first;
  they set it at onboarding and can change it later.
- Charts and comparisons show one currency at a time, with a switcher when
  the person holds more than one currency.
- Plans keep a fixed currency. When an account in another currency pays
  toward a plan, the person records both amounts exactly as their bank
  charged them. The rate comes from their real transaction, never from
  Cuadrao.

### AI providers

Locked at 2:20 PM CT. All three providers stay behind the server, and none of
them writes saved balances. The env inventory is in the master plan's
[§B4.1](cuadrao-master-plan.md#b41-argus-era-env-vars-and-data-providers-keep-drop-park-fact-for-where-read-proposed-for-the-call).

- OpenRouter is kept, for the chat models (GPT and Grok) and for vision
  extraction.
- Grok voice is the provider for the chat voice-call feature. The feature is
  new and not wired yet, so it has no setting name today. Once built it gets a
  server-only key, and the phone never holds it.
- Perplexity is kept, for finance search. Cuadrao integration requires a separately assigned runtime slice;
  [#813](https://github.com/lagarcess/argus/pull/813) records the delivery sequence.

### Space model timing

Locked at 2:21 PM CT. The space-model change lands before TestFlight, which
is a few days out. Which migration steps that covers is the Head of
Engineering's sequencing in the master plan's
[§B2.3](cuadrao-master-plan.md#b23-mapping-today-onto-it-and-the-migration-path-proposed).
The model itself, including business roles and the business retention rule,
is still open for the founder.

## October 4, 2026: constitution reconciliation

After the source upload in [PR #835](https://github.com/lagarcess/argus/pull/835),
the founder instructed the mobile lane to settle the conflicts using existing
decisions and carry the principles into their canonical owners. The
[reconciliation record](../research/cuadrao-constitution-2026-10-04/RECONCILIATION.md)
records the dispositions; the [principles index](../research/cuadrao-constitution-2026-10-04/PRINCIPLES.md)
links to the updated owners.

This adopts the bounded principles and resolves conflicting documentation. It
does not select unresolved business pricing, fiscal providers, the full space
model, Gmail import or the Cuadrao agent architecture. The source originals stay
unchanged. Feature catalog priorities do not add launch requirements, and this
documentation authorization does not authorize runtime, deployment or provider work.

## October 4, 2026: runtime reuse and customer work removed

The founder clarified that Argus already uses Render Workflows for backtests and
approved extending that foundation rather than evaluating it as a new platform.
The subsequent alignment request records an ongoing Cuadrao conversation as the
experience direction and requires the existing issues to measure customer work
removed.

The [architecture reuse map](../ARCHITECTURE.md#cuadrao-reuse-decisions),
[continuous conversation requirements](argus-minimum-viable-ecosystem-experience.md#continuous-cuadrao-conversation)
and [journey acceptance questions](../PRIVATE_LAUNCH_RUNBOOK.md#customer-work-removed)
own the details. #826 still owns the bounded runtime contract before #827
implementation. Reuse does not claim memory or voice is connected, choose a new
schema, authorize paid evaluations or permit deletion of active Argus services.


## October 4, 2026: continuous-chat stack and launch pillars

The founder approved LangGraph, the existing Mem0/pgvector integration, scoped
on-demand context injection and Render Workflows as the starting stack for
Cuadrao's continuous agentic chat. The [architecture owner](../ARCHITECTURE.md#cuadrao-reuse-decisions)
records the choice and corrects the earlier blanket pgvector deferral. Temporal
and Inngest require a demonstrated workflow gap; Braintrust is optional quality
tooling. Neither workflow selection nor memory retrieval changes the canonical
owner of financial records or grants access across spaces.

The founder also requested a complete launch breakdown and updates to missing
issue acceptance. The [execution pillars](argus-execution-board.md#parallel-execution-and-priority)
map the existing #817 checklist to parallel tracks and the final serial release
sequence. #826 retains the bounded runtime contract; the foundation choice is
settled, while exact first-release jobs and memory/voice inclusion remain in the
scope record. This planning lock does not claim implementation or approve
merges, hosted changes, paid evaluations or distribution.


## October 4, 2026: recurring work, categories and Plan usefulness

The founder approved the reviewed recurring, category, gesture and projection
direction and explicitly chose expected-payment preparation with confirmation
when paid. The [MVEE](argus-minimum-viable-ecosystem-experience.md#recurring-setup-upcoming-and-useful-scenarios)
owns the recurring/Upcoming/scenario behavior and
[category correction rules](argus-minimum-viable-ecosystem-experience.md#category-suggestions-and-useful-corrections).
The [native design guide](../../.agent/designs/cuadrao/DESIGN.md#account-and-movement-actions-october-4-target)
owns the revised account gestures and movement shortcuts.

Implement these behaviors from Cuadrao's own requirements, contracts and tests.
Midday is a research reference, not a source-rewrite assignment; rewording copied
code is not independent implementation. Any proposed source reuse requires its
own license review. Existing #818/#822/#823/#824 track the work. Pattern
suggestions follow usable recurring setup; forecasting-library selection needs
measured benefit. No runtime, provider, hosted activation or additional launch
blocker is created by this documentation lock.


## October 5, 2026: Apple session revocation applicability

The founder approved Apple credential-state checks for sessions signed in with Apple. Known email and Google sessions retain access when the account also links Apple. Older mixed-provider sessions whose sign-in method is unknown require one explicit sign-in to establish it. Linked identities do not prove the current session's sign-in method.

The existing native session journal owns successful grant provenance. Other callers derive admission from SessionController; they do not infer a provider from email, linked identities or a second cache. PR864 carries the implementation and local proof, pending its exact-head CI and integration landing. Real Apple authorization/revocation, hosted settings and feature activation remain separate gates. This decision does not select #798's orphan or Hide My Email linking policy.


## October 6, 2026: first-release assistant and memory and voice scope

The founder decided in chat:

1. The consumer app's chat assistant is the agentic assistant described in the
   [MVEE](argus-minimum-viable-ecosystem-experience.md#agentic-ecosystem-direction-and-sequence),
   a goal-to-action assistant for personal and household finances in the style of
   the founder's cited references (Meta Muse and similar assistants). What the
   earlier Argus research and backtest chat did is not the target experience of
   the consumer app.
2. The old code, services, prompts and gates **stay until the founder decides to
   remove them**. This decision removes, hides and changes nothing. It changes
   what the consumer assistant is meant to be, not the existing runtime.
   [MVEE section 7](argus-minimum-viable-ecosystem-experience.md#7-carry-forward-the-existing-argus-investment)
   is read together with this entry: existing capabilities stay until explicitly
   removed, and this entry does not remove any.
3. **Memory and voice are included in release 1.** This answers the inclusion
   question that #818, #826, #828, #829 and #831 left open. The master plan's
   "Researched, parked" voice row is superseded. Grok voice stays the selected
   provider, behind the server, per the October 4 provider lock.

What this makes required: the acceptance items those issues already wrote as
conditional on included memory or voice now apply. They are memory consent,
correction and forgetting controls reachable and persistent in release (#829,
#827); consent checked before any chat, document, memory or voice transmission
(#828); disclosure and microphone purpose audit covering voice and memory
(#831); and connected recall, consent-decline and forgetting journeys (#833).
No new requirement is invented here.

Still open, and not answered by this entry: which first jobs the assistant does in
release 1 (#818 and #826), and the consent scope and versioning policy (#828).
This entry does not authorize implementation, a model-instruction change, a paid
provider run, hosted activation or deployment. The #826 contract still precedes
#827.

## October 10, 2026: Business agent direction

The founder approved these points after two audits of the Business core flows:

- The roadmap captured evidence and then stopped. A record was not complete. One agent now carries each conversation to a complete draft.
- Version 1 talks only to the owner. The accountant answers in the web view.
- The model reads the message. The tools enforce permissions, approval, exact money and record-once rules.
- Reuse LangGraph, OpenRouter, the tool registry, WhatsApp intake, document jobs, money services and server flags. Jev and an MCP server are deferred.
- `main` stays as the Argus tribute. Cuadrao work branches from `codex/private-alpha-next`.
- "I paid with my own money" is recorded against an owner funds source. The accountant classifies it.
- Approval is a permission, not a fixed role. The business admin holds it and can grant it to an associate. An accounting firm gets it for each client through that client's grant. An action ledger shows who did each action, through which grant and for whom.
- The OpenRouter key caps AI spend. The founder names the models for each PR that makes model calls.
- The default currency is DOP. The reviewer can change it before sign-off.
- Build only what J1 to J3 need, then test with one real owner and one real accountant. Other work waits until real use asks for it.

The [Business agent execution spec](lanes/cuadrao-business-agent-execution-spec.md) owns the contract, the work order and the defaults. No decision is open.

## October 10, 2026 hosted Business beta and build grant

At 21:39 UTC, Lucas clarified that the customer milestone is a real production
system reachable over the internet, demonstrated behind the marketing demo.
A laptop-only demonstration does not satisfy it. Provenance is
`Sentinel_197f868cd67c8191806a86d8f425ea91`. At 21:41 UTC, he clarified an
invite-only web beta using existing tools, separate from Apple TestFlight.
Provenance is `Sentinel_3b97373fd34081918bde53aeecce4293`.

At 22:13 UTC, Lucas authorized the bounded hosted Business build, clean merges
to `codex/private-alpha-next` and staging only. Provenance is
`Sentinel_fc5880c0d93c8191abd96767711ff688`. The root coordinator owns the sole
merge slot and staging actions. This replaces the general implementation and
hosted hold only within that assigned Business flow. It does not authorize
main or production promotion, public signup, marketing or legal launch,
Apple TestFlight, or unrelated Consumer work.

The [execution manifest](argus-execution-board.md#business-hosted-invite-only-build-october-10-2026)
owns the current assignments, dependencies and pending action gates. The
[execution spec](lanes/cuadrao-business-agent-execution-spec.md) still owns
C0-first order and the larger J1 to J3 direction. The first customer proof
must join real owner messages to one traceable record visible to an authorized
accountant over the internet. It must preserve originals, visible unknown or
unverified facts, correction history and grant-scoped human approval.

"Pagué 850" is an illustrative J1 input, not a phrase to detect or the whole
acceptance set. Use varied ordinary transactions, factual follow-ups, uncertainty
and corrections through the typed interpreter and canonical tools. Judge saved
state and user behavior. Do not substitute literal reply matching, word lists,
regex intent gates or per-reply human wording approval for evaluations.

Controlled WhatsApp test-recipient access differs from public onboarding.
A hosted loop needs its permitted sender, verified callback and WABA subscription,
authenticated sender-to-Business link, and grant-scoped readback. #941 still owns
its remaining activation and policy prerequisites. A simulated transport or old
tunnel does not prove that loop or authorize a callback cutover.

At 22:22 UTC, Lucas approved the existing Cuadrao Render workspace
`tea-d5rdkfk9c44c73e7a1ig`. Provenance is
`Sentinel_6aaf381568a88191b21c0240807c0f52`. His runtime direction replaces
the older configured mix. Favor `anthropic/claude-haiku-5.5`,
`openai/gpt-6-luna-pro` and `deepseek/deepseek-v4.1-flash`. Use Grok only
when needed. Prioritize the fastest reliable choice; he identified GPT Luna
Pro as the slowest candidate. The coordinator verified all three exact IDs
in OpenRouter's public catalog with structured-output and tool support.
Catalog metadata does not prove runtime latency or authorize a paid call.

A later continuation names Grok 4.3 as the first evaluation judge. Provenance is
`Sentinel_70caa32aa180819187d0ffaaf50e6bd9`. Do not make Astra development
runtime or judge API calls. A future paid-tier Astra option is hypothetical.
Codex coding agents use a separate subscription; their model names do not
select a runtime provider. The named runtime configuration remains replaceable.
Do not turn model selection into a new model-platform build. Calibrate the
judge with known-good and known-bad cases. Retain deterministic saved-state
assertions, so same-model agreement is never the sole proof of correctness.

At 22:26 UTC, Lucas approved a $5 total limit for this test run only.
Provenance is `Sentinel_dadf8d7f1e70819182eb7974f221a5fd`. He requested
identification of the development key before setting the overall development
spending limit. At that checkpoint, the limit was awaited and the coordinator
held live calls. The 22:32 UTC continuation below supersedes that run cap and
spending hold.

Grok 4.3 remains the first judge. Sonnet 5.5 is a possible stretch choice only
when a demonstrated need and fresh confirmation justify it. It is not an
automatic fallback. No Astra development runtime or judge API call is approved.

The coordinator interprets the existing one-owner, one-authorized-accountant,
one-Business-at-a-time milestone as a direct named-accountant grant for the
first bounded flow. This is implementation sequencing under existing authority,
not a new founder decision. Full firm-to-human delegation does not gate that
first acceptance. Preserve L11's firm-delegation requirement for later work;
it is not claimed complete. Do not invent a firm identity for the pilot.

Synthetic grants in isolated tests are authorized. Creating a real persistent
grant still requires the actual business's authorization and the named
accountant's scoped setup. The agent never holds approval permission.

At 22:32 UTC, Lucas authorized the existing development
`OPENROUTER_API_KEY` until its allowance is exhausted or it expires.
Provenance is `Sentinel_c52a9cf3b5308191b363e9c59f5993fa`. This supersedes
the $5 test-run cap and the hold for an overall development spending limit.
Use this existing development key only. Do not swap in a registered or guest
key, rotate credentials or expand the authorization to another key.

The coordinator's safe provider read reported total usage of $227.432355357.
Subtracting that from the authorized $300 ceiling gives a conservative
$72.567644643 remaining allowance before concurrent usage. The key expires at
`2026-10-12T02:21:00Z`. This is an operational snapshot, not a new constant.
The provider's larger monthly-remaining figure is not the authorized allowance.
The root coordinator alone coordinates live calls, reservations, concurrency
and token bounds. Refresh usage before calls and account for outstanding work.
All calls, judges, fallbacks and retries consume the same allowance. Use only
synthetic data. Stop when the conservative allowance is exhausted or the key
expires. Do not infer unlimited spend or an automatic reset of authorization.

Grok 4.3 and the earlier named runtime candidates retain their scope. No Astra
runtime or judge API call is approved. Sonnet 5.5 still needs demonstrated need
and fresh confirmation. No live call has occurred at this documentation
checkpoint because C0, runtime and evaluation readiness are still incomplete.

Tonight's target is online verification, contingent on the build, staging web
setup and candidate acceptance. It is not a readiness promise. The existing
staging-only deployment grant remains. New costs or access expansion need
concrete scoped confirmation. No secret change, real customer-data transmission
or persistent tester grant follows from this record. Named testers and real
grants still need actual business authorization and scoped setup.
