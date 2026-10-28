# Inicio, shared bar and scoped search design checkpoint, 2026-10-28

## Clearance and frozen source

Lucas cleared this checkpoint on 2026-10-28 ("Go, lock at end") after approving
each piece below in the design lane. On 2026-10-28 he also ruled that approved
designs do not stay behind preview flags: the approved Inicio, bar, scoped search
and Actividad are the default in every build, and only data that does not exist yet
is left out (see "Flags and gates").

- Branch: `claude/design-activity-home-04523b`, merged with
  `origin/codex/private-alpha-next` at `7a1113b70`.
- Frozen commits: the commits that add and update this document; the exact head
  SHA is in the handoff message.
- The orchestrator cleared edits to `transacciones/**`, `recepcion/**` and the
  search window files on 2026-10-28. This checkpoint does not authorize migrations,
  deployment, flag changes or backend scope.
- Live: every Business screen on staging. Local preview with sample data:
  `/dev/business-preview?view=overview|inbox|transactions|business|activity` with
  `NEXT_PUBLIC_MOCK_AUTH=true`. Sample states (local preview only):
  `&money=current|empty|long`, `&attention=empty`, `&setup=new`,
  `&monthClose=loading|empty|error`, `&activity=contract|empty|loading|error`.
- Screens (390 phone, 1440 with the rail open and collapsed, and the search window's
  three states) are in the shared notes folder `inicio-checkpoint-20261028/`, not in
  the repository.

## Approved surfaces

The design rules live in `.agent/designs/cuadrao-business-app/DESIGN.md`
("Page heading" and "Top bar, canvas and search"). In short:

- **Inicio** is three layers in a bounded 80rem box: Resumen del negocio (Necesita
  atención beside Configurar negocio and Continuar trabajando), Finanzas por mes (the
  month selector heads the month's figures and Para cerrar), and Cobros y pagos.
  Personalizar Inicio reorders the three. Cards are neutral; color carries meaning only.
- **The shared bar** on every Business screen: heading · Buscar ⌘K · Agregar · icons ·
  avatar, one center line, opaque under its heading, bounded with the content.
- **Scoped search** on Bandeja and Registros, through one search window. The lists
  lend their own query (`foundation/list-search.ts`); there is no second filter state.
- **Registros and Bandeja toolbars** drop their search field and Agregar on wide screens
  in the preview. Registros' Export is its own button, still gated on the `export`
  permission. Bandeja keeps Export under "Más acciones" (#1406 rules unchanged).
- **Setup** shows only to people who may configure the Business
  (`canManageBusiness` in `business-ui.tsx`, the one rule Negocio already used).

- **Actividad** reads `GET /business/activity` (#1407) live: rows as the feed returns
  them, no filters, no Registro column and no record links (those need #1410 and
  ACT-2a), "Cargar más" on `next_cursor`, and an error state with the server's
  reference plus Reintentar and Ir a Inicio.

## Flags and gates

Approved designs carry no flag. What remains, why, and what removes it:

| Gate | Where | Why it stays | Removed by |
|---|---|---|---|
| Recent work hidden live | `HomeWork` (`samples`) | no `GET /business/recents` | that endpoint; then delete `RECENT_WORK` |
| Setup hidden live | `HomeWork`, `HomeSetupLead` | no `GET /business/setup` | that endpoint; then delete `SETUP_STATE` |
| Registrar cobro / pago hidden | `settlementAction` (`openSettlement`) | no payment workflow for open items | a server workflow passed as `openSettlement` |
| Actividad filters, Registro column, links hidden live | `ActivityDraft` (`live`) | #1407 sends no labels or link targets | #1410 and ACT-2a fields |
| Facturas en borrador row | `useHomeCounts` (`businessInvoicingEnabled`) | Facturación's own feature flag, not this design | Facturación's release |
| Business search (bar search, scoped search) | `NEXT_PUBLIC_OMNISEARCH_ENABLED` (on unless "false") and `NEXT_PUBLIC_BUSINESS_SEARCH_ENABLED` (off unless "true"), read once as `barSearchAvailable` in `list-search.ts` | the shell's existing search gate, not this design; staging's hosted value is unverified | set `NEXT_PUBLIC_BUSINESS_SEARCH_ENABLED=true` on staging for the demo. Off: the bar shows no search and Bandeja and Registros keep their own field, so nothing is lost |
| Sample states (`?money=`, `?attention=`, `?setup=`, `?activity=`, `?monthClose=`) | `money-preview.ts`, `HomeOverviewDraft`, `ActivityDraft`, `BusinessMonthClosePanel` | a local design tool, development with mock sign-in only | never needed live; delete with the samples |

Safety gates for external actions (issuing fiscal invoices, sending email, bank
connections) live in their own lanes and are untouched here.

Legacy kept for one release: `BusinessMonthClosePanel`'s `layout="inicio"` branch is
no longer rendered by any screen; its tests still cover it. Remove the branch and move
those tests to the `finance` layout in the next cleanup.

## Fields each element needs

| Element | Source | Status |
|---|---|---|
| Greeting, date, Business name | bridge greeting, `chosen.name` | live |
| Necesita atención rows | Bandeja records (`con_problema`, `por_revisar`) | live |
| Necesita atención count | `waiting_on_person_count` (union of both buckets) | MISSING (count hidden live) |
| Registros por revisar row | `POST /business/reports/query` overview `needs_review` | live |
| Facturas en borrador row | `GET /business/invoices` `stage_counts.draft` | live where Facturación is on |
| Continuar trabajando | `GET /business/recents` | MISSING (hidden live; drafts row still shows) |
| Configurar negocio steps | `GET /business/setup` (required vs optional, done) | MISSING (hidden live); "Crear el negocio" must report done |
| Actividad rows | `GET /business/activity` | live |
| Finanzas por mes, Para cerrar | month close (existing wiring) | live |
| Por cobrar, Por pagar | `GET /business/open-items` (document totals, all months) | live |

## Actions

| Action | Status |
|---|---|
| Row open (Bandeja, records, drafts) | live |
| Registros por revisar → Registros | live, unfiltered; MISSING Registros opened on the review filter |
| Facturas en borrador → Facturación | live, unfiltered; MISSING Facturación opened on drafts |
| Registrar cobro / Registrar pago | hidden; MISSING a server-backed payment workflow (`openSettlement` seam) |
| Ver todas (Cobros y pagos) | expands in place; MISSING a scoped Registros destination |
| Scoped search filter, clear, widen | live through the list's own query |
| Agregar (bar), Export (Registros) | live, same permissions as before |

## Notes for other owners

- **Search owner:** `ChatCommandPalette.tsx` gained `initialQuery`, the Business-only
  scope (`command-palette/WorkspaceSearchScope.tsx`) and the adaptive layout
  (`workspaceSearchView`, `adaptiveSearchPlacement`, `usePaletteLayoutMode`), all keyed
  on `WorkspaceSearch.adaptive` / `scope`, which only Business search sets. Chat search
  is unchanged and its tests pass as written. `useBusinessSearch.ts` fallback strings
  now say "this business"; `__tests__/business-search.test.tsx` checks the hook's real
  copy in both languages.
- **Registros owner:** `RecordsToolbar` lends `filter.query` (200-character cap kept);
  #1412's report location and `isProgrammaticPop` guard are untouched. On a phone the
  toolbar keeps its field.
- **Bandeja owner:** `ReceptionPreview` lends its query; `ReceptionAddMenu` takes
  `addInBar`. #1406 and #1411 behavior is unchanged.
- **Shell owner:** `WorkspaceMain` and `ChatInterface` carry `data-workspace-canvas` and
  `data-workspace-bar`; bounds apply only under `body[data-workspace-bounded]`.
- **Shared canvas width:** `BUSINESS_CANVAS_MAX` in `foundation/business-canvas.ts`.
- **Copy:** draft Spanish copy for Home and Actividad still lives in their `COPY`
  objects; new locale keys sit under `business.search.*`, `business.month_close.*` and
  `business.page_intro.*`. Copy approval and moving the draft objects into the locale
  files belong to the copy pass.
- **Open design question (Lucas):** "Exportar registros" is reachable from the bar's Agregar menu
  (the whole-Business export sheet) and from each list's toolbar (Registros' Export button exports
  the current report; Bandeja's "Más acciones"). Decide whether the bar menu keeps it once the lists
  carry their own.
- **Known failures, not from this lane:** the four
  `workspace-preview-invitation` tests read `temp/home-setup/index.html`, identical to
  the base branch, and fail there too.
