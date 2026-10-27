import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessCapture, GrantedSpace, ReceiptSummary } from "@/lib/business-api";
import type { BusinessContextValue, BusinessPanelState } from "@/components/business-app/BusinessWorkspace";

const originalEnvironment = { node: process.env.NODE_ENV, mock: process.env.NEXT_PUBLIC_MOCK_AUTH };
let cleanup = async () => {};
beforeAll(() => { GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 1000 }); (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; });
afterEach(async () => {
  await cleanup(); cleanup = async () => {};
  (await import("@/components/business-app/foundation/toasts")).clearToasts();
  (await import("@/components/layout/overlayStack")).resetOverlayStack();
  document.body.innerHTML = "";
  if (originalEnvironment.node === undefined) Reflect.deleteProperty(process.env, "NODE_ENV"); else Reflect.set(process.env, "NODE_ENV", originalEnvironment.node);
  if (originalEnvironment.mock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = originalEnvironment.mock;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

async function mount({ production = false, width = 1440, role = "owner", prepare = true }: { production?: boolean; width?: number; role?: GrantedSpace["role"]; prepare?: boolean } = {}) {
  Reflect.set(process.env, "NODE_ENV", production ? "production" : "development");
  process.env.NEXT_PUBLIC_MOCK_AUTH = production ? "false" : "true";
  (window as unknown as { happyDOM: { setViewport: (size: { width: number; height: number }) => void } }).happyDOM.setViewport({ width, height: 1000 });
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const { Plus } = await import("lucide-react");
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const Inbox = (await import("@/components/business-app/BusinessInboxPanel")).default;
  const source = (await import("@/components/business-app/fixture-data")).createFixtureBusinessDataSource({ chatAvailable: false });
  const i18n = (await import("i18next")).default.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: (await import("@/public/locales/es-419/common.json")).default } }, interpolation: { escapeValue: false } });
  const seed = (await source.receipts("all"))[0];
  let receipts: ReceiptSummary[] = [
    { ...seed, id: "review-receipt", merchant: "Recibo admitido", bandeja: { por_revisar: true, leyendo: false, con_problema: false } },
    { ...seed, id: "reading-receipt", merchant: "Recibo en lectura", status: "queued", bandeja: { por_revisar: false, leyendo: true, con_problema: false } },
    { ...seed, id: "problem-receipt", merchant: "Recibo con problema", status: "needs_attention", bandeja: { por_revisar: false, leyendo: false, con_problema: true } },
  ];
  const notes: BusinessCapture[] = [{ draft_id: "admitted-note", source_id: "note-source", version: 1, revision: 1, text: "Nota admitida", received_at: seed.received_at, review_state: "open" }];
  const emails = (await source.emailDeliveries()).filter(email => email.id === "email-boletin" || email.id === "email-estacion");
  assert.equal(emails.length, 2);
  const globalActivity = { reading_count: 92, unread_count: 94, presentation: "unread" as const, pending_review_count: 95, needs_attention_count: 93, ready_to_review_count: 91 };
  const chosen: GrantedSpace = { space_id: "count-business", grant_id: "count-grant", name: "Negocio sintético", role, capabilities: prepare ? ["read", "prepare"] : ["read"], access_seen: true };
  let uploads = 0;
  const opened: BusinessPanelState[] = [];
  let context: BusinessContextValue = {
    userId: "count-person", source: { ...source, receiptPage: async () => ({ items: receipts, activity: globalActivity }) },
    records: { workspace: await source.workspace(), overview: null, inbox: receipts, notes, notesTruncated: false, emails, error: false, receiptActivity: globalActivity },
    spaces: [chosen], chosen, chooseBusiness: () => {}, markAccessSeen: async () => {}, lostAccess: false, clearLostAccess: () => {}, revision: 0, reload: () => {}, refresh: async () => "updated",
    period: { key: "all", from: "", to: null }, setPeriod: () => {}, panel: { kind: "inbox" }, openPanel: next => opened.push(next),
    actions: { create: role === "owner" && prepare ? [{ id: "upload_receipt", label: "Agregar", icon: Plus, run: () => { uploads++; } }] : [], composer: [], starterEntries: [] },
    bridge: null, attachedReceipt: null, clearAttachedReceipt: () => {}, openExport: () => {}, emailRefresh: { refresh: () => {}, refreshing: false, stalled: false }, retrySources: () => {},
  };
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  const render = () => act(async () => { root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}><Inbox /></BusinessContext.Provider></I18nextProvider>); });
  cleanup = async () => { await act(async () => root.unmount()); host.remove(); };
  await render();
  const settle = async (ready: () => boolean) => { for (let i = 0; i < 50; i++) { await act(async () => { await new Promise(resolve => setTimeout(resolve, 10)); }); if (ready()) return; } throw new Error(`Missing expected state: ${host.textContent}`); };
  await settle(() => host.querySelector(production ? '[data-testid="bandeja-row"]' : '[data-testid="reception-row"]') !== null);
  const click = async (node: HTMLElement | null | undefined) => { assert.ok(node); await act(async () => node.click()); };
  const tab = (key: string) => host.querySelector<HTMLButtonElement>(`#reception-tab-${key}`);
  const badge = (key: string) => tab(key)?.querySelector("span")?.textContent;
  const row = (name: string) => [...host.querySelectorAll<HTMLElement>('[data-testid="reception-row"]')].find(element => element.textContent?.includes(name));
  const organize = async (name: string, action: string) => { await click(row(name)?.querySelector("input")); await click(host.querySelector<HTMLButtonElement>(`button[aria-label="${action}"]`)); };
  return { host, context, opened, uploads: () => uploads, click, tab, badge, row, organize, act, settle, async changeArrivals() { receipts = [...receipts.filter(receipt => receipt.id !== "review-receipt"), { ...receipts[0], id: "new-receipt", merchant: "Recibo sin admitir" }]; context = { ...context, revision: context.revision + 1 }; await render(); await settle(() => host.textContent?.includes("Actualizar lista") === true); } };
}

test("preview badges count admitted mixed arrivals independently of global activity, filters and local archives", async () => {
  const page = await mount();
  assert.deepEqual([page.badge("review"), page.badge("processing"), page.badge("attention"), page.badge("archived")], ["2", "2", "2", "0"]);
  await page.click(page.tab("review"));
  assert.equal(page.host.querySelectorAll('[data-testid="reception-row"]').length, 2);
  assert.ok(page.row("Nota admitida"));
  assert.deepEqual([page.badge("processing"), page.badge("attention")], ["2", "2"], "category counts do not follow the active filter");
  await page.organize("Recibo admitido", "Archivar");
  assert.deepEqual([page.badge("review"), page.badge("archived")], ["1", "1"]);
  await page.click(page.tab("all")); await page.organize("Recibo con problema", "Archivar");
  assert.deepEqual([page.badge("attention"), page.badge("archived")], ["1", "2"]);
  await page.changeArrivals();
  assert.deepEqual([page.badge("review"), page.badge("archived")], ["1", "1"], "stale archived IDs and new arrivals outside admission do not count");
  const update = [...page.host.querySelectorAll<HTMLButtonElement>("button")].find(button => button.textContent === "Actualizar lista");
  await page.click(update);
  assert.equal(page.badge("review"), "2");
  await page.click(page.tab("archived")); await page.organize("Recibo con problema", "Restaurar");
  assert.deepEqual([page.badge("attention"), page.badge("archived")], ["2", "0"]);
  assert.equal(page.context.records.receiptActivity?.ready_to_review_count, 91, "global Home activity remains unchanged");
});

for (const width of [1440, 390]) for (const role of ["owner", "accountant"] as const) test(`production nonmock inbox preserves title and ${role} actions at ${width}px`, async () => {
  const page = await mount({ production: true, width, role });
  assert.equal(page.host.querySelector('[data-testid="reception-preview"]'), null);
  const titles = [...page.host.querySelectorAll("h2")].filter(heading => heading.textContent === "Bandeja");
  assert.equal(titles.length, width < 768 ? 1 : 0, "desktop uses the existing Workspace header, phones retain the panel heading");
  const upload = page.host.querySelector<HTMLButtonElement>('[data-testid="business-primary-upload"]');
  const review = page.host.querySelector<HTMLButtonElement>('[data-testid="business-primary-review"]');
  if (role === "owner") { assert.ok(upload); assert.equal(review, null); await page.click(upload); assert.equal(page.uploads(), 1); }
  else { assert.equal(upload, null); assert.ok(review); await page.click(review); assert.deepEqual(page.opened, [{ kind: "receipt", receiptId: "review-receipt", list: "inbox" }]); }
});

test("production nonmock read-only owner retains Add capability refusal", async () => {
  const page = await mount({ production: true, prepare: false });
  assert.equal(page.host.querySelector('[data-testid="business-primary-upload"]'), null);
  assert.equal(page.host.querySelector('[data-testid="business-primary-review"]'), null);
});
