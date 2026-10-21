# Spanish Core simulator continuation

These manual checks use the unchanged Core app built from
`40ff4967040c854ca5dd0764115227544011a6e2`. They are not a new build or XCTest
execution. The native source still matches that revision at local handoff
commit `769654e23`. All visible account names and amounts are synthetic.

The existing Consumer simulator initially contained the parked Goal experiment.
The Core app was restored on the simulator before these captures. Its executable
SHA-256 is recorded in [the manifest](manifest.json). No prototype screenshot is
included. The preserved Goal experiment remains outside this checkpoint.

## Observed results

- Budget `Food DF84D` shows DOP 155.00 spent, DOP 5.00 available, and a DOP 160.00
  limit before and after relaunch. The two captures have identical image hashes
  and distinct capture times.
- Back returns to the saved Search query with the DOP filter and correct Budget
  result. The first Search capture still shows loading. A later Accounts → Plans
  filter check returns the same result, query, and currency. The settled capture
  shows that the spinner has cleared. A stable UI snapshot alone did not prove
  that loading had finished.
- Transaction entry accepted 12.34, then Cancel returned without Review or
  Confirm. Home still shows the partial DOP 26,518.50 total and five unknown
  balances. The retained image records the final Home state. This check made no
  financial write and did not add an independent API readback.
- The Free Add tray exposes Account, Transaction, and Plan. The navigation and
  Search controls shown here contain no assistant or receipt entry point.

| Image | Observed state |
| --- | --- |
| [Budget before relaunch](budget-before-relaunch.jpg) | Saved spending, available amount, and limit |
| [Budget after relaunch](budget-after-relaunch.jpg) | Same values after relaunch |
| [Search after relaunch](search-after-relaunch.jpg) | Preserved query, currency, and result while loading |
| [Search settled](search-settled.jpg) | Same query and result after the filter check, with no spinner |
| [Home](home.jpg) | Partial balance and unknown balances after cancellation |
| [Add tray](home-add-tray.jpg) | Current Free entry points |

The first captures were taken on October 11 between 19:18 and 19:22 UTC, or
2:18 and 2:22 p.m. Central. The settled Search continuation was captured later
that afternoon. Exact file times, hashes, and UI snapshots are in the manifest.
The images are unchanged originals.

## Acceptance limits

The app uses `https://cuadrao-api-staging.onrender.com` and its assigned
`cad1cbe1e` backend pin. This continuation did not perform a fresh hosted SHA
readback. It does not establish phone acceptance, extreme Dynamic Type, receipt
extraction, a trusted paid entitlement, or connected paid chat. No hosted
configuration, provider call, product UI, or financial record changed.

The earlier complete XCTest journeys retain their original results and source
revisions in [the Core checkpoint](../README.md). These manual checks supplement
that evidence without relabeling earlier runs as new passes.
