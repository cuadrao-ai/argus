# Personal signup pet and phone

Current visual source `d81766f0b371d427f7346cdf1b8dcc1de052ca97` (initial scene `c8eab10647c56a49591033f5e5a026bb8a5befa6`), October 9, 2026. Founder requested keeping the left-hand copy and signup, replacing the Home preview with a hand-held phone showing the native welcome screen, and adding a square pet that watches the cursor and delivers an envelope after signup succeeds. The founder chose the welcome screen with the logo and signup button. The founder locked the visual baseline in the [accepted checkpoint](../accepted-design-checkpoint.md). The subsequent copy cleanup and pending footer refinement do not imply release approval.

## Behavior

The original code-native hand holds a composite welcome preview on the right. The black silhouette, slimmer fingers, silver phone edge and fading wrist follow the founder-provided Base reference. The screenshot file remains unchanged; an HTML overlay replaces its old wordmark with the canonical header SVG, `cuadrao-lockup-light.svg`. This is a Marketing composition, not a native-app change. The pet peeks from the email field, follows fine pointers with its eyes, and becomes excited during submission. A successful registered response starts one 1.1-second flight. The envelope leaves the CTA and the pet hops with it toward the central phone logo. A ripple marks arrival and the pet settles there. Confirmation appears and receives focus immediately. Errors and unexpected responses preserve the email and produce no flight. Signup request, persistence, privacy and duplicate behavior remain unchanged.

The Model the Domain principle kept SignupState as the only owner of request truth. Decorative state contains measured positions only. The parent and independent design judge selected the smaller CSS animation sketch after comparing two designs. See [decision](design-decision.md), [candidate A](design-a.md), and [candidate B](design-b.md).

Mobile stacks the phone below the intake. A flight is skipped if its destination is offscreen. No decorative auto-scroll occurs. Fine-pointer eyes reset on pointer exit and keyboard navigation. Reduced motion skips eye movement, bounce and flight. Scrolling, resizing or changing motion preference settles an active flight. A visual review caught a 39-pixel headline shift during confirmation; explicit grid rows remove that shift and a browser assertion guards it.

## Asset provenance

The welcome image is copied unchanged from `docs/reports/evidence/cuadrao-release-ui/2026-10-03-w1/release-design-launch-light.png`. Source dimensions are 1320×2868. The [native evidence](../../cuadrao-release-ui/README.md) records the October 3 simulator design capture. It is historical design evidence, not a claim about the current shipping app. The original preview caption was removed at the founder’s request during final copy polish. This evidence retains the historical asset provenance; the phone is a Marketing composition, not a shipping-app claim.

Served asset `marketing/public/cuadrao-site/personal-welcome-preview.png` has SHA-256 `8dc8c6e298742c0bfcec5261a1d4f79d93d4d2733ca46b1a2bc6356b23b22f7c`. The hand, pet and envelope are original SVG/CSS graphics. No Base artwork was extracted. The native logo was not redrawn. Consumer files, app services and simulators were not modified or launched.

## Verification

- Fresh production build, Marketing typecheck, lint and diff checks pass.
- 33 Personal signup/motion browser checks pass. One pointer-only test is intentionally skipped in the touch project. Tests cover delayed response gating, success and natural settlement, duplicate signup, unavailable storage, unexpected responses and retry, focus, pointer tracking, scroll cancellation, reduced motion, 320/390-pixel layouts, privacy and pre-hydration behavior in both languages.
- Four focused automated WCAG 2.1 AA checks pass for Personal in ES/EN on desktop and mobile.
- The parent inspected final desktop/mobile screenshots and in-flight/settled captures. Independent scoped implementation review and the final layout-delta review are clean, with zero actionable findings, comments to remove or suppressions.
- [Browser results](browser-results.txt), [accessibility results](accessibility-results.txt), [build results](build-results.txt), and [exact-source capture manifest](screens/manifest.json).
- [Desktop idle](screens/personal-es-1440-idle.png), [desktop flight](screens/personal-es-1440-flight.png), [desktop settled](screens/personal-es-1440-success.png), [mobile](screens/personal-es-390-idle.png), and [short demo recording](screens/personal-signup-demo.webm). Matching English screenshots are in the same directory.

The recording and screenshots intercept the browser's signup request with a registered fixture. No request reaches the signup server or a provider. These demonstrate animation, not a real registration. The existing signup suite separately exercises storage with its mock provider. No physical iPhone/Safari acceptance is claimed.

## Continue safely

Resume `codex/marketing-touchup-delivery` in the existing Marketing worktree with PR #939. Updated preview is `http://127.0.0.1:4512/personal`, with real provider credentials unset. Comparison 4511 remains preserved. The subsequent documentation/evidence commit changes no Marketing runtime source. No push, merge, hosted change, publication, public-form activation or real email occurred. All workers have handed back ownership.

From `marketing/`, after building, use isolated test ports:

```sh
CI=1 MARKETING_E2E_SITE_PORT=4540 MARKETING_E2E_PUBLIC_PORT=4541 MARKETING_E2E_MOCK_PORT=4542 bun run test:e2e e2e/personal.spec.ts e2e/personal-motion.spec.ts
CI=1 MARKETING_E2E_SITE_PORT=4540 MARKETING_E2E_PUBLIC_PORT=4541 MARKETING_E2E_MOCK_PORT=4542 bun run test:e2e e2e/site.spec.ts --grep 'personal.*automated WCAG'
bun run scripts/capture-personal-pet.mjs
```

Keep current forms disabled from real providers until the founder approves activation. Use the live local demo or saved recording to review successful delivery.


## Live local demo follow-up

The founder asked for the closer hand, current website wordmark inside the phone and a live mock submission. Open `http://127.0.0.1:4513/personal` (or `/en/personal`), enter `demo@example.test`, submit, then use **Repetir / Replay**. The persistent bilingual badge identifies the simulation. The normal confirmation text is also simulated on this port. Nothing is saved or sent. Desktop shows the full journey when both the pet and destination are visible; reduced motion and offscreen destinations still skip travel.

Run from `marketing/` while the provider-disabled 4512 preview is running:

```sh
node scripts/personal-demo.mjs
node --test scripts/personal-demo.test.mjs
```

The demo binds only to `127.0.0.1:4513`. Only its same-origin POST `/api/signups` produces a delayed registered fixture. It discards request bytes, blocks other mutations/API routes and proxies page/assets to fixed loopback 4512 without cookies or authorization. No production form code or provider configuration changed. The Model the Domain principle retained SignupState and Flight; the demo boundary owns simulated responses.

Verification for this follow-up: typecheck, lint, fresh production build, one real-HTTP boundary test, 33 signup/motion tests and four accessibility tests passed. One pointer-only check is intentionally skipped for touch. These browser checks ran at `f354c0218`; the final delta `787297077` only moves decorative SVG coordinates and retains that behavioral evidence. A fresh final build and exact-source screenshots/clip cover the final visual change. Independent full-delta and final SVG-delta reviews were clean, with no comment flags. The in-app browser submitted the local fixture, showed confirmation and reset to an empty form through Replay. No provider request was involved.

Process checkpoint: final preview PID 2188 on 4512; demo PID 1265 on 4513. Verify the PID and cwd before any later restart. Original comparison PID 11951 on 4511 remains untouched. These are observations, not stable process identifiers. All delegated agents returned ownership and stopped. Work remains local and unpushed; this is not a release/readiness claim.


## Reference geometry correction

The founder clarified that the previous black silhouette still missed the reference phone angle and hand shape. Source `2e0cb71b84779b73d7f6b1d2d8ee8a24bce879bf` reconstructs both in one 480×820 frame against the [supplied reference](founder-hand-reference.png). The front phone has a rising top edge (8 pixels over 280 in that frame) and its bottom shifts 44 pixels left over its height. A separate silver side provides depth. The thumb, continuous palm, curled fingers and diagonal wrist now follow the supplied silhouette; the middle finger reaches farther across the screen. The native welcome image remains a Marketing composite with the current canonical header artwork and is fitted to the narrower reference screen. This is a close visual reconstruction, not a pixel-identical copy of the full Base page.

Parent desktop/mobile inspection caught and fixed a bezel painting seam and a gap below the phone. Final independent delta review is clean. Fresh build, typecheck and lint passed. Thirteen focused motion checks passed with one intentional touch skip at `ebf674df6`; the final painting-only changes preserve that behavior. Final exact-source ES/EN desktop/mobile captures and the recording have been refreshed. The in-app browser confirmed the new transform is loaded. The form and motion state owners are unchanged; the target still derives from the transformed logo position. See [motion output](reference-motion-results.txt). Both 4512 preview and 4513 mock use the corrected scene. No other lane or comparison changes occurred. Prior process IDs are historical; use `lsof` and verify cwd before stopping anything.


## Reader-facing angle refinement

The founder approved retaining the current hand and turning the phone slightly toward the reader. Source `fbc064e0da41be93bfbdb1201e76031d1a915578` changes only the phone CSS: mild 3D perspective, a smaller shear, and a slimmer silver side. Hand paths, form, branding and motion logic are unchanged. Fresh build and 13 focused motion checks passed, with one intentional touch skip. Final desktop/mobile ES/EN images and the clip pin this source. The parent visually inspected the render and refreshed the in-app preview. See [angle motion results](reader-angle-motion-results.txt). Both 4512 and the 4513 mock serve this version; reload an existing tab. This approved, contained CSS adjustment was implemented directly and does not claim a separate independent review. No publish, push, provider or other-lane changes.


## Phone slogan removal and brand parity

The founder requested removing the phone slogan because the middle finger covered it, and asked about the color difference between the central icon and the icon beside the name. The central artwork was baked into the historical native capture; the name already used the current canonical lockup. Source `1c4dca80a512919a523fc9649c8ccd1f96fa8539` clears the old central icon and slogan in the rendered Marketing composition, then overlays `cuadrao-mark-light.svg` from the same canonical brand source as the header lockup. The dark green, pale green and lime overlap now agree. No colors or logo geometry were recreated. `sync-brand.mjs` derives both served SVGs from `marketing/brand/`; the native PNG remains unchanged on disk.

The central image and flight anchor derive their center from the same `welcome.logo` coordinates. Hand, angle, form, native welcome buttons and motion logic are unchanged. Typecheck/lint/build pass; 15 existing brand tests pass. Final ES/EN desktop/mobile idle, pending, flying and settled captures/clip pin this source, with no page errors. The parent verified that the slogan and old mark are fully covered, the current icon loads and the welcome buttons remain visible. Independent scoped review is clean with zero comment/suppression flags. Prior motion evidence is retained for the unchanged state/geometry behavior. This is Marketing-only; no native or hosted update is implied. Preview 4512 and mock4513 remain available; comparison4511 is preserved. Workers have returned ownership and stopped.


## Personal copy cleanup, October 9, 2026

Runtime source `d81766f0b371d427f7346cdf1b8dcc1de052ca97` removes the design-review caption beneath the phone and the duplicate saved-email explanation. The invitation and confirmation are shorter in ES and EN. Early-access status, privacy, error handling and signup truth remain intact. The separate 4513 simulation retains its badge and Replay control because it does not save registrations. No footer changes were made; the founder will provide a clip for the image reveal below the cropped wordmark.

Fresh build, typecheck, lint and diff checks pass. The focused signup/motion suite passes 33 checks with one expected pointer-only skip on touch. Independent scoped review is clean. Desktop/mobile ES/EN captures and the clip were refreshed at this exact runtime source; the parent inspected the rendered success view and verified the regular preview copy in the browser. [Copy browser results](copy-polish-browser-results.txt) and [copy build results](copy-polish-build-results.txt) record this pass. Earlier accessibility evidence is retained across this text/removal-only change, not claimed as a new run.

The accepted tag `codex/marketing-design-checkpoint-2026-10-09` remains unchanged at `0a026651060576a0e359efd5f2b868c70222e556`. Continue on the existing branch/worktree. Preview 4512 was rebuilt with providers unset; mock 4513 remains separate and comparison 4511 is preserved. No push, merge, deployment, hosted change, real email or public-form activation occurred. Both delegated copy agents returned ownership and stopped.


### Signup demo synchronized with final branding

Current capture source `ece1aa067f6c810dd349fb57742a4eb0bd235ee9`. Refreshed screenshots and clip use `http://127.0.0.1:4513` and include its simulation badge. Capture responses are intercepted fixtures; the real local proxy submission and Replay were separately verified in the in-app browser. The demo proxies the current4512 build, so footer branding, favicon and the accepted hand/phone scene stay in sync. No email is saved or sent.


### Phone language correction

Runtime `d5436b7e861876fea205ac7cdb68ac943702c8fa` localizes the phone CTA labels through the page locale. See [verification and tab identity notes](locale-check/README.md). The refreshed demo and screenshots include this correction.


## Gentle invalid-email reaction, October 9, 2026

Runtime source `0455fa4c2a7795064ea85b75879c83b09eec52e6` adds one small tilt and blink when an empty or malformed email is submitted. The pet looks toward the field and the existing localized error explains the correction. Typing alone does not trigger rejection. A valid correction clears the error and restores the normal pose. Service and network failures retain the calm pose; reduced motion shows a still expression. Native email constraints own local validity, and the existing SignupState rejection owns the pet expression. This applies the Model the Domain principle without adding a second validation state or parser.

The 4513 demo consumes the same 4512 page assets. Try `oops`, submit, then correct to `demo@example.test` and submit again. Replay resets the form. No email is saved or sent. The [updated clip](screens/personal-signup-demo.webm) includes rejection, correction and simulated success. The [capture manifest](screens/manifest.json) pins the source; desktop/mobile ES/EN screenshots include the invalid state. Parent visual inspection confirmed the inline error, field focus and small pose change at both sizes.

Build, lint, typecheck and the demo HTTP boundary test pass. [Focused browser results](invalid-email-browser-results.txt) show 49 passing tests and one intentional touch/pointer skip. The first run exposed a test locator that also matched Next.js's route announcer; scoping it to the signup hero fixed the test without changing runtime behavior. Independent runtime review returned no findings. All workers returned ownership and stopped.

This reaction is a local checkpoint for founder tryout. It has not been pushed; PR939 remains at `781e820f5986e1d009bbfb2fb61ffd6ea6912d56`, whose earlier CI passed. No new CI claim applies to this local delta. Preview4512 PID56318 and fixture-only4513 PID1265 are current observations; verify listeners before restarting. Comparison4511 remains untouched. Deployment, hosted changes, public forms and real email remain on hold.
