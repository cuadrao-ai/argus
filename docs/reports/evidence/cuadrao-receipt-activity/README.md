# Business receipt activity: local browser evidence

These screenshots show the real local web application with mocked API transport. They do not establish hosted email, WhatsApp, live extraction or customer acceptance.

The Chromium checks use a visible Inbox at 1280 × 900, English with the sidebar expanded and Spanish with it collapsed. They cover saved-unread rows, explicit owner consent, reading rings, completion dots, shared sidebar counts and the five-second completion refresh. The receiving-address fixture is safely disabled. All external requests are blocked.

- `saved-en.png` and `saved-es-419.png`: receipts wait unread for owner consent.
- `reading-en.png` and `reading-es-419.png`: the existing reader is active.
- `ready-en.png` and `ready-es-419.png`: completed receipts remain unread.

Run from `web` with the mock-auth local application on port 3137:

```sh
PLAYWRIGHT_BASE_URL=http://localhost:3137 bunx playwright test e2e/business-receipt-activity.spec.ts e2e/business-receipt-upload-recovery.spec.ts --workers=1
```

Result: four checks passed. The upload checks cover desktop and mobile, same-file/idempotency retry and unsupported-file replacement, without a per-file AI consent checkbox. DOM tests additionally verify visibility, focus, hydration revision, stale acknowledgements and Business-switch cancellation.
