# Historical insights and native paging

UI-only preview verified October 1, 2026 (native result timestamps are October 2 UTC).
Final application source: `86aa3e8d520eed10543897e3bf77d8fdcc0ce5a9`.
This documentation/evidence checkpoint does not change that application source.

## Delivered behavior

- Historical averages use 6 or 12 complete covered months. Covered zero months count;
  incomplete coverage and future data cannot create averages.
- Category trends compare the recent three months with the preceding nine only
  when activity supports a sustained comparison. Historical pages use their own cutoff.
- Two featured cards lead to the full collection and actual supporting monthly records.
- Native period pages follow the finger. Short cancelled drags settle back; completed
  drags reveal adjacent periods. Hold inspection preserves the period. Controls stay anchored.
- Balance keeps the net-position hero in both modes. Positive assets have a separate
  allocation total; deductions remain separate. Activity uses expense-category shares.
- Both modes use the same dimensional, selectable allocation bar and stable All/category row.
- Home stays quiet. These fixtures are UI examples, not a connected ledger or valuation feed.

## Verification and provenance

`python3 ios/DesignPreviewTests/run_home_balance.py`: 57 checks passed.
Coverage includes exact averages, covered-zero denominators, missing coverage,
insufficient trend activity, historical cutoffs, calendar boundaries and spending scope.
Modularity budget and whitespace checks passed.

Native simulator: iPhone 18 Pro, iOS 27, dedicated device
`8AFB6084-8918-416E-9164-E21061306BEC`.

| Result bundle | Acceptance retained |
| --- | --- |
| `test_sim_2026-10-02T03-22-06-383Z_pid473_75e9d5a0.xcresult` | Eight baseline journeys passed: quiet Home/spaces, history/distribution, account return, large English and empty/unknown history. Two new failures were repaired below. |
| `test_sim_2026-10-02T03-27-15-629Z_pid473_97605781.xcresult` | Large English insight journey passed after locale repair. Three remaining gesture/selection failures were repaired below. |
| `test_sim_2026-10-02T03-29-50-624Z_pid473_8f114a43.xcresult` | All three affected journeys passed: expense periods/distribution, native paging/net-balance meaning, insights/records/return. Source `c70ed6f5`. |
| `test_sim_2026-10-02T03-33-35-645Z_pid473_6c14b960.xcresult` | Both affected journeys passed again at final source `86aa3e8d`: expense periods/distribution and insights/records/return. |

This is source-scoped acceptance, not a claim of one ten-test run at the final head.
The final delta changes only Activity's selection row, duplicate date labels and
supporting-entry date localization. Native pager, coverage logic, Balance, quiet Home
and large-text insight layouts retain their earlier acceptance. Read-only final delta
review returned clean with no concrete blockers; earlier selection-interception and
See-all eligibility findings were fixed and rechecked.

## Visual evidence

- [Historical average](historical-average-es.png), [all highlights](all-highlights-es.png),
  [category decomposition](category-decomposition-es.png) and
  [supporting months](supporting-months-es.png): final native source `86aa3e8d`.
- [Large English text](historical-large-en.png): passing large-English journey; the
  relevant insight layout and localized chart labels are unchanged at final source.
- [Native paging recording](interactive-paging.mp4) and
  [mid-drag frame](interactive-paging-mid-drag.png): passing paging journey at `c70ed6f5`.
  The recording shows cancellation, finger-following adjacent pages and inspection;
  paging source is unchanged at `86aa3e8d`.

Signed iPhone preview build 3410 was built from `86aa3e8d` and installed on
Sr.Garces i15, iOS 27.0.1. Device app inventory confirms bundle version 3410.

Future connected coverage, record ownership and valuation work stays in the
[main roadmap](../../../../../specs/argus-execution-board.md#cuadrao-consistency-pass-and-home-chart-follow-up).
