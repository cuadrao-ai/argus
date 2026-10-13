# Cuadrao native design

Approved native baseline, October 2, 2026. The founder approved consolidating the native
preview's typography, money editing and reference gallery before receipt splitting.
This guide owns Cuadrao's native visual and interaction conventions, including
approved behavior to apply to the connected app. It does not implement that
behavior or change production Argus web styling, financial contracts or providers.
The October 2 release-readiness pivot below supersedes conflicting preview rules.
Read a rule as approved direction, not proof that it is shipped.
The [main roadmap](../../../docs/specs/argus-execution-board.md#cuadrao-release-ui-landing-order)
owns the release UI landing order, and its
[design dispositions](../../../docs/specs/argus-execution-board.md#cuadrao-design-dispositions),
C01 to C10, own follow-up work. Together they own unfinished work and delivery
status. Existing approved account,
chat, voice and Plan behavior is preserved unless this guide explicitly revises it.

This is a reference organized by design rule, not a sequence of polish notes.
The [Argus guide](../argus/DESIGN.md) supplies the document structure; Cuadrao keeps
its native type, palette and artwork. Delivery evidence belongs in the roadmap.

## Connected presentation ownership

The October 5 connection uses the existing approved Preview views. Connecting a
backend does not authorize a second Home, different typography, new artwork, or a
replacement navigation bar. Preview and connected hosts render shared components.
Preview owns sample records. Existing account, financial-loop, and Plan models own
live reads, review, confirmation, and recovery.

This applies to the full interface: Home and expanded charts, Plan, Chat, Search,
Updates, Profile, settings, and Household destinations. The shared app shell owns
the approved menu bar, temporary-chat exit, keyboard and voice presentation. Each
connected host supplies its authorized records and actions to the shared views.
Check must preserve the complete experience before a replacement build is called
restored. Verifying only the connected money slice is insufficient.

Development examples for capabilities awaiting a backend remain visibly labeled
and isolated from real financial writes. Preserve the separate Preview app and
source checkpoint during recovery; install candidates over Check only.

Missing live data uses the approved empty treatment. A current balance does not
establish historical coverage. Future Plan points do not become balance history.
Home's Upcoming reads its own rolling 30-day projection. A row opens review;
a due date never records a payment. Simulator evidence and physical-phone
acceptance remain distinct.

## 1. Character and surface purpose

Cuadrao is warm, clear and personal. Home offers a calm first glance; Plan makes
exploration inviting; Chat leaves space for conversation. Shared typography,
amount behavior and controls make these feel related without identical layouts.
Art belongs where it identifies an intention. It should not compete with a money
value, make a row hard to scan or imply that a prediction is certain.

| Surface | Heading purpose | Treatment |
| --- | --- | --- |
| Home | Welcome: Hola / Hello plus preferred name | Compact native system greeting |
| Chat | Invite conversation | Expressive serif landing text; preserve typed opening behavior |
| Plan | Look ahead: Lo que viene / What's ahead | One serif heading with the primary plus; no repeated subtitle |
| Profile and Settings | Identify the destination | Personal identity, quiet grouped destinations and clear native titles |
| Expanded insights | Identify the selected period | Serif feature title; controls stay anchored while period evidence pages |

Tab identity does not require a second literal surface title. Keep heading/action
alignment, typography roles and touch behavior consistent. Copy, illustration and
content density can vary with purpose.

## 2. Color palette and roles

`WelcomePalette` is the only native palette owner. Read its adaptive values rather
than copying RGB literals into screens. Colors below describe roles, not a new store.

| Token | Role |
| --- | --- |
| `background`, `surface` | Page and quiet supporting surfaces; adapt to appearance |
| `ink` | Primary content; secondary system text for metadata |
| `pine`, `sage`, `overlap` | Primary emphasis, quiet selection wash and layered art |
| `moneyInput` | Legible positive entered amounts |
| `sunshine`, `clay`, `bloom` | Plan artwork and stable category accents |
| `onAccent` | Readable content on accent surfaces |
| `separator`, `border` | Quiet boundaries |

Category colors come from `CuadraoExpenseCategoryStyle`. Keep them stable in charts,
rows and drill-down. Pair color with names or symbols. A spending increase is not
an error or a moral judgment. Destructive actions retain their existing semantic
red; don't repaint them with a category accent. Artwork may use depth and gradients
without turning numeric charts into decorative data.

## 3. Typography rules

`CuadraoTypography` owns display and money roles. Default point sizes below describe
the standard Large content-size category; semantic Dynamic Type scaling remains
authoritative. Do not freeze a screen to these point sizes.

| Role | Native style / default pt | Design | Weight | Use |
| --- | --- | --- | --- | --- |
| `screen` | largeTitle / 34 | Serif | Regular | Expressive landing heading, Plan or detail name |
| `feature` | title / 28 | Serif | Regular | Period heading or a substantial local headline |
| `section` | title2 / 22 | Serif | Regular | Cuentas, Tus planes, Lo que destaca |
| `body` | body / 17 | System | Regular | Explanations and reading |
| `supporting` | subheadline / 15 | System | Regular | Financial row labels, selectors, secondary descriptions |
| `caption` | caption / 12 | System | Regular | Dates, counts and supporting metadata |
| `action` | body / 17 | System | Medium | Primary action text |
| `amount` | largeTitle / 34 | Rounded | Medium | Hero and primary editable amounts |
| `secondaryAmount` | title2 / 22 | Rounded | Medium | Secondary summary amounts |
| `rowAmount` | subheadline / 15 | Rounded | Medium | Row amounts and percentages |

All money roles use monospaced digits. Editing and display use matching weight and
semantic size through the shared UIKit/SwiftUI bridge. Use the role for the amount's
importance, not for the screen it appears on. Fixed 30/36-point money styles and
system headline money are not alternate Plan treatments.

Use native line metrics and default tracking. Do not transplant Argus web line
heights or letter spacing into SwiftUI. Multiline prose and titles wrap. Avoid
fixed-height text containers. Long amounts may shrink within bounded money fields;
other large-text content wraps or scrolls. Keep currency codes visually subordinate
and present exactly once beside an amount where context requires them.

Expandable financial rows are controls, not section headings: use `supporting`
for names, `caption` for counts and `rowAmount` for money/percentages. Keep serif
`section` for real content groups. Equivalent hierarchy uses the same role across
Home, Plan, Chat results and expanded insights.

### Intentional native exceptions

- Home greeting: native title2 semibold system type, not a second expressive hero.
- Navigation bars, Forms, menus and standard native controls retain system semantics.
- Profile identity, avatar initials, icons, voice timers and the Cuadrao wordmark
  have distinct roles; the wordmark is brand artwork, not a text style (see
  [Brand identity](#brand-identity-mark-wordmark-and-lockup)). Their existence does not authorize a blanket serif migration.
- Invitation artwork and estimated completion dates are not financial amount roles.
  Keep their approved treatment and ensure artwork does not hide required text.
- Chart ticks may use native caption2. Numeric chart callouts should use a compact
  shared money role when they represent amounts.

Any new exception needs a named purpose and a gallery specimen. Don't override a
shared money role with a local weight, design or hardcoded size.

### Brand identity: mark, wordmark and lockup

One source for all three lanes (iPhone, web, Business). Marketing owns the artwork;
it lives in `marketing/brand/` and `marketing/app/icon.svg`, pinned at commit
`73286f8cac6f8d335ad17980002590b0c0fefb60` (PR #906), with the full spec in
`marketing/brand/README.md`. The lockup SVGs are pinned at commit
`acf1b180a70eb8e40a792c5dc0838d024d0ab17f` (they gained an intrinsic width and height so
the asset compiler does not store oversized bitmaps; paths unchanged). Take the SVGs as they are: do not redraw, approximate,
re-colour or re-set them in a font.

- **Wordmark.** Lowercase `cuadrao`, Space Grotesk 2.0.0, weight 700, letter-spacing
  -0.085em, line-height 1, with the font's kerning on (a-d, r-a, a-o), the website's
  `.wordmark`; SIL OFL 1.1. Native code shows it only as the outlined SVG, which
  already carries the kerning, never as live text, so the font is neither shipped nor
  approximated. Earlier icon sheets used 600 / -0.045em; that was an approximation.
- **Lockup.** Mark and wordmark as one composition. With the wordmark's font size as
  1 em: mark height 1 em (the mark's ink is about 1.11 em wide), gap 0.25 em from the
  mark's unrounded box (about 0.28 em between ink and first letter), the mark's centre
  0.35 em above the baseline, clear space 0.5 em on every side. The lockup SVGs'
  viewBox is authoritative; do not recompute these numbers from prose. Minimum: wordmark at 20 px font size,
  mark alone at 16 px.
- **Files.** Each brand SVG names its gradients `a`, `b`, `c`: use them as image files
  (asset catalog), never inline two of them in one document. `cuadrao-lockup-light.svg` / `cuadrao-lockup-dark.svg` (welcome),
  `icon.svg` (app icon and favicon, tiled), `cuadrao-mark-light.svg` (mark alone on
  light), `cuadrao-mark-dark.svg` (mark alone on `#172b26` only).
- **Colours.** Light surface `#fafbf8`: wordmark `#172b26`; mark front `#2f5a49` to
  `#1d4236`, back `#cfdccf` to `#bccdbf`, overlap `#a6e06a` to `#6fbf46`. Dark surface
  `#172b26`: wordmark `#fafbf8`; mark front `#fffcf2` to `#e3dcc2`, back `#8fa38f` to
  `#5b7566` at 55% opacity, overlap `#b6e87a` to `#7fcb4f`. Gradients run top-left to
  bottom-right. The dark artwork is drawn for `#172b26`; on any other dark its
  translucent back square changes tone slightly. The welcome screen therefore uses
  `#172b26`; the invitation card and the chat empty state keep their palette
  backgrounds and accept that small shift rather than change their layout.
- **One component.** `CuadraoBrand` draws the lockup everywhere in the app (welcome at
  268 pt wide through `CuadraoWelcomeLockup`, the invitation card and the chat empty
  state at the compact 153 pt, which keeps the 32 pt height the old lockup had; the chat
  empty state applies its existing 0.85 scale, so it shows about 130 pt wide).
  Never redraw it or set the wordmark as text.
- **Large decorative mark.** Invitation pages keep their large mark (208 pt frame):
  `CuadraoMark` in the asset catalog, `cuadrao-mark-light.svg` on light and
  `cuadrao-mark-dark.svg` on dark (not the tiled icon), so it is the same size in both. On
  the invitation page's palette background it accepts the same slight back-square tone
  shift as the lockup there.
- **App icon.** `icon.svg` rendered full-bleed at 1024 x 1024 with the tile corner
  radius 0 (iOS rounds it and rejects transparency). Dark and tinted variants are not
  designed yet; a new founder decision is needed first.
- **Typography roles stay native.** The brand adds no text style. Buttons, headings,
  forms and amounts keep the roles in the table above.

## 4. Components and selection

Use existing native buttons, sheets, rows and context menus. Preserve approved
icons and icon-only navigation. Major content uses the existing 24-point page
inset, with 8/12/16/24 spacing where appropriate; these are layout conventions,
not a mandate to flatten artwork, chat composition or native Form insets.
Keep touch targets at least 44 points. Show error text alongside semantic color.
The money editor retains its short grouping fade and respects Reduce Motion.
Scroll-edge materials belong behind persistent chrome, never across interactive
content. Surface-specific gestures retain their existing meanings.

### Sheet controls

Every sheet closes and confirms the same way, through three components in
`CuadraoSheetToolbar.swift` and `CuadraoCancelToolbar.swift`. None has a glass
oval, rim or underline.

- **Cancel, Close or Back** is plain text on the leading side.
- **Confirm** is a check mark on the trailing side, used only when the sheet has no
  primary button of its own (Edit profile, crop photo, Reorder Home, receipt item,
  exact amount). A sheet with its own button shows Cancel only, so two confirms never
  compete. A disabled check is dimmed and still announced.
- **Done** is plain text on the trailing side, used only on sheets that show something
  and have nothing to confirm (filters, spaces, people, currency list, updates, saved
  receipt viewer).
- Nothing sits above the keyboard: no Done button, keyboard toolbar item or input
  accessory view, because on iOS 26 each floats as a blue pill over the sheet's own
  button. A keyboard closes by tapping away from the field (one rule for the whole
  app in `KeyboardTapAway`), by scrolling, or with Return. A tap on or right beside the
  field being edited keeps the keyboard. `ios/DesignPreviewTests/run_no_keyboard_accessory.py`
  fails the model-test run when a source adds one.

Do not add raw `ToolbarItem(.cancellationAction)` or `(.confirmationAction)` items to
a sheet. Alerts and confirmation dialogs keep the system look.

### Choices and currency

Single-choice selectors show the current value and a downward chevron, with a
checkmark on the selected option. Apply this grammar to space and currency choices,
where a choice is necessary. Reserve the sliders/filter icon for controls that open
multiple filter dimensions. Align typography, caret weight and accessible touch
targets across equivalent controls while retaining each surface's composition.
Short choice lists can use native menus; long currency catalogs use a searchable
sheet. Fixed currency is a static code without a chevron, with a lock where useful.
Home's currency choice filters a view; plan/group creation chooses a currency that
stays fixed afterward. Shared presentation does not introduce conversion or change
those ownership rules. Delivery status remains in the main roadmap.

### Selection alignment

`CuadraoChoiceMenu` uses a native Picker with text-only options. The system owns
the checkmark column; never switch a selected row to Label while unselected rows
use Text. Keep captions centered independently of selection indicators. Appearance
checks sit on the preview image; searchable currency checks sit after a Spacer.

## 5. Layout, depth and touch targets

Keep the existing 24-point content inset and the 8/12/16/24 spacing rhythm. Native
Forms keep their own insets. Hierarchy comes from spacing and role, not extra labels
or repeated cards. Financial rows align names left and numeric columns right.

Keep native material behind chrome. Rounded chart surfaces and Plan artwork retain
their approved shapes; use depth for grouping or allocation selection, not to imply
larger financial proportions. Visible icon size and its 44-point hit target differ.
Do not add a pill background merely to enlarge a tap target.

## 6. Surface hierarchy

<a id="locked-plan-hierarchy--october-1-2026"></a>
### Plan

Share Home's interaction language while preserving Plan's hierarchy. Plan's main
distinction is Para ti / En grupo. The founder's subsequent whole-surface review
supersedes the separate Tus planes space filter and standalone forecast-month row.

Keep one space choice attached to the forecast, alongside Tu mes / Your month,
not beside the page title. Dates remain explicit within the chart/readout; do not
repeat October above it. Hide the choice when only one compatible space exists.
Tus planes shows all active personal plans with space metadata on each card, without
Todos or a second space filter. A forecast-space change never sets a new plan's
space: creation starts with an explicit editable Personal choice.

Keep the header's primary plus, whose action and accessible name follow Para ti /
En grupo. Remove the header ellipsis: preview controls belong in the title hold
menu, while each collection has a quiet archived-items destination for its own
records, reachable after all items are archived. Keep a welcoming creation action
in empty states; remove the duplicate group-create action from populated lists.
Cards use the shared collection gestures below; detail retains visible editing,
renaming and archive actions. Group People owns invitations and member management.
Tapping the avatar stack opens People. Only the local organizer scenario exposes
member management; removal is reviewed, blocks outstanding balances, and retains
historical expenses/contributions. Connected permissions remain roadmap work.

Same action, same behavior; different purpose, different composition. Shared
money behavior, typography, icons, selectors, gestures and return paths provide
consistency. Plan retains its illustration, exploration and personal language. The forecast
playground entry is a quiet “Explorar escenarios / Explore scenarios” link beneath
the forecast, rather than an attention-seeking headline or primary action.
Implementation status and future work live in the design branch's
[consistency pass and Home chart follow-up](https://github.com/lagarcess/argus/blob/fc7650eab4eac9298a09eea37eddc3964a709fba/docs/specs/argus-execution-board.md#cuadrao-consistency-pass-and-home-chart-follow-up),
at commit `fc7650ea`.

The header reads **Lo que viene / What's ahead** with the primary plus beside it.
Remove the old literal Plan heading and its subtitle. Preserve the heading's
preview hold menu and the Para ti / En grupo choice.

### Home welcome and history perspectives

Home uses a compact, static native-system greeting: Hola / Hello plus Profile's
preferred name, or just the greeting if missing. The shared preview profile state
lives in `CuadraoHomeCanvas`; Profile edits and Home read the same value. No date
competes with the greeting. Space switching changes financial scope, not the welcome.
The space creation shortcut uses the shared plain plus. In Household, the existing
avatar stack sits left-aligned between spaces and the amount. It includes the owner
and accepted members only; pending invitations never count as members. Tapping it
opens People. The current preview roster supports the owner and one companion.
The greeting's context menu holds the preview reset tools (first use, household
with no shared accounts, with activity) and opens the gallery (Guía visual /
Visual guide). Both are on integration in `CuadraoHomeCanvas.swift`, since #786
(design PR 3) for the gallery entry.

### Home account and activity shortcuts

Cuentas / Accounts and Movimientos / Activity share the same trailing plain plus.
Home keeps quick creation and row gestures; no accounts-header ellipsis or redundant
configuration cluster. Account rows use the same collection gestures as Plan.
Tapping the Accounts heading opens its management surface, where visible reorder
and archived-account recovery remain discoverable. The entry remains available
when all accounts are archived. Account detail retains visible owner actions;
Home's shortcut does not become the only way to manage a record.

### Home section order and first use

**Ordenar Inicio / Reorder Home** moves whole feed sections through its existing
compact sheet with Cancel, Done and Reset. Greeting, space selector and navigation
stay fixed. Saved section order applies across spaces and survives relaunch. Empty
sections retain their place without adding empty feed content. This is distinct
from the tray-free account and Plan item ordering in section 10.

Personal Home with no accounts offers one add-account action; don't show empty
summary totals or reordering before content exists. Household distinguishes no
household, alone, invitation pending and joined with nothing shared. Inviting or
accepting never silently shares private accounts or creates joint records.

Invitation sharing uses the native share sheet. Creating or copying a link is not
delivery or membership; dismissing the sheet proves neither. Recipient acceptance
and Ahora no / Not now preserve private accounts. Preview acceptance remains local;
production invitation and permission contracts stay in the main roadmap.

### Accounts

Accounts remain in Home's feed, with every non-archived account visible and no
internal list scroller or View all cap. Tap opens the account's balance and activity.
Current shared collection gestures below supersede the original hold-action/reorder
tray experiment. Account detail retains its native back path and visible actions.

Creation requires a type; name and initial balance remain optional. Blank balance
means unknown. **Pending founder confirmation (October 13, 2026):** the Mobile lane
change #1047 (not on integration yet) starts a new money account saved with no opening
amount at a recorded 0.00. Property, vehicle, other asset, Business and on-device guest
accounts stay unknown. Until the founder confirms, "blank means unknown" is the rule
on this page. Currency belongs at the left of the right-aligned money editor.
Preserve approved vectors, inline validation, whole-unit-first entry and a disabled
save while required input is invalid. Archive preserves history and supports recovery.

The [September 30 Accounts study](../../../docs/specs/cuadrao-accounts-design-lock.md)
is historical provenance, not a second current rulebook. Its earlier ellipsis,
hold-menu and reorder-tray rules are superseded here. Connected reconciliation and
financial contracts retain their own owners.

## 7. Financial charts and storytelling

### Home balance chart

Home keeps a compact recorded-position chart, with the same debt signs and asset
ownership shares as its amount. `CanvasBalanceHistory` owns that projection;
`CuadraoHomeOverview` owns presentation. Select currencies separately, never add
or convert them. Personal/Hogar retain the existing account-scope owner.

Tap to retain one observed date/value, hold and drag to inspect, and use Hoy/Today
to return to the current balance. The native chart leaves regular vertical
scrolling available. Keep the pine line, subtle fill and readable range labels.
Keep test/sample provenance in preview tooling and evidence, not in Home content. Missing history gets an empty state; no flat
line, inferred pre-account balances or forecast is invented. A new account or
currency/kind/share change cannot silently borrow old example observations.

The existing Próximamente / Upcoming link opens Plan as a separate surface; it does not imply its sample
forecast is computed from Home's accounts. Connected history/forecast ownership
and scope-preserving navigation remain in the main roadmap.

<a id="locked-home-and-expanded-insights-direction--october-1-2026"></a>
### Expanded insights

**Quiet Home:** compact welcome, existing space selector, amount, one history line,
and short available-history ranges (for example 1 mes / 1 month). Only offer ranges
supported by the person's recorded history. Keep a subtle, accessible expand icon.
Do not show Evolución / Distribución controls, insight paragraphs or test/sample
copy on Home. Genuine unknown/partial values remain distinguishable from zero;
removing preview disclosures does not authorize invented financial facts.

**Expanded insights:** the native Balance / Actividad choice is right-aligned in
the anchored header, above the compact period/chart controls. Each moving page
starts with a left-aligned period headline above its amount. Week/month show the
first and last calendar dates; year shows the year. Use
`CuadraoTypography.feature` (native title serif) and ink, not the secondary
supporting style. Larger text can wrap without shrinking the title or truncating
choices. Keeping controls anchored lets the period and its evidence move together.
Balance remains recorded net position. Activity uses expenses from the same local
activity owner as the transaction list, filtered by space and currency. Transfers,
income and changing balances do not become spending. Historical fixtures stay in
preview code; connected delivery is still roadmap work.

**Controls:** Semana / Mes / Año and the chart / distribution icons share one compact
row. Adapt to localized labels and larger text, preserving 44-point targets. No
previous/next chevrons or Back to today button in detail. The single period label
above the amount follows the selected range; tick context stays on the axis. Swipe right for older periods, left toward the present;
stop at the oldest available period and today. Real neighboring period pages follow the finger through native paging; do not
use decorative edges with an update-only gesture. VoiceOver custom Previous/Next period actions provide the same navigation.
Long-press inspection must not page; vertical scrolling remains available.

Switching chart/distribution preserves the selected period. For Balance, historical
allocation uses matching recorded account snapshots and identifies their date;
never relabel current assets as a past allocation. Missing observations remain
unknown. The hero remains recorded net balance in both modes. Its current snapshot says
Balance neto · Hoy / Net balance · Today. Label the positive composition separately
as Distribución de activos / Asset allocation, with its own total. Deductions and
net balance remain separate from the positive 100% composition.

**Activity:** vertical bars stack expenses by category. Week uses daily buckets;
month uses calendar-week buckets clipped to the month, labeled with their day
spans; year uses months. Respect the locale calendar when forming week boundaries.
Only recorded dates contribute; future buckets remain unfilled. Colors match category rows, which disclose the same
expense records. The distribution icon shows the selected period's category shares.
`CuadraoExpenseCategoryStyle` owns category colors and vector choices. Reuse
WelcomePalette's Plan accents (pine, clay, sunshine, bloom and overlap); do not
introduce the default neon chart palette. Category icons match Home's 24-point,
1.7-point rounded vector family and 42-point soft tile. Reuse approved Home paths
where their meaning fits; keep new outline vectors in the same asset catalog.
Totals remain actual recorded expenses, never projected spend or savings. Unknown
categories are Otros / Other, never guessed from merchant text.

**Chart storytelling and empty states — founder locked October 1:** expanded
Activity follows chart and takeaway → category breakdown → highlights. Place one
short factual takeaway near the hero amount. Below the categories, show at most
two useful highlights, each with a plain-language explanation, a matching category
icon/color where relevant, and supporting comparison bars or a small trend chart.
Reuse the shared typography, category artwork and palette; no competing icon family.
A highlight opens the supporting records or category detail in the same context.
Show Ver todos / See all only when additional supported highlights exist.

Choose meaningful evidence: a category change, a large transaction explaining a
spike, or a sustained trend with sufficient history. Label both comparison periods
and use a common visual scale. For a running period, compare only the equivalent
elapsed portion of the previous period with adequate recorded coverage; a partial
month must not be compared with an entire completed month. Do not force a trend
from sparse history or color an increase as a moral failure. Balance explanations
must derive from recorded positions/contributors, never infer spending or returns
from balance changes. Home itself keeps its quiet hierarchy.

Empty, first-use, loading and unavailable states follow the shared state rules in
[section 8](#8-empty-loading-and-unavailable-states). Keep historical highlights
labeled with their real window even when the selected month is empty.

Reference basis: the founder-provided Wallet screenshots show highlights below
categories, explanatory comparisons and category icons. The Mobbin search returned
[Wallet period/category breakdown](https://mobbin.com/screens/82a32fee-bf5f-4c39-b4b8-0e002de68d4c)
and [Health explicit no-data states](https://mobbin.com/screens/e60672f4-262f-478f-9326-6a6a2262f43f),
not those exact Wallet highlight screens. This adapts their hierarchy to Cuadrao;
it does not adopt Wallet's typography or duplicate its entire card stack.

**Distribución: decomposable bar, category rows, account detail.** The bar shows the
whole positive asset distribution. Selecting a category emphasizes its segment;
other segments recede or separate while preserving context. Matching expandable
rows reveal the category's accounts, keeping amounts readable independently of the
visual. Example: Todo → Ahorros → Mi tranquilidad / Fondo de la casa. Tiny segments
remain reachable through rows. Tapping the selected category again or Todo restores
the whole. Keep category colors stable across the bar, rows and drill-down.
Category rows use a down/up chevron to expand or collapse. Account rows use a
right chevron and push the existing account detail within the insights navigation
stack. Back preserves the selected category and scroll position. Detail actions
reuse `CuadraoAccountModal` and the shared account model; edits are reflected on
return. Do not dismiss insights and strand the person at the Accounts root.

Subtle depth is approved as a visual direction, with proportional front-facing
widths; depth must not distort the financial comparison. The proposed gentle
separation/reassembly is our interaction design, not a claim that reference
screenshots prove that animation. Use a simple fade with Reduce Motion. Account
percentages retain the same positive-asset-total denominator through drill-down;
any later within-category percentage needs an explicit denominator label. Debt and
other negative balances stay separate. One currency at a time, with no conversion.
The user-facing name stays Distribución / Breakdown, not Decomposition.

The bar is the baseline. A donut remains only a future experiment candidate with
the same rows, values and interactions; no chart-type chooser is required on Home.

References: [Wealthsimple history](https://mobbin.com/screens/667bf371-6e73-42f5-b179-574e62d9b64b),
[Apple Wallet periods](https://mobbin.com/screens/82a32fee-bf5f-4c39-b4b8-0e002de68d4c),
[Apple comparison and paging](https://support.apple.com/en-us/102329),
[Public allocation](https://mobbin.com/screens/07c1ff8c-f0da-4bf0-919a-d21b2ac5ff43),
[Origin disclosure](https://mobbin.com/screens/7edb40e1-bbbe-4c1a-9916-f10f943d7685).
Founder-supplied decomposition screenshots are retained with this decision's
[reference evidence](https://github.com/lagarcess/argus/blob/fc7650eab4eac9298a09eea37eddc3964a709fba/docs/reports/evidence/cuadrao-native-design/home-distribution-reference/README.md)
on the design branch at commit `fc7650ea`. They motivate the hierarchy and subtle depth; they are not
Cuadrao implementation or acceptance evidence.

### Balance change breakdown

The line view answers **Qué cambió / What changed**. Below its chart, show opening
and closing observations with their actual dates, followed by each account's signed
contribution to the change. Use the same scoped currency, debt signs and ownership
share as the hero. Account rows push the existing detail and preserve insights on return.

`CanvasBalanceHistory` owns snapshot matching and contribution arithmetic. One typed
period projection supplies the hero, comparison and breakdown. Row changes must
reconcile to the displayed total change. Never fill a missing opening amount with
zero or call an unexplained balance increase income, earnings or investment return.

A new month keeps the latest known balance and its observation date. A single
observation gives a known amount but no change comparison. If the baseline is inside
the period, name its actual date rather than claiming a full-period comparison.
An empty historical interval may show its last known observation with its date;
never draw a fabricated flat history or use later data. Partial accounts remain explicit.

The stacked view answers **Dónde está / Where it is**: positive assets, individual
accounts and separate deductions. Changing chart mode does not change financial scope.

### History-based insights and interactive periods

Expanded Balance and Activity share native horizontal paging with vertical scroll
inside each page. The period headline, amount and supporting content travel
together; metric and period/chart controls remain anchored. Cancelled drags return
to the same page, completed drags reveal the adjacent period, and range changes
return to the present. Long-hold chart inspection must leave the selected period
unchanged. Home retains its compact inspection behavior.

Activity highlights use completed covered months for 6/12-month averages and a
recent-three versus preceding-nine category comparison. Covered zero months count
in averages. Incomplete months and future pages never leak into these windows.
A sustained category comparison needs activity throughout both windows, not an
isolated large expense. One or two supported highlights sit below categories;
Ver todos / See all opens the full collection grouped into averages and categories.
Each insight opens its supporting monthly records. Current-period comparisons
still use equal elapsed coverage. No history means no invented average or trend.

`CuadraoAllocationBar` owns the dimensional bar for both financial views. Geometry,
selection lift, Reduce Motion fade and proportional widths agree across views;
asset types and expense categories retain their own meaning and shared palette.

## 8. Empty, loading and unavailable states

Use one shared chart-state treatment. Soft static silhouettes fade into the page,
with a restrained Cuadrao ornament using the Plan palette. Decorative shapes have
no axes, values, category encoding, inspection gestures or accessible data points.
They identify the missing content without pretending to be records.

| State | Presentation and behavior |
| --- | --- |
| Current month with missing coverage | Sin datos / No data, compact artwork and a record-entry action; no invented zero or comparison |
| Historical period with missing coverage | Sin datos / No data and neutral past-period copy; keep period navigation |
| Confirmed complete coverage with zero spending | Show the known zero, even without an expense row; distinguish it from missing coverage. A comparison against it shows the amount difference, not a percent ([October 2 Home comparisons lock](../../../docs/specs/argus-decision-log.md#home-comparisons), clarified 10:18 PM CT) |
| First use with no history | Welcoming artwork and one working record-entry action |
| Incomplete or unavailable history | Distinguish unknown from zero; omit unsupported comparison claims |
| Real records, even one | Real chart immediately; leave future buckets empty |
| Loading | Same visual footprint with subtle temporary motion; freeze motion for Reduce Motion |

Empty is settled; loading is temporary. Do not shimmer a permanent empty state or
invent waiting in a synchronous preview. The gallery can demonstrate loading; an
actual surface shows it only while a real operation is pending. Historical insights
may remain below a new month's empty state with their actual date window visible.
Keep period navigation available; do not silently switch to the previous month.

References: [Wise empty monthly spending](https://mobbin.com/screens/409c5a70-c57f-4abc-a2e4-f8361af101ba),
[Klarna faded chart forms](https://mobbin.com/screens/1b5919b4-9b02-43db-8e30-540ea5f01fce),
[N26 balance breakdown](https://mobbin.com/screens/3dd2aac4-95c3-4f96-b2ae-bf7455f3400d),
[Copilot account changes](https://mobbin.com/screens/935c477f-d2a5-43b4-b68b-1640269c698e).
These references informed the approved adaptation; they do not define Cuadrao's fonts.

## 9. Money editing

Typing means whole units first, with optional decimal places. Group thousands
while editing and preserve selection/caret, including deletion near separators.
Pad the currency's decimal places on blur. Reject letters, malformed pasted
grouping, excess precision and out-of-range values without silently rounding an
entered amount. Show the inline error and prevent saving while it remains.
A valid subsequent edit clears that field's error; editing another field does not.

Empty is an empty input with a quiet formatted-zero placeholder. Positive entered
amounts use the shared adaptive teal. Optional account balance still distinguishes
unknown from zero. Required plan amounts must be entered before creation; optional
starting progress can remain zero. New personal plans and groups no longer inherit
fictional target or monthly-contribution defaults. Named examples keep their sample
values. Existing records and repayment amounts derived from an actual preview
balance can still populate their editors; those are not arbitrary suggestions.

Keep primary and secondary amount hierarchy, currency choice at creation and
fixed currency after creation. Do not change financial storage or add exchange
rates as a typography/input change. A proposed future recommendation must disclose
its basis and be explicitly applied; no such recommendation is implemented here.

## 10. Gestures and continuity

### Collection gestures

`CuadraoOrderedCollection` is the shared interaction for Home account rows,
personal plans and group cards. On integration it came with #783. Since #785
(design PR 2), personal plans and group cards use it. Since #786 (design PR 3),
Home account rows use it and Home opens plans and groups, all inside the design
preview only. This records the implemented baseline; the account-specific
October 4 target below supersedes its account action arrangement. Tap opens detail; swipe right reveals Edit
(including rename); swipe left reveals Archive. Neither swipe executes on a full
swipe. Hold and drag reorders directly in place, without a context menu or an
ordering tray. Sheets are for actual editing, invitation and review flows.

Use native iOS 27 reorder/swipe containers. iOS 17–26 retain native drag/drop and
visible Edit/Archive alternatives; the deployment minimum remains unchanged.
Accessibility actions include Edit, Archive, Move up and Move down. The existing
account management destination remains an alternative with visible order handles.
`CuadraoCollectionOrder` applies only the visible IDs without moving hidden or
archived records. Preview owners persist plan/group order and fixture account order;
connected viewer-specific order is a future contract, not a shared financial edit.

#### Account and movement actions: October 4 target

Founder-approved, not yet a connected implementation claim. For account rows,
swipe right reveals Add movement; swipe left reveals Edit and More. More holds
applicable secondary account actions, including Archive. Keep hold-and-drag
reordering and visible/accessibility alternatives under the existing ordering
contract. Personal Plan and group-card Edit/Archive actions are unchanged.

Movement rows open the selected transaction detail, preserving their origin.
Provide Edit and category shortcuts through the same authorized correction
owner; detail retains secondary actions and an accessible alternative. Do not
copy message deletion semantics into financial records. No full swipe executes
a destructive financial action. Only expose actions the current user can perform.
The exact movement edge arrangement remains part of the bounded UI slice.

The inspected WhatsApp references show [More/Archive](https://mobbin.com/screens/0f157572-5769-4d59-aca4-6b40022c0d57)
and [Unread/Pin](https://mobbin.com/screens/8b979f79-a8d1-4f0e-873a-f79f803a179b)
on opposite sides. They inform grouping; Cuadrao's actions and financial
confirmation rules retain their own meaning. #824 owns connected gesture and
navigation reconciliation, with command permissions from #822.

Native period paging follows the finger and settles or cancels naturally. Chart
inspection is tap or hold, leaving ordinary horizontal paging and vertical scrolling
available. Motion communicates state and continuity. Reduce Motion uses restrained
fades instead of lift or decorative animation. Return preserves selected scope,
period and category. A date boundary never resets financial facts.

## 11. Capture, Chat and Recents

Use these native capture and Recents conventions. The production web behavior
remains in the Argus guide.

- The attachment action is **Escanear** in Spanish and **Scan** in English,
  with a document-scanner symbol. Photos and files remain independent entry points.
- Apple's native document scanner owns capture, page cropping and retakes. Cuadrao
  owns entry, saved drafts and review around that native screen. Delivery and the
  interpretation boundary belong to [roadmap C01](https://github.com/lagarcess/argus/blob/fc7650eab4eac9298a09eea37eddc3964a709fba/docs/specs/argus-execution-board.md#c01--native-scan-and-receipt-split),
  on the design branch at commit `fc7650ea`.
- Recents uses title-first rows, separate Pinned/Recent sections, unread/current
  indicators, and one conversation object shared with Chat and Search. Do not repeat a sample subtitle on every row. Dates derive from the last
  message timestamp, shared with Search; metadata changes do not update recency.
  Render Hoy/Ayer or Today/Yesterday, then a localized short date (including the
  year for older years). Unknown dates remain absent. Preview fixtures have explicit
  sample message dates; these are not backend history.
- Swipe right pins/unpins; swipe left archives or restores. Rows show quiet dates at the trailing edge, with no visible ellipsis.
  Touch-and-hold and VoiceOver actions expose the same contextual commands.
  Pin uses amber, archive uses slate, restore uses Cuadrao green; delete retains
  its destructive red treatment in the menu, not a new swipe action. Mark read/unread comes first, followed by pin, rename, archive and delete.
  Delete requires confirmation and retains recovery in Deleted. Actions on a row
  never also open it. Opening temporary-chat destinations keeps the existing discard
  confirmation. Archiving/deleting the active regular chat opens a fresh chat.

### Contextual conversation entry

**Founder-locked October 2, 2026.** One **Preguntar a Cuadrao / Ask Cuadrao**
action points the assistant at a selected record. Broader permitted app context
remains available; selecting a record tells Cuadrao what the person means.

1. Keep Home and collection rows quiet. Use existing record actions instead of
   repeating a Chat button beside each item. Preserve assigned edit/archive/order
   gestures.
2. Make the action discoverable in record details. Reuse an existing action menu;
   where none exists, use a quiet labelled action in the detail content rather
   than adding an ellipsis solely to conceal it.
3. Show the selected record in a removable composer chip. Chart context includes
   its selected period and filters. This is a focus reference, not a separate
   group messaging destination or a requirement for one conversation per plan.

4. Open contextual Cuadrao over the active detail. Closing it reveals the same
   source, selection and scroll position. The main Chat tab uses the same
   conversation and unfinished message.
5. Selecting context changes only the removable chip. Preserve existing text and
   attachments; never send automatically. Removing the chip leaves the message
   intact. A sent message retains its original context reference.
6. Keep unfinished regular conversations reachable when switching chats. Temporary
   conversations keep their existing discard rules; selecting a record does not
   silently enable broader app context or turn Temporary off.

The founder approved completing this continuity behavior on October 2. UI delivery
and connected context contracts remain in
[roadmap C04](https://github.com/lagarcess/argus/blob/fc7650eab4eac9298a09eea37eddc3964a709fba/docs/specs/argus-execution-board.md#c04--contextual-conversation-handoff),
on the design branch at commit `fc7650ea`.

Mobbin references inspected October 2:
[Fabric item selection and Ask AI](https://mobbin.com/flows/a9096ee9-967b-4110-a738-d77acb704671)
shows the chosen item in the composer;
[Grok document question](https://mobbin.com/flows/1fdf3416-da7c-49f1-b9be-8f481dc6f586)
shows a removable source attachment. These support explicit context, not a claim
that either app implements Cuadrao's record permissions or continuity contracts.

### Group people and receipt placement

**Founder-approved October 2, 2026.** Personas / People contains member identity,
shared-plan balances or contributions, invitations, and former participants.
Receipt capture and saved receipt cards belong in Gastos / Expenses. Contextual
Cuadrao entry belongs in the group's existing detail actions, not beside Add receipt
or above the people list.

Member removal is secondary and owner-only. A trailing swipe reveals Remove on
iOS 27 without executing on full swipe. Older systems retain a native contextual
action; VoiceOver exposes the same review. Preserve the existing removal review,
outstanding-balance restriction, and history. Members are not reorderable cards.
Keep the shared debt-direction labels, colors and symbols visible.

[Bond's member actions](https://mobbin.com/screens/a6e69b41-ae6e-4e2e-b6b6-b0bb75f27e9c)
keep removal out of the resting row;
[X's removal row](https://mobbin.com/screens/873d27a4-ba4e-4922-8055-09d02debd295)
shows a trailing swipe action. Cuadrao preserves its own confirmation and ownership
rules rather than copying those apps' deletion semantics.

### Receipt capture and review

Choose a receipt source once. Chat **Escanear / Scan** opens the native scanner.
The group's and existing Saved receipts view's **Añadir recibo / Add receipt**
menus offer Scan, Photos and Files, then open the chosen native picker immediately. Do not insert a second source
chooser, currency form or promotional landing page before acquisition.
Capture has one full-screen presentation containing the native picker. Do not open
a receipt tray underneath it. After the original is saved, close capture before
opening the review sheet. Cancel before acquisition returns to the originating
screen without a receipt. An unfinished expense keeps its edits on return.

Capture saves a draft and opens a compact review. **Después / Later** lets the person
leave immediately; leaving never confirms an expense. A personal import can remain
without a currency until review. Choose its currency once before editing amounts
or confirming; then it stays fixed. A group supplies its fixed currency immediately.
An unknown currency must not be displayed as DOP or another guessed currency.
Return through the existing Chat or group entry. Do not add a top-level receipt
inbox or automatically reopen review on launch.

Personal Chat, group Chat and Plan open the same receipt identity. Generic files
remain attachments unless the person chooses the receipt journey. Keep merchant,
date, category and total readable before revealing editing controls. Use the shared
money editor and category symbols. A keyboard appears only when editing requires it.

A group receipt inherits the group's fixed currency. Confirm the payer and people,
propose an equal split, and reveal item assignment under **Por consumo / By item**.
Shared items retain one price and several people. Show how many items still need
assignment. Included tax and service appear once; an added tip is separate.
The final review shows each person's share before one explicit confirmation.

Color explains direction. **Te deben / You're owed** uses the positive pine accent;
**Debes / You owe** uses a legible warm clay accent. Settled amounts use a quiet
neutral treatment. Always retain the direction label and symbol. Category colors
continue to describe categories, not debt, and destructive red remains separate.

Location is optional and attached only through an explicit choice. Label a capture
pin as where the receipt was scanned, not as the merchant's address. Denied access
never blocks a draft. A later review must not relabel the phone's current location
as the original capture location.

Prepared examples demonstrate the proposed automatic categorization and review.
An imported image or file must not acquire invented merchant, amount or item data.
Real extraction and connected posting remain roadmap work.

References: [Apple document camera](https://developer.apple.com/documentation/visionkit/vndocumentcameraviewcontroller),
[scan output](https://developer.apple.com/documentation/visionkit/vndocumentcamerascan),
[Apple gestures](https://developer.apple.com/design/human-interface-guidelines/gestures),
[Claude title-first history](https://mobbin.com/screens/9059f305-c9bb-44b9-b0fe-efe19e50a428),
[Messages contextual swipe controls](https://mobbin.com/screens/1ad68688-b638-4f85-b754-7ef96f6d45e5).
The exact gesture mapping above is Cuadrao's adaptation, not a claim that these
reference apps use the same mapping.


October 1 refinement: the founder replaced the visible Recents ellipsis with
last-message dates. Swipe colors adapt [Fiverr's amber star](https://mobbin.com/screens/d6624e4d-927d-46b3-a3f1-d763ef7dd04a)
and [Telegram's gray archive](https://mobbin.com/screens/7b4ae82f-5122-4626-82c9-a6ef11bea8dc).
The row's shared contextual actions are exposed through Apple's
[accessibility actions](https://developer.apple.com/documentation/swiftui/accessible-controls).

### Search and Profile boundaries

Search retains its supported Accounts, Activity, Plans, Chats and Files perspectives.
Memory appears only with the enabled native memory feature and its controls.
Financial currency filters do not filter nonfinancial content. Household excludes
private chats, source files and memory; a preview filter is not authorization.
The October 2 support-surface assignment reopens Profile polish within the existing
identity and App, Account, Support groups. Settings keep literal native headings.
Release builds hide the avatar-editing entry and development builds keep the full
editor, including initials, themes and photos
([decision of October 3, 2026](../../../docs/specs/argus-decision-log.md#october-3-2026-avatar-editing-in-release)).
Group covers are a separate feature. Home reads the same preferred name and
avatar owner; Appearance retains its existing preference owner.

Invitation QR codes may represent app access, a household invitation or a plan
invitation. The card must name its purpose. This does not enable public profile
QR codes, usernames or contacts discovery. Keep those deferred. The release
rules below distinguish counters and permissions before sharing visual components.

A plan code card inherits its plan's artwork or selected cover, name and member
context. The QR sits on an opaque light panel with a clear four-module margin;
art stays outside the code. On-screen and exported cards share one composition.
The native share sheet owns user-directed export. Sample-code wording travels
with preview exports, and scanning must not imply a live invitation until the
invitation contract is connected.

Profile keeps the main navigation on its landing page, with clearance inside the
scrolling content so Sign out stays above it. Pushed Settings pages hide the main
navigation and return through native Back. The navigation path owns this state.

Generic feedback borrows Argus's comment, problem and idea categories. Only a
problem opens the title, reproduction steps and expected/actual outcome fields.
Switching categories preserves each draft; Save draft accepts unfinished text.
Conversation-specific ratings and context consent belong to contextual feedback,
not the Settings entry. Submission and durable intake remain roadmap work.

Search opens account and plan results in its own navigation stack. Chat handoff
has an explicit return to Search and preserves the current query and filters.
An empty perspective describes that content type. A no-match state preserves the
query and offers a clear way to remove it or reset the active filters.

Updates is a quiet inbox with read/unread state, source-linked rows and direct
access to notification preferences. Opening a detail keeps Back anchored to the
inbox. A contextual suggestion is not a new financial event; do not invent an
event date, threshold crossing or milestone from a current value. Ordinary
transactions and chat messages do not each earn an inbox notification. The bell
and list derive unread state from the same visible items. Delivery preferences
control future delivery channels; disabling them does not erase the inbox.
The current preview keeps read state and edited profile fields for the session.
Connected identity and durable inbox state belong to the main roadmap.

Empty inbox and no-match states use small Cuadrao artwork and one useful recovery
action where available. Reserve chart silhouettes for financial chart states.
Do not add permanent loading motion or test disclosures to these screens.

## 12. Localization and accessibility

Support English and Latin American Spanish in every static label, empty state and
action. Use the app locale for date captions; currency precision and formatting come
from `CanvasMoney`. Controls expand for localized text and accessibility sizes rather
than clipping or shrinking labels. Preserve clear VoiceOver labels, selected states,
header traits and gesture alternatives. Known zero and unavailable data remain distinct
in spoken output. Art is decorative unless it conveys information absent from text.

Verify real screens in both appearances and larger text. Component previews alone do
not prove keyboard, navigation, scrolling, focus or gesture continuity.

## 13. Release-readiness interaction rules

**Founder direction, October 2, 2026. Design requirements, not delivered screens.**
The [main roadmap](../../../docs/specs/argus-execution-board.md#cuadrao-release-ui-landing-order)
owns checkpoint order, implementation gaps and acceptance. These rules refine the
native release. They do not remove existing production web capabilities.

### Integration is the starting point

Household and Connected changes retain current integration's models, commands,
auth flow and permission checks. Their presentation uses the approved shared
Preview views, artwork and interaction details. Preserve
create, accept, consent, transfer, leave, remove, close and recovery behavior.
Administrator authority over membership is separate from ownership of money.
A household membership does not expose accounts, files or conversations by itself.

### Account deletion and legal access

Use **Eliminar cuenta / Delete account**, distinct from deleting a financial
account, leaving a household or removing a member. Put Privacy and Terms in a
stable signed-in Help or Account destination. Opening either preserves the user's
place in Settings. Legal content must use approved URLs and remain reachable
from authentication as appropriate.

Use one readable consequences screen, followed by one deliberate verification
step. Show the applicable consequences together rather than a series of retention
screens. Use native titles, body type and the shared destructive action treatment.

- Explain removal of the account and its data. The stated exceptions are the
  anonymous invite record and, in plans other people own, the person's amounts
  kept under "Exmiembro" / "Former member" (decision 17 in the
  [lane handoff](../../../docs/specs/lanes/mvee-five-lane-handoff.md#lane-6-account-deletion)).
  Add Iris's founder-locked consequences block from the lane handoff's
  [copy](../../../docs/specs/lanes/mvee-five-lane-handoff.md#copy-founder-locked-iriss-wording).
  This copy must match the connected deletion and retention contract before
  release; the UI cannot certify anonymization itself.
- If the person administers a household, explain succession to its longest-standing
  remaining member. Show the actual successor only when resolved by the owner.
- If the person owns shared history, explain that deletion removes the household's
  locked copy of that history. Do not describe deleting another member's records.
- A shared debt plan whose owner deleted their account is archived read-only, not
  handed over (decision 19 in the lane handoff, the Head of Engineering's call).
  Participants see Iris's founder-locked banner on it, from the lane handoff's
  copy, item 4, and get the usual member note. Show it as a closed plan with no
  edit actions.
- Reuse supported identity verification, such as a code sent to an existing verified
  channel. Cover incorrect/expired code, resend, cancellation, in-progress and
  retry states without requiring a support conversation.
- Show **Cuenta eliminada / Account deleted** and the signed-out destination only
  after confirmed completion. A queued operation gets an honest pending state.
  A failure retains a recoverable state and does not pretend deletion succeeded.

The six-lane handoff owns deletion retention and the founder-locked copy. With no
remaining member, the household closes (October 2 lock). Shared-plan amounts
remain under Exmiembro / Former member with receipts, photos and notes removed.
Open balances become closed, not paid. Plans the person created pass to their
longest-standing participant, except shared debt plans, which close read-only.
Do not promise that previously emailed support copies are erased. Deletion
completion, retention and resolved successor facts belong to the connected
contract. Ordinary leave, removal and archive keep their distinct
history rules. Account deletion must not silently redefine them.

### Welcome screen

One main brand composition and the two native actions; nothing else.

- The lockup is the only brand element: no repeated header lockup, no tagline.
  Marketing's lockup SVG, at most 268 pt wide, narrowing on small screens instead of
  clipping, centred in the space above the buttons (about 40% down a 874 pt screen).
- Background is the website's paper `#fafbf8` on light and `#172b26` on dark. This
  applies to the welcome screen only; other screens keep their palette backgrounds.
- Actions keep their native treatment: `Crear cuenta` / `Create account` as the
  filled primary and `Iniciar sesión` / `Sign in` as the outlined secondary, 56 pt
  high, 16 pt corners, 28 pt side margins, 12 pt apart, native body semibold type that
  follows Dynamic Type. The screen scrolls at large text sizes; nothing is clipped.
- Accessibility: the lockup is one element labelled `cuadrao`. Identifiers:
  `cuadrao.welcome.lockup`, `cuadrao.welcome.signup`, `cuadrao.welcome.signin`.

### Authentication and invitation purpose

Sign-in for TestFlight is **Apple, Google and email**
([October 2 founder decision](../../../docs/specs/argus-decision-log.md#sign-in-for-testflight)).
Email works with any address and has an in-app confirmation step. Engineering
builds Apple and Google behind default-off flags until the founder supplies the
keys; connected buttons stay hidden while a flag is off.
Both social flows need loading, user cancellation, recoverable error and return
to the intended invitation. Use Apple's native authorization treatment. Request
a preferred name only if it is missing; reuse a supplied or saved name. A private
relay email is valid and does not imply that the name is missing. Cancellation
returns quietly to the same form. Do not expose a provider button as working until
its connected path is ready.

App access is invitation-gated for this native release. A valid link or QR can
supply the code; do not make people retype it. Manual entry supports paste,
validation, retry and invalid/expired/used-code states. People without access can
open the cuadrao.ai waitlist. Existing admitted users retain Sign in and recovery.
Preserve the invitation across installation/authentication when supported; manual
code entry remains the recovery path. Visiting the waitlist is not proof of joining.

| Invitation purpose | What it grants | Visible rules |
| --- | --- | --- |
| Invite someone to Cuadrao | App admission | Share link, copy code and QR represent one invitation; show the returned quota, such as 7 de 10 disponibles / 7 of 10 left |
| Invite to a household | Membership after acceptance, and app admission for a new user | Only the administrator sends it; it does not consume the personal ten; account sharing remains a separate consent |
| Capped group access link | App admission for several invitees, beta only | Only the founder creates it, with a cap and expiry; show actual usage, full, expired and revoked states; a full link sends people to the waitlist; it never grants household membership or creates a financial plan |
| Invite to a plan | Participation in that specific plan | Preserve the plan's membership and permission rules; do not treat it as app admission |

A cap, a remaining personal quota and a member count are different values. Read
them from their owners. Opening or sharing a link does not count as acceptance.
Founder group links are beta-only and created by the founder account. Under the
lane contract, group-link redemptions do not use anyone's personal ten; read the
counter from its owner rather than guessing it. A household invite also admits a
new user: carry both purposes through validation without charging the personal
quota.

A full link explains the limit and offers the waitlist. Show **Estás en la lista /
You're on the waitlist** only after enrollment is confirmed. Use one invite-card
composition with purpose, identity/theme, code, QR and native sharing. Keep QR art
outside its quiet zone and test scan reliability. Public profile QR stays deferred.

### Updates, chart truth and historical access

Use the Updates inbox for invitation acceptance, administrator handoff,
owner deletion with history removal, and household closure. Use Iris's
founder-locked wording for the deletion note and the new-owner message. The lane
that causes an event writes its entry: Household writes the closure when the last
member leaves, and Lane 6 writes the administrator handoff and any closure a
deletion causes. The Updates lane owns only how entries are displayed and the push
opt-in (Yelena's rule, October 2). Each notice explains
what changed and opens the relevant authorized destination. A closed household
opens an explanation, not a broken detail. Do not leave deleted financial history
readable through an old notification.

Bill reminders appear three days before the due date and on the due date. The
bill owner determines whether an occurrence is still due, paid or cancelled.
Explain push value in context, then request native permission. Declining push
preserves the inbox. A denied permission offers system Settings when the person
asks to enable it again. Push text never includes amounts or sensitive detail.
An example is **Tienes un pago próximo / You have an upcoming payment**.

A zero comparison baseline produces a monetary difference, never an infinite or
invented percentage. Missing coverage produces **Sin datos / No data**. A month
with confirmed complete coverage and no spending is a known zero and shows 0,
even without an expense row. It counts in covered averages and amount
comparisons. Unknown, partially covered and confirmed zero periods remain
different states. Keep the
quiet chart and established category colors, icons and typography.

After an account move, the previous household's authorized pre-move history is
muted and read-only. Pair color with a lock and **Solo lectura / Read-only** plus
an explanation of the move. Keep readable contrast and hide editing gestures.
Do not show new activity in the old scope. An archive, move, withdrawal of access
and deletion are different operations; the backend must resolve which history
remains authorized. An owner deletion removes its retained copy as stated above.

### Profile visibility and feature-timed controls

Remove the **Por correo / By email** notification toggle. This does not remove
email authentication or recovery. Household email invitations and update email
are not in this pass (October 2 lock), so no email invitation delivery is implied.
Hide Personalization, Security and sessions, Shared conversations, Removed
activity, Memory, Usage, More options, conversation bulk actions and
the avatar-editing entry in the initial native release. Design commit `fc7650ea`,
from Yelena's UI checklist, hides Personalization, Security and sessions, Shared
conversations, Removed activity and photos. Usage, More options and conversation
bulk actions are hidden by #786 (`a20362d3`) as a Head of Engineering judgment
call. Memory (`.memory`) is hidden until native memory arrives with its
controls. These are designed rows whose backend is still owed, not cuts.
`CuadraoFirstRelease` hides them only in release builds; development builds show
every row, and `--cuadrao-release-gates` previews the release set in a DEBUG build. Yelena is ordering their backends after chat. **Por correo / By email**
stays removed because Updates go to the inbox and push only. Keep supported
preferences, help, legal links, deletion and sign-out.

The founder retained the personal photo picker in the design. Its shared avatar
and photo components stay. Release builds hide the avatar-editing entry and
development builds keep the full editor, including photos
([decision of October 3, 2026](../../../docs/specs/argus-decision-log.md#october-3-2026-avatar-editing-in-release)). An unset avatar keeps
the existing Profile tab icon. Any selected initials, theme or photo replaces
that icon, with the same selection read by Profile. Removing the selection
restores the icon. Selection remains session-local until the profile storage
contract is connected; do not imply a hosted upload. Avoid
empty destinations, unavailable rows and new Coming soon settings sections.

Before a live chat, voice or document-reading action shares personal data with
an external model, disclose the data, recipient and purpose and obtain explicit
consent. Preserve the draft when declined; do not send or automatically process
an attachment. Local capture/save-for-later remains usable. This control must
ship with the first feature that transmits data, even if that precedes the other
later controls. Temporary mode is not a substitute for this consent.

Connected sources and Disconnect arrive with Gmail/Plaid activation, under the
existing source owner. Explain stopping future access separately from deleting
previous imports. Memory controls arrive with native memory, including off and
reset as distinct actions; switching off must not falsely claim deletion.

### Trackle reconciliation

Borrow clear labels for amounts and budget progress paired with elapsed time in
Plan. Keep Home quiet; do not add Trackle's dense shortcut and category rows.
Keep Cuadrao serif headings, rounded money, illustration and category icon family.
The shared avatar belongs in the Profile tab, without an extra Home action.
An unset avatar keeps the existing Profile tab icon. Selecting initials, a theme
or a photo replaces that icon without an additional circular frame or background;
the tab's shared selected highlight remains. Profile settings and the editor use
a circular frame. Their empty state is a muted circle with an add-camera symbol,
not an enlarged navigation glyph. A photo retains its circular crop in both places.
[Instagram's edit-profile screen](https://mobbin.com/screens/968761ca-7201-48ba-a822-06e3f5c6620a)
was visually inspected for the circular picture and separate editing action;
the empty camera treatment follows the founder's supplied reference.

### Research and interpretation

Mobbin references were visually inspected on October 2. They are curated examples,
not evidence of a verified App Store ranking or proof of backend behavior.

| Reference | Borrow for Cuadrao | Avoid copying |
| --- | --- | --- |
| [Revolut account closure](https://mobbin.com/flows/c6abd5fc-c863-4a79-8388-f9ef0debebda) | Reachable legal links, explicit consequences and verification recovery | Multiple retention pitches and bank-specific retention claims |
| [Places invitation code](https://mobbin.com/flows/bf0f3d56-76ea-4605-92ed-9e50cd3afc67) | Warm invitation entry with focused code input | Its Skip bypass; Cuadrao's access gate must remain truthful |
| [WHOOP join by code](https://mobbin.com/flows/f1c6102e-f9d6-48ed-96c4-5109ae0b3ca9) | Explain the code's purpose and show invalid-code feedback beside input | Team membership as a substitute for app admission |
| [Discord invitation settings](https://mobbin.com/flows/a53ad8f2-6e22-409b-b6f6-783ceed2a44d) | Expiry and maximum uses together, followed by native sharing | Discord's visual density and temporary membership model |
| [LINE invitations](https://mobbin.com/flows/e605fc4e-9bd4-4f54-81fc-72f4b4a689ab) | Shareable invitation/QR identity | Contacts upload or discovery scope |
| [Monzo notification settings](https://mobbin.com/flows/bd14662f-e114-4479-908c-35c7f242a3b2) | Separate useful notification purposes and clear settings groups | Its email controls or unrelated products |

Apple's [deletion guidance](https://developer.apple.com/support/offering-account-deletion-in-your-app/)
allows identity confirmation and requires an accessible deletion path with truthful
completion. [Review guidelines](https://developer.apple.com/app-store/review/guidelines/)
cover TestFlight, privacy access, login options and consent before third-party AI
sharing. These requirements do not establish Cuadrao's retention implementation.
Apple's [sign-in guidance](https://developer.apple.com/videos/play/wwdc2022/10122/)
explains first-authorization name delivery; its [notification guidance](https://developer.apple.com/documentation/usernotifications/asking-permission-to-use-notifications)
favors permission requests in context.

<a id="13-implementation-owners"></a>
## 14. Implementation owners

| Shared decision | Single code owner | Usage |
| --- | --- | --- |
| Typography roles | [CuadraoTypography.swift](../../../ios/ArgusFoundation/Cuadrao/CuadraoTypography.swift) | Use named roles for expressive headings and amounts. Native navigation titles, text bodies and system controls retain their semantic text styles. |
| Adaptive palette | [WelcomePalette](../../../ios/ArgusFoundation/Cuadrao/CuadraoCanvas.swift) | Pine, sage, background, surface, ink, borders and positive input text. Shared native Cuadrao views use these adaptive light/dark values in both Preview and connected hosts. The historical type name remains; do not create a competing Cuadrao palette. Preview routing stays isolated from real financial records. |
| Money parsing and caret behavior | [CanvasDecimalInput.swift](../../../ios/ArgusFoundation/Cuadrao/CanvasDecimalInput.swift) | Accounts uses this native text editor on integration. Since #785 (design PR 2), Plan uses the same editor through `PlanAmountInput` and `CanvasMoneyValueInput`, inside the design preview only; Home reaches Plan since #786 (design PR 3). |
| Currency precision, formatting and limits | [CanvasMoney.swift](../../../ios/ArgusFoundation/Cuadrao/CanvasMoney.swift) | Derive preview limits and formatting here; currency selection/immutability retains its plan/group owner. |
| Numeric preview bridge | [CanvasMoneyValueInput.swift](../../../ios/ArgusFoundation/Cuadrao/CanvasMoneyValueInput.swift) | Adapts existing numeric preview models to decimal editing text; it is not a new financial store. |
| Plan amount composition | [PlanAmountInput.swift](../../../ios/ArgusFoundation/Cuadrao/Planning/PlanAmountInput.swift), on integration since #785 (design PR 2), design preview only | Currency, rounded amount, focus underline and inline error. Accounts keeps its approved bordered, right-aligned composition around the same editor. |
| Choice labels and add shortcuts | [CuadraoChoiceControls.swift](../../../ios/ArgusFoundation/Cuadrao/CuadraoChoiceControls.swift) | Shared value/caret, native single-selection menu, fixed code and section plus. |
| Balance period and account changes | [CuadraoBalancePeriod.swift](../../../ios/ArgusFoundation/Cuadrao/CuadraoBalancePeriod.swift) | One observed opening/closing pair, signed contributions and matching allocation; reuses `CanvasBalanceHistory`. |
| Empty and loading treatment | [CuadraoChartState.swift](../../../ios/ArgusFoundation/Cuadrao/CuadraoChartState.swift) | Shared decorative forms; `CanvasSpendingStory` classifies financial states. Loading is a gallery specimen until a real operation needs it. |
| Expanded chart controls | [CuadraoChartControls.swift](../../../ios/ArgusFoundation/Cuadrao/CuadraoChartControls.swift) | Icon view choice and localized period choice, including selected accessibility state. |
| Account management | [CuadraoAccountsCollection.swift](../../../ios/ArgusFoundation/Cuadrao/CuadraoAccountsCollection.swift), on integration since #786 (design PR 3), design preview only | Native ordering and archive recovery over the existing shared account model. |
| Reference gallery | [CuadraoDesignGallery.swift](../../../ios/ArgusFoundation/Cuadrao/CuadraoDesignGallery.swift), on integration since #786 (design PR 3) | Uses real shared components. Preview-only. It opens from a hold on Home's greeting → Guía visual / Visual guide, or with `--design-gallery`. That routing came to integration with #786. |

<a id="14-reference-gallery-and-evolution"></a>
## 15. Reference gallery and evolution

The gallery is on integration since #786 (design PR 3), inside the design preview
only. The gallery offers Spanish/English, light/dark and large-text controls. It contains
headings, amounts, a row, a disabled action, working Account/Plan input fields,
and the real shared choice, add and chart controls.
Use it to compare states, then verify the actual surfaces: isolated components do
not prove keyboard, scroll or navigation behavior. The gallery does not post data.

For a new feature, reuse the shared roles/components first. When a new pattern is
necessary, mark it experimental in its assigned work; promote it here after review
and migrate equivalent usages together. Update the component owner rather than
copying a style or parser. Preserve each surface's useful personality. Tests should
exercise meaningful behavior and navigation, not freeze every styling literal.
Future chart, receipt, provider and connected-delivery work stays in the roadmap.

The gallery also shows primary/secondary/row money beside the shared editor and the
empty-month, first-use, unavailable and loading treatments. Use it as a living specimen,
not a screenshot-only style sheet. The main roadmap owns implementation status and
unfinished connected work; this guide owns the approved visual and interaction rules.
