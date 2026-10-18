# Business settings and staging health follow-up

Local verification on October 16, 2026. This packet uses synthetic preview data.
It does not establish hosted acceptance. Root owns independent Eval, exact-head
CI acceptance, merge, and the staging walk.

## Delivered behavior

- Business settings hide Country and currency, archived chats, usage limits,
  and legacy terms/privacy links, including keyboard quick jumps.
- Business general feedback says “Cuéntanos cómo te va con Cuadrao. Leemos cada
  comentario.” It keeps the privacy disclosure and removes More information.
- Business language choices show English once. Personal settings retain their
  current options even when the deployment enables Business.
- Copy address already showed “Dirección copiada.” after clipboard success.
  That implementation is retained; deferred success and rejection now have tests.
- Owner bootstrap reads GET `/business/space`. Only an exact 404 with
  `business_space_missing` permits POST. Permission/server failures never do.
  Selected accountant spaces, shared concurrent initialization, and auth
  generation fences retain their existing owners.
- API and web GET `/health` return full Render `RENDER_GIT_COMMIT` as `git_sha`,
  or null when unavailable/invalid. Web health is dynamic and no-store.

## Source and integration

Initial fetched base: `8b8d3dfa8b10e44e54444d4bd4969876a7472e4f`.
Code changes: `231892117` (health/bootstrap), `7fe86b055` (settings), and
`a92b63d26` (existing country guard test aligned to the approved surface scope).
Failing tests precede their fixes at `3bf50ca62` and `76ea46dbc`.
Integration `bc16c70c8` was merged one-way at `e1697c18f6ffe2e806b37b2d978fabc834afbe59`.
Its migration-history changes do not overlap this lane. No migration is added
by this change.

Shared-file boundaries: `business-api.ts` changes only startup plus its auth
fence import; `ProfileMenu.tsx` changes visibility and quick-jump choices.
Both “Mi negocio” names and naming endpoints remain unchanged. The separate
naming lane needs a fresh overlap review before landing. Provider transport,
Render configuration, and CI scanner files are untouched.

## Browser evidence

The existing `/dev/business-preview?view=inbox` ran on loopback with mock auth
and the repository breakpoint fixture serving synthetic profile responses.
No hosted mutation, customer data, model call, upload, or feedback submission
was used. Screenshots were captured with the in-app browser. Before images
precede the settings fix; after images use `7fe86b055` runtime code. Feedback
was reloaded to fetch the changed locale bundle before the final image.

| Surface | Before | After |
| --- | --- | --- |
| Main settings | [Before](before-menu.jpg) | [After](after-menu.jpg) |
| Preferences | [Before](before-preferences.jpg) | [After](after-preferences.jpg) |
| Language | [Before](before-language.jpg) | [After](after-language.jpg) |
| Data controls | [Before](before-data.jpg) | [After](after-data.jpg) |
| General feedback | [Before](before-feedback.jpg) | [After](after-feedback.jpg) |

[Successful address copy](copy-confirmed.jpg) records the existing status text.
Clipboard rejection is covered by the deferred DOM test, not a browser failure
injection. The browser viewport override did not produce the requested phone
CSS width; this packet makes no mobile-width acceptance claim. The override
was reset and the lane's tab and preview processes were closed.

## Local checks

- Full web suite: 2677 passed, 0 failed, 277 files, 19467 expectations.
- Web webpack production build: passed, including TypeScript and dynamic health.
- Focused health/bootstrap: 21 passed; auth ownership: 4 passed.
- Settings/shared-shell/email tests: 21 passed. Country/settings rerun: 11 passed.
- API health metadata: 7 passed (valid, absent, malformed and newline metadata).
- Python Ruff check/format, modularity budget, and changed documentation links pass.
- Required mocked Python harness was attempted with provider keys empty.
  Nine runnable modules plus health produced 242 passes and 2 failures from the
  local SciPy PROPACK binary loader. Trajectory collection has the same error.
  A lane-local exact-lock SciPy 1.15.3 wheel still fails with a nonzero offset
  in `__DATA/__thread_bss` for `_spropack`. Shared environments were not changed.
  Linux CI must supply the complete mocked/backend result.
- The API import-boundary subprocess suite cannot see the lane-local dependency
  overlay because it replaces PYTHONPATH; it remains a CI gate.
- A raw standalone web tsc command reports existing test-environment type errors;
  the production Next build's TypeScript check passes.

## Review and rollback

The canonical absence fact is the server's typed missing-space response, not
browser storage or a missing membership list entry. This preserves revoked
access errors and first-time creation idempotency. The surface context supplies
Business visibility, not the deployment feature flag.

No new persistence, permissions, model instructions, service settings, or paid
calls are introduced. Roll back this PR to restore the previous settings and
bootstrap behavior. Root must record final-head CI and hosted health SHA probes
before reporting staging completion.
