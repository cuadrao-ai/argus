# English Personal waitlist draft

Iris approved the English copy through Lucas on October 16, 2026, with the
success detail explicitly stating that the email is in Spanish. Root owns the
new head's independent exact-head Eval, CI, integration and staging. This record
proves local behavior with explicit CAPTCHA and provider fixtures. It does not
prove live Turnstile acceptance, hosted delivery or permission to publish.

## Scope and ownership

`PersonalEarlyAccess` renders one form for both locales. English uses the existing
Spanish expense values with translated visible labels. The request shape and
server remain unchanged. `WaitlistCaptcha` receives the page locale for its
widget language. Its script, action, config request and callbacks stay shared.

The header's existing `#early-access` anchor now reaches the English form. The
hero action submits that form without leaving `/en/personal`. Privacy links to
`/en/privacy`. The Business link reads exactly "Is it for your business? Contact
us" and links to `/en/contact`.

The current Spanish confirmation, reminder, welcome and later launch email
content remains the owner of email wording. This draft adds no English email,
locale storage, migration, send, scheduler or legal change. Spanish form wording
and behavior stay intact. Footer and global styles belong to other writers.

## Proposed copy

[The complete copy-review table](COPY_REVIEW.md) lists each English string and
its Spanish counterpart. The table includes existing introduction and phone
labels, new form states, links and validation text.

## Verification and detection

Before implementation, the navigation browser regression failed because the
English email field did not exist. After implementation, the Personal form,
waitlist and motion tests passed in desktop and mobile browser projects.
The new tests check English labels, option payload values, privacy and contact
links, warning, success focus, no JavaScript, duplicate registration, retry,
honeypot no-write behavior, CAPTCHA expiry and error callbacks, and Spanish
email delivery through local mock providers.

The local package passed lint, TypeScript, its production build and 212 unit
tests. Four existing database-dependent tests were skipped. No server or data
change requires new database proof in this presentation-only draft.

Original integration base was `4599d7dc7d2ba0f6ba80af87350b3a92113a11c5`.
Integration advanced to `c35aef09a487c3961c176df42364fe6ded092c33` and was merged
one-way by fast-forward before the lane commit. The intervening footer change
has no shared request, state, API or data owner. Its page-level layout is checked
with the rebuilt Personal browser tests and footer regression suite.

## Tradeoffs and rollback

Keeping the server's accepted expense values avoids a second data contract.
Translated labels are typed against all existing choices. A schema change that
adds a choice will require its English label at compile time.

The form exposes an English entry into a Spanish email flow. The approved
success detail makes that language boundary explicit. Revert this draft commit to restore the
English link to the Spanish form. A code revert changes no signup data.

## Reconciled local evidence

The final local browser run passed 79 checks and skipped the existing
fine-pointer case on the touch-only mobile project. The run includes footer
regressions after integration reconciliation. Both screenshots below use a
fixture CAPTCHA token; no real widget appears in these images.

The original four PNGs from `06003045d33117da9b968c59a5123d54f4ed7639` are
preserved outside Git at `/Users/garces/.codex/visualizations/2026/10/16/01a1430c-fce8-78b1-a002-a704ae804d29/cuadrao-sprint/english-waitlist-06003045d` with byte counts and SHA-256 hashes in
`manifest.json`. Lucas requested this external evidence storage. These captures
precede the approved Spanish-email sentence and are retained as historical
proof. No footer-lane evidence was changed.

Reproduce from `marketing/`:

```sh
bun run lint
bun run typecheck
bun test __tests__
bun run build
MARKETING_E2E_MOCK_PORT=4610 MARKETING_E2E_SITE_PORT=4611 MARKETING_E2E_PUBLIC_PORT=4612 bun run test:e2e e2e/personal.spec.ts e2e/personal-english-waitlist.spec.ts e2e/personal-waitlist.spec.ts e2e/personal-motion.spec.ts e2e/footer.spec.ts
```

The branch ownership gate, modularity budget on the reconciled tree and
`git diff --check` passed. Independent exact-head review and hosted verification
remain with root. Iris's copy review is complete with the Spanish-email sentence applied.

## Approved-copy reconciliation

The later integration head is `eb54d6f2c7f260012bb1a08780970d16b8bc38b4`.
The one-way merge is `7c709e08106b48b436d782624c4c62ff1542c874`. Both lanes
appended ownership entries; the merge retained both entries and verified that
all shared entries were identical. The upstream changes affect the page canvas
and footer logo, with no shared form, request, state or persistence changes.

Iris's only copy edit adds "The email is in Spanish." to the success detail.
The exact sentence and matching browser assertion changed together. The rebuilt
page passed lint, typecheck, ownership, modularity and 46 focused desktop/mobile
checks for English and Spanish forms plus the newly integrated background.
The prior unit and motion evidence remains applicable because those contracts
and handlers did not change.

Updated form and success screenshots are external at
`/Users/garces/.codex/visualizations/2026/10/16/01a1430c-fce8-78b1-a002-a704ae804d29/cuadrao-sprint/english-waitlist-approved-copy`.
These stable visual captures use reduced motion and explicit CAPTCHA and
registered-response fixtures. The separate 46-check run proves the shared local
handler. The external `manifest.json` records the integration and final code
heads, sizes and SHA-256 hashes. This follows Lucas's request to keep screenshot/video evidence
out of Git. The original four PNGs remain in the separate historical directory
listed above. No footer-lane images were removed by this lane.
