# Business period ZIP download

Gastos now mounts the existing approved export control. PR #1066 removed it from individual records because exports belong to a period. The period entry point was missing. Individual records continue to omit the control.

The server-listed selected Business supplies its name and read capability. The request omits the optional draft anchor and uses the existing selected grant header. No dossier is fetched and no own-Business fallback is added. The API rechecks current authorization. Browser auth generation and selected grant checks reject stale responses, including while the response body is read. Business or period changes remount the control and abort its request.

Todo starts at 2000-01-01. A range longer than 366 inclusive days keeps download disabled. The existing Spanish date fields and hint let the person choose an explicit supported range. The client does not truncate records or enlarge the backend contract.

## Verification

- Baseline regression commit `8f1a0b9f7` produced `0 pass, 2 fail`. Both failed with `AssertionError: Gastos mounts the Spanish ZIP download control`, actual `undefined`.
- `cd web && bun test __tests__/business-*` produced `202 pass, 0 fail` across 34 files.
- The 14 mounted export tests cover owner and read-only accountant clicks, original ZIP bytes, selected grant, Todo dates, server period end, 403/404/413/503 retry, Business/period/permission/session changes, stale grant before click and disabled preview.
- Focused ESLint passed. Production `bun run build --webpack` passed, including its TypeScript check and 14 generated pages. Standalone `tsc --noEmit` exposes existing repository test-declaration errors in `bun:test`; it is not a clean repository gate.
- `python3 scripts/check_modularity_budget.py --top 3` passed. Integration fetch remained at `02502122aae107bc71ff123c7fb8060dc88f93ab`, the original worker base. There was no integration reconciliation merge or semantic overlap.

The local browser probe uses the real `/biz?view=expenses` UI and intercepts every API call with synthetic fixtures. All external hosts are blocked. It proves a browser download, not hosted customer acceptance or backend ZIP content generation. The screenshots contain synthetic data only.

Run an environment-free local dev server from `web` with process-only `NEXT_PUBLIC_MOCK_AUTH=true`, `NEXT_PUBLIC_ENABLE_SPANISH=true`, `NEXT_PUBLIC_BUSINESS_PILOT_ENABLED=true`, `NEXT_PUBLIC_ARGUS_API_URL=http://127.0.0.1:17977/api/v1`, and provider keys blank. Use `bun run dev --webpack --hostname 127.0.0.1 --port 17978`. Then run from repository root:

```sh
mkdir -p temp/receipt-export
OPENROUTER_API_KEY= ALPACA_API_KEY= ALPACA_SECRET_KEY= bun run docs/reports/evidence/business-export-download-20261017/browser-probe.ts
```

Decisive output:

```text
CONTROL_VISIBLE true
ALL_DISABLED true
DOWNLOAD business-export-2026-10-01-2026-10-17.zip QUERY [ "?start=2026-10-01&end=2026-10-17" ]
NO_OVERFLOW true
```

[Desktop](after-desktop.png), [explicit dates under Todo](after-explicit-dates.png), and [390px mobile](after-mobile.png) show the approved Spanish export copy. These images were captured on the final production code delta; the final head is rechecked after documentation is committed.

## Ownership and limits

The worker owns three frontend production files, the related tests, ownership entry and this evidence. Model and reasoning are GPT-6.1-sol, high. No paid calls, backend, migration, environment file, sidebar/menu, Marketing, production, merge or deployment changes are included.

The read-only topology check reported root `.env` and `web/.env.local` missing. The root coordinator explicitly authorized environment-free mocked unit/build/browser checks with provider keys blank and no environment loading or writes. Dependencies were reused through a worker-local `node_modules` symlink. Real local backend/provider acceptance remains outside this verification.

Independent exact-head Eval, terminal CI, unresolved review threads and hosted staging acceptance remain coordinator gates. The detection is the mounted click regression, which fails if the period control disappears again. Roll back this narrow frontend change to remove the control; it creates no persistent records.
