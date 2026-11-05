# Signed-in Consumer acceptance on staging

This checkpoint covers the founder-assigned signed-in free account. It covers
manual accounts, transactions, budgets, goals, Search, separate currency totals,
corrections, persisted balances, English, Spanish and large text.

Guest mode, saved receipts, shared plans, the parked transaction redesign and
RevenueCat are outside this checkpoint. No phone work or further hosted changes
were performed.

## Runtime and provenance

- Integration base: `cd14c9883f180876d27c121f0787b25a73529492`.
- October 10 reconciliation: integration `59c695a0e2690f28bd5c5e48b73a66ce07ebc785`
  entered the Consumer branch through merge `14bae401b58b1de2ca63dd1b77e0bfc275eb412a`.
  App and test source bytes remain unchanged from published head `9bba18fea`.
  [Reconciliation metadata](integration-reconciliation.json) preserves the initial
  check and recorded native sources. Final review and CI status live in
  [PR #952](https://github.com/lagarcess/argus/pull/952).
- Native configuration: Release, iPhone 18 Pro simulator, iOS 27.0.
- API: `https://cuadrao-api-staging.onrender.com`.
- Backend: `cad1cbe1ec27ff89c08eadbec31718a0e627383c`.
- Live deployment: `dep-db4qeilckfvc73fss4kg`, verified through Render's read API.
- The registered synthetic identity and its existing records were preserved.
- Native auth used the existing local CAPTCHA test fixture. Identity and money
  requests reached staging. This does not verify a hosted CAPTCHA bridge or a
  production sign-in journey.

## Test repairs

The current Home shows a selected currency balance and gross recorded spending
in its expanded Activity view. The old tests expected four labels from the
previous Home. The revised tests read the current UI and preserve exact account
balances, correction history and relaunch checks. A separate canonical API
readback checks income, purchases, refunds and net spending around each native
money journey. Amounts remain integer minor units and currencies stay separate.

The navigation helper treated a collapsed Home tab as a usable target because
it still existed in the UI tree. XCTest reported a hit point of `{-1, -1}`.
The helper now uses the visible Home surface and reveals navigation before
choosing a hidden tab. The ordinary-tap regression passes three account-return
cycles. The earlier centre-tap hypothesis was refuted and removed.

The old correction helper deleted characters from the current caret. It could
leave part of the previous amount in place. Replacement now uses native Select
All before typing. Exact final balances and API deltas verify the result.

The reconciliation test exposed another stale helper assumption. Full-screen
swipes overshot a coverage answer and returned it beneath the fixed Review
button. The helper counted the tap although the answer stayed unselected.
A preview-only replay confirmed that three of four answers were selected; it
then cancelled without saving. Scroll targets now use bounded movements and
must fit the visible area before the tap. Fixed controls retain ordinary taps.
The answer loop advances only after selection or final confirmation appears.
[Diagnostic excerpts](test-repair-probes.json) record both reproductions.

The account helper also left the nickname keyboard open before choosing a
non-default currency. It now uses the existing keyboard dismissal first.
The original reconciliation, USD and Spanish journey then passed, including
the canonical API readback.

The same scroll helper incorrectly excluded the Plan header with an invented
top boundary of 115 points. A no-write probe opened the visible button at 82
points with an ordinary tap. The top boundary now derives from the scroll view
and visible system bars. When a target enters the viewport but remains
untappable, bounded scrolling continues toward the center. The permanent
offscreen-header regression opens and cancels the account sheet successfully.

Home's balance history also changes the header position when loading finishes.
The account-entry helper now waits for the existing loading indicator to clear
before scrolling or tapping. A no-write native probe verifies that sequence.
The budget rerun passed all account-entry steps and reached its plan editor.
It stopped later at a separate amount-field identifier defect before saving a
budget.

The landscape test's app-only screenshot was clipped even though its assertions
passed. A full-screen capture shows all three Add menu rows at the largest text
size. The test now retains that full-screen image. Its final rerun passed with no
skips, and the [retained image](screenshots/large-text-landscape-final.png) was
visually inspected.

The budget editor reuses the goal amount field. Its visible label updates, but
its test identifier stays `goal.target` instead of `budget.limit`. A no-save
regression reproduces this in one test. The founder approved the independently
reviewed one-line native fix. It moves
the identifier assignment into the UIKit update method. The same regression
now passes on `7a66caad0`, with zero failures or skips. The full budget rerun
failed earlier in account-entry setup. It could not reach `accounts.add` before
the first account editor opened. No Save, Review or Confirm action occurred in
that run. Its cause is not yet established; budget acceptance remains open.

Goal acceptance then exposed an empty-input test error. XCTest reports the
`0.00` placeholder as the field value, so the replacement helper requested
Select All despite there being no text. The contribution was not saved.
The no-save regression passed empty, grouped and real-zero replacement on
`bc8e6afa9`. The goal rerun passed that step, recorded a contribution and
submitted its correction, then stopped at return navigation. The Back button
existed before it could receive a tap. The helper now waits for hittability.
A no-save replay opened and cancelled correction, returned to the goal, and
verified DOP 750.00 with the corrected DOP 150.00 contribution. The full rerun
then passed that correction, release/relink, target editing and archive/restore.
It failed later when its Search helper tapped a collapsed tab directly. The
Search entry now uses the existing navigation-reveal helper. The retained-goal
replay passed the remaining Search, relaunch and Spanish steps without
creating another goal or moving more money.

Search setup also exposed an invented lower boundary in the scroll helper.
Expectation Save was visible at y=764 inside its scroll view, but the helper
reserved the bottom 130 points even though this form has no fixed footer. A
no-save probe confirmed the expectation boundary at y=874 and the separate
transaction Review button at y=760. A test-only repair now derives that edge
from visible fixed controls. The retained coverage replay passed all required
answers and reached Confirm, then cancelled without saving. Search passed that Save step, account editing
and transaction correction. It then reached a stale assertion that incorrectly
required the DOP filter summary to disappear when selecting Plans. The repaired
assertion requires Plans selected and the existing currency summary preserved.
The full Search rerun passed with no failures or skips. It preserved the DOP
filter, saved the bill at DOP 35.00 and found that bill after a Spanish relaunch.

## Acceptance record

This is a partial checkpoint. No complete free-tier acceptance claim is made.
The identifier regression passes, but the broader budget rerun failed during
account-entry setup before any budget assertions. As verified on October 10,
draft [#952](https://github.com/lagarcess/argus/pull/952) is published at
`9bba18fea6878049bbcff1f86d93fce7b3237f7f`, and its
[push CI passed](https://github.com/lagarcess/argus/actions/runs/38034083813).
The draft-triggered PR CI and smoke jobs were skipped. This status correction
does not claim new native runs. Each native result retains its recorded source.
Large-text money entry and cancellation passed, but visual acceptance remains
open because the transaction Date label wraps into a single-letter column.

| Journey | Native result | Canonical API result |
| --- | --- | --- |
| Income, spending, refunds and three corrections | [1 passed](results/income.json) | [Exact deltas passed](readbacks/income-verification.json) |
| Transfers and wrong-account correction | [1 passed](results/transfer.json) | [Exact deltas passed](readbacks/transfer-verification.json) |
| Card payment, purchase refund and credit balance | [1 passed](results/card.json) | [Exact deltas passed](readbacks/card-verification.json) |
| Balance reconciliation, separate currencies, unknown balance and Spanish | [1 passed](results/currencies.json) | [Exact deltas passed](readbacks/currencies-verification.json) |
| Reopen account entry after detail navigation | [1 passed](results/navigation.json) | No writes |
| Reopen account entry after header scrolls offscreen | [1 passed](results/scroll-regression.json) | No writes |
| Release Add tray, collapse and slide navigation | [1 passed](results/release.json) | Native assertions |
| Add menu at largest text size in landscape | [1 passed](results/large-text-final.json) | No writes |
| Account and expense entry/cancel at largest text in portrait | [1 passed](results/large-text-money.json); visual issue remains | No Save, Review or Confirm action |
| Search account editing, income correction, bill editing and Spanish relaunch | [1 passed](results/search-final.json) | Native saved-value and origin assertions |
| Goal Search, relaunch and Spanish on the saved corrected goal | [1 passed](results/goal-retained-search.json) | No writes; exact supported DOP 750.00 |
| Goal → Budget → Goal amount field identifier | [1 passed](results/plan-identity-after.json) | No writes |

These listed cases had no failures or skips in their final runs. The complete
goal workflow has split evidence. Its data operations passed before a stale
Search-tab tap failed the original test; the no-write replay passed the remaining
Search and persistence steps. This is not a claim that the entire original goal
case ran green in one execution. The four money
journeys include native relaunch checks. Failed earlier attempts and their synthetic records were kept.
Every readback compares the account's existing records before and after exactly
one native journey; unrelated currencies must stay unchanged.

The first three money runs used `248317cbf`. The currency run used `f43dbad00`.
The offscreen-header regression used `daaf417dc`. The final large-text run and the first goal and Search attempts used
`6cf0e029f`. Goal stopped at the empty amount helper. Search stopped during
session restoration before creating any Search records. Later Search attempts
reached the editors and exposed the fixed-footer and currency-summary test
errors described above. The final Search journey passed on `64c26e085`.
The intervening commits change test navigation and input only. Those earlier runs used the same app source tree as integration. The approved
one-line identifier repair is the sole later product change; the earlier
numerical and visible-UI evidence remains applicable, but was not rerun wholesale
on the new identifier source. [Initial source](source-provenance.json),
[scroll repair](coverage-source-provenance.json) and
[picker repair](picker-source-provenance.json),
[viewport repair](scroll-source-provenance.json) and
[Home readiness repair](home-ready-source-provenance.json),
[empty amount repair](empty-amount-source-provenance.json) and
[boundary and Back probes](boundary-readiness-source-provenance.json), and
[Search filter repair](search-filter-source-provenance.json), and
[retained-goal Search repair](goal-search-source-provenance.json), and
[large-text money probe](large-text-money-source-provenance.json), and
[approved identifier repair](identifier-fix-source-provenance.json) record the exact tested
files. These records retain earlier successful runs at their tested sources;
they do not claim that every case ran at the final documentation commit.

Selected visual evidence shows [reconciliation](screenshots/per-account-reconciliation.png),
[unknown USD balance](screenshots/separate-currency-unknown-balance.png) and the
[Spanish income form](screenshots/income-spanish-light.png), and
[Search after Spanish relaunch](screenshots/search-spanish-relaunch.png), and
[the saved goal in Spanish](screenshots/goal-spanish-restored.png).

The readback command is `ios/scripts/consumer-money-readback.py`. Run `capture
before`, one native journey, `capture after`, then `verify` for that journey.
Its private login file and native test runner must remain outside Git. The
committed evidence contains only synthetic screenshots and aggregate results.

## Open acceptance items

- The amount-field identifier regression passes after the approved one-line
  repair. The [full budget rerun](results/budget-after-identifier-fix.json) failed
  during account-entry setup because `accounts.add` could not reach the visible
  scroll area. No budget assertions ran. Its cause needs diagnosis.
- Largest-text transaction layout needs repair. In the
  [retained screenshot](screenshots/large-text-transaction-ready-unreviewed.png),
  the Date label wraps one letter per line beside its picker. The controls remain
  usable and the native test is green, but that does not close visual acceptance.
  The affected current surface is `ConnectedTransactionSheet.swift:98`. No
  transaction redesign or layout source was changed.
- The new form check covers English account/expense input and cancellation,
  not every free-tier screen or a saved transaction at largest text. The images
  do not show an onscreen software keyboard, so keyboard-occlusion acceptance
  is not claimed. English/Spanish money, Search and goal evidence is separate.
- A first Search launch raced session restoration. Subsequent native sign-in
  runs passed; no shared auth implementation was changed.
- Full local pytest remains blocked at collection
  by the pre-existing SciPy binary load error described in `local-checks.json`.
