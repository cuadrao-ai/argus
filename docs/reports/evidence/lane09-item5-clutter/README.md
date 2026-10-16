# Business clutter cleanup

Item 5 and folded item 8 put review work before totals, remove the enabled-reading notice from Bandeja, and keep one inbox subhead. Unknown totals stay unknown. The existing server acknowledgement remains the only durable owner of access-banner dismissal.

This is a local synthetic checkpoint. Root owns integration reconciliation, independent Eval, merge and staging.

## Source and scope

- Frozen item 4 base is `e0c8d94b9d348c5c086f966c2bdffc29df0c4d1d`.
- Implementation is `eb8367b5b59a9433a6e38d04338934fe7612d3e6`.
- Initial fetched integration was `466ba25cf69f70ec054a9d094b2d76b16b41a0bd`. Final fetch was `742f4b72a3f082194e56cbcccb679ab7a8ca8394`.
- Root must retain the auth/session changes in integration and the separate item 3 reference-label commit. No reconciliation or rebase was performed here.
- The only shared provider edit adds an access-list revision after successful acknowledgement. It cancels a listing that started before dismissal, then reads the canonical server state again.
- Auth transport, session storage, `ensureSpace`, backend contracts and navigation are unchanged.

The [overview layout reference](https://mobbin.com/screens/d8564614-5b4c-4cdc-8088-0891fc9260df) was opened and visually inspected in the browser. The existing primary upload action stays above the content. The review summary precedes compact empty totals in DOM and visual order.

## Empty-state truth

The exact approved Spanish line is `Todo aprobado. Pa'que cuadre.`. It appears only after an unfiltered current-Business read returns at least one non-email-original receipt, every such receipt has `status=confirmed`, and the server says `pending_review_count=0`. Missing, failed or contradictory evidence keeps the existing plain empty copy. Dismissed receipts do not count as approved. Truncated notes cannot prove completion.

The complete-list contract was checked in these existing owners.

- `web/lib/business-api.ts` calls `GET /business/receipts?view=all` without a period or page argument.
- `src/argus/api/routers/business.py` accepts `view=inbox|all`, with no pagination parameter.
- `src/argus/api/business_drafts.py` applies the closed-state filter only for `inbox`.
- `src/argus/domain/business/service.py` enumerates connected readable receipt sources for the current scope.
- `src/argus/domain/ingestion/connections_postgres.py` lists that scope without a SQL limit or offset.

No browser history or empty filtered list serves as approval evidence. The new proof read aborts when its view closes. A source, activity or Business change invalidates the displayed proof.

## Verification

| Check | Result |
| --- | --- |
| `bunx playwright test --config e2e/business-clutter.playwright.config.ts` | 10 passed, localhost transport only |
| Focused Bun suite across access dismissal, review counts, receipt activity, locales, upload controls and loading | 29 passed, 267 expectations |
| Current integration plus only the acknowledgement fence, across actual BusinessApp owner boundary, access dismissal, existing account boundary and space readiness | 9 passed |
| `bun run build` with synthetic process environment | Passed |
| `bun run lint` | Passed, 0 errors and 8 existing warnings |
| `python3 scripts/check_modularity_budget.py` on the worker tree | Passed, no violations |
| Locale catalog diff and `git diff --check` | Passed; English and Spanish catalogs unchanged |
| Independent comment-only review of the item delta | Clean, 0 changes requested |

The riskiest probe was `bun test __tests__/business-access-dismissal.dom.test.tsx`. On untouched integration `466ba25cf`, the result was `2 pass, 1 fail`. A listing that began before Entendido restored the banner after the acknowledgement succeeded. With the narrow revision fence, the same test returned `3 pass, 0 fail`.

The actual owner-boundary test uses the real `BusinessApp`, with synthetic auth events and delayed old-owner list and acknowledgement responses. It passes on current integration with the fence. It fails on this deliberately unreconciled stack because the frozen item 4 base lacks integration's owner-keyed `BusinessApp`. Root must reconcile first and rerun `business-clutter-owner-boundary.dom.test.tsx`; a test-only provider key is not accepted as owner-boundary proof. Final independent Eval and merged-tree modularity remain with root. Hosted behavior, provider extraction, backend regressions and guest browser checks were not run locally.

## Desktop and phone evidence

Before images use the frozen item 4 source. After images use the implementation tree committed as `eb8367b5b`; the commit changed no rendered source after capture. Both widths used synthetic saved records and no remote API requests.

| View | Before | After |
| --- | --- | --- |
| Resumen, 1280px | [Before](before-overview-1280.png) | [After](after-overview-1280.png) |
| Resumen, 390px | [Before](before-overview-390.png) | [After](after-overview-390.png) |
| Bandeja, 1280px | [Before](before-inbox-1280.png) | [After](after-inbox-1280.png) |
| Bandeja, 390px | [Before](before-inbox-390.png) | [After](after-inbox-390.png) |

## Cleanup

No worker server remains on port 3195. Removed only owned build and temporary source outputs. Dependencies, the Playwright configuration, screenshots, tests and local reproduction logs remain.

| Removed path | Allocated bytes |
| --- | ---: |
| `web/.next` | 209,707,008 |
| `temp/lane09-item5/current-tip` | 11,923,456 |
| `web/temp/clutter-results` | 4,096 |
| Total | 221,634,560 |

Whole-volume `df -k` available space changed from 185,663,256 KiB to 185,880,488 KiB. Other processes share the volume. The path measurements above identify this cleanup's actual scope.
