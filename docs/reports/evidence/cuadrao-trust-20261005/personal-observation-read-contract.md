# Personal accepted-observation read: proposed contract

Status: conservative engineering direction accepted by root, with source checks and runtime verification still required. Counsel owns the bounded native reader; root retains financial meaning and authorization. Recorded-observation design is already locked. This unit does not complete #820/#824 history, personal net totals, attribution, or insights acceptance.

throughput checkpoint: n/a, read-only investigation

## Decision

Reuse existing API reads. No new route, backend DTO, migration, flag, attribute journal, or second financial projection is needed for raw accepted account observations.

Existing sources already return all required facts:
- GET /financial-accounts and GET /financial-accounts/{id}: current account metadata, server currency/exponent, accepted opening fields and audit revisions. Owners: src/argus/api/routers/financial_accounts.py:66–86; recording/schemas.py:123–145,168–197.
- GET /financial-accounts/{id}/balance-checks: accepted checks/value updates, revision, kind, observed_amount_minor, as_of, time_zone, recorded_at, author; paginated, newest reviewed version first. Owners: financial_loop.py:284–309; loop_reads.py:55–71; loop_schemas.py:131–165.
- Optional asset account.asset.estimates already includes the same accepted opening/value-update observations plus audit revisions. Do not independently concatenate these with checks and double-count them. The uniform opening + check-page route is sufficient for every account kind.
- GET /financial-home provides the authoritative FinancialHomePeriod month/time_zone/start_at/end_at_exclusive. Reuse it, rather than inventing a second month boundary calculator. Existing financial-home read is owned by BudgetService.home -> planning.storage.read -> recording.loop_reads.home_response.

## Minimal internal value

A native read-only value, not a new wire API:

PersonalAccountObservations {
  accountID, accountVersion,
  currency, currencyFractionDigits,
  currentMetadata { nickname, type, archived, ownershipShareBps, updatedAt },
  observations [{ recordID, revision, kind, amountMinor, asOf, timeZone, recordedAt }],
  period { month, timeZone, startAt, endAtExclusive },
  openingObservation?, closingObservation?, comparisonState,
  readState
}

Amounts are signed raw account minor units. Neither observations nor comparisons multiply by current ownership share or derive historical kind allocation. The metadata wrapper explicitly says current. No generic balance/position or net-worth name is used for this raw series. Existing current Home balance remains unchanged.

The opening is opening's accepted top-level revision, not opening.revisions as extra plotted points. Checks are already accepted current revisions. Past audit revisions remain audit evidence only. No transaction-derived points, future Plan points, now point, interpolation, or synthetic zero are added.

## Read ownership and consistency

Extend the existing FinancialLoopModel per-account read owner with a dedicated observations operation. Do not use open(), which fetches activity unnecessarily, or create another session/transport owner. Reuse SessionController.financialChecks and its existing identity-bound transport; reuse the existing account GET transport for version verification.

For one account:
1. Read fresh account A through the current session owner.
2. Fetch every check page, preserving the server review-order across pages.
3. Read fresh account B through the same owner. Publish only if ID/version/currency agree with A, all pages completed, and the session generation/profile/request still matches.
4. Otherwise expose stale/incomplete/unavailable, no derived comparisons. Do not silently reuse another account's pages or old-profile data. The caller may explicitly refresh; no unbounded automatic retry.

Each existing repository account read owns a repeatable-read transaction. PostgresFinancialAccountRepository.list_accounts/get_account/_load and loop_postgres.hydrate load canonical observations. Check cursor pins account version and rejects stale subsequent pages. Bracketing equal monotonically increasing account versions prevents mixing independently fetched opening/check generations, including first-page mutations. There is no shared cross-account snapshot and none is claimed.

Keep archived accounts in the personal source selection. Existing list_accounts has no archived filter; API_CONTRACT.md:7017 locks inclusion in position totals. Existing AccountsModel may filter display rows, so use its complete source list rather than the visible active-account subset. This operation is PERSONAL only; no household get_any_account reader or grants are introduced.

## Period selection

Use parsed instants, preserving original observation date and IANA zone in the result. Period is half-open [startAt,endAtExclusive).
- Opening: latest accepted observation with asOf <= startAt, if available. If absent, use the earliest accepted observation within the period as the actual baseline, and mark comparisonState=partialBaseline; never label it a full-period opening.
- Closing: latest accepted observation with asOf < endAtExclusive, including a dated prior observation when the interval is empty. Never use an observation after the selected period.
- If no eligible fact exists: unavailable amount, no comparison.
- If opening and closing select the same record/revision: known dated fact, comparisonState=singleObservation, no difference claim. Do not emit a fabricated zero change or flat line.
- With two distinct eligible facts: raw difference uses checked Int64 subtraction, retaining both dates and IDs. No income/return/earnings classification. Arithmetic overflow yields unavailable comparison, not a wrap or clamp.
- Equal-date facts retain the server's accepted review order; opening precedes checks at the same instant. Preserve list ordering as tie provenance rather than guessing from record UUIDs or correction recorded_at. Check API currently orders by reviewed_version; this order must be covered by a fixture.
- Period range controls beyond an existing server-issued period are out of this unit. No invented week/year calculator.

## Authorization and side effects

Reuse require_financial_accounts_context: surface flag before auth, current registered user, guest/conversion denial. Existing service.get/repository._load restrict by account ID + user_id and return the same 404 for absent/foreign IDs. Native requests use existing SessionController expectedIdentity. Binding changes clear in-flight results. All operations are GET; no financial writes or provider calls occur.

## Proposed edit ownership and budget

Native owner only, coordinate with #824 presentation owner before touching FinancialLoopModel:
- NEW ios/ArgusFoundation/Accounts/FinancialObservationRead.swift: internal normalized facts and pure period selection, target <=160 lines.
- ios/ArgusFoundation/Accounts/FinancialLoopModel.swift: small identity/generation guarded orchestration into existing accountReads or a dedicated per-account value, target <=65 added lines; extract helper if its existing budget is tight.
- ios/FinancialModelTests/FinancialModelTests.swift or a registered sibling test file: boundary/model tests, target <=200 lines using shared fixtures rather than copies. Prefer sibling to avoid growing the existing large file.
- Existing ios/Packages/ArgusSession/Sources/ArgusSession/FinancialLoopTransport.swift and FinancialAccountTypes.swift should need no edits. Confirm existing account GET method visibility before implementation.
- Backend source should need no edits. If tests prove a required wire fact truly absent, report the exact absence before proposing any additive DTO.
- Docs/evidence: one bounded contract/evidence record, <=100 prose lines. Combined-tree modularity check remains mandatory before merge.

Expected slice <=4 source/test files and <=425 new lines; no chart/palette/layout changes, no temporal attribution workaround. Independent review covers the source adapter and its stale-session/pagination behavior. No overlapping Mac run until root grants the scheduler slot.

## Verification plan, not executed

- Pure cases: corrected opening selects accepted revision only; corrected value update; no opening; one observation; inside-period baseline; empty month with dated prior fact; later fact excluded; same-date review ordering; archived account; negative/zero raw amount; USD/JPY/KWD server exponents; overflow comparison; original stored zone preserved.
- Model cases: multiple pages, version changes before/between/after pages, cursor conflict, request interruption, account A -> B, identity A -> B, sign-out while GET waits, forbidden GET returns no protected data, partial page failure never becomes complete history.
- Reuse actual backend acceptance files tests/financial_accounts/test_api.py, test_loop_api.py, test_assets.py; real local Postgres tests/test_financial_accounts_api_postgres.py and tests/test_financial_loop_postgres.py for current accepted correction/readback and owner/guest denial. Add cases only for a demonstrated uncovered boundary; no mirrored implementation tests.
- Compile native source and run focused FinancialModelTests under root scheduler. Physical device and hosted gates remain open. No provider calls needed.

## Remaining technical checks

1. Confirm AccountsModel stores an unfiltered complete account source and exposes fresh account GET without introducing a second cache.
2. Confirm existing native decoder accepts all server date offset/precision variants; use existing decoder/parser owner.
3. Confirm same-date check order and version monotonicity for every correction writer, including value-update correction.
4. Agree a finite pagination resource bound. Recommended engineering cap: stop with explicit incomplete state after a bounded page count; never report partial fetch as complete. Do not silently impose a product history-retention period.
5. This unit delivers raw per-account recorded facts. To wire the approved aggregated Home chart, historical ownership and account classification evidence remains a separate required foundation contract. Existing shares/kinds must not be projected backward.

Reviewed at source HEAD 66d70570bd2342e04de1d2f91d2ce727070e1080. No relevant source differences from requested a2c65549. No repository edits, local records, services, tests, or builds.

## Source handoff update

Existing design already selects recorded observations. Counsel verified version advancement, pinned pagination, archived inclusion and existing ISO parsing. A newer same-local-day check can have an earlier clock time; unsupported ordering yields unavailable comparison, never a guessed closing fact. The 64-page engineering cap yields incomplete state without claiming a retention period. The return-valued model operation adds no second result cache. Root owns the remaining historical type/share provenance gap; raw facts do not complete the aggregate Home chart or insights.
