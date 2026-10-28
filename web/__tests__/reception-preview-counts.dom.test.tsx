import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessCapture, GrantedSpace, ReceiptActivity, ReceiptSummary } from "@/lib/business-api";
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

async function mount({ production = false, width = 1440, role = "owner", prepare = true, tweak = receipts => receipts, markRead }: { production?: boolean; width?: number; role?: GrantedSpace["role"]; prepare?: boolean; tweak?: (receipts: ReceiptSummary[]) => ReceiptSummary[]; markRead?: (id: string, cursor: string) => Promise<ReceiptActivity> } = {}) {
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
  let receipts: ReceiptSummary[] = tweak([
    { ...seed, id: "review-receipt", merchant: "Recibo admitido", bandeja: { por_revisar: true, leyendo: false, con_problema: false } },
    { ...seed, id: "reading-receipt", merchant: "Recibo en lectura", status: "queued", bandeja: { por_revisar: false, leyendo: true, con_problema: false } },
    { ...seed, id: "problem-receipt", merchant: "Recibo con problema", status: "needs_attention", bandeja: { por_revisar: false, leyendo: false, con_problema: true } },
  ]);
  const notes: BusinessCapture[] = [{ draft_id: "admitted-note", source_id: "note-source", version: 1, revision: 1, text: "Nota admitida", received_at: seed.received_at, review_state: "open" }];
  const emails = (await source.emailDeliveries()).filter(email => email.id === "email-boletin" || email.id === "email-estacion");
  assert.equal(emails.length, 2);
  const globalActivity = { reading_count: 92, unread_count: 94, presentation: "unread" as const, pending_review_count: 95, needs_attention_count: 93, ready_to_review_count: 91 };
  const chosen: GrantedSpace = { space_id: "count-business", grant_id: "count-grant", name: "Negocio sintético", role, capabilities: prepare ? ["read", "prepare"] : ["read"], access_seen: true };
  let uploads = 0;
  let reloads = 0;
  const opened: BusinessPanelState[] = [];
  let context: BusinessContextValue = {
    userId: "count-person", source: { ...source, receiptPage: async () => ({ items: receipts, activity: globalActivity }), ...(markRead ? { markReceiptRead: markRead } : {}) },
    records: { workspace: await source.workspace(), overview: null, inbox: receipts, notes, notesTruncated: false, emails, error: false, receiptActivity: globalActivity },
    spaces: [chosen], chosen, chooseBusiness: () => {}, markAccessSeen: async () => {}, lostAccess: false, clearLostAccess: () => {}, revision: 0, reload: () => { reloads++; }, refresh: async () => "updated",
    period: { key: "all", from: "", to: null }, setPeriod: () => {}, panel: { kind: "inbox" }, openPanel: next => opened.push(next),
    actions: { create: role === "owner" && prepare ? [{ id: "upload_receipt", label: "Agregar", icon: Plus, run: () => { uploads++; } }] : [], composer: [], starterEntries: [] },
    bridge: null, attachedReceipt: null, clearAttachedReceipt: () => {}, openExport: () => {}, emailRefresh: { refresh: () => {}, refreshing: false, stalled: false }, retrySources: () => {},
  };
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  const render = () => act(async () => { root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}><Inbox /></BusinessContext.Provider></I18nextProvider>); });
  cleanup = async () => { await act(async () => root.unmount()); host.remove(); };
  await render();
  const settle = async (ready: () => boolean) => { for (let i = 0; i < 50; i++) { await act(async () => { await new Promise(resolve => setTimeout(resolve, 10)); }); if (ready()) return; } throw new Error(`Missing expected state: ${host.textContent}`); };
  await settle(() => host.querySelector('[data-testid="reception-row"]') !== null);
  const click = async (node: HTMLElement | null | undefined) => { assert.ok(node); await act(async () => node.click()); };
  const tab = (key: string) => host.querySelector<HTMLButtonElement>(`#reception-tab-${key}`);
  const badge = (key: string) => tab(key)?.querySelector("span")?.textContent;
  const row = (name: string) => [...host.querySelectorAll<HTMLElement>('[data-testid="reception-row"]')].find(element => element.textContent?.includes(name));
  const organize = async (name: string, action: string) => { await click(row(name)?.querySelector("input")); await click(host.querySelector<HTMLButtonElement>(`button[aria-label="${action}"]`)); };
  return { host, context, opened, uploads: () => uploads, reloads: () => reloads, click, tab, badge, row, organize, act, settle, async changeArrivals() { receipts = [...receipts.filter(receipt => receipt.id !== "review-receipt"), { ...receipts[0], id: "new-receipt", merchant: "Recibo sin admitir" }]; context = { ...context, revision: context.revision + 1 }; await render(); await settle(() => host.textContent?.includes("Actualizar lista") === true); } };
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

const rows = (page: Awaited<ReturnType<typeof mount>>) => [...page.host.querySelectorAll<HTMLElement>('[data-testid="reception-row"]')];

for (const width of [1440, 390]) for (const role of ["owner", "accountant"] as const) test(`the live Bandeja renders Reception and ${role} actions at ${width}px`, async () => {
  const page = await mount({ production: true, width, role });
  assert.equal(page.host.querySelector('[data-testid="reception-preview"]')?.getAttribute("data-mode"), "live");
  const titles = [...page.host.querySelectorAll("h2")].filter(heading => heading.textContent === "Bandeja");
  assert.equal(titles.length, width < 768 ? 1 : 0, "desktop uses the existing Workspace header, phones retain the panel heading");
  const upload = page.host.querySelector<HTMLButtonElement>('[data-testid="business-primary-upload"]');
  const review = page.host.querySelector<HTMLButtonElement>('[data-testid="business-primary-review"]');
  if (role === "owner") { assert.ok(upload); assert.equal(review, null); await page.click(upload); assert.equal(page.uploads(), 1); }
  else { assert.equal(upload, null); assert.ok(review); assert.equal(review.textContent, "Revisar recibos"); await page.click(review); assert.deepEqual(page.opened, [{ kind: "receipt", receiptId: "review-receipt", list: "inbox" }]); }
});

test("a read-only owner sees no Add capability in the live Bandeja", async () => {
  const page = await mount({ production: true, prepare: false });
  assert.equal(page.host.querySelector('[data-testid="business-primary-upload"]'), null);
  assert.equal(page.host.querySelector('[data-testid="business-primary-review"]'), null);
});

test("live shows only what arrived: no example note, no selection, no archive, no seen toggles", async () => {
  const page = await mount({ production: true, tweak: receipts => receipts.map(receipt => ({ ...receipt, activity: { state: "ready" as const, unread: false, completion_cursor: "c" } })) });
  assert.equal(rows(page).some(row => row.getAttribute("data-kind") === "message"), false, "no synthetic WhatsApp note");
  assert.equal(page.host.textContent?.includes("Vista previa"), false);
  assert.equal(page.host.querySelector('input[type="checkbox"]'), null, "no checkboxes while nothing durable backs the actions");
  assert.equal(page.tab("archived"), null, "no Archivados tab");
  assert.equal(page.host.querySelector('[role="region"][aria-label="Acciones masivas"]'), null);
  assert.equal(rows(page).length, 6, "three receipts, one note and two emails");
  assert.equal(rows(page).filter(row => row.getAttribute("data-unseen") === "true").length, 0, "nothing is seeded as unseen");
});

test("live tab numbers are the server's, not a count of the rows loaded", async () => {
  const page = await mount({ production: true });
  assert.deepEqual([page.badge("review"), page.badge("processing"), page.badge("attention")], ["91", "92", "93"]);
  await page.click(page.tab("review"));
  assert.deepEqual([page.badge("review"), page.badge("processing"), page.badge("attention")], ["91", "92", "93"], "the active view does not move the numbers");
});

test("live marks a receipt unseen only when the server says its activity is unread, and never marks anything locally", async () => {
  const unread = (receipt: ReceiptSummary) => receipt.id === "review-receipt" ? { ...receipt, activity: { state: "ready" as const, unread: true, completion_cursor: "c1" } } : { ...receipt, activity: { state: "ready" as const, unread: false, completion_cursor: "c0" } };
  const page = await mount({ production: true, tweak: receipts => receipts.map(unread), markRead: async (_id, cursor) => ({ state: "ready", unread: false, completion_cursor: cursor }) });
  const dotted = () => rows(page).filter(row => row.getAttribute("data-unseen") === "true").map(row => row.textContent);
  assert.equal(dotted().length, 1);
  assert.match(dotted()[0] ?? "", /Recibo admitido/);
  await page.click(rows(page).find(row => row.textContent?.includes("Nota admitida"))!.querySelector<HTMLElement>("button"));
  assert.equal(dotted().length, 1, "opening a note marks nothing locally");
});

test("a receipt still being read never carries the dot, and each channel keeps its own word", async () => {
  const page = await mount({
    production: true,
    tweak: receipts => receipts.map(receipt => receipt.id === "reading-receipt"
      ? { ...receipt, channel: "email" as const, activity: { state: "reading" as const, unread: true, completion_cursor: null } }
      : receipt.id === "review-receipt" ? { ...receipt, channel: "whatsapp" as const, activity: { state: "ready" as const, unread: false, completion_cursor: "c" } } : { ...receipt, channel: "web" as const, activity: { state: "ready" as const, unread: false, completion_cursor: "c" } }),
  });
  const row = (name: string) => rows(page).find(item => item.textContent?.includes(name))!;
  assert.equal(row("Recibo en lectura").getAttribute("data-unseen"), "false");
  assert.equal(row("Recibo en lectura").querySelector('[data-testid="reception-channel"]')?.textContent, "Correo");
  assert.equal(row("Recibo admitido").querySelector('[data-testid="reception-channel"]')?.textContent, "WhatsApp");
  assert.equal(row("Recibo con problema").querySelector('[data-testid="reception-channel"]')?.textContent, "Carga manual");
});

test("opening a ready, unread receipt acknowledges it once through the read route and reloads", async () => {
  const calls: [string, string][] = [];
  const page = await mount({
    production: true,
    tweak: receipts => receipts.map(receipt => receipt.id === "review-receipt" ? { ...receipt, activity: { state: "ready" as const, unread: true, completion_cursor: "cursor-7" } } : { ...receipt, activity: { state: "reading" as const, unread: false, completion_cursor: null } }),
    markRead: async (id, cursor) => { calls.push([id, cursor]); return { state: "ready", unread: false, completion_cursor: cursor }; },
  });
  const row = rows(page).find(item => item.textContent?.includes("Recibo admitido"))!;
  await page.click(row.querySelector<HTMLElement>("button"));
  await page.settle(() => page.reloads() > 0);
  assert.deepEqual(calls, [["review-receipt", "cursor-7"]]);
  const other = rows(page).find(item => item.textContent?.includes("Recibo en lectura"))!;
  await page.click(other.querySelector<HTMLElement>("button"));
  assert.equal(calls.length, 1, "a receipt nobody finished reading has nothing to acknowledge");
});

test("a failed acknowledgement changes nothing on screen", async () => {
  const page = await mount({
    production: true,
    tweak: receipts => receipts.map(receipt => receipt.id === "review-receipt" ? { ...receipt, activity: { state: "ready" as const, unread: true, completion_cursor: "cursor-9" } } : receipt),
    markRead: async () => { throw new Error("offline"); },
  });
  const row = rows(page).find(item => item.textContent?.includes("Recibo admitido"))!;
  await page.click(row.querySelector<HTMLElement>("button"));
  await page.act(async () => { await new Promise(resolve => setTimeout(resolve, 30)); });
  assert.equal(page.reloads(), 0);
  assert.equal(rows(page).find(item => item.textContent?.includes("Recibo admitido"))?.getAttribute("data-unseen"), "true");
});

test("a WhatsApp receipt shows no sender instead of one inferred from its merchant", async () => {
  const page = await mount({ production: true, tweak: receipts => receipts.map(receipt => receipt.id === "review-receipt" ? { ...receipt, channel: "whatsapp" as const, email_delivery_ids: [] } : receipt) });
  const row = rows(page).find(item => item.textContent?.includes("Recibo admitido"))!;
  const sender = row.querySelector('[data-testid="reception-sender"]');
  assert.equal(sender?.getAttribute("data-known"), "false");
  assert.equal(sender?.getAttribute("aria-label"), "Remitente no disponible");
});

test("the dev preview keeps its labeled example, selection and local archive", async () => {
  const page = await mount();
  assert.equal(page.host.querySelector('[data-testid="reception-preview"]')?.getAttribute("data-mode"), "preview");
  assert.ok(rows(page).some(row => row.getAttribute("data-kind") === "message"));
  assert.ok(page.host.querySelector('input[type="checkbox"]'));
  assert.ok(page.tab("archived"));
});
