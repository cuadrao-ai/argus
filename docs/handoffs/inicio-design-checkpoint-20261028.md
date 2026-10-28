# Inicio, shared bar and scoped search design checkpoint, 2026-10-28

## Clearance and frozen source

Lucas cleared this checkpoint on 2026-10-28 ("Go, lock at end") after approving
each piece below in the design lane. Everything ships behind the local-preview
gate `INICIO_REDESIGN_PREVIEW` (`web/components/business-app/inicio/preview.ts`):
production keeps today's layout until that gate opens.

- Branch: `claude/design-activity-home-04523b`, merged with
  `origin/codex/private-alpha-next` at `7a1113b70`.
- Frozen commits: the two commits that add this document; the exact head SHA is in
  the handoff message.
- The orchestrator cleared edits to `transacciones/**`, `recepcion/**` and the
  search window files on 2026-10-28. This checkpoint does not authorize migrations,
  deployment, flag changes or backend scope.
- Preview: `/dev/business-preview?view=overview|inbox|transactions|business` with
  `NEXT_PUBLIC_MOCK_AUTH=true`. Preview-only states: `&money=current|empty|long`,
  `&attention=empty`, `&setup=new`, `&monthClose=loading|empty|error`.
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

## Fields each element needs

| Element | Source | Status |
|---|---|---|
| Greeting, date, Business name | bridge greeting, `chosen.name` | live |
| Necesita atención rows | Bandeja records (`con_problema`, `por_revisar`) | live |
| Necesita atención count | `waiting_on_person_count` (union of both buckets) | MISSING |
| Registros por revisar row | `GET /business/reports` overview `needs_review` | real, not yet read by Inicio (fixture) |
| Facturas en borrador row | `GET /business/invoices` `stage_counts.draft` | real, not yet read by Inicio (fixture) |
| Continuar trabajando | `GET /business/recents` | MISSING (fixture) |
| Configurar negocio steps | `GET /business/setup` (required vs optional, done) | MISSING (fixture); "Crear el negocio" must report done |
| Finanzas por mes, Para cerrar | month close (existing wiring) | live |
| Por cobrar, Por pagar | `GET /business/open-items` (document totals, all months) | live |

## Actions

| Action | Status |
|---|---|
| Row open (Bandeja, records, drafts) | live |
| Registros por revisar → Registros | live, unfiltered; MISSING Registros opened on the review filter |
| Facturas en borrador → Facturación | live, unfiltered; MISSING Facturación opened on drafts |
| Registrar cobro / Registrar pago | disabled; MISSING a server-backed payment workflow (`openSettlement` seam) |
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
- **Copy:** draft Spanish copy for Home and Actividad still lives in their `COPY`
  objects; new locale keys sit under `business.search.*`, `business.month_close.*` and
  `business.page_intro.*`. Copy approval and moving the draft objects into the locale
  files belong to the copy pass.
- **Known failures, not from this lane:** the four
  `workspace-preview-invitation` tests read `temp/home-setup/index.html`, identical to
  the base branch, and fail there too.
