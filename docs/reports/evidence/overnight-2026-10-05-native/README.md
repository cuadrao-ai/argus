# Overnight native evidence, 2026-10-05

Simulator captures for two serialized native tracks on `codex/private-alpha-next`
work (#822, #824). Synthetic identities on an isolated local stack; no provider
calls, no physical phone, no hosted acceptance. Exact heads and test counts are in
each PR body; this folder keeps the images the bodies cite.

Environment: "Overnight Cuadrao 18 Pro" (iPhone 18 Pro, iOS 27.0, UDID
`C6303D9B-FCF8-46DC-BFBF-779DD2548940`), local stack `ios-accounts-59900`
(`local_stack.py ... --accounts --port-base 59900`, API `--accounts-enabled on`),
CAPTCHA bridge on 59905, committed-response-loss proxy on 59912 for the one
opt-in case. The iOS 26.5 fallback uses a throwaway iPhone 17e simulator created
for the run and deleted afterwards.

## Track 2: recurring from a movement, Home Upcoming (#822, #824)

| Capture | What it shows |
| --- | --- |
| `recurring-movement-detail-action.png` | Expense detail with the new secondary action and its one-line explanation (dark appearance). |
| `recurring-review-form-prefilled.png` | The existing expectation form prefilled: Bill, name from the note, DOP 350.00, the movement's account, next date Oct 25, Every month, day 25. |
| `home-upcoming-recurring.png` | Home Upcoming inside its own window (Until Nov 4), projected DOP 300.00, the planned Rent occurrence with "Planned, not recorded". |
| `home-upcoming-unchanged-by-plan-horizon.png` | Home after Plan's horizon was moved to +60 days: same window, same total. Plan itself projected DOP -50.00 in the same run. |
| `home-upcoming-after-fulfilment.png` | After recording the payment from the Home row: the occurrence is gone, the total stays DOP 300.00 (counted once). |
| `home-upcoming-preserved-after-reopen.png` | Same Home after terminate and relaunch. |
| `recurring-save-response-lost.png` | Expectation save whose committed response was dropped by the proxy: the form shows the pending retry. |
| `recurring-saved-once-after-retry.png` | After relaunch and retry: one expectation, one occurrence, one movement. |
| `recurring-movement-detail-spanish.png` | Spanish (es-419) income detail with "Configurar como recurrente". |
| `recurring-review-form-spanish.png` | Spanish review form (Ingreso, Cada mes). |

Baseline defect before/after (`FinancialLoopUITests/testConnectedPlanRecordsLinksCorrectsAndReopens`):
at 7e0c0b1d9 (identical `ios/` to 76b6afcb4) the test fails at
`FinancialLoopUITests.swift:265` on a fresh identity (no `home.netWorth.DOP`), exit 65;
on this branch it passes, 1 test, 0 failures.

## Track 3: Home movement detail and row gestures (#824)

| Capture | What it shows |
| --- | --- |
| `home-movement-row-before-open.png` | Home scrolled to a movement row before the tap. |
| `home-movement-detail.png` | The movement's authorized detail pushed from Home with its own back button. |
| `home-movement-back-same-position.png` | Home after back: the same row at the same frame. |
| `account-swipe-add-movement.png` | Account row swiped right: Add movement. |
| `account-swipe-edit-more.png` | Account row swiped left: Edit and More. |
| `account-more-menu.png` | More: Check balance and Archive. |
| `account-archived-from-more.png` | The row gone from Home after Archive. |
| `account-restored-after-more-archive.png` | The account restored from Archived accounts and back on Home. |
| `movement-swipe-edit.png` | Movement row swiped right: Edit. |
| `movement-swipe-category.png` | Movement row swiped left: Category. |
| `movement-category-shortcut.png` | The correction editor opened by the Category shortcut with the category control in view. |

Captures suffixed `-ios26` come from the iOS 26.5 fallback run (context menu and
detail actions instead of swipes).

Raw `.xcresult` bundles stay ignored because authentication diagnostics can carry
synthetic credentials; these PNGs were exported from them.
