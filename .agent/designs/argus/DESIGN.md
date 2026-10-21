# Design System Inspired by Argus

This guide owns Argus visual conventions and existing interaction detail. The
[MVEE](../../../docs/specs/argus-minimum-viable-ecosystem-experience.md) owns
surface structure, household contexts, and product behavior. New native
implementations and exact glass materials require design/engineering work.

## 1. Visual Theme & Atmosphere

Argus should feel elegant, modern, crisp, and trustworthy across personal and
household finances. Preserve Space Grotesk display typography, Inter body text,
generous whitespace, and the restrained neutral palette. Existing large
marketing-hero sizes are surface-specific examples, not default sizes for
mobile financial screens.

Near-black and white dominate Argus. Product status and financial meaning use
the muted palette below. The implemented shared colors are owned by
[`web/app/globals.css`](../../../web/app/globals.css); existing artifact and
failure treatments have their own shared owners listed below. Do not introduce
bright alternate values or assume every reference color has a global CSS token.

Argus pairs pill-shaped actions with quiet text and icon navigation. The
[Buttons section](#buttons) owns their distinct visual sizing; the
[mobile hit-area baseline](#17-mobile--web-behavior) applies to both. A compact
visible control must still be easy to tap. Inter body text and restrained
letter-spacing support a calm, readable financial experience.

**Key Characteristics:**
- Space Grotesk weight 500; 136px is a large marketing-hero example, not a mobile default
- Near-black (`#191c1f`) + white, with restrained semantic color
- Pill action buttons and quiet navigation controls, sized by the [component styles](#buttons)
- Inter for body text with positive letter-spacing (0.16px–0.24px)
- Muted financial, informational, attention, and failure treatments
- Flat content surfaces with depth through contrast; glass mobile navigation follows the MVEE
- Tight display line-heights (1.00) with relaxed body (1.50–1.56)

## 2. Color Palette & Roles

### Primary
- **Argus Dark** (`#191c1f`): Primary dark surface, button background, near-black text
- **Pure White** (`#ffffff`): Primary light surface and dark-button label
- **Light Surface** (`#f4f4f4`): Secondary button background, subtle surface

### Historical Brand / Interactive References
The earlier guide also listed blue references (`#494fdf`, `#4f55f1`,
`#376cd5`). These are not shared tokens in `web/app/globals.css` and are not
instructions to recolor current primary controls or links. Preserve each
existing component's treatment unless its redesign is explicitly assigned.

### Semantic (Muted Alpha Palette)
Argus avoids "casino-terminal" vibrancy. Semantic tones are desaturated to feel educational and premium.

- **Muted Rose** (`#d66d75`): `--rui-color-danger`, financial negatives and existing destructive controls; not the universal system-failure color
- **Muted Teal** (`#5ba897`): `--rui-color-teal`, positive states
- **Emerald Mist** (`#70a38d`): Existing artifact success tint
- **Soft Blue** (`#7da0ca`): Existing artifact informational tint
- **Slate Indigo** (`#5a677d`): Reference neutral accent; not a shared global token
- **Dusty Gold** (`#c2a44d`): `--rui-color-warning`, attention/warning

### Neutral Scale
- **Mid Slate** (`#505a63`): Secondary text
- **Cool Gray** (`#8d969e`): Muted text, tertiary
- **Gray Tone** (`#c9c9cd`): Reference for borders/dividers

### Existing Implementation Owners

- [`globals.css`](../../../web/app/globals.css) owns the shared teal, warning,
  and rose tokens, plus light/dark page backgrounds and foregrounds.
- [`artifact-status-tones.ts`](../../../web/lib/artifact-status-tones.ts) owns
  artifact status colors, including their text, border, wash, and dark variants.
  Use its existing status mapping; a finished calculation is not automatically
  a positive financial outcome.
- [`failure-treatment.ts`](../../../web/lib/failure-treatment.ts) owns retryable,
  terminal, degraded, and quiet failure treatments. Terminal failures use warm
  red (`#b3593f` light / `#e08d70` dark), distinct from financial-negative rose.
- [`avatar-theme.ts`](../../../web/lib/avatar-theme.ts) owns avatar color choices;
  they are personalization, not financial status.

Use these owners rather than recreating their treatments from the palette.
Muted swatches are not universal small-text colors: retain the existing darker
light-theme text and lighter dark-theme text variants. Always pair meaning with
labels or symbols. New financial-record states and a complete ecosystem dark
theme still require design; this reconciliation does not define those contracts.

## 3. Typography Rules

### Font Families
- **Display**: `Space Grotesk` — geometric grotesque, fallback stack: `Space Grotesk`, `Inter`, `Arial`, `sans-serif`
- **Body / UI**: `Inter` — standard system sans
- **Fallback**: `Arial` for specific button contexts

### Hierarchy

| Role | Font | Size | Weight | Line Height | Letter Spacing | Notes |
|------|------|------|--------|-------------|----------------|-------|
| Display Mega | Space Grotesk | 136px (8.50rem) | 500 | 1.00 (tight) | -2.72px | Stadium-scale hero |
| Display Hero | Space Grotesk | 80px (5.00rem) | 500 | 1.00 (tight) | -0.8px | Primary hero |
| Section Heading | Space Grotesk | 48px (3.00rem) | 500 | 1.21 (tight) | -0.48px | Feature sections |
| Sub-heading | Space Grotesk | 40px (2.50rem) | 500 | 1.20 (tight) | -0.4px | Sub-sections |
| Card Title | Space Grotesk | 32px (2.00rem) | 500 | 1.19 (tight) | -0.32px | Card headings |
| Feature Title | Space Grotesk | 24px (1.50rem) | 400 | 1.33 | normal | Light headings |
| Nav / UI | Space Grotesk | 20px (1.25rem) | 500 | 1.40 | normal | Navigation, buttons |
| Body Large | Inter | 18px (1.13rem) | 400 | 1.56 | -0.09px | Introductions |
| Body | Inter | 16px (1.00rem) | 400 | 1.50 | 0.24px | Standard reading |
| Body Semibold | Inter | 16px (1.00rem) | 600 | 1.50 | 0.16px | Emphasized body |
| Body Bold Link | Inter | 16px (1.00rem) | 700 | 1.50 | 0.24px | Bold links |

### Principles
- **Weight 500 as display default**: Space Grotesk uses medium (500) for ALL headings — no bold. This creates authority through size and tracking, not weight.
- **Billboard tracking**: -2.72px at 136px is extremely compressed — text designed to be read at a glance, like airport signage.
- **Positive tracking on body**: Inter uses +0.16px to +0.24px, creating airy, well-spaced reading text that contrasts with the compressed headings.

## 4. Component Stylings

### Buttons

The pill variants below specify primary and secondary actions. Their padding
does not apply to quiet navigation, disclosure controls, or icon-only controls.
Preserve those controls' compact visible text or icon, without adding a pill
background or the action variants' horizontal padding. Extend the invisible hit
area as needed to meet the [mobile target baseline](#17-mobile--web-behavior),
without overlapping adjacent targets. Keep accessible names, visible focus and
selected/expanded states appropriate to the control. Visual size and tap area
are separate requirements.

**Primary Dark Pill**
- Background: `#191c1f`
- Text: `#ffffff`
- Padding: 14px 32px
- Radius: 9999px (full pill)
- Hover: opacity 0.85
- Focus: `0 0 0 0.125rem` ring

**Secondary Light Pill**
- Background: `#f4f4f4`
- Text: `#000000`
- Padding: 14px 34px
- Radius: 9999px
- Hover: opacity 0.85

**Outlined Pill**
- Background: transparent
- Text: `#191c1f`
- Border: `2px solid #191c1f`
- Padding: 14px 32px
- Radius: 9999px

**Ghost on Dark**
- Background: `rgba(244, 244, 244, 0.1)`
- Text: `#f4f4f4`
- Border: `2px solid #f4f4f4`
- Padding: 14px 32px
- Radius: 9999px

### Destructive confirmations

The existing web owner is
[`ConfirmDialog.tsx`](../../../web/components/ui/ConfirmDialog.tsx), used by
Recents (`ChatSidebar`) and Omnisearch (`ChatCommandPalette`). Preserve this
pattern when carrying record removal into new surfaces:

- Center the dialog above the active surface with a dimmed, lightly blurred
  backdrop. Existing light treatment: black at 25%, 4px blur, white panel,
  18px radius, subtle border, 20px padding, maximum width 384px. Dark treatment
  uses black at 60% and the existing dark panel. Respect viewport margins.
- Use a specific question, name the record, and explain the real consequence.
  Keep supporting copy restrained; do not imply permanent deletion or recovery
  that the operation does not support.
- Cancel is an outlined pill. The explicit destructive action is a muted-rose
  (`--rui-color-danger`, `#d66d75`) pill with a white label; destructive entry
  points use the same semantic treatment. Keep 48px targets in the phone sketch.
- Retain the component's compact 17px display heading and 13px body/action text;
  its existing semibold dialog heading is an exception to general heading defaults.
- Use a labeled modal alert dialog with focus containment, safe initial focus,
  Escape/backdrop cancellation and focus return. Production `useModalSurface`
  owns topmost-layer and system-back behavior. Do not claim native parity from
  the disposable web dialog. While saving, prevent duplicate confirmation and
  respect the owner's busy-state dismissal rules.
- Apply the rose family consistently to destructive entry points in Accounts,
  chat, Recents/Search and Profile & settings, including Delete all conversations
  and Request account deletion. Do not color ordinary navigation (such as opening
  Recently Deleted) as destructive.
- Account deletion remains a support request in the existing product, not an
  immediate delete operation. `ProfileDeleteRequestDialog.tsx` uses a soft rose
  action (12% rose background, `#b94c55` text; `#e7a2a8` text in dark mode) for
  Contact support. Preserve that semantic difference from a filled-rose delete
  confirmation; common color meaning does not require identical action severity.
- Conversation deletion can name Recently Deleted because that recovery exists.
  Financial-entry removal must describe its own actual recovery. The sketch's
  immediate Undo is not a promise of a production retention policy.

Founder confirmed reuse of this pattern for account-entry removal on September
27, 2026. The balance-check experience is owned by
[MVEE account activity and balance checks](../../../docs/specs/argus-minimum-viable-ecosystem-experience.md#account-activity-and-balance-checks).
Use inline form errors, not browser validation popups, in the reviewed account
forms. Financial differences stay neutral and labeled; rose is reserved here
for the destructive action, not for an unexplained balance difference.

### Cards & Containers
- Radius: 12px (small), 20px (cards)
- No shadows — flat surfaces with color contrast
- Dark and light section alternation

### Existing Alpha Navigation

The MVEE owns the pivot navigation and header behavior; retain the following as existing Alpha styling context.

- Space Grotesk 20px weight 500
- Clean header, hamburger toggle at 12px radius
- Pill CTAs right-aligned

## 5. Layout Principles

### Spacing System
- Base unit: 8px
- Scale: 4px, 6px, 8px, 14px, 16px, 20px, 24px, 32px, 40px, 48px, 80px, 88px, 120px
- Large section spacing: 80px–120px

### Border Radius Scale
- Standard (12px): Navigation, containers
- Card (20px): Feature cards
- Pill (9999px): Primary and secondary action buttons

## 6. Depth & Elevation

| Level | Treatment | Use |
|-------|-----------|-----|
| Flat (Level 0) | No shadow | Existing content surfaces; MVEE mobile navigation has a separate glass direction |
| Focus | `0 0 0 0.125rem` ring | Accessibility focus |

**Existing surface treatment**: Preserve flat content surfaces. The MVEE explicitly approves a glass treatment for mobile navigation; exact material, elevation, and native implementation remain design/engineering work. That exception does not authorize decorative shadows throughout the app.

## 7. Do's and Don'ts

### Do
- Use Space Grotesk weight 500 for all display headings
- Follow the [component button styles](#buttons); preserve each surface's quiet text and icon navigation controls.
- Keep the palette to near-black + white for marketing surfaces
- Apply positive letter-spacing on Inter body text

### Don't
- Keep content surfaces flat; the approved mobile navigation may use a glass material and appropriate elevation.
- Don't use bold (700) for Space Grotesk headings — 500 is the weight
- Don't confuse compact visible controls with small hit areas; follow the [mobile target baseline](#17-mobile--web-behavior).
- Don't apply semantic colors to marketing surfaces — they're for the product

## 8. Responsive Behavior

### Breakpoints
_Design targets below are intentional for this system; if implementation keeps Tailwind defaults, map these ranges explicitly in component specs._
| Name | Width | Key Changes |
|------|-------|-------------|
| Mobile Small | <400px | Compact, single column |
| Mobile | 400–720px | Standard mobile |
| Tablet | 720–1024px | 2-column layouts |
| Desktop | 1024–1280px | Standard desktop |
| Large | 1280–1920px | Full layout |

## 9. Agent Prompt Guide

### Quick Color Reference
- Dark: Argus Dark (`#191c1f`)
- Light: White (`#ffffff`)
- Surface: Light (`#f4f4f4`)
- Positive: Muted Teal (`#5ba897`)
- Negative: Muted Rose (`#d66d75`)
- Neutral: Slate Indigo (`#5a677d`)

### Example Component Prompts
- "Create a hero: white background. Headline at 136px Space Grotesk weight 500, line-height 1.00, letter-spacing -2.72px, #191c1f text. Dark pill CTA (#191c1f, 9999px, 14px 32px). Outlined pill secondary (transparent, 2px solid #191c1f)."
- "Build a pill button: #191c1f background, white text, 9999px radius, 14px 32px padding, 20px Space Grotesk weight 500. Hover: opacity 0.85."

### Iteration Guide
1. Space Grotesk 500 for headings — never bold.
2. Keep pill action styling; compact icon-only navigation is allowed with accessible names and a clear selected state.
3. Flat content surfaces; glass mobile navigation follows the MVEE direction.
4. Muted semantic colors — never terminal neon.
5. Calm motion and status language for trust.

## 10. Product UX Principles

- **Preserve chat within the ecosystem**: Existing chat behavior remains valuable. The MVEE owns the roles of chat and the other surfaces; manual entry and direct controls are first-class paths.
- **Not a Dashboard**: Argus should never feel like a dashboard-first backtesting tool.
- **Progressive Disclosure**: Offer clear summaries and focused detail through conversation or direct controls. Manual entry must work without AI.
- **Trust Through Honesty**: Result cards must be simple, trustworthy, and explanation-ready.
- **Frictionless Revisit**: Help people resume a record, plan, question, or comparison without rebuilding context.
- **Anti-Clutter**: Avoid dense tables, multi-tab parameter overload, and "trading terminal" noise.

## 11. Primary Chat Interface

- **Persistent Input**: The chat input must remain highly visible and ergonomic (especially on mobile).
- **Starter Prompts**: Displayed as polished, high-contrast chips or cards to reduce "blank page" friction.
- **Streaming States**: AI responses support real-time token streaming to feel alive.
- **Calm Progress States**: When simulating, use human-centric status language and subtle motion (pulse dots, progress shimmers).
  - Progress states are driven by **`stage_start` server-sent events from the agent runtime pipeline**, not local frontend timers.
  - The frontend must map `stage` values from the backend to these display labels:

    | Backend `stage` | User-facing label |
    |---|---|
    | `interpret` | "Understanding your idea..." |
    | `clarify` | "I have a question..." |
    | `confirm` | "Here's what I found..." |
    | `execute` | "Running backtest..." |
    | `explain` | "Reviewing results..." |
    | `next_step` | "What's next..." |

  - The frontend must **never fake these states with timers**. If no `stage_start` event has been received, show a neutral loading indicator only.
- **Inline Results**: Backtest result cards appear directly in the flow of conversation.
- **Minimal Actions**: Follow-up actions should be clear but few. Under
  private-alpha defaults, examples are "Explain result", "Refine idea", and
  "Add decision". "Save Strategy" and "Add to Collection" must not appear while
  their product flags are disabled.
- **Pills are buttons; rows are next moves.** A pill is a true button — result
  and confirmation card CTAs, starter prompts, and the user's own echoed action
  bubble. Anything conversational the assistant offers — clarify options,
  follow-ups, discovery candidates — renders as a stacked next-move row under
  the message that offered it, so a question and its answers stay together.
  Sentence-length choices do not belong in pills; they wrap badly and they hide
  the detail that makes the choice meaningful.

### Next-move rows

- **Anatomy**: borderless at rest, with a muted leading `↳` glyph carrying the
  affordance — touch devices never hover, so the rest state must read as
  tappable on its own. On hover or press, a hairline border plus wash appears,
  **sized to the text**: a short label gets a short box.
- **Hit area is not the visible box.** The tappable region spans the full
  message column and stays at least 44px tall regardless of how narrow the
  hover box is. Never make someone aim at the text.
- **Detail is visible, never a tooltip.** A discovery row shows the
  resolver-owned name and its reason inline. Tooltips hide the very thing that
  makes one candidate different from another, and they do not exist on touch.
- **Text is sized by rules, not by locale.** Never truncate identity; clamp only
  secondary detail. Use logical properties so RTL mirrors (the `↳` included),
  keep separators as their own nodes so locales can restyle them, allow wrapping
  in scripts without spaces, and let content grow the row rather than fixing its
  height.
- **Grounded rows wear their evidence; the drawer owns the rest** (decision
  2026-07-28). Each grounded discovery row carries one muted domain chip — its
  first corroborating source — after the reason text; tapping it opens the
  sources drawer anchored to that source. The footer under grounded rows is the
  `N sources ›` entry point alone: never a respelled domain list, and never an
  "as of" date, because the search date is not the articles' date — each source
  shows its own date in the drawer, which also keeps sole ownership of outbound
  URLs. Cheap answers carry no chips and show the from-general-knowledge marker
  line instead; zero sources **is** the ungrounded signal, derived, never
  asserted.

### When next moves are live

- **Exclusive vs menu.** Clarify options answer one question, so the group stops
  rendering once answered — the reply is already in the transcript. Discovery
  candidates are a menu, not a question: choosing one does not retire the
  others, so they persist and stay tappable. Discarding them would force the
  user to ask again, which re-runs a metered search to re-tell them something
  Argus already said.
- **One in-flight lock.** The composer and every next-move row share a single
  "a turn is running" signal. Persistent rows outlive the newest turn, so
  without the shared lock they become a way to fire turns around a disabled
  composer. Locked rows stay visible and readable — they are evidence — and
  simply stop accepting taps. This is per-tab UI state, not a substitute for a
  backend concurrency guard.
- **Cards win.** While an active card owns the conversation's actions, no
  conversational next moves are offered alongside it.

## 12. Result Card Design

Result cards are the primary unit of "validation." They must be glanceable and honest.
- **Truthful Charts**: Embedded result charts may be used when they stay calm, readable, and mobile-friendly. Markers must represent executed fills only, not raw strategy triggers.
- **Low-Clutter Events**: Dense buy/sell activity should use progressive marker density and sparse labels so the chart reads like evidence, not a trading terminal.
- **Fixed Metrics**: Show beginner-friendly metrics by default (e.g., Total Return, Max Drawdown, Benchmark Delta; Win Rate only when meaningful closed trades exist).
- **Structure**: Title, date range display, status pill, metrics rows, assumptions footer, and CTAs.
- **Assumptions Footer**: Must be visible but secondary.
  - *Example*: `Long-only • Equal weight • No fees/slippage • Benchmark: SPY`
- **Visual Distinction**: Assumptions should be styled with muted slate typography to distinguish them from the "Result" without feeling like a warning.

### Computed answers: answer first, editable inputs

A computed answer (a loan payment, a savings goal, a yield, valuation scenarios) uses one card pattern in chat, Search, decisions and shared pages.
- **Answer first**: The prose answers the question and states each computed figure from the card. The card sits under it, collapsed to the result and a toggle.
- **Inputs that drive the result**: Opened, the card shows the three to five inputs that drive the result, each with one quiet provenance line: stated by you, the page title and date it was read from, Argus market data on its date, or an assumption the answer states. A blank input or the solved unknown never shows; a figure only you know is asked as one plain question instead.
- **Edit in place**: Typing a new input recomputes instantly with no model call, and the prose's figures follow the card; the previous result is labeled until the new one lands.
- **Stored beside today**: A reopened decision and the Search dossier show the stored result and today's side by side; the stored result never moves.
- **Honest failure**: Inputs that do not solve keep the card open, name the one field, and offer the backend's typed fix as a tap, through the one failure treatment. A lookup that fails answers from Argus market data and stated assumptions and says what it could not look up, with the lookup's notice under the answer; it never becomes the answer or the conversation title.
- **Compare and continue**: Two results of one kind sit side by side with signed differences in each fact's own unit. Continuing opens a new chat that links back to the unchanged source.
- **Frozen receipts**: A shared calculation is read-only, lists what Argus used with each page, and offers no recompute.
- **Width**: At 390px the card, the comparison and the dossier stack in one column; from 768px the comparison sits in two.

## 13. Retired Strategy Surface

The dedicated Strategies destination and result-card Save action are retired.
Current saved-idea recall and decision-state browsing live in Omnisearch/Idea
Ledger. Historical Strategy metadata may hydrate without rendering a new write
control or destination.

## 14. Recents, Legacy Records, and Search

- **Recents Feed**: A chronological continuity surface for chats and completed
  runs. Do not advertise hidden Strategies or Collections as current
  private-alpha destinations.
- **Legacy Collections**: Historical rows remain read-compatible, but no
  navigation, picker, setting, empty state, or write action is rendered.
- **Idea Recall**: Omnisearch/Idea Ledger is the active artifact-recall surface
  for Ideas, Evidence, Decisions, Backtests, and their source conversations.
- **Fuzzy Search UI**: Global omni-search should support "Fuzzy Human Memory" with suggestion chips:
  - *Suggestions*: `Last week`, `Tesla ideas`, `Crypto`, `Pinned`, `Recent chats`.

### Growing lists across ecosystem surfaces

Founder-locked September 27, 2026. Inherit the current Argus list interaction
patterns; do not independently reinvent pagination or disclosure in each surface.

| Surface | Approved interaction |
| --- | --- |
| Home account preview | Up to three rows with View all opening Accounts; no unbounded inline expansion |
| Accounts | Show more / Show less within groups when lists become long; short lists need no expansion control |
| Account activity, Search, Updates | Fetch further rows in batches, keep visible results and scroll position, and offer retry on failure |
| Plan | Compact previews with View all, or expandable groups when the content warrants them |

“Show more / Show less” changes visibility of already loaded rows. “Load more”
fetches another batch. Do not present those as interchangeable operations. Preserve
stable row geometry, keyboard focus, accessible expanded-state/group labels and
adequate touch targets. Hide unnecessary controls when no more rows exist.

**Identified inheritance from the current product code:**

- [`ChatSidebar.tsx`](../../../web/components/sidebar/ChatSidebar.tsx) owns Recents
  group expansion controls with `aria-controls`, `aria-expanded` and group-specific
  accessible names. [`chat-recents.ts`](../../../web/lib/chat-recents.ts) owns
  visibility selection and the existing five-row group default. Home's three-row
  preview is a separate summary choice, not a change to the Recents constant.
- [`ChatCommandPalette.tsx`](../../../web/components/sidebar/ChatCommandPalette.tsx)
  owns cursor-backed result loading, request-currentness and duplicate protection.
  [`CommandPaletteLoadMoreControl.tsx`](../../../web/components/sidebar/CommandPaletteLoadMoreControl.tsx)
  owns loading/disabled/error/retry presentation and explicitly retains current
  results on failure. Its current visible label is “More”; “Load more” above
  describes the behavior, not a claim about the existing string.

These are inspected repository owners, not a new verification of the deployed
build. Reuse appropriate web owners and carry their behavior into native clients
through agreed contracts; do not blindly copy chat-specific grouping, page sizes
or identity rules into financial records.

**Mock boundary:** the Home three-row preview and View all are demonstrated.
Accounts grouping and paginated activity/Search/Updates are approved interaction
direction, not implemented server pagination in the disposable sketch. Production
integration requires an assigned contract and verification; this lock assigns no
new backend work.

### Conversation activity and unread presentation

Conversation activity is a typed continuity signal, not a reason to reorder
Recents or infer state from message text. Each chat row shows at most one marker
using this locked precedence:

| Priority | Typed state | Left-lane presentation |
| ---: | --- | --- |
| 1 | `queued`, `running`, or `checking` | Calm working ring |
| 2 | `needs_attention` | Existing shared attention/failure treatment |
| 3 | `needs_input` | Static attention marker |
| 4 | `new_activity` | Muted teal dot |
| 5 | `manual_unread` | Muted teal dot |
| 6 | `none` | No marker |

- **Fixed row geometry**: The existing left `w-11` lane owns the marker. The
  right trailing slot owns the quick-jump keycap or ellipsis menu. A marker,
  keycap, hover state, or selection must never move the title, subtitle, or row
  height.
- **Selected rows preserve state**: The selected-row wash does not hide,
  replace, or recolor away the winning marker. Expanded Recents and Quick Peek
  use the same per-row presentation; the collapsed aggregate uses a ring when
  any loaded chat is working and otherwise a dot when any loaded chat is
  unread.
- **Typed accessible names**: Marker graphics are decorative. The row's
  accessible name appends exactly one phrase derived from typed state, with
  catalog-backed English and Latin American Spanish parity:

  | State | English (`en`) | Spanish (`es-419`) |
  | --- | --- | --- |
  | Running | Working | En curso |
  | Queued | Queued | En espera |
  | Checking | Checking status | Consultando el estado |
  | New activity | New activity | Actividad nueva |
  | Manual unread | Marked unread | Marcada como no leída |
  | Needs input | Needs your input | Necesita tu respuesta |
  | Needs attention | Needs attention | Necesita atención |

- **One Jump to latest control**: When the latest activity is visible, the
  control is hidden. Above the latest activity, one unchanged 44px target uses
  this state machine and always scrolls to the same latest-activity sentinel:

  | Current presentation | Inner treatment | Accessible label |
  | --- | --- | --- |
  | Idle/read | Down arrow | Jump to latest |
  | Queued/running/checking | Restrained three-dot wave | Jump to latest; Argus is working below |
  | New/manual unread | Down arrow plus teal marker | Jump to new activity |
  | Needs input | Down arrow plus attention marker | Jump to the latest question |
  | Needs attention | Down arrow plus shared failure treatment | Jump to the latest recovery |

- **Recents owner menu**: Keep one restrained ellipsis glyph inside a target
  that is at least 44px in both axes. On fine pointers it appears on row hover,
  trigger focus, or while open; on coarse pointers it remains visible without
  hover. Focus uses the standard visible ring. Escape closes the menu and
  returns focus to its trigger. Mark as read/unread remains the first item, and
  nested menu actions never activate the row.
- **Reduced motion**: Under `prefers-reduced-motion`, the working marker is a
  static open ring and the Jump control uses a static three-dot glyph. Remove
  rotation, wave, flashing, rapid pulsing, and repeated scale animation without
  removing the state label or immediate visual meaning.
- **Polite transitions**: Meaningful typed transitions may be announced once
  through one polite live region. Polling, token updates, and animated dots are
  never announced. All row, menu, Jump, toast, and announcement copy comes from
  the `en` and `es-419` catalogs.

## 15. Settings and Feedback UX

- **Core Settings**: Visible support for Language, Theme, Feedback, Account, Recently Deleted, and Archived Chats.
- **Feature Guarding**: Preserve existing hidden/flagged settings according to [current production availability](../../../docs/PRODUCT.md#current-production-availability-and-planned-changes). A planned experience does not enable its controls; change visibility only with its approved implementation and rollout.
- **Accessible Feedback**: Simple conversational or form-based entry accessible from the settings surface.

## 16. Language & Localization UX

- **Supported Languages**: English (`en`) and Spanish (`es-419`).
- **Standardized i18n**: All static UI strings must be translatable.
- **Language Selection**: Should feel premium and be accessible at signup and in settings.
- **Consistency**: The AI response language must always mirror the UI language preference.
- **Locale Logic**: Date, number, and currency formatting must adapt to the `locale` token.

## 17. Mobile & Web Behavior

- **Accidental Zoom Prevention**: All input fields (text, select, textarea) must use a **Minimum 16px Font Size** to prevent iOS auto-zoom.
- **Generous Tap Targets**: All interactive elements (buttons, chips, nav) must meet the **44px minimum** hit area.
- **Phone-first Layout**: Design for native iOS/Android and responsive web. Existing web/PWA details do not decide the native architecture. Avoid desktop-only dashboard patterns.

### Money entry in the ecosystem sketch

Approved interaction direction, September 27, 2026; not a claim that production
has this shared control yet. Preserve existing decimal keyboards, readable
currency markers, inline validation and editing continuity. Account balances,
asset estimates, credit limits, goals and entry corrections should derive their
input behavior from one money-entry owner per client and a common contract.

- Show the currency unambiguously; a bare `$` is insufficient context.
- Keep at least 16px input text, tabular figures, a decimal keyboard, and a
  visible example of separators and decimal precision. Currency determines
  fractional precision; UI locale determines separators.
- Preserve the user's text and caret during typing. Show a formatted readback;
  group and pad decimals on blur. Editing and pasting must not silently change
  the amount's meaning.
- Validate the complete input. Do not blindly remove commas, letters or currency
  labels; reject malformed grouping, mismatched currency, excess precision and
  exponent notation with an inline explanation. Do not guess an ambiguous
  decimal separator or silently round a pasted amount.
- Blank optional amounts mean unknown, independently of zero, except a new
  money account's starting balance, which the server records as 0.00. Required goals
  and positive-only amounts retain their own constraints. Allow negative bank
  balances where the account supports being overdrawn.
- A currency change revalidates the same amount; it does not perform FX
  conversion. Make that distinction visible when an amount is already entered.
- Save and redisplay the same accepted value, including cents. Native/web
  integrations still require the production money-arithmetic and API contracts;
  the disposable sketch's local numeric storage is not that contract.

## 18. Product Anti-Patterns

Argus is **NOT**:
- **Spreadsheet Software**: No dense data grids or cell-based parameter inputs.
- **Broker Terminal**: No aggressive red/green neon or complex multi-pane layouts.
- **Toy Trading Game**: No "gamified" badges or misleading profit claims.
- **Forced Setup**: Avoid long required wizards. Provide short manual forms and conversational entry as equally usable options; new onboarding policy remains open.

## 19. Accessibility Baseline

- **Visible Focus States**: `0 0 0 0.125rem` rings for all keyboard navigability.
- **Non-Color Meaning**: Positive/Negative metrics must be paired with labels, icons, or clear +/- text signs.
- **Accessible Labels**: All icon-only controls (e.g., Close X, Search) must have visible or ARIA labels.

## 20. Metrics Visual Language

- **Muted Tones**: Use the Semantic Muted Palette (`#5ba897`, `#d66d75`, etc.).
- **Educational Intent**: Metrics should feel like data to learn from, not an alarm to react to.
- **No Alarmist Motion**: Avoid flashing or rapid updates. Use calm shimmers for loading states.

## 21. Motion & Continuity

- **Motion Principle**: Argus motion should feel **calm, informative, and never frantic**.
- **Transitions**: Use simple fades and slide-ups for cards to maintain the "Flat" identity.
- **Premium Loading**: The "Simulation" state is a trust-building moment. Use the defined status language carefully.

---

## 22. Guest Entry and Rollback

- `/` presents the chat-first guest entry by default. The Guest server and
  presentation flags are emergency kill switches: explicit `false` restores
  the auth-first landing and stops new anonymous bootstrap.
- Preserve the current landing implementation and centered auth modal for
  configuration rollback and later conversion.
- Guest chrome reads the server-owned `public_account_access_enabled`
  permission and never a remembered flag value. When the server permits
  permanent accounts, guest chrome offers **Create account** alongside **Sign
  in**. When it does not, the conversion surface offers an access request
  instead, and no public **Create account** action appears. This design owns the
  rule, not the current value; for what the gate is set to today, read
  `docs/PRODUCT.md`.
- Temporary status, fixed expiry, allowance boundaries, feedback, and errors
  must remain calm, accessible, and localized in English and Spanish.
- The frontend flag selects presentation only; a server-denied guest session
  must stay on the entry surface with one honest retry and no fake local
  conversation.

## 23. Usage Allowance Meter

- Use the lowest normalized remaining capacity across the active hourly and
  daily allowance windows. The window closest to exhaustion governs the meter
  because it is the user's real near-term constraint.
- **Green / Muted Teal** (`--rui-color-teal`): at least 30% remains, including
  exactly 30% (at most 70% consumed).
- **Amber / Dusty Gold** (`--rui-color-warning`): more than 10% and less than
  30% remains (more than 70% and less than 90% consumed).
- **Red / Muted Rose** (`--rui-color-danger`): 10% or less remains, including
  exhaustion (at least 90% consumed).
- Color is supporting information only. Always retain the exact remaining
  count and truthful reset time, and use calm localized language with no pulse,
  flashing, or casino-terminal treatment.

## 24. Design Decision Filter

When designing any Argus surface, ask:

> *Does this help someone understand, maintain, or improve their financial picture with less effort?*

If not, it likely should wait.

### Financial context and planning refinement — September 28, 2026

Financial spaces use one quiet horizontal text row: selected dark semibold,
others muted, with an accessible 44px Add target. Do not apply the action-pill
style or the section underline to spaces. Plan sections retain their underline
below the space row. Currency belongs beside amounts, not in the space row. The `+` opens
Household, Business and Custom creation, with a quiet Manage spaces action.
Use the same private-space naming form from this menu and account-move review.
Space lifecycle meaning is owned by the MVEE's Managing private spaces section.
Archive is neutral and reversible; Delete empty space uses the existing rose
destructive confirmation. Recently deleted and Restore remain neutral. Preserve
space names and archived status in Search, and do not put lifecycle controls
beside every space tab.

Home places a restrained Coming up section between recorded position and the
account preview. Reuse Plan's forecast and show its date, currency and included
accounts; no promotional banner, duplicate chart or independent calculation.
List at most two upcoming items and link to Plan. Existing growing-list rules,
blur, typography, destructive confirmations and reduced-motion behavior apply.

Financial recovery identifies space and account before confirmation. Refunds,
balance adjustments and value changes use explicit labels; color alone never
carries their meaning. Optional financial notes share the 200-character limit.
These are disposable-template decisions, not claims of backend implementation.

### Transient confirmations and errors

Carry forward `web/components/chat/ChatToast.tsx` and `useChatToast.ts`:
neutral confirmations use the white, lightly bordered floating pill; errors use
its warm error text/border and warning icon, with the existing dark variants.
Undo uses teal. These toast error colors are distinct from the muted-rose
confirmation button used for destructive actions. Do not invent a green success
banner or insert status blocks that shift page content.

Use one presenter across surfaces, one toast at a time, above navigation and
clear of safe areas. Neutral feedback expires after three seconds. An action
such as Undo can last longer, with its timer paused while focused or hovered;
recovery remains available after it expires. Respect reduced motion and use
polite status announcements, assertive announcements for errors. Keep field
validation beside its field. The template uses a shared adapter, not independent
account/settings notification styling.


### Final mobile design lock — September 28, 2026

The founder locked the complete disposable mobile template and ecosystem reports.
The [lock handoff](../../../docs/reports/mobile-design-lock-2026-09-28.md)
identifies the immutable source/evidence archive and verification limits.
MVEE owns the accepted behavior; this lock does not change existing API/data
contracts or enable production features.

Chat header layout is fixed by state:

| State | Left | Right |
| --- | --- | --- |
| Empty regular | Recents | Temporary entry |
| Active regular | Recents, New chat | Share, More |
| Empty or active temporary | Recents, New regular chat | Temporary settings |

New stays left, with a reserved slot to prevent Recents shifting. The dashed
conversation glyph stays right; it never morphs into New. No redundant landing
pill. Header/landing fade is 150ms and reduced motion disables it. Composer
suggestions collapse at the same 200ms pace as the attachment tray expands;
keep the greeting mounted and make hidden suggestions inert.

Settings keeps the identity row followed by App, Account, Support. Use quiet
headings and group spacing, with separators only between related rows. Space
and Household management remain in the space controls, not duplicated here.
Recents, account activity and global Search retain the shared quiet search
language. Empty Chats and no matching results offer an explicit New chat action.
No additional visual exploration is required by this freeze; later changes
need an explicit request and a new dated checkpoint.

## Cuadrao native living guide

Native Cuadrao appearance and interaction decisions for the design-preview Home
path live in [`.agent/designs/cuadrao/DESIGN.md`](../cuadrao/DESIGN.md), including
the October 2, 2026 balance-change / visual-state polish from checkpoint
`8cf52a18acaad9d3805311f424e37d2e124af515` (after Home activity insights
`5ae634279e358a6bd130b12f59c6a067f77c2c25`). Connected Cuadrao continues to own
runtime financial truth; the living guide does not invent backend owners.
