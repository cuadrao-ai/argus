# Cuadrao documentation authority

**Updated:** November 1, 2026.

This guide separates current Business web product direction, technical contracts, historical context and authorized work.

## Start here

1. Read the [README](../README.md) and [pilot review spec](specs/cuadrao-pilot-review-spec.md) for current product and pilot behavior.
2. Read [AGENTS.md](../AGENTS.md) for codebase facts and safety rules.
3. Use [PRODUCT.md](PRODUCT.md) for the short product overview.
4. Read the relevant technical contract and the explicitly assigned brief before changing behavior.

The current brief bounds the work. A spec, roadmap, old assignment or green test does not authorize implementation, spending, hosted changes or deployment.

## One owner per kind of decision

| Question | Owner | Boundary |
| --- | --- | --- |
| Who is Cuadrao for, and what does it do today? | [README](../README.md) and [product overview](PRODUCT.md) | Small businesses and their accountants, through the web app |
| How should Bandeja, the dossier and month close work in the pilot? | [Pilot review spec](specs/cuadrao-pilot-review-spec.md) | Approved pilot behavior and acceptance criteria, not proof that every item has shipped |
| What architecture, payloads and persistence contracts apply? | [Architecture](ARCHITECTURE.md), [API contract](API_CONTRACT.md), [API schema](api/openapi.yaml) and [data model](DATA_MODEL.md) | Verify the relevant contract against code. Legacy personal and chat sections do not override current product scope. |
| What are the month-close data and API rules? | [Month-close contract](contracts/business-month-close.md) | Request and response shapes, settlement grain, open items and sin comprobante rules. The pilot spec owns the review experience. |
| What visual and interaction rules apply to the Business web app? | [Business web app guide](../.agent/designs/cuadrao-business-app/DESIGN.md) | Read with the pilot spec. The guide still references the [locked colours](../.agent/designs/cuadrao/DESIGN.md#locked-colours--october-18-2026) in the legacy native guide. This does not restart mobile work. |
| What design and release contracts apply to the marketing site? | [Website guide](../.agent/designs/cuadrao-business/DESIGN.md), [forms contract](specs/cuadrao-marketing-forms-contract.md) and [launch runbook](runbooks/cuadrao-marketing-launch.md) | Apply to the remaining Business site. The former Personal page and signup routes are removed. Dated launch reports remain evidence for their recorded revision. |
| Which flows have been walked, and when? | [Core flows](CORE_FLOWS.md) | Dated evidence only. Old personal or chat rows do not establish current scope. |
| Which decisions and work led here? | [Decision log](specs/argus-decision-log.md) and [execution history](specs/argus-execution-board.md) | Historical decisions, assignments and evidence. Older private iPhone and chat plans are not current direction. |
| What may an agent build now? | The explicit assignment and its scoped spec | The brief names allowed files, acceptance and action authority. No historical assignment grants a restart. |
| How is work reviewed and released? | [PR template](../.github/pull_request_template.md), [CI/CD discipline](specs/private-alpha-ci-cd-sota.md), [launch runbook](PRIVATE_LAUNCH_RUNBOOK.md) and [manifest template](release-manifests/TEMPLATE.md) | Evaluation, privacy, branch, merge and deployment safeguards still apply. Documentation alone grants no release authority. |
| Which legal documents may be published? | [Legal open questions](legal/OPEN_QUESTIONS.md) | Legal drafts require review before publication. They are not published policy. |

## Current product boundaries

Only the owner role can approve records. The pilot accountant holds the Dueño seat. Nothing is approved automatically.

The personal iOS and Android apps are archived. Chat is being removed. Guest mode is gone from the Business app. Remaining interpreter code keeps the model-facing text safeguards in [AGENTS.md](../AGENTS.md).

The pilot spec excludes archive, the invoice cascade, USD rate handling, and email and WhatsApp changes. Do not infer new decisions for them.

<a id="what-remains-technical-or-undecided"></a><a id="founder-deferral"></a><a id="current-implementation-batch-september-28-2026"></a>

## Older documents: disposition

| Document | Status | How to use it |
| --- | --- | --- |
| [Minimum viable ecosystem experience](specs/argus-minimum-viable-ecosystem-experience.md) | Historical personal and household direction | Preserve the rationale. Its mobile, chat and guest plans do not govern the Business pilot. |
| [Business agent execution spec](specs/lanes/cuadrao-business-agent-execution-spec.md) | Historical agent and chat build plan | Reuse only relevant technical context under an explicit brief. It does not restore chat or assign its former work streams. |
| [Connected Business flow](specs/cuadrao-business-connected-flow-spec.md) and [E0 plan](specs/cuadrao-business-e0-implementation-plan.md) | Earlier Business design and implementation plans | Read their technical context alongside the current pilot spec and contracts. Their old ownership and build order are not a new assignment. |
| [Execution board](specs/argus-execution-board.md) and [mobile design lock](reports/mobile-design-lock-2026-09-28.md) | Dated delivery and design history | Preserve evidence. The private iPhone finish line no longer sets product direction. |
| [Constitution source package](research/cuadrao-constitution-2026-10-04/README.md) | Supporting input and decision history | Originals include superseded proposals. They do not assign work or add launch gates. |
| [Pivot strategy](specs/argus-pivot-strategy.md), [answers roadmap](specs/argus-answers-that-stay-true-roadmap.md), [decision memo](specs/private-alpha-next-decision-memo.md) and [roadmap](specs/private-alpha-next-roadmap.md) | Historical strategy and technical context | No new assignments from their old queues |
| [Wave 1](specs/wave-1/README.md) | Historical package specifications | Keep relevant technical safeguards. Do not resume old packages without an explicit assignment. |
| [Active-roadmap pointer](specs/argus-active-roadmap.md) and [grounded-finance pointer](specs/argus-grounded-finance-roadmap.md) | Historical redirects | Use this authority map for current ownership. |
| [Pain-point research](research/2026-09-26-dr-latam-finance-painpoints-mvee.md) | Supporting research | Recommendations do not become requirements automatically. |

Historic reports stay in place. Their release claims describe the recorded revision, not today's hosted state. Archived direction does not remove privacy, authorization, money or data safeguards from remaining code.

## Handoff rule

Name the current spec section, deliverable, technical owners, allowed files, open decisions and required evidence. Distinguish approved behavior from verified completion. Report conflicts instead of inventing product choices.
