# Personal action in the receipt row menu

This is lane 09 item 7, critique 2.7. It helps the accountant review the Bandeja without mistaking a classification command for a saved status. The owner is `/root/lane09_item7_personal_action`. Root owns reconciliation, independent strongest-model Eval, and landing.

## Boundary

- Sole writer worktree is `/private/tmp/cuadrao-lane09-item7-personal-action`, branch `codex/lane09-item7-personal-action`.
- Exact supplied parent is `4fafd03f77b254fa2250192430e49e94ea626d5c`, PR #1182. The parent worktree stayed read-only.
- Integration at initial fetch was `742f4b72a3f082194e56cbcccb679ab7a8ca8394`. Final read was `71531306793d28ff3e3ccab42272132d2dea4e9d`.
- The source commit is `639f8cd1c6a95ebab9fa99dc97916bd33ac6c3f2`. The final evidence-only commit preserves that product tree. Source screenshots and the final eight browser checks were captured at this source commit.
- Root must reconcile current integration and retain auth #1178 before final CI and Eval. This worker did not merge or rebase. Local modularity passes; would-be-merged modularity remains root's gate.

## Choice and shared ownership

`ReceiptRow` now opens the existing `ActionMenu` from a 44px ellipsis control. Its menu item uses the existing approved label, `Marcar como personal` or `Ya no es personal`. `RecordMarks` still renders the backend's saved Personal status and attribution. On phones, amount and status sit under the merchant so the menu stays beside the row.

The tradeoff is one extra tap for classification. The row keeps the command near its receipt and keeps the existing undo toast. Moving it into detail would add a larger navigation step and use a different action path.

`usePersonalMark` is byte-identical to the parent. The backend still owns edit eligibility, current-version reads, idempotency, personal classification, totals, saved state, and errors. No locale catalog, API, backend, financial authority, or shared environment changed.

The only shared menu change is the `ActionMenuProps.actions` type. It accepts the existing closed `BusinessAction["id"]` union plus `mark_personal`. Its runtime function, focus handling, positioning, and all prior action IDs are unchanged. Independent Eval should recheck this signature and the existing Create menu callers. The only other lane test edit waits for the upload dialog's `popstate` before the next navigation in `business-upload-controls.spec.ts`.

The Model the Domain principle kept the existing `ReceiptSummary` and mutation hook as the data owners. Test Behavior, Not Implementation shaped the tests around visible menus, saved chips, undo, blocked actions, and actual API requests.

## Evidence

| Check | Result |
| --- | --- |
| Baseline production `/biz`, 1280px and 390px | 2 passed, 4 later cases intentionally skipped; the 390px Personal button wraps beneath the receipt |
| Failing-test checkpoint `8772f2045` | 13 pass, 3 fail before the menu exists |
| `receipt-marks.dom.test.tsx` | 16 pass |
| `business-approve-next.dom.test.tsx`, `business-upload-controls.dom.test.tsx`, `business-inbox-notes.test.tsx`, `business-approved-revision.dom.test.tsx`, `business-money-readback.test.ts` | 32 pass across 5 files |
| `business-personal-menu.spec.ts` | 8 pass in the production build |
| Existing `business-upload-controls.spec.ts` with history synchronization | 6 pass |
| Canonical `bun run build` | Pass |
| Focused ESLint and `git diff --check` | Pass |
| Local modularity budget | Pass, no violations |

The eight new browser cases cover desktop and 390px menu placement, 44px triggers/items, visible trigger focus, Enter, arrows, Home, End, Escape, outside cancellation, row-open navigation, no horizontal overflow, editable owner and preparer, read-only actor, saved status after reload, current versions, distinct idempotency keys, undo, unmark, pending/failure feedback, and failed-receipt recovery controls.

The riskiest command was the real production build's synthetic save/undo browser check:

```sh
CUADRAO_PERSONAL_EVIDENCE_DIR=../docs/reports/evidence/lane09-item7-personal-action NEXT_PUBLIC_MOCK_AUTH=true NEXT_PUBLIC_BUSINESS_PILOT_ENABLED=true bunx playwright test --config e2e/business-personal-menu.playwright.config.ts
```

Output was `8 passed (11.3s)`. API responses were intercepted synthetic fixtures. This checks the browser contract, not hosted authorization or database persistence. Money totals code is unchanged and the existing money readback tests pass.

### Retained failures

The first save fixture had no prepared draft ID, so the unchanged hook correctly made no mutation. The fixture now identifies a prepared draft. No product guard was changed.

The older recovery suite first failed twice after Escape and before the receipt row appeared. A parent build passed both cases once. A second item7 run passed desktop and failed phone with `net::ERR_ABORTED`. The modal cleanup schedules `history.back()` in `useOverlayBackDismiss`; dialog disappearance does not mean that traversal completed. The test now waits for its actual `popstate`, with all recovery assertions retained. All six cases then passed. The earlier logs are preserved, and no modal runtime code changed.

The initial sandboxed build stalled before compilation and was stopped. The allowed local build completed successfully. Automatic approval review rejected this worker's cancellation attempt on parent #1182 because root owns merge controls. Root then completed inspection/cancellation and confirmed no pending merge. No worker attempted another cancellation route.

## Screenshots

| State | Desktop | 390px |
| --- | --- | --- |
| Before | [Before](before-inbox-1280.png) | [Before](before-inbox-390.png) |
| After | [After](after-inbox-1280.png) | [After](after-inbox-390.png) |
| Keyboard focus | [Focus](after-focus-1280.png) | [Focus](after-focus-390.png) |
| Menu | [Menu](after-menu-1280.png) | [Menu](after-menu-390.png) |
| Recovery | [Recovery](after-recovery-1280.png) | [Recovery](after-recovery-390.png) |

## References and limits

The signed-in [Mercury row reference](https://mobbin.com/screens/f77b24a7-e68e-4fc1-b5ac-91856a92f12b) was opened and visually inspected in the in-app browser. Its transaction rows keep commands in a trailing column. [Apple HIG menus](https://developer.apple.com/design/human-interface-guidelines/menus) supports a compact command menu with clear action labels. [Apple HIG accessibility](https://developer.apple.com/design/human-interface-guidelines/accessibility) recommends 44pt iOS targets and keyboard access. The current [WWDC26 design guide](https://developer.apple.com/wwdc26/guides/design/) emphasizes readable content and layouts that adapt to screen size. The Argus web guide supplies the local menu/focus pattern; the Cuadrao Business design guide supplies the brand reference only.

This is desktop Chromium with a 390px viewport, not a physical phone or native Safari/Windows test. No native app, installed PWA, hosted login, staging, production, real receipt, model/provider call, or paid service was used. Mock auth was enabled only in the explicitly authorized local test process. The actual logged-in hosted flow remains unverified.

Detection signals are the row-menu browser tests and unchanged money/approval tests. Independent review remains root-owned and pending. This is a draft handoff, not a READY or hosted customer acceptance claim.

## Reproduce

From `web/`, use empty lane-local environment files and these process settings:

```sh
NEXT_PUBLIC_MOCK_AUTH=true NEXT_PUBLIC_ENABLE_SPANISH=true NEXT_PUBLIC_BUSINESS_PILOT_ENABLED=true NEXT_PUBLIC_ARGUS_API_URL=http://localhost:3197/api/v1 NEXT_PUBLIC_SUPABASE_URL=http://localhost:3197 NEXT_PUBLIC_SUPABASE_ANON_KEY=synthetic bun run build
NEXT_PUBLIC_MOCK_AUTH=true NEXT_PUBLIC_BUSINESS_PILOT_ENABLED=true bunx playwright test --config e2e/business-personal-menu.playwright.config.ts
```

The recovery configuration is retained in `web/temp/item7-recovery.config.ts` and copied beside this report. The data source denies off-local requests. Root's old-stack owner-boundary assertion was not weakened.

## Cleanup

The worker removed only its two build outputs and its Playwright result cache. Measured allocation before removal was **82,481,152 bytes**, with **78,832,359 logical bytes**. `df -k` reported 181,200,000 KiB available before and after at its reported precision. APFS allocation is not a claim of identical free-space gain. No listener remains on port 3197. Dependencies, local configurations, empty local environment files, worktree, and evidence remain. [Cleanup measurements](cleanup.txt) record the commands' output.
