# Core flows for both apps

**Created:** October 13, 2026. Owner of the core-flow list for Cuadrao Business (web)
and Cuadrao Personal (iPhone). It is also the founder's test checklist.

Other documents link here. They do not repeat the list. The
[execution manifest](specs/argus-execution-board.md) owns work status and the
[MVEE](specs/argus-minimum-viable-ecosystem-experience.md) owns approved experience.
This file owns one thing: which flows exist, and when each was last walked.

## Labels and state

Labels use the repo vocabulary.

| Label | Meaning |
| --- | --- |
| `enabled` | Feature active for a named environment and audience, with approval and readback evidence. |
| `implemented` | Full issue scope landed on integration. Acceptance or activation may still be pending. |
| `verified` | Issue acceptance passed with a linked commit, environment and user-journey evidence. |
| `deferred` | Not in the current build on purpose. |
| `triage` | A hypothesis or user report not yet checked. |
| open PR | Built, not landed. It is not `implemented`. |
| lane branch | Merged into the Mobile lane branch only, not on integration. |

State: ✅ works, ⚠️ gap, ❌ failed.

**Stale rule.** A row's ✅ is stale when code in its area changed after the build it
was walked on. A stale row shows ✅ but must be walked again.

**Design fixes rule.** Every row has a "Design fixes" cell: a link to that screen's design
fix list, or "none yet" (never empty). A flow cannot show ✅ while its list has an open
blocker. An open blocker turns the row ⚠️ until the list item is closed. The founder
keeps the lists. Where: to be set by the founder (no path exists yet). The lists start
with the accountant screens, once the Grok bot walks them. This file does not create them.

**Last walked** is required in every row. If never walked, write "never".
Format: date (UTC), build, who. Build is the integration SHA the staging services ran
(web tests) or the lane SHA plus phone build folder (iPhone tests). Who is founder,
claude, or a named bot. "unverified" means the fact was reported and not checked
against git, GitHub or a log.

## Business (web)

Flows 1 to 7 are the trackers [#943](https://github.com/lagarcess/argus/issues/943) to
[#949](https://github.com/lagarcess/argus/issues/949).

| Flow | Label | State | Last walked | Result and note | Owner | Design fixes |
| --- | --- | --- | --- | --- | --- | --- |
| 1. Access and clients | triage | ✅ | see rows below | Parent of the access rows | #943 | none yet |
| 1a. Sign-up and sign-in | triage | ✅ | 2026-10-12, build not recorded (staging before the #1035 deploy), claude, read-only in the founder's staging browser | Works. Known report, not yet checked: login lands on /chat. Logout needing two clicks. | #943 | none yet |
| 1b. Accountant invite and read-only view | triage | ⚠️ | never | Invite by email and owner grant landed (#988). Not walked. | #943 | none yet |
| 2. Capture | triage | ✅ | see rows below | Parent of the capture rows | #944 | none yet |
| 2a. Upload to approve to saved expense | triage | ✅ | 2026-10-12, build not recorded (staging before the #1035 deploy), claude, read-only | Works end to end in the founder's browser | #944, #947 | none yet |
| 2b. Several files and all types | triage | ⚠️ | never | Not walked | #944 | none yet |
| 2c. Manual expense | triage | ⚠️ | never | Not walked | #944 | none yet |
| 3. Extract and categorize | triage | ⚠️ | never | Not walked as its own flow | #945 | none yet |
| 3a. Invoice checks (e-CF) | implemented | ⚠️ | never | Merged and on staging at `30911e7fb`. Never walked by the founder. | #945 | none yet |
| 3b. DGII QR check, fill and the DGII link | implemented | ⚠️ | never | Merged and on staging at `30911e7fb` (#1051, #1053). Never walked by the founder. | #945 | none yet |
| 4. Review and correct | triage | ⚠️ | never | Not walked as its own flow. Reported, under investigation: "a person with approval permission must approve" shown to the owner. | #946 | none yet |
| 4a. Several purchases, duplicate, rebind | implemented | ⚠️ | never | Landed (#996, #997, #998, #1012). Never walked by the founder. | #946 | none yet |
| 5. Approve and record once | triage | ✅ | 2026-10-12, build not recorded, claude, read-only | Covered by 2a | #947 | none yet |
| 6. Find and inspect | triage | ✅ | see rows below | Parent of the find rows | #948 | none yet |
| 6a. Home counts, Bandeja, Novedades, period control | triage | ✅ | 2026-10-12, build not recorded, claude, read-only | Works at that build. Reported, under investigation: Overview inbox count 0 with a note pending. Period changes landed after (#1016). | #948 | none yet |
| 6b. Search | triage | ✅ | 2026-10-12, build not recorded, claude, read-only | Works at that build | #948 | none yet |
| 6c. Open a saved expense | implemented | ⚠️ | never | Landed (#1030, #1033), on staging at `30911e7fb`. Never walked by the founder. | #948 | none yet |
| 7. Reconcile and hand over | triage | ⚠️ | never | Not walked | #949 | none yet |
| 7a. Export | triage | ⚠️ | never | CSV and Excel export landed (#973). Reported, under investigation: export panel on the record page. | #949 | none yet |

### A. The accountant's month

Its own row, separate from Flow 1, so it cannot sit behind the owner's setup. The
accountant opens a period, sees every record with its evidence and uncertainty, asks
or receives corrections, and accepts the month as sufficient. Source: journey J8 and
the E3 accountant month test in the
[Business agent execution spec](specs/lanes/cuadrao-business-agent-execution-spec.md).

| Flow | Label | State | Last walked | Result and note | Owner | Design fixes |
| --- | --- | --- | --- | --- | --- | --- |
| A. Accountant's month: open a period, see every record with evidence and uncertainty, ask or receive corrections, accept the month | triage | ⚠️ | never | Never walked. | #949, spec J8 and E3 | none yet |

## WhatsApp and email

| Flow | Label | State | Last walked | Result and note | Owner | Design fixes |
| --- | --- | --- | --- | --- | --- | --- |
| Link a number | triage | ✅ | 2026-10-13 01:08 UTC, build not recorded, founder | Works | #944 | none yet |
| Receipt intake and acknowledgement | triage | ✅ | 2026-10-13 01:11 UTC, build not recorded, founder | Works | #944 | none yet |
| AI read, follow-up reply and filled form | triage | ✅ | 2026-10-13 03:50 UTC, staging API on `16d96c621`, founder | Works. A first PDF at 03:24 UTC failed on an expired Meta token; fixed by rotating the token. | #944 | none yet |
| AI-permission switch | triage | ⚠️ | never | Switches landed (#1011, #1019, #1022). Not walked on its own. | #944 | none yet |
| AI chat in WhatsApp | deferred | ✅ | not applicable | Off on purpose. WhatsApp reads receipts only. Any other text gets one fixed reply with the web link. | [Authority](DOCUMENTATION_AUTHORITY.md) | none yet |
| Email forward | triage | ⚠️ | never (never walked end to end) | Cause confirmed 2026-10-13: the API has no Resend webhook signing secret (log line `missing: webhook_secret_present`). | #944 | none yet |

## Personal (iPhone)

Personal had no numbered flows before this page. They are locked here by today's tiers.
Detail is in [MVEE section 1.3](specs/argus-minimum-viable-ecosystem-experience.md#13-complete-scope-checklist)
and [section 6](specs/argus-minimum-viable-ecosystem-experience.md#6-connected-journeys-that-the-ecosystem-must-support).

- **P1. Free without an account.** On the phone only: no account, a local book, receipts kept on the device, no AI read.
- **P2. Free with an account.** Sign-in, accounts, activity, reconciliation, Home, Plan, Search, receipts with AI read after consent, Updates, Profile.
- **P3. Household.** Invitations, shared records and plans. (In English copy write "household". The Spanish label is Hogar.)

Full stays off this list until the founder and the coordinator shape it.

**Test sheet.** PRUEBA_MOVIL is not in this repository: unverified, check where it lives.
Step numbers below are mapped from the results the founder reported on 2026-10-13. Each
mapping is inferred from the described result and not read from the sheet, so confirm it
against the sheet. Steps 10 to 36 are not yet walked and not mapped.

**Founder walk:** 2026-10-13 about 03:00 UTC, phone build `phone-build-ebff591e0`, lane tip
`ebff591e0`. Steps 1, 2, 3, 4 and 9 pass. Step 5 not tested (refund entry not intuitive).
Step 6 fails (a zero balance shown as unknown; an "already included" question on every
movement). Step 7 fails (a card expense showed the wrong account and did not move the card;
the card is missing from Transfer). Step 8 unsure (balance numbers).

Fixes merged on the Mobile lane branch only, not on integration: #1045, #1046, #1047,
#1056. #1059 is an open PR. Rows these fixes touch are "fixed on lane branch, not re-walked".

| Flow | Label | State | Last walked | Result and note | Owner | Design fixes |
| --- | --- | --- | --- | --- | --- | --- |
| P1. Free without an account | triage | ⚠️ | never | Not walked. Parent row. | MVEE 1.3 Access | none yet |
| P1a. Local book and receipts kept on the device, no AI read | triage | ⚠️ | never | Not walked | MVEE 1.3 Access, Intake | none yet |
| P2. Free with an account | triage | ⚠️ | 2026-10-13 ~03:00 UTC, `ebff591e0` / `phone-build-ebff591e0`, founder | Parent row. Steps 1 to 9 walked, results below. | MVEE 1.3 | none yet |
| P2a. Sign-in (steps 1 to 4, mapping inferred) | triage | ✅ | 2026-10-13 ~03:00 UTC, `ebff591e0` / `phone-build-ebff591e0`, founder | Steps 1 to 4 pass. Which step is sign-in: unverified. | MVEE 1.3 Access | none yet |
| P2b. Accounts (step 6, inferred) | triage | ❌ | 2026-10-13 ~03:00 UTC, `ebff591e0` / `phone-build-ebff591e0`, founder | Step 6 fail: zero balance shown as unknown. Fixed on lane branch (#1047), not re-walked. Pending founder confirmation of the #1047 rule. | MVEE 1.3 Accounts | none yet |
| P2c. Activity (steps 5 and 7, inferred) | triage | ❌ | 2026-10-13 ~03:00 UTC, `ebff591e0` / `phone-build-ebff591e0`, founder | Step 7 fail: card expense on the wrong account, card missing from Transfer. Fixed on lane branch (#1045), not re-walked. Step 5 (refund) not tested. | MVEE 1.3 Activity | none yet |
| P2d. Reconciliation (steps 6 and 8, inferred) | triage | ❌ | 2026-10-13 ~03:00 UTC, `ebff591e0` / `phone-build-ebff591e0`, founder | "Already included" asked on every movement. Fixed on lane branch (#1056, #1046), not re-walked. Step 8 unsure on balance numbers. #1059 open. | MVEE 1.3 Reconciliation | none yet |
| P2e. Step 9 (area unverified) | triage | ✅ | 2026-10-13 ~03:00 UTC, `ebff591e0` / `phone-build-ebff591e0`, founder | Passes. Which area it covers: unverified. | MVEE 1.3 | none yet |
| P2f. Home | triage | ⚠️ | never | Steps 10 to 36 not walked. Which step: unmapped. | MVEE 1.3 Home | none yet |
| P2g. Plan | triage | ⚠️ | never | Not walked. Step: unmapped. | MVEE 1.3 Plan | none yet |
| P2h. Receipts with AI read after consent | triage | ⚠️ | never | Not walked. Step: unmapped. | MVEE 1.3 Intake | none yet |
| P2i. Search | triage | ⚠️ | never | Not walked. Step: unmapped. | MVEE 1.3 Search | none yet |
| P2j. Updates | triage | ⚠️ | never | Not walked. Step: unmapped. | MVEE 1.3 Updates | none yet |
| P2k. Profile, language and appearance | triage | ⚠️ | never | Not walked. Step: unmapped. | MVEE 1.3 Profile | none yet |
| P3. Household | triage | ⚠️ | never | Not walked. Parent row. | MVEE 1.3 Household | none yet |
| P3a. Invitations | triage | ⚠️ | never | Not walked. Step: unmapped. | MVEE section 12 | none yet |
| P3b. Shared records and plans | triage | ⚠️ | never | Not walked. Step: unmapped. | MVEE 1.3 Household | none yet |
| Voice | deferred | ✅ | not applicable | Later. | MVEE 1.3 Voice | none yet |

Phone build constraints: the build profile expires 2026-10-13 22:03 UTC. The Apple ID is
not signed in to Xcode. Both are as reported: unverified.

## Platform

| Flow | Label | State | Last walked | Result and note | Owner | Design fixes |
| --- | --- | --- | --- | --- | --- | --- |
| Worktree environment tool | triage | ⚠️ | never | Not walked as a flow | [AGENTS.md](../AGENTS.md) | none yet |
| CI | implemented | ✅ | PR #1058 checks, 2026-10-13, bot (GitHub Actions) | CI trigger rules (#1040) and poppler (#1042) landed | [CI/CD discipline](specs/private-alpha-ci-cd-sota.md) | none yet |
| Docs | triage | ⚠️ | never | Alignment PR #1058 open | [Authority](DOCUMENTATION_AUTHORITY.md) | none yet |
| Legal drafts | triage | ⚠️ | never | Drafts only (#1029). Company not formed. Lawyer review before publication. | [Open questions](legal/OPEN_QUESTIONS.md) | none yet |
| Staging deploys | triage | ⚠️ | never | Render deploy state is as the coordinator reported: unverified. Check the Render dashboard. | [Board](specs/argus-execution-board.md) | none yet |

## How to use this as a checklist

1. The founder posts pass or fail for a row.
2. The coordinator updates that row (date, build, who, result) in the same commit as
   any fix PR when possible.
3. A row with ✅ and a "last walked" older than its area's last code change is shown
   stale. Walk it again before trusting it.
4. A design fix list with an open blocker turns the row ⚠️ until the item is closed.
5. Never write ✅ for a flow nobody walked. Write "never".
