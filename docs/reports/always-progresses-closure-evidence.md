# Always Progresses Closure Evidence

Status: **BASELINE COMPLETE ON INTEGRATION — PR #268 merged as `847c413b`;
STANDING QUALITY BAR ACTIVE**

Post-merge qualification: this ledger proves the bounded acceptance matrix. A
later same-conversation stress audit found additional long-chain exploration
gaps without invalidating the exact journeys recorded here. Those observations,
attribution limits, and issue-intake groups are recorded in
[the 2026-07-25 post-merge stress audit](2026-07-25-always-progresses-post-merge-stress-audit.md).
No fix or GitHub issue is authorized by that report.

A separate guest-lane post-integration check reproduced an ordinary starter
runtime failure after the guest branch absorbed this integration checkpoint.
That signal is recorded in
[the guest runtime regression observation](2026-07-25-guest-post-integration-runtime-regression.md).
Its cause remains unassigned; this ledger must not be used to blame either the
integration runtime or guest code before the bounded differential diagnosis.

Reviewed PR head: `5585c6a7a328f65f9a36b2f004e79e1c1d761b55`

Final authorized real-Run HEAD: `e73350f065f9b258d0927b735123f73e21af617e`

Integration squash merge: `847c413b3c3fe90d9b17e0aeb79b16c0c1a15b72`

Recorded locally: 2026-07-25

This ledger separates production-parity browser evidence from deterministic
exact-current-head evidence. The final real backtest was founder-authorized
only at clean HEAD `e73350f`; later corrections were browser-found continuity
fixes and were verified without another real Run. Private traces and
screenshots are named for local correlation but are not committed.

## Integration and workflow preflight

- The completed integration merge is
  `37591fed4a77b7b65495a6f595946366dcbab7fb`, with parents
  `ac4eb1612d4dc356599bdd8a8aa222f0d3d33b40` and
  `d6d1134ddbec34462fc4d7487ed1a58d4a41c5f1`.
- The final-Run lane used isolated Supabase API/database ports `57531/57532`,
  backend/frontend/workflow ports `8721/3721/8740`, and a fresh normal,
  non-admin QA identity.
- Before the browser opened, the backend effective environment was verified
  from its running process without printing credentials:
  `CUADRAO_PERSISTENCE_MODE=supabase`,
  `ARGUS_DEV_MEMORY_FALLBACK=false`,
  `ARGUS_MARKET_DATA_PROVIDER_MODE=live_provider`,
  `CUADRAO_CHECKPOINTER_MODE=postgres`, `CUADRAO_MOCK_AUTH=false`,
  shadow/dispatch/workflow execution enabled,
  `RENDER_USE_LOCAL_DEV=true`, and
  `RENDER_LOCAL_DEV_URL=http://127.0.0.1:8740`.
- `.github/workflow-proof.sh` ran in local mode against that same workflow
  server and isolated database. Workflow job
  `48f54028-ddc9-43d6-8036-2e09f6d498b7` reached durable terminal success
  through task `trn-d9iius6gnqfrimulpj4g`.

## Founder-visible journey ledger

| Journey | Result and evidence |
| --- | --- |
| 1. Clarification to result | **Pass.** Traced headed Playwright CLI session `argus-task8-e73350f-final` resolved `page.getByTestId("edit-execution-costs")` exactly once. The element was a `BUTTON`, `type=button`, accessible name `Edit costs`, inside the intended AAPL / $10,000 / Jan 3, 2023-Dec 31, 2024 / daily / SPY / no-cost confirmation. Screenshot `edit-target-card-before.png` recorded that identity before activation. The editor visibly applied 0.10% fees and 0.05% slippage; the old card was superseded and the replacement confirmation preserved every fact. Only then did `page.getByRole("button", { name: "Run backtest", exact: true })` resolve once and receive exactly one click. Job `2b76e05d-019e-4daf-b0d1-6e14e621cb83`, workflow task `trn-d9ij2k6gnqfrimulpj50`, and immutable Run `7080fcca-b4e8-52c1-acaa-c3ae5cf9a019` succeeded. One job, one Run, one result, one `backtest_runs` usage settlement, and one result-summary receipt/cost settlement were durable. The result retained costs and all launch facts; Quick take (+99.9% vs SPY +53.6%) and result identity survived reload. Trace `trace-1785016293730.trace`; screenshots `run-target-card-before.png` and `journey1-result-after-reload.png`. |
| 2. Clarification loop break | **Pass.** Conversation `a18665f5-2416-498f-9fbd-2ebdc313de60` answered an unresolved date request with “Use a reasonable period.” The typed terminal was `no_progress`; AAPL, $25,000, SPY, and daily survived while dates remained unset. Exactly one Provide missing detail, Keep idea unchanged, and Cancel action appeared; Run, job, and backtest Run counts stayed zero. Reload on product HEAD `d6b57f3` preserved the three actions exactly once. Traces `trace-1785021125094.trace` and `trace-1785021567780.trace`; screenshots `journey2-final-head-no-progress.png` and `journey2-d6b57f3-reload.png`. |
| 3. Ordinary-turn interruption and Retry | **Pass.** Spanish conversation `5fb32aed-9a6f-4460-b09a-98c2f532dc7a` persisted failed turn `2bb89c73-803e-4836-8f3f-8f18e342a3b0` as `recoverable_failed`, attached one `Reintentar`, and created no Run, receipt, or usage charge. After reload and normal-backend restoration, one strict `Reintentar` click completed retry `e1290955-bd5e-42ae-bbfb-7f7e1f70989d`. Success appeared once and survived reload. Hour/day chat usage both equaled one; eight route receipts and eight cost rows appeared only after the successful retry. Trace `trace-1785020561314.trace`; screenshots `journey3-spanish-recoverable-failure.png` and `journey3-spanish-retry-success.png`. |
| 4. Ambiguous Run response | **Pass.** The same Journey 1 job/Run/result identity was inspected after reload. There was no second execution or settlement. The deterministic current-head browser harness also asserts exactly one `run_backtest` submission and exactly one reloaded result. |
| 5. Stale action and replacement | **Pass.** An old confirmation Run authority was submitted through the authenticated browser API after replacement and was rejected before compute. The current confirmation stayed intact; job and Run counts for that stale submission stayed zero. Trace `trace-1785019660298.trace`; screenshot `journey5-stale-run-rejected.png`. |
| 6. Result-based continuation | **Pass.** Refining completed Run `7080fcca-b4e8-52c1-acaa-c3ae5cf9a019` produced a new AAPL confirmation for Jan 3-Dec 31, 2024 with $10,000, SPY, and daily preserved. The new Run control was never clicked. The original Run remained immutable; aggregate counts stayed one job, one Run, and one IdeaVersion. Trace `trace-1785020264219.trace`; screenshot `journey6-refined-confirmation.png`. |

The final Run failure rule was not triggered: the sole final authorized click
passed. No fourth Run was attempted or authorized.

## Browser mechanism and current-head preservation

The replacement mechanism was the repository Playwright CLI backed by headed
Chrome, with action/network tracing enabled before navigation. Strict locators,
element-count assertions, DOM identity checks, confirmation-card containment,
and a pre-click screenshot proved the Edit costs button rather than its adjacent
Run action was activated.

After the authorized `e73350f` Run, product corrections were limited to the
browser-reproduced no-progress/result-refinement continuity boundaries,
modularity-preserving frontend composition, and the internal-review correction
described below. No later real Run occurred. On the final candidate:

- the final Journey 2 recovery UI survived reload;
- a zero-Run edited-cost replacement confirmation preserved its facts before
  and after reload (`final-head-preservation-replacement-confirmation.png`,
  `final-head-preservation-after-reload.png`,
  `trace-1785019394349.trace`);
- Spanish Account Security rendered exactly one password control and each of
  the three session controls, no Run control, and the same state after reload
  (`task8-security-spanish-d6b57f3.png`,
  `trace-1785021776585.trace`).
- interrupted ordinary turns keep one request-correlated, owner-scoped Checking
  path until durable completion, failure, or abandonment; navigation cancels
  the reads, and correlation/read exhaustion falls back to the existing
  same-conversation load Retry without replaying the turn or inventing runtime
  failure.

## Deterministic current-head browser harness

`web/e2e/always-progresses.spec.ts` is a zero-provider, zero-paid harness over
the real chat UI. It proves:

- clarification before confirmation;
- Edit costs opens `execution-cost-editor` without a chat request or
  `run_backtest`;
- applying 0.10% fees and 0.05% slippage creates a replacement confirmation;
- only the latest edited confirmation is submitted;
- exactly one Run action is sent;
- one result and Quick take remain after reload.

Exact focused result:

```text
NEXT_PUBLIC_MOCK_AUTH=true \
NEXT_PUBLIC_ARGUS_API_URL=http://127.0.0.1:9/api/v1 \
PLAYWRIGHT_PORT=3201 \
PLAYWRIGHT_REUSE_EXISTING_SERVER=false \
bunx playwright test e2e/always-progresses.spec.ts \
  --project=chromium --workers=1 --reporter=list

Result at `cadb175`: 1 passed (5.2s)
```

## Integrated verification

| Gate | Exact result |
| --- | --- |
| Hermetic runtime/spine/admission/reload/jobs/state-machine/mocked-eval matrix | `1521 passed in 16.07s` with dev-mode export, provider keys blank, and `synthetic_unit_fixture` |
| Disposable PostgreSQL lifecycle | `38 passed` against `postgresql://127.0.0.1:57532/postgres` |
| Canonical modularity | `scripts/check_modularity_budget.py` passed; `interpret.py` 3232/3234 lines and `ChatInterface.tsx` 2583/2598 lines |
| Full frontend | `502 pass, 0 fail` |
| Frontend lint and production build | passed |
| Chart/Security/Usage focused units | `72 passed` |
| Chart and Usage Playwright | `12 passed` |
| Capability-truth deterministic regression | `60 passed` across future-performance admission, unsupported honesty/conservation, and capability registry |
| Security browser journey | Spanish controls and reload passed; Run count zero |
| Always Progresses deterministic browser harness | `1 passed` |

The first integrated deterministic invocation accidentally inherited local QA
environment values and failed quickly. It was classified as local environment
leakage, not product evidence. The corrected invocation explicitly called
`argus_export_dev_mode`, blanked provider keys, forced
`synthetic_unit_fixture`, and produced the 1,521-pass result above.

## Internal review disposition

The final whole-branch internal review found one Important reachable issue:
ordinary stream interruption stopped durable reconciliation after two reads
and could leave Checking static until reload. The bounded correction:

- shows Checking before reconciliation and keeps the composer locked only while
  durable state remains unresolved;
- continues exact request-correlated owner reads near the 120-second runtime
  deadline and just beyond the existing 15-minute stale-turn boundary;
- hydrates later terminal truth automatically;
- cancels on navigation/unmount;
- maps uncorrelated, failed-read, or exhausted resolution to the existing
  same-conversation load Retry without inferring failure or replaying the turn.

Mutation-catching red tests proved the old two-read stop and locked exhaustion.
The corrected focused suite passed 55 tests; full frontend passed 502; lint,
build, modularity, diff check, and the deterministic browser harness passed.
Two delta reviews cleared the terminal path and then the exhaustion boundary
with no remaining Critical, Important, or Minor finding.

## Review, publication, and integration disposition

- The sanctioned interpreter eval passed `27/27` at product head `7750a247`.
  Later corrections through `5585c6a` were confined to transport,
  persistence, dispatch metadata, and durable Run-message identity; they did
  not change interpreter prompts, routing, tiers, or capability behavior.
- Independent whole-branch review cleared the product candidate. Codex Cloud
  review then found two reachable P2 defects: post-dispatch metadata failure
  could terminalize an already-dispatched job, and ambiguous Run replay could
  persist a second action message. Both were fixed at `5585c6a`, covered by
  focused backend/frontend, workflow, trajectory, disposable-Postgres, and
  zero-provider browser checks, and their review threads were resolved.
- Final GitHub CI at `5585c6a` reached terminal green with 11 successful,
  zero failing, and zero pending checks.
- PR #268 merged into `codex/private-alpha-next` as `847c413b` on
  2026-07-26. The reviewed PR head and squash-merge trees are byte-equivalent.

## Remaining external gates

- This ledger closes the founder-visible **Argus always progresses** product
  pillar at the integration checkpoint.
- Render canary, deployed-browser proof, tester exposure, promotion to `main`,
  and production deployment remain separate founder-directed release gates.
- Issue-specific acceptance that exceeds this pillar remains open rather than
  being implied complete by the merge.
