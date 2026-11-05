# Combined invitation and responsiveness verification

Ten selected simulator journeys passed on October 4, 2026: zero failures and
zero skips. This run covers #790, #810 and #812 together after #809 landed.
It complements the [24 release UI checks](../pr790/README.md).

## Provenance

- Exact local candidate: `25ce9a4d1a93516b21c3d52723b95468e5cbe149`.
- iOS subtree: `e2404d5e1d05d51761343cd18d7747605d884794`.
- The iOS subtree is byte-identical to accepted candidate
  `03a33ef2be86cd86f4ad65c51d3e95a08a0e7ba8`.
- Device: iPhone 17e simulator, iOS 27.0. One Mac test process owned this run.
- [Test results](test-results.txt) identify all ten cases and their durations.
- [Capture manifest](manifest.json) maps screenshots to test cases and original
  attachment names. Screenshots are exported from the same successful run.

The candidate includes #812's optimizations. These images verify the combined
app; they do not claim that #810 alone contains #812. Later documentation and
squash commits retain this evidence only while the iOS subtree remains identical.

## Coverage

Six invitation journeys cover valid and rejected codes, an unanswered admission
check, the default-off path, Household handoff, personal quota and one-time
secrets, and group-link limits and expiry. Four journeys cover chart paging,
spending highlights, Search recovery and chart-context return.

| Capture | What was inspected |
| --- | --- |
| [Unanswered access](access-unanswered-es-light.png) | Retry and sign-out while admission stays closed |
| [Chart context](context-chart-selection-en.png) | Context chip and retained chart selection |
| [Balance paging](interactive-paging-balance-es.png) | Period selection and balance meaning |
| [Month title](story-month-title-es.png) | Selected period heading and spending hierarchy |
| [Supporting months](story-supporting-months-es.png) | Historical data supporting the insight |
| [Average](story-history-average-es.png) | Six-month average, category palette and marks |
| [All highlights](story-all-highlights-es.png) | Highlights presentation |
| [Distribution](story-distribution-decomposition-es.png) | Selected distribution and decomposition |
| [Plan search](search-real-plan-es.png) | Search result and destination |
| [Chat return](search-chat-return-es.png) | Return from an existing conversation to Search |
| [Empty search](search-no-results-es.png) | No-results recovery |

An independent reviewer inspected all 11 captures. No new visual regression was
identified. Some captures show scrolled content under fixed controls; they are
not pixel-equality baselines. Five invitation tests have interaction assertions
without screenshot calls.

## Limits

These are simulator fixture/harness journeys. They do not verify hosted invite
round trips, a production migration, physical-phone persistence, or frame hitch
performance. No hosted flag was enabled. The earlier full candidate suite
(119 passed, 48 skipped, zero failures) remains separately recorded in the
[recovery evidence](../../cuadrao-mobile-recovery-2026-10-04/README.md).
