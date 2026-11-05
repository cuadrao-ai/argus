# Cuadrao record review and approved branding

This is synthetic local UI evidence for #942, rendered with the configured `es-419` locale. No hosted, provider, customer-data or grant action was used. The development indicator is visible. Server data such as synthetic account nicknames is displayed as supplied.

## Reconciliation and scope

Original base: `77ddf2c7d33cc4c7273cc4c39354b5152fe01e91`. Current integration: `650b0fc660777cbcdfb1ea99a3be7beecbbe1a96` (C0 #955). One-way merge: `7667ee1e19589bed2e00aa1b9c08600965554860`. No conflicts or worker edits to backend, migrations, environments or authority documents. The only incoming web change was `web/AGENTS.md`; all implementation, fixtures, API projections, assets and tests remain byte-identical to the independently reviewed `85d564ae1b998d3f372828728855dab26e5b5deb`.

C0 is a shared semantic dependency: its landed sourced fact, RecordContext, dossier, review/approval version and idempotency contracts match the frozen transport this UI consumes. The merge imports those contracts without changing UI behavior. Runtime routes, real authorization/worker integration and hosted acceptance remain separate coordinator-owned work. No API receipt proves which pending review key produced a later revision; the UI therefore retains unacknowledged corrections and blocks approval instead of treating a new version or matching facts as success.

The [manifest](manifest.json) records captured heads, hashes, exact source scope and tracked-web tree equality. This publication changes only evidence. Its final head is recorded in the PR; the implemented web tree remains equal to the reconciliation head.

## Actual rendered proof

- [Spanish desktop auth artwork](brand-signin-light-spanish-1280.png) and [Spanish mobile dark auth artwork](brand-signin-dark-spanish-390.png), freshly captured at reconciliation head.
- [Retained unconfirmed correction](uncertain-retained-intent-spanish.png): the canonical header is another human's revision while the disabled form preserves the attempted correction. Saved facts/history and the uncertainty warning render separately; approval remains paused.
- [Owner-funded expense list](owner-funded-expenses-spanish.png) and [search result](owner-funded-search-spanish.png): `Dinero del dueño`, date, category and amount are visible with server `account_id=null`.

Record captures come from reviewed head `85d564ae1`; their complete implemented web tree was revalidated equal after reconciliation. No local screenshot establishes hosted customer readiness.

## Verification

- At reconciliation head: `bun test __tests__`, 2,329 passed / 218 files; `bun run lint`, zero errors and eight unchanged warnings; `python3 scripts/check_modularity_budget.py`, no violations; `git diff --check`, clean.
- Reconciled branding browser suite: 7/7 passed, both viewports/themes, sidebar controls, asset load, favicon byte match and Personal hydration.
- Reviewed record head: affected record/search browser 36/36 passed, including lost response after own write, request lost before write plus a different human's revision, repeated status GET without resubmission, acknowledged own save/readback/new intent, owner-funded Spanish list/search. Retained unchanged by the tree comparison.
- Actual signed-out draft login bounce: 1/1 passed with temporary local process settings only; canonical ID retained and unexpected query keys removed. No environment-file change.
- Full TypeScript remains failing: 8,298 diagnostics at reconciled head, versus 8,306 at original base. No new scoped source/test diagnostic. This is not a full typecheck or production build pass.
- Fresh independent functional review at `85d564ae1`: no actionable findings, focused 15/15 passed. Fresh no-comments reviews of implementation/fixes and restored source delta: zero flags. Unchanged code was not re-reviewed as a new defect source after reconciliation.
- GitHub exact-head required CI is recorded in the PR; merge and staging remain coordinator-owned.

## Approved-work accounting

| Work | Status and provenance |
| --- | --- |
| Canonical sourced contracts/action foundation | Landed separately as C0 #955, integration `650b0fc66` |
| Bounded record review, legacy corrected-value/source fallback | Implemented in this PR: `d9d09f6c5`, `3f3fab80a` |
| Idempotent review transport, explicit expense decision, returned fiscal/history/proposal facts, owner-funds projection | Implemented in this PR: `1cafe58a7` |
| Previously approved unpublished Cuadrao branding | Surgically restored in `67583d5e7`; sidebar/mark `212282765`, artwork/AuthForm/assets/locales `e05bdcffe`, palette `5887b7034`, favicon/title `bca99e4e1`, hydrated tab title `d136c3394`, latest palette successor `11fd99836` |
| Older literal palette states | Superseded by the approved `11fd99836` derived canonical color states; no whole-sandbox recovery |
| Canonical draft auth return | Implemented in `81d95d3d1`; existing same-origin/allowlist validation retained |
| Uncertain-intent retention and owner-paid list/search labels | Implemented in `85d564ae1`; final independent delta review clean |
| UI integration landing | Pending this PR and coordinator serialized merge; publication does not imply landed status |
| Hosted internet flow and real backend acceptance | Pending coordinator integration/auth/API/worker/staging acceptance; local evidence does not close J2 or broader #942 |

SVG gradient IDs and asset bytes are preserved from the approved source commits. Rendering uses existing Next Image with `unoptimized` and eager loading; no new suppression. Personal branch behavior, sidebar controls and original receipt links remain preserved.
