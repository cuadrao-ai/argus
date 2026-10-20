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
- Input text is at least 16px.
- Money uses fixed-width (tabular) digits everywhere, so columns of amounts align.
- Labels and headings wrap. They never truncate or clip.

### Spacing, shape and depth

- Spacing moves in 4px steps.
- Surfaces are flat. Separate them with colour contrast and hairlines, never
  decorative shadows.
- Corners are 12px for standard elements and 20px for cards. Buttons are fully round.

### Widths

Design and check each screen at the five widths of the Argus guide. Nothing
scrolls sideways at any width.

| Name | Width |
| --- | --- |
| Mobile small | under 400px |
| Mobile | 400–720px |
| Tablet | 720–1024px |
| Desktop | 1024–1280px |
| Large | 1280px and up |

### Motion

Motion is calm and short. With reduced motion on, show the end state without
movement. Loading placeholders stop moving.

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

- Every field has a visible label. Example text never replaces the label or
  the instructions.
- Errors sit under their field, in plain words that say how to fix the value.
  Never use browser validation pop-ups.
- A valid edit clears that field's error. Editing another field does not.

### Delete confirmations

- Ask a specific question that names the record.
- Say what actually happens. Promise only the recovery that exists.
- Cancel is an outlined button. The confirm button uses `#9e2f39`.
- The confirm button works once. While the delete runs, a second press does nothing.
- Trap focus in the dialog. Escape and the backdrop cancel. When the dialog
  closes, focus returns to the control that opened it.

### Toasts and saves

- One toast at a time, from one presenter, clear of the page's controls.
- A plain confirmation lasts 3 seconds. A toast with Undo lasts longer and its
  timer pauses on hover and focus.
- Never insert a banner that shifts the page. Field errors stay beside their field.
- A failed save never shows as success. Keep the owner's input and offer one
  honest retry.
- Announce confirmations politely and errors assertively to screen readers.

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

## 4. Accessibility

- Every control shows a visible focus ring, `0 0 0 0.125rem`.
- Icon-only buttons have a Spanish label.
- Every target is at least 44px.
- Meaning is never shown by colour alone.
- Reduced motion is respected, as in [Motion](#motion).

## 5. Dominican formats and language

- The app is always in Spanish (`es-419`).
- Dates read DD/MM, with the year as DD/MM/AAAA where it is needed.
- Every amount shows RD$ explicitly, with two decimals. Number separators follow
  the `es-419` locale.
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

**Behavior rules (pending from Product).**

### Bandeja

Bandeja follows [Growing lists](#growing-lists) and shows each receipt's status as
in [Status](#2-status).

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

**Behavior rules (pending from Product).**

## 7. Voice

Placeholder until Product sends final wording. Lead with the answer, put the
number first and show RD$ explicitly. The examples below are placeholders, not
approved copy:

- PLACEHOLDER: "Te faltan 3 documentos de octubre."
- PLACEHOLDER: "No pudimos confirmar el proveedor. Revísalo antes de exportar."
