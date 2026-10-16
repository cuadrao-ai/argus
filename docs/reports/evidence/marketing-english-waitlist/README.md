# English Personal waitlist draft

Release is held for Iris's review of the English copy. Lucas relays the proposal.
Root also owns independent exact-head Eval, integration and staging. This record
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

The form exposes an English entry into a Spanish email flow. That scope is
explicit and held for Product review. Revert this draft commit to restore the
English link to the Spanish form. A code revert changes no signup data.

## Reconciled local evidence

The final local browser run passed 79 checks and skipped the existing
fine-pointer case on the touch-only mobile project. The run includes footer
regressions after integration reconciliation. Both screenshots below use a
fixture CAPTCHA token; no real widget appears in these images.

- [Desktop form](desktop-form.png) and [desktop success](desktop-success.png).
- [Mobile form](mobile-form.png) and [mobile success](mobile-success.png).

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
remain with root. Iris's copy review is still pending.
