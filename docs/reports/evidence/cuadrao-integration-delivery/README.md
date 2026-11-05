# Cuadrao integration delivery

This evidence covers the English and Spanish Business, Personal and contact pages. It verifies an integration preview, not public launch readiness. The website remains default-off and noindex. Business examples use fictional records. Contact only prepares a local review. Personal signup returns HTTP 503 without saving an address. Supabase capture is tracked in #882.

## Candidate and evidence

Original integration base: `ad7eb9ccb8261456d12ce5a26686682bbce9ae2f`.
Initial verified web tree: `2e29861249b9818d46e866dd069582424c932c5c`.
The PR and independent review record identify the final head. The initial tree binds the broad matrix to its source. The final privacy fix changes only Personal hydration and fieldset styling; its affected layouts and form paths were reverified below. The final tree is recorded in the PR terminal audit.

All captures were taken on October 7, 2026 against a production Next.js build. Local preview was enabled on port 3223 and disabled on port 3224. No hosted changes, provider turns, real financial records or messages were used.

## Results

- Frontend lint passed with eight existing warnings and no errors.
- All 2,249 frontend tests passed (17,613 assertions).
- Production build and its TypeScript check passed.
- Signup endpoint test passed. The actual browser receives unavailable status, retains the entered test address and shows an error; it never claims a saved registration.
- Browser storage disclosure regression passed, two tests.
- Modularity budget passed against the combined tree; integration was an ancestor at capture time.
- [Header results](header-results.json): six routes at four widths, no overlaps or overflow, inline back arrow, correct locale destination and Escape behavior.
- [Owner examples](owner-results.json): 80 selected states fit, with currency separation, cash scenario arithmetic, five capture examples, reviewed proposals, search return, updates, receipt and invoice checks.
- [Presentation](presentation-results.json): 24 layouts, five FAQs, valid anchors, mobile form order, no broken images, locale sharing metadata, honest form states, reduced motion and no page errors.
- [Boundary checks](boundary-results.json): 22 enabled/disabled route checks; existing development-route block and legal pages preserved. English app preference survives Spanish and English marketing pages and the return to the app.

Independent browser comparison confirms identical existing home/legal and synthetic public-receipt content against integration, including JavaScript-disabled receipt rendering. Enabled Spanish app preference also survives both marketing languages and the return to the app. The independent PR verdict records these checks and the final fix review.

## Privacy fix verification

The reviewer reproduced a native GET that placed an email in the Personal URL without JavaScript. The form now stays disabled until hydration and declares a POST action. [Before](hydration-red.txt), the two Personal no-JavaScript cases fail while four contact/hydrated cases pass. [After](hydration-green.txt), all six pass. The test lives at `web/e2e/business-form-hydration.spec.ts`; run it with `CUADRAO_WEBSITE_PREVIEW=true` and the production preview as `PLAYWRIGHT_BASE_URL`.

[Eight final Personal layout checks](personal-results-final.json) pass on the production build of source commit `405ee5e5b`; the affected Personal screenshots are refreshed. The original header, Business, contact and owner-example evidence is retained because those runtime files did not change. The final full frontend suite remains 2,249 passed. No JavaScript-free form submission or successful signup is claimed.

## Visual samples

- [Business desktop](business-en-1440.png) and [phone](business-es-390.png).
- [Personal phone](personal-en-390-full.png).
- [Contact desktop](demo-en-1440-full.png).
- [Founder note](founder-es-1440.png).

The adjoining scripts reproduce the checks with Playwright CLI. Set their output directory to your checkout before running. Source-to-page coverage is recorded in the [coverage matrix](../cuadrao-owner-vision/coverage.md).

## Remaining public-launch work

- #880 owns public routing, cuadrao.ai configuration, indexing, privacy and end-to-end launch verification.
- #881 owns Business inquiry delivery.
- #882 owns Personal early access through existing Supabase. SQLite and its operator tooling are excluded from this PR.

These issues remain open. Integration merge does not activate the website or make the product examples available as a live Business app.
