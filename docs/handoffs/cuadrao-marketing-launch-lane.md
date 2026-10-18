# Cuadrao marketing website lane: handoff

## Queued security follow-ups after PR #1223

[PR #1223](https://github.com/lagarcess/argus/pull/1223) remains pinned at `03d6ca64acfa76250ac5d58637f4a31cc3cc1dda`. Original item 1 is undelivered and tracked by [#1227](https://github.com/lagarcess/argus/issues/1227). The receipt gates remain held.

Only after #1223 lands, prepare a separate small PR for confirmation-page state on load. Confirmation GET must read token state without mutation. A used or expired token must immediately show its approved used or expired screen. A valid token must show the existing heading, "Confirma que quieres recibir noticias de Cuadrao en este correo.", and "Confirmar". Keep all mutations and email sends behind POST. Preserve approved copy and test used, expired, and valid tokens, including GET state preservation and explicit POST behavior. This is a queued dependency, not implemented work or an open code PR.

The [promotion checklist](../runbooks/cuadrao-marketing-launch.md#waitlist-scheduler-credential-order) owns secret setup before old-key rotation. Neither this queue nor a passing local check authorizes hosted settings, production actions, merge, or release.

Current continuation: [Polish round, October 11, 2026](#polish-round-october-11-2026), which supersedes the freeze below for the items it lists. [Claude handoff and freeze](#claude-handoff-and-freeze-october-11-2026) still governs everything it covers that the polish round does not change. This checkpoint supersedes historical next-step and approval instructions below.

Lane parent: [#880](https://github.com/lagarcess/argus/issues/880) (children #887 to #892). Written 2026-10-09 when the lane was paused so the founder can reserve Claude usage for the Consumer lane. Everything a successor needs is in the Git repository and the linked GitHub records. No private notes, session scratchpad or conversation is required.

This document is the single pickup point. It links to the canonical contracts and evidence instead of copying them; if this page and a linked source disagree, the linked source wins.

## 0. Read this first

**The successor's immediate scope is website aesthetics, worked with the founder, while Cuadrao LLC formation is pending.** Nothing is authorized to publish.

**First action:** ask the founder which aesthetic tweaks they want. Resume the existing touch-up branch and worktree recorded below. Do not restart from integration or discard the current work. Do not start anything listed under "Held" in section 1.

**The founder may change Business positioning after an interview with José.** Do not rewrite the website's promise, headlines or story from that interview or in anticipation of it. Visual work (spacing, type scale, color use, imagery, motion, layout polish) is in scope; changing what the Business site claims or who it speaks to is not, until the founder brings the outcome.

## Touch-up ownership checkpoint, 2026-10-09

The founder assigned this Codex chat ownership of Marketing only. This checkpoint
supersedes the earlier fresh-branch instruction. Business and Consumer worktrees,
code, and services are outside this assignment.

**The founder has not accepted the current design.** Prior passing tests and
review reports do not establish design approval. The first question was sent to
the founder asking what to change and what to keep. The founder later requested the screenshot removal and footer correction recorded below. Whole-page design acceptance remains pending.
New copy remains a draft in the [copy review](../reports/evidence/cuadrao-marketing-touchup/copy-review.md).

Verified at 13:54 America/Chicago on 2026-10-09:

- [PR #939](https://github.com/lagarcess/argus/pull/939) is open and draft, targeting `codex/private-alpha-next`.
- Branch `codex/marketing-touchup-delivery` is checked out at `/Users/garces/.codex/worktrees/cuadrao-marketing-delivery/private-alpha-next`.
- Local HEAD and GitHub PR head both equal `e09ee0e35b3c92546cf86c47f83b2fdbf10b47af`. The worktree was clean before these documentation updates.
- The original integration base is `bbf4da23f01296af4ac639386fe9a0960218a49f`. No fetch, reconciliation, reset, or rebase was performed during pickup.
- Updated preview `http://127.0.0.1:4512/` returns HTTP 200. Its existing process runs from this worktree's `marketing/` directory.
- Original comparison `http://127.0.0.1:4511/` returns HTTP 200. Its existing process runs from `/Users/garces/.codex/visualizations/2026/09/26/01a0de75-29ee-71f0-8f58-0d2bb3934a33/cuadrao-marketing-touchup/canonical/marketing`.
- Neither preview was restarted or changed. Preserve the comparison files and process.

The [touch-up evidence](../reports/evidence/cuadrao-marketing-touchup/README.md)
records the prior implementation and verification. Its screenshot manifest pins
`85c8cdf2a17c4a8dc6ff2990b75d6d44451cc40e`. The only subsequent change under
`marketing/` is test synchronization in `e2e/touchup.spec.ts`. Prior browser logs
record 142 passing checks and six repeated footer checks. Those suites were not
rerun during pickup, and no new visual acceptance or CI verdict is claimed.

The repository-wide pstack checkpoint points to the older connected-preview lane,
not this touch-up. Use this handoff, PR #939, and its committed evidence to continue.
No private transcript is required.

Next, record the founder's requested changes here before implementing them in
`marketing/`. Keep new copy Spanish first for founder review. Use the isolated test
ports in the evidence README so tests do not displace either comparison preview.
Read the mandatory product and technical documents before code changes.

No merge, publication, hosted change, real email, or public-form activation is
authorized. Existing LLC, operator wording, and provider holds still apply.

## Founder follow-up, 2026-10-09

The founder requested removal of the Business product screenshot because the product is incomplete and the numbers are incorrect. The Marketing-only change removes its whole section, related copy and styles, and the served image. Historical source captures remain in the evidence folder. See the [touch-up correction record](../reports/evidence/cuadrao-marketing-touchup/README.md#founder-correction-2026-10-09).

The founder confirmed the footer should rest at the cropped Cuadrao wordmark with photos fully hidden. Extra downward scrolling reveals a short photo peek, and release returns to the crop. The local Marketing implementation now removes autoplay, the grid and pause control, keeps normal page height and native upward/keyboard navigation, and disables peeking for reduced motion. Typecheck and lint pass. The rebuilt preview passes 20 focused browser checks. Fresh screenshots are committed under `docs/reports/evidence/cuadrao-marketing-touchup/footer-peek-screens/`; prior footer checks describe the removed animation.

The founder supplied the replacement footer photos. The unchanged dressmaker PNG is on the left and the unchanged artisan JPG on the right, with native dimensions and CSS upper-body cropping. Original files and the main editorial photos are preserved. The crop was inspected locally; final design acceptance remains open. The [footer correction record](../reports/evidence/cuadrao-marketing-touchup/README.md#footer-correction-2026-10-09) owns implementation details and remaining verification. The capture script writes new evidence to `footer-peek-screens/` without replacing historical captures. No Business or Consumer runtime, services, forms, or original comparison files were changed.

### Header and drag refinement request, 2026-10-09

The founder approved changing the navigation label to **Cómo funciona** and separating the language controls visually from main navigation. The English counterpart is **How it works**. The founder also requested less footer drag resistance and asked for inspection of Granola first. The release captain visited [Granola](https://www.granola.ai/) and exercised its footer: extra scrolling readily revealed a shallow photo band, then the footer returned when input stopped. This is an interaction reference, not permission to copy its assets.

The bounded Marketing implementation groups ES/EN separately and uses one localized navigation label for desktop and mobile. Footer input accumulates without losing movement between frames; touch holds the peek until release. Photos still hide fully at rest. Typecheck, lint, production build, 26 focused browser checks and 2 existing same-page language checks pass. The parent reviewed the diff and desktop/mobile screenshots. Source is `80cb9aca17b8a3789ea32f121928af1b48226484`; [current evidence](../reports/evidence/cuadrao-marketing-touchup/README.md#header-and-drag-refinement-2026-10-09) contains the manifest and logs. Both previews return 200. The original listener remains PID 11951. Work is committed locally, not pushed; the last verified GitHub head remains the pickup head above. Resume this branch without reset/rebase. Whole-page design acceptance remains pending. Existing release holds remain unchanged.

### Scroll-driven receipt story request, 2026-10-09

The founder said the latest header/footer view looks good, then requested that scrolling advance the receipt through Recibir, Revisar, and Aprobar. This feedback applies to the reviewed view, not publication or whole-page acceptance. The proposed pattern is a short sticky story with normal document scrolling, reverse progression on upward scroll, natural release after the final step, and click/keyboard rail shortcuts. A fit check must keep the receipt readable on phones; reduced motion keeps the plain manual presentation. The existing illustrated amounts and development disclosure remain unchanged.

The founder confirmed holding the section through all three steps and asked whether the whole page should become a larger scroll story. The recommendation is one primary receipt transformation now, with quieter surrounding sections. A second sequence should wait for another concrete product story; no whole-page animation expansion is assigned.

Implemented and verified at source `5c3c2d4a41ea2a1d1d76244b0158a1c32f28e805`. Normal scroll owns the active chapter and rail fill; each stage has half a viewport of travel, including a final reading interval before release. Desktop holds the complete scene. On phones the introduction scrolls away, then the rail, disclosure, and receipt pin together below the header. Reduced motion or insufficient height uses ordinary manual tabs without extra scroll distance. No product copy or claims changed.

Fresh build, typecheck, lint, and **42 focused browser checks pass**. Initial screenshot review caught a clipped mobile heading; the final layout and added regression check correct it. The bounded final code review is clean. [Evidence and continuation](../reports/evidence/cuadrao-marketing-touchup/README.md#scroll-driven-receipt-story-2026-10-09) includes exact-source screenshots, logs, reproduction commands, and limits. The existing Marketing branch contains local commits only; PR #939 has not been pushed or merged. Preview 4512 serves the rebuilt source with real provider credentials unset. Original comparison 4511 remains preserved. Whole-page design acceptance and all release holds remain pending.

## 1. Scope and decisions

### Status

| Item | Approved | Implemented | Verified | Pending |
| --- | --- | --- | --- | --- |
| Independent website package `marketing/` (Next.js, Bun, own lockfile) | yes | yes, on integration | CI, browser suite, local review | none |
| Business inquiry form (Resend) | yes | yes | mock providers only (unit, browser); **no real email has been sent** | hosted receipt test (held) |
| Personal early-access signup (Supabase) | yes | yes | mock and local real PostgREST/Postgres (see evidence) | production migration and hosted test (held) |
| Operator tools: `marketing/scripts/signups.ts`, `marketing/scripts/verify-origin.ts` | yes | yes | unit tests, local runs | first hosted use (held) |
| Privacy notice (Spanish and English) | wording approved 2026-10-08 as a draft, then three corrections | yes | review, CI, browser | **publication held** |
| "Lean, calm" mark, favicon, Apple icon, brand artwork | approved 2026-10-08 | yes | review, CI | none |
| Website-only promotion to `main` (Option B) | opening approved, **merging not approved** | draft PR #927 | CI, release-gate review | founder approval |
| Production migration `20260920000000` | no | repo file only | applier digest computed, never run against a hosted database | held |
| Render service `cuadrao-marketing` | no | not created | no Render state ever read | held |
| Domain cutover, indexing, Search Console | no | no | n/a | held |

### The founder's permissions and holds (as stated, 2026-10-07 to 2026-10-09)

Done under explicit permission: merging #895, #903, #923, #906 and #926 into integration (each once final head CI was green, a review was complete and no blocker was open); opening #927 as a draft under Option B; read-only inspection of Cloudflare and Resend; creating the `notify.cuadrao.ai` domain in Resend with tracking off and adding its DNS records (the founder added the DKIM record by hand and a scoped Cloudflare token for the other three).

Held, each needing its own explicit yes naming the exact object:
- **Cuadrao LLC and the operator wording.** Formation is pending. The privacy notice has no operator section on purpose and names no individual. The prepared "Cuadrao LLC" wording is in the [runbook](../runbooks/cuadrao-marketing-launch.md) ("Operator wording (prepared, not published)") and must stay unpublished until the founder confirms the company is formed and operates the site.
- **Public contact and signup forms** stay unpublished for the same reason.
- **#929 and #927 merges.** The founder merges #929; the successor must not merge it, or #927, to simplify anything.
- **The production migration, the paid Render service (about $7 per month), provider secrets, hosted emails, the domain cutover, indexing and Search Console.**
- **Integration merges never authorize promotion to `main`, deployment, migrations, emails or publication.**
- This handoff PR is not to be merged without the founder's approval.

### What the successor must not infer or start

- Approval of wording is per string. The founder approved the privacy text and the Contact under-form line (the same correction, applied in #926). They did not approve other new strings individually; confirm new or changed copy with the founder, Spanish first. Keep the Contact under-form line consistent with the privacy page (a unit test guards the Contact line).
- Do not publish, announce, index, create a Render service, enter or request secrets in chat, send any email to a real address, run the migration applier, or change DNS. Do not treat a green CI or a merged PR as permission for any of these.
- Do not redraw the mark or approximate the wordmark. Sources and hashes: section 4.
- Do not touch the iOS app or consumer files; the Consumer lane owns native use of the brand assets.
- Do not clean up Git history that contains the founder's name (the founder said none is needed).
- Do not use hosted facts in section 4 as current; they are dated observations.

## 2. Exact work state

Measured 2026-10-09 with `git fetch origin`.

| Ref | SHA |
| --- | --- |
| `origin/codex/private-alpha-next` (integration) | `5d9a1f55aa03a56a1b8e3afb064f4b4c70e25aec` (this handoff PR is cut from it) |
| `origin/main` | `a9286b21886eb03df7a21f2f4b7d5e79af570679` (144 commits and 35 migrations behind integration) |

### Pull requests

| PR | State | Head / merge SHA | Notes |
| --- | --- | --- | --- |
| [#895](https://github.com/lagarcess/argus/pull/895) website package and forms | merged | `fbb6bb447` (head `d0447a7da`) | landing on [#880](https://github.com/lagarcess/argus/issues/880#issuecomment-6049488390) |
| [#903](https://github.com/lagarcess/argus/pull/903) origin verifier, claim-then-send notices | merged | `1ffb53548` (head `32ad2c207`) | |
| [#923](https://github.com/lagarcess/argus/pull/923) notice-run stop and review notes | merged | `a9a30b37d` (head `37c68ea81`) | carried the #903 landing record |
| [#906](https://github.com/lagarcess/argus/pull/906) privacy rewrite, "Lean, calm" mark, brand artwork | merged | `b5e440c48` (head `5fd4de67c`) | landing: [PR comment](https://github.com/lagarcess/argus/pull/906#issuecomment-6069299602), [#880](https://github.com/lagarcess/argus/issues/880#issuecomment-6069299930) |
| [#926](https://github.com/lagarcess/argus/pull/926) Contact line says "to reply", not "only" | merged | `5d9a1f55a` (head `22a0b5d70`) | review and landing on the PR and [#880](https://github.com/lagarcess/argus/issues/880#issuecomment-6071016567) |
| [#929](https://github.com/lagarcess/argus/pull/929) recapture evidence, fix two revert notes | **open**, base integration | head `f555e53267b71bc36417fbbbabad9c2c636d1ff9` | scope below; founder merges |
| [#927](https://github.com/lagarcess/argus/pull/927) website-only promotion to `main` | **open draft**, base `main` | head `2d44044e405a4eae37d1c22567a5c3137ff53b7f` | not authorized to merge |

**#929's actual scope.** Documentation and evidence images only; no code. The final review of #927 found that the evidence folder's privacy and contact screenshots still showed text that #906 and #926 replaced, including the withdrawn privacy wording that named an individual. `capture.mjs` was rerun against a fresh production build at integration `5d9a1f55a`. Changed: eight screenshots (`es-privacy`, `en-privacy`, `es-contact`, `en-contact` at 1440 and 390 pixels) plus `webkit-en-contact-390.jpg`, `browser.json`, one row in the [evidence README](../reports/evidence/cuadrao-marketing-launch/README.md) (it now names the commit), and two revert notes (`marketing/README.md` and the runbook now say that on `main`, reverting the promotion commit removes `marketing/` and its migration file and nothing else). Home and Personal captures are byte-identical to before. 13 files; CI 18 of 18 green (one earlier install failure was the registry flake described in section 3, cleared by a rerun).

### Dependencies and merge order

1. **#929 merges into integration first** (founder). Then the candidate #927 equals integration on every path it carries.
2. **#927 merges only on the founder's explicit approval to promote**, after the pre-merge confirmations in section 5.
3. The migration, Render service, secrets, tests and cutover follow the order in the held deployment request: [deployment request](https://github.com/lagarcess/argus/issues/880#issuecomment-6069169773) (steps 0 to 5) and [held migration and Render requests](https://github.com/lagarcess/argus/issues/880#issuecomment-6069364033).

### Deployment candidate and its refresh procedure (#927)

Branch `codex/cuadrao-marketing-main-promotion-prep` is cut from `origin/main` (`a9286b218`). At head `2d44044e4` it carries **142 files: 140 new, 2 modified, 0 deleted** (`git diff --name-status origin/main...HEAD`). Carried: `marketing/**`, `supabase/migrations/20260920000000_cuadrao_early_access_signups.sql` (SHA-256 `ea2a2a010d31f1c05222561d5f90fa024df2fac46a466107c7bdf3138d11aad0`), `tests/test_cuadrao_early_access_postgres.py`, the [launch record](../reports/2026-10-07-cuadrao-marketing-launch.md), the [runbook](../runbooks/cuadrao-marketing-launch.md), the [forms contract](../specs/cuadrao-marketing-forms-contract.md) and the [evidence folder](../reports/evidence/cuadrao-marketing-launch/README.md). The two modified files, `.github/workflows/ci.yml` (a `marketing-checks` job and its entry in the aggregate `ci` job's `needs`) and `tests/test_ci_workflow.py`, are written for `main`'s simpler workflow and are **not** mirrored from integration. `web/`, `src/`, `ios/`, `render.yaml` and every other migration are byte-identical to `main`.

Refresh once after any change lands on a carried path:

```bash
# in the candidate worktree, on codex/cuadrao-marketing-main-promotion-prep
git fetch origin
SRC=<integration commit that contains the accepted change>
git checkout $SRC -- marketing \
  docs/reports/2026-10-07-cuadrao-marketing-launch.md \
  docs/runbooks/cuadrao-marketing-launch.md \
  docs/specs/cuadrao-marketing-forms-contract.md \
  docs/reports/evidence/cuadrao-marketing-launch \
  supabase/migrations/20260920000000_cuadrao_early_access_signups.sql \
  tests/test_cuadrao_early_access_postgres.py
# remove carried files that no longer exist upstream
for d in marketing docs/reports/evidence/cuadrao-marketing-launch; do
  comm -23 <(git ls-files $d | sort) <(git ls-tree -r --name-only $SRC $d | sort)
done | xargs -r git rm -q -f
git diff --stat $SRC HEAD -- <the same paths>   # must be empty after the commit
git commit -m "feat(marketing): refresh the candidate to <SRC>" && git push
```

A push to a `codex/**` branch runs full CI. Then update the body of #927 (heads, counts) and confirm `git diff --name-status origin/main...HEAD` is still 140 added, 2 modified, 0 deleted and that `web/`, `src/`, `ios/`, `render.yaml` are unchanged.

### Branches and local state

| Branch | Role | State |
| --- | --- | --- |
| `codex/cuadrao-marketing-main-promotion-prep` | candidate for #927 | pushed, head `2d44044e4` |
| `codex/cuadrao-evidence-refresh` | #929 | pushed, head `f555e5326` |
| `codex/cuadrao-marketing-handoff` | this document | pushed with this PR |
| merged and no longer needed: `codex/cuadrao-marketing-launch`, `codex/cuadrao-marketing-website-ops`, `codex/cuadrao-privacy-icloud-wording`, `codex/cuadrao-contact-line-consistency`, `codex/cuadrao-903-landing` | merged branches | left in place, no cleanup |

**Uncommitted or local-only work: none.** Every worktree this lane used was clean when it stopped. Local worktrees (convenience only, not required): `argus-worktrees/cuadrao-marketing-main-prep`, `cuadrao-landing` (#929), `cuadrao-privacy`, `cuadrao-903-review` (detached review checkout), `cuadrao-marketing-launch`, `cuadrao-handoff`. The session's own worktree has an untracked `probes/` directory that predates this lane and belongs to the native-auth proof work, not to this lane; do not touch it.

### Issues

#880, #881, #882, #887, #888, #889, #890, #891 are open (#892 is deferred). Their acceptance is not closed because hosted acceptance, publication and cutover have not happened. Do not close them from the repository state alone.

## 3. Verification

Each result names the commit it covers. "Browser" means the Playwright suite (desktop and mobile projects, with the automated accessibility checks) against a **fresh** production build. Every figure was observed on a clean checkout of that commit unless stated.

| Commit / PR | Unit | Typecheck, lint | Browser | CI (GitHub) |
| --- | --- | --- | --- | --- |
| `32ad2c207` (#903) | 132 pass (review) | clean | 85 and 86 verifier checks, local, both modes | all green |
| `37c68ea81` (#923) | 135 pass | clean | verifier 87 (candidate mode) and 88 (public mode) checks, 0 failed, wrong mode rejected (exit 1), local | 18 of 18 |
| `5fd4de67c` (#906) | 175 pass | clean | 130 of 130 at `cc8fb0e9d`, fresh build; screenshots rebuilt at `5fd4de67c` | 18 of 18 |
| `22a0b5d70` (#926) | 177 pass | clean | 130 of 130, fresh build | 18 of 18 |
| `f555e5326` (#929) | no code change | n/a | recapture ran on a fresh build at `5d9a1f55a` | 18 of 18 after rerunning an install flake: [run](https://github.com/lagarcess/argus/actions/runs/37859719987) |
| `2d44044e4` (#927 candidate) | in CI | in CI | in CI (177 unit, 130 browser) | push run green: [run](https://github.com/lagarcess/argus/actions/runs/37859748948) (frontend, backend, guest-release-gates, marketing, ownership, aggregate `ci`) |

Evidence files: the [evidence README](../reports/evidence/cuadrao-marketing-launch/README.md) names each file and the commit it vouches for ([storage proof](../reports/evidence/cuadrao-marketing-launch/storage-proof.md), [verify-origin local run](../reports/evidence/cuadrao-marketing-launch/verify-origin-local.json), [browser report](../reports/evidence/cuadrao-marketing-launch/browser.json), [screens](../reports/evidence/cuadrao-marketing-launch/screens)). The verifier's local run was repeated after the redirect-host change at `61294c3c2`; the file records the counts.

### Reviews and what was done about them

Independent reviews were run by separate agents; their full text is not in the repository, so their findings and dispositions are recorded here and in the landing records.

| Subject (head) | Verdict | Findings and disposition |
| --- | --- | --- |
| #903 (`32ad2c207`) | clean | Four non-blocking findings (a provider outage could claim every row; hand-send advice assumed one run; failed-release path untested; evidence counts) and doc nits. All settled in #923. |
| #923 (`61294c3c2`, `5698c7776`) | clean, twice | Non-blocking: the release-failed advice could lead to a second email; stop message for test sends; a missing test; evidence attribution. Fixed at `5698c7776` and `37c68ea81`. |
| #906 (`acf1b180a`, `cc8fb0e9d`, `5fd4de67c`) | one blocking each at the first two heads, clean at `5fd4de67c` | Blocking: "only to reply" was inaccurate because the contact email also keys an in-memory submission limit; then the limiter's sweep ran only on submission, so the "at most two hours" statement could be false on a quiet site. Fixed by a timer sweep and by the three approved wording corrections. Also fixed: malformed `favicon.ico` header, wrong kerning and ink numbers in the brand README, test gaps. Not changed, by choice: every brand SVG names its gradients `a`, `b`, `c` (use them as image files, never two inline; documented in the brand README) so the approved hashes stay stable. |
| #926 | clean (proportionate, by the lane's author, posted on the PR) | A sweep of every "solo" and "only" in the site copy found no other exclusive data-use claim except the Personal line, which review confirmed accurate. |
| #927 (`056998035`) | clean | Non-blocking: main's aggregate `ci` is skipped, not failed, when a needed job fails (pre-existing on `main`); stale evidence (fixed in #929); two false revert notes (fixed in #929); dated statements become false at merge. Comment on the [PR](https://github.com/lagarcess/argus/pull/927#issuecomment-6071091669). |

### Reproduce the relevant checks

Prerequisites: Node 24.21.0 (the pin in the [runbook](../runbooks/cuadrao-marketing-launch.md)), Bun 1.3.14 (`ARGUS_CI_BUN_VERSION` in `.github/workflows/ci.yml`; a lockfile written by another Bun version is unreadable in CI, regenerate with `npx -y bun@1.3.14 install`), and Playwright Chromium (`npx playwright install chromium`).

```bash
cd marketing
npx -y bun@1.3.14 install --frozen-lockfile
bun test __tests__
bun run typecheck
bun run lint
bun run build                      # required: Playwright serves an existing build and otherwise tests a stale site
CI=1 npx playwright test           # starts the mock providers (4510) and the site (4511, 4512)
```

- Free the ports first and kill stale `next-server` and `mock-providers` processes; orphans cause cross-run interference. Run Playwright with `CI=1` and write to a log; piping it can hang.
- Read-only origin check (from `marketing/`): `bun run scripts/verify-origin.ts <origin> [--public --www <origin>]` (GET only; candidate mode expects noindex, `--public` expects indexable).
- Evidence recapture: `bunx next start -p 4511` then `node ../docs/reports/evidence/cuadrao-marketing-launch/capture.mjs http://127.0.0.1:4511 <commit>` from `marketing/`.
- Brand regeneration (only if the mark or wordmark changes, which needs the founder): `python3 scripts/make-brand-assets.py` (needs `fonttools`, `brotli`, `uharfbuzz`) and `node scripts/make-icons.mjs`. Tests keep every brand file's geometry identical.
- Main-shaped workflow test (candidate only): `pytest tests/test_ci_workflow.py` from the repository root with the repo's Python environment (38 passed with `tests/test_private_alpha_canary_split.py` in the final review).

Environment-variable names the tests and the site use (values are never committed): `RESEND_API_KEY`, `RESEND_API_URL`, `CUADRAO_INQUIRY_FROM`, `CUADRAO_INQUIRY_TO`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `CUADRAO_SITE_INDEXING`, `CUADRAO_TRUSTED_CLIENT_IP_HEADER`, `CUADRAO_NOTICE_FROM` (operator notice script), `NODE_VERSION`, `NEXT_TELEMETRY_DISABLED`. The Playwright config injects test values pointing at the local mock; see [`marketing/.env.example`](../../marketing/.env.example) and the [forms contract](../specs/cuadrao-marketing-forms-contract.md).

Local preview that cannot send real email: start `node marketing/e2e/mock-providers.mjs`, then run `next start` from `marketing/` with the Resend and Supabase variables above pointing at `http://127.0.0.1:4510` and a throwaway key and recipient. Submissions land in the mock.

### Known failures and unresolved findings

- **CI install flake.** An install step sometimes fails with "Fail extracting tarball for next" (a registry error, not code). Rerun the failed jobs after the run has finished.
- **`main`'s aggregate `ci` job** is skipped, not failed, when a job it needs fails, and a skipped required check counts as passing. Pre-existing on `main`; whoever merges #927 must read every job, not only `ci`. Integration's workflow already has the stricter form.
- **Stale sentence in the launch record:** "Its own landing is recorded below once it merges" (about #906) is out of date; the landing is on #906 and #880. Fix it the next time the record changes. Dated statements ("nothing was promoted to `main`", `main`'s newest migration) become false when #927 merges; update them in the post-merge record.
- The Business footer and founder story show the founder's name and LinkedIn by the founder's instruction. The privacy notice names no operator or individual.
- No unresolved blocking finding is open on any PR in this lane.

## 4. Operational context

### Brand sources (approved 2026-10-08, "Lean, calm")

Pinned and hashed in the [pinned comment on #906](https://github.com/lagarcess/argus/pull/906#issuecomment-6066490040). Files: [`marketing/app/icon.svg`](../../marketing/app/icon.svg) (tiled; iOS icon and favicon), [`marketing/brand/`](../../marketing/brand/README.md) (mark without tile in light and dark, outlined wordmark in two colors, light and dark lockups, with the specification, geometry and colors in `brand/README.md`). The wordmark is the website's own: Space Grotesk 700, letter-spacing -0.085em (not the lighter variant shown on early icon sheets). The shared design guide that the Consumer lane records native use in is [`.agent/designs/cuadrao/DESIGN.md`](../../.agent/designs/cuadrao/DESIGN.md) ("Brand identity"). `marketing/app/apple-icon.png` (180 px) is web-only; never enlarge it. No dark or tinted iOS icon variants exist.

### Services, connectors and credentials

| System | Use | Access | Where an authorized operator supplies credentials |
| --- | --- | --- | --- |
| GitHub (`gh`) | PRs, CI, issue records | authenticated CLI | operator's own login |
| Resend | `notify.cuadrao.ai` sending | connector available | the sending key (restricted to `notify.cuadrao.ai`) is created and typed by the founder into Render; never in chat, commits, logs or evidence |
| Cloudflare | zone `cuadrao.ai` DNS | connector available; a scoped day-long token was used once and deleted by the founder | cutover would need a new scoped token created by the founder |
| Supabase (free plan) | Personal signup table | connector listed as connected but the project-level server rejected its credentials (HTTP 401) when last checked 2026-10-09 | `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` typed by the founder into Render and the operator's shell; the production connection string for the applier is held by the founder |
| Render | the website service | **connector returned "unauthorized" on 2026-10-08/09**; the CLI token was expired on 2026-10-07; no Render state has ever been read by this lane | the founder reconnects the Render connector in Claude's Settings, Connectors; a project-level `render` server uses its own API key, replaced from the Render dashboard |
| iCloud Mail | `hola@cuadrao.ai` custom-domain mailbox | the founder's account | the founder |

### Hosted facts, with when and how they were observed (do not treat as current)

- **Resend `notify.cuadrao.ai`:** domain created, region `us-east-1`, tracking off; reported **Verified** with four records. Recorded 2026-10-08 in the [launch record](../reports/2026-10-07-cuadrao-marketing-launch.md), read through the Resend connector. Not reread since.
- **Cloudflare zone `cuadrao.ai`:** 9 records before and 12 after the three records were added; 0 of the 9 existing records changed (iCloud MX and SPF, Apple domain TXT, `sig1` DKIM CNAME, Resend root records). Recorded 2026-10-08 from a Cloudflare API readback in the launch record. No DMARC record exists as of that date. Never add Cloudflare Email Routing: it would replace the iCloud MX.
- **Supabase GitHub integration:** disabled by the founder on 2026-10-08. Verified **by behavior** (no preview branch appeared on three migration PRs; a probe commit showed no Supabase check), not by reading the dashboard setting, which is dashboard-only. The #927 release review asked for a dashboard confirmation before merging.
- **Production migration ledger:** read-only observation on 2026-10-07 (81 entries; production's newest equals `main`'s newest, `20260914120000`, but the ledgers differ); recorded in the [runbook](../runbooks/cuadrao-marketing-launch.md). It will have changed if the consumer lane applied anything since.
- **Render:** nothing observed.
- **Production Supabase project reference** `lgdhvepyrzbnscqssgqq` is the one named by Supabase's own PR notices on 2026-10-07; the founder confirms it when issuing an approval record.

### Migration applier (the consumer lane's tool)

`scripts/ops/apply_approved_migrations.py` applies an explicit version list and refuses hosted hosts unless a committed approval record names them; `scripts/ops/production_migration_gate.py` is the read-only gate. The run digest for `["20260920000000"]` is `090e86fa74fb104a0d3984653624cf72fd65faa8ac7bb2a930ed937c73fb0f8f` (computed locally, never run against a hosted database). The signup migration must precede the consumer's 35 files because the applier records versions as a strict prefix. Full packet and prerequisites: the [held request](https://github.com/lagarcess/argus/issues/880#issuecomment-6069364033). `supabase db push` is never used.

## 5. Next steps

**What the successor can do now (no approval beyond the founder's direction in conversation):**

1. Ask the founder for the aesthetic tweaks. Resume `codex/marketing-touchup-delivery` in the existing worktree recorded in the ownership checkpoint.
2. For each requested tweak, update `marketing/` on the existing branch and verify the affected behavior. Use the isolated test ports in the touch-up evidence README. Continue PR #939. Record any founder-authorized landing on the PR and #880. Integration remains protected.
3. Keep new or changed user-facing words Spanish first and confirmed with the founder. Keep the Contact line and the privacy page consistent.
4. After a tweak lands on a path #927 carries, refresh the candidate once (section 2) and update #927's body.
5. Do not change product copy that expresses Business positioning until the founder reports the José interview outcome.

**What requires the founder's approval (each its own explicit yes):**

1. Merge #929 (founder merges), then promotion (#927) under the pre-merge confirmations: the Supabase GitHub integration really off in the dashboard; the auto-deploy setting of the `argus-backtests` service (not in `render.yaml`); every CI job read, not only `ci`.
2. Confirm Cuadrao LLC is formed and operates the site; then publish the operator wording and the forms.
3. Apply `20260920000000` (founder runs the gate, backup and applier; consumer lane's tool).
4. Create the Render service (phase 3a without provider secrets, later 3b) and reconnect the Render connector if a read is needed.
5. Provider secrets, two founder-supplied test addresses, hosted tests, then cutover, indexing and Search Console.
6. Merge this handoff PR.

## 6. Canonical sources and optional material

Canonical, not copied here: the [launch record](../reports/2026-10-07-cuadrao-marketing-launch.md), [runbook](../runbooks/cuadrao-marketing-launch.md), [forms contract](../specs/cuadrao-marketing-forms-contract.md), [package README](../../marketing/README.md), [brand README](../../marketing/brand/README.md), [evidence](../reports/evidence/cuadrao-marketing-launch/README.md), [shared design guide](../../.agent/designs/cuadrao/DESIGN.md), and on #880 the [deployment request](https://github.com/lagarcess/argus/issues/880#issuecomment-6069169773), the [held migration and Render requests](https://github.com/lagarcess/argus/issues/880#issuecomment-6069364033) and the [checkpoint comment](https://github.com/lagarcess/argus/issues/880#issuecomment-6073256570).

Optional, not needed to resume, and not committed: the working session's scratchpad held icon exploration sheets (rounds of mark variations and the finalists sheet, as images and HTML), screenshots of the local site, a one-off Cloudflare record script that read a scoped token from a local `.env` (the founder deleted the token), and review mutation scratch copies. The approved artwork and every hash needed to resume are in the repository and on #906; losing the scratchpad loses nothing required.

### Current local verification

The screenshot removal and footer peek pass a fresh production build and 20 focused browser checks. The hidden photo-loading failure found during the first run is fixed. See the touch-up evidence README for the result and photo provenance. Both implementation agents returned ownership and stopped. Only the updated Marketing preview on 4512 was rebuilt and restarted. The original comparison remains on 4511. Header feedback is advisory; no header changes were requested or made. No merge, push, publication, provider activation, or hosted change occurred.

The final runtime source is `f98974687caecc01c24786007e448754a782d1a2`. Its fresh screenshot manifest pins that exact source. Later evidence-only changes preserve the runtime bytes. The local changes remain unpushed while the founder reviews the design.

## Personal signup motion request, 2026-10-09

The founder requested a more playful Personal early-access page using the Base reference composition with Cuadrao's existing copy/form on the left and a hand holding a phone on the right. The founder chose the mobile welcome screen with its logo and signup button. A square pet should peek out near the email input, follow the pointer with its eyes, get excited on submission, and travel with an envelope to the phone logo on success.

The Marketing implementation will preserve signup truth and confirmation copy. Only a successful registered API response may trigger the delivery celebration, and confirmation must not wait for animation. Errors preserve the email. Keyboard, touch and reduced-motion visitors retain a complete form. No Consumer or Business code, services, simulator, hosted state, real email or public signup activation is authorized by this visual request.

A historical native welcome capture was located in `docs/reports/evidence/cuadrao-release-ui/2026-10-03-w1/release-design-launch-light.png`. It shows the Cuadrao lockup, squares, tagline, Crear cuenta and Iniciar sesión. It is October 3 simulator design evidence, not a claim about the current shipping app. The unchanged image is copied as `marketing/public/cuadrao-site/personal-welcome-preview.png`; provenance stays with the release-UI evidence README. The hand illustration will be an original code-native graphic, not extracted Base artwork. Implemented and locally verified at `c8eab10647c56a49591033f5e5a026bb8a5befa6`. The scene uses the existing SignupState, a small decorative geometry record, and a single finite success flight. Confirmation is immediate. Errors produce no flight, and reduced motion/offscreen targets skip travel. The parent corrected a headline shift found in visual review. Fresh build, typecheck, lint, 33 signup/motion checks and four Personal accessibility checks pass; one pointer-only test is intentionally skipped for touch. Independent implementation and final-delta reviews are clean. [Personal pet evidence](../reports/evidence/cuadrao-marketing-touchup/personal-pet/README.md) contains provenance, exact-source captures, a short mock-response recording and reproduction instructions. The 4512 preview is rebuilt with real provider credentials unset. The original comparison and all other lane services remain untouched. Work is local only, with no push or publication. Founder visual acceptance of this new scene remains pending.


### Personal hand and live demo refinement, 2026-10-09

The founder liked the first scene and requested a hand closer to the supplied Base reference, current header lettering inside the phone, and a live local mock. Final runtime source is `7872970775ffdd4b92deeb9b43fe3586b6ea43ba`. The black hand has slimmer fingers and a fading wrist. The welcome screenshot remains unchanged on disk; a canonical header SVG overlay updates the rendered wordmark. This is a composite Marketing preview, not a Consumer app change.

The safe live demo is `http://127.0.0.1:4513/personal`, with a bilingual no-email-saved badge and Replay. Start it with `node scripts/personal-demo.mjs` from `marketing/` while the provider-disabled 4512 server runs. Its loopback-only proxy discards signup bodies and returns a fixture; other mutations are blocked. Updated preview PID 2188 (4512), demo PID 1265 (4513); verify process cwd before restart. Original 4511/PID11951 is untouched. Build/typecheck/lint, one HTTP boundary test, 33 motion/signup checks and four accessibility checks passed, with one intentional touch skip. Behavioral checks are retained across the final SVG-only delta; final captures pin the final source. Independent final review is clean. Browser mock submission and Replay were verified. See the Personal pet evidence README and its refreshed recording. No push, hosted changes, public-form activation, real email, merge or publication occurred. Current design refinement remains for founder review. All workers returned ownership and stopped.


### Reference angle and grip correction

The founder rejected the earlier phone angle/hand geometry while retaining the rest of the scene. Final visual source `2e0cb71b84779b73d7f6b1d2d8ee8a24bce879bf` uses a shared reference frame, rising phone top edge, left-shifted lower edge, silver side and a continuous curled grip. Parent fixed two painting seams after render inspection. Thirteen focused motion checks pass with one intentional touch skip; build/typecheck/lint and final independent review are clean. Final desktop/mobile ES/EN captures and clip are refreshed. The supplied reference is now durable in `personal-pet/founder-hand-reference.png`; [Personal evidence](../reports/evidence/cuadrao-marketing-touchup/personal-pet/README.md) owns reproduction and provenance. Preview remains 4512 and simulated signup remains 4513. No form/runtime/provider or other-lane changes, no push, and no publication. Agents have returned ownership and stopped. Founder review of the corrected geometry remains pending.


Latest founder steering: keep the corrected grip and turn the phone slightly toward the reader. Visual source `fbc064e0da41be93bfbdb1201e76031d1a915578` adds gentle perspective and narrows the silver edge through three CSS declarations. Fresh build and 13 motion checks pass (one intentional touch skip); exact-source captures/clip refreshed in Personal evidence. Preview 4512 and mock 4513 use the change. The hand, signup logic and other lanes remain untouched. Local only, unpushed.


Latest phone cleanup source `1c4dca80a512919a523fc9649c8ccd1f96fa8539` removes the slogan inside the phone and replaces its older screenshot icon with the canonical light mark. The lockup and central mark now use the same approved greens and lime overlap. A code-native overlay preserves the original PNG; no Consumer screen was changed. Hand, reader-facing angle, welcome buttons and motion are retained. Typecheck/lint/build, 15 brand tests, refreshed exact-source browser captures and independent scoped review pass. The current source and provenance are in Personal evidence. Preview4512 and mock4513 remain local; no push, publication, provider activation or other-lane changes. All workers stopped.


## Accepted baseline lock before final footer polish

The founder requested locking all progress so far. [Accepted design checkpoint](../reports/evidence/cuadrao-marketing-touchup/accepted-design-checkpoint.md) is now the current continuation authority for this touch-up. It records baseline `ee4a93e04`, runtime `1c4dca80a`, the local annotated tag, preservation boundaries and the remaining Personal-footer/polish work. It supersedes earlier pending-design-acceptance wording only for the accepted baseline. Footer requests are awaited; no speculative footer edits were made. No launch, merge, push, publication, hosted change, public-form or real-email authorization is implied.


### Personal copy polish after baseline lock

At the founder’s request, source `d81766f0b371d427f7346cdf1b8dcc1de052ca97` removes the phone’s design-preview caption and repetitive signup wording in both languages. Privacy, early-access status and actual signup behavior remain. The separate mock keeps its simulation label. Fresh build/typecheck/lint and 33 signup/motion browser checks pass, with one expected touch skip; independent scoped review is clean. Exact-source screenshots and recording are refreshed in [Personal evidence](../reports/evidence/cuadrao-marketing-touchup/personal-pet/README.md). The accepted checkpoint tag is unchanged. The founder will send a footer inspiration clip; await it before changing the photos/reveal. Preview 4512 is rebuilt with real providers unset, mock 4513 and original comparison 4511 remain available. Local only, unpushed; no release approval or other-lane changes.


### Personal footer sequence trial, October 9, 2026

The founder approved trying the Granola-inspired image sequence on Personal only. Source `7f0f1354d68ee0638ed2ebca36425b7c359af428` layers the existing dressmaker and artisan photos and plays one finite swap during the extra-scroll reveal. No playback controls or continuous loop. Existing spring-back timing remains. Business keeps its photo pair; its desktop footer screenshot is byte-identical before and after.

Fresh build/typecheck/lint, 42 focused browser checks, independent scoped review, and desktop/mobile visual inspection pass. [Personal footer evidence](../reports/evidence/cuadrao-marketing-touchup/personal-footer/README.md) owns the design tradeoff, exact-source captures, short clip, and reproduction. Preview 4512 is rebuilt with providers unset. Comparison 4511 and signup mock 4513 are preserved. The accepted baseline tag is unchanged. This new trial awaits founder feedback; no final replacement, hosted, merge, push, or activation authority is implied. All agents returned ownership and stopped.


### Personal ends at the wordmark

The founder requested removing Personal footer photos and ending at the cropped wordmark. Source `2ab403d6df815ea1ff66d792d504564cab44109d` bypasses FooterMotion on Personal and deletes the unused sequence option/styles. Business motion is restored to its pre-trial source and its screenshot is unchanged. Fresh build/typecheck/lint, 30 focused browser checks, scoped review and desktop/mobile visual inspection pass. [Current footer evidence](../reports/evidence/cuadrao-marketing-touchup/personal-footer-wordmark/README.md) supersedes the prior sequence trial. Preview4512 is rebuilt; comparison4511 and signupmock4513 are preserved. No push, hosted changes, merge, publication, real email or public activation. All delegated agents stopped.

### Personal accepted lock and final Marketing polish, October 9, 2026

Current continuation authority: [final polish and replacement-readiness report](../reports/evidence/cuadrao-marketing-touchup/final-polish/README.md). The founder accepted Personal; local tag `codex/marketing-personal-accepted-2026-10-09` locks `3a0f125e5`, with a durable [checkpoint](../reports/evidence/cuadrao-marketing-touchup/personal-accepted-checkpoint.md). Final audit found no new Personal design change needed.

At the founder's request, Business editorial florist/accountant images, captions and disclosure are removed. Founder portrait/signature remain. Both pages and other shared Marketing footers now end at the static cropped wordmark; the obsolete photo-reveal component and styles are deleted. Runtime source `1d87ca636`, verified/captured candidate `8a45ab0a482b5d7674a50d7c90058915e4fabe00`. Later docs/evidence preserve runtime bytes. Business changes are available for founder visual review.

Build/typecheck/lint and 177 unit tests pass. Full browser run: 181 passed, one intentional touch skip, two one-pixel rounding assertion failures; eight affected footer cases pass after correcting the assertion tolerance. No runtime fix was needed. Sixteen ES/EN desktop/narrow-view combinations pass in Chromium/WebKit with 32 durable screenshots. Independent scoped runtime review and final tooling/runbook delta review are clean. All three delegated agents returned ownership and stopped. Logs and exact-source manifest are in the final report.

Remaining replacement gates: publish/reconcile accepted work into the release candidate and exact-head CI; confirm actual privacy operator wording; approved migration/configuration and hosted signup storage/dedupe/restart/removal checks; real-device Safari smoke; explicit promotion/deployment/public-form/cutover/indexing approval and rollback target. Signup backend already exists. The runbook now consistently reflects its prior analysis that the signup migration can be its own first ordered prefix; Personal does not depend on a Consumer product launch. Production status/tool readiness must be refreshed before execution.

Preview4512/PID30054 uses the fresh provider-disabled build. Original4511/PID11951 and mock4513/PID1265 remain unchanged; all return HTTP200. Verify cwd/PIDs before restarting. Branch remains `codex/marketing-touchup-delivery`; no push, merge, hosted changes, public activation or real email. PR939 remains open draft at remote `e09ee0e35`; local acceptance is not remote release readiness. No Business/Consumer product worktrees or services changed.


### Authorized PR update, footer branding and original-layout archive

The founder authorized pushing all accepted changes to PR939 and obtaining green CI; deployment and public forms remain held. [Latest verification](../reports/evidence/cuadrao-marketing-touchup/final-polish/README.md) records candidate `ece1aa067f`, canonical small-footer lockups, regenerated light-mark favicon,177 unit tests,183 passing browser checks/one expected touch skip,16 browser/locale/viewport captures, synced mock signup and clean independent review. Original base `bbf4da23f` advanced to `43fac94de` through the iOS-only keyboard change. No Marketing semantic overlap; one-way reconciliation merge `ece1aa067f` and merged-tree modularity pass. No product worktree or service changed.

The original layout is now a durable [source archive and screenshot index](../reports/evidence/cuadrao-marketing-touchup/original-layout-archive/README.md). Its original files match source171779c97 and remain untouched. The old4511 process had stopped; a separate archive extraction now serves4511 with providers unset. Current4512 and fixture-only4513 serve the accepted design plus footer branding/favicon. Verify listener cwd before any later restart.

PR939 remains draft targeting integration. No merge, deployment, hosted changes, public forms or real email. Read GitHub for terminal exact-head CI rather than assuming the previous head’s result. The current report and screenshots supersede historical footer-photo and old-icon descriptions.


## Phone locale follow-up, October 9, 2026

Runtime `d5436b7e861876fea205ac7cdb68ac943702c8fa` makes the Marketing phone preview follow the header language. Existing hand, angle, artwork and submission logic are unchanged. Build/lint/typecheck/modularity pass; focused signup/motion tests pass 35 with one intentional touch skip. ES/EN desktop/mobile WebKit captures and signup demo evidence are refreshed. Independent scoped review is clean. See [locale verification](../reports/evidence/cuadrao-marketing-touchup/personal-pet/locale-check/README.md). Integration remains `43fac94de2672600079f312258908f05747a9d63`. The following evidence-only commit retains this exact runtime evidence. Continue on the existing branch/PR939. Preview4512 and mock4513 are current; comparison4511 is preserved. Deployment and public forms stay on hold.


## Invalid-email pet reaction, October 9, 2026

Founder approved a subtle rejection reaction and refreshed demo. Runtime `0455fa4c2a7795064ea85b75879c83b09eec52e6` derives a small tilt/blink and fieldward gaze from existing SignupState rejection. Native validation still blocks invalid POSTs; valid correction resets the pose/error. Network and service failures keep the pet calm. Reduced motion uses a still expression. No hand, phone, Business page, API or provider changes.

Build/lint/typecheck, demo boundary test and 49 focused browser checks pass, with one expected touch skip. Independent scoped review is clean. [Personal evidence](../reports/evidence/cuadrao-marketing-touchup/personal-pet/README.md) records exact-source ES/EN desktop/mobile captures, the refreshed clip and test output. Both preview4512 and mock4513 include the change. Demo is reset for founder tryout at http://127.0.0.1:4513/personal. Comparison4511 is preserved.

This new reaction and its evidence are local, unpushed checkpoints. Remote PR939 remains `781e820f5986e1d009bbfb2fb61ffd6ea6912d56` with its earlier green CI; do not apply that CI result to the new local delta. Continue the existing branch, preserve earlier accepted design and wait for feedback on this reaction. No merge, deployment, hosted changes, public forms or real email. Workers stopped; Marketing ownership remains with this thread.


## Reaction accepted for PR update

The founder accepted the invalid-email pet reaction and authorized pushing it to PR939 and obtaining green CI. [Reaction acceptance](../reports/evidence/cuadrao-marketing-touchup/personal-pet/reaction-acceptance.md) supersedes the preceding local-only and pending-feedback instructions. Runtime remains `0455fa4c2`; exact-source evidence is retained. Integration is unchanged at `43fac94de`, with no new overlap and a passing merged-tree modularity check. The final CI result belongs to the publication head and is recorded in PR checks and the terminal verification comment. Deployment, hosted changes, real email and public forms remain on hold.


## Integration preparation, October 10, 2026

The [PR939 reconciliation record](../reports/2026-10-10-pr-939-reconciliation.md) supersedes earlier branch-status and local-only instructions. The accepted design is locked. PR929 landed as `4cb85949b4dea6855971c8268aac1bd1a0cacb01`; PR939 incorporates that remote integration head and the preserved PR929 landing records. Its runtime is unchanged from accepted published head `a706ed2284ad67f959d334baa2d4e0305217ac93`. Review and CI must cover the final reconciliation head before a separate merge slot. PR927 remains held against main. All publication and public-form holds remain unchanged.


## Claude handoff and freeze, October 11, 2026

Durable copy: [PR939 freeze and recovery record](https://github.com/lagarcess/argus/pull/939#issuecomment-6114756187).

Marketing is frozen. The founder-accepted bilingual design is in integration through PR939, including the scroll receipt story, static cropped-wordmark endings, canonical branding/favicon, bilingual phone welcome screen, and signup pet reactions. This is a verified integration outcome, not a published customer website. No new Marketing work or stopped environment repair is assigned.

### Landed source and verification

- PR939 merged as `61a75b2a9c30a06fd6b1d035b626f126df51c57e` from reviewed head `b7ac69db19062d75700ab0331122e1485f76d64b`. The trees match exactly. [Terminal landing evidence](https://github.com/lagarcess/argus/pull/939#issuecomment-6101164111) records clean independent review, zero unresolved threads, and successful exact-merge [CI](https://github.com/lagarcess/argus/actions/runs/38077870513) and [smoke](https://github.com/lagarcess/argus/actions/runs/38077870583).
- PR929 evidence landed as `4cb85949b4dea6855971c8268aac1bd1a0cacb01`. Its three ledger records are represented once in PR939. [PR929 verification](https://github.com/lagarcess/argus/pull/929#issuecomment-6100922536).
- PR927 remains OPEN/DRAFT against `main`, at `9ecd31ff1f919c3d25f48952dd7feb6e508eee12`. Main remains `a9286b21886eb03df7a21f2f4b7d5e79af570679`.
- On this read-only check, remote integration is `a6f1f4b3171837d50c82268effa7a12a83df590e`. That later head is not a new Marketing readiness or CI claim. Do not move or reconcile this frozen lane merely because integration advanced.

### Stopping point and approvals

The nearest started step, preservation recovery accounting, is closed with the limits below. Source, evidence, local notes, branch refs and settings remain preserved. The optional SciPy repair is stopped. Do not restart it merely to tidy an unused environment.

Deployment, hosted changes, real email and public forms remain held. Publication requires approved ES/EN privacy wording naming the actual responsible operator for Meta, plus separate LLC clearance. Do not invent an operator or publish "LLC pending". PR927/main promotion needs its own authorization. Pages-first has not been selected; it would explicitly withhold both forms. Hosted signup/migration/provider acceptance and real-device Safari verification remain future release work, not proof supplied by mocked browser tests.

### Checkout and recovery accounting

- Delivery checkout: `/Users/garces/.codex/worktrees/cuadrao-marketing-delivery/private-alpha-next`, branch `codex/marketing-touchup-delivery`, head `b7ac69db19062d75700ab0331122e1485f76d64b`. The handoff update is local only; no post-merge branch push is made.
- Restored managed chat checkout: `/Users/garces/.codex/worktrees/382a/private-alpha-next`, clean detached head `e09ee0e35b3c92546cf86c47f83b2fdbf10b47af`. The tracked tree matches its pre-archive source exactly. Native restore recovered it after thread archive unexpectedly removed it. Keep this chat and checkout unarchived.
- Saved checkpoint branch `codex/marketing-pr929-ledger-checkpoint` still points to `0767f10fd2f8b160517deea83d0f196247e87310`.
- The restored checkout's `.venv` was known to exist before archive, but its original directory/symlink type and target were not recorded. It was absent after native restore. A new local directory was reconstructed with existing Python3.10.20 and locked main/dev/workflows dependencies. This is reconstruction, not byte-exact recovery. Poetry reported zero installs/updates/removals needed afterward, and `pip check` passed. `scipy.linalg` still fails loading `_spropack` with the macOS zero-fill-section error. No wheel replacement occurred after the stop instruction. This limits future Python/backend work in this old checkout; it does not affect the landed Marketing design.
- `/Users/garces/.codex/worktrees/382a/private-alpha-next/.env` and `/Users/garces/.codex/worktrees/382a/private-alpha-next/web/.env.local` are absent now. Their pre-archive existence and original sources are UNVERIFIED. Do not label them confirmed losses or copy another lane's credentials. No secret values were inspected, copied, generated or reconstructed.
- `web/node_modules`, `marketing/node_modules` and `marketing/.next` under the restored checkout are absent now. Prior presence is UNVERIFIED. These are rebuildable dependencies/output, not confirmed archive losses.
- There is no complete pre-archive ignored-file manifest. Native source recovery does not prove preservation of all ignored state. No non-reconstructible ignored-file loss is confirmed.

### Preserved local notes and evidence

The delivery checkout retains all seven untracked notes: `.audit/marketing-brand-publish.todo.md`, `.audit/marketing-ownership.todo.md`, `.audit/personal-footer-sequence.todo.md`, `.audit/pet-invalid.todo.md`, `.audit/pet-publish.todo.md`, `.audit/phone-locale.todo.md`, and `.audit/pr-939-reconciliation.todo.md`. Their older branch/approval statuses are historical; this handoff and the terminal PR record supersede them. The existing tracked `.audit/marketing-touchup.todo.md` is also preserved.

Recovery logs remain local at `/private/tmp/cuadrao-382a-venv-plan.txt`, `/private/tmp/cuadrao-382a-venv-install.txt`, and `/private/tmp/cuadrao-382a-venv-verify-plan.txt`. They are not a complete archive inventory or a claim of a working SciPy environment.

The durable design source and captures remain in `docs/reports/evidence/cuadrao-marketing-touchup/`, including final polish, phone locale, pet reaction, and the [original-layout archive](https://github.com/lagarcess/argus/blob/b7ac69db19062d75700ab0331122e1485f76d64b/docs/reports/evidence/cuadrao-marketing-touchup/original-layout-archive/README.md). The archive hash still matches `6aa3b6d38c9774ac39ac36c3cb0ee5046266f13b9c53475e3e511090197f48aa`.

The original comparison source remains at `/Users/garces/.codex/visualizations/2026/09/26/01a0de75-29ee-71f0-8f58-0d2bb3934a33/cuadrao-marketing-touchup/canonical/marketing`. The existing extraction remains at `/private/tmp/cuadrao-layout-reference-20261009/cuadrao-original/marketing`. Neither is deleted or rebuilt.

### Ownership and cleanup

The founder owns design approval. This Marketing Lane chat is the outgoing implementation owner; this record is ready for Claude, whose acceptance is not yet confirmed. No separate active Marketing preview/design executor was identified.

No listener is active on comparison4511, preview4512 or demo4513. No lane subagent is running. Processes found in the restored checkout are Codex/ChatGPT node runtimes and MCP tooling, including one unclassified app-owned node process; their non-use is not established, so all remain untouched. No confirmed unused Marketing test process needed stopping.

Permanent deletion candidates: none proposed. No files, worktrees, refs, settings, fixtures, credentials or unique evidence were deleted. No new full-repository copy, service start, product edit, archive action or optional repair was performed during this freeze.


## Polish round, October 11, 2026

The founder resumed Marketing polish, working with Claude, and said work ends at integration: nothing goes to `main`. Every release hold above is unchanged. Nothing here authorizes publication, hosted changes, real email or public forms.

### What changed (all under `marketing/`)

- **Header:** the primary button starts as the sage tint `#e8ede3` and fills with the brand dark green on first scroll (300 ms, instant for reduced motion).
- **Footers:** vertical column dividers, sage or brand-green column headings, a Legal column (Privacidad, plus Términos and Quién es responsable as non-clickable placeholders), the contact email, and a bottom bar with the copyright line. Business is dark; Personal, Contact and Privacy share a light version. Both share one legal column and one bottom bar.
- **Social icons:** TikTok, Instagram and YouTube, behind `CUADRAO_SOCIAL_PREVIEW=1`. Without the flag the row is absent. An icon shows by itself once its link is set in `marketing/lib/social.ts`. X and Threads are not listed until the founder decides.
- **Business hero:** one rotating use-case line under "Cada cuenta. En su sitio." (Spanish and English drafts, paused in a hidden tab, still for reduced motion). The development-stage note and the two section labels "EL PRIMER PILOTO" and "DETRÁS DE CUADRAO" are removed everywhere, as is the "en desarrollo" sentence. The sample-data line stays.
- **Copy:** the limits answer is simpler and kinder; the bio reads "tecnología y datos" and "technology and data".
- **Business inquiry form:** optional role, preferred channel with a validated WhatsApp number, "how did you hear about Cuadrao", a pilot checkbox, a message helper and example, and a quiet counter for the last 100 characters. The new answers become a short Spanish block at the top of the existing `description`; the server contract is unchanged (see the forms contract). The left column no longer moves when WhatsApp is chosen.
- **Phone and privacy:** the line under the form and the privacy notice now say a WhatsApp number may be shared. The next-step line says "Te escribimos pronto…", not a deadline.
- **Personal hand:** the black filler under the ring and pinky fingers now sits inside the bezel line, so no black shows on the screen at 390, 1024 and 1440 px.
- **Mobile:** no horizontal overflow on any page; the header logo, footer logo and pilot checkbox now have 44 px targets.

### Verification at this head

Lint, typecheck, 191 unit tests, a production build with the social flag unset (as CI builds it), and the full browser suite (199 passed, 1 skipped as before, including the accessibility checks on all eight pages). The modularity budget guard reports no violation. Not tested: a physical phone, a real provider, or the hosted site.

### Founder approvals

The founder approved, in chat on October 11, 2026, the new copy of this round (rotating phrases and their English, form labels and helper text, the next-step line, footer labels, the simplified limits answer), the WhatsApp-number privacy wording, the "Cuadrao LLC" footer wording as it appears, and the Business hero direction from the October 8 customer call. This is approval of the source in this PR, not of publication. Unchanged: the footer's Terms and Who-is-responsible entries stay non-clickable until their pages exist; the LLC and operator holds, public forms, deployment, the migration, Render and cutover each still need their own yes; nothing goes to `main`.

The scope above is source only. Reconciling this into the release candidate (#927) is not part of this round.
