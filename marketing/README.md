# Cuadrao marketing website

The public Cuadrao website: Business, Personal, contact and privacy, in Spanish and English. It is an independent Next.js package. It shares nothing at runtime with the Argus API or the legacy `web/` app, needs no Argus environment group, and has its own lockfile.

Forms, limits and data: [forms contract](../docs/specs/cuadrao-marketing-forms-contract.md). Release settings, cutover and rollback: [launch runbook](../docs/runbooks/cuadrao-marketing-launch.md). Design: [website design guide](../.agent/designs/cuadrao-business/DESIGN.md).

## Run

```bash
bun install --frozen-lockfile
bun run dev          # http://localhost:3000
bun run lint && bun run typecheck && bun test
bun run build && bun run start -- -p 3000
bunx playwright install chromium && bun run test:e2e   # needs a build
```

The touch-up review and exact ES/EN draft copy live in [the delivery record](../docs/reports/evidence/cuadrao-marketing-touchup/README.md). Dev and build derive the served header lockup from `brand/`; edit the canonical source, not its public copy.

For parallel local lanes, override `MARKETING_E2E_SITE_PORT`, `MARKETING_E2E_PUBLIC_PORT` and `MARKETING_E2E_MOCK_PORT` together. The browser suite reads the existing production build, so rebuild after every product change. `MARKETING_CAPTURE_URL=http://127.0.0.1:4512 node scripts/capture-touchup.mjs` captures all routes in an isolated headless browser; run it only against the committed build named in its manifest.

Provider settings are optional locally. Without them each form shows its unavailable state.

## Layout

| Path | Owns |
| --- | --- |
| `lib/site-routes.ts` | The one URL map: paths, canonical and alternate URLs, sitemap entries, rewrites, old-path redirects |
| `lib/page-metadata.ts` | Titles, descriptions, share images |
| `lib/indexing.ts`, `proxy.ts`, `app/robots.ts`, `app/sitemap.ts` | Runtime indexing switch (`CUADRAO_SITE_INDEXING=public`); every other host sends `noindex` |
| `lib/forms/` | Inquiry and signup handlers, validation, limits, configuration |
| `lib/ops/`, `scripts/signups.ts` | Operator removal and availability notice |
| `components/` | Pages, copy and styles moved from `web/components/business` |
| `app/icon.svg`, `scripts/make-icons.mjs` | Cuadrao mark ("Lean, calm") and the PNG/ICO files rendered from it |
| `brand/` | The mark without its tile (light and dark), the outlined wordmark and the two lockups, with the wordmark specification, colours and lockup geometry in `brand/README.md`. Tests keep every file's shapes identical to `app/icon.svg` and the wordmark's styling equal to the site's `.wordmark` rule |

Spanish is unprefixed (`/`, `/personal`, `/contacto`, `/privacidad`); English is under `/en`. The App Router tree is `/[locale]/[[...slug]]`; a rewrite serves Spanish from the unprefixed path and the internal `/es` tree redirects to it.

## Environment

See the forms contract. Nothing here is read at build time except through `next.config.ts`, so changing a variable needs a restart, not a rebuild.

## Reverting the extraction

The package only added files under `marketing/`, a migration and docs, and removed the website from `web/`. On integration, reverting the extraction commits restores the pre-extraction `web/` routes behind `CUADRAO_WEBSITE_PREVIEW`. On `main`, which never had those routes, reverting the promotion commit removes `marketing/` and its migration file and nothing else. Either way it touches no application data. The signup table and its rows are untouched by a code revert; dropping the table is a separate, deliberate migration that must preserve registrations first.
