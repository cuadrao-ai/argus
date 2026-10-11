# Argus documentation authority

**Updated:** September 29, 2026. Private iPhone direction and financial-loop landing.
**Business assignment reconciled:** October 10, 2026. See the hosted Business
decision and assignment below. The September mobile lock retains its scope.
Current delivered work, remaining scope and action authority live in the
[execution manifest](specs/argus-execution-board.md), not in this ownership guide.
**Purpose:** Help an agent distinguish approved product direction, existing technical contracts, historical rationale, and authorized implementation work.

## Start here

1. Read [AGENTS.md](../AGENTS.md) for repository, safety, review, and delivery rules.
2. Read [PRODUCT.md](PRODUCT.md) for the product overview and the boundary between the existing Alpha and the approved pivot.
3. Read the [minimum viable ecosystem experience (MVEE)](specs/argus-minimum-viable-ecosystem-experience.md) for the approved audience, surfaces, ingestion, loop, household collaboration, and open decisions.
4. Read [ARCHITECTURE.md](ARCHITECTURE.md), [API_CONTRACT.md](API_CONTRACT.md), [DATA_MODEL.md](DATA_MODEL.md), and [DESIGN.md](../.agent/designs/argus/DESIGN.md) before relevant technical or UI work. Their existing contracts are not replaced by experience prose.
5. Read the [private iPhone execution manifest](specs/argus-execution-board.md) for
   current landed work, authorized actions, dependencies, ownership and acceptance.
6. Read the explicitly assigned package or slice. For a Wave 1 assignment, start with [its README](specs/wave-1/README.md) and the package's existing gates. A roadmap or brainstorm does not assign work by itself.

For Business work, read the [hosted beta and build grant](specs/argus-decision-log.md#october-10-2026-hosted-business-beta-and-build-grant)
and the [current assignment](specs/argus-execution-board.md#business-hosted-invite-only-build-october-10-2026)
before interpreting a dated hold. That assignment is a bounded exception for
Business integration and staging. It does not restart Consumer mobile work,
authorize Apple TestFlight or change public signup or marketing publication.

## One owner per kind of decision

| Question | Owner | Boundary |
| --- | --- | --- |
| What is Argus becoming, for whom, and how should it feel and work? | [MVEE](specs/argus-minimum-viable-ecosystem-experience.md) | Approved experience, not a shipped-feature inventory or technical implementation specification |
| How does that relate to the existing product? | [PRODUCT.md](PRODUCT.md) | Current product overview and explicit existing-capability contracts; verify actual availability against code/release evidence |
| Which founder decisions changed, and when? | [Decision log](specs/argus-decision-log.md) | Decision provenance and links; detailed requirements remain with their owner |
| What architecture, payloads, and persistence contracts apply? | Architecture, API contract, and data model docs above | Existing system contracts/technical intent and the [locked interface stacks](ARCHITECTURE.md#approved-platform-direction); some statements describe targets, not proof of implementation |
| What visual and interaction conventions apply? | [Argus web guide](../.agent/designs/argus/DESIGN.md) and [Cuadrao native guide](../.agent/designs/cuadrao/DESIGN.md) | Each owns its named platform. Cuadrao rules cover preview and connected native adoption; they do not claim implementation. MVEE owns product behavior, while the execution manifest owns status and remaining work. |
| What brand and design direction applies to the new business website? | [Cuadrao for business working guide](../.agent/designs/cuadrao-business/DESIGN.md) | Owns the approved Business and Personal marketing presentation, founder note, and illustrative examples. The [website delivery record](reports/2026-10-07-cuadrao-website-integration.md) owns integration evidence; the [launch record](reports/2026-10-07-cuadrao-marketing-launch.md) owns launch status. The independent `marketing/` package's [forms contract](specs/cuadrao-marketing-forms-contract.md) and [launch runbook](runbooks/cuadrao-marketing-launch.md) own its endpoints, data, release settings and rollback. It does not establish Business application or consumer-app availability. |
| What is the Business agent build order, from WhatsApp conversation to accountant package? | [Business agent execution spec](specs/lanes/cuadrao-business-agent-execution-spec.md) | Founder-approved direction (October 10, 2026). Owns the agent contract, the work streams, the gap register and the journey acceptance for Business core flows 1 to 7 (tracker [#942](https://github.com/lagarcess/argus/issues/942)). The connected flow spec keeps its product scope. `API_CONTRACT.md` and `DATA_MODEL.md` keep endpoint and persistence truth. It claims no built behavior. |
| What is the connected Business workflow and first offline fiscal-engine plan? | [Connected Business flow](specs/cuadrao-business-connected-flow-spec.md) and [E0 implementation plan](specs/cuadrao-business-e0-implementation-plan.md) | Founder-approved design and task-by-task review plan. Business owns implementation when Lucas coordinates it. Consumer retains shared migration and release ownership; Marketing retains its separate launch. P0 source verification remains open. Publication proves no runtime capability or live fiscal authorization. |
| What is an agent authorized to build now? | Explicit assignment and its scoped package/spec | MVEE approval does not assign every feature, unlock stages, or authorize provider integrations |
| What is next, who owns it, and what counts as done? | [Private iPhone execution manifest](specs/argus-execution-board.md) | One execution map; states and evidence links do not authorize a restart, merge or deployment |
| How is work reviewed and released? | AGENTS.md, [CI/CD discipline](specs/private-alpha-ci-cd-sota.md), [launch runbook](PRIVATE_LAUNCH_RUNBOOK.md), [manifest template](release-manifests/TEMPLATE.md) | Existing evaluation, privacy, branch, merge, and deployment gates remain in force |
| What evidence or thinking informed a direction? | Linked research and historical strategy docs | Inputs and provenance, not independent scope authority |

## Constitution source material

The [October 4 Cuadrao constitution package](research/cuadrao-constitution-2026-10-04/README.md)
preserves three founder-supplied originals and the settled conflict dispositions.
Its principles index links to the adopted rules in the existing canonical owners.
The originals remain supporting input, including their superseded proposals.
This package does not assign implementation or add launch gates.

## What is settled

The MVEE is the single detailed owner of the approved ecosystem. Its section 1.1 locks the audience and near-term financial emphasis; section 12 includes partner invitations and personal/household views. Sections 3–5 define surfaces and information ingestion. Sections 8–9 distinguish boundaries and open decisions. Section 11 defines pain-point coverage and the reinforcing loop.

The product remains one connected Argus experience that carries forward existing chat, calculations, research, and historical comparisons. These capabilities are not gated behind debt repayment. The design direction retains the Argus visual identity. Native iOS/Android plus web and their [interface stacks](ARCHITECTURE.md#approved-platform-direction) are approved. The September [MVEE delivery lock](specs/argus-minimum-viable-ecosystem-experience.md#12-private-iphone-delivery-the-immediate-finish-line) prioritizes the physical iPhone over the internet, preserves the existing web, freezes the general web remake, and records the deferred consumer agentic runtime. The later [hosted Business decision](specs/argus-decision-log.md#october-10-2026-hosted-business-beta-and-build-grant) and its bounded assignment govern that Business flow. The [execution manifest](specs/argus-execution-board.md) owns the proposed sequence and unassigned work. Detailed contracts still need their scoped implementation assignments.

“Locked” means founder-approved direction. It does not mean implemented, validated market demand, a final schema, a model instruction change, or permission to deploy.

The current mobile reference is the [September 28 design lock](reports/mobile-design-lock-2026-09-28.md).
It succeeds the earlier September 27 sketch carried by PR #714. Read its archive
and current MVEE/DESIGN together; historical screenshots do not reopen later
decisions. The [recording response](specs/lanes/financial-recording-decision-response.md)
distinguishes settled experience from remaining recommendations for PR #724.

## Carry forward, change explicitly

Argus has one evolving product and one set of technical owners. The MVEE
defines approved experience changes; it does not reset the production feature
inventory. Existing behavior and gates remain valid unless a specific approved
change replaces them. A feature omitted from the MVEE is not implicitly retired.

Distinguish a contradictory product mandate from a temporal difference:
“this feature is hidden today” can coexist with “enable it in the next push.”
Keep current availability and its approved transition together in
[PRODUCT.md](PRODUCT.md#current-production-availability-and-planned-changes),
and link there from other documents. Do not delete accurate production truth
merely to make an experience specification read as if it has shipped.

## What remains technical or undecided

Do not infer these from a polished demo or the MVEE:

- Registration/conversion mechanics and enforcement of the [locked guest access boundary](specs/argus-minimum-viable-ecosystem-experience.md#guest-access-and-registration); guest financial persistence is no longer an open product choice.
- Financial capabilities beyond the landed [account first slice](specs/lanes/financial-accounts-first-slice.md), [local financial loop](specs/argus-execution-board.md#pr-745-integration-landing), [Household membership API](specs/argus-execution-board.md#pr-763-integration-landing), [Household native consent/activity](specs/argus-execution-board.md#pr-766-integration-landing), and [shared Household planning](specs/argus-execution-board.md#pr-773-integration-landing), including unsupported historical-data conversion. Existing account/activity/reconciliation API and money contracts remain authoritative; do not redesign them from vision prose.
- Household physical-iPhone/internet delivery, external invitation delivery, hosted migration/enablement, and Business/Custom lifecycle beyond the default-off membership + native consent/activity + shared planning package ([PR #763](specs/argus-execution-board.md#pr-763-integration-landing), [PR #766](specs/argus-execution-board.md#pr-766-integration-landing), [PR #773](specs/argus-execution-board.md#pr-773-integration-landing)). Consent/visibility, membership/authorization, bounded native financial projection, and shared Plan consumers are settled for that package; those remaining surfaces are not.
- API routes, action schemas, chat-to-record integration, runtime state ownership, jobs, and event contracts for the new surfaces.
- Voice integration contracts under the [selected voice/chart direction](ARCHITECTURE.md#voice-and-chart-direction), OCR providers, supported file formats/institutions, secure bank-access design, wallet/device capabilities, and automatic-acceptance policies.
- Scheduling, external-fact monitoring, notification delivery channels, and associated data access.
- Native client architecture beyond the locked interface stacks: shared contracts/components, authentication, local storage/offline synchronization, supported OS/device ranges, delivery order, rollout flags, acceptance gates, and work packages for the full ecosystem.

Before implementing a change in these areas, define its bounded technical contract and acceptance conditions using the existing system as the starting point. Continue unrelated authorized work; escalate a concrete unresolved product choice or conflicting package instead of inventing it.

## Older documents: disposition

| Document | Status after this reconciliation | How to use it |
| --- | --- | --- |
| [Pivot strategy](specs/argus-pivot-strategy.md) | Historical strategic proposal; conflicting experience direction superseded | Preserve rationale and research; do not promote every proposal into scope |
| [Answers that stay true](specs/argus-answers-that-stay-true-roadmap.md) | Historical product board plus carried-work/release reference | Saved-answer ideas may support the MVEE; preserve unresolved issues and operational rules without treating its brainstorm as today's assignment |
| [Private Alpha Next decision memo](specs/private-alpha-next-decision-memo.md) | Historical strategic/technical rationale | Follow its compatibility pointer to archived technical context for a named slice; its old product framing does not override the MVEE |
| [Wave 1](specs/wave-1/README.md) | Existing package specifications; experience conflicts require reconciliation | Preserve assigned work, dependencies, review gates, and safe completed work. Do not silently cancel, expand, or rewrite packages |
| [Private Alpha Next roadmap](specs/private-alpha-next-roadmap.md) | Superseded P2 history and technical reference | No new assignments from its old queue |
| [Old active-roadmap pointer](specs/argus-active-roadmap.md) and [grounded-finance pointer](specs/argus-grounded-finance-roadmap.md) | Historical redirects with a current authority pointer | Follow this document for current ownership instead of chaining stale active-board claims |
| [Social/market research mapping](research/2026-09-26-dr-latam-finance-painpoints-mvee.md) | Supporting research and decision history | Approved choices live in the MVEE; raw recommendations and metrics do not become requirements automatically |

Retired strategy narratives now live in `docs/archive/`, with compatibility pointers at their former paths. Their issue references and dated reasoning are preserved. Active product and design statements are rewritten in place; current readers need not mentally override a second product identity. Technical endpoint, entity, and runtime contract sections remain unchanged. Date-specific production claims in archives are historical snapshots.

## Wave 1 reconciliation boundary

The private iPhone execution manifest supplies the current delivery map and records explicit assignments and landed work. It does not itself restart Wave 1 or any stopped lane. Applicable technical and release gates still apply when a package is explicitly assigned; historical package sequencing does not override current founder authority or the named lane's priority.

In particular, Wave 1's two-audience landing, limited navigation, hidden account/upload/budget surfaces, and earlier onboarding assumptions are package-era choices, not permanent limits on the ecosystem. A temporary shipping subset may still be appropriate, but the assigned spec must say so explicitly. Before implementing a conflicting experience requirement, reconcile that package with the founder-approved MVEE and record what is retained, revised, or deferred. Do not expose unfinished surfaces just because they are approved in the vision.

Safety fixes, instrumentation, and existing calculator work are not discarded by a pivot. Assess actual semantic overlap with the assignment; unchanged applicable safeguards continue to apply.

## Current implementation batch (September 28, 2026)

**Historical batch, stopped and superseded.** This heading remains as a stable
link for earlier decisions. The founder subsequently stopped all lanes, froze
web work, closed the research/proof PRs and requested the private iPhone plan.
The current owner is the [execution manifest](specs/argus-execution-board.md).
It does not dispatch work or carry forward an old merge grant to new PRs.

The prior [#727 coordination handoff](https://github.com/lagarcess/argus/pull/727#issuecomment-5878051744)
assigned the account-backend, iPhone, Android, web and chart owners. Preserve their
branches and changes for explicit salvage, not automatic resumption. Historical
batch wording is retained in [integration before this lock](https://github.com/lagarcess/argus/blob/de8729843b726a3fd03210cebcedede5e44227c8/docs/DOCUMENTATION_AUTHORITY.md).

[#735](https://github.com/lagarcess/argus/pull/735) landed the default-off account
backend. [#738](https://github.com/lagarcess/argus/pull/738) and
[#739](https://github.com/lagarcess/argus/pull/739) landed local native session
integration. Those are reusable components, not proof of the private iPhone
outcome. The manifest records the inspected starting point and incomplete work.

[#723](https://github.com/lagarcess/argus/pull/723),
[#724](https://github.com/lagarcess/argus/pull/724),
[#725](https://github.com/lagarcess/argus/pull/725) and
[#726](https://github.com/lagarcess/argus/pull/726) are closed unmerged as of this
publication. Earlier instructions to finish or land them are historical. Reuse
relevant findings selectively; do not restart their review or implementation loops.

### Founder deferral

The [MVEE holds](specs/argus-minimum-viable-ecosystem-experience.md#16-holds-later-work-and-unresolved-decisions)
own deferred work. Revenue, pricing, billing, new growth sharing and new ecosystem
analytics do not block core private delivery. Existing operational and cost
safeguards remain. The prior pause on broad user trials does not prohibit the
explicitly requested founder dogfooding and physical-phone demonstrations.

### Infrastructure and publication boundary

The [MVEE infrastructure decision](specs/argus-minimum-viable-ecosystem-experience.md#14-infrastructure-and-cost-constraints)
locks reuse of Render, the current Supabase project and current plan, existing
identity and a modular backend. It does not authorize hosted migrations, settings,
paid providers or deployment. Existing API/data/security contracts remain in
force; reconcile their concrete amendments within assigned implementation work.

The original documentation-only publication did not authorize implementation.
Subsequent founder grants and their completed outcomes are recorded in the
[execution manifest](specs/argus-execution-board.md). Consult that current state
before acting; this ownership guide neither grants nor revokes restart, merge,
preview, deployment or spending authority.

## Handoff rule

An implementation handoff should identify the MVEE section it serves, its bounded deliverable, current technical owners, unresolved decisions, allowed/no-touch files, and evidence required. It must distinguish founder-locked direction from technical contracts and verified completion. Start from the manifest and link to MVEE requirements instead of copying another scope list.
