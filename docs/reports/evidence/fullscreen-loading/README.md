# Full-screen loading bar

Owner: web full-screen loading lane. Scope approved by Lucas on October 16, 2026.
Base: `955b96b16133883fff3008604065583ff6294bb3`.

The startup profile check and landing session check share a 240px Cuadrao lockup
and a matching 240px bar. A mount-local timer delays both the visual and the
status announcement for 300ms. Unmount clears the timer. The bar is indeterminate;
it does not claim a percentage or a processing stage. Existing brand assets and
color tokens supply light and dark appearance. Reduced motion stops the sheen.

The Spanish status is exactly `Cargando`, visually hidden and announced politely.
English uses the existing `common.loading` label. In-app receipt and conversation
waits keep their existing text and skeletons. No locale, sidebar, auth behavior,
API, data, provider, or marketing changes are included.

Model the Domain kept the state to one delayed visibility value with one owner.
Prove It Works led to checks against the mounted page and computed browser styles.
The tradeoff is a blank initial 300ms for fast loads. A CSS module isolates the
animation from other loading indicators. Detection uses the behavioral test suite;
this purely visual change adds no telemetry or stored browser data.

## Verification

- `bun test __tests__`: 2663 passed before the final English-label test was added.
- `bun test __tests__/business-loading.dom.test.tsx`: 9 passed on the final source.
- `bun run build`: passed. An initial sandboxed build was stopped because the
  local process restrictions prevented it from completing; the isolated build
  outside that restriction passed. Generated configuration changes were removed.
- `bun run lint`: passed, with 8 existing warnings outside this change.
- Ownership and modularity checks passed.
- Browser suite: 9 passed. The full-screen checks cover both entry gates, 299ms absence, 300ms
  presence, fast-load cancellation, moving sheen, reduced motion, hidden status,
  and equal logo/bar widths. It blocks all non-local requests.
- The existing Business loading browser suite also checks the unchanged
  overview, inbox, receipts, updates, and receipt-detail waits.

Run the browser checks from `web` with:

```sh
bun node_modules/@playwright/test/cli.js test -c e2e/fullscreen-loading.playwright.config.ts
```

The config starts a local fixture server. `PLAYWRIGHT_BASE_URL` can select an
already-running local server. Capture images by setting
`CUADRAO_LOADING_EVIDENCE_DIR` to an absolute directory. The before images were
captured on the base; the after images use the implementation in this PR.
These are local fixture proofs, not a staging deployment or a real account walk.

## Images

| View | Before | After | Reduced motion |
| --- | --- | --- | --- |
| Phone, light | [Before](before-light-390.png) | [After](after-light-390.png) | [Still](after-reduced-light-390.png) |
| Phone, dark | [Before](before-dark-390.png) | [After](after-dark-390.png) | [Still](after-reduced-dark-390.png) |
| Desktop, light | [Before](before-light-1280.png) | [After](after-light-1280.png) | [Still](after-reduced-light-1280.png) |
| Desktop, dark | [Before](before-dark-1280.png) | [After](after-dark-1280.png) | [Still](after-reduced-dark-1280.png) |
