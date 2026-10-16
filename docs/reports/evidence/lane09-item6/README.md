# Lane09 item6: Business navigation and shortcuts

Code commit: `9db2a7010f49834a7fa0db1d3f840552a97c2e3a`. Stack base: `9104dc11b39be993089c3c402061ea63eb51ed9f`.
Observed integration ref: `742f4b72a3f082194e56cbcccb679ab7a8ca8394`.
Date: 2026-10-16. Local synthetic data only. This is a draft delivery.
Root owns integration reconciliation, final independent Eval, merge and staging.
The old stack lacks #1178. No auth/session/history readiness changes were made.
Root must retain #1178 and item3 evidence follow-up `1c19658c` when reconciling.

## Delivered

- Four Business sections: Resumen, Bandeja with the server-owned count, Gastos and Novedades.
- Business switcher and search at the top. Access and the existing profile/settings/help surface at the bottom. Business Recents and chat creation controls are suppressed.
- The existing filled upload action remains in content. The existing note action moves into Bandeja as a secondary action. No new create action or approval endpoint.
- Collapsed labels appear on hover and keyboard focus. Section hints use the current platform. Phone tabs have 44px-or-larger targets and retain the four sections on record pages.
- The phone content height reserves the 64px tab bar and `env(safe-area-inset-bottom)`. The existing sticky receipt approval footer remains inside that region.
- The existing shortcut sheet lists review actions first and searches action labels or key names. Spanish uses only final9b labels. English reuses existing labels, including Sidebar, with no catalog changes.

## Keyboard contract

The owning technique is `web/components/keyboard/useChatKeyboardShortcuts.ts`: document `keydown` listener in capture phase (`true`), then `preventDefault()` only after a matched action is consumed. The existing non-Business branch is preserved. This handles a browser-released event; it does not grant the page control over keys the browser or OS never releases.

| Action | Mac | Ctrl platform |
| --- | --- | --- |
| Aprobar | Cmd+Shift+Enter | Ctrl+Shift+Enter |
| Aprobar y siguiente | Cmd+Shift+S | Ctrl+Shift+S |
| Recibo anterior / siguiente | Cmd+Shift+Up / Down | Ctrl+Shift+Up / Down |
| Editar dato | Cmd+Shift+E | Ctrl+Shift+E |
| Subir recibo | Cmd+Shift+Period | Ctrl+Shift+Period |
| Four section jumps | Cmd+Alt+1–4 | Ctrl+Shift+1–4 |
| Buscar | Cmd+K | Ctrl+K |
| Atajos de teclado | Cmd+Slash | Ctrl+Slash |
| Sidebar | Cmd+Shift+Backslash | Ctrl+Shift+Backslash |
| Ajustes | Cmd+Shift+Semicolon | Ctrl+Shift+Semicolon |

The upload chord reuses Argus's existing new-chat chord. Search, sheet, sidebar, settings and quick-jump chords keep the existing choices. Chat rename/archive/delete/pin/read/Recents actions are absent from Business. No reject action, single-key shortcut or bare question-mark alias. Close/reload/address/navigation/tab and screen-reader combinations are not registered. Matching uses physical `code`, exact platform modifiers and no repeats. Input, textarea, select, editable, composition, handled-event, overlay and phone-width guards precede dispatch. Existing typed capabilities and operation state register only available receipt actions. Approval calls the existing `write` or `approveAndNext` method and keeps their version and idempotency guards.

## Exact shared ownership for root Eval

- `ChatWorkspace`: optional `keyboardShortcuts` and `bottomNavigation` fields.
- `ChatInterface`: Business initial sidebar state, existing Omnisearch listener gate, optional search callback and bottom-navigation slot. Auth/session/history code is unchanged but its owning file must be rechecked after #1178 reconciliation.
- `useChatKeyboardShortcuts`: optional workspace dispatch before the existing Argus branch, preserving capture listener and existing shell setters.
- `keyboard-shortcuts.ts`: typed workspace definitions, exact matching/display/query/target guards; quick jumps reuse `quickJumpIndexForEvent`.
- `KeyboardShortcutsOverlaySurface`: optional workspace rows and searchable label/key list. Existing modal/overlay/focus handling and Argus rows remain.
- `ChatSidebar`: suppress Business chat/Recents quick jumps and show the search hint. `SidebarNavButton`: optional interaction hints and active-page semantics, existing defaults retained.
- `WorkspaceMain`: optional phone tab clearance.
- `BusinessWorkspaceContent`: `openPanel` and `chooseBusiness` clear abandoned title focus; optional shell props and the existing Access footer.
- `ReceiptDossierReview` and `ReceiptEntry`: register already-available action callbacks and field focus only. No change to approval, revision, write transport or idempotency methods.
- `bandeja-order`: `clearTitleFocusUnless`. The intended receipt still consumes one title-focus handoff.
- `installBreakpointFixture`: only the main frame initializes synthetic localStorage, so blocked opaque child frames do not throw test-setup errors.

The old ReceiptEntry cleanup consumed a handoff during React's development Strict Mode effect rehearsal. With the old cleanup, the focused-title test passes normally and fails in Strict Mode (`activeElement.id` is empty). Navigation now cancels abandoned handoffs, while mounting does not consume them. The same production /biz synthetic transport probe passes with the old cleanup and with the new cleanup. Existing unavailable-next and leave-while-loading assertions remain.

The inherited approve-next test fixture now honors `receiptPage('all')` and returns confirmed receipts to the existing item5 saved-state proof. Its expected empty copy uses the already-locked item5 text. Approval/version/idempotency assertions remain intact.

## Verification

| Check | Result | Evidence |
| --- | --- | --- |
| Focused Bun tests | 58 pass, 0 fail, 8 files, 390 expectations | [unit](navigation-unit.txt) |
| Business browser matrix | 18 pass, 0 fail: 6 cases in each engine | [matrix](navigation-matrix.txt) |
| Corrected actual receipt image/fields phone proof | 3 pass across all engines | [phone correction](navigation-phone-final.txt) |
| Existing Argus keyboard-layers and keyboard-passes | 21 pass, Chromium production, Business flag off | [Argus](navigation-argus-keyboard.txt) |
| Existing clutter/locale cases plus production title focus | 11 pass, Chromium production | [production](navigation-production-final.txt) |
| Old focus Strict Mode reproduction | 1 normal pass, 1 Strict Mode fail, expected red | [red](navigation-focus-strict-before.txt) |
| Old focus production comparison | 1 pass | [before](navigation-focus-production-before.txt) |
| New focus production comparison | 1 pass; also included in final production 11 | [after](navigation-focus-production-after.txt) |
| Canonical `bun run build` | pass | [build](navigation-build.txt) |
| Canonical `bun run lint` | 0 errors, 8 inherited unused warnings | [lint](navigation-lint.txt) |
| Locale parity | covered by `locales.test.ts`, no catalog change | [unit](navigation-unit.txt) |
| Modularity and ownership | pass on this tree | [modularity](modularity.txt), [ownership](ownership.txt) |

Focused files: `workspace-keyboard-shortcuts.test.ts`, `business-approve-next.dom.test.tsx`, `business-switcher.dom.test.tsx`, `keyboard-shortcuts.test.ts`, `chat-keyboard-shortcut-policy.test.ts`, `keyboard-shortcuts-overlay.test.ts`, `keyboard-shortcuts-overlay-render.test.tsx`, `locales.test.ts`.

The browser matrix exercises every advertised chord, all four jumps, search, sheet filtering by labels/keys, approval and approve-next, field focus, read-only suppression, input blocking, overlay blocking, bare-question-mark rejection, repeat/composition/modifier guards, reserved-key nonconsumption and phone suppression. Positive actions use Playwright keyboard presses. The reserved/repeat/composition/editable guard probe dispatches DOM keyboard events and checks that they are not consumed; it does not prove native browser chrome behavior.

| Surface | Evidence status |
| --- | --- |
| Chromium, Firefox, WebKit on this Mac host | PASS for automated page behavior |
| Native desktop Chrome/Firefox and Safari | UNVERIFIED: native computer control is locked; WebKit is not native Safari |
| Native Windows browsers | UNVERIFIED: no Windows surface available; Ctrl-path unit cases are not Windows proof |
| 390px phone viewport | PASS for layout, targets, tab/approval clearance and keyboard gating |
| Installed PWA, physical phone, nonzero device safe area | UNVERIFIED; implementation uses safe-area CSS, no device or installation claim |
| Integration/release | BLOCKED on root reconciliation and final exact-head independent Eval; draft skipped CI is not acceptance |

All API responses were synthetic or locally mocked. No provider/model call, login, paid platform setup, environment-file write, migration, deploy, or staging/production mutation. The initial production attempt had the Business route disabled; the fixture was corrected before recording the comparison. An early combined Argus run used the Business build, which redirects /chat; its wrong-surface failures were not counted as regressions or passes. Argus was then rebuilt with Business disabled and all 21 tests passed.

## Reproduce

From `web/`, build using process-only synthetic values:

```sh
NEXT_PUBLIC_MOCK_AUTH=true NEXT_PUBLIC_ENABLE_SPANISH=true NEXT_PUBLIC_BUSINESS_PILOT_ENABLED=true NEXT_PUBLIC_ARGUS_API_URL=http://localhost:3196/api/v1 NEXT_PUBLIC_SUPABASE_URL=http://localhost:3196 NEXT_PUBLIC_SUPABASE_ANON_KEY=synthetic bun run build
bun run lint
bunx playwright test --config e2e/business-navigation.playwright.config.ts
CUADRAO_NAV_PRODUCTION=true bunx playwright test --config e2e/business-navigation.playwright.config.ts --project chromium
```

The final command is the riskiest production focus probe: **1 passed**. The retained ignored regression configs are also copied beside this report. To repeat Argus, build with `NEXT_DIST_DIR=.next-navigation-argus` and `NEXT_PUBLIC_BUSINESS_PILOT_ENABLED=false`, keeping the other synthetic variables, then use `temp/navigation-argus.playwright.config.ts`.

## Design decisions and references

DONE: used one typed shortcut table and a typed receipt callback registry. This applies pstack's Model the Domain principle. A second document-level listener or DOM button-click dispatch would duplicate ownership or guess capability state, so both were rejected. Optional shared-shell fields preserve existing callers. DONE: moved title-focus cancellation to the navigation methods after reproducing development failure and production success. DONE: moved only the existing note action into its section; retained Access at the footer.

Throughput checkpoint: the initial gate was source/authority, exclusive worktree and method ownership. Browser, build and DOM checks used separate outputs. Shared shell changes stayed with this sole writer. One writer is the smallest safe decomposition because navigation, the registry and receipt callback lifecycle are coupled. Root dispatches a fresh independent Eval and owns reconciliation. No extra writers were spawned.

Read `.agent/designs/argus/DESIGN.md`, `.agent/skills/apple-hig-expert/references/platform-specifics.md`, [HIG tab bars](https://developer.apple.com/design/human-interface-guidelines/tab-bars), [HIG layout](https://developer.apple.com/design/human-interface-guidelines/layout), and [WWDC22 Explore navigation design for iOS](https://developer.apple.com/videos/play/wwdc2022/10001/). Applied four stable labeled sections, targets at least 44px, and bottom-safe-area clearance. On 2026-10-16, also read the current [WWDC26 design guide](https://developer.apple.com/wwdc26/guides/design/) and [WWDC26 search session transcript](https://developer.apple.com/videos/play/wwdc2026/292/). These inform recognizable search controls and clear search scope; the older navigation session is supplemental, not a substitute for the current guide.

Opened all 11 supplied visual references in the existing browser session without login or purchase: [1: transaction rows](https://mobbin.com/screens/f77b24a7-e68e-4fc1-b5ac-91856a92f12b), [2: detail hierarchy](https://mobbin.com/screens/512520ce-bc7e-4819-9cc4-16049b6e6572), [3: dashboard](https://mobbin.com/screens/d8564614-5b4c-4cdc-8088-0891fc9260df), [4: empty state](https://mobbin.com/screens/dc52d8c6-76a8-49f7-a3ce-66c4b7b35500), [5: table skeleton](https://mobbin.com/screens/09371ef3-f0d0-4fc9-8ab1-607ab3d0e4ab), [6: page skeleton](https://mobbin.com/screens/bc5f336e-30e3-46f4-b461-62fa59e80f04), [7: sidebar skeleton](https://mobbin.com/screens/cca735a9-0a0c-4e0e-a541-2e7d413e730e), [8: persistent tabs](https://mobbin.com/screens/209d586d-c74b-476b-883f-50b5d26c6a78), [9: tabs during loading](https://mobbin.com/screens/d3158271-a0e5-4672-bea0-44ef4aebcb1c), [10: lone-spinner anti-pattern](https://mobbin.com/screens/ee29de9a-5441-4a89-829c-007e134b74e1), [11: decorative-loader anti-pattern](https://mobbin.com/screens/a2269caf-8ccc-4cff-b151-3de6d9e19470). Applied stable labels, top search and hierarchy. Retained tabs during loading without copying decorative floating shapes. No item3/item5 loading changes. 

## Screenshots

Matched synthetic /biz captures use the same clutter fixture before and after:

| View | Before | After |
| --- | --- | --- |
| Overview desktop | [before](before-overview-1280.png) | [after](after-overview-1280.png) |
| Bandeja desktop | [before](before-inbox-1280.png) | [after](after-inbox-1280.png) |
| Overview 390px | [before](before-overview-390.png) | [after](after-overview-390.png) |
| Bandeja 390px | [before](before-inbox-390.png) | [after](after-inbox-390.png) |

Additional engine-named captures show the [shortcut sheet](chromium-after-shortcuts-1280.png), [collapsed focus label](chromium-after-collapsed-focus-1280.png), and [phone image/approval clearance](chromium-after-review-390.png) and [fields/approval clearance](chromium-after-review-fields-390.png). Screenshots contain invented sample records only.

## Cleanup

Removed only lane-owned build and test outputs: 410237015 logical bytes. Retained dependencies, ignored test configs, this worktree and all evidence. Port 3196 had no listener. APFS clone allocation prevents equating logical bytes with disk space recovered. [Measured cleanup and df](cleanup.txt).

Phone evidence correction: the original capture used a message-only dossier whose inherited synthetic name contained English text. The phone test now opens the existing receipt fixture, saves its review fields, expands its original image, and checks the actual approval footer against the tabs. Its existing record name is Mi negocio; no locale or product copy changed.
