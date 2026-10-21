# Cuadrao marketing launch evidence

Evidence for the independent `marketing/` package. Each file names the commit it vouches for. See the [launch record](../../2026-10-07-cuadrao-marketing-launch.md) for status; nothing here is hosted proof unless it says so.

| File | What it shows | Vouches for |
| --- | --- | --- |
| [parity-results.json](parity-results.json), [parity.mjs](parity.mjs) | 48 of 48 full-page screenshots byte-identical between the legacy `/business` pages and the extracted package (Chromium and WebKit, 1440 and 390 pixels, es and en, light and dark) | `ca97f5389`, extraction only |
| [storage-proof.md](storage-proof.md) | Signup route, PostgREST and Postgres end to end, operator removal and notice dry run, constraints. The migration was later hardened (explicit `service_role` revoke); its 11 table tests were rerun against a database whose default privileges hand `service_role` everything, as hosted Supabase does | `3e6cf00de`, migration rerun at `48174d8c3` |
| [browser.json](browser.json), [screens/](screens/), [capture.mjs](capture.mjs) | Page identity, icons, redirects, health, robots, storage emptiness and screenshots of every page | `5d9a1f55a` (integration after #926). Recaptured after review found the privacy and contact screenshots still showed text that #906 and #926 replaced; every other page is byte-identical to the earlier capture |
| [verify-origin-local.json](verify-origin-local.json) | The read-only origin verifier passes both modes on local builds and rejects the wrong mode | the commit that adds `scripts/verify-origin.ts` |

Hosted evidence (Render address, real inquiry receipt, hosted signup, domain) does not exist yet and is not claimed.

## Test runs on the final code

- Unit: 123 passing at `4567c95c4` (`bun test`; CI holds the current count), lint and typecheck clean. The inquiry recipient (`CUADRAO_INQUIRY_TO`, no default) was added after the screenshots were captured; it changes no rendered page.
- Browser: 130 passing across desktop (1440) and mobile (390) in Chromium, covering both forms against recording providers (receipt, double click, retry after a lost response, provider down, repeat signup, no cookies or browser storage), identity, redirects, indexing on candidate and public hosts, 404 page, mixed-case URLs and automated WCAG 2.1 AA checks on all eight pages.
- Clean install: `bun install --frozen-lockfile` with Bun 1.3.14, then build and start on Node 24.21.0 with an empty environment: health 200, pages 200, both forms answer a truthful 503.
- `web/` is byte-identical to its state before the website was added (`git diff da2d4633f^ -- web` is empty); it still lints (0 errors), passes 2,221 tests and builds.
- Modularity budget: no violations. Changed-document links: clean.
