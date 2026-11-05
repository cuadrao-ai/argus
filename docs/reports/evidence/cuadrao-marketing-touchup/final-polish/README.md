# Final Personal polish and Business photo removal

## Current branding and PR update

The founder authorized updating PR939 and getting CI green while deployment and public forms remain held. Candidate `ece1aa067f6c810dd349fb57742a4eb0bd235ee9` adds canonical light/dark icon-and-wordmark lockups inside the existing footer columns; the large cropped wordmark remains text. Favicon SVG, ICO and Apple icon are generated from the canonical light mark on paper. No signup behavior or dark source artwork changed.

Fresh build, typecheck/lint, 177 unit tests and all 183 browser checks pass (one expected pointer-only skip on touch). Refreshed manifest and 32 screenshots cover16 ES/EN desktop/mobile Chromium/WebKit combinations. Parent inspected footer alignment in both palettes. The local signup demo proxies the same current build; simulated submission and Replay were verified in the in-app browser. Its boundary test passes and refreshed screenshots/clip use only mocked responses. Independent review is clean; its lazy-logo test finding was corrected by scrolling the logo into view before checking load.

Integration advanced during this pass from original base `bbf4da23f01296af4ac639386fe9a0960218a49f` to `43fac94de2672600079f312258908f05747a9d63` (iOS keyboard fix). Its native-only code/tests and native design rule do not overlap Marketing runtime owners, API/data contracts, UI state, migrations, environment variables or affected Marketing tests. Normal one-way merge `ece1aa067f6c810dd349fb57742a4eb0bd235ee9` reconciles the branch. Modularity passes on that merged tree. Marketing build bytes are unchanged by reconciliation; existing behavioral evidence is retained and screenshots pin the merged source. No product worktree/service was edited.

[Original layout archive](../original-layout-archive/README.md) includes a source download, exact commit/tree, checksum, historical screenshot index and isolated replay instructions. The old comparison was restored from that archive on4511 after its old process stopped; original files remain untouched.

CI status belongs to the latest PR939 head/checks. This documentation commit does not assert a future CI result. Deployment, public forms, provider configuration, real email, hosted changes and merge remain held.

## Previous polish checkpoint

October 9, 2026. Current local candidate: `8a45ab0a482b5d7674a50d7c90058915e4fabe00`; runtime source: `1d87ca636`. Later documentation/evidence commits preserve these runtime bytes. This report supersedes historical footer-photo/reveal and editorial-photo descriptions.

## Accepted design and final changes

The founder accepted Personal and asked to lock it. Local tag `codex/marketing-personal-accepted-2026-10-09` points to `3a0f125e5671cf752a9c8c0a9b56f5ab87549e20`; [checkpoint](../personal-accepted-checkpoint.md). Final audit found no reachable Personal design, copy, form or metadata issue requiring another redesign.

Business now omits the florist/accountant section, its captions and illustration disclosure. Founder portrait/signature remain. All Marketing footers end at the static cropped wordmark. Obsolete reveal code and styles are deleted. Historical photo files remain on disk but are not rendered. Personal's accepted form, hand/phone, brand and success motion remain intact.

## Verification

- Production build, TypeScript, lint and diff checks pass; 177 unit tests pass.
- Full desktop/mobile browser run: 181 passed, one intentional pointer-only touch skip, two footer assertion failures. Both failures were a one-pixel scroll rounding difference with unchanged page height, not a reveal or layout defect. The assertion now uses the same one-pixel tolerance as the physical-ending check. All eight affected footer cases pass on rerun. Unchanged passing cases retain their evidence; no runtime changes followed the full run.
- 16 Chromium/WebKit route/viewport combinations pass: Business and Personal, ES/EN, 1440×900 and 390×844. The [manifest](screens/manifest.json) pins 32 page/footer screenshots to the exact candidate. No overflow, footer photos, reveal elements or browser exceptions. WebKit is engine coverage, not a claim of physical Safari/iPhone verification.
- Parent inspected Personal mobile and Business desktop/mobile captures. Three of four Personal Chromium footer captures are byte-identical to accepted evidence; Spanish desktop was visually checked. Independent scoped runtime review returned clean. Final verification-tooling/documentation review is recorded in the handoff.
- Browser suite uses isolated local mock providers on 4540/4541/4542. No real email, signup storage, provider request or hosted change.

## What remains before replacing the old page

1. Carry the accepted local work into PR #939 and refresh the bounded website promotion candidate. Reconcile with current integration, review semantic overlap and obtain exact-candidate CI. This report is local design verification, not release READY.
2. Confirm the actual responsible operator and publish approved ES/EN privacy wording. Older notes record LLC formation as pending; present legal/entity status was not re-verified here.
3. Through the approved operator process, refresh the production migration ledger and applier readiness, apply/verify the existing signup migration, and configure hosting/Supabase. The signup API already implements durable insert, deduplication and removal/suppression. No new backend is needed. Personal can use the independently ordered signup migration; it does not require launching the Consumer product. The runbook's contradictory batch wording is corrected to match its existing independent-prefix analysis.
4. With approval, verify hosted storage, repeated signup, persistence after restart, removal/suppression, failure recovery, desktop/mobile Safari and metadata. Local 4512 intentionally has provider credentials unset. Personal signup does not promise or send an immediate confirmation email; the later availability-notice workflow is separate.
5. Obtain explicit promotion/deployment/public-form and domain/indexing approval, with a named rollback target. Preserve the old site until cutover is approved.

Canonical execution details: [launch runbook](../../../../runbooks/cuadrao-marketing-launch.md). Production state was not changed or freshly audited.

## Continuation

Worktree `/Users/garces/.codex/worktrees/cuadrao-marketing-delivery/private-alpha-next`, branch `codex/marketing-touchup-delivery`. Original integration base `bbf4da23f01296af4ac639386fe9a0960218a49f`; no reconciliation or READY claim in this pass.

GitHub readback on October 9: #939 open draft at `e09ee0e35b3c92546cf86c47f83b2fdbf10b47af`; #927 website promotion open draft at `2d44044e405a4eae37d1c22567a5c3137ff53b7f`; #929 evidence handoff open at `f555e53267b71bc36417fbbbabad9c2c636d1ff9`. Local changes remain unpushed.

Preview: http://127.0.0.1:4512/personal and `/`, listener PID30054, cwd `marketing/`, provider credentials unset. Original comparison4511/PID11951 and mock-signup4513/PID1265 preserved; all three return HTTP200. Verify PID/cwd before any restart. Reproduce captures with `node marketing/scripts/capture-final-polish.mjs`; rebuild before testing any future runtime changes. Tests use `MARKETING_E2E_SITE_PORT=4540 MARKETING_E2E_PUBLIC_PORT=4541 MARKETING_E2E_MOCK_PORT=4542` to avoid preview collisions.

No Business/Consumer product files or services changed. No merge, push, publication, real email, public activation or hosted change. Business visual changes remain available for founder review.
