# Shared Home history contract audit

Source-only audit, October 5, 2026. Integration inspected:
`13a1a339cbab1a3896e10779477658af63e062b3`. Recovered UI inspected at the
assigned immutable source `1f8a716e7cb89bb9e78f4575f39d7c8dca0790df` using
`git show`; its checkout has since advanced, so this report does not certify
that checkout's current head.

## Finding

Current Home amounts have a canonical read contract. Attributed Home historical charts and complete-period spending comparisons
still lack their full connected contracts. Existing personal account/check APIs
already expose raw accepted observations; no new server payload is needed for
that bounded native read. A current known balance does not establish earlier balances, and a
balance check does not establish complete spending coverage.

The captain reports that #824's #838 rolling-30-day Upcoming and #839 movement
detail/swipes landed, while full history, insights, coverage and move-history
remain untouched. This report did not independently read GitHub. #824 remains
Counsel's presentation lane; SharedFoundations #820 read-contract coordination
remains with the root captain. Neither issue is closed by this audit.

## Locked behavior and current contracts

| Fact | Verified source at integration |
| --- | --- |
| No currency conversion or blended total; primary first; one chart/comparison currency | `docs/specs/argus-minimum-viable-ecosystem-experience.md:267-274` |
| Opening/check facts are distinct from activity; discrepancies stay visible; a known balance can coexist with incomplete transactions | MVEE `368-394` |
| Confirmed complete month with no spending is zero; missing coverage is Sin datos; earlier zero uses an amount difference | MVEE `885-887`; `docs/specs/argus-decision-log.md:248-258` |
| Recorded-position observations, matching debt signs/shares, no fabricated history or borrowed observations after currency/kind/share changes | `.agent/designs/cuadrao/DESIGN.md:257-267` |
| Actual opening/closing dates, signed same-scope account contributions, one observation without comparison, explicit partials, no later-data substitution | Cuadrao DESIGN `390-404` |
| Monthly recorded-only spending uses an explicit reporting zone and half-open interval; refunds use return month; transfers/card payments excluded; loan costs count, principal excluded | `docs/API_CONTRACT.md:7250-7264` |
| Current positions use ownership shares; activity uses full amounts; archived accounts remain in summaries | API contract `7261-7264` |
| Observation coverage binds exact observation/activity revisions and retains earlier choices; it is not a whole-period completeness claim | `docs/DATA_MODEL.md:1963-1970`; `src/argus/domain/recording/loop.py:83-88,136-149` |

These are approved semantics, not proof of implemented historical charts.
`docs/DOCUMENTATION_AUTHORITY.md:18-30,68-83` keeps product direction, technical
contracts and implementation assignments with their separate owners.

## Narrow source owner map

| Owner/path | Existing truth | Missing surface |
| --- | --- | --- |
| `src/argus/domain/recording/loop_reads.py:148-248` | Current per-currency amounts, known/unknown counts, freshness, monthly spending, five recent activities | No historical points, gap/partial status or complete-period evidence |
| `src/argus/domain/recording/loop_schemas.py:187-225` | Home response, period and literal `recorded_only` coverage | No Home aggregate-series/complete-period response; per-account APIs already expose observations |
| `src/argus/domain/recording/records.py:25-45`; `loop.py:15-100,102-149,152` | Dated opening/check/activity records, zones, revisions, author/recording provenance and reconciliation links | No historical aggregate projection or sampling policy |
| `src/argus/domain/recording/money_home.py:11`; `spending.py:19` | Reporting interval and canonical spending classification | No complete-period confirmation |
| `src/argus/domain/household/financial.py:110`; `projection.py` | Authorized activity-history and current-position readers | No authorized balance-series DTO; revision history is not chart history |
| `ios/Packages/ArgusSession/Sources/ArgusSession/FinancialLoopTypes.swift:222-279` | Current Home DTO, currency exponent, period and coverage | No connected balance/spending-series adapter |
| Recovered `ios/ArgusFoundation/Connected/ConnectedCuadraoBalanceOverview.swift:38-63` at assigned UI SHA | Canonical current amount, partial/unknown count, freshness and explicit unavailable-history state | Unconditionally renders chart placeholder; current facts alone cannot replace it with a line |
| `ios/ArgusFoundation/Cuadrao/CuadraoBalanceHistory.swift:27-49,70`; `CuadraoSpendingStory.swift:8-24` | Preview observation matching and example coverage | Preview fixtures and coverageStart are not production facts |

The recovered current header is already bound separately from history. Its
currency fallback at recovered file line 11 selects the first server row; C1's
primary/explicit-choice presentation work is separate from a history contract.

## Precise missing contracts

1. **Balance-series technical adapter.** Recorded-position observation meaning
   is already locked by Cuadrao DESIGN `257-267,390-404`; no new founder choice
   between observations and reconstruction is needed. Define the attributed aggregate adapter, sampling,
   gaps, partial account coverage, backdated corrections, timezone,
   account inclusion and historical shares/types. Existing dates and provenance
   permit some grounded observations; they cannot prove intervening balances or
   balances before the first anchor. `loop.observations` uses current opening
   revision and checks; it is not an as-of replay engine.
2. **Complete spending coverage.** Define who confirms completeness, for which
   account/currency/period, with provenance and correction invalidation. The
   existing `included` fact answers whether an activity is included in a balance
   observation. It cannot establish a zero spending month. Monthly sum zero under
   `recorded_only` means recorded sum zero, not confirmed complete zero.
3. **Authorized history scope.** The adapter must derive from current access
   owners and the applicable frozen/pre-move history rules. Settle how moved,
   deleted, revoked and frozen accounts appear; do not replay unavailable facts
   from native cache or derive historical permissions from current membership.
4. **One shared read shape.** Define currency/exponent, reporting zone, interval,
   authorized included accounts, points with source references, gaps/unknowns,
   freshness and comparison eligibility. The native chart must render that
   contract rather than rebuild a financial ledger.

## Bounded next units

Current header/currency presentation can use existing summaries. After the
captain settles the missing contract, separate the canonical history reader/DTO,
complete-period coverage contract, and native adapter into small owned units.
Reuse existing positions, spending classification and authorization. Acceptance
should cover known zero versus missing coverage, zero comparisons, corrections,
archive/move/access loss and exact currency precision.

Recommendation for the current state: keep the current header visible and show
history as unavailable until its contract is settled. Label spending as
recorded-only until complete-period evidence exists. This is temporary truthful
status, **not approval to remove required history, insights or comparisons**.
No new product choice, implementation assignment or release waiver is created.

## Accepted bounded handoff: existing personal observation reads

Correction: the earlier observation-versus-reconstruction question was unnecessary.
Cuadrao DESIGN `257-267,390-404` already locks recorded positions and comparisons.
The captain also accepted conservative reuse of existing PERSONAL API reads and
assigned Counsel the native reader/adapter under `FinancialLoopModel`. No new
backend DTO, API route or migration is needed for raw per-account observations.
The engineering proposal is described in the source-only
`/private/tmp/cuadrao-personal-observation-read-contract-20261006.md`; source
citations below were checked against integration. This unit does not complete
attributed Home totals, full history/insights, coverage or move-history acceptance.

Existing wire facts:

- Account GET/list: `src/argus/api/routers/financial_accounts.py:66-86`;
  `recording/schemas.py:123-145,168-197` returns current metadata, currency/exponent
  and the accepted opening's record/revision, amount, as_of, zone and recorded_at.
  Opening audit revisions are evidence, not extra plotted observations.
- Balance-check GET: `src/argus/api/routers/financial_loop.py:284-309` returns
  paginated accepted checks/value updates, newest reviewed version first.
  `recording/loop_reads.py:55-71` and `loop_schemas.py:131-165` expose observation
  amount, kind, dates, revision and author. Preserve this order for ties.
- Home's existing `FinancialHomePeriod` supplies the server reporting interval;
  do not add a native month-boundary calculator. Avoid separately concatenating
  optional asset estimates with checks and double-counting the same facts.

Small internal native value, illustrative only; this is not a new wire contract:

```text
PersonalAccountObservations {
  accountID, accountVersion, currency, currencyFractionDigits,
  currentMetadata { nickname, type, archived, ownershipShareBps, updatedAt },
  observations [{ recordID, revision, kind, amountMinor, asOf, timeZone, recordedAt }],
  period { month, timeZone, startAt, endAtExclusive },
  openingObservation?, closingObservation?, comparisonState, readState
}
```

Amounts represent signed RAW account minor units. Normalize existing integer wire
amounts losslessly; do not apply current ownership shares or historical kind
allocation. Metadata explicitly remains current. No aggregate net-worth/position
claim follows from this raw series; current Home totals keep their existing owner.
No transaction-derived, future Plan or fabricated now points; no interpolation,
synthetic zero or flat history. Currency/kind/share changes cannot borrow old
observations. Historical temporal kind/share evidence and compatible aggregate
scope remain separate foundations work, not a workaround in the native reader.

Read under existing session/transport ownership: fresh account A, every check
page, fresh account B. Publish only with matching account/version/currency and
unchanged identity/request generation. A stale cursor, interrupted/partial page
fetch or identity change produces incomplete/unavailable state, not comparison.
Use finite bounded paging and explicit refresh; no unbounded retry or second
cache. Include archived personal sources rather than only visible active rows.
No cross-account atomic snapshot or household permission is claimed.

Use the existing half-open period and preserve actual observation dates/zones.
Opening is the latest accepted fact at/before start; absent that, an inside-period
baseline carries its actual date and partial-baseline state. Closing is the latest
fact before the end, including a dated prior fact for an empty interval. Never
substitute later data. One record/revision means a dated known fact without a
change comparison. Two eligible facts permit checked raw subtraction, not an
income/return label. Missing facts or overflow leave comparison unavailable.

Keep spending on existing `coverage:"recorded_only"`. This unit adds no
completeness store and infers no complete zero from a sum, empty list, opening or
check. Complete-period spending coverage is separate. Pre-move/frozen/deleted-owner
history depends on its spaces/history owner; this PERSONAL unit adds no household
reader or grants and does not close that dependency.

Next unit and ownership:

1. Counsel owns the assigned native reader/adapter within existing
   `FinancialLoopModel`; root coordinates the single canonical contract and merge
   queue. Shared money owner changes remain serial; no competing worker/ledger.
2. Start with failing native contract/model tests for accepted revisions, actual
   dates, ties, known zero, one observation, inside-period baseline, later-data
   exclusion, precision, overflow, paging/version conflict and identity loss.
   Reuse existing backend/real-PostgreSQL acceptance tests for canonical readback
   and owner/guest denial; add cases only for a demonstrated uncovered boundary.
   Backend source should need no edits; report any proven missing fact first.
3. Counsel retains layout ownership. The attributed Home aggregate/temporal
   metadata contract remains missing; current account kind/share must not be
   projected backward. A raw-account reader is useful progress, not full Home
   acceptance or approval to remove the remaining surfaces.

C1 remains current Home currency ordering/selection. C3 remains the separate
connected Plan forecast consumer; it provides no history or spending completeness.
There is no new founder meaning gate, API implementation or release claim here.

## Limits

Source inspection only. No customer/account records, phone, Mac/device tooling,
environment, database, provider or service reads. No tests, build, physical-device
or delivery claim. Only this report was written; no code edits, Git commit,
push, PR creation, merge or deployment. No child agents or running resources.
