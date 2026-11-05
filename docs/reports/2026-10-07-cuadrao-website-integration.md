# Cuadrao website integration record

PR [#884](https://github.com/lagarcess/argus/pull/884) contains the October 7 founder-authorized website delivery to `codex/private-alpha-next`. Its terminal PR comment records the final reviewed head, merge SHA, review verdict and exact-head CI. This record travels with the same PR so branch protection applies to the documentation as well as the code.

## Outcome and boundaries

English and Spanish Business, Personal and contact pages preserve the approved presentation. Fictional examples explain money, plans, capture, assistant proposals, search, updates, personal/business separation and customer payments. The [coverage matrix](evidence/cuadrao-owner-vision/coverage.md) maps the source vision to the page and explains exclusions.

The site remains default-off through `CUADRAO_WEBSITE_PREVIEW=false` in the tracked web environment template. Preview pages remain noindex. Contact prepares a local review only. Personal signup returns HTTP 503 without storage or messages; the previous local SQLite experiment is not part of the delivered code. No new database, dependency or middleware service is introduced.

The independent review found a pre-hydration native form GET that could put a Personal email address in the URL. The fix follows the existing contact form's hydration guard and uses an explicit POST target. A real-browser regression covers both languages with JavaScript disabled and verifies retained input after the actual unavailable response.

## Lineage and evidence

- Original and pre-review integration base: `ad7eb9ccb8261456d12ce5a26686682bbce9ae2f`.
- Integration was an ancestor of the candidate. No reconciliation merge or intervening semantic overlap was present at review start. The terminal PR comment records the final pre-merge refresh.
- [Production browser evidence](evidence/cuadrao-integration-delivery/README.md) records the verified source tree, responsive layouts, form states, metadata, route gates and shared app checks.
- Independent review compares the actual parent and candidate browser surfaces, including enabled Spanish preferences and a synthetic public receipt without JavaScript. Its PR verdict is required before merge.
- Parent verification includes frontend tests, lint, production build/TypeScript, focused browser tests, modularity budget and changed-document links. GitHub CI and local smoke must be terminal and passing before merge.

## Remaining work

The public launch parent [#880](https://github.com/lagarcess/argus/issues/880) remains open for domain/routing, indexing, privacy and hosted acceptance. [#881](https://github.com/lagarcess/argus/issues/881) owns actual Business inquiry delivery. [#882](https://github.com/lagarcess/argus/issues/882) owns durable Personal signup through the existing Supabase infrastructure and notification/removal operations. Preserve any real earlier local registrations through separately reviewed handling; this delivery does not inspect or migrate a signup database.

These follow-ups are not closed by #884. The existing financial APIs, native app, model instructions, hosted configuration and deployments are outside this delivery.

## Landing procedure

After GitHub confirms the merge, fast-forward the clean canonical integration checkout, verify merge-tree parity, reconcile the three open issues and wait for exact-head integration CI and smoke. Record that outcome on #884. No documentation-only direct push or protection bypass is required because the execution and integration ledgers are included in the reviewed PR.

## Footer follow-up

[PR #886](https://github.com/lagarcess/argus/pull/886) applies the founder-selected hollow footer while retaining its lowered crop and original Space Grotesk + Inter typography. [Browser evidence](evidence/cuadrao-hollow-footer/README.md) covers Business and Personal in both languages. The terminal PR comment records the reviewed head, merge and integration checks. This presentation change does not complete or alter the remaining launch work above.

## Launch extraction

The public launch moves the site out of `web/` into the independent `marketing/` package and connects its forms. Record: [Cuadrao marketing launch](2026-10-07-cuadrao-marketing-launch.md). The statements above describe the #884 delivery; its default-off `CUADRAO_WEBSITE_PREVIEW` route and 503 signup endpoint no longer exist once the launch lands.
