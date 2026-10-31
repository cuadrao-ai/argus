import { monthCloseWire, OPEN_ITEMS_WIRE } from '../e2e/support/month-close-wire';
import { installBreakpointFixture } from '../e2e/support/breakpoint-fixture';
import { createFixtureBusinessDataSource } from '../components/business-app/fixture-data';
import type { Page, Route } from '@playwright/test';
import type { BusinessSearchKind } from '../lib/business-search-api';
declare const Bun: {
  serve: (options: { hostname: string; port: number; fetch: (request: Request) => Promise<Response> }) => unknown;
  sleep: (milliseconds: number) => Promise<void>;
};
const source = createFixtureBusinessDataSource({ chatAvailable: false });
type Preview = {
  scenario: 'slow' | 'fast' | 'consent' | 'error';
  language: 'es-419' | 'en';
  monthClose: 'normal' | 'zero' | 'error' | 'refused';
  inbox: 'normal' | 'zero' | 'failed' | 'refused';
  earliest: string;
};
let config: Preview = { scenario: 'fast', language: 'es-419', monthClose: 'normal', inbox: 'normal', earliest: '2026-08' };
const handlers = new Map<Preview['language'], (route: Route) => Promise<void>>();
for (const language of ['es-419', 'en'] as const) {
  const page = { addInitScript: async () => {}, route: async (_p: string, handler: (route: Route) => Promise<void>) => { handlers.set(language, handler); } } as unknown as Page;
  await installBreakpointFixture(page, { language, emptyChat: true });
}
const headers = {
  'Access-Control-Allow-Origin': process.env.EVIDENCE_WEB_BASE_URL ?? 'http://127.0.0.1:4417',
  'Access-Control-Allow-Credentials': 'true',
  'Access-Control-Allow-Methods': 'GET, POST, DELETE, OPTIONS',
  'Access-Control-Allow-Headers': 'authorization, content-type, x-argus-user-id, x-request-id, x-argus-client-capabilities',
  'Content-Type': 'application/json',
};
const json = (data: unknown, status = 200) => Response.json(data, { status, headers });
Bun.serve({ hostname: '127.0.0.1', port: Number(process.env.EVIDENCE_FIXTURE_PORT ?? '4418'), async fetch(request) {
  if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers });
  const url = new URL(request.url), path = url.pathname;
  if (path === '/__preview' && request.method === 'POST') {
    const body = await request.json() as Partial<Preview>;
    config = {
      scenario: body.scenario === 'slow' || body.scenario === 'consent' || body.scenario === 'error' ? body.scenario : 'fast',
      language: body.language === 'en' ? 'en' : 'es-419',
      monthClose: body.monthClose === 'zero' || body.monthClose === 'error' || body.monthClose === 'refused' ? body.monthClose : 'normal',
      inbox: body.inbox === 'zero' || body.inbox === 'failed' || body.inbox === 'refused' ? body.inbox : 'normal',
      earliest: /^\d{4}-\d{2}$/.test(body.earliest ?? '') ? body.earliest! : '2026-08',
    };
    return json(config);
  }
  const run = { ...config };
  if (request.method === 'POST' && path === '/api/v1/auth/signup') return json({ user: { id: 'synthetic-preview-only' }, session: null });
  if (path === '/api/v1/business/search/recents') {
    if (request.method === 'POST') { const body = await request.json() as { q: string }; await source.addSearchRecent!(body.q); return json({}); }
    if (request.method === 'DELETE') { await source.clearSearchRecents!(); return json({}); }
    return json({ items: await source.searchRecents!() });
  }
  if (path.startsWith('/api/v1/business/search/recents/') && request.method === 'DELETE') { await source.removeSearchRecent!(decodeURIComponent(path.split('/').pop()!)); return json({}); }
  if (path === '/api/v1/business/search/opens' && request.method === 'POST') { const body = await request.json() as { kind: BusinessSearchKind; id: string }; await source.recordSearchOpen!(body.kind, body.id); return json({}); }
  const receiptMatch = /^\/api\/v1\/business\/receipts\/([^/]+)(?:\/(source|read))?$/.exec(path);
  if (receiptMatch) {
    const id = decodeURIComponent(receiptMatch[1]);
    if (request.method === 'POST' && receiptMatch[2] === 'read') {
      const body = await request.json() as { completion_cursor: string };
      return json(await source.markReceiptRead!(id, body.completion_cursor));
    }
    if (request.method === 'GET' && receiptMatch[2] === 'source') {
      const blob = await source.receiptSource(id);
      return new Response(blob, { headers: { ...headers, 'Content-Type': blob.type } });
    }
    if (request.method === 'GET' && !receiptMatch[2]) return json(await source.receipt(id));
  }
  if (request.method !== 'GET') return json({ code: 'local_preview_unsupported' }, 501);
  const gate = ['/api/v1/business/spaces', '/api/v1/business/consent', '/api/v1/me'].includes(path);
  if (gate && run.scenario !== 'fast') await Bun.sleep(1100);
  if (path === '/api/v1/business/spaces') {
    if (run.scenario === 'error') return json({ code: 'preview_directory_unavailable' }, 503);
    return json({ spaces: await source.spaces(), closed_spaces: [] });
  }
  if (path === '/api/v1/business/consent') return json({ version: url.searchParams.get('version'), accepted_at: run.scenario === 'consent' ? null : '2026-10-01T12:00:00Z' });
  if (path === '/api/v1/business/space') return json(await source.ensureSpace('es-419'));
  if (path === '/api/v1/business/workspace') {
    if (run.inbox === 'failed') return json({ code: 'synthetic_read_failed' }, 418);
    if (run.inbox === 'refused') return json({ code: 'business_unavailable' }, 404);
    return json(await source.workspace());
  }
  if (path === '/api/v1/business/overview') return json(await source.overview(url.searchParams.get('from') ?? '2026-10-01', url.searchParams.get('to')));
  if (path === '/api/v1/business/receipts') {
    const page = await source.receiptPage!(url.searchParams.get('view') === 'all' ? 'all' : 'inbox');
    if (run.inbox === 'zero') return json({ ...page, items: [], activity: { ...page.activity, ready_to_review_count: 0, needs_attention_count: 0, reading_count: 0 } });
    return json(page);
  }
  if (path === '/api/v1/business/captures') return json(await source.captures());
  if (path === '/api/v1/business/expenses') return json({ items: await source.expenses('2026-10-01', null) });
  if (path === '/api/v1/business/email/deliveries') return json({ items: await source.emailDeliveries() });
  if (path === '/api/v1/business/email/inbox' && request.method === 'GET') return json({ groups: [{ id: 'remitentes_nuevos', items: [] }, { id: 'bandeja', items: [] }] });
  if (path === '/api/v1/business/email') return json(await source.emailIntake());
  if (path === '/api/v1/business/receipt-activity') return json((await source.receiptPage!('inbox')).activity);
  if (path === '/api/v1/business/fiscal-profile') return json(await source.fiscalProfile());
  if (path === '/api/v1/business/month-close') {
    await Bun.sleep(run.scenario === 'fast' ? 0 : 800);
    if (run.monthClose === 'error') return json({ code: 'synthetic_month_failed' }, 418);
    if (run.monthClose === 'refused') return json({ code: 'business_unavailable' }, 404);
    const wire = monthCloseWire(url.searchParams.get('month') ?? '2026-10');
    wire.earliest_month = run.earliest;
    if (run.monthClose === 'zero') {
      wire.cuentas_por_cobrar = [];
      wire.cuentas_por_pagar = [];
      wire.dgii_forms = { '606': 'no_operations', '607': 'no_operations' };
      for (const currency of wire.currencies) {
        // monthCloseWire shares its status constant; keep the zero variant local to this response.
        currency.by_status = structuredClone(currency.by_status);
        currency.income_before_itbis_minor = 0;
        currency.income_before_itbis = '0.00';
        currency.expense_before_itbis_minor = 0;
        currency.expense_before_itbis = '0.00';
        currency.net_result_minor = 0;
        currency.net_result = '0.00';
        currency.itbis_owed_minor = 0;
        currency.itbis_owed = '0.00';
        currency.itbis_cobrado_minor = 0;
        currency.itbis_cobrado = '0.00';
        currency.by_status.invoices.pendiente.count = 0;
        currency.by_status.invoices.pendiente.before_itbis_minor = 0;
        currency.net_result_final = true;
      }
    }
    return json(wire);
  }
  if (path === '/api/v1/business/open-items') {
    if (run.monthClose === 'zero') return json({ ...OPEN_ITEMS_WIRE, cuentas_por_cobrar: { count: 0, totals: [], overdue: { count: 0, totals: [] }, items: [] } });
    return json(OPEN_ITEMS_WIRE);
  }
  if (path === '/api/v1/business/search') {
    const q = url.searchParams.get('q') ?? '';
    const cursor = url.searchParams.get('cursor'), kind = url.searchParams.get('kind');
    return json(cursor && kind ? await source.searchMore!(q, kind as BusinessSearchKind, cursor) : await source.search(q));
  }
  if (path.includes('/business/')) return json({ code: 'local_preview_unsupported' }, 404);
  let response: Response | undefined;
  const handler = handlers.get(run.language);
  if (!handler) return json({ code: 'local_preview_missing_handler' }, 500);
  const route = { request: () => ({ url: () => request.url }), fulfill: async (options: NonNullable<Parameters<Route['fulfill']>[0]>) => {
    const body = options.json === undefined ? options.body?.toString() : JSON.stringify(options.json);
    response = new Response(body, { status: options.status ?? 200, headers });
  } } as unknown as Route;
  await handler(route);
  return response ?? json({ code: 'local_preview_missing_fixture' }, 500);
}});
console.log('Synthetic Home checkpoint fixture API at http://127.0.0.1:4418');
