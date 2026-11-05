# Private Alpha Next Integration

Status: Integration staging/process context with a historical product ledger.
Use [documentation authority](../DOCUMENTATION_AUTHORITY.md) for approved
experience and assigned-work ownership. Check current PRs and release evidence
for landing/deployment status. The historical ledger below stops at August 2,
2026; later bounded landings are recorded separately below.
Date: 2026-06-10
Last reconciled: 2026-10-10 (PR #929 Marketing evidence landing; PR #937 Consumer keyboard landing; PR #919 and #921 Consumer iPhone landing; PR #905, #908, #909, #913, #914, #918, #920 Business landings; PR #904 + PR #901 Business pilot landing; Cuadrao launch reconciliation; PR #773 landing register restored; PR #809/#790/#810/#812 code checkpoint; PR #808/#813/#814/#815 documentation landing; PR #766 + PR #764/#763 + PR #760 + PR #759 + PR #757 + PR #755 + PR #753 + PR #751 + PR #749 + PR #747 + PR #745 + PR #743 + PR #735 + PR #739 + PR #738 + PR #733 + PR #672 + PR #695 + PR #721 + PR #711 landing registers; historical ledger still
through 2026-08-02)
Branch: `codex/private-alpha-next`
Audience: Founder, Codex, external async agents, reviewers

## Later bounded landings

- October 10, 2026: [PR #929](https://github.com/lagarcess/argus/pull/929) squash-merged as `4cb85949b4dea6855971c8268aac1bd1a0cacb01` from reviewed head `a8d1a5e80`, with identical trees. Historical privacy/contact evidence and main-specific rollback notes are preserved. The [landing record](../reports/2026-10-10-pr-929-reconciliation.md) owns verification. #939 follows only after this landing is verified and needs a separate merge slot. #927/main promotion, deployment and public forms remain held.
- October 9, 2026: [PR #937](https://github.com/lagarcess/argus/pull/937) squash-merged as `43fac94de2` from accepted head `87d7a8ab6`, with identical trees and no intervening integration overlap. Lucas accepted the four committed simulator journeys and green CI; physical VoiceOver/Switch Control checks remain unverified and are removed from this PR's gate. Build 3455 installation and launch were verified, but it still uses the local backend. The [landing record](../reports/2026-10-09-pr-937-integration-landing.md) owns source identity, retained evidence and limits. Next: signed-in free manual money against the staging API only. #877 stays open. Guest, receipts, shared plans, transaction redesign and RevenueCat remain outside the active assignment. The merge itself authorized no hosted change. Lucas later approved the completed money-gate activation and same-code restart/deploy on pinned staging `cad1cbe1e`, with a synthetic login. No newer code, migrations, production changes or TestFlight upload.
- October 9, 2026: Consumer iPhone landings under [#877](https://github.com/lagarcess/argus/issues/877) and one Business fix, each squash-merged on the founder's instruction after green exact-head CI and no open review comments. [PR #931](https://github.com/lagarcess/argus/pull/931) as `86f8e4f6e`: + then Transaction opens the editor on the primary-currency account instead of listing every account. [PR #934](https://github.com/lagarcess/argus/pull/934) as `e9d9fa4a1`: the bar folds into the + on Plan, Search and Profile as on Home. [PR #930](https://github.com/lagarcess/argus/pull/930) as `b8f1dc7c1` (Business lane, #928): funds a focused repair's field-fidelity approval from the repair pool; consumer-reviewed at `a1b5d9afa`. [PR #935](https://github.com/lagarcess/argus/pull/935) as `8a14aad25`: saved receipts client behind the receipts switch, off in Release; the stacked parent's squash conflicted once in the shell file and was reconciled before landing. Phone build 3453 (Release, from #934) is installed and accepted. Saved receipts have not run against a real server, and the hosted storage and deletion smoke test is a separate approval before receipts are enabled anywhere. No migration, deployment or feature activation.
- October 8, 2026: Consumer iPhone landing under [#877](https://github.com/lagarcess/argus/issues/877), in this order, on the founder's instruction.
  - [PR #919](https://github.com/lagarcess/argus/pull/919) as `31a73c501` (accepted head `c98676ea9`): the + menu as an anchored card with a nub on the open bar and labeled round buttons stacked from the folded +, the free-tier Search wording, and the home-screen name "Cuadrao". Review fixes: the menu scrolls at large text and in landscape, icons stay in their badges, empty-state copy follows the bar.
  - [PR #921](https://github.com/lagarcess/argus/pull/921) as `826ace6d4` (accepted head `808c36ff7`): Marketing's approved "Lean, calm" mark as the app icon, the welcome screen as one lockup and two native actions on `#fafbf8` / `#172b26`, the shared lockup on the invitation card and chat empty state, and the brand identity in `.agent/designs/cuadrao/DESIGN.md`. Marketing's SVGs are pinned: lockups at `acf1b180a`, the rest at `73286f8ca`.
  - Before merge: integration had changed no iOS files since #919's base; the two PRs' files are disjoint and identical in integration to their accepted heads; the combined menu, large-text, welcome and lockup checks passed on the local integration merge; exact-head CI and smoke on `826ace6d4` passed.
  - Phone build 3452 is built from `826ace6d4`. No migration, deployment or feature activation.

- October 8, 2026: [PR #920](https://github.com/lagarcess/argus/pull/920) merged as `f5a2007cd`.
  - A switch now stops only new intake. With document extraction or ingestion off, saved Personal documents and Business receipts stay readable and deletable, with Storage erased first. WhatsApp unlink is always available to the signed-in owner.
  - `ARGUS_BUSINESS_CHAT_ENABLED` (default off) keeps Business chat off until its tool restrictions and required tests pass.
  - Before merge: exact-head CI green, clean, and an independent review that said ship.
  - The founder approved the Business search and receipt-state copy on October 8. The "AI result unknown" text was replaced by the founder's wording in the PR that carries this note.
  - No migration, deployment or activation.

- October 8, 2026: after Consumer recorded the Build 2 candidate `64833f6d2` on [#833](https://github.com/lagarcess/argus/issues/833), the rest of the Business queue merged, in order. Each had green exact-head CI, contained integration and had no open review threads:
  - [PR #908](https://github.com/lagarcess/argus/pull/908) as `56f50b2f6`: durable document preparation jobs, migration `20261008110000` (B2).
  - [PR #909](https://github.com/lagarcess/argus/pull/909) as `fa5923529`: WhatsApp receipt intake, migration `20261008130000` (B3), with founder-approved reply copy.
  - [PR #913](https://github.com/lagarcess/argus/pull/913) as `7ec48872e`: the Business API, with no migration.
  - [PR #914](https://github.com/lagarcess/argus/pull/914) as `6022747cb`: separate Personal and Business spaces, migration `20261008140000` (B4), plus Business search, receipt next steps and the read-only scripts `business_spaces_precheck.sql` and `business_space_rows.sql`.

  - [PR #918](https://github.com/lagarcess/argus/pull/918) as `20a88440c`: S4 chat separation without the model-facing tool catalog. Personal and Business chats keep separate Recents, history, search, delete-all and Compare lists. Artifact routes refuse Business chats, Business turns skip memory, and the /biz palette drops the investing filters. It has no migration and needs B4 before it deploys. Two independent reviews said ship.

  All are outside Build 2 and default-off. B2 to B4 are not applied anywhere hosted. Any build that reads them needs B1 to B4 applied first. Once Business data exists in hosted, the build carrying #914 is the minimum compatible code version. Evidence on #914 covers local end-to-end runs, the compatibility rehearsal, flags-off and the live read-only check. No deployment, hosted migration or flag change.

- October 8, 2026: [PR #905](https://github.com/lagarcess/argus/pull/905) squash-merged as `64833f6d2` from head `404825055` onto the Consumer Build 1 freeze `cad1cbe1e` ([#833](https://github.com/lagarcess/argus/issues/833)). It moves retained document sources to a private Supabase Storage bucket, with dual read of the legacy bytea and an account-deletion `storage` step. It adds migration `20261008100000_financial_document_source_objects.sql` (B1), not applied anywhere hosted. It is the only Business PR in Consumer Build 2; #908, #909, #913 and #914 wait for the recorded Build 2 candidate. The document surface stays off. The rehearsal on #914 shows that code older than this cannot read or delete Storage-backed documents: once documents are stored in hosted, this release is the minimum compatible code version. #778 stays open until B1 is applied and verified in hosted. No deployment, hosted migration or flag change.

- October 7, 2026: Cuadrao Business owner pilot, first two landings under [#900](https://github.com/lagarcess/argus/pull/900). [PR #904](https://github.com/lagarcess/argus/pull/904) squash-merged as `ee4acd50e` from head `43ad4a70b`: one receipt review read from the draft, its evidence and its import event, with no migration. [PR #901](https://github.com/lagarcess/argus/pull/901) squash-merged as `d2d0c6d38` from head `72f7f07c8`: the Business screens inside the chat shell at `/biz`, behind `NEXT_PUBLIC_BUSINESS_PILOT_ENABLED` (default false, now in `web/.env.local.example`), plus the guarded money input. With the flag off, `/chat` matched integration byte for byte in en and es-419 on desktop and phone. Exact-head CI was green on both and neither had open review threads. No linked issue closes. Storage (#905), preparation jobs (#908) and WhatsApp intake (#909) carry migrations and stay unmerged until the consumer freeze is posted. No deployment, hosted migration, Business activation or paid provider call.

- October 7, 2026: [PR #884](https://github.com/lagarcess/argus/pull/884) delivers the default-off Cuadrao Business and Personal marketing preview. The [website delivery record](../reports/2026-10-07-cuadrao-website-integration.md) links exact-head evidence and launch follow-ups #880–#882. No public activation, hosted persistence, financial-runtime or native-app change.

- October 6, 2026: documentation-only [Cuadrao launch reconciliation](../reports/2026-10-06-cuadrao-launch-reconciliation.md) and [#877 recovery handoff](../reports/2026-10-06-cuadrao-877-recovery-handoff.md) on top of `df3882668413e7978d3983adfe1f054cb83595c4`. It restores the PR #773 landing register recovered from draft #774, and records open-PR dispositions for #781, #774, #732, #646 and #744. No runtime, test, configuration, migration, flag, hosted or deployment change.

- October 6, 2026: atomic confirmed local cleanup #876 landed as `184d2614e4d2beb5ed994bd3cd8f3a5ef211f1dd`. [Record](../reports/evidence/cuadrao-trust-20261005/pr876-landing-record.json) preserves validated filesystem/SDK boundaries, without app UI or provider completion claims. Housekeeping uses #873; integration CI running and smoke passed.
- October 6, 2026: native deletion core #875 landed as `8146d16e90633eb543781f8882665482f0d5dca9`. [Record](../reports/evidence/cuadrao-trust-20261005/pr875-landing-record.json) distinguishes verified local command behavior from final UI, filesystem, provider and device gates. Housekeeping uses #873; exact integration CI37408905271 and smoke37408905356 passed.
- October 6, 2026: native Apple first-name safety #874 landed as `a2c65549b3ffcb97ee0be24b971110be8c090b32`. [Record](../reports/evidence/cuadrao-trust-20261005/pr874-landing-record.json) preserves accepted local source proof and external gates. Protected-branch housekeeping continues through #873; exact integration CI and smoke passed.
- October 6, 2026: session safety #864 landed as `5d46a73d4d97b0412dccff517eb43c73e4316977`, following reviewed housekeeping #860. [Landing record](../reports/evidence/cuadrao-trust-20261005/pr864-landing-record.json) preserves independent proof and remaining gates. Integration CI37405778022 and smoke37405778015 passed; bookkeeping proceeds through protected-branch PR #873. No hosted or activation change.
- October 5, 2026: bounded Trust and Foundations slices #851, #844, #846, #858, #857, #863, #853, #868, #862, #849, #869, #847, #854, #845, #865 and #871 landed through `c0d44d399b8fbf2edcdd0a8fd3ad4759a0e9c548`. [The run record](../reports/evidence/cuadrao-trust-20261005/active-queue-20261005.md) preserves merge records, independent evidence and exact integration check state. Housekeeping proceeds by PR under branch protection. Narrow fixture/profile/observer defects #861/#848/#867 are resolved; parents remain open. New worker slices remain unmerged until their exact-head checks pass. No social/deletion activation, hosted migration, legal publication, main promotion or deployment.

- October 4, 2026: [Cuadrao code integration checkpoint](../reports/2026-10-04-cuadrao-code-integration-landing.md), #809, #790, #810 and #812. The QA gate, release UI, default-off invitation client and responsiveness changes preserve the latest approved foundation documents. The report and final #812 landing comment record source identity, merge lineage and terminal CI. Thirty-four fresh selected simulator journeys passed. Physical-phone, hosted-service and feature-enablement gates remain open.

- October 4, 2026: [Cuadrao documentation landing](../reports/2026-10-04-cuadrao-docs-integration-landing.md), PRs #808, #813, #815 and #814, through `883d289ff8f9c4261f63078d10121de7fb371789`. Deletion edge-case decisions, the mobile execution checkpoint, October 4 direction and historical-spec archives are recorded together. No runtime, configuration, migration, deployment or phone-build change. The report owns merge lineage, retained evidence and remaining gates.

- October 2, 2026: [PR #773](https://github.com/lagarcess/argus/pull/773) squash-merged as `f28b56421caf71d6610caf1cce891e1848e0ace1`, from Exact publication head `dee829f8a3a7f83fb25cd81aaf3fa6deac8bfe45` onto tip `15e57931584b21dd7f9e453dbeb9127fc4b8cff3` (`merged_by` app/cursor at 00:47:28 UTC). Default-off shared Household planning on #763/#766: budgets, bills, goals and debt with explicit view/edit rights, unequal responsibilities, private funding redaction, departure retention freezes, and Home/Plan/Search. Tip at promote was already the worker merge-base; no reconcile merge; no intervening overlap. Pre-merge Exact-head CI/smoke SUCCESS; Preview SKIPPED at limit; Codex P1 freeze fixed/resolved; zero unresolved threads; modularity clean; squash tree ≡ worker tree `2f55d72b…`. The [execution manifest](argus-execution-board.md#pr-773-integration-landing) and [landing report](../reports/2026-10-02-pr-773-integration-landing.md) own retained evidence and remaining limits. Migrations `20261001190000` and `20261002000000`–`20261002050000` stay clear of ingestion reserved `20261002120000`–`20261002120300` and are not production-applied. `CUADRAO_HOUSEHOLDS_ENABLED` stays default-off. No linked issue closure. Physical iPhone/internet, external invites, hosted enablement, Preview repair, and parked design checkpoint `aba489b0…` remain outside. Integration CI 36947752893 and smoke 36947752913 passed at `f28b5642` (read back October 6); the landing-docs PR #774 never merged and is superseded by the October 6 reconciliation. No deployment, hosted configuration change, signing, main promotion or next-slice start. #768–#772 untouched.

- October 1, 2026: [PR #766](https://github.com/lagarcess/argus/pull/766) squash-merged as `079ec8d819f8e2513cc624bfa7a4eb9ca60c7627`, from Exact publication head `04831ccb12a46b89a3cd5f5391139d3589321815` onto tip `09ce4e0af3b6df7a41e2d21c52c67b4fe7c82c0a` (`merged_by` lagarcess at 15:10:45 UTC). Default-off Household native consent + canonical financial activity on #763 membership and #760 shell: named-account grants, view/edit separation, Home/People/invitation/Search/corrections en/es-419, private-leg redaction, owner-qualified history, and server-derived `households_unavailable` gating. Tip at promote already ancestor of the worker; prior reconcile `4fed9efb…` was docs-only. Pre-merge Exact-head CI/smoke/Preview SUCCESS; Codex follow-up clean; zero unresolved threads; modularity clean. The [execution manifest](argus-execution-board.md#pr-766-integration-landing) and [landing report](../reports/2026-10-01-pr-766-integration-landing.md) own retained evidence and remaining limits. `CUADRAO_HOUSEHOLDS_ENABLED` stays default-off; additive consent/grant migrations are not production-applied. No linked issue closure. Physical iPhone/internet, external invites, shared Plan consumers, Business/Custom, hosted enablement, Accounts tab, Apple-on-connected-path, and parked design checkpoints `1dcd12a5`/`1b2005fd9` remain outside. Exact integration CI/smoke and final tip parity after landing-docs housekeeping are recorded on the merged PR. No deployment, hosted configuration change, signing, main promotion or next-slice start.

- October 1, 2026: [PR #760](https://github.com/lagarcess/argus/pull/760) product squash-merged as `819870e6fcfd28d469b12691fe2471e00e2000db`, from Compact-verified Exact head `0462f3ade6d347bd13644eda5636264c007034c0` onto integration including Household product merge #763 (`fbcc399bdb888d89af594422cfa319a4c26c60e5`). Connected Cuadrao auth/Home/shell lands with Compact matrix green on exclusive sim `1A90F684…`; Search/AuthJourney/complete-loop retained; design checkpoint `1dcd12a5` adopt=none; chat/voice parked. Reconcile overlap with #763: path none; recording additive `get_any_account` only; Compact personal-loop evidence retained with post-reconcile complete-loop smoke. The [execution manifest](argus-execution-board.md#pr-760-integration-landing) and [landing report](../reports/2026-10-01-pr-760-integration-landing.md) own retained Compact evidence and remaining limits. Exact integration CI/smoke, landing-docs housekeeping merge `#765` as `631d405142435d059ab6ef419f8235bf0ad52947`, and tip parity are recorded; do not treat the product squash as the lasting tip. No linked issue closure required for this landing; iPhone pending allowed; design checkpoints remain founder-named only. No deployment, hosted configuration change, signing, main promotion or chat/voice slice start.

- October 1, 2026: [PR #763](https://github.com/lagarcess/argus/pull/763) squash-merged as `fbcc399bdb888d89af594422cfa319a4c26c60e5`, from verified head `7b80190d057c89b5f92b03845f374a810253dda1` onto unchanged integration `9b5e8643f0493145bd672c2af6e7508371d4cfa0`. Default-off Household membership API: create → synthetic invite → accept → explicit account grants, leave/remove/revoke/close/transfer-admin, security-definer membership RLS helper, and deletion-safe historical attribution. Hermetic in-memory two-user lifecycle tests landed with the feature (`PERSISTENCE_MODE=memory`, mocked Auth/Supabase); real Auth/Postgres/RLS verification remains pending. Codex P1/P2 findings (recursive RLS, deletion-safe identity, lock order) fixed at Exact head with zero unresolved threads and all 17 CI checks SUCCESS. The [execution manifest](argus-execution-board.md#pr-763-integration-landing) and [landing report](../reports/2026-10-01-pr-763-integration-landing.md) own retained limits and remaining real-stack/native/shared-consumer work. No linked issue closure; `CUADRAO_HOUSEHOLDS_ENABLED` remains default-off in tracked templates. The additive household migration is not applied to production. Exact integration CI/smoke and final tip parity for this docs landing are recorded in the merged PR #764 landing comment. Design, simulators and the physical-phone environment remain untouched by #763. No deployment, hosted configuration change, signing, main promotion or next-slice start.

- September 30, 2026: [PR #759](https://github.com/lagarcess/argus/pull/759) squash-merged as `0cd8d1658c8a58d0a8e29e3307f948aed11ecbc3`, from verified head `12a48f598da40fdad16c96caf80a92324f2eb1a4` onto unchanged integration `9d6ed94491be9d904da881901a6d7a2dc8cf635b`. Locally verified personal property, vehicle and other assets connect whole estimates, explicit ownership shares, date/basis, corrections, archive/restore and canonical debt links to Accounts, Home and Search. Unknown is distinct from zero; estimates affect net worth without becoming cash, spending or forecast movements. Existing linked debt counts once. Approved-head and merge trees are identical. Green applicable checks, clean independent and scoped Codex review, zero unresolved findings and final-head native/API revalidation are preserved in the [terminal audit](https://github.com/lagarcess/argus/pull/759#issuecomment-5922943880). The [execution manifest](argus-execution-board.md#pr-759-integration-landing) owns the retained demo, remaining limits and MVEE work. No linked issue closure or new production configuration; financial exposure remains default-off. The additive asset migration is locally/ordinary-preview verified and has not been applied to production. Exact integration CI, smoke, bounded landing housekeeping and final parity are recorded in the merged PR landing comment. All demos, Cuadrao and the physical-phone environment remain preserved. No deployment, hosted configuration change, signing, main promotion or next-slice start.

- September 30, 2026: [PR #757](https://github.com/lagarcess/argus/pull/757) squash-merged as `63b73ea80df9af2a61aa99f83afb9595408d0370`, from verified head `563c7011c8e37905d148d027665f4449971014d7` onto unchanged integration `7c29b2a9b3f4680f6804a2abc8378df45b05540c`. Locally verified personal debt plans connect card payments and explicit loan principal/interest/fees, partial/extra payments, dated returns, lifecycle and conditional payoff to Accounts, Plan, Home and Search. Recording remains the money owner; intentions and projections never become actual balances or duplicate spending. Approved-head and merge trees are identical. Green applicable checks, clean independent review and zero unresolved findings are preserved in the [terminal audit](https://github.com/lagarcess/argus/pull/757#issuecomment-5920292387). The [execution manifest](argus-execution-board.md#pr-757-integration-landing) owns the retained demo, remaining limits and MVEE work. No linked issue closure or new production configuration; financial exposure remains default-off. The additive debt migration is locally/ordinary-preview verified and has not been applied to production. Exact integration CI, smoke, bounded landing-documentation PR and final parity are recorded in the merged PR landing comment. All demos and the physical-phone environment remain preserved. No deployment, hosted configuration change, signing, main promotion or next-slice start.

- September 30, 2026: [PR #755](https://github.com/lagarcess/argus/pull/755) squash-merged as `dc48c074b457cfb461e128aee2dcc58f9db3a342`, from verified head `f6dfd482a1e4dc802f0d64eba22bc91a4f01d48f` onto unchanged integration `6a9d0338d2b2e7106877e0e5d1f9f5aaa70d67ec`. Locally verified personal savings goals connect explicit known-balance allocations, canonical contributions/corrections, shared shortfalls and lifecycle to Plan, Home and Search. Planned progress remains separate; unsupported savings show Needs review without redistribution or duplicated money. Approved-head and merge trees are identical. Green applicable checks, clean independent review and zero unresolved findings are preserved in the [terminal audit](https://github.com/lagarcess/argus/pull/755#issuecomment-5906057156). The [execution manifest](argus-execution-board.md#pr-755-integration-landing) owns the retained demonstration and remaining MVEE work. No linked issue closure or new production configuration; financial exposure remains default-off. The additive goal migration is locally/preview verified and has not been applied to production. Exact integration CI, smoke, bounded landing-documentation PR and final parity are recorded in the merged PR landing comment. No deployment, hosted configuration change, signing, main promotion or next-slice start.

- September 29, 2026: [PR #753](https://github.com/lagarcess/argus/pull/753) squash-merged as `ff1d9795af50ad1566d59e7e986e2cc31be2ca82`, from verified head `55d211636bc187cda2fe88fba152c5724a95907c` onto unchanged integration `9f51912198c2c77e239f670a2b3f78da2942afed`. Locally verified personal monthly budgets connect canonical expenses, corrections and received-month refunds to Plan, Home, contributing activity and Search, preserving scope and navigation/retry state. Limits do not change balances or forecasts. Approved-head and merge trees are identical. Green applicable checks, clean independent review and zero unresolved findings are preserved in the [terminal audit](https://github.com/lagarcess/argus/pull/753#issuecomment-5903364607). The [execution manifest](argus-execution-board.md#pr-753-integration-landing) owns the retained demonstration and remaining MVEE work. No linked issue closure or new production configuration; financial exposure remains default-off. The additive budget migration is locally/preview verified and has not been applied to production. Exact integration CI, smoke and final landing parity are recorded in the merged PR landing comment. No deployment, hosted configuration change, signing, main promotion or next-slice start.

- September 29, 2026: [PR #751](https://github.com/lagarcess/argus/pull/751) squash-merged as `5c143e642249872cd1d807a92dc4dd367c698671`, from approved head `f753d5111876457c98be9ffe0235123dbf107eb9` onto unchanged integration `22f9c8cda8a65c74985e367d8cef68e55515e16b`. Locally verified iPhone Search connects owned accounts, current activity and Plan expectations to their real editors, preserving refreshed search origin and exact scroll across Back/reopening in English and Spanish. Approved-head and merge trees are identical. Green applicable checks, clean independent review and zero unresolved findings are preserved in the [terminal audit](https://github.com/lagarcess/argus/pull/751#issuecomment-5900394900). The [execution manifest](argus-execution-board.md#pr-751-integration-landing) records the retained demos, isolation and remaining MVEE work. No linked issue closure or new production configuration; financial exposure remains default-off. Exact integration CI and final landing parity are recorded in the merged PR landing comment. No deployment, hosted change, signing, main promotion or next-slice start.

- September 29, 2026: [PR #749](https://github.com/lagarcess/argus/pull/749) squash-merged as `88d513c0ef2791b4277eb571ce6b1f4f291d3a5c`, from approved head `a2b6ed2bf849582de19aceedd61a3861d1c768e2` onto unchanged integration `21309f0832d438fd18651f47209e8c789a8fcc53`. Locally verified connected Plan/Home commitments, recurrence, fulfillment, corrections and dated currency-separated forecast reuse the canonical recording service. Approved-head and merge trees are identical. Green applicable PR checks, clean independent review and zero unresolved threads are preserved in the [terminal audit](https://github.com/lagarcess/argus/pull/749#issuecomment-5897315197). The [execution manifest](argus-execution-board.md#pr-749-integration-landing) retains all three runnable demos and remaining MVEE work. No linked issue closure or new production configuration; financial exposure remains default-off. Exact integration CI and final parity are recorded in the merged PR landing comment. No hosted migration, deployment, signing or main promotion.
- September 29, 2026: [PR #747](https://github.com/lagarcess/argus/pull/747) squash-merged as `6eb057e9abe23ecbbfa0228b9ba0e57623d2f696`, from approved head `5a997df3142dd9ca2d73207f8e4d8822705a646d` onto unchanged integration `b4fed10fe5cd325a7cd3e6ac21b87e9fbf5eb819`. Locally verified income, spending, owned transfers, card payments and refunds with corrections, reconciliation, recovery and identity isolation; transfer From/To clarity included. Approved-head and merge trees are identical. Green PR CI/smoke and clean scoped review are preserved in the [terminal audit](https://github.com/lagarcess/argus/pull/747#issuecomment-5895015807). The [execution manifest](argus-execution-board.md#pr-747-integration-landing) retains the runnable demos, evidence and remaining visual/full-MVEE work. No linked issue closure or new production configuration; exposure remains default-off. Exact integration CI/smoke and final parity are recorded in the merged PR landing comment. No hosted migration, deployment, signing or main promotion.
- September 29, 2026: [PR #745](https://github.com/lagarcess/argus/pull/745) squash-merged as `afc3db5ae679a32676fae94ed7c5e9c9ef68b633`, from approved head `944b2cb70ab008aa2ed9385b5d81555bad84f7fd` onto unchanged integration `fcbb70cc2899ca6a05c03c49316e9a4e4cbf5333`. Complete local simulator financial loop with canonical expenses/corrections/reconciliation and connected Accounts/Home; merge and approved-head trees are identical. Green PR CI/smoke and clean scoped review with zero unresolved threads are preserved in the [terminal audit](https://github.com/lagarcess/argus/pull/745#issuecomment-5888571700). The [execution manifest](argus-execution-board.md#pr-745-integration-landing) owns remaining work and the runnable demo. No linked issue closure or new production environment variable; financial exposure remains default-off. Signing, physical-phone installation and deployment remain deferred. Exact post-merge integration CI/smoke are recorded in the merged PR landing comment. No main promotion or hosted configuration change.
- September 29, 2026: [PR #743](https://github.com/lagarcess/argus/pull/743) merged as `12bccd4d6e173a5d8805e495fd30b7ead36741c6`, from approved head `25a861b5ba70b404c93d99de91ad80b01b522729` onto `de8729843b726a3fd03210cebcedede5e44227c8`. Published the private iPhone MVEE lock and [execution manifest](argus-execution-board.md), linked through [documentation authority](../DOCUMENTATION_AUTHORITY.md), with superseded assignments marked historical and native recovery checkpoints preserved. PR CI passed; the Codex fix review was clean, zero threads remained open, and the later preservation-pointer delta was verified. No linked issues to close or environment/config changes. Implementation remains stopped; no deployment or main promotion. Exact integration CI is recorded in the merged PR landing audit.
- September 29, 2026: [PR #735 integration landing](../reports/2026-09-29-pr-735-integration-landing.md), merged as `296195e86c972e846c251d256b3cc211975bfd57`. Financial accounts first slice behind `ARGUS_FINANCIAL_ACCOUNTS_ENABLED` default-off; opening writes bind caller-visible `expected_version`. No hosted enablement, deployment, or main promotion.
- September 29, 2026: [PR #739 integration landing](../reports/2026-09-29-pr-739-integration-landing.md), merged as `738e11a4813f85feff051e6bb4f3d05fc19453a1`. Android registered-session continuity behind local opt-in; default-off; financial features remain samples. No deployment or main promotion.
- September 29, 2026: [PR #738 integration landing](../reports/2026-09-29-pr-738-integration-landing.md), merged as `00368a64658a106ee705db241a92d3b1aabce127`. Default-off iPhone registered sessions (Keychain + official Swift Auth SDK); financial destinations remain samples. No deployment or main promotion. [#739](https://github.com/lagarcess/argus/pull/739) squash-merged immediately afterward as `738e11a4813f85feff051e6bb4f3d05fc19453a1`.
- September 28, 2026: [PR #733 integration landing](../reports/2026-09-28-pr-733-integration-landing.md), merged as `c3b2042b9b69c5b75e173d145ed0020f00ccd79e`. Cross-platform chart validation prototype and evidence accepted; Android/Vico remains conditional and merge does not approve production chart adoption. No deployment or main promotion.
- September 28, 2026: [PR #672 integration landing](../reports/2026-09-28-pr-672-integration-landing.md), merged as `86df1ee95cc3c88d713efa6a24538c6217b2ea29`. Docs-only accuracy audit (calculation catalog ownership, memory/sharing production truth, decision-log locks, durable promotion evidence, in-place founder board publication). No deployment or main promotion.
- September 28, 2026: [PR #695 integration landing](../reports/2026-09-28-pr-695-integration-landing.md), merged as `25015963600fa9dd9290080bf641238693509a37`. Disables unused `argus-api` onrender hostname (`renderSubdomainPolicy: disabled`); runbook/readiness require HTTP 404 from that host after Blueprint sync. Issue #686 hygiene; no deployment or main promotion.
- September 28, 2026: [PR #721 integration landing](../reports/2026-09-28-pr-721-integration-landing.md), merged as `3b9313f3dcf80e3ff9eddfcce8818a829a081225`. Two OpenRouter DEBUG catchers log error class and origin instead of exception text. Issue #710 proposed for separate closure. No deployment or main promotion.
- September 27, 2026: [PR #711 / issue #689 integration landing](../reports/2026-09-27-issue-689-integration-landing.md), merged as `ed6d9b2b53bbb5366bfe5a452249ba2cd7e2bbb1`. Shared research-cache isolation is landed. At that landing, discovery's current-turn provenance/cache-reuse follow-up remained open as [#712](https://github.com/lagarcess/argus/issues/712); [#712](https://github.com/lagarcess/argus/issues/712) was later closed as completed through merged [#715](https://github.com/lagarcess/argus/pull/715) (`f0a90763b79e5625ac0a4789cdfa171cda023963`). No deployment or main promotion.

## Historical product ledger through August 2, 2026

Latest product change: PR #366 at `2b023576`, which makes grounded
discovery's failures as honest as its successes — typed routing for current
searches, working Retry for transient failures, non-retryable honesty with a
forward path for configuration failures, and fail-closed citation evidence
(issue #344). This completes the #347 checkpoint-gap batch for this cycle;
the integration head is the promotion-freeze candidate. It follows PR #354
at `4a6a237a` (truthful guest quota recovery, issue #346) and PR #358 at
`7b3221a1` (all-or-retry compound edits, issue #339) and PR #359 at
`a35bb29f` (recommendation continuity through the shared clarify contract,
issue #345) and PR #373 at `81e7a1ac` (first-login guest
claims with preserved anti-enumeration, issue #372) and PR #351 at `30af0dca` (immediate Recents refresh on
claimed conversions, issue #342) and PR #374 at `d8c7070a` (robust activity timestamp parsing and
exception retention, issue #371) and PR #370 at `c324f877` (typed first-page dossier
cursors, issue #341), PR #360 at `42d96da7` (issue #349 verification
evidence), and PR #375 at `c334cf3e` (stated-capital preservation on unsupported
turns, issue #368), PR #352 at `0942507b` (unified OS-aware keyboard
registry and contextual shortcut legend, issue #334), PR #356 at `48de2f3f`
(rounded menu highlights, issue #343), PR #357 at
`9f97f1dc` (guest dossier conversion gating, issue #340), PR #353 at
`7e4c58f8` (proven-continuity rail attention clearing, issue #337), PR #355
at `c01d5730` (opening-turn asset/capital preservation, issue #336), PR #362
at `b2e8975c` (live-eval environment repair, issue #361), and PR #348 at
`38874bae` (self-hosted canonical fonts).
Later commits may reconcile documentation and issue state without changing
product behavior. New work must branch from the current remote
`codex/private-alpha-next` head rather than pinning either product SHA. The
accepted post-promotion
vertical slices are graph range switching (PR #264), account recovery/session
controls (PR #261), truthful Usage allowances/accounting (PR #259), and
executable capability truth (PR #266), the Always Progresses continuity
baseline (PR #268), calendar-materiality classification (PR #267), chat-header
title/owner-menu correction (PR #274), explicit onboarding removal (PR #275),
truthful stale Run settlement (PR #277), and supported strategy-transition
preservation (PR #278), plus the default-on grounded-discovery baseline
(PR #276), modeled-cost preservation (PR #280), and the Guest experience
(PR #279), followed by chat next-move presentation (PR #281). Provider-free
backend test isolation landed through PR #282, and PR #286 made the complete
`tests/` directory the backend CI gate. PR #287 then delivered resolver-owned
discovery selection identity and candidate/entity corroboration. PR #285 then
bounded Conversations, Messages, History, and Omnisearch/Idea Ledger reads at
the Postgres boundary while preserving cursor, ranking, ownership, and artifact
contracts. This is an integration checkpoint, not a deployed or
tester-exposed SHA. PR #288 then completed canonical fact-preserving recovery
after stale or failed actions without changing public artifact contracts.
Later slices culminated in PR #298's visitor/day Guest settlement, honest
discovery progress, and per-candidate source ownership, followed by PR #299's
instant and race-safe browser-session conversation switching. PR #300 then
completed comparison name grounding, unsupported-target disclosure, and
discovery-act preservation through pending confirmations. PR #302 completed
bounded progressive Recents disclosure, and PR #303 reconciled catalog-valid
benchmarks with explicit zero price bars before confirmation. PR #304 then
completed distinct Quick take, Explain result, typed Try next, and recoverable
failure ownership across live turns, durable jobs, reload, English, and
Spanish. PR #305 then completed issue #253's deterministic decision-first
recall projection and panel as `88ab906d`. PR #306 completed the Full
Omnisearch memory-inspector journey as `b71f1eaf`: one ranked conversation row,
bounded object-first transcript recall, jump-to-match, deterministic dossiers
and asset rollups, exact decision filtering and mutation refresh, and
provider-free **Run it fresh** composition. The accepted implementation keeps
the #232 pagination/cursor boundary and #252 navigation-race guarantees, adds
no RAG/embeddings or durable recall model, and closes the Omnisearch product
lane without claiming deployment or tester exposure.
PR #316 subsequently completed issue #309's bounded run-dossier history and
effective-decision browser as `9aa209d4`. PR #318 made accepted-turn downstream
failures remain assistant-owned across reload and Retry as `f6d0981e`, followed
by the test-isolation checkpoint `1ed8d4f0`; issue #313 is closed. PR #315 added
the current-conversation activity rail as `6e20328c`. PR #317 then added one
central keyboard-shortcut registry, localized help overlay, and shared Recents
and Settings quick-jump behavior as `2ff6f3c6`, without changing Cmd/Ctrl+K
Omnisearch or the existing F2 rename binding. PR #324 aligned Recents hints with
that registry as `812c8fef`, and PR #311 then completed the typed, provider-free
current-data retest action as `51984a42`; issue #310 is closed.

The next integrated group adds bounded product and release-readiness work:
registered-only avatar themes through PR #312 (`40eba1f6`); public-alpha
capacity, capped-key, requested-access, approval-email, and hosted-proof
mechanics through PR #319 (`1c3775aa`); one shared frontend failure vocabulary
through PR #320 (`53c36d40`); auth copy, localized errors, and consistent card
containment through PRs #323, #325, and #328 (`c1a13949`, `05fbef06`, and
`403ea114`); and removal of the unavailable Release Notes row through PR #327
(`22bec7da`). Public account access stayed founder controlled at that landing
despite the completed technical-readiness proof. The founder opened it in
production on 2026-08-12, so public registration is open now.

PR #329 added the durable backend/data conversation-activity and read-state
foundation as `8a5d621b`; PR #331 completed its chat/Recents frontend consumer
as `ec3a0a52`. The #329 migration is not claimed as hosted by these integration
merges. PR #326 closed issue #321 as `8e2a6217` with bounded
invisible/interactive CAPTCHA deadlines and an accessible localized challenge
dialog. PR #330 then completed deferred Guest bootstrap as `94476226`, keeping
anonymous identity and CAPTCHA acquisition behind the first submission while
preserving #331 activity ownership. Issue #314 remains a separate API evidence
gap discovered during typed-retest delivery, not unfinished #310 work.
PR #348 then self-hosted the canonical Inter and Space Grotesk variable fonts
as `38874bae`, removing the Google Fonts network dependency from build,
runtime, and provider-free browser QA. It added no environment variable,
deployment, API, schema, or migration requirement. The separate low-priority
fallback-order alignment remains issue #350.
PR #362 then repaired the sanctioned live-eval harness as `b2e8975c`, closing
issue #361: the explicit `ARGUS_EVAL_ENV_FILE` environment now preloads before
Argus imports, so calendar-aware live cases exercise real market sessions and
report `calendar_alignment` truthfully instead of failing 17 of 39 cases under
the leaked synthetic fixture calendar. The change is confined to
`tests/evals/` and added no environment variable, deployment, API, schema, or
migration requirement.
PR #355 then closed issue #336 as `c01d5730`: provider-resolved assets and
capital supplied in a terse opening turn survive into clarification and the
confirmation card, with post-LLM provider-context reconciliation removing only
stale asset blockers once every extracted traded-asset mention is accounted
for. Mixed, ambiguous, underfilled, overflow, and cross-class contexts stay
blocked. Accepted evidence includes the exact-head live-eval gate and a
founder-witnessed browser reproduction of the original G-01 transcript. It
added no environment variable, deployment, API, schema, or migration
requirement.
PR #353 then closed issue #337 as `7e4c58f8`: a rail needs-attention tick for
a clarification clears only when a later active confirmation is proven, via
backend-owned typed metadata (`strategy_path_id`, `source_result_run_id`, and
provenance-checked user values), to continue the same strategy path; unproven
or unrelated confirmations fail closed. The Guest rail keeps its single
legitimate completed-run tick visible. The first exact-head verification
failed and was repaired (e2e seed omitted real workflow metadata) before
acceptance; the final head passed the real local-Supabase Guest replay
independently. It added no environment variable, deployment, API, schema, or
migration requirement.
PR #357 then closed issue #340 as `9f97f1dc`: guest Omnisearch dossiers keep
Add/Edit decision actions visible and conversion-gate activation through a
typed `available | account_conversion_required` availability contract across
Python, OpenAPI, and TypeScript, then resume the exact run, decision state,
and note after conversion. The server remains authoritative and no guest
write path exists; the gated presentation activates only for clients
declaring the additive `dossier_decision_conversion_v1` capability header, so
legacy clients keep the prior stripped behavior. `docs/API_CONTRACT.md` and
`docs/api/openapi.yaml` changed in-PR with compatibility tests; it added no
environment variable, deployment, schema, or migration requirement. Issue
#341 is now unblocked for dispatch from the post-#357 integration head.
PR #356 then closed issue #343 as `48de2f3f`: menu-row hover/selected
highlights use one rounded inset-pill geometry across Settings, Profile,
Recents overflow, and chat-header menus, with destructive-red and neutral
action colors unchanged. Class-only change; hover evidence is committed
in-repo under `docs/reports/evidence/issue-343/`. The founder explicitly
overruled the absent on-PR Codex review after personal visual checks. It
added no environment variable, deployment, API, schema, or migration
requirement.
PR #352 then closed issue #334 as `0942507b`: Omnisearch and active-chat
keyboard actions share one OS-aware behavior registry (EN/es-419 labels and
execution from one source), with a contextual shortcut legend that stays
quiet at rest, contextual Omnisearch actions, arrow navigation, quick jump,
keyboard-aware delete confirmation, and a responsive help sheet. Its first
head was returned for composed-tree modularity violations and re-landed
after genuine extraction; ChatInterface.tsx now sits exactly at its budget
limit, so future lanes touching it must extract first. It added no
environment variable, deployment, API, schema, or migration requirement.
PR #375 then closed issue #368 as `c334cf3e`: the stated-starting-capital
recheck now also runs on `unsupported_or_out_of_scope` turns, so an explicit
non-DCA capital amount survives capability-honesty recoveries without
changing the unsupported verdict, dates, assets, or DCA behavior. Accepted
evidence: red-first mocked regression plus one targeted live rerun of the
original news-sentiment case, re-captured at the exact final head. The
founder waived the ceremony reconcile-merge commit after an independently
verified no-overlap disposition (all intervening landings were docs or
web-only). This fix upgrades PR #363's pending evidence bar. It added no
environment variable, deployment, API, schema, or migration requirement.
PR #370 then closed issue #341 as `c324f877`: explicit `timestamptz`/`uuid`
casts on the nullable first-page dossier cursors repair the guest Decision
history 500 (`AmbiguousParameter` on the untyped null comparison) — not a
guest-guard or transport failure, and the issue was nearly closed as
not-reproducible before the mandated real-browser re-evidencing surfaced
the true failure in the Postgres reader. Evidence: same-session 500→200 at
the exact head with the screenshot committed in-repo; guest workspace
isolation re-proven. It added no environment variable, deployment, API,
schema, or migration requirement.
PR #360 then closed issue #349 as `42d96da7`: conversation-activity truth is
now verified with durable in-repo evidence — registered manual-unread
persists, survives reload, clears, and never reorders Recents; each Guest
state is individually classified with owner actions account-only. Docs and
four committed screenshots plus one date-stable Playwright fixture line; no
product behavior, API, schema, or migration change.
PR #374 then closed issue #371 as `d8c7070a`: `_as_datetime` normalizes
Postgres-trimmed fractional seconds and trailing `Z` offsets with explicit
regex-free string handling before parsing (founder-directed), repairing the
~1-in-10 broken-Recents failure observed in live QA, and the API middleware
now retains the exception in its failure log while keeping the HTTP body
generic. No environment variable, deployment, API, schema, or migration
requirement was added.
PR #351 then closed issue #342 as `30af0dca`: the guest-to-account handoff
awaits the promise-returning Recents refresh after ownership confirmation and
before a pending action resumes, so the claimed conversation is visible
immediately; ordinary mutation refreshes remain fire-and-forget. Accepted on
a founder-witnessed live conversion journey at the exact composed tree plus
full composed-tree gates. Its first live-proof attempt discovered #371 and
#372; the integration-side headroom extraction `34782abd` preceded this
landing. No environment variable, deployment, API, schema, or migration
requirement was added.
PR #373 then closed issue #372 as `81e7a1ac`: signup eagerly creates the
destination profile (guarded against Supabase's obfuscated duplicate
response) so a brand-new account's first-login claim satisfies the handoff
foreign key; optional usernames are prevalidated case-insensitively before
Auth-user creation under transaction-scoped advisory locks, returning typed
`409 username_taken` for new-account conflicts while existing-email requests
keep the provider's indistinguishable duplicate path. Three review rounds
each removed a real regression (FK failure, email oracle, username oracle).
No environment variable, deployment, schema, or migration requirement was
added; `docs/API_CONTRACT.md` records the username semantics.
PR #359 then closed issue #345 as `a35bb29f`: recommendation follow-ups
inherit every still-applicable owned fact (assets, capital, window,
timeframe, benchmark, modeled costs) unless the user changes them, with the
historical result immutable and the new confirmation active — routed through
the shared clarify contract with model voice and degraded fallback. Accepted
at the full clean bar: live 40/40 with no waivers, strategy-diverse browser
proof (weekly DCA with recurring contribution; SMA 50/200 inheritance), and
full deterministic gates. No environment variable, deployment, API, schema,
or migration requirement was added.
PR #358 then closed issue #339 as `7b3221a1`: the artifact-edit planner
derives required typed targets from the entire turn — any operation count
over the full edit vocabulary — and only plans that provably materialize
every target may claim ready_to_confirm, verified against the real
application path; partial application retries or asks, and unsupported
content declines to the normal flow. Six adversarial review rounds hardened
coverage against faked completeness. The lane's 24/41 live report was
independently diagnosed and lane-confirmed as the known root-.env
synthetic-calendar misconfiguration, corroborated by #359's adjacent 40/40.
Issue #335 is unblocked and stacked for the next cycle. No environment
variable, deployment, API, schema, or migration requirement was added.
PR #354 then closed issue #346 as `4a6a237a`: the guest quota-exhaustion
message states the actual reset time and offers conversion; the guest
allowance rises to two simulations via migration
`20260802090000_raise_guest_simulation_allowance.sql` (landed in-repo and
preview-proven; hosted application remains a promotion-runbook step);
visitor prechecks use the daily reset horizon; first-admission
classification is atomic; and the authoritative public-launch canary in
`docs/GUEST_PUBLIC_LAUNCH_SAFETY.md` now expects the two-simulation policy.
`first_result_completed` idempotency is explicitly deferred to #376. The
lane also fixed a real guest chat-stream cookie-auth gap its browser matrix
exposed, and its dead-at-birth Supabase preview branch was deleted and
recreated to prove the migration on hosted preview infrastructure.
PR #366 then closed issue #344 as `2b023576`: recent-IPO, trending-crypto,
multi-category, and escalation requests route through the typed discovery
path with resolver-validated cited candidates; transient failures retry and
genuinely recover; configuration failures stop honestly without dead-end
affordances or wait-promises, redirecting to provider-free symbol testing;
and citation fallback evidence is bounded and fail-closed. Sixteen per-SHA
in-repo evidence sets with probe-vs-proof labeling; provider-mode breadth is
parked as #377. This was the cycle's final landing before the promotion
freeze.

Current product and assignment ownership follows
[documentation authority](../DOCUMENTATION_AUTHORITY.md). The interim roadmap,
P2 roadmap, and earlier decision memo are historical references. This document
preserves staging/process safeguards and a dated integration ledger; it does
not assign current product work.

For release-gate and canary decisions, the archived decision memo is
later-context only; it does not replace the release references below.

For smoke, canary, manifest, and deployment discipline, use
`docs/specs/private-alpha-ci-cd-sota.md`, `docs/PRIVATE_LAUNCH_RUNBOOK.md`, and
`docs/release-manifests/TEMPLATE.md`.

## Purpose

This document preserves integration branch-process context after the
private-alpha conversation trust checkpoint. Start new work from the current
remote integration branch and its explicit assignment, using AGENTS.md for
current delivery rules.

The integration branch is a staging lane. It is allowed to collect reviewed work
before a future PR, but it is not a release branch and must not be merged or
deployed automatically.

## Current Release Gate Reference

The private-alpha promotion path still uses the CI/CD SOTA gate in
`docs/specs/private-alpha-ci-cd-sota.md` plus the operator instructions in
`docs/PRIVATE_LAUNCH_RUNBOOK.md`.

**Production promotion executed 2026-08-05:** the sixteen-landing checkpoint
batch plus the acceptance-walk fixes shipped to production at `7ef89a90`
(`argus-api`, `argus-app`, and workflow version `wfv-d9p88253erlc73d3u8s0`).
Evidence: [`docs/release-manifests/2026-08-05-main-production-promotion.md`](../release-manifests/2026-08-05-main-production-promotion.md).
`main` and `codex/private-alpha-next` were identical at that SHA; the branch
resumes its staging-lane role for the next cycle from this baseline.

Before testers are invited, the release captain must prove:

- local smoke passed for the candidate SHA;
- `argus-api` and `argus-app` latest Render deploys are `live` at the candidate
  SHA;
- Render release config audit produced the expected `env_fingerprint`,
  `workflow_env_fingerprint`, `workflow_env_status=ready`, `workflow_task`, and
  `real_workflow_task`;
- warmup ran `workflow_proof` against the deployed `argus-backtests` workflow
  and emitted `workflow_runtime_provider_mode=live_provider` plus
  `workflow_runtime_proof=ready`;
- the `Private Alpha Canary` workflow or equivalent manual commands passed both
  English, Spanish, and provider-path canaries;
- the canary evidence artifact is retained as `private-alpha-canary-evidence`;
- a release manifest exists from `docs/release-manifests/TEMPLATE.md` and names
  SHA, env fingerprints, workflow env status, canary evidence, rollback target,
  approver, and backtest service mode.

Production deploys remain manual and founder-directed. No production deploy
happens from this branch unless the founder explicitly asks for a deploy check.

## Branch Model

Use this flow:

```text
main
  -> codex/private-alpha-next
       -> codex/<focused-high-leverage-slice>
       -> codex/<focused-low-risk-debt-slice>
```

Rules:

- `main` remains the clean release checkpoint.
- `codex/private-alpha-next` is the only integration staging branch.
- Codex worker branches start from `codex/private-alpha-next`.
- Create worker worktrees as siblings of the repo, never nested inside another
  Argus checkout. Nested worktrees can inherit a parent `.env` through dotenv
  upward search, which can silently turn mocked runs into live LLM/provider
  calls.
- Workers do not push directly to `main`.
- Jules work is decommissioned for the near term. Do not create or maintain
  `jules/**` branches, `codex/private-alpha-next-jules-intake`, or Jules intake
  PRs unless the founder explicitly reactivates that workflow.
- External async agents, if reintroduced later, must use a fresh
  founder-approved delegation model and must not push directly to
  `codex/private-alpha-next`.
- Codex reviews worker diffs before they are merged or cherry-picked into the
  integration branch.
- High-leverage work lands in `codex/private-alpha-next` first.
- Every slice ends with tests run, browser QA notes when relevant, known
  caveats, and a conventional commit.
- No production deploy happens from this branch unless the founder explicitly
  asks for a deploy check.

## Claude Review Workflow

Claude review is a bounded review aid, not an always-on push hook.

- During active development, run Claude Code CLI reviews on demand from the
  terminal against a bounded local diff before commit or before internal review.
- For promotion candidates, run Claude review as an explicit gate through a
  manual GitHub workflow, PR label, or review command after the lane is stable.
- Do not run Claude review automatically on every push. WIP branches should not
  accumulate noisy automated review comments before a lane is ready.
- Reviews use `AGENTS.md` ("Commits, PRs and review"), the canon docs, the
  active roadmap or lane spec, and the correct parent branch for the diff.
- Promotion-gate review focus is defined by Yelena's ship playbooks (internal).
  The integration workflow especially depends on regression detection,
  language-agnostic runtime-spine protection, modularity, API contract drift,
  frontend truth ownership, tests/browser-QA gaps, and release-gate discipline.

## Quarantine Reference Branches

These branches are intentionally preserved as reference material, not as merge
sources:

- `codex/private-alpha-next-quarantine-fc231e8`: preserves the broader P2
  direction and UI/product ideas, but its backend/runtime/data scope
  destabilized Argus. Use it only for product direction, UI salvage candidates,
  tests, and anti-pattern evidence.
- `codex/private-alpha-next-p2.1-quarantine`: preserves a narrower P2.1 slicing
  attempt around capabilities and indicator truth, but it again drifted against
  Argus runtime principles. Use it only for cautionary evidence, possible test
  cases, and scope lessons.

Do not broad cherry-pick or merge from either branch. Any salvage must be
rebuilt from current `codex/private-alpha-next` after a bounded roadmap slice is
approved.

## Current Closed Items

Do not reopen these as debt unless a new bug is reproduced:

- Fast GitHub CI baseline exists.
- Manual CD remains manual.
- Post-merge `argus-app` deploy smoke passed on `2fc4773`.
- Empty composer send tooltip exists.
- Composer caret, placeholder, and `@` button alignment were polished for the
  known empty/focused/clicked states.
- Restored archived/recently-deleted chats refresh without the original stale
  list smell.
- The old static `@` preview was replaced with provider-backed discovery plus
  the supported indicator catalog.
- Asset discovery quality is closed for this batch: provider and indicator
  search results rank exact ticker/alias matches first, common crypto/currency
  aliases replace the full typed phrase, repeated browser-session discovery
  queries use the local cache, and stale visible results cannot be selected
  while a newer query is loading.
- The misleading "share conversation id" pseudo-action was removed.
- Status/action parity is closed for this batch: confirmation, queued/running,
  terminal job, result-card, feedback, retry, and more-menu surfaces now follow
  one artifact lifecycle, internal Copy ID is hidden, and terminal job actions
  remain scoped to the durable artifact instead of transcript prose.
- Result voice cleanup is closed for this batch: Quick take and Explain result
  remain distinct, Explain result uses the deeper fact-grounded breakdown
  surface, and the old duplicate result-card Try next action remains removed.
  PR #304 adds the successor surface: capped typed rows under one localized Try
  next owner, with ordinary conversational turns still handled by the LLM chat
  brain.
- Local live QA proof was captured on 2026-06-11 in QA mode with real Supabase
  auth and API persistence: a GOOG buy-and-hold conversation rendered the
  confirmation card, completed result card, Quick take, and Explain result;
  no visible Try next, Quick Breakdown, Copy ID, or console/API regression was
  observed.
- Pre-merge internet readiness passed on 2026-06-11 for commit `dd65bf6`:
  Render `argus-api` deploy `dep-d8lj6ureo5us73fanrcg` and `argus-app` deploy
  `dep-d8lj8cjtqb8s738jf28g` both reached `live`; warmup passed in
  `real-workflow` mode; the authenticated canary conversation
  `d2fba747-bb93-45be-a48d-0fc944982423` completed durable job
  `93c89ccf-fb88-4ae2-ba93-4e0ab7b821c6` with run
  `e654ed96-efc0-44d6-86fe-033383c2d625`; and a deployed browser shell smoke
  rendered the unauthenticated front door without new console errors after
  reload.
- Post-merge main deploy passed on 2026-06-12 UTC for commit `f335d78`:
  Render `argus-api` deploy `dep-d8lkvl48aovs73dmc1dg` and `argus-app` deploy
  `dep-d8lkvnm7r5hc73d968k0` both reached `live`; warmup passed in
  `real-workflow` mode; the authenticated developer canary conversation
  `4ac80db0-5eb2-40cc-9a5b-a232c73ace01` completed durable job
  `2d65a145-94b8-404e-a949-2f0e0907d51a` with run
  `f17c8578-78b0-4bd6-82a2-24aaf17feff9`; and the canary confirmed the
  confirmation card, `run_backtest` action, async job/run result, LLM readout
  voice, and persisted messages.
- `docs/archive/LAUNCH_GATE_FINAL_CLOSURE_PLAN.md` is archived historical context.
- Adaptive result-chart range switching is complete at PR #264: viewport-only
  presets and Custom/Reset preserve canonical result truth and passed live
  EN/ES desktop/mobile QA.
- Account recovery and session controls are complete at PR #261: Settings ->
  Security is reachable and recovery, password change, and current/other/all
  session actions passed real-auth QA.
- Usage allowance truth is complete at PR #259: Settings -> Usage is reachable,
  hourly/daily message and simulation truth is backend-owned, accounting is
  durable and replay-safe, and exact-head real-auth/local-persistence QA passed.
- Executable capability truth is complete at PR #266 / issue #241: supported
  golden cross reaches the ordinary runnable path; recognized non-executable
  momentum breakout, news-sentiment rules, and future-performance requests stay
  non-runnable; compatible facts survive recovery; and only an explicit
  supported alternative plus a historical period creates a new confirmation.
  Final candidate `e10bdd2` passed founder-visible browser QA and landed as
  `bbd1d2b`.
- The Always Progresses continuity baseline is complete at PR #268: ordinary
  and action retries are durable, Run admission/reconciliation is exact-once,
  completed results remain immutable, and the bounded EN/ES browser matrix
  passed. It landed as `847c413b` and remains a standing quality bar rather
  than an open-ended repair program.
- Calendar-materiality classification is complete at PR #267: routine
  exchange-calendar alignment stays quiet while provider-coverage truncation
  receives one typed, reload-stable notice. It landed as `d6d1134`.
- The bounded chat-header and onboarding cleanup is complete through PRs #274
  and #275: owner controls follow the active chat, and the explicit
  private-alpha onboarding product has been removed. They landed as
  `291b58f7` and `88ae8c77`.
- Stale Run settlement is complete at PR #277 / issue #273: stale actions
  create no compute, settle to typed Updated truth, preserve the latest
  actionable confirmation, and remain stable after reload. It landed as
  `2d5a2b52`.
- Supported strategy-transition preservation is complete at PR #278 / issue
  #270: buy-and-hold can transition to a typed 50/200 SMA crossover while
  preserving assets, capital, dates, daily timeframe, benchmark, and modeled
  costs through confirmation, launch projection, and reload. It landed as
  `b80d95a2`.
- Modeled-cost preservation is integrated from PR #280 at `d16f7496`: asset,
  date, capital, and strategy edits preserve explicitly owned fee/slippage
  assumptions; card and natural-language edits share the canonical evidence
  boundary; explicit zero clears costs; and confirmation, launch, and reload
  agree. Issue #271 is complete; PR #280's bounded same-chat integration
  journey is the closure evidence. Any later repetition belongs to promotion
  qualification, not issue acceptance.
- Grounded Discovery Search v1 is integrated from PR #276 at `c212107a`.
  Explicit peer/category discovery has one typed route, bounded source-backed
  Search, resolver-validated candidates for equity, crypto, and currency-pair
  assets, persisted EN/ES rendering, honest kill-switch recovery, and
  operational cost evidence. Search is part of the normal Argus shape and
  defaults on; explicit `false` is the emergency kill switch. Issue #244 stays
  open because one comparison phrasing missed the typed route in the sanctioned
  eval; that gap, Render configuration, and an exact-SHA canary are required
  before tester exposure.
- Chat next-move presentation is integrated from PR #281 at `8fde4ac1`, with
  resolver-owned discovery selection identity added by PR #287 at `ea2b3f35`.
  Clarify options, supported follow-ups, and discovery candidates render as
  stacked rows under their owning message; verified candidate reasons remain
  visible; and persisted discovery evidence opens in a source-safe panel
  without another provider call. The shared in-flight lock protects the
  composer and rows in one tab. A selected candidate now carries the identity
  the resolver already verified as a normal asset mention, including across
  durable Retry, without becoming a prepared execution action. Remaining work
  is backend concurrent-turn admission, honest live progress, guest discovery
  allowance, and any general assumption carry-forward beyond selected identity.
- Candidate/entity corroboration is integrated from PR #287. A source-named
  entity must agree with the resolved candidate, preventing unrelated
  cross-class ticker collisions such as a gold miner for a Tron request.
  Crypto-exposure vehicles are currently filtered with true collisions; #244
  owns the deliberate product design needed to surface them safely.
- Guest access is integrated from PR #279 at `53e812e9`: verified anonymous
  identity, one temporary owner-scoped workspace, fixed lifetime allowances,
  exact-once settlement, one simulation, conversion/claim, cleanup, Guest
  shell, capability gates, and privacy-safe funnel evidence. Guest defaults on
  with explicit-off rollback; public-account access is separately founder
  controlled and has been open in production since 2026-08-12.
  Issue #293 is closed with no-defect evidence after one real guest session
  crossed the one-hour JWT boundary without losing its conversation or
  workspace. Hosted configuration, canary, and public traffic remain later
  release gates.
- Backend verification is provider-free by default after PR #282 at
  `059f8e82`: root test fixtures force synthetic market data and keep provider
  credentials explicitly empty so dotenv cannot silently restore them. Both
  alpha API suites are part of `backend-checks`.
- Backend CI is directory-complete after PR #286 at `75e87206`: the gate runs
  the full `tests/` tree, the stale pure-approval fixture is corrected, and a
  guard test prevents the workflow from returning to a curated file list.
  Issues #283 and #284 are closed. This changes verification coverage, not
  runtime behavior.
- Bounded database pagination and search are complete at PR #285 / issue #232:
  Conversations and Messages use stable keyset reads, completed-result
  projection uses bounded batches, and History and Omnisearch/Idea Ledger
  bound their source candidates while preserving public cursor compatibility,
  ordering, ownership, ranking, exact ledger groups, and canonical artifacts.
  It landed as `7b7920bb`. The founder-accepted sparse/deep/final History Run
  scan exception remains documented: returned candidates and normal measured
  distributions are bounded, while a maintained History read model is deferred
  scale architecture.
- Browser-session transcript reuse and navigation race safety are complete at
  PR #299 / issue #252. Fresh and stale conversations render immediately from
  the bounded user-and-conversation cache; true cold misses replace the prior
  transcript with a delayed truthful retrieval state; retired loads cannot
  commit over the latest destination; and destination-owned failure/Retry,
  scroll restoration, auth clearing, EN/es-419, keyboard, and reduced-motion
  behavior passed exact-head browser QA. It landed as `f368febb`. Profiling did
  not justify prefetch or virtualization, so neither was added.
- Comparison grounding and discovery-act continuity are complete at PR #300 /
  issues #292 and #296. Company names reach the provider-backed resolver,
  unsupported named comparison targets reconcile to the class default with a
  localized pinned disclosure, and a pending confirmation cannot capture a
  typed discovery ask. It landed as `c21f842f`.
- Progressive Recents disclosure is complete at PR #302 / issue #245. Recents
  uses the bounded chat-only conversation endpoint, caps each loaded unpinned
  time group at five until explicitly expanded, and loads older pages only
  after an accessible single-flight action. It landed as `928dcdbb` while
  preserving PR #299 switching, race, selection, attention, and reload truth.
- Benchmark price-coverage reconciliation is complete at PR #303 / issue #301.
  An explicit provider zero-bars response for a catalog-valid benchmark
  reconciles to the class default at card time with the existing localized
  disclosure; transport failures remain owned by the run path. It landed as
  `da9f8500`.
- Result and recovery surface ownership is complete at PR #304 / issue #249.
  Quick take owns the glance readout, Explain result owns grounded
  comprehension, stacked typed rows own Try next, and retryable composition
  failures render distinctly and resolve in place. Durable job projection,
  reload, non-repetition, accessibility, and English/Spanish parity were
  included in the accepted lane evidence. It landed as `59a274c3`.
- Fact-preserving recovery is complete at PR #288 / issue #272: stale or
  failed actions restore the latest usable canonical confirmation or result
  anchor, preserve assets, capital, requested/effective dates, daily timeframe,
  benchmark, rules, and modeled costs, and ask only for genuinely missing
  fields. Prior results remain immutable, later explicit edits supersede
  recovery state, and recovery creates no duplicate job, Run, or usage.
- Requested/effective period truth is complete and issue #251 is closed. PR
  #262 established the shared coverage contract, PR #267 classified quiet
  calendar alignment versus material provider truncation, and PR #268
  preserved the resulting artifact through continued conversation and reload.
  PR #297 completed the trajectory-ledger reconciliation as `09044231`,
  removing stale #241/#251 masks while preserving #239's exact current
  failures. Issue #243 is closed; promotion evidence remains solely with #233.
- Hosted cost-ledger visibility is repaired and issue #246 is closed. The
  existing `20260702000001_add_cost_ledger_entries` migration was applied
  directly to the hosted Argus Supabase project with matching migration
  history. RLS and service-role-only append/read privileges were verified; no
  application commit, deploy, or PR was required. See
  `docs/reports/issue-246-cost-ledger-closure-evidence.md`.
- Structural OpenAPI compatibility is complete and issue #234 is closed. PR
  #289 landed as `8a66f0ba`: generated FastAPI structure remains authoritative,
  the checked artifact is reproducibly generated, and CI enforces normalized
  public path/method, parameter, request/response schema, required-field, enum,
  exclusion, and server-prefix compatibility. Both PR and post-merge CI passed.
  PR #290 then landed the compatible request-size and correlated RFC 9457
  failure boundary as `b073b1a0`; issue #235 is closed.
- Chat request and correlated-failure ownership is complete at PR #290 /
  `b073b1a0`. Declared and chunked bodies enforce the same early ingress
  ceiling; typed field/list/depth/serialized-size limits fail before expensive
  work; unexpected exceptions preserve CORS and return sanitized RFC 9457 JSON
  with one header/body/log request id. Rejection isolation, exact-boundary
  acceptance, canonical SSE stability, OpenAPI regeneration, and structural
  compatibility are directly tested. PR and post-merge CI passed.
- Guest grounded-discovery metering is integrated from PR #291 at `f1e65dde`.
  Guests receive two searches per visitor per day, renewing a temporary
  workspace does not reset the allowance, and a configurable global daily
  ceiling bounds total attempted Search spend. The additive
  `visitor_usage_counters` migration is integrated but still requires
  application to each hosted target during promotion. Issue #244 remains open
  for the broader discovery activation and accepted follow-up register.
- Discovery continuity PR #295 is integrated at `8f17a45e`. Resolver-verified
  candidate rows are now the default path; paid Search is reserved for
  explicit requests or current-fact needs. Typed retry and fair charging,
  async provider offload, incomplete-rule copy, and EN/es-419 J1/J2 continuity
  are proven.
- Discovery and Guest continuity PR #298 is integrated at `ba0aa2f6`.
  Search and verification emit truthful live progress, each discovery row owns
  its citation action, and Guest message/simulation limits settle against a
  privacy-safe visitor/day identity across temporary-session renewal. This
  completes the planned second pass, not promotion: hosted migrations,
  configuration, and exact-SHA canary gates remain open.

## P0 Reintegration Checkpoint

The clean reintegration strategy is now part of the process model:

- `codex/private-alpha-next` remained the clean integration gate.
- contaminated autonomous work was preserved under
  `codex/private-alpha-next-quarantine-fc231e8` for read-only reference.
- P0 continuity was rebuilt as a focused clean slice at `bbd9f10`.
- quarantine commits may be inspected for ideas, tests, and failure evidence,
  but runtime code should not be broadly cherry-picked.

## Historical Follow-Up Register (August 2, 2026)

This register preserves the checkpoint's follow-ups. Verify current issue state
and obtain an explicit assignment before taking work from it:

1. **Finish the remaining interim product outcome and activation gates**
   - Grounded discovery now includes the PR #295 continuity pass at
     `8f17a45e`, PR #298's second pass at `ba0aa2f6`, PR #300's comparison
     grounding and discovery-act continuity at `c21f842f`, and PR #303's
     benchmark coverage reconciliation at `da9f8500`. Do not rebuild the cheap
     verified rows, Search-exception policy, live progress, citation ownership,
     visitor/day Guest settlement, or comparison corridor. Keep #244 open only
     for the accepted exposure-vehicle product decision and the hosted
     migrations, Render configuration, and exact-SHA canary.
   - Full Omnisearch may now build against the accepted grounded-discovery
     contract. Its owner must reconcile onto this checkpoint and must not
     invent discovery truth or implicitly activate Search.
   - Always Progresses is delivered and now acts as the quality bar for these
     slices; it is not the next broad pillar to redispatch.

2. **Advance bounded continuity follow-ups by owner**
   - #269 landed through Guest PR #279 at `53e812e9` and is closed. Do not open
     a second runtime lane.
   - #271 landed through PR #280 at `d16f7496` and is closed. #272 landed
     through PR #288 at `9f3453a3` and is closed; do not open another modeled
     cost or canonical recovery lane without a new reproduction.
   - #273 is closed at `2d5a2b52`. #249 is closed through PR #304 at
     `59a274c3`; Quick take, Explain result, typed Try next rows, and
     recoverable failure now have distinct owners while preserving Guest
     hydration, discovery rows, conversation switching, and bounded Recents.
     No artifact-presentation follow-up remains without a new reproduction.
   - The exact handoff table lives in
     `docs/specs/private-alpha-interim-roadmap.md`.

3. **Evidence-aware idea loop source thesis**
   - Perplexity, citations, research-to-testable-hypothesis loops, inbox briefs,
     saved research, and monitoring remain design/reference material until the
     active roadmap starts a bounded slice.
   - `docs/specs/evidence-aware-idea-loop.md` is preserved in `docs/specs/` as
     the source thesis that informed
     `docs/specs/private-alpha-next-decision-memo.md`. It is not the active
     sequencing document.
   - The decision memo and P2 roadmap preserve historical rationale and
     contracts. Use [documentation authority](../DOCUMENTATION_AUTHORITY.md)
     and the explicit assignment for current work. This source thesis does
     not authorize implementation.

## Integrated Guest Checkpoint And Later Promotion Gates

PR #279 landed on `codex/private-alpha-next` as `53e812e9`. The section below
preserves its migration, ownership, rollback, and later promotion contract; it
is not an active worker-branch instruction.

Migration order is fixed:

1. `20260724101324_add_guest_workspaces.sql`
2. `20260724102309_add_guest_session_allowances.sql`
3. `20260724102645_guest_conversation_and_cleanup.sql`
4. `20260724110000_restore_settle_only_usage.sql`
5. `20260724110100_serialize_guest_feedback.sql`
6. `20260724110200_align_guest_cleanup_candidates.sql`
7. `20260724211312_guest_workspace_handoffs.sql`
8. `20260724223000_replace_guest_conversation.sql`
9. `20260724230000_harden_guest_public_boundaries.sql`
10. `20260725220148_fix_expired_guest_complete_graph_cleanup.sql`
11. `20260726001954_isolate_guest_cleanup_candidates.sql`
12. `20260726001955_enforce_guest_terminal_message_limit.sql`
13. `20260726002158_respect_permanent_conversation_ownership.sql`
14. `20260726014754_isolate_poisoned_guest_orphans.sql`
15. `20260726185021_harden_guest_lifecycle_ownership.sql`
16. `20260727230000_add_visitor_usage_counters.sql`
17. `20260728120000_visitor_keyed_guest_settlement.sql`

The earlier message-settlement and atomic-backtest-admission migrations remain
prerequisites and must retain their existing order. Integration must reset a
fresh local database and rerun the zero-skip guest Postgres/Auth matrix before
promotion. Migration 16 adds an opaque, visitor-owned daily discovery counter
and global attempted-search bucket. Migration 17 re-keys Guest message and
simulation settlement to the same privacy-safe visitor/day boundary. Both must
be present before Guest grounded discovery is exposed.

The conversion contract has two owners:

- ordinary signup creates a different permanent Auth UUID, binds it to the
  workspace-lifetime signup handoff, and claims the complete guest graph after
  immediate session creation or first confirmed login;
- an existing registered account claims the complete guest graph through the
  short-lived, email-hash-bound, single-use server handoff. Login completes
  the claim before returning its session and can reconcile one ambiguous
  same-destination response without repeating transfer.

Neither path copies visible prose in the browser or merges guest lifetime
counters into registered hour/day counters. Guest server/bootstrap and
presentation flags default on as emergency kill switches. Rollback is flags
first: explicitly disable the frontend guest presentation, then server guest
bootstrap. Leave public-account access untouched, because guest rollback does
not close public registration. Do not roll back by deleting guest
rows or reverting already-applied migrations.
The server guest flag is the creation gate: disabling it stops new anonymous
sessions while existing verified guests drain to conversion, fixed expiry, or
transactional cleanup.

Always Progresses, Grounded Discovery, modeled-cost preservation, Guest, and
visitor-owned Guest discovery metering are reconciled at the integration
checkpoint. Before promotion to `main` or public traffic, apply migrations
through `20260728120000`, configure
`ARGUS_DISCOVERY_GLOBAL_DAILY_CEILING`, and complete
`docs/GUEST_PUBLIC_LAUNCH_SAFETY.md`: branch-deployed exact-SHA canary, hosted
anonymous Auth and server-validated Turnstile, trusted-origin/rate-limit
verification, hard provider budget, scheduled cleanup ownership, first-traffic
monitoring, release manifest, and founder traffic/cost approval.

## Historical Evidence Retention

Completed specs, plans, and browser reports remain in place when GitHub issues,
PR descriptions, or closure ledgers link to their paths. Their status banners
mark them as completed execution records or superseded observations. Moving
those files into `docs/archive/` would break evidence lineage without reducing
active ambiguity.

Current document ownership is defined by the authority map. The MVEE owns
experience; explicit packages own assigned work; this document and release
references supply applicable process safeguards. Retired strategic narratives
have archive copies and compatibility pointers. Completed Always Progresses
plans and dated reports remain regression evidence, not dispatch instructions.

## Known Non-Blocking Debt

Track these as future validation slices, not blockers for the current main
deploy:

1. **Composer paste and long copied-result handling**
   - Live observation on 2026-06-11: `Copy Plain Text` can copy a non-empty
     result breakdown into the Codex browser tab clipboard and show `Copied`,
     but pasting back into `ChatInput` can fail when the browser does not
     support or allow the current `document.execCommand("insertText")` paste
     path after the paste handler calls `preventDefault`.
   - Product concern: long copied result text can overwhelm the persistent
     composer if pasted inline. Frontier chat products often promote long
     copied content into file-like attachments, but Argus should not fake
     `.txt` attachments while the current OpenRouter-backed chat path does not
     support text-file inputs.
   - Future validation should confirm normal-browser versus Codex-browser
     behavior, define an Argus-scale long-text paste treatment such as capped
     inline paste, paste preview, or explicit large-text handling, then replace
     the `execCommand` paste path with a modern contenteditable or state
     insertion path and add Bun plus browser QA.
   - This is not ready for delegated implementation until the product behavior
     is scoped. A future scout may later run a read-only validation inventory or
     help draft a GitHub task prompt if external-agent work is reactivated.

## Deferred External-Agent Scout Candidates

External async-agent work is decommissioned for the near term. If the founder
reactivates it later, these are the only categories that should be considered
for bounded scout or janitor work:

- Docs classification proposals: canon, active plan, historical evidence,
  archive candidate.
- Dead-code candidate inventories for active-tree code.
- Large-file inventory with proposed extraction seams, without performing broad
  refactors.
- Small test coverage additions around already-stable behavior.
- i18n/key consistency reports and narrow copy fixes.

External agents must not touch:

- Supabase migrations, RLS, auth, or service-role behavior.
- Render config, deploy scripts, workflow env sync, or production env names.
- `src/argus/agent_runtime/stages/interpret.py` or runtime routing without
  explicit approval.
- LLM provider plumbing, OpenRouter profiles, Perplexity integrations, or model
  fallback chains.
- Backtest engine execution semantics.
- Frontend state that invents backend facts.

## Documentation Hygiene

Use these classes:

- **Canon**: `docs/PRODUCT.md`, `docs/ARCHITECTURE.md`,
  `docs/API_CONTRACT.md`, `docs/DATA_MODEL.md`,
  `.agent/designs/argus/DESIGN.md`, and `AGENTS.md`.
- **Active specs**: current milestone docs, including this file and approved
  future specs.
- **Historical evidence**: completed launch/milestone closure reports and
  browser/canary evidence.
- **Archive**: stale plans superseded by merged implementation or newer specs.

The former interim issue dependency map and Wave 0 plan are archived at
`docs/archive/private-alpha-interim-issue-roadmap-2026-07-21.md`. The active
interim roadmap now contains only founder outcomes, retained decisions,
delivery discipline, and current completion truth.

Do not delete historical docs casually. Prefer adding a short status banner that
points to the active source of truth, then archive only after review.

## Verification Expectations

For docs-only changes:

- `git diff --check`
- link/path sanity check for referenced docs

For frontend changes:

- focused `bun test` suites for touched behavior
- `cd web && bun run build`
- browser QA in the Codex browser for visible behavior

For backend/runtime changes:

- focused pytest suite for touched behavior
- `poetry run ruff check src tests workflows scripts`
- local or live smoke only when the change affects runtime/deploy behavior

## Stop Conditions

Stop and ask before proceeding if a task:

- requires new Supabase schema, RLS, or production data writes;
- changes runtime routing or result readout provenance;
- changes Render service topology, env var names, or deploy behavior;
- starts implementing Perplexity Research Lab features;
- needs a product decision about public sharing, privacy, or revocation.
