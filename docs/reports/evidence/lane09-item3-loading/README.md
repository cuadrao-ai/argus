# Lane 09 item 3 loading evidence

The Business initial and cold-chat loading view uses the existing Cuadrao mark.
It waits 150 ms before showing the visible Spanish line `Cuadrando…` and the
single polite screen-reader announcement `Cargando Cuadrao`. A fast completed
load mounts neither indicator. Unmount cancels the timer. English and Personal
conversation copy still comes from the existing locale catalogs. No catalog
keys or English strings were added.

## Source and scope

- Before source is item 2 commit `0b9c2ced3448703296d6c66849f9412fc7d472ae`.
- After source is code commit `6aa2fa107a425a55c2a1e99942519bb8af6925d5`.
- The before run temporarily restored only the six owned runtime files in the
  isolated item 3 checkout. The saved item 3 source was then restored.
- `ChatInterface.tsx` changes only the retrieval import and loading JSX.
  `ConversationRetrievalState.tsx` owns the initial visibility timer and
  Spanish Business loading presentation.
- `business-ui.tsx` owns the row, overview-card and receipt-detail placeholders.
  `BusinessOverviewPanel.tsx` changes only its loading props.
  `ReceiptReviewPanel.tsx` and `ReceiptDossierReview.tsx` change only loading
  layout props. Other existing list callers use the shared row layout.
- Public `web/app/page.tsx`, auth, session, history options, receipt actions,
  permissions, requests and focus logic are unchanged by this item.

The isolated stack starts at the item 2 commit. The root coordinator owns
integration reconciliation and final independent Eval. The root must preserve
urgent auth PR #1178's `useRecentConversations` options when reconciling
`ChatInterface.tsx`. That PR landed as
`466ba25cf69f70ec054a9d094b2d76b16b41a0bd`; its change is outside this worker's
ownership. Worker-tree checks do not establish the reconciled-tree gate.

## Browser proof

All records, responses and sessions are synthetic. The browser blocks every
non-local request. The existing `/dev/business-preview` fixture supplies the
Business application. Only its built-in 240 ms waits are extended to 1800 ms by
the test so screenshots can capture the loading state. The production loading
delay stays 150 ms. No hosted records or provider calls are used.

`web/e2e/business-loading.spec.ts` runs at 1280 by 900 and 390 by 900. For each
width, the committed screenshots cover initial loading, overview, inbox,
expenses, updates and receipt detail before and after. Two additional after
screenshots cover initial loading with Reduce Motion. There are 26 screenshots.

The after browser test checks Spanish visible and polite announcement text,
no horizontal overflow on each loading view, and computed `animation-name:
none` under Reduce Motion for both the mark and skeletons. Geometry checks
verify three overview cards in two desktop columns or one phone column, plus
two desktop receipt columns or one phone column. Receipt preview placeholders
measure 320 px high on desktop and 112 px high on the phone.

The initial full-app view is still blocked on the existing profile probe. The
application shell remains visible during in-page loads. Placeholder geometry
represents the expected content shape; final content height varies with saved
data. These checks do not claim hosted customer acceptance or a real assistive
technology session.

## Checks

- 55 tests pass across `business-loading.dom.test.tsx`,
  `chat-lifecycle-source.test.ts`, `workspace-language-prose.test.ts`,
  `business-approve-next.dom.test.tsx`, and
  `business-approved-revision.dom.test.tsx`.
- Six existing locale tests pass. Full catalog leaf-key parity also passes,
  with 2317 keys in each supported locale and no missing keys in either.
- The eight new DOM tests cover a completed 100 ms load with no indicator,
  a 170 ms load with the approved line and single announcement, timer cleanup,
  a fresh delay on remount, cold-chat copy, canonical English/Personal copy,
  and each decorative skeleton layout.
- Before browser matrix passes 2 of 2. Final after browser matrix passes 2 of 2.
- Targeted ESLint passes for the six runtime files and two dedicated test files.
- Canonical `bun run build --webpack` passes, including Next's TypeScript check.
  The isolated build uses `NEXT_DIST_DIR=temp/loading-build`; Next's automatic
  `tsconfig.json` additions are restored after the check. CI/build configuration
  is unchanged.
- Worker-tree modularity budget passes with no violations. Root owns the
  required check on the reconciled integration tree.
- `git diff --check` passes.

The first browser attempt reused cached inbox data and targeted a desktop nav
button at phone width. Fresh preview routes fixed the test setup; no product
navigation change was made. Standalone broad `tsc --noEmit` reports existing
Bun test declaration errors across the repository. The canonical production
build is the build gate, with no test or type exclusions added.

Full remote CI, unresolved review-thread verification and independent Eval are
pending root coordination. This is an implementation checkpoint, not DONE.

## Local cleanup

The worker stopped its local server on port 3113 and closed its temporary
reference tab. It deleted only its own `.next`, `temp/loading-build`, local
Playwright result caches and named `/private/tmp` scratch files. `du -sk`
recorded 568700 KiB of build/test caches. `df -k` available space rose from
187944704 to 188513524 KiB, a measured gain of 568820 KiB, about 555.5 MiB.

The isolated worktree, branch, shared installed-dependency link and committed
26 screenshots are retained so the root can reconcile and review the item.
No environment files, shared caches or other workers' processes were changed.

## Design sources

- The assigned external lane 09 brief and ranked polish list supplied the
  approved strings and scope. Neither external brief was copied into the repo.
- The existing [Argus design guide](../../../../.agent/designs/argus/DESIGN.md)
  supplies the shared mark sizing, calm motion and reduced-motion treatment.
- [Apple HIG Loading](https://developer.apple.com/design/human-interface-guidelines/loading)
  and [Accessibility](https://developer.apple.com/design/human-interface-guidelines/accessibility)
  were consulted for loading feedback and reduced motion.
- The cited [Square skeleton reference](https://mobbin.com/screens/09371ef3-f0d0-4fc9-8ab1-607ab3d0e4ab)
  was opened and visually inspected in the browser. Its content-shaped neutral
  placeholders informed the list layout.
