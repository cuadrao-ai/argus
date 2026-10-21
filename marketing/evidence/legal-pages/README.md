# Spanish legal-page evidence

Owner: Lane 05. The October 16 overnight assignment limits this slice to the
three cleared Spanish legal pages, footer links and staging wiring. This slice
does not unblock the three-receipt flow. The coordinator owns staging and landing.

The original integration base is `6bfa52658c86175e2382e60c9fe9bc9459dbf189`.
The branch was fast-forwarded to `84e3f69397013a4d14f7a6b6bc36097680041b61`.
The intervening change affects email intake only, with no marketing overlap.

## Copy proof

The source is `cuadrao-legal-pages/marketing` in the founder's cleared archive.
Only Spanish text is imported. HTML review annotations are removed. No notes,
backup files or new English translations are published. The existing English
privacy page is retained.

Run from the repository root with the approved archive path:

```sh
python3 marketing/scripts/verify-legal-source.py "$LEGAL_ARCHIVE"
```

The verifier compares every word, in order, after removing Markdown formatting
and normalizing whitespace. It passed for privacy (878 words), terms (375 words)
and data deletion (181 words). The unit tests pin the resulting text digests.
The browser tests compare the complete rendered article against that content.

## Local verification

From `marketing/`:

```sh
bun install --frozen-lockfile
bun run build --webpack
bun run typecheck
bun run lint
bun run test
MARKETING_E2E_MOCK_PORT=4570 MARKETING_E2E_SITE_PORT=4571 MARKETING_E2E_PUBLIC_PORT=4572 bun run test:e2e e2e/legal.spec.ts e2e/site.spec.ts e2e/footer.spec.ts --project=desktop
```

Results: 183 unit tests pass across 16 files; 53 browser tests pass. Build,
typecheck, lint and the repository modularity check pass. The browser run uses
local mock providers. It makes no model calls and sends no real messages.

The six legal-page browser cases cover 320px and 390px widths, 200% CSS zoom
reflow, heading order, 24px footer targets, visible keyboard focus, private-host
noindex headers and automated WCAG 2.1 AA checks. All have zero automated
violations. Body text uses the existing dark ink on cream palette and a maximum
70ch column. The stylesheet keeps the existing heading and body fonts.

The [before privacy screenshot](before/privacidad-390.png) comes from the
integration base. Terms and data deletion returned 404 there. The six `after/`
images show the changed content tree at both viewport widths. Each screenshot
is full-page and includes the footer. No form behavior changes in this slice.

The first browser attempt overlapped a local rebuild and had one missing
noindex header. The complete rerun after the build finished passed all 53 cases.
The default local bundler stalled; the existing webpack option built successfully.

## Staging handoff

The new `cuadrao-marketing-staging` declaration uses the free plan, manual deploys
and `CUADRAO_SITE_INDEXING=private`. Every existing service definition is unchanged.
Build from `marketing/` with `bun install --frozen-lockfile && bun run build --webpack`.
Start with `bun run start -- -p $PORT`. Both commands were exercised locally.
The legal pages need no secrets. The coordinator must confirm the staging URL,
exact deployed commit and hosted page behavior before claiming hosted acceptance.

Tradeoff: the existing forms remain unavailable when provider configuration is
absent. Forms, retention jobs, unsubscribe behavior and IP trust remain outside
this narrowed slice. No table or migration is changed. The three legal URL names
are documented as empty values in the web example; this does not activate links.

The copy digest tests and route/browser checks detect drift. Rollback is a revert
of this PR plus the coordinator's manual rollback of the staging candidate.
