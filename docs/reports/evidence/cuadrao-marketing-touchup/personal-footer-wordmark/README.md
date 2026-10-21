# Personal footer ends at the cropped wordmark

The founder removed the Personal photo reveal after reviewing the sequence trial. Personal now renders the existing footer links and cropped wordmark without FooterMotion. No footer photos, reveal listener, image swap, playback control, or extra-scroll animation is mounted on Personal. Business retains the existing two-photo reveal.

The route's existing personal property owns this distinction. The unused sequence option and CSS were deleted. The earlier trial remains in Git and its evidence folder as history. No supplied photo assets were deleted because Business still uses them.

The accepted checkpoint tag is unchanged. This local adjustment does not authorize merge, publication, hosted changes, real email, or public-form activation. Resume the existing codex/marketing-touchup-delivery branch and PR #939. Preview is http://127.0.0.1:4512/personal; comparison 4511 is preserved.

Runtime source `2ab403d6df815ea1ff66d792d504564cab44109d`. Production build, typecheck, lint, and diff checks pass. All 30 focused browser checks pass across desktop and mobile-sized Chromium, including both Personal languages and the existing Business footer/header behavior. The parent inspected desktop and phone screenshots and reloaded the in-app browser, confirming zero footer images and zero reveal panels on Personal. Independent scoped review is clean, with no added comments or suppressions. Both agents returned ownership and stopped.

The Business footer capture is byte-identical to the prior trial and baseline capture, with SHA-256 `3e550acce9e4be97c1e16568dd5a08d43e9f06679458b9924271d61801de8098`. No physical Safari/iPhone acceptance is claimed.

[Desktop](screens/footer-es-1440-rest.png), [phone](screens/footer-es-390-rest.png), [source manifest](screens/manifest.json), [browser results](browser-results.txt), and [build results](build-results.txt) preserve this checkpoint. Matching English captures are included.

Reproduce from `marketing/` after building:

```sh
CI=1 MARKETING_E2E_SITE_PORT=4540 MARKETING_E2E_PUBLIC_PORT=4541 MARKETING_E2E_MOCK_PORT=4542 bun run test:e2e e2e/personal-footer.spec.ts e2e/touchup.spec.ts
node scripts/capture-personal-footer.mjs
```

No forms are submitted by these captures. The local preview was restarted with provider credentials unset. Work remains local and unpushed. This source supersedes the photo-sequence trial for Personal only. Subsequent evidence commits retain the same runtime bytes.
