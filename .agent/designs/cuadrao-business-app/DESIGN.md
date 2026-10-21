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

This guide covers the light appearance. Dark appearance needs its own design.

### Type

- Headings use Space Grotesk at weight 500, never bold. Body and controls use Inter.
- The app's scale is **16 body, 21 section title, 26 page title**. The
  golden-ratio display sizes (42 and 68) belong to the marketing site: in a
  dense money screen they push the numbers below the fold.
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

One canvas holds every Business screen (Lucas, October 21, 2026): at most
75rem (1200px) wide, left-aligned at the main area's 32px gutter from the
tablet stop up. The top bar spans the same box, so the search starts at the
canvas's left edge and the actions end at its right edge on every screen.
Inside it, Inicio and Transacciones fill the canvas, the Bandeja keeps its
48rem list beside the record tray, and Negocio and other forms keep a 40rem
column at its left. No screen widens or moves the canvas. Owner:
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

### Seven states

Every component defines seven states: default, hover, focus, pressed, disabled,
loading and error. A disabled control shows why it is disabled next to it.

### Forms

One owner builds every field: `web/components/ui/FormField.tsx` (field styles in
`web/components/ui/form-field.ts`, password rules in `web/lib/password-strength.ts`).
Use it; never restyle a field by hand (Lucas, October 21, 2026).

- Every field has a real label above it that never leaves. Example text never
  replaces the label or the instructions.
- A field stays quiet while the owner types. Leaving it with something in it
  checks it. From then on it is checked on every keystroke, so the error clears
  the moment the value is fixed. Editing another field does not clear it.
- Each field reserves one line for its hint or its error, so the submit never
  moves. Errors say how to fix the value. Never use browser validation pop-ups.
- The submit stays pressable. A failed submit opens a summary at the top that
  links to each broken field and moves focus there.
- Autofill is styled to the surface. Codes such as an RNC are text with
  `inputMode="numeric"`, never `type="number"`.
- Passwords show a live checklist and a strength meter (Débil, Casi lista,
  Fuerte), always with the word. They use the shared eye toggle, never block
  paste, have no confirm field, and set `passwordrules` for password managers.
  Only the server's real minimum blocks a password.

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
  phone it is a full page with a way back. It is the one sheet that is not
  modal.
- **Sheets:** Agregar, Exportar registros, settings, forms and lists.
- **Popovers:** pickers (a date, a month, a menu, the period's Personalizado
  range, which opens under its segment and in a sheet on a phone).
- **Alerts:** closing a month, deleting, removing someone's access.

### Sidebar and account

Lucas set this on October 20, 2026. The left sidebar is where you work; the
top right is who you are.

- **Top left:** the business you are working in (its initial, name and your
  role), the one name that reads first. Its menu switches business and opens
  **Configurar negocio**. The open and close toggle sits beside it.
- **Then:** the screens: Inicio, Bandeja, Transacciones. Negocio is reached from the
  business menu (Configurar negocio), the one door.
- **Foot of the rail:** the Cuadrao mark, small and quiet.
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
- **Top bar:** spans the one canvas and never changes per screen. Search on the left, always
  visible (its placeholder says what it finds). On the right: **Agregar ▾**,
  the one global action, whose menu holds Exportar registros and Copiar
  dirección de reenvío; the **Ocultar montos** eye, which
  blurs every amount for screen sharing; then the account. No screen repeats
  these buttons. Phones keep Agregar ▾ at the top of each screen instead.
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
- The top bar's Agregar is the green primary on every screen (Lucas, October
  21, 2026). "One per screen" counts the page's content only, never the top
  bar: Igualar sugerencias is Transacciones' one primary in the page while
  Agregar stays green above it.
- `components/business-app/business-ui.tsx` owns the classes
  (`primaryButtonClass`, `secondaryButtonClass`, `quietButtonClass`,
  `dangerButtonClass`, `dangerConfirmButtonClass`). Compose a width or a margin
  onto one; never copy its colours.
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

### Toasts and saves

- One toast at a time, from one presenter, clear of the page's controls.
- A plain confirmation lasts 4 seconds. A toast with Undo lasts longer and its
  timer pauses on hover and focus.
- Never insert a banner mid-page that shifts the content. Field errors stay beside their field.
- A failed save never shows as success. Keep the owner's input and offer one
  honest retry.
- Announce confirmations politely. An inline error is `role="alert"`. The
  toast type has no error or warning kind, so the compiler refuses one.

### Errors

Type the error first; each type has its own surface (Lucas, October 20, 2026):

| Type | Example | Surface |
| --- | --- | --- |
| Validation | A typo in an RNC | Inline under the field, after the owner leaves it and live from then on. The action stays pressable and a failed press lists each broken field (see Forms). |
| Network | The connection dropped | The banner docked at the top ("Estás sin conexión. Lo que hagas ahora no se guarda hasta que vuelva."). It moves the bar and the page down, never covers them, and leaves when the connection is back. |
| Server | The save failed on our side | Inline where the work is, with Reintentar and the reference code. A failed confirm says so inside its alert, whose button tries again. Never a toast. |
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
- Ventas and Entradas in records mode (no bank data) wait on a server read of
  the period's ventas; until then records mode lists gastos and Entradas
  shows "-".
- Single-letter keys work only while focus is in the table and not in a field.

## 4. Accessibility

- Every control shows a visible focus ring, `0 0 0 0.125rem`.
- Icon-only buttons have a Spanish label.
- Every target is at least 44px.
- Meaning is never shown by colour alone.
- Reduced motion is respected, as in [Motion](#motion).

## 5. Dominican formats and language

- The app is always in Spanish (`es-419`).
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

The month is a 16px control at the right of the greeting row, not a second title; a phone wraps it under the greeting.

Order: the greeting row; "Para cerrar <mes>" with the month's figures (Ingresos, Gastos, Resultado neto, ITBIS) directly under it; then "Pendiente hoy", an h3 that holds Por cobrar and Por pagar side by side from the tablet stop up and stacked on a phone. Those two cards cover every month, so they sit apart from the month block.

Two columns once the canvas is 56rem or wider (Lucas, October 21, 2026): 38fr and 62fr, 24px apart. Row 1: the greeting row on the left, "Pendiente hoy" on the right at the greeting's 26px, one height and baseline. Row 2: "Para cerrar <mes>" beside Por cobrar and Por pagar. Row 3: the month's figures as two cards on the same columns, Ingresos and Gastos on the left, Resultado neto and ITBIS on the right over the Por cobrar and Por pagar columns. Cards in a row end together. Narrower, one column in the order above.

"Cerrar <mes>" shows only when the month can close. While steps remain, one quiet line takes its place: "Cuando termines los 3 pasos, podrás cerrar octubre."

- A card is a small muted label, the total at 22px with its currency, and, when anything is overdue, a red line: "2 vencidas · RD$ 12,300.00", summed exactly per currency.
- A row is a round 44px check, the name, a lateness chip ("30 días tarde" in red, "vence hoy", "vence en 8 días"; owner `formatLateness`), and the amount. A row with no due day shows its issue day instead.
- Overdue rows come first, oldest first, then the nearest due. Four rows show, then "Ver las N".
- The check removes the row and offers Deshacer, which sets it back to pendiente. A failed mark puts the row back with an error toast.
- A Por pagar row opens its expense. A Por cobrar row is plain until an invoice has a record screen.

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
