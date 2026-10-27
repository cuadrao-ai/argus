# Cuadrao Business web app design

The founder locked the rules in this guide on October 18, 2026. They cover the
signed-in Business web app's core path: sign-in, Inicio, Bandeja, receipt detail,
month close and the 606/607 export. Other screens follow the same foundations
until they get their own sections. Read a rule as approved direction, not proof
that it is shipped.

The [website guide](../cuadrao-business/DESIGN.md) owns the landing pages. The
[native guide](../cuadrao/DESIGN.md) owns the locked colours and wins any
conflict with this guide. The edge-case rules below come from the
[Argus web guide](../argus/DESIGN.md). Product owns each screen's behavior rules
and adds them in the slot each screen section leaves for them.

## 1. Foundations

### Colour

Use the [locked colours](../cuadrao/DESIGN.md#locked-colours--october-18-2026)
and no others for these roles:

| Role | Value |
| --- | --- |
| Page background | `#F7F5EE` cream |
| Input border | `#7d8a84` |
| Aprobado | `#2f5a49` on `#e3ebe1` |
| Pendiente | `#735c14` on `#f2e8c9` |
| Necesita atención | `#9e2f39` on `#f6dfe0` |
| Destructive confirm button | `#9e2f39` with a white label |

Both appearances use the same hierarchy and semantic roles. Home inherits the
existing app dark canvas (`#141517`) and shared card surface (`#1f2225`). Embedded
setup uses that same card surface, white primary text, white at 70% for secondary
text and white at 12% for hairlines. Waiting uses `#f6e7c1`; attention uses
`#ec9aa0`. These inks always accompany a status label. Neutral surfaces stay
neutral; do not add green washes to instructions.

### Type

- Headings use Space Grotesk at weight 500, never bold. Body and controls use Inter.
- The app's scale is **16 body, 21 section title, 26 page title**. The
  golden-ratio display sizes (42 and 68) belong to the marketing site: in a
  dense money screen they push the numbers below the fold.
- Secondary text, status labels and the setup progress count use 14px. Do not
  shrink them at narrow widths. The progress ring remains 44px with tabular digits.
- The sidebar and Business menu share the same 40px neutral square business avatar
  with a 20px briefcase fallback. Keep the trigger and switching behavior unchanged.
- Business sidebar navigation and the current business name use Inter at 16px.
  The access label and count badges use 14px; the navigation rows remain 44px tall.
- Embedded setup and dossier previews inherit `--font-inter` and
  `--font-space-grotesk` from the app. Do not declare a font name that bypasses
  the loaded font tokens.
- Input text is at least 16px.
- Labels and headings wrap. They never truncate or clip.

### Numbers

The founder set these rules on October 20, 2026. Each rule has one owner in
the code, named after it, and every screen uses that owner.

- **Digits.** Every amount uses fixed-width (tabular) digits, so columns of
  amounts align. A column of amounts is right-aligned.
- **Exact.** Money is exact: integer minor units in the API, rendered without
  rounding or a float. Lists, rows and column totals always show the exact
  amount. Owner: `formatAmount` and `formatMoney` in `business-format.ts`.
- **Currency in the header.** A list of amounts in one currency names it once,
  in its header, on the total: "Por cobrar" over "RD$ 33,540.00". Its rows show
  the number only. A row in another currency shows its own symbol, such as "US$ 50.00".
  Totals in different currencies are never added together or converted: the
  header lists one total per currency, the header's currency first. Owner:
  `openItemsHeaderCurrency` in `business-month-close.ts`. A single amount with
  no header, such as a Bandeja row, keeps its symbol.
- **Short headline figures.** Only the big summary figures (Ingresos, Gastos,
  Resultado neto, ITBIS a pagar) shorten, and only from 10,000 up: "RD$ 58.4 mil",
  "RD$ 1.3 M". Spanish uses "mil" and "M", never "k". One decimal, rounded half
  up. The exact amount shows in a tooltip on hover and on keyboard focus, and
  is what a screen reader reads. The row shortens together: when its largest
  figure is 10,000 or more, every figure in it uses that unit ("RD$ 9.6 mil"
  beside "RD$ 58.4 mil"), and below that every figure is exact. Owner:
  `formatHeadlineMoney`.
- **Relative time when recent.** Under 7 days a time reads relative: "hace 15
  minutos", "ayer", "hace 3 días". From 7 days on it reads as a short date,
  "12 oct", with the year only when it is not this year: "24 dic 2025". Owner:
  `formatRelativeTime` for timestamps and `formatRelativeDay` for calendar days.
- **Unknown is "-".** An amount the system does not know shows a plain short
  dash ("-"), never the long one, never 0 or RD$0.00. A real zero shows as
  RD$0.00. A negative amount keeps its minus sign in front of the number, so a
  lone dash is never a sign. Owner: `UNKNOWN_VALUE` in `business-format.ts`.
- **Ocultar montos.** Every amount carries the `cuadrao-amount` class, so
  Ocultar montos hides it, headline figures included.

### Spacing, shape and depth

- Spacing follows the golden ratio from 8px: **8, 13, 21, 34, 55**. A gap
  inside a control is 8, between related items 13, between groups 21,
  between sections 34, around a page 55. Lucas set this on October 20, 2026;
  screens adopt it as each one is redesigned, not in one sweep.
- A split layout gives content about 62% and actions or details about 38%.
- Surfaces are flat. Separate them with colour contrast and hairlines, never
  decorative shadows.
- Corners come from one scale, Tailwind theme tokens in `web/app/globals.css`
  (Lucas, October 21, 2026). A guard test fails on any other corner in a
  Business file.

  | Token | Radius | For |
  | --- | --- | --- |
  | `rounded-mark` | 4px | chips (status, lateness, type), counts, key caps, skeleton lines, a focus outline on text |
  | `rounded-item` | 8px | inputs, menu items, rows, small tiles, blocks inside a surface |
  | `rounded-surface` | 16px | cards, sheets, popovers, menus, toasts |
  | `rounded-full` | pill | buttons, segmented controls, switches, the search field, avatars, dots, progress bars, the sheet handle |

- **Concentric.** An inner shape's radius is the outer radius minus the
  padding between them, rounded down to the scale. Below 4 it is 4 or square.
  When the padding is at least the outer radius, the curves do not meet and
  the inner shape keeps its own step. It is never rounder than its container.
  Controls stay pill wherever they sit.
- **Docked.** A sheet docked to the bottom of a phone rounds its top corners
  only. A full-height drawer touches the top, right and bottom edges, so it
  is square, with a hairline on its open side. A full page is square.
- **Focus.** The focus ring is an outline that follows the element's own
  radius, offset outward. Every focusable shape carries a radius, so no ring
  is square on a round control.

### Widths

Design and check each screen at the five widths of the Argus guide. Nothing
scrolls sideways at any width.

One fluid canvas holds every Business screen (Lucas, updated October 23, 2026).
It fills the available main area with 32px gutters from the tablet stop up.
When the sidebar collapses, the canvas's left edge follows it and the canvas
widens. Its right edge stays at the same gutter. The top bar spans the same
box, so search starts at the canvas's left edge and the actions end at its
right edge on every screen. There is no fixed maximum width on this outer
canvas. Inside it, Inicio and Transacciones fill the canvas, the Bandeja keeps
its 48rem list beside the record tray, and Negocio and other forms keep a
40rem column at its left. No screen moves the outer canvas. Owner:
`web/components/chat/workspace-canvas.ts`. Phones keep their 16px gutters.

| Name | Width |
| --- | --- |
| Mobile small | under 400px |
| Mobile | 400–720px |
| Tablet | 720–1024px |
| Desktop | 1024–1280px |
| Large | 1280px and up |

### Motion

Lucas set these on October 20, 2026:

1. **Fast.** Interface motion stays under 250ms. Only a sheet's drag release and
   the toast stack's spring run longer, because the hand or the stack drives them.
2. **Ease out.** Fast off the mark, gentle at the end. Never linear.
3. **No bounce on menus.** Overshoot reads as slow. Springs are for things the
   owner throws (a sheet, a toast).
4. **Grow from the source.** A menu or popover scales from the control that
   opened it (`transform-origin` on that edge).
5. **Reduced motion is a fade.** Never a flight. Loading placeholders stop.
6. **Composited only.** Animate `transform` and `opacity`. Never width, height,
   top or left on every frame.

## 2. Status

A record has one of three statuses: **Aprobado**, **Pendiente** or **Necesita
atención**. Show each as its word, its colour and a dot together, every time.
Colour alone never carries the status. A status that looks clickable has a 44px
target.

## 3. Components

### Setup guidance and permission explanations

The founder requested these clarifications during the workspace-guide review.
The preview demonstrates them; this section does not certify backend wiring.

- Neutral surfaces carry instructions, summaries and permission explanations.
  Do not use the approved/success green wash to make ordinary information stand
  out. Use heading size, spacing and a hairline for hierarchy. Green fills remain
  for primary actions and confirmed positive states. Amber means waiting; red
  means an error or attention is required. Always include a label, never color alone.
- Mark an optional task as Optional in its heading. A field can be required to
  perform that task without making the task compulsory. On a one-field invitation
  form, keep the email's required semantics and validate on submit; the task's
  Optional label and Skip for now action explain the choice without an asterisk.
- Skip for now preserves the draft and leaves the task unfinished. Show For later,
  never a completion check. Complete the collaborator-invitation step and advance
  the completion wheel once the invitation is confirmed created. Derive this from
  the existing pending or granted result, not a separate completion flag. Keep
  Pending acceptance visible while pending; the completed guide task does not
  imply acceptance, email delivery or granted access. Draft, sending and failed
  requests do not complete the step.
- Show the selected Business in 16px body type with a semibold name before the
  invitation fields. Use “Acceso” / “Access” consistently. Permission descriptions
  stay visible inside each access option, without a tooltip.
- The Business-menu invitation supports one or more people. Each row owns its
  email, access and send result. An owner can choose Owner, Admin, Editor or Viewer.
  A single existing Owner may invite another Owner; the invitation supplies that
  approval, and the recipient must still accept. Admins cannot grant Owner access.
  At least one active Owner must remain. These are intended product rules; the
  preview does not implement backend authorization or membership changes.
- Left-align the short-task dialog title and selected Business context. Use one
  editable recipient list with Email and Access column headings. A small Add action
  below the last recipient appends a blank row and moves focus to its email field.
  Align it to the email column’s right edge, above the footer divider.
  Start and reset with one blank row. Keep access descriptions in the role options.
  On phones, stack each email above its access selector and removal action.
- Keep title, business subtitle and fields close together. The subtitle explains
  collaboration in the selected Business; keep the business name at 16px semibold.
  Trash removes a recipient row; the top-right X closes the dialog.
- Validate nonempty emails on blur. A green outline/check means email format is
  valid and there is no known duplicate or pending-member conflict. Its accessible
  label says Email format valid; it never confirms an account, delivery or access.
  Empty untouched fields stay neutral. Editing a valid field removes its check
  until the next blur; after an error, validation updates while typing. Recompute
  all row feedback when an email changes or a row is removed, so duplicate feedback
  cannot stay stale. A failed send retains its error and has no green format check.
  This compact batch form keeps empty feedback collapsed; show errors beside their
  recipient and let the dialog or tray scroll. Do not reserve a blank error row for
  every person. This is the batch-form exception to the general Forms reserve rule.
- Every row owns its email and access; it can be edited or removed before sending.
  A single entered email sends directly. Ignore extra blank rows when nonempty rows
  exist; an entirely empty submission shows the required error on the first row.
  Invalid nonempty rows and case-insensitive duplicates block submission. Identify
  locally known pending invitations and members without inventing backend knowledge.
  Separate the footer with a subtle divider. Send and Retry fill its width, with
  green reserved for the primary action. The close X preserves the draft; omit
  a duplicate Cancel action. Keep Invite more and Done after full success.
- Configurar exposes the Acceso / Access tab at every width, retaining its existing
  route. The local development review shows collaborators first and pending invites
  separately. Use compact, unframed rows with a 32px avatar, readable email, a quiet
  borderless access trigger and neutral trash. The trigger reuses the invitation
  picker: descriptive floating options on desktop and a tray on phones, never a native
  select menu. Do not infer names from email addresses.
  Neutral row hover and focus replace per-row dividers; phones put controls below the
  identity, aligned right. Keep 44px action targets and explain protected controls
  through accessible help. Trash asks for confirmation. Pending invitations sit in a
  small, initially collapsed disclosure with their count and one top divider. Expanded
  rows retain access, pending acceptance, quiet Resend and cancel-invitation trash.
- The Access panel reuses the invitation modal and its business-scoped local history.
  Resend remains pending and never grants access. Cancellation/revocation replaces
  that person's local history with a tombstone, so stale guide snapshots cannot
  recreate access or block a later invitation. The earlier guide task stays complete.
  Self-removal/demotion and removing the last owner are blocked with an explanation.
  Only an owner may assign Owner. These preview controls do not enforce backend roles.
- Synthetic accepted-member fixtures are seeded once only for fixture-space. Other
  businesses receive no invented members. This panel is development-and-mock gated;
  the existing live access component and its API behavior remain unchanged.
- Keep membership and access lists under Configurar in Business settings. The
  invitation dialog contains only the people being invited and their send results;
  do not add current-member or pending-invitation history disclosures here.
- The preview uses its signed-in member and confirmed local invitation history
  only to reject self-invites, known members and pending duplicates. Missing identity
  stays unknown. Production requires authoritative membership and invitation facts
  for validation; the preview does not manufacture members or assign default access.
- Sending prevents duplicate submission and keeps the recipient list visible.
  Successful rows become read-only with their access and Pending acceptance label.
  Failure stays beside the affected row. Retry sends only unsent rows and preserves
  earlier successes. Full success offers Invite more and Done. Invite more clears
  the batch; Done closes it and opens a fresh batch next time. Both preserve the
  known invitation history and the guide's completed invitation step.
- A created invitation completes the guide task, not acceptance. Track invitations,
  resend/cancel and later access changes in Business settings, outside this short
  task. Do not trap the invitation form in an acceptance-pending screen.
- The local preview simulates sending and stores only browser-local drafts/results.
  It never sends email or grants access. Its design-review failure fixture is a URL
  parameter, not a customer-facing control. Production must render authoritative
  invitation and membership results from the backend before this UI is enabled.
- Apply the same hierarchy, labels and validation behavior in EN and ES. Check both
  themes and phone/tablet/desktop widths. Do not reduce type to fit more content.

### Guide readiness and progress

- After creation or joining, the header says the workspace is ready. Its supporting
  line states that the remaining actions are optional. Readiness never depends on
  finishing invoicing, uploading a document or inviting another person.
- A compact neutral progress ring shows `n / n` in its center. It counts confirmed
  guide outcomes, including workspace creation; it does not measure readiness.
  Keep it visible when collapsed. Give screen readers a translated description
  of completed guide actions. Do not add another progress bar or percentage.
- Each unfinished optional row retains its Optional label beside any current status.
  For later and awaiting review remain unfinished. Neither earns a completion check.
  An invitation that was created counts as complete even while acceptance is pending;
  the owner has finished the guide action.
- The completed creation row becomes Your workspace. It remains expandable for
  review and name correction. Its completion check remains visible while editing.
- Every row puts its chevron in the same trailing column. On narrow screens, status
  wraps below the title while the chevron stays at the far edge. Keep normal type.
- A ready workspace starts with the guide collapsed unless the person explicitly
  expanded it. Keep that choice through refresh. The phone's existing Add action
  stays above the optional guide. Guide state belongs to the selected Business;
  local preview state must never leak to another Business.
- Use the header to collapse or expand the guide. Remove the duplicate Done for now
  footer. Deferring a specific task still preserves its draft and optional status.

### Workspace forms and recovery

These decisions apply to every workspace-guide step and its Business dossier.
They extend Forms below, including email aliases, authorized senders and invoicing.

- Use the signup field pattern. Labels remain above populated inputs. Saved data
  stays editable in the same input. Remove introductions that only repeat labels.
  Keep one contextual group at a time. Do not split two related fields into a wizard.
- Inputs and primary form actions use 16px text. Labels use 15px and feedback uses
  14px. Input rows are at least 48px tall. Buttons, suggestions, radios and checkbox
  rows have targets at least 44px tall. Stack actions when their labels need room.
- Share the field, feedback and action styles across steps. Extra blank margins
  must not add a second error reserve. Reserve the tallest translated feedback
  message at the current width, including radio-group and availability errors.
- Check only the current step on Continue. An invalid submission keeps the step
  open, displays an inline repair message, and focuses the first invalid control.
  Do not disable Continue merely because a user has not yet filled the fields.
- Save drafts through Back, collapse, close and refresh. A draft is not a committed
  change. Save or Continue applies it. Cancel leaves the saved value unchanged.
- Completion does not lock editing. A completed workspace step opens its current
  name and country. Edit name changes the display name of the same workspace.
  Keep the completion count. Do not create another workspace or change its legal
  name, country, email alias, documents or access. Business settings owns this edit
  after the guide is dismissed. Use existing edit permissions when wired.
- Initial creation needs name and country only. Country has no silent default.
  Preserve an explicit saved choice. Treat it as declared operating country, not
  verified tax jurisdiction. Unresolved fiscal conflicts require review before
  invoicing activation, while basic use remains available. Backend enforcement,
  country-change permissions and audit rules belong to the integration checkpoint.
- Known invitations show the existing Business and granted access. Do not ask the
  invitee to recreate its details. Optional tasks can be deferred without a check.

### Help tooltips and disclosures

- A tooltip adds one short explanation. For a fixed permission summary, it states
  the limits. Keep the destination and permission being granted visible in the form.
- Use the shared Tooltip visual pattern with a neutral surface, fine border and
  readable text in both themes. An info icon has a 44px button target, an accessible
  name and an associated tooltip. It does not navigate or open a dossier.
- Show help on hover, keyboard focus or tap. Escape and outside interaction dismiss
  it without closing the parent form. Keep focus on the trigger after Escape.
  Users can move the pointer into the tooltip to read it. Keep it within the visible
  screen and out of document flow, so opening help does not move fields or actions.
- Use a disclosure for several sentences, technical dates or manual instructions.
  Disclosures may contain actions and fields. Tooltips contain no interactive
  controls and never hold required instructions, errors, consent or destructive
  consequences. Do not replace useful help with an unexplained icon.
- Do not use native title attributes for help copy. Keep iframe accessibility titles
  accurate. Production integration must reuse the shared Tooltip and FormField
  components; the local HTML preview demonstrates behavior only. Confirm touch
  activation and hover persistence before adopting the shared tooltip unchanged.
- Check every form in English and Spanish, both themes, and phone, tablet and
  desktop layouts. Long feedback must wrap without clipping or horizontal scrolling.
  Use normal text sizes and one page or sheet scroll area.

### Selection controls

- Dropdown pickers use the existing menu surface: 16px corners, a fine border,
  neutral light/dark surfaces and 44px rows. Use listbox/option semantics for
  selection, a visible selected check, keyboard navigation, Escape and outside
  dismissal. Match the action menu visually without treating values as actions.
- Checkboxes use rounded square corners, never sharp squares. The native input
  and its label form one clickable row at least 44px tall. Space toggles the
  focused checkbox; focus stays visible. Keep the input's checked semantics.
- A parent checkbox derives its checked, empty or mixed state from its children.
  Set the native `indeterminate` property and `aria-checked="mixed"` together.
  Clicking mixed selects all; clicking all clears. In searchable lists it applies
  to visible matches only and preserves hidden selections, explained beside the
  control. With no matches, disable the parent and leave it unchecked.
- A checkbox edits a draft. Save or Continue applies the choice. Keep draft
  recovery separate from a committed setting or confirmation. Immediate settings
  use a switch when that behavior is appropriate.
- Preview scenario controls belong outside customer forms, behind explicit
  preview controls. Fixtures remain identified as sample data. Do not expose
  backend state selectors as customer choices.

### One receiving address across Business surfaces

- The setup guide, Agregar menu, upload dossier and Business email settings use
  the same Business receiving-address source. Reuse BusinessEmailAddress and
  CopyButton rather than creating another address or availability model.
- If an address exists, show it and Copy. If none exists, use the existing
  Get a receiving address action and its loading/error states. Custom aliases and
  renaming are unresolved capabilities, not promised setup requirements.
- Automatic reading remains a separate Business setting across all intake channels.
  Opening Email must not create a separate consent step.
- A document task completes only after a received-document result. Opening upload,
  copying an address or linking a phone does not complete it. Review-only fixtures
  may demonstrate receipt completion; they must be isolated and labelled.
- Preview navigation belongs to its own tab and surface. Shared saved facts may
  update without replacing the open step; refresh restores that tab's navigation.

### Business context in setup

- The sidebar establishes the active Business. Do not repeat its name in routine
  setup steps, document method selection, email setup or the invoicing guide.
- Keep the destination visible when linking a WhatsApp sender or inviting someone.
  A separate Business dossier may identify the Business once in its header.

### Business profile

- Configurar uses Perfil / Profile as the visible first tab, keeping `tab=datos`.
  In the local design preview, the existing labelled form stays on the left and
  a restrained Completa tu perfil checklist sits on the right. Phones stack them.
  Only this preview tab uses the full canvas: a flexible main card and a 20rem
  checklist rail. The checklist has an inset neutral-gray basic section and a
  lighter Detalles adicionales section; both stack below the form on phones.
- Reuse the shared Business avatar, field validation and descriptive picker.
  Nombre del negocio is the workspace display name, not a separate legal name.
  Show the saved operating country when known. Do not invent registry fields,
  completion percentages, required checklist totals or an overall completed state.
  Filled green checks and struck labels mean saved facts only; incomplete facts
  use muted hollow circles. Name, valid identification, matching confirmed legal
  name, country and address form the basic section. Email, phone, website and
  description are additional details. Checklist actions focus their source field.
- Address, province, municipality, business email, phone or WhatsApp, website and
  short description are optional business-provided details, separate from registry
  identity. They persist as one object in the existing scoped guide. An address
  does not require province or municipality. Invalid email or website blocks save
  until fixed or cleared; a domain may normalize to HTTPS. Shared inline errors
  and a linked submit summary explain corrections. Failed local saves retain the
  draft; saving contacts does not reset an unsaved identity draft.
- Electronic invoicing lives in the main card, outside the checklist, as a
  separate optional capability. Configure, Continue
  setup and View setup derive from the existing business-scoped guide state.
  Its entry reuses the existing dossier; changing its path stays inside that
  dossier and Back preserves the current step. Home keeps its existing flow.
- A displayed legal name comes only from a confirmed registry match whose RNC
  still matches the current business tax identifier. A changed RNC clears the
  stale registry result and derived legal-name draft. An entered tax identifier
  alone is not verified, and saving profile details does not activate invoicing.
- This profile form uses a development-and-mock-only local source adapter and the
  existing guide store. It makes no fiscal-profile API calls. The backend registry
  verifier and legal-name autofill remain unwired. The live fiscal profile still
  exposes one name, tax identifier and edit permission; this design does not add
  a legal-name API contract or change backend access rules. Missing legal name
  stays Sin verificar; local confirmation timestamps are not registry sync dates.
- Registry economic activity, regime or category, tax office, issuer authorization,
  supporting documents, branches and currency remain future field/source decisions.
  They are not current autofill. Invoice setup status is not issuer authorization.
  Team management stays in Acceso; this pass adds no logo upload or team controls.

### Invoicing entry and saved setup

- Home offers path cards, not an activation switch. Existing issuer and getting
  started open distinct journeys in the Business dossier. Keep the main Home guide
  compact: current status and Continue setup after a path starts.
- Show one next action and one contextual step at a time. Reuse saved Business
  details in the standard labelled, prefilled inputs used by signup. Do not turn
  saved fields into separate edit disclosures.
  Back and closing preserve progress. Basic app use does not depend on completion.
- Keep registry match, user confirmation, authority to act and invoicing activation
  separate. Saving details never claims activation. Legal name does not overwrite
  the workspace display name. Source dates belong in a details disclosure.
- Awaiting review and active each show their status and saved details in one
  dossier view. Do not make View summary and Back cycle between two read-only
  screens. Home uses View setup for these states, not Continue setup. A primary
  action is present only when there is a next task to perform.
- Render service-owned activation states. Instructions use neutral surfaces;
  waiting uses an explicit amber status, and active requires a confirmed result.
  Preview fixtures are identified and their controls stay outside customer forms.

### Seven states

Every component defines seven states: default, hover, focus, pressed, disabled,
loading and error. A disabled control shows why it is disabled next to it.

### Forms

One owner builds every field: `web/components/ui/FormField.tsx` (field styles in
`web/components/ui/form-field.ts`, password rules in `web/lib/password-strength.ts`).
Use it; never restyle a field by hand (Lucas, October 21, 2026).

- Every field has an associated, visible label above it. The label stays when
  the field is focused, filled or autofilled. Placeholders are examples only.
  Floating labels are not the Business default. Make required fields clear.
- A field stays quiet while the owner first types. Check a nonempty value on blur.
  An empty field stays quiet until submit. Once a field has an error, recheck it
  while typing and clear the error as soon as it is fixed. Editing another field
  does not clear it. Submit checks every required field.
- An error has a colour, an icon and a short repair message. Associate the message
  with the input and set `aria-invalid`. The focus ring remains visible over an
  error state. It has at least 3:1 contrast against its adjacent surface.
- Reserve space for feedback at the current width and language. One line is only
  enough when every possible message fits. `reserveMessages` measures the wrapped
  messages without exposing hidden copies to screen readers. Never clip an error.
- Long forms use a summary after a failed submit, with links to broken fields.
  Short signup and sign-in forms use inline feedback and focus the first invalid
  input after its message renders. Do not repeat these errors in a top banner.
  Keep a form-level alert for request failures that no field alone can explain.
  Never use browser validation pop-ups. Do not focus an input on page load and
  open the mobile keyboard before the owner chooses a field.
- Show success only when a useful check has completed. A valid email format may
  get a small check inside the field and a message stating what was checked.
  It does not mean the address exists, belongs to the owner or is verified.
  An edit revokes the check until validation runs again. Do not mark optional
  names or a sign-in password as verified.
- Autofill matches the field surface in both themes and keeps text readable.
  Preserve autocomplete purposes and password-manager support. Codes such as an
  RNC are text with `inputMode="numeric"`, never `type="number"`.
- New passwords show a live checklist and a strength estimate with a word, such
  as Débil, Casi lista or Fuerte. Separate the required minimum from advice about
  predictable words and patterns. The estimate is coaching, never a guarantee
  about entropy or cracking time. Existing sign-in passwords have no meter or
  new-password minimum. The server remains the authority on acceptance.
- Keep paste enabled, use the shared visibility control, set `passwordrules`
  for new passwords and do not add a confirmation field. Auth entry retains
  the eye and eyelash icons chosen by Lucas. Only activating that control changes
  visibility. Eye activation focuses the password input, then changes its type.
  Focusing or typing in the field never changes visibility. Verify the rendered
  masking in the target browser, not only the input type and icon state.
- While submitting, preserve values and show one spinner in the submit button.
  Mark the form busy and make its inputs read-only with readable text. Disable
  competing actions with a visible explanation from the loading button. Guard
  repeat click and Enter events synchronously. A late result must not replace a
  different auth mode. Show an input spinner only for a real check of that input.
- Disabled fields use a muted surface and readable text, not reduced opacity
  alone. Read-only and disabled are different states. A read-only field remains
  focusable; a disabled action cannot run.
- Keep server error codes in state and translate their messages when rendering.
  Language changes update visible feedback. Clear obsolete request errors on
  credential edits or a mode change, preserve entered values after failure, and
  offer the next useful action. Never reveal account existence unless the
  existing authentication contract explicitly permits that response.
- Buttons state the next action without unsupported promises. Auth sign-in uses
  Continuar / Continue. Signup keeps its approved action copy. No claim that an
  account is free is added by the form.

### Auth entry

These decisions cover the initial signup and sign-in screens. Confirmation,
recovery and later onboarding keep their own contracts.

- Desktop uses a 50/50 split from 1280px. The logo is centred on the left and the
  form is on the right. Both auth modes use the same layout. First and last name
  share a row from 768px and stack on small screens; both remain optional.
  Keep their labels clean, above the inputs. Identify the optional name row once
  with a quiet note associated with that group. Remove required-field legends
  and visual asterisks; email and password retain native `required` semantics
  (Lucas, October 22, 2026). Signup can be taller than sign-in. Keep the same
  width, padding and visual treatment without adding filler to equalize heights.
  Anchor the desktop hero and card to a common starting position so interaction
  does not recenter the whole column. On tall desktop viewports, lower this
  starting position with the viewport height instead of capping it near the top.
  From 768px through 1279px, use one centred column with a 576px form cap and
  a smaller logo. Below 768px, preserve the existing mobile layout. In desktop
  windows up to 800px tall, reduce the top space and hero size while preserving
  input sizes, readable text and natural vertical scrolling. Keep the hero's
  reserved height stable across auth modes within each layout.
- Auth inputs use the card surface in both themes. The shared field surface token
  keeps other screens unchanged; white is not an accessibility requirement.
- Signup reveals the minimum and advice when the password receives focus. The
  meter starts reporting strength as text is entered. Keep coaching open after
  engagement so it does not repeatedly expand and collapse during edits. A
  filled or invalid password also reveals help. This is an intentional expansion
  on interaction, not space reserved on arrival. Other shared-field consumers
  retain their existing coaching behavior.
- The compact system, light and dark controls stay at the top-right. Language
  stays below the card. The mobile layout remains stacked without the split
  background. Field accessibility and feedback rules apply at every width.
- The background uses the approved cream and pine tokens. The desktop gradient
  fades from left to right into the solid form side, with separate light and
  dark strengths. Approved strengths are 12% for light and 10% for dark; these are design choices,
  not separate palette colours.
- Hero copy responds to language and auth mode. Form titles remain clear and
  separate. Locale files own the words. Only the hero uses the shared typewriter,
  once on display or an intentional language or mode change. Typing in a field
  does not restart it. Reduced motion shows the whole phrase immediately.
- Reserve the hero's final size and expose the complete phrase to screen readers
  without announcing each character. The animation never delays the form.
- Verify both languages, themes and auth modes at desktop and mobile widths.
  Include keyboard focus, wrapped errors, zoom, autofill, retries, duplicate
  submits and delayed responses. Shared field changes also check signed-in
  consumers. Local design acceptance does not authorize integration.

### Delete confirmations

- Ask a specific question that names the record.
- Say what actually happens. Promise only the recovery that exists.
- Cancel is an outlined button. The confirm button uses `#9e2f39`.
- The confirm button works once. While the delete runs, a second press does nothing.
- Trap focus in the dialog. Escape and the backdrop cancel. When the dialog
  closes, focus returns to the control that opened it.

### Sheets and alerts

Lucas set these rules on October 20, 2026. Every overlay is one of two
containers, chosen by what the owner is doing:

- **Sheet** for work done while the page stays in view: a form, a picker, a
  list, a record's details. `AdaptivePanel` owns it.
- **Alert** for a full stop: deleting, closing a month, anything that cannot be
  undone. `ConfirmDialog` owns it. It is centred with a scrim at every width.
  A delete confirms in `#9e2f39`; a full stop that removes nothing confirms in
  the brand green.

Sheet rules:

1. **Snap points.** Below 1024px a sheet is a bottom sheet that rests at peek
   (a summary), half (a form) or full (long content), never in between. Each
   sheet names the snaps it allows. Let go between two and it springs to the
   nearest. Menus and pickers are the only sheets that hug their content.
2. **Speed before distance.** A quick downward flick closes a sheet from any
   height; a quick upward flick lifts it one snap. A slow drag closes it only
   below half of its lowest snap.
3. **Side drawer on desktop.** From 1024px a sheet is a drawer on the right,
   at least 320px and at most 40% of the screen wide. No blur and no dimming:
   the page stays readable beside it, and a click beside it closes it.
4. **One sheet at a time.** Opening something from inside a sheet replaces it
   and shows a back arrow that returns to it. One sheet, one swipe to leave.
5. **Flat.** No blur, no shadow. Edges are hairlines and corners are
   `rounded-surface`, flat on the docked side.

Which container, screen by screen (Lucas, October 20, 2026):

- **Pages:** Inicio, Bandeja, Transacciones, Novedades, Acceso.
- **Record tray:** a receipt, draft, email or expense opens beside its list on
  desktop, without a scrim, so another row can be opened straight away. On a
  phone it is a full page with a way back, except a Registros record glance:
  that opens in the shared modal bottom sheet and returns to the same list
  position when closed (October 25, 2026). The desktop record tray remains
  non-modal.
- **Sheets:** Agregar, Exportar registros, settings, forms and lists.
- **Popovers:** pickers (a date, a month, a menu, the period's Personalizado
  range, which opens under its segment and in a sheet on a phone).
- **Alerts:** closing a month, deleting, removing someone's access.

### Dossier gradient, approved October 24, 2026

All web desktop dossiers use the same static pine gradient, including profile
forms and record trays. The shared `AdaptivePanel` desktop drawer owns it through
[`adaptive-panel.module.css`](../../../web/components/ui/adaptive-panel.module.css).
Individual dossiers do not define their own gradient.

- The gradient uses `--cuadrao-green`, which supplies the correct green for each
  theme. Its strength is 8% in light mode and 6% in dark mode.
- The color starts at the bottom edge and fades to transparent 25% of the way
  up the panel. The existing panel background remains underneath.
- The gradient stays anchored to the panel while its content scrolls. It has no
  animation and does not indicate loading, recording, success, or progress.
- Fields, validation, buttons, spacing, and scrolling keep their existing rules.
  The gradient does not move actions or add empty space below a form.
- Phone sheets and narrow-screen record pages remain plain. Centered dialogs
  and popovers do not inherit this treatment.
- Sign-in and signup keep their separate horizontal gradient and approved
  12% light and 10% dark strengths. Dossiers use the softer values above.

Visual checks cover light and dark desktop dossiers, a long scrolling record,
and a narrow phone layout. The gradient must not reduce text or control clarity.

### Shell baseline, approved October 23, 2026

This is the expected Business shell behavior for all current and future screens.
The rules in [Widths](#widths) and [Sidebar and account](#sidebar-and-account)
are one contract, including when a record tray is open.

- Collapsing the left rail moves the canvas's left edge and gives the canvas
  more width. Its right edge stays anchored to the same gutter. Expanding the
  rail reverses this without sliding the whole surface sideways.
- An open desktop record tray stays attached to the browser's right edge.
  Changing the left rail does not move or resize that tray. The canvas keeps
  its gutter beside the tray and adapts in the remaining space.
- On narrow screens, record details use the existing full-page layout with
  Back. Navigation stays usable and content scrolls vertically without
  sideways overflow.
- Light and dark themes use the same geometry and interactions. Hover labels
  do not expand the rail. Settings and the toggle share one saved desktop mode.

Future Home, onboarding and record work must preserve this baseline. A change
requires Lucas's explicit design approval; integration must not silently
replace it. This design approval does not authorize release or handoff.

Regression coverage lives in `business-canvas.dom.test.tsx`,
`business-sidebar-rail.dom.test.tsx`, `business-sidebar-shell.dom.test.tsx`,
`mobile-shell-layout.test.tsx` and `sidebar-mode-state.test.ts` under
`web/__tests__/`. Browser checks must also cover the open tray, both rail modes,
both themes and narrow viewports; DOM tests alone do not prove pixel geometry.

### Sidebar and account

Lucas set this on October 20, 2026. The left sidebar is where you work; the
top right is who you are.

- **Top left:** a neutral briefcase icon and the selected business display name
  entered during setup. Do not show an initial badge or a role subtitle. Use the
  same business name in the menu header; it is separate from the legal name.
  Its menu switches business and opens **Configurar negocio**. The open and close
  toggle sits beside it. The collapsed rail keeps the same briefcase icon.
- The Business menu starts with a briefcase avatar placeholder and the saved
  business name. The signed-in member email and “Your access” role form an identity
  block directly underneath. A divider separates identity from the Invite
  collaborator and Configure menu rows. A second divider separates Add business
  and Switch business. Use the same plain row pattern for all actions. The email
  is account identity, never the receiving address. Add business stays disabled
  until its supported action is connected.
- Invite opens a centered short-task dialog on desktop and the existing full tray
  below the desktop breakpoint. Home keeps its position and width behind it.
  The access picker floats beyond the dialog on desktop; on small viewports it
  uses a nested fit tray and returns focus to the selector. Recipient rows wrap
  access beneath email on narrow screens. Keep body type at 16px and helpers at
  14px; scroll a long batch within the dialog or tray instead of shrinking text.
- Choose the container by purpose:

  | Container | Purpose |
  | --- | --- |
  | Business menu or submenu | Quick choices near the trigger, such as switching business or choosing an action. |
  | Centered dialog, tray on small screens | One short task, such as preparing and sending invitations. |
  | Right dossier | Inspect or edit an item while keeping its source visible, such as a receipt beside its list. |
  | Business settings | Ongoing management of collaborators, access and invoicing configuration. |

- **Then:** the screens: Inicio, Bandeja, Transacciones. Negocio is reached from the
  business menu (Configurar negocio), the one door.
- **Foot of the rail:** the Cuadrao mark, small and quiet.
- **Docked sidebar, locked October 23, 2026:** Business desktop has two modes,
  Expanded at 240px and Icons only at 64px. The sidebar sits beside the shared
  canvas and never covers its content. Only an explicit toggle, keyboard
  shortcut or preference selection changes its width. The canvas resizes with
  it during the existing 200ms transition. Hover, focus, Escape and a click in
  the page do not change the mode.
- **Saved mode:** a new Business workspace starts Expanded. The saved Business
  choice wins after that. The toggle and preferences update the same choice.
  An old Business On hover preference becomes Icons only. Personal preferences
  remain separate. At tablet widths the rail stays Icons only; phones keep the
  existing navigation. These responsive changes do not overwrite the saved
  desktop choice.
- **Collapsed labels:** hovering or keyboard focus shows the existing simple
  tooltip after 300ms. It names the destination and its shortcut when present.
  It never opens a flyout or expands the rail. Clicking an icon navigates
  directly. The active destination stays highlighted and each icon keeps an
  accessible name. Escape dismisses the tooltip. Reduced motion removes the
  width animation; the choice and navigation remain available.
- **Opening and closing the rail** takes 200ms, ease out. Nothing inside
  changes shape: icons keep one position, labels fade, the business mark
  stays where it is, and the open header stays until the rail has closed.
- **Screen icons** are Phosphor: outline when idle, filled on the screen you
  are on. Becoming the current screen crossfades the two weights in 120ms (the
  outline leaves 60ms later, so the icon never dims) and settles the icon from
  92% to full size in 180ms, ease out, no overshoot; a press shrinks it to 92%.
  Each icon also acts out its screen in one short move: Inicio's four cards
  shrink and settle back corner to corner (360ms, 50ms apart); a receipt drops
  into the Bandeja, bounces once as the tray dips 1px, then slides in behind
  the lip (560ms); Transacciones' arrows slide past each other and settle
  (500ms, the second 60ms later). The move plays on pointer hover over the
  row's soft fill (Inicio and Transacciones again on leave), on keyboard
  focus, and when the icon becomes the current screen, which is the only
  trigger on phones. A move under way finishes rather than restarting, and
  every move ends at rest. At rest the icons are Phosphor's, pixel for pixel.
  Nothing plays on first paint or while the rail opens or closes. Reduced
  motion swaps the weight at once and moves nothing. The rail and the phone tabs share one owner:
  `components/business-app/nav-glyphs.tsx` and its stylesheet.
- **Top bar:** spans the one canvas. From the tablet stop up, Inicio shows the
  current localized date in small muted uppercase above the welcome greeting on
  the left, using the existing display font. Its search field sits near the right,
  followed by the invitation hand-heart, **Ocultar montos**, notifications and the account. Other desktop
  screens omit the greeting and search field; Cmd K still opens search. Business
  search opens below the field with aligned right edges, and expands left from
  that fixed edge within the viewport. Without the field, it uses the same header
  region as its anchor. Personal search and phone search keep their own layouts.
  **Agregar ▾**, with Exportar registros and Copiar dirección de reenvío, belongs
  beside each content heading on desktop. On Inicio it sits beside Pendiente hoy;
  in Transacciones it keeps Igualar sugerencias beside it. Phones keep Agregar ▾
  at the top of each screen instead.
  Home greets by the viewer's local time on desktop and phone: 05:00–11:59
  Buenos días / Good morning; 12:00–17:59 Buenas tardes / Good afternoon;
  18:00–22:59 Buenas noches / Good evening; 23:00–04:59 Noche de enfoque /
  Late-night session. Add a comma and the saved preferred name only when present.
  Reuse the sign-in typewriter on the first visible Home appearance in a browser
  tab's session. Reserve the whole phrase's layout and expose it once to assistive
  technology. Reduced motion is static. Navigation, reload, viewport, language,
  name and time-period changes do not replay it. Store only a session sentinel,
  never the greeting or name. Local date and period refresh at boundaries and
  when the page resumes; server rendering does not guess the viewer's clock.
  Content scrolls under the bar through a soft fade in the surface's own
  color, on every screen the bar is on. A screen starts 32px below the bar
  (16px on a phone), and Inicio's cards sit 24px apart from the tablet up.
- **Top right of the canvas:** the person's account (Perfil, Preferencias,
  Datos y privacidad, Ayuda, Comentarios, Cerrar sesión). Its sheets open on
  the same side, so the eye does not cross the screen. Phones already put it
  there.
- **Negocio** is a page, not a sheet: Datos (name and RNC), Equipo y accesos,
  Correo de recibos. Nothing about the business lives in the account menu.

### Buttons

Four levels, never a fifth (Lucas, October 21, 2026). All are fully round with
a 44px target.

| Level | Look | Use |
| --- | --- | --- |
| **Primary** | Cuadrao green fill | The screen's one main action: Agregar, Aprobar, Descargar. One per screen or sheet. |
| **Secondary** | Outlined | An alternative next to the primary: Volver, Revisar después, No es este. |
| **Quiet** | Green text, no fill | An action inside content: Reintentar, Ver correo, Mostrar más. |
| **Danger** | `#9e2f39` | Only the confirm of a delete, inside its alert. The outlined form opens that alert. |

- Black fills, ad-hoc green pills and one-off outlines are not a level. Pick
  the nearest of the four.
- A sheet's X is its only way to leave. Do not add Listo or Hecho to a sheet
  just to close it. A footer button names the next step (Guardar, Aprobar).
- Agregar stays green beside the content heading on desktop (Lucas, October 25,
  2026). Transacciones also keeps its existing Igualar sugerencias action beside
  it. This placement replaces the earlier global top-bar action rule.
- `components/business-app/business-ui.tsx` owns the classes
  (`primaryButtonClass`, `secondaryButtonClass`, `quietButtonClass`,
  `dangerButtonClass`, `dangerConfirmButtonClass`). Compose a width or a margin
  onto one; never copy its colours.
- Setup previews inherit these exports and the app stylesheet. Do not maintain a
  second button palette in the sketch. Cancel, Skip for now and Save and close
  use Secondary when paired with the primary form action. Change path beside
  Continue setup is also a Secondary alternative, not a green Quiet action.
- Copy controls use `foundation/CopyButton.tsx`. Copy the raw value; keep the label
  stable while the icon becomes a check for two seconds. Announce success to screen
  readers. Do not add a persistent Copied sentence or a second success notification.
  A failed copy leaves the value selectable and shows a short inline repair message.
- Tabs, the segmented control, icon-only round buttons, rows and menu items are
  their own components, not button levels.

### Segmented control

One control picks one of a few periods or views. A tinted track holds the
segments; the chosen one is white. It is a radio group: arrow keys move the
choice. Keep it to four short words or fewer. A rare choice (any other dates)
is a link under the control, not another segment.

Its thumb moves on springs, not a fade or a jump:

- The edge that leads the move is quick; the trailing edge follows on a softer
  spring. The thumb stretches by changing its width, never by scaling, so its
  round ends keep their shape. It lands with a small bounce.
- Pressing a segment reaches the thumb about 14px toward it. Releasing
  commits the move. Sliding off with the button down springs it back.
- With reduced motion on, the thumb moves straight to its place.

### Notifications

Severity picks the surface, never habit (Lucas, October 20, 2026). The same
news at four volumes:

| Surface | When | How it leaves |
| --- | --- | --- |
| **Toast** | Confirmations only: something the owner just did finished, such as a save, a copy or a download. Never an error. | On its own after 4 seconds; 8 with **Deshacer**, which every destructive action offers. |
| **Banner** | A condition of the whole app: the service is degraded, access changed, offline. | Docked at the top of the app, never inserted mid-page. Stays until the owner closes it or the condition ends. |
| **Alert** | A choice that must come before anything else: delete, close a month, remove access. | Only by choosing. Never two at once. |
| **Badge** | Something waiting quietly: receipts to review, new since the last visit. | When it is cleared. |

One toast at a time (Lucas, October 21, 2026): the newest replaces the one on
screen, Deshacer included, because stacked undos act on work the owner has
moved past. Marks in a row share one toast ("3 facturas cobradas") with one
Deshacer for all of them. An alert never stacks.

### Business notification list, local design preview

The bell opens a compact, flat 400px popover with a 16px radius and a hairline
border on desktop. Width and height stay inside the viewport; only the list
scrolls. Phones use the shared bottom sheet. The header uses a quiet double-check
control to mark all read, with a full accessible label, and a close control.

Rows show a small unread dot, a bold unread title, a muted timestamp, and quiet
action and dismiss controls with 44px targets. Product updates have a subtle
neutral tint. All/Unread is a compact inline menu with arrow-key navigation;
Escape closes that menu first and returns focus to its trigger. Dismissing a row
returns focus to the filter. The list never repeats task or inbox counts.

This local design uses three sample notices only in development with mock auth
and the preview prop. Read and dismiss state belongs to the selected Business
and lasts only while this shell is mounted. Direct and nonmock use is empty.

Notification empty states share a static 88px bell illustration in the auth
envelope's rounded forest-green, cream, sage, and lime style. Use transparent
artwork with a subtle theme-aware backdrop. Keep the panel title left-aligned
and center the illustration, 16px state heading, and 14px explanatory copy.
No notifications hides the filter and mark-all control and has no CTA. Nothing
unread keeps the filter and offers a quiet View all action that restores the read
list. These states derive from the available notice lists. Loading and failures
must remain distinct when the backend is connected. Final dismissal moves focus
to the empty heading; View all returns focus to the filter. Phones keep the shared
content-sized bottom sheet.

### Personal invitation to Cuadrao, local design preview

The account menu opens Invitar a Cuadrao with a hand-heart icon. This invitation
introduces someone to Cuadrao for their own business and grants no Business access.
Desktop also shows the same hand-heart before the privacy eye, with a 44px target
and shared tooltip. Both entry points open the same dialog and invitation history.
Closing returns focus to the opener. Phones retain only the account-menu entry.
Rewards remain outside this checkpoint.

Use a centered, flat desktop dialog and the shared phone sheet. Center the
hand-heart, title, and short explanation. Link and Copy share a row; email and
Send share the next row. Stack these controls on phones. Reuse FormField validation,
44px actions, CopyButton feedback, theme colors, and close/focus behavior.

A quiet divider introduces sent and joined counts. Invitation history opens
inside the same surface with Back, keeping the email draft. Show newest invitations
first with email, date, and quiet status. Copying a link does not raise sent counts.

The current implementation requires Business development mode with mock auth.
It uses a reserved example-domain link and in-memory simulated sends. Counts derive
from those local rows; joined remains zero. Closing and reopening preserves rows
while ProfileMenu remains mounted. Reloading or remounting clears them. Real delivery,
recipient acceptance, durable history, and pilot admission remain backend work.

### Toasts and saves

- One toast at a time, from one presenter, clear of the page's controls.
- A plain confirmation lasts 4 seconds. A toast with Undo lasts longer and its
  timer pauses on hover and focus.
- Never insert a banner mid-page that shifts the content. Field errors stay beside their field.
- A failed save never shows as success. Keep the owner's input and offer one
  honest retry.
- A failed collection or payment mark restores the item and keeps its error
  beside that row inside Por cobrar or Por pagar. A failed Undo whose row is
  absent stays inside the same card. Neither shifts the card headers.
- Retry keeps the restored row and error visible, disables duplicate attempts,
  and shows saving progress. Clear only that item's error after its save
  succeeds. A different item's save never clears it. Keep the error announcement
  separate from the changing retry control so progress does not repeat it.
- Announce confirmations politely. An inline error is `role="alert"`. The
  toast type has no error or warning kind, so the compiler refuses one.

### Errors

Type the error first; each type has its own surface (Lucas, October 20, 2026):

| Type | Example | Surface |
| --- | --- | --- |
| Validation | A typo in an RNC | Inline under the field, after the owner leaves it and live from then on. The action stays pressable and a failed press lists each broken field (see Forms). |
| Network | The connection dropped | The banner docked at the top ("Estás sin conexión. Lo que hagas ahora no se guarda hasta que vuelva."). It moves the bar and the page down, never covers them, and leaves when the connection is back. |
| Server | The save failed on our side | Inline where the work is, with Reintentar and the reference code. A failed confirm says so inside its alert, whose button tries again. Never a toast. |
| Refused | The server said this Business or this part of it is not available: 404 `business_unavailable`, 503 `email_capture_unavailable` | Inline where the work is, with no Reintentar, since asking again gets the same answer, and "Si crees que es un error, escríbenos a hola@cuadrao.ai." Never blames the connection. Only these status and code pairs (owner `refusedForGood` in `failure-screen.ts`); any other 503, `business_bank_unavailable` included, keeps Reintentar. |
| Permission | Access was removed | A full-page notice with the way back. It is the only error that replaces the page. |

- When the surface that failed has closed, send the owner to where the work
  lives. A copy of the forwarding address that fails from the Agregar menu or
  from search opens Negocio, Correo de recibos, where the address shows with
  its own copy button.
- Every error has a way out: Reintentar, Actualizar or "Escríbenos a
  hola@cuadrao.ai". A dead end is never shipped.
- Never "Ocurrió un error". Say what broke and what happens next.
- A modal is the last resort, for a choice the owner must make before anything else.

### Success

1. **Say what happened, with the specifics.** "Gasto de RD$3,450.00 en
   Ferretería La Esquina aprobado", not "Listo".
2. **Offer the next action.** Approving offers the next receipt. Exporting
   names the file. A check mark with no button is a dead end.
3. **Dismissal follows stakes.** A saved setting gets a toast. A closed month
   gets a summary that stays, with what to file next.
4. **Leave one open loop.** Closing a month points to the 606 and 607; an
   invite points to its status.
5. **Celebration scales with rarity.** Only the first closed month gets a
   moment. Every other save is quiet.

### Avatars

`Avatar` owns every picture of a person.

- The person's photo when there is one; else two initials (first and last
  word, or the first two letters of one word, or the name before an email's
  @); else a person icon.
- The tint comes from the name, so a person keeps one color everywhere. Every
  tint keeps its initials at 4.5:1.
- Sizes are 24, 32 and 40. People are round; the business is a square mark.
- A pending invite draws a dashed ring instead of a fill.
- A group overlaps up to three and counts the rest as "+N".

### Toggles

`Switch` owns every on/off control.

- The rail is twice the knob's diameter plus its padding, so the knob travels
  one diameter. The rail's corner is the knob's radius plus the padding, so
  the curves stay concentric.
- A press widens the knob toward where it is going; the release carries it
  there on the same springs as the segmented thumb.
- One flip changes four things together in 250ms, ease out: rail colour, knob
  position, knob shadow and the label.
- Space toggles it, focus shows the ring, and `role="switch"` with
  `aria-checked` announces the new state.
- Optimistic: it flips first, shows a spinner in the knob while the server
  answers, and rolls back if the server says no, saying so beside the switch
  with Reintentar. Never a toast.

### Empty, zero and loading

These three states look different:

- **Empty:** nothing is recorded yet. Show what is missing and one action to add it.
- **Zero:** the records are complete and the real total is RD$0.00.
- **Loading:** a request is running. Show loading only while something is truly
  pending, never on a settled empty state.

A month with no receipts is not a closed month at RD$0.00. Unknown is never shown as zero.

### Entry into Home

Keep the sign-in button busy while checking credentials. During Business startup,
use one Cuadrao loader across session, directory, consent and profile checks.
Show it only after 300ms of continuous pending work. A faster entry goes straight
to Home. Keep the same loader mounted between checks; do not insert a full-page
skeleton or restart the bar. Never delay ready content to finish an animation.

The loader uses the destination canvas in each theme. Its bar is indeterminate
unless progress is measured. Reduced motion shows a static indicator. Announce
loading once per episode with a polite status; do not move or trap keyboard focus.
Consent prompts and actionable errors replace loading as soon as they are known.
Once Home can render its structure, any remaining data placeholders stay inside
their final positions. Unknown values remain distinct from zero.

### Growing lists

Rules for any list that grows past one screen, Bandeja first:

- **Ver más** and **Ver menos** show and hide rows already loaded.
- **Cargar más** fetches the next batch. These two are different actions; never
  swap their labels.
- If a fetch fails, rows already shown stay, the scroll position stays, and a
  **Reintentar** button appears.
- Row height stays stable as rows load. Focus stays where it was.
- Hide the control when there are no more rows.

### Dense tables

Lucas set these on October 21, 2026, for working surfaces such as
Transacciones. They win over the 16px body and the golden spacing inside the
table only.

- Text sits left, numbers right, in tabular figures. Nothing is centred.
- No stripes. One hairline between rows. Hover lights the row's surface in
  80ms; every transition stays under 150ms, with no bounce.
- The header pins on vertical scroll. The first column pins on horizontal
  scroll, and a column that is the point of the screen may pin right.
- An empty cell is "-" when missing (read as "sin dato", or as what it means,
  such as "Sin recibo" in Comprobante), a real 0.00 only when zero is known,
  and a skeleton only while loading. A blank cell is a question, so no cell is
  left empty.
- Long text truncates to one line with a tooltip. Numbers never truncate.
- Row actions appear on hover and on keyboard focus, each with its key, over
  text columns and never over a number. Touch gets a kebab. Every action is
  also in the tray and the keyboard.
- A sort arrow shows only on the sorted column.
- Density: Compacto 40px, Normal 48px (the default), Amplio 56px. Type stays
  14px in every mode; inputs stay 16px. The choice sits in a quiet view
  options button and is kept per person on the account (`table_density` on
  `/me`; owner `table-density.ts`). Phones ignore it: rows become two-line
  list items of at least 64px.
- Records mode (no bank data) lists the period's gastos and ventas, each in
  its own currency. Entradas shows "-" until the server sends a total of the
  period's ventas; the web never adds rows to make one.
- Single-letter keys work only while focus is in the table and not in a field.

## 4. Accessibility

- Every control shows a visible focus ring, `0 0 0 0.125rem`.
- Icon-only buttons have a Spanish label.
- Every target is at least 44px.
- Meaning is never shown by colour alone.
- Reduced motion is respected, as in [Motion](#motion).

## 5. Dominican formats and language

- The app is Spanish first (`es-419`) by default. A person may choose English in
  Preferencias > Idioma de la app, saved on the account. `resolveLanguage` is the
  one owner: the account, then the device, then `es-419`. The browser is ignored.
- A typed date reads DD/MM/AAAA. A shown date follows [Numbers](#numbers).
- Every amount shows its currency, once per list as [Numbers](#numbers) says,
  with two decimals. Number separators follow the `es-419` locale.
- Never convert currency. An amount in another currency keeps its own currency label.

## 6. Core screens

Each screen uses the foundations and components above. Product's per-screen
rules go in each screen's slot and win over the general rules in this guide for
that screen.

### Sign-in

Founder direction: keep the current sign-in form and add an image panel beside it
at wide widths. This is not a full redesign. Product owns when it ships.

Photo brief for the side panel: real Dominican business counters, hands and
documents in daylight. No stock imagery or clichés. Nothing private appears in
frame, such as readable names, tax numbers or amounts.

**Behavior rules (pending from Product).**

### Inicio

Local Home checkpoint, October 24, 2026: preserve the current implementation and the month bounds below. The proposed separation of invoicing and collaboration remains unapplied. Pending navigation, progress and color decisions, verification limits and evidence are recorded in `docs/reports/home-checkpoint-20261024.md`. This is a local design baseline, not backend or release acceptance.

The month is a 16px control above the checklist, not a second title. On desktop the greeting lives only in the top bar. A phone keeps the month beside its content greeting and wraps it underneath when needed. The picker shows only the current month and supported past months, bounded by the service-provided current and earliest month. Future months are omitted, not shown disabled. When no earlier supported month is known, show the current month alone. Keep the month control visible even with one option so later bulk-upload history uses the same control.

Order: the month control, with the content greeting on phones only; "Para cerrar <mes>" with the month's figures (Ingresos, Gastos, Resultado neto, ITBIS) directly under it; then "Pendiente hoy", an h3 that holds Por cobrar and Por pagar side by side from the tablet stop up and stacked on a phone. Those two cards cover every month, so they sit apart from the month block.

Two columns once the canvas is 56rem or wider (Lucas, October 21, 2026): 38fr and 62fr, 24px apart. Row 1: the month control on the left, "Pendiente hoy" and Agregar on the right, one height and baseline. Row 2: "Para cerrar <mes>" beside Por cobrar and Por pagar. Row 3: the month's figures as two cards on the same columns, Ingresos and Gastos on the left, Resultado neto and ITBIS on the right over the Por cobrar and Por pagar columns. Cards in a row end together, including empty states. Keep the label at the shared top edge and center a compact empty-state group in the available body height. Do not shorten one card in isolation or leave a hole above the figures row. Narrower, one column in the order above.

"Cerrar <mes>" shows only when the month can close. While steps remain, one quiet line takes its place: "Cuando termines los 3 pasos, podrás cerrar octubre."

- A card is a small muted label, the total at 22px with its currency, and, when anything is overdue, a red line: "2 vencidas · RD$ 12,300.00", summed exactly per currency.
- A row is a round 44px check, the name, a lateness chip ("30 días tarde" in red, "vence hoy", "vence en 8 días"; owner `formatLateness`), and the amount. A row with no due day shows its issue day instead.
- Overdue rows come first, oldest first, then the nearest due. Four rows show, then "Ver las N".
- The check removes the row and offers Deshacer, which sets it back to pendiente. A failed mark puts the row back and says so within the affected row, with Reintentar when trying again can help. The toast only confirms a mark; there is no error toast.
- A Por pagar row opens its expense. A Por cobrar row is plain until an invoice has a record screen.

- Keep the received-document outcome separate from opening an intake action.
  Preview completion reads received receipt rows, not button clicks.
- Review-ready, still-reading and attention counts are separate groups. Give each
  its own label. Waiting uses amber; attention uses red. Never present their sum
  as the review-ready count or imply the groups are its breakdown.
- Floating preview diagnostics are opt-in through `?devtools=1`. They must not
  cover Home actions in the normal review URL.
- The phone Add action stays above the optional guide and below the header fade.
  At rest, the fade must not tint or blur the action.
- Both money cards keep the same label and total header in populated and empty
  states. A confirmed empty list with a known Business currency shows a formatted
  zero, such as RD$ 0.00. Keep server totals when supplied; never guess a currency
  or turn an unknown amount into zero. A shared subtle divider separates the
  total header from the body in both cards. Do not add separators between their
  document rows; keep those rows grouped with spacing. Center the settled status, explanation
  and action together within the available body area.
- Either settled money card uses the shared compact empty state: a small check,
  status, one explanation and a secondary Add action into the existing document
  flow. Keep its outer card aligned with the row and its content grouped,
  without a large illustration. When both balances are settled, keep the shared passive summary.
  First-run empty states retain their useful next action.
- Home uses the shared 16px body/control, 14px secondary and 21px section roles.
  Its summary figures keep the explicit 22px exception. A known reading state
  blocks a ready-to-close claim without displaying an unknown-value placeholder.
  While reading continues, omit the promise that completing the listed tasks is
  enough to close. Render the checklist footer only when it has a status or action.

**Behavior rules (pending from Product).**

### Bandeja

Bandeja is the one place receipts wait. Novedades folded into it on October 20,
2026: its rows were the same receipts, and its one extra fact (what is new)
is now the top group.

- A segmented control splits the same rows: **Por revisar** (the shared count
  Inicio and the sidebar show), **Con problema** and **Todo**, everything
  that arrived. Phones use the short names Revisar and Problemas.
- An email is only how a receipt arrived (Lucas, October 20, 2026). Once it
  saves a receipt, that receipt is the row. An email is a row of its own only
  while it is read (in Por revisar, like a receipt being read) or when it
  brought no receipt (in Con problema and Todo, counted there): "Correo de"
  the sender, the subject in quotes, and why. A repeat of a saved file is no
  row. Reintentar sits on that row when the server allows a retry.
- The full email history lives in Negocio > Correo de recibos, under the
  receiving address, as a quiet Historial with its refresh.
- What arrived since the last visit sits on top under "Nuevo desde tu última
  visita". The server's unread flag decides it.
- A row is one quiet line: name and total, then the state, the time and the
  marks. A problem says itself in red, in a few words. Fixes (Reintentar,
  Subir otro archivo, Escribir datos) live in the record, not in the row.
- Typed notes are rows like receipts.
- An email opens like a record: beside the list on a desktop, a full page
  with a way back on a phone. A receipt that came by email says "Llegó por
  correo · Ver correo", which opens the same email.
- Bandeja follows [Growing lists](#growing-lists).

**Behavior rules (pending from Product).** Product may add a "Falta información"
state here. Until Product defines it, it is not a status.

### Receipt detail

Every receipt that Cuadrao sorted automatically shows why it was sorted that way.
Product's rules set the exact presentation.

**Behavior rules (pending from Product).**

### Month close

A month without receipts shows as empty, never as a closed month at RD$0.00.

**Behavior rules (pending from Product).**

### 606/607 export

This guide sets the screen's presentation only, not the file formats. The
screen shows amounts in RD$ and never converts currency.

Exportar registros is one sheet, from the Agregar menu on every screen. The period is a
segmented control with this month, last month and this year by name, and
"Otras fechas" for a typed range of up to 366 days. Under it, one line gives
the exact dates. "Incluye" lists what the ZIP holds: records (Excel and CSV),
originals, and the 606 and 607, whose line says whether they come with this
period: included, close the month first, or whole month only. Exportar is the
green action pinned at the bottom. A finished download closes the sheet and
says so in a toast.

**Behavior rules (pending from Product).**

### Transacciones

Transacciones answers "does every peso that moved have its proof?" It replaced
Gastos for everyone on October 21, 2026: its name, place and shortcut, and old
Gastos links. Only the igualar parts (movements, suggestions, the run,
Desigualar, sin comprobante, the segments and their counts, "Banco al día
hasta") wait behind `businessBankMatchingEnabled`, default off. With it off,
or while the server has the bank routes off, the screen lists the period's
saved gastos and ventas in the same columns with no Por igualar flags:
Entradas and Salidas exact per currency, the receipt icon in Comprobante when
a file backs the record, each row opening its record in the record tray.
Lucas decided these on October 21, 2026:

- The screen is **Transacciones**, the verb **Igualar**, the segments **Por
  igualar**, **Igualadas** and **Todas**. Por igualar groups Sugerencias,
  Falta comprobante and Comprobantes sin movimiento.
- Version one is one movement to one document, plus "no lleva comprobante"
  with a reason (Cargo del banco, Entre mis cuentas, Compra informal,
  Personal). Splits, abonos and partial matches come later.
- Igualar also marks the document pagado or cobrado. The server writes it;
  the screen reads the state again after each decision and never moves a row
  itself.
- A row's state is a gray shape icon, its word on hover and for screen
  readers; the tray shows the full word. Red is for errors only.
- The table follows [Dense tables](#dense-tables). The last column is the
  igualar slot: "¿Este?" on a suggestion, the proof's icon once igualada, a
  round "+" when proof is missing.
- Igualar sugerencias is the screen's primary and walks the suggestions in the
  tray, most confident first. Igualadas in a row share one toast with one
  Deshacer, offered only when the server can take a decision back. A failed
  decision says so in the tray with Reintentar and its reference.
- The totals (Entradas, Salidas, Por igualar, Igualadas) are the server's,
  exact, one per currency. A total the server does not serve reads "-".
- The ledger fills the one canvas, as in [Widths](#widths).

## 7. Voice

Placeholder until Product sends final wording. Lead with the answer, put the
number first and show RD$ explicitly. The examples below are placeholders, not
approved copy:

- PLACEHOLDER: "Te faltan 3 documentos de octubre."
- PLACEHOLDER: "No pudimos confirmar el proveedor. Revísalo antes de exportar."

### Registros local preview: filters and table preferences

In the development mock preview, phone Filters uses the full-height sheet: a group list opens one group editor, Back keeps the draft, Apply commits, and close/Escape discards. Navigation rows are buttons with chevrons; the desktop rail keeps tabs. Date format belongs in the input placeholder, with the message slot reserved for validation.

Desktop preview table preferences are local memory only, including saved views. They do not invoke the production `/me` density persistence described above. Contraparte stays visible and fixed first; Monto and Moneda stay visible but can move independently. Other columns may hide or reorder. Column movement preserves focus; Space grabs/drops, arrows move, and Escape cancels the grabbed order. A picked-up column has a full-row outline and tint plus a filled handle, in both themes. The instruction area keeps its height while showing pickup feedback. A visible drop marker shows the actual insertion edge. Changing columns or row height preserves the current page. Phone list composition does not change with desktop column preferences.

### Registros local preview: record cells and annotations

Activity dates in the Registros preview show the year in the selected language, for example `25 oct 2026` or `Oct 25, 2026`. A calendar day does not shift with the device time zone. Missing or invalid dates show a dash. This rule applies to the table, narrow list and loaded-record glance; other recent-time displays keep their existing wording.

Estado uses a small colored text label from the top overview palette. Registros is an explicit exception to the global status-dot rule above; its labels have no inner dot. Review uses peach, approval uses yellow, and ready uses soft sage (#B8D0BE) with forest-green ink (#2f5a49), with the corresponding dark colors. The ready overview card and Listo status pill share the #B8D0BE background in the light theme. The overview keeps the same neutral text and icon colors as the other cards; the shared dark background stays muted deep green. Overview selection edges and keyboard focus rings use that same neutral card ink in both themes. The Listo label uses green ink; the primary action keeps its solid green fill. The row label is Listo or Ready. The top card keeps Listos para exportar. Workflow does not describe payment state.

The desktop table shows separate Monto and Moneda columns, adjacent by default. Monto shows the exact original-currency number, aligned right with tabular digits and the shared privacy mask. Moneda shows RD$ or US$ through `currencySymbol`; filters retain DOP and USD. Both columns remain visible. Each column moves independently through its own drag handle or keyboard controls. Narrow rows keep the amount and currency together at the upper right.

Notas shows only the current note on one line, with a tooltip for the full text. Empty notes use a quiet dash at rest on desktop. Hovering or focusing any part of the row reveals a pencil in the same slot; touch keeps the pencil visible. Clicking a note opens a compact editor on desktop or the shared sheet on a phone. Notes allow 500 characters with the same quiet, right-aligned current/limit counter as feedback. The counter describes the field without announcing each keystroke. Existing longer local notes stay intact on open and must be shortened before saving. Save applies the local value; Cancel, close and Escape discard the draft. There are no author, history, edited or activity indicators. Adjunto replaces Comprobante in preview table/settings/filter/glance labels. A known missing attachment uses a dash at rest on desktop and reveals a quiet plus when any part of the row is hovered or focused. Touch keeps the plus visible. The action retains a 44px target without shifting content; unknown remains a dash. Existing evidence opens its original record path. A local file can be selected, validated and previewed for that record, without uploading it.

One in-memory annotation map is keyed by Business and stable record kind plus ID. Saved local values survive filtering, paging, viewport changes and the loaded-record glance. They do not persist across refresh or reach the backend. Permissions use the existing prepare capability. Narrow rows offer visible Notes and Attachment icon buttons with 44px targets, stacked in the right-side action slot and separate from the row-open button. Related-record grouping and a new writing flow remain deferred.


### Registros preview sorting

Fecha, Monto and Contraparte are sortable through full header buttons. Only the active column shows an arrow and aria-sort. Fecha starts newest first, Monto starts largest magnitude first, and Contraparte starts locale-aware A–Z. Clicking the active header reverses it. The phone sort picker offers the same six orders and shares the selected sort. Local named views keep that sort with their column and summary preferences.

Sort the whole filtered loaded set before slicing a page. Changing sort returns to page one, without changing result counts or financial totals. Missing or invalid sort values remain last in both directions. Equal values use stable record kind and ID. Monto compares exact original-currency magnitudes and is available only when the entire filtered set has one known currency. With mixed currencies, its header and phone options explain how to choose a currency in Filtros. If filters make an active amount sort unavailable, show an explicit date-order fallback notice and the date arrow. Retain the intended amount order so it resumes when the results again have one currency. No conversion or mixed-currency numeric comparison is implied.

### Registros evidence and payment relationships, 26 October 2026

Keep three intents separate: add a new document through the existing intake; add supporting evidence to an existing activity through Adjunto; and Igualar an imported bank movement with an existing activity. Linking evidence never creates another purchase, changes the amount or marks the activity paid. A cash purchase can remain valid without a bank movement. Por revisar does not make every unmatched document incomplete.

The approved evidence design allows several attachments per activity. Add appends; it never replaces an existing attachment. Preserve the original file and its Business. A document already linked elsewhere needs an explicit conflict explanation; never move it automatically. No unlink action is available until its contract, permissions and any payment effects are defined. Existing evidence stays linked when a download is temporarily unavailable.

Con documento means linked evidence only, not verified, approved, fiscally accepted or paid. Sin documento and Sin movimiento vinculado are separate conditions. The local attachment filter reads only the loaded record's known evidence state: Con documento includes true, Sin documento includes false, and neither includes unknown. A selected local File is a preview that disappears on refresh, not a durable link, and must say so in the editor and its saved local presentation. It never changes that filter state or fiscal completeness.

Reuse of an already received document is a backend-dependent design path. Keep its selector unavailable until a complete authorized candidate list and link eligibility are supplied; the current inbox omits confirmed and dismissed documents. Device selection does not bypass that missing link contract or start a second ingestion flow. Editing follows the existing prepare capability; read-only access offers only authorized reads. Matching remains behind its existing default-off gate and needs the shared partial-payment contract before release. Future checkpoint notes and acceptance cases live in the Registros report; this rule records design intent, not a backend handoff or activation.


### Registros attachment form and loading alignment, 26 October 2026

The annotation footer follows the collaborator invitation form: one full-width
primary action with the item radius (8px), separated by one hairline. The X closes;
no duplicate Cancel button. This full-width form action is an exception to the pill
shape used for toolbar and file-picker buttons. On phone the sheet owns the footer
divider and safe-area padding, without a second inner divider.

Attachment selection uses the receipt intake's dashed inset, file-upload icon,
format/size guidance, pill file-picker action, and desktop drag/paste affordances.
Phone wording offers file selection. Supporting evidence selection must not start
new-document intake or claim a durable upload/link while it remains local-only.

Registros loading retains its overview and toolbar. Pending rows follow the same
visible columns/order, pinned identity, density, container breakpoint, phone
identity/value/state layout and pagination footprint as loaded records. Use the
shared delayed shimmer and reduced-motion behavior, not generic list placeholders.
Command-K focuses the mounted Records search and must not steal focus from an open
overlay; Home retains its existing global search.

### Registros metric shelf, 26 October 2026

The sales and expense summary uses three compact metric cards, with the rounded
shape, icon placement and neutral text of the overview cards. Use quieter neutral,
sage and cream surfaces, with dark-theme equivalents. The cards remain read-only
until the amount drill-down contract is connected. Todos still hides this summary.

Show at most two currency rows in each metric, in the same order across all three
cards. Do not add currencies together or create a second currency filter. When
more than two currencies occur, one shared action opens every currency in the
existing dossier. Group that breakdown by currency, with total, settled amount
and balance inside each group. Phone uses the shared sheet. Close or Escape
returns focus to the trigger. Retain the dossier gradient and privacy masking.

On narrow containers, stack the three cards with labels on the left and amounts
aligned on the right. Keep unknown settlement values unknown. Exclusions remain
available through the first card's information control. Existing financial
eligibility and filters retain their current meaning.

Financial summaries appear automatically for the Sales or Expenses record filter.
The mixed Todos view has no financial summary. There is no summary visibility
preference or separate Summary settings tab. Desktop table settings contain
Columns and Row height. Phone retains Filters and Sort without an empty settings
shortcut. A display preference must never change record eligibility or totals.

### Invoicing: customers, schedules and empty states

Facturas, Clientes and Programadas share one workspace switch. Customers use a
desktop table with identity, explicit dated activity, last invoice, last payment
and next planned draft. Creation date is optional in settings and hidden by
default. Phone uses compact rows and the same dossier for details. Unknown facts
remain dashes; customer edits do not rewrite existing invoice snapshots.

Programadas opens the existing dossier/sheet. Reuse the customer picker and a
saved draft as the template, with a separate schedule copy. Default to creating
drafts. Automatic issuance is an explicit choice only when actual readiness is
verified; an unavailable choice explains what is missing. Keep paused schedules
and archived customer history visible. An occurrence date is planned, not proof
that execution happened. Preserve month-end and leap-year anchors.

Empty states depend on context: first use offers a clear creation action; an
empty stage is quiet; filtered zero offers clearing filters; an empty active
schedule list with paused entries offers access to paused schedules. Use the
invoice, customer directory and schedule calendar illustrations in
`web/public/images/invoicing/`. Do not reuse the notification bell for these jobs.
Keep the same restrained illustration scale, spacing and typography across them.

For invoice tables, group Moneda | Total | Por cobrar. Currency appears once in
its own column and both amounts align right with tabular figures. On phone,
retain currency beside each amount since there is no shared column header.
Keep filtering currency separate from changing display or converting values.


### Invoicing editor and workspace contract, 26 October 2026

Use the [current behavior guide](../../../docs/reports/invoicing-preview-20261026.md)
for the complete implemented interaction inventory and preview limitations. The
[review-draft handoff](../../../docs/handoffs/invoicing-design-checkpoint-20261026.md)
owns outstanding wiring and acceptance requirements; it is not checkpoint clearance.

Facturación has its own identity: workspace segments for Facturas, Clientes and
Programadas, then underline stage tabs inside Facturas. Do not reproduce the large
Records overview cards. Financial metric cards appear only in Todas, below the
controls, and follow the filtered results across pages. They are read-only and use
the compact Records card family. Preserve two currency rows plus a single overflow
dossier action. Do not introduce another currency filter. Moneda gives the currency
context for both Total and Por cobrar in the desktop table.

Before the first invoice, three setup cards sit above the contextual invoice art.
Their actions open existing flows. A completion check must derive from valid saved
facts, never from a click or visit. This progress contract still needs backend
connection; the illustration and polished cards do not establish readiness.

Creation opens the dossier expanded, with a left step form and right live document
separated by a vertical hairline. Use Customer, Details, Terms and Review. The name
picker remains the one name field, whether selecting or adding a customer. Hide
unneeded fields at cold start and remove the autofill notice after it has served
its purpose. Invoice type belongs to Terms, not the customer's identity.

Only one item editor is expanded at a time. Its collapsed summary remains one click
away; invalid fields reopen the affected item. Quantity stays compact and delete
has its own aligned target. The footer stays anchored. Next is the single primary
step action; Save draft and Back are quiet. Save draft accepts unfinished work.
Review has one primary preparation action near the email fields and quiet section
edit links. Use the collaborator-invite primary button shape, not extra pill CTAs.

The final document/email preview uses an underline tab bar. Live section markers
are rounded corner brackets, inset clear of content, with three subtle squeezes on
section entry and a reduced-motion alternative. Never put editing markers in saved
or printed output. The document's customer/date split, products divider and localized
branding footer preserve a clear reading order.

Pagination sits outside the table card: result count left, page-size picker centered,
and bounded page navigation right. Match Registros spacing, labels and focus targets.
These shared patterns do not imply all Records features are already implemented in
Facturación. Saved views, exports and request recovery need their own contracts.
