# Connected Search independent review

Reviewed SHA: `b5188adfd70ce985204b5106fc712977a9ae755c`
Base: `22f9c8cda8a65c74985e367d8cef68e55515e16b`
Verdict: two actionable P2 findings; not clean yet.

This was one focused, read-only review. I read AGENTS.md, documentation authority, the manifest Search assignment, MVEE Search requirements, the connected financial API contract, implementation, and relevant tests. I did not operate a simulator, service, database, credentials, device, or provider. Reproductions below are established by code-path tracing, not a separate live execution. Captain-provided test results were not rerun. `git diff --check` passed. Repository files were not changed.

## P2: Keep Search account navigation independent of Accounts selection

Location: `ios/ArgusFoundation/Search/FinancialSearchView.swift:72-75` (also `FinancialSearchModel.swift:128-131`).

Search retains `.account(A)` but only renders it while `accounts.selected` still equals A. Opening Search assigns the shared Accounts selection. Accounts Back clears that selection; opening B replaces it. The shell keeps every tab mounted, so these mutations immediately affect the retained Search destination.

Reproduction: open account A from Search; switch to Accounts; tap Accounts Back (or select B); return to Search. The existing authorized A now shows `search.destination.unavailable`, without a retry, because a different tab changed its selection. This is a false missing-record state and breaks connected navigation. Opening A from Search also overwrites any retained Accounts selection.

Fix must account for the shared detail activity owner as well as the label lookup: `AccountActivityView` reads the single `loop.activity/checks` arrays, and `FinancialLoopModel.open` only accepts results matching `accounts.selected`. Merely resolving A independently from `accounts.accounts` would leave simultaneously mounted A/B detail surfaces reading one activity collection. A bounded navigation/presentation ownership fix should avoid conflicting account-detail owners and retain Search origin on return. Verify Search A -> Accounts Back/B -> Search, and the activity rows/actions of whichever detail is visible.

## P2: Retire pending destination opens when the search origin changes

Location: `ios/ArgusFoundation/Search/FinancialSearchModel.swift:57-63`.

Updating the query, kind, or currency rotates only the list request token. It does not rotate `detailRequest` or clear `opening`. The input and filter controls remain enabled during `open`, whose completion checks only `detailRequest` and session identity. Therefore a slow result open from the old query remains authorized to publish after the user changes the Search context.

Reproduction: delay the account-detail read; tap result A; while the loading indicator is visible, change the query or category; allow the old detail response to complete. Search opens A over the new query/results. With an expectation, the same path presents the old expectation editor. Until the obsolete request finishes, current rows are also disabled by `opening`. This violates the current-request guard and origin-preservation behavior.

A small fix can retire pending detail work and release its loading state on origin changes (with generation guards keeping old completions inert), or consistently prevent origin changes for the whole opening interval. Verify a delayed destination response cannot navigate or present an editor after a newer origin is selected.

## Other reviewed boundaries

No additional actionable backend ownership, cursor isolation, canonical money/projection, or persistence findings in this pass. Search uses the existing owner gate and current logical activity projection; its documented full-owner snapshot loading limitation is stated honestly. Native model tests cover list-result races and relaunch, but do not cover the two destination/navigation cases above. No claim is made that the captain's in-progress native acceptance or later commits have been reviewed.

## Affected-fix follow-up: 68c45b8f0

Scope: only `b5188adf..68c45b8f0`, covering independent account navigation/cache reads, pending destination retirement, immutable scroll restoration, the Search accessibility container, and affected tests. No full re-review of unchanged code. Read-only restrictions remained in force; no tests, simulators, services, or databases were operated. Diff whitespace check passed. Captain reports 18 model tests and generic build passing; exact-head native acceptance remains captain-owned.

The two original P2 findings are resolved in code. Search uses a destination ID against the canonical account cache; Accounts selection is separate. Account activity/check state and request guards are keyed by account ID, so simultaneously mounted details do not overwrite each other's rows or cursors. Query/filter changes retire the detail token, clear opening state, and reject old account/expectation completions. Restoration now keeps the saved anchor immutable during initial layout. No additional actionable finding in that restoration/accessibility delta from source review; native geometry proof is still required.

### P2: Recover the account acted on, not the Accounts tab selection

Location: `ios/ArgusFoundation/Accounts/AccountsModel.swift:183-185` (related call at `125-130`).

The independent-selection fix changes Search to upsert A without selecting A, but the generic no-draft error recovery still fetches `selected.id`. Consequently, archive/restore from Search acts on A while its conflict/ambiguous-write recovery reads B, or reads nothing if Accounts is at its list. This is a directly affected consequence of the selection fix: previously Search set the selection to A, so the fallback fetched A.

Reproduction: keep Accounts selected on B; open A from Search; change A's version externally or arrange an accepted archive response to be lost; archive/restore A. On 409 or ambiguous 5xx, `run` re-reads B. A remains at its old version/status in the canonical cache. A retry submits the stale version again and cannot reconcile the result without leaving and reopening the Search detail. Backend optimistic concurrency prevents incorrect writes, but recovery on the active Search record is broken.

Bounded remedy: make archive/restore recovery carry the operation's account ID independently of navigation, while preserving B's selection. Verify a stale-version or accepted-but-response-lost archive on A refreshes A and leaves B selected. This does not require a new persistence owner or a navigation reset.

Follow-up verdict: original findings closed; one related P2 remains, so this delta is not yet clean.

## Final affected-fix follow-up: 12ade77d98ac74864ad05ca629548be055e89452

Reviewed only `68c45b8f0..12ade77d9`: operation-target recovery, shared account error/busy/retry presentation, repeated Search control no-op behavior, and their tests. Exact reviewed SHA is `12ade77d98ac74864ad05ca629548be055e89452`.

Verdict: **clean affected-fix review; no remaining actionable findings from this review.** All three recorded P2 findings are closed.

Archive/restore now passes its own account ID to `run(targetAccountID:)`, and recovery fetches that ID independently of Accounts navigation. Detail Retry calls `refresh(account.id)`, which upserts without selecting. Shared detail status exposes errors and busy state on the active owning screen. The new regressions cover archive and restore under 409/503 responses while retaining a separate Accounts selection and verify the recovery/read request targets.

Search updates now compare the requested origin with the existing origin before clearing anything. Re-selecting the current query, kind, or currency preserves results, loaded pages, cursor, and scroll origin; actual changes still retire obsolete requests and clear the old result set. The model regression covers both the no-op and changed-filter paths. The native fault-delay adjustment changes test observability only.

`git diff --check 68c45b8f0 12ade77d9` passed. This remained a read-only source/test review. Captain reports 20 model tests and native build passing; I did not rerun them or operate the simulator, services, database, device, credentials, or providers. Exact-head native acceptance, CI/reconciliation, and release authority remain with the captain/founder; this verdict does not claim those gates completed.

## Restoration delta follow-up

Exact reviewed SHA: `b304c2f529fe770934f8c87892ff314deb7a292b`.
Delta: `12ade77d98ac74864ad05ca629548be055e89452..b304c2f529fe770934f8c87892ff314deb7a292b`.

Verdict: **clean affected-fix review; no actionable findings in this delta.** Prior closed findings remain closed. Unchanged code was not subjected to a new full review.

The loading/opening indicator is now an overlay rather than a row inside the result stack, so showing and removing it no longer changes result-row geometry. Restoration retains its immutable target when an unchanged anchor is temporarily constrained by layout, rather than declaring success at an intermediate content boundary. Explicit dragging releases pending restoration, allowing subsequent visible-row observations to own the saved origin. When the original anchor disappears, the existing surviving-row selection is retained and boundary fallback is permitted; an empty result explicitly clears obsolete restoration. Request/owner guards and query-change retirement remain intact.

The new model tests exercise delayed layout completion, removed-anchor boundary fallback, explicit-scroll cancellation and persistence, and empty-result cleanup. Native assertion changes add failure geometry and screenshot diagnostics without weakening the existing three-point tolerance. The generated OpenAPI additions match the two already-reviewed GET routes and their typed response schemas; no new runtime endpoint behavior is introduced by this delta. The manifest/review publication accurately attributes the earlier clean verdict to its earlier exact SHA and leaves assembled acceptance/CI pending.

Verification performed here: read-only source/test/contract inspection and `git diff --check 12ade77d9 b304c2f52` (passed). The captain reports 22 model tests and a generic native build passing and is rerunning native geometry/recovery acceptance. I did not rerun tests, operate services/simulators/databases/devices, inspect credentials, or modify repository files. This review does not claim the in-progress native acceptance or remaining release gates completed.

## Final measured-scroll follow-up

Exact reviewed SHA: `c775b0cdd1e05f4088fd9eb5d0ccf798d50882a4`.
Review scope: net delta from `b304c2f529fe770934f8c87892ff314deb7a292b` only.

Verdict: **clean affected-delta review; no actionable findings.** Earlier closed findings remain closed.

The runtime delta eagerly measures the already loaded Search rows with `VStack` and removes `ScrollViewReader`/`scrollTo`. The existing `UIScrollView` restoration code is now the sole owner of offset adjustment. The deferred completion path retains the restoration-token guard, requests layout, and uses the same measured-row adjustment as preference updates. This directly addresses the captain's demonstrated underestimated lazy content height and competing offset writes. It does not change backend loading, pagination, query state, identity guards, or money behavior. No temporary logging remains in the net diff.

The targeted native test now starts from an explicit fresh sign-in and checks the same row position across two successive relaunches. It retains the existing position tolerance and failure diagnostics; it does not relax acceptance. Eager layout applies to retained loaded pages, so it is a proportional local geometry fix for this bounded Search lane; this review does not infer a new large-dataset performance requirement.

`git diff --check b304c2f52 c775b0cdd1e05f4088fd9eb5d0ccf798d50882a4` passed. Review was read-only; no repository files, tests, simulator, services, credentials, or device were operated. The captain reports repeated-relaunch acceptance passed at `89747bb51` before diagnostic cleanup and is recording the final editor journey. This review does not claim final-head native acceptance, CI, or release gates completed.
