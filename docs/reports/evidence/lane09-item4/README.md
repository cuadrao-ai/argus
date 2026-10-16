# Item 4 receipt upload and recovery

This checkpoint covers critique 1.2 and 1.5 only. It starts from frozen item 3
`f247aef6acc1b99397b88af0fac74935df1d09db`. The implementation commit is
`e5e72b8b8900bf292e567f26c9edfbac4851e6cc`.

Owners see one green Subir recibo action at the top of Resumen and Bandeja.
Resumen removes the duplicate upload pill. Other pills and the existing email
receiving card stay secondary. A failed saved receipt shows its full error,
Reintentar when the server permits preparation, and Escribir datos when the
server permits manual entry. The manual button opens that same receipt's existing
form. Retry uses the existing consented prepare API and refreshes server state
on both success and refusal. An in-flight guard blocks repeat activation.

Only BusinessOverviewPanel.tsx and BusinessInboxPanel.tsx change at runtime.
The queue, API, auth, permission state, model-facing text and catalogs are unchanged.
Unsupported upload types retain the existing backend-code-driven rejection and
replacement action. No filename-based type classification was added.

The exact Spanish manual label applies only to es-419. English reuses the existing
Record expense label. The DOM test switches es-419 to en and back on the same row.
No new locale key or English wording was added.

## Verification

- Canonical `bun run build` passed with process-only mock auth, Business and Spanish
  flags, and `NEXT_DIST_DIR=.next-item4-build`. Generated tsconfig output was
  restored. No shared environment file was created or changed.
- Canonical `bun run lint` passed with zero errors and eight pre-existing warnings
  in ReceiptDossierReview.tsx and ChatSidebar.tsx. Neither file changes here.
- 46 targeted tests passed across business-upload-controls.dom.test.tsx,
  locales.test.ts, business-inbox-notes.test.tsx, receipt-activity.dom.test.tsx,
  receipt-marks.dom.test.tsx and receipt-upload-queue.test.ts.
- Eight Chromium tests passed across business-upload-controls.spec.ts and the
  existing business-receipt-upload-recovery.spec.ts. Both widths are 1280 and 390.
  The cases cover permission combinations, owner and accountant, retry refusal,
  successful retry, repeat keyboard activation, same-receipt manual entry,
  44px action heights, horizontal overflow, and reduced-motion presentation.
- The two screenshot cases passed again at implementation commit e5e72b8b8,
  with explicit single-upload-action and same-receipt URL assertions.
- The initial new test failed on the missing Resumen main action before the fix.
- Worker modularity passed. Offline merge-tree `abc864898df754a8dbd47dba869a426eca07b392`
  against integration `466ba25cf69f70ec054a9d094b2d76b16b41a0bd` also passed with
  zero budget violations. This did not merge or rebase the worker.

The riskiest probe was the synthetic 503 retry followed by success at both widths.
`CUADRAO_UPLOAD_EVIDENCE_DIR=../docs/reports/evidence/lane09-item4
PLAYWRIGHT_PORT=3214 bunx playwright test e2e/business-upload-controls.spec.ts
--grep 'owner upload' --workers=1` passed two tests. Process flags were
`NEXT_PUBLIC_MOCK_AUTH=true`, `NEXT_PUBLIC_BUSINESS_PILOT_ENABLED=true` and
`NEXT_PUBLIC_ENABLE_SPANISH=true`. The test checked one request after failure,
two requests after a deliberate second retry, and still two after manual entry.
All Business requests used synthetic fixtures. External browser requests were
blocked. There was no provider call, hosted ingestion, login or customer data.

## Screenshots

The before images show frozen item 3. After images show the implementation
commit above. Phone inbox after-images scroll the existing content container so
both recovery buttons fit in the capture.

| Screen | Desktop before | Desktop after | Phone before | Phone after |
| --- | --- | --- | --- | --- |
| Resumen | [Before](before-overview-1280.png) | [After](after-overview-1280.png) | [Before](before-overview-390.png) | [After](after-overview-390.png) |
| Bandeja | [Before](before-inbox-1280.png) | [After](after-inbox-1280.png) | [Before](before-inbox-390.png) | [After](after-inbox-390.png) |

Retry failure, manual entry and reduced-motion captures use the same `after-`
filename prefixes in this folder. The cited Mercury Home Mobbin reference was
opened and visually inspected in the signed-in in-app browser. Its filled first
action and quieter secondary pills informed the hierarchy only.

## Handoff and limits

Independent exact-head Eval, integration reconciliation, merge and staging are
owned by the root coordinator. No READY or hosted-readiness claim is made here.
The urgent auth/session work in integration changes the Business context and
transport used by these buttons. Merge-tree has no textual conflicts, but that
shared ownership requires the root to repeat the affected fixture cases after
reconciliation. Preserve the auth/session changes. Do not rebase this stack.
Backend and guest checks were not run locally because this slice changes only
Business render methods. The final PR comment records exact head and CI IDs.

The Model the Domain principle kept ReceiptSummary permissions authoritative.
Laziness Protocol kept the existing queue, form and APIs. Test Behavior, Not
Implementation selected user clicks, keyboard actions and observed requests.

Disk before was 717Gi used and 179Gi available. Disk after was 721Gi used and
179Gi available. Dependency files were copied into this isolated worker after
Turbopack rejected a dependency symlink. All fixture servers stopped when their
Playwright command finished. Local configs, logs, build outputs and the offline
merge-tree inspection remain under ignored worker paths for follow-up.
