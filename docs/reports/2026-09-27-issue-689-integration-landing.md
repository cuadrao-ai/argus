# Issue #689 integration landing

## Landed change

- PR: [#711](https://github.com/lagarcess/argus/pull/711)
- Approved PR head: `58a080006b1f8530a69e72992273afb2ebb7ed41`
- Original and final pre-merge integration: `61ef59d12f0f38ab3df507712e02f17991bedced`
- Squash merge: `ed6d9b2b53bbb5366bfe5a452249ba2cd7e2bbb1`
- Merge time: September 27, 2026, 16:20:50 UTC
- Integration parent: `61ef59d12f0f38ab3df507712e02f17991bedced`
- Reviewed and landed tree: `6860a3d9f7f1464421328007da753263253f7e42`

The founder authorized this merge only with unchanged head/gates. The head,
passing checks, resolved review threads, and clean canonical integration
checkout were verified immediately before the conditional-head squash merge.
The canonical checkout then fast-forwarded cleanly. There were no intervening
integration changes or semantic overlap, so accepted lane evidence is retained.

## Outcome and remaining work

Grounded inline and background research answers no longer enter shared storage.
Eligible public discovery packets use one versioned identity derived from the
actual provider query. Legacy entries and queued job keys cannot bypass the
new boundary. The private-context and changed-public-dimension regressions are
recorded in the [reproduction report](evidence/689/reproduction.md).

Issue [#689](https://github.com/lagarcess/argus/issues/689)'s cross-user answer
reuse defect is delivered. The chosen bypass addresses omitted dimensions
without treating hashed private text as public data.

At landing time, issue [#712](https://github.com/lagarcess/argus/issues/712)
remained open as separate, founder-retained work: current-turn provenance can
unnecessarily bypass public discovery caching, increasing cost and latency. It
was confirmed and tracked after the terminal clean review under AGENTS.md's
late-finding rule; it is not repaired or hidden by this landing. No #710
logging work was incorporated.

## Accepted evidence and exception

- Research suite: 886 passed; mocked eval harness: 272 passed.
- [Ready-for-review CI](https://github.com/lagarcess/argus/actions/runs/36331993453): success, including 9,223 backend tests, frontend checks, and disposable PostgreSQL/auth guest gates.
- [Runtime regression](https://github.com/lagarcess/argus/actions/runs/36331993515): 2,750 passed.
- [Exact-worker smoke](https://github.com/lagarcess/argus/actions/runs/36331862871) and [PR merge-ref smoke](https://github.com/lagarcess/argus/actions/runs/36331993461): passed. The merge-ref tree also matches the landed tree.
- The founder approved only the 390 pre-existing Ruff diagnostics in 63 unchanged files for this PR. Fresh comparison proved all 63 files identical to the integration base. No new-error waiver or repository-policy change applies; CI-scope lint passed.
- The [terminal audit](https://github.com/lagarcess/argus/pull/711#issuecomment-5853691749) preserves command failures, review dispositions, and the bounded approval.

## Documentation and environment audit

The API cache contract was updated in #711. This landing adds its integration
register entry and this report. The older roadmap is an archived narrative,
so its history is retained rather than rewritten as a current assignment.
No additional plans need archival. The runtime diff adds no environment names,
feature flags, migrations, hosted settings, or tracked-template requirements.
No ignored environment file or secret value was changed.

The housekeeping diff is documentation-only. Its final SHA, clean local/remote
parity, and exact-head integration CI/smoke results are recorded in the merged
PR's landing-completion comment after the checks reach terminal state; this
report does not anticipate those results.

## Authority boundary

This checkpoint stops at `codex/private-alpha-next`. No main promotion,
deployment, hosted configuration change, customer-data access, paid evaluation,
live provider call, or tester exposure is part of this landing.
