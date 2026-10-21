# Phone preview language follow-up

Runtime source `d5436b7e861876fea205ac7cdb68ac943702c8fa` fixes the phone preview after a header language change. Its CTA labels now derive from the same locale copy as the page. The original Spanish PNG remains unchanged; a decorative layer replaces its button region. English shows Create account and Sign in. Spanish shows Crear cuenta and Iniciar sesión. The accepted hand, phone angle, brand artwork and animation target remain unchanged.

## Verification

- The parent reproduced Spanish button pixels on the English page before the fix and verified ES to EN to ES afterward in the in-app browser.
- Production build, lint, typecheck and diff checks passed. Modularity passed from the repository root against the reconciled tree.
- The focused signup/motion suite passed 35 checks with one intentional pointer-only touch skip. See [browser output](browser-results.txt).
- Four WebKit locale/screenshot checks passed at 1440px and 390px. The parent inspected the English mobile phone and full desktop demo captures.
- The existing [demo captures](../screens/manifest.json) and video were refreshed at this source through the local4513 proxy. Captured signup responses are browser fixtures, with no provider calls.
- Independent scoped review was clean, with no added comments or suppressions. Both workers returned ownership and stopped.

## Tab identity check

Port4512 root serves `Cada cuenta. En su sitio. | Cuadrao`, the intended Business title. `/personal` serves `Tus finanzas, en orden. | Cuadrao Personal`. Both favicon endpoints return HTTP200 with image content types. Served ICO and SVG bytes match the committed assets. The gray numeral in the founder's Safari screenshot is consistent with a local-host fallback; the Safari-specific cache cause remains unconfirmed because active user interaction prevented a fresh-tab check. No speculative favicon or title change was made.

## Continuation

Existing branch and PR939 remain the delivery owner. Integration remains `43fac94de2672600079f312258908f05747a9d63`, with no new drift. Runtime verification above applies to `d5436b7e861876fea205ac7cdb68ac943702c8fa`; the following evidence-only commit does not alter runtime source. Preview4512 and mock4513 have the fix. Comparison4511 is unchanged. No merge, deployment, hosted change, real email or public-form activation is authorized.
