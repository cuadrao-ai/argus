# Cuadrao marketing touch-up review

## Current final polish

The authorized PR update includes footer icon-and-wordmark branding and the current favicon. [Old layout source and screenshots](original-layout-archive/README.md) remain available for inspiration. Deployment and public forms stay on hold.

Personal is accepted and [locked](personal-accepted-checkpoint.md). [Final polish and replacement readiness](final-polish/README.md) is the current continuation authority. Business editorial people photos are removed; both pages now end at the static cropped wordmark. Historical photo/reveal descriptions below are superseded.

## Scope and holds

This work moves the proposed spacious touch-up into the maintained Next.js marketing app. The founder accepted the progress so far as the [locked design baseline](accepted-design-checkpoint.md). Personal now ends at the [cropped wordmark](personal-footer-wordmark/README.md), as requested after the photo-sequence trial. The final local polish pass is complete; launch gates remain in the report above. Passing tests do not establish final replacement or launch approval. The current ownership and resume point are in the [Marketing handoff](../../../handoffs/cuadrao-marketing-launch-lane.md). Business, Personal, Contact and Privacy remain available in Spanish and English. Shared routes, form handlers, privacy text and consent logic remain the existing canonical implementations. No iframe or comparison-server dependency remains.

The new text is a draft for founder review in [copy-review.md](copy-review.md). No merge, publication, hosted migration, Render service, provider secret, real email or domain action is authorized by this report. Public forms and the operator section retain the LLC/operator hold. A local start without provider configuration reports unavailable and cannot send mail.

Original integration base: `bbf4da23f01296af4ac639386fe9a0960218a49f`. Branch: `codex/marketing-touchup-delivery`.

## Founder correction, 2026-10-09

The founder requested removal of the incomplete Business product screenshot because its numbers were incorrect. The Marketing page no longer renders that section in either language. Its localized copy, unused styles, and served `business-review.webp` asset are removed. Historical evidence images remain here for traceability.

The earlier screenshots and browser results below describe the previous page. They do not verify this removal or establish design approval. The removal passes TypeScript, lint, and 40 focused unit tests covering existing sample money, priorities, and routes. The rebuilt page passes all 20 focused browser checks on desktop and mobile. That removal left header and footer behavior unchanged. The separate footer correction below supersedes the previous motion design.

## Footer correction, 2026-10-09

The founder confirmed that footer photos must be fully hidden at rest. The natural page ending remains the existing cropped hollow Cuadrao wordmark. Extra downward wheel or touch input at the page bottom briefly reveals a bounded photo strip; stopping input returns it to the crop. There is no added scroll height, autoplay, moving grid, pause button, scroll lock, or forced scroll correction. Upward scrolling and keyboard navigation remain native. Reduced motion keeps the static crop.

The implementation uses one reveal offset on a clipped track containing the footer content and an absolutely positioned photo strip. Moving the content together prevents a second crop across the top of the wordmark during the peek. The rendered photo strip bounds the reveal at 120 to 200 pixels according to screen width. Native overscroll alone was rejected because it cannot consistently expose custom clipped photos across browsers.

The founder supplied replacement footer photos during this correction. The dressmaker appears on the left and the artisan on the right. Original files are copied unchanged; Next/Image owns responsive delivery, and CSS crops toward the upper body without stretching. The release captain inspected the final crop. Founder visual acceptance remains pending; the later header direction is recorded below. The main editorial florist/accountant images remain unchanged.

Typecheck, lint, and a fresh production build pass. All 20 focused browser checks pass on desktop and mobile. They cover resting crop, wheel peek, idle return, fixed document height, upward wheel departure, keyboard navigation, reduced motion, both languages, and dispatched touch drag/release. The first run caught the hidden photos remaining unloaded because they were lazy-loaded. Both footer images now load eagerly through the existing Next.js image optimizer; the rerun passes. Dispatched touch events test the handler; they do not prove physical iPhone overscroll behavior. The release captain reviewed the bounded diff and verified the rebuilt preview. No founder design acceptance, new GitHub CI verdict, or release readiness is claimed.

`marketing/scripts/capture-touchup.mjs` now writes to `footer-peek-screens/` and captures rest, peek, and settled states. It preserves the historical `screens/` images and manifest. Existing screenshot and test evidence below does not validate this correction.

## Header and drag refinement, 2026-10-09

The founder authorized **Cómo funciona** and separate language controls, and requested lighter footer drag after checking [Granola](https://www.granola.ai/). Direct browser inspection confirmed that Granola readily exposes a shallow photo band on extra scroll and returns after input stops. Only the interaction informed this refinement; no reference assets were copied.

The header now uses **Cómo funciona / How it works** from one localized navigation field on desktop and mobile. ES/EN has its own outlined group, filled current selection, and 44-pixel minimum targets. Language links preserve the current page, and the navigation link retains its existing product-section destination.

The footer previously added each input to a still-animating rendered position, losing movement between frames. It now accumulates the requested displacement, uses 0.75 input gain instead of 0.35, waits 240 ms after the last wheel input, and returns over 500 ms. A held touch stays open until release. The existing photo-strip height still bounds the peek. Photos remain fully hidden at rest; reduced motion and native upward/keyboard scrolling remain intact.

Verification against source `80cb9aca17b8a3789ea32f121928af1b48226484`:

- Typecheck, lint, fresh production build, and diff checks pass.
- **26 focused browser checks pass**, including both languages, mobile menu Escape/focus, navigation destinations, language-control target size, gentle wheel accumulation, held touch, idle/release return, fixed page height, reduced motion, and 320-pixel overflow checks.
- **2 existing same-page language-switch checks pass**, desktop and mobile, on Contact.
- Parent reviewed the implementation diff and screenshots at 1151, 1200, and 1440 pixels, plus the 390-pixel menu and footer peek/settled states. No actionable finding remained in this bounded review. Dispatched touch tests do not establish physical iPhone behavior.
- [Screenshot manifest](header-drag-screens/manifest.json), [desktop header](header-drag-screens/header-1440.png), [mobile menu](header-drag-screens/header-mobile-menu.png), [peek](header-drag-screens/footer-peek.png), [settled](header-drag-screens/footer-settled.png), and [browser log](header-drag-results.txt). The capture script now writes `header-drag-screens/`; both previous evidence folders are preserved.
- Preview 4512 was rebuilt with real form-provider credentials unset. Original comparison 4511 and its listener PID 11951 were preserved. Implementation and evidence are local commits on the existing branch; no push, merge, hosted change, or publication was performed.

The later evidence commit changes only documentation and images, so runtime source is identical to the manifest. Whole-page founder design acceptance remains pending. This is a local review result, not a READY or GitHub CI claim.

## Scroll-driven receipt story, 2026-10-09

The founder approved a section that holds through Recibir, Revisar, and Aprobar, then releases the page. They also asked whether the entire page should tell a larger scroll story. The current recommendation is one primary receipt transformation with quieter surrounding sections, adding another sequence only when there is another concrete product story. This change does not expand whole-page motion or alter product claims, sample amounts, or development disclosures.

The implementation uses native document scrolling and CSS sticky, the pattern demonstrated by [Scrollama's sticky example](https://russellsamora.github.io/scrollama/sticky-side/). No Scrollama dependency was added. Scroll position owns both the active chapter and continuous rail fill. Each chapter spans half a viewport; the final interval gives time to read before release. Upward scrolling reverses the sequence. Click and arrow-key shortcuts move to the chosen chapter, and passive scroll never moves focus. There is no wheel interception, forced snapping, or autoplay.

Desktop holds the full introduction and receipt scene. Phones let the introduction scroll away and hold only the rail, disclosure, and receipt below the header. A fit check measures the tallest card and removes the added runway when content cannot fit. Reduced motion retains ordinary manual tabs, consistent with [W3C reduced-motion guidance](https://www.w3.org/WAI/WCAG22/Techniques/css/C39.html). The initial visual review found a partially clipped mobile heading; a separate mobile stage and regression coverage resolved it before final capture.

Verification against source `5c3c2d4a41ea2a1d1d76244b0158a1c32f28e805`:

- Fresh production build, typecheck, lint, and diff checks pass.
- **42 focused browser checks pass** across desktop and mobile: ES/EN forward and reverse progression; all three stages; final-stage hold and page release; native wheel input; click/keyboard shortcuts; focus preservation; 390-pixel anchor entry and resize; 320-pixel readability; short landscape and reduced-motion fallbacks; existing header, footer, and withdrawn-screenshot checks.
- The release captain inspected desktop and phone captures, including both languages. A final read-only review of the mobile delta returned clean, with no actionable findings. All delegated writers returned ownership; no agent has an active follow-up.
- [Screenshot manifest](scroll-story-screens/manifest.json) pins this source. It includes all three stages in ES/EN at 1440×900 and 390×844, plus the short-height manual fallback. [Desktop review stage](scroll-story-screens/story-es-1440-2.png), [phone review stage](scroll-story-screens/story-es-390-2.png), and [English phone approval](scroll-story-screens/story-en-390-3.png).
- [Browser results](scroll-story-results.txt) and [build results](scroll-story-build.txt). Headless Chromium and dispatched touch coverage do not establish physical iPhone/Safari behavior.
- Updated preview 4512 serves this build with real form-provider credentials unset. Comparison 4511 and its listener PID 11951 are preserved. No Business or Consumer files/services changed. No push, merge, publication, hosted change, or real email occurred.

Reproduce from `marketing/` after building:

```sh
CI=1 MARKETING_E2E_SITE_PORT=4540 MARKETING_E2E_PUBLIC_PORT=4541 MARKETING_E2E_MOCK_PORT=4542 bun run test:e2e e2e/capture-story.spec.ts e2e/touchup.spec.ts
bun run scripts/capture-story.mjs
```

Only the Marketing preview may be stopped for a rebuild, after verifying its process working directory. Preserve comparison 4511. The subsequent evidence commit contains documentation and captures only; runtime source is identical to the manifest. Continue on `codex/marketing-touchup-delivery`, retaining PR #939 and the original integration base recorded in the handoff. This is a local design iteration, not a READY, current GitHub CI, or whole-page founder acceptance claim.

## Personal pet and phone, 2026-10-09

The founder requested a more playful Personal intake with a hand-held native welcome screen and a square pet delivering an envelope. The [Personal evidence record](personal-pet/README.md) owns the design decision, asset provenance, exact-source screenshots, mock-response recording, 37 passing checks and one touch-only skip. Source is `c8eab10647c56a49591033f5e5a026bb8a5befa6`. This supersedes prior Personal screenshots. Founder visual acceptance remains pending.

## Historical reference decisions

Both founder-provided recordings were inspected directly, frame by frame:

- Granola, recording `2026-10-09 at 12.41.17 AM`: a shallow image band under the oversized cropped footer wordmark. Adapted as a bounded 200 px desktop / 150 px mobile ending, not another full-screen section.
- YC, recording `2026-10-09 at 12.44.04 AM`: thin moving grid lines, corner squares, cropped type. Adapted to Cuadrao pine, sage and lime. No reference logos or footage are reused.

The previous footer started moving when visible, paused off screen, and had an explicit pause control. That design is superseded by the founder correction above. Its historical evidence remains below.

The original hero card behavior is a 2 degree resting rotation to 1 degree on hover over 220 ms. The maintained touch-up uses that same behavior; there was no separate shake keyframe in the source.

The document journey uses a keyboard-operable three-tab progress rail. The pilot sequence remains an ordered list with a connecting rail. Numerical prefixes are removed.

## Asset provenance

- Header lockup: canonical `marketing/brand/cuadrao-lockup-light.svg`. `marketing/scripts/sync-brand.mjs` derives the served copy during dev/build.
- Florist and accountant images: founder-provided illustrative images, recovered from the prior approved touch-up assets, already optimized as WebP. The page labels them as AI illustrations, not customers.
- Footer dressmaker: founder-supplied `codex-clipboard-123a87f8-93d2-4fef-be87-24e3c1fa6ed2.png`, copied unchanged to `marketing/public/cuadrao-site/footer-dressmaker.png` (1456×1360).
- Footer artisan: founder-supplied `grok-image-064f7fef-226b-4166-92db-7e8aa4579b64.jpg`, copied unchanged to `marketing/public/cuadrao-site/footer-artisan.jpg` (1728×1152). Neither image is asserted to depict a customer.
- Withdrawn Business product image: historical local synthetic capture, removed at the founder's request. The source evidence below remains for traceability.
- Founder portrait, signature, Personal screen and footer artwork retain the canonical existing assets.

## Reproduction

From `marketing/`, install the pinned lockfile with `bun install --frozen-lockfile`.

```sh
bun run test
bun run typecheck
bun run lint
bun run build
CI=1 MARKETING_E2E_SITE_PORT=4540 MARKETING_E2E_PUBLIC_PORT=4541 MARKETING_E2E_MOCK_PORT=4542 bun run test:e2e
bun run start --hostname 127.0.0.1 -p 4512
```

The browser suite supplies mock provider configuration and synthetic addresses. It covers validation, success, unavailable and retry states without sending real messages. The environment-variable overrides isolate its three servers from the founder's comparison and Business servers. Default CI ports are unchanged.

The comparison page on 4511 is a separate preserved snapshot. The touch-up does not fetch any assets or content from it.

## Verification record

Implementation commit: `85c8cdf2a17c4a8dc6ff2990b75d6d44451cc40e`. Test-only pause synchronization: `fc1c3a0c40aae17075228674f330ef3a10d7170c`.

- 177 unit tests pass; typecheck, lint and fresh production build pass.
- Final complete browser matrix: **142/142 pass**, desktop 1440 px and touch/mobile 390 px, plus all routes at 320 px with reduced motion. Includes form validation, mock success, unavailable/retry, canonical routes, keyboard navigation, image loading and automated WCAG 2.1 AA checks.
- Footer pause repeated three times per desktop/mobile: **6/6 pass**. The initial test measured before React applied the pause and saw one frame of movement; the final assertion waits for the rendered paused state and still verifies a fixed position.
- Independent focused code/UI review and final delta review: **clean, no actionable findings**. No unchanged runtime was opened for speculative work.
- Modularity budget: no violations. Integration remained `bbf4da23f01296af4ac639386fe9a0960218a49f`; no reconciliation merge or semantic overlap was needed.
- [Screenshot manifest](screens/manifest.json) pins the actual product implementation commit and capture time. The later commit changes only test synchronization; product source is identical, so these images described that earlier revision. The Business page images are now historical after the removal above. The final evidence commit changes documentation/images only.
- [Desktop Business](screens/business-es.png), [390 px Business](screens/business-es-390.png), [320 px Business](screens/business-es-320.png), [Personal](screens/personal-es.png), [Contact](screens/contact-es.png), [Privacy](screens/privacy-es.png). Matching English images are in the same directory.
- [Footer first frame](screens/footer-motion-start.png), [later frame](screens/footer-motion-later.png), [paused state](screens/footer-paused.png).

Hosted checks and publication are not part of this local acceptance. GitHub CI and founder copy approval remain separate gates.

### Withdrawn Business image provenance

The Business runtime owner captured `business-inbox-source.png` and `business-review-source.png` at 1440×1000 from the running local `/biz` app on October 9, 2026, checkout head `d136c3394`. It used a separate synthetic account, Spanish profile and an actual saved fixture upload (`receipt-dop.png`). AI preparation was off. The review form is intentionally unfilled and the receipt is not claimed to be an approved expense. No DOM text was replaced and no owner account was changed. The former served image was a browser viewport clip of the receipt/review area so the product stays readable and development chrome stays outside the frame.

The focused browser log is [footer-peek-results.txt](footer-peek-results.txt). The updated preview runs on 4512 with real form-provider credentials unset. The original comparison on 4511 is preserved.

Visual verification found a native browser edge bounce competing with the custom peek. Marketing now disables the native vertical edge effect through CSS while keeping normal scrolling. The final photo crop uses `center 20%`. The focused suite passes again after this correction. The removed screenshot URL returns 404, both previews return 200, and the original comparison listener remains PID 11951.

### Current visual evidence

[The new manifest](footer-peek-screens/manifest.json) pins runtime source `f98974687caecc01c24786007e448754a782d1a2`. [Rest](footer-peek-screens/footer-rest.png), [peek](footer-peek-screens/footer-peek.png), and [settled](footer-peek-screens/footer-settled.png) show the new ending. Business, Personal, Contact, and Privacy captures cover both languages, plus Business at 320 and 390 pixels. The final evidence commit changes no runtime source. These local review artifacts do not establish founder design approval.


Personal hand and live mock follow-up: final visual source `7872970775ffdd4b92deeb9b43fe3586b6ea43ba`. The [Personal evidence](personal-pet/README.md) records current header artwork in the phone, the reference-style black hand, updated screenshots/clip and safe live demo at `http://127.0.0.1:4513/personal`. No email is saved or sent by that demo.
