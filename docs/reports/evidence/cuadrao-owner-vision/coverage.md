# Business vision coverage

This matrix checks website coverage. It is not a release manifest. The Business product is in development. Interactive demonstrations use fictional records. Shared consumer capabilities do not establish Business availability.

Sources read on October 6, 2026:

- **MVEE-B**: the supplied `/Users/garces/.codex/worktrees/baaf/private-alpha-next/docs/specs/argus-minimum-viable-ecosystem-experience.md`.
- **MVEE-C**: [current MVEE](../../../specs/argus-minimum-viable-ecosystem-experience.md). Its October 4 recurring and category sections are newer than the supplied version.
- **Plan**: [Cuadrao master plan](../../../specs/cuadrao-master-plan.md). Proposals are not founder locks or shipped capabilities.
- **Decisions**: [decision log](../../../specs/argus-decision-log.md), including October 4 launch, currency, recurring and October 6 assistant decisions.
- **Brief**: `/tmp/cuadrao-business-website-brief.md`.

The implemented page covers all 25 rows below. “Demonstrated” means a working local interaction with fictional records, not a shipped Business capability. “Explained” means copy or FAQ coverage, not a working product feature.

| Capability | Source lines | Truthful status | Required page treatment | Implemented destination |
| --- | --- | --- | --- | --- |
| Cash, accounts, income, expenses, debts and changes | MVEE-B 278–329; Plan 852 | Planned Business adaptation | Money summary, dated account coverage and underlying movements | Demonstrated: `#money-tab-position`, `#money-tab-movements` |
| Separate currencies | Decisions 418–435 | Approved rule | DOP and USD separately; no converted total | Demonstrated: DOP/USD controls in `#money-panel` |
| Transfers, refunds, corrections and reconciliation | MVEE-B 323–370, 781–794; Plan 852 | Planned adaptation | Supporting money detail; transfer is not revenue | Explained: FAQ boundary answer |
| Budgets | MVEE-B 604–627 | Planned adaptation | Recorded expense against spending limit | Demonstrated: `#plan-tab-budgets` |
| Savings goals and debt plans | MVEE-B 608–642 | Planned adaptation | Reserve progress and a debt commitment; actual versus expected | Demonstrated: `#plan-tab-budgets`, reserve and equipment debt |
| Upcoming commitments and expected income | MVEE-B 309–313, 618–642; MVEE-C 715–729 | Shared approved direction; Business planned | Dated timeline with expected collection distinctly unpaid | Demonstrated: `#plan-tab-upcoming` |
| Cash outlook and what-if | MVEE-C 735–751 | Planned adaptation | Schedule-based projection, delayed-payment scenario, no actual balance mutation | Demonstrated: `#plan-tab-outlook`, two dated scenarios |
| Manual and typed entry | MVEE-B 694–710; Plan 246 | Planned Business capture | Reviewable proposal and manual alternative | Demonstrated: `#work-tab-capture`, Manual/Texto selectors and editable review |
| Voice capture and conversation | MVEE-B 712–732; Decisions 552–566 | Consumer release inclusion locked; Business planned | Explicit planned label; no fake live microphone | Explained with transcript example: Voz/Voice selector; no microphone |
| Photos, files and statements | MVEE-B 734–755; Plan 226, 243 | Planned; exact supported formats unverified | Source and draft review; no universal parser claim | Photo/file proposal demonstrated; statements and unsettled formats explained in input FAQ |
| Categories, uncertain data and duplicates | MVEE-B 738–749; MVEE-C 753–775 | Planned | Editable review and existing receipt linking without duplicate expense | Category review demonstrated in Capture; existing-record linking in `#expense-tab-linked` |
| Assistant answers and proposed actions | MVEE-B 548–558, 576–596; Decisions 565–566 | Planned; exact first jobs unresolved | Record-backed answer, editable proposal, confirmation in example | Demonstrated: `#work-tab-assistant`, source link and editable reminder |
| Search and return to source | MVEE-B 644–654; Plan 186 | Planned adaptation | Find a sample record, inspect it, return without losing query | Demonstrated: `#work-tab-search`, detail and query-preserving return |
| Reminders and useful updates | MVEE-B 658–666 | Planned adaptation | Explain an upcoming payment or budget threshold and link to action | Demonstrated: `#work-tab-updates`, dated payment and missing-document destinations |
| Personally paid business expense | Plan 225, 244 | Planned proposal; ownership contracts unresolved | Distinct linked personal and business entries | Demonstrated: `#money-tab-separation` |
| Owner contributions and withdrawals | Plan 225, 244 | Planned proposal | Cash movement distinct from sales and expenses | Demonstrated: signed effects in movements and separation views |
| Customer context | Plan 227, 854 | Planned collections-focused records | Customer, sale, payment and remaining balance together | Demonstrated: `#la-idea`, shared named customer/invoice/payment |
| Quotes and non-fiscal drafts | Plan 228, 245, 855 | Planned | Supporting customer chapter; no fiscal validity claim | Explained: sales/documents FAQ |
| Partial payments, matching, allocation and fees | Plan 229, 856 | Planned | Preserve invoice arithmetic and explain allocation scope | Partial payment demonstrated in `#record-panel`; matching/allocation and fees explained in sales FAQ |
| Tracking invoices issued elsewhere | Plan 865; Decisions 393–400 | Approved pilot direction; not verified available | Distinguish tracking from issuing fiscal documents | Explained: sales/documents FAQ; fiscal FAQ preserves issuance distinction |
| Reports, documents and period package | Plan 230, 857, 873 | Planned | Supporting owner task with unresolved items visible | Explained: web workspace strip, sales FAQ and expandable `#preparar-registros` |
| Full Business web workspace | Decisions 385–390 | Approved direction; in development | Clearly identify full web product | Explained: web/mobile surface strip before `#como-funciona` |
| Thin iPhone companion | Decisions 385–389; Plan 564–566 | Planned for first Business testers only | Capture, quick approvals and money checks; no public availability | Explained: web/mobile strip, pilot-only companion and no public app claim |
| Collaborators, invitations and permissions | Plan 224, 851, 858; Decisions 373–375, 457–458 | Scope unresolved | Name as being defined, not a committed role matrix | Explained: permissions still being defined in web strip and scope FAQ; no role presets promised |
| Pilot audience, scope, price and next step | Plan 267–276, 396–400 | Agreed per business; price and first segment unresolved | Preserve founder conversation; no invented price or offer | Explained: `#como-funciona`, pricing/contact FAQ and `/business/demo` |

## Intentional exclusions and gates

| Capability | Disposition and reason |
| --- | --- |
| Live e-CF issuance | Partner-first direction approved; provider and issuer gates remain. Explain in FAQ without claiming availability. |
| Own fiscal backend, DGII MCP and PSFE status | Internal and longer-term work. Not a customer-facing pilot demo. |
| WhatsApp intake | Proposed and dependent on Meta onboarding. Not a promised input method. |
| Telegram | Candidate only. Excluded from commitments. |
| Gmail | Founder decision open. Excluded from promised integrations. |
| POS connectors and payment links | Discovery and provider gates open. No working claim. |
| External API and MCP | Later and permission-dependent. Outside pilot offer. |
| Projects and time tracking | Optional future scope in Plan 233. Reference screenshots do not approve it. |
| Tax filing, bank execution and cards | Gated or outside this pass. No execution claim. |
| Automatic Dominican bank feeds | Coverage unavailable. Manual records remain useful; no bank logos or implied sync. |
| Plaid | Consumer direction with production review required. Does not establish Business or Dominican coverage. |
| Investment simulations, product shopping and household sharing | Separate consumer capabilities. Not required to explain Business owner jobs. |
| Security, consent, deletion and privacy | Product requirements. Show review/control boundaries without invented certifications or guarantees. |

## Delivery boundary

The contact form remains a local review flow. It sends no inquiry and books no meeting. The email link opens the visitor's mail app. No contact or waitlist submission is part of verification.
