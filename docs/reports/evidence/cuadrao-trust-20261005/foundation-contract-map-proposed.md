# Cuadrao shared foundation contract map

Planning evidence at integration 875de09ac2115acec42e09060b92878aa5f18eff, October 5, 2026. Read-only investigation. This document proposes contracts and owners. It grants no runtime, migration, provider or hosted authority. Root is the release captain and sole integration merge queue.

## Authority and scope

AGENTS.md and docs/DOCUMENTATION_AUTHORITY.md distinguish settled product direction, technical contracts and implementation assignment. Read PRODUCT, MVEE, ARCHITECTURE, API_CONTRACT, DATA_MODEL, Cuadrao DESIGN, execution board, master plan B2, decision log and frozen lane handoff. Issue snapshots #818, #819, #820, #805, #828 and #826 were supplied by root.

Consumer launch includes Personal and Household. Business/fiscal/Gmail do not become consumer requirements. Providers and reuse are settled. OpenRouter supplies chat and vision, Perplexity supplies finance search, Grok is the planned voice provider. LangGraph, existing Mem0/pgvector, scoped on-demand context and Render Workflows are the chosen foundations. Exact first-release chat jobs and memory/voice inclusion remain unresolved in #818/#826. The space migration precedes TestFlight, but its detailed model is still open. Master-plan B2 remains explicitly proposed.

## One owner per fact

| Fact | Canonical owner at baseline | Readers and dependent work | Exclusive implementation owner |
| --- | --- | --- | --- |
| Registered person and session | auth.users/profiles and existing session/identity services | Native session, social flags, deletion actor | Identity-safety owner. |
| Household membership incarnation and active access | households, household_members; households.version owns authorization generation; admin_user_id owns administrator authority | Household lifecycle, financial adapters, shared plans, consent context, deletion and future scoped jobs | Shared permissions owner for #819. Root must assign this writer before implementation. |
| Account ownership | financial_accounts.user_id | Recording, Personal RLS, grants, Search, documents destination and deletion re-keying | Shared ownership/migration owner for #819, serialized with permissions and deletion. |
| Account sharing and edit rights | household_account_grants with membership incarnation and revocation | household/access.resolve, require_edit, financial adapter | Same #819 permissions owner. Membership never implies sharing. |
| Plan definition and financial history | Existing planning definitions, canonical Money activities/revisions and financial_plan_links | shared planning projection/progress, Home/Plan, deletion preserved history | Existing financial core owner, coordinated by root. |
| Shared plan visibility and contribution consent | household_plan_bindings, household_plan_participants and pinned retained revisions | Shared Planning, contributor reads and deletion | Same shared permission owner. Do not copy definition balances into bindings. |
| Former-member identity and deletion workflow | account_deletion/service.py plus deletion migration and household/deletion.py | Anonymous preserved contributions, debt archives, operator retry | Analytics-deletion owner controls shared deletion state. Deletion-recovery owns tests/runbook only. |
| Actual bilateral open balance | No canonical record found in the current SharedContribution/Responsibility contracts | Decision 17 closed line, active-total exclusion and settlement | New bounded accounting contract needs founder approval, then one financial/deletion writer. |
| Provider transmission permission | No shared authoritative versioned consent found; document draft holds extraction boolean | Chat, extraction, embeddings, sensitivity/classifier and retry dispatch | One consent-policy owner for #828. Root must assign this writer. |
| Permission to remember/use context | Existing memory_consent_actions, settings, confirmed memory_records and service policy | Memory proposal, retrieval, indexing and controls | Existing memory owner. Consent-policy owner integrates transmission permission without replacing memory semantics. |
| Current dispatch authorization | Existing subject/access owners, not queued job claims or screen state | Documents, model boundaries, memory and eventual workflow execution | Consent-policy owner composes shared authorization owner at dispatch. |
| Currency and primary preference | Canonical recording precision/currency and existing profile preference owner | Home, charts, plan contribution amount pairs | Currency owner separately assigned by root for #820. |
| Release inventory and public claims | Reachable code evidence plus frozen launch matrix | Legal draft, privacy manifests, App Store answers and handoff | Privacy-evidence writer reconciles claims after runtime changes. PR #781 owner remains legal-draft owner. |

## Existing permission model, traced

HouseholdService.transaction resolves current household and membership under the household row lock. SharedPlanningService.context then resolves allowed accounts through access.resolve and obtains canonical owner/account locks. require_scope binds a request to membership_id and expected_authorization_version. AccountAccess names original owner and edit permission. require_edit checks every dependent account and rejects mixed-owner execution. Personal account reads retain strict-owner access.

DATA_MODEL.md lines 1982-1993 and API_CONTRACT.md lines 7470-7475 explicitly make the existing household tables the only authority. Membership incarnation changes on rejoin. Adding space_memberships as another mutable Household membership store would break this contract unless all readers migrate and the original authority is retired in the same reviewed transition.

The locked household-permission-policy keeps accounts personally owned, makes sharing explicit, and revokes grants on leave/removal. Administration and record editing are separate. Acceptance never grants automatic account visibility, private document visibility, chat access or resharing.

## Consumer space options for decision

Option A adds an explicit spaces registry while preserving Household ownership and authorization semantics. Each registered person receives one Personal space. Each household container uses the existing households.id. Personal roots reference that registry but retain one original ownership fact until their bounded reader migration. Household membership, grant and generation checks derive from existing tables. Shared plan bindings continue to connect personally owned definitions under the already approved rules.

Option B implements the full proposed B2 root ownership change. Shared roots become household-owned; actor references become membership references. The existing Household authority must migrate into, or become, the canonical space-membership authority rather than remain a competing store. This changes personal-owner service/RLS rules, per-plan ownership, departure/handover and deletion placeholder behavior. It requires an explicit model lock and broader real-Postgres acceptance.

Recommendation for the immediate consumer step is Option A unless the founder explicitly requires household-owned roots now. It makes the space concrete without changing current sharing/deletion meaning. This recommendation is not a settled decision and cannot be reported as completing #819 until the founder agrees that it satisfies the before-TestFlight migration requirement. Business roles/retention remain excluded.

Founder question. Should consumer space migration preserve current personal root ownership plus Household grants, or should shared plan roots become owned by Household before TestFlight? Recommend preserve current semantics for the first consumer migration and stage root ownership changes only under an explicit bounded contract.

## Frozen former-member balance gap

The outcome is locked. Preserve an existing open amount and provenance; remove that closed amount from active totals; never call it paid or forgiven; settlement records a new authorized event. Locked copy is “Saldo con Exmiembro: $X (cerrado)” and “Balance with Former member: $X (closed)”. The handoff also locks debt-plan read-only archival as the exception to ordinary plan handover.

SharedContribution in planning_schemas.py lines 190-204 stores contributor, amount, applied amount, currency, date, purpose and original activity provenance. Responsibility at lines 179-187 stores an agreed planned amount for a period/occurrence/schedule/date. Neither specifies a creditor, debtor, receivable, debt acknowledgement or repayment obligation. planning_progress.summary lines 38-71 reduces actual and applied plan contributions. A difference between responsibility and contribution is therefore not established debt.

Do not calculate the frozen line by subtracting these fields. Do not hide preserved contributions from actual expense/history totals merely because their author is deleted. The closed-balance exclusion must apply to an approved interpersonal balance projection, while recorded financial facts remain unchanged.

Founder question. What constitutes an “open balance with” a member in today's product, and which canonical event establishes its amount and direction? Recommend an explicitly confirmed interpersonal obligation with immutable currency/amount and source revisions. A responsibility or contribution alone must not create one. Confirm whether an active plan participant with edit rights can mark it settled, or whether all active participants may do so. The existing wording “a member” does not settle viewer financial mutation rights. Settlement should acknowledge closure of that obligation without inventing a bank payment or altering original contributions unless a separate payment event is explicitly confirmed.

If such balances do not exist today, do not backfill a guessed balance or present missing as zero. Keep #805 and deletion activation gates open while independently landing approved identity/provider recovery fixes.

## Provider consent options for decision

Current document capture saves source bytes and drafts before extraction. upload holds a consent boolean; queue requires explicit true; resume checks draft.consent before extractor.extract. This preserves declined captures, but it does not represent withdrawal, disclosure version, named purpose/provider or current space generation.

The native ReleaseAIConsentView accepts a disclosure and callbacks. Its saved label is presentation, not evidence of server consent persistence. Memory enables approved categories and confirms canonical records, independently from transmission. Mem0MemoryProvider indexes confirmed text with infer=False and returns canonical IDs; query and projection invoke the injected embedder. personalization_memory_assessor calls a sensitivity classifier through OpenRouter. These are outbound personal-data paths even though Mem0 extraction is disabled.

Option A stores per-person provider-transmission consent with purpose/provider/disclosure-version and current allowed/declined/withdrawn state. Every call resolves that current policy plus current authorized source scope. Record-scoped document opt-in can remain a stricter prerequisite. Membership never grants permission for another member's private records. No existing document boolean or memory-use consent silently becomes accepted provider consent.

Option B stores independent consent on each space with each person's processing decision. This requires defining whose data a Household participant may authorize and whether consent from every data subject is needed. Membership/admin authority cannot answer that product/privacy choice by itself. It also complicates first-release Personal paths.

Recommend Option A with explicit Household disclosure limited to the data already authorized for that actor; default deny any undefined third-party personal-data scope. Founder must approve whether transmitting explicitly shared household records can proceed under the acting person's permission or requires each contributor's processing consent. Resolve this alongside #819, not in a low-level adapter.

Version recommendation is one named disclosure version tied to named processing purposes/providers. A material change requires fresh consent. Withdrawal blocks future calls and each retry; it cannot recall prior transmission. Already returned observations/drafts stay reviewable under source authorization. Policy controls future dispatch without rewriting financial facts or claiming provider deletion. Whether pending response results can be retained after withdrawal also needs an explicit rule. Recommend preserve already-dispatched results as a draft with visible processing history, while stopping undispatched follow-up work.

## First-release jobs and inclusion

#818/#826 still require bounded first read and proposed-write jobs. Recommend the first contracted read explain the user's currently authorized financial position/commitments. A proposed-write job can prepare a transaction or expected payment draft that uses existing commands only after explicit revision-bound confirmation. This is a proposed scope, not authorization to build the agentic rewrite in Trust.

Recommend leaving new connected voice and native semantic-memory use out of first consumer activation until their assigned privacy, interruption/relaunch and provider acceptance pass. Preserve existing foundations and existing Argus consumers. The founder must approve inclusion or deferral; a provider choice does not settle release availability.

## Verifiable delivery units

1. Land the approved #818 consumer matrix and selected #819/#828 contract in a documentation PR. Independent review checks every row against one owner and named gates. No status claim beyond planning.
2. Implement additive consumer space registry/backfill only after the model choice. Real Postgres proves registered-person uniqueness, existing identifier/history preservation, isolation and rollback/forward recovery. This does not switch financial RLS yet.
3. Migrate one root/reader family per PR. Account ownership and current grants must agree by derivation. Real Postgres proves revoked/rejoined member denial and denied mutations produce no protected effects. Reconcile deletion FK/non-FK census for each changed root.
4. Implement server provider-consent record and policy with deterministic deny/withdraw/version tests on real Postgres. This lands default-off until every included dispatch reader connects.
5. Integrate document dispatch including background resume and retries first. Preserve source/draft on refusal and prove no extractor call. Recheck consent immediately before dispatch, including after leases/interruption.
6. Integrate current chat and memory embedding/classifier entry points separately according to release inclusion. Mocked transport tests prove zero calls on deny and current authorized scope on allow. Existing consumer compatibility needs an explicit migration contract; do not activate a new global policy that silently disables retained web consumers.
7. Implement frozen-balance records/read/settle only after the financial source and settle authorization contract. Real Postgres proves freeze and event creation are atomic/retry-safe, amounts/currency/provenance unchanged, active balance exclusion and all other financial totals unchanged. Include viewers, revoked memberships, interrupted and duplicate commands.
8. Final privacy owner reconciles exact reachable behavior, consent wording, manifests and legal draft recommendations. No policy publication or claim of provider/deletion/device completion.

One integration queue reconciles latest integration and semantic overlap before each merge. Use expected-head guarded merges, exact-head CI and independent review. Every unit preserves phone and hosted acceptance gates. Sequence Work into Verifiable Units changed this plan from one security rewrite to independently tested roots and dispatch adapters. Model the Domain changed the proposal from extraction booleans and inferred contribution debts to explicit consent states and an acknowledged accounting event.

## Proof limits and cleanup

This planning worker ran only read-only file searches and source inspection. No runtime test was run and no local/provider/device pass is claimed. It started no server, simulator or child process and changed no shared branch, database, hosted setting or existing document. The captain must record current remote integration again before any implementation or READY claim.

## Captain ownership assignment

The captain owns the single integration merge queue and unresolved contract decisions. Ownership is assigned to roles so a fresh agent can take a fix round without creating another writer.

| Shared boundary | Single accountable owner | Current disposition |
| --- | --- | --- |
| #818 release matrix and retained jobs | Captain | Proposed inclusion decisions pending founder response. |
| #819 ownership, membership, grants and authorization generation | Captain, shared permissions role | Existing canonical household contract preserved; migration model pending. No competing membership store. |
| #820 primary currency and profile writes | Currency role, PR #853 | Independently reviewed; reconciliation in progress. |
| #820 paired transfer amounts and shared denomination eligibility | Money role, PR #854 | Independent review found incorrect public amount after a correction; fresh fix owner assigned. |
| Identity and SessionController | Identity role | #844 reviewed release guard first; remaining shared session changes serialized after #853. |
| Deletion state, provider outcomes and commands | Deletion role, PR #847 | Default-off provider implementation reviewed. Recovery proof #846 owns tests/runbook only. |
| #805 former-member obligation | Captain, accounting contract role | Canonical obligation source and settlement rights unresolved; dependent implementation blocked. |
| #828 transmission consent policy | Captain, consent policy role | Proposed policy awaiting scope/version/household decisions; no parallel rule introduced. |
| Evidence, legal recommendations and final claims | Captain, documentation role | #845 inventory owner; #781 retains legal drafts. Publication remains gated. |

Sequence Work into Verifiable Units keeps each contract change and its proof in a separate PR. Existing personal ownership, household grants and memory-use permission remain authoritative until an approved migration explicitly replaces them.
