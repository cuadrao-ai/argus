import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessCapture, GrantedSpace, ListoApproval, ListoItem, ReceiptActivity, ReceiptSummary } from "@/lib/business-api";
import type { BusinessContextValue, BusinessPanelState } from "@/components/business-app/BusinessWorkspace";
import type { BusinessDataSource } from "@/components/business-app/business-data";

let cleanup = async () => {};
beforeAll(() => { GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 1000 }); (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; });
afterEach(async () => {
  await cleanup(); cleanup = async () => {};
  window.localStorage.clear();
  (await import("@/components/business-app/foundation/toasts")).clearToasts();
  (await import("@/components/layout/overlayStack")).resetOverlayStack();
  document.body.innerHTML = "";
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

const OWNER_PERMISSIONS: GrantedSpace["permissions"] = ["read", "prepare", "approve", "manage", "assign_owner", "download", "export"];
const EDITOR_PERMISSIONS: GrantedSpace["permissions"] = ["read", "prepare", "download", "export"];

async function mount({ width = 1440, role = "owner", prepare = true, permissions, tweak = receipts => receipts, markRead, bar = false, approveListos, receiptsOnly = false }: { approveListos?: BusinessDataSource["approveListos"]; width?: number; role?: GrantedSpace["role"]; prepare?: boolean; permissions?: GrantedSpace["permissions"]; tweak?: (receipts: ReceiptSummary[]) => ReceiptSummary[]; markRead?: (id: string, cursor: string) => Promise<ReceiptActivity>; bar?: boolean; receiptsOnly?: boolean } = {}) {
  (window as unknown as { happyDOM: { setViewport: (size: { width: number; height: number }) => void } }).happyDOM.setViewport({ width, height: 1000 });
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const { Plus } = await import("lucide-react");
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const Inbox = (await import("@/components/business-app/BusinessInboxPanel")).default;
  const BusinessHeader = (await import("@/components/business-app/foundation/BusinessHeader")).default;
  const source = (await import("@/components/business-app/fixture-data")).createFixtureBusinessDataSource({ chatAvailable: false });
  const i18n = (await import("i18next")).default.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: (await import("@/public/locales/es-419/common.json")).default } }, interpolation: { escapeValue: false } });
  const seed = (await source.receipts("all"))[0];
  let receipts: ReceiptSummary[] = tweak([
    { ...seed, id: "review-receipt", merchant: "Recibo admitido", bandeja: { por_revisar: true, leyendo: false, con_problema: false }, bandeja_group: { group: "attention", reason: "missing_ncf", draft_id: "draft-review", version: 2 } },
    { ...seed, id: "reading-receipt", merchant: "Recibo en lectura", status: "queued", bandeja: { por_revisar: false, leyendo: true, con_problema: false }, bandeja_group: { group: "reading", reason: "reading", draft_id: null, version: null } },
    { ...seed, id: "problem-receipt", merchant: "Recibo con problema", status: "needs_attention", bandeja: { por_revisar: false, leyendo: false, con_problema: true }, bandeja_group: { group: "attention", reason: "unreadable", draft_id: null, version: null } },
    ...["uno", "dos", "tres"].map((name, index) => ({ ...seed, id: `listo-${name}`, merchant: `Listo ${name}`, bandeja: { por_revisar: true, leyendo: false, con_problema: false }, bandeja_group: { group: "listo" as const, reason: null, draft_id: `draft-${name}`, version: index + 1 } })),
  ]);
  const notes: BusinessCapture[] = receiptsOnly ? [] : [{ draft_id: "admitted-note", source_id: "note-source", version: 1, revision: 1, text: "Nota admitida", received_at: seed.received_at, review_state: "open" }];
  const emails = receiptsOnly ? [] : (await source.emailDeliveries()).filter(email => email.id === "email-boletin" || email.id === "email-estacion");
  assert.equal(emails.length, receiptsOnly ? 0 : 2);
  const globalActivity = { reading_count: 92, unread_count: 94, presentation: "unread" as const, pending_review_count: 95, needs_attention_count: 93, ready_to_review_count: 91, bandeja_attention_count: 96, bandeja_listo_count: 97 };
  const chosen: GrantedSpace = { space_id: "count-business", grant_id: "count-grant", name: "Negocio sintético", role, capabilities: !prepare ? ["read"] : role === "owner" ? ["read", "prepare", "approve"] : ["read", "prepare"], permissions: permissions ?? (role === "owner" ? OWNER_PERMISSIONS : EDITOR_PERMISSIONS), access_seen: true };
  let uploads = 0;
  let reloads = 0;
  const opened: BusinessPanelState[] = [];
  let context: BusinessContextValue = { receivingChannels: { email: { available: true }, whatsapp: { available: true } },
    userId: "count-person", source: { ...source, receiptPage: async () => ({ items: receipts, activity: globalActivity }), ...(receiptsOnly ? { captures: async () => ({ items: [], has_more: false }) } : {}), ...(markRead ? { markReceiptRead: markRead } : {}), ...(approveListos ? { approveListos } : {}) },
    records: { workspace: await source.workspace(), overview: null, inbox: receipts, notes, notesTruncated: false, emails, error: false, receiptActivity: globalActivity },
    spaces: [chosen], chosen, chooseBusiness: () => {}, markAccessSeen: async () => {}, lostAccess: false, clearLostAccess: () => {}, revision: 0, reload: () => { reloads++; }, refresh: async () => "updated",
    period: { key: "all", from: "", to: null }, setPeriod: () => {}, panel: { kind: "inbox" }, openPanel: next => opened.push(next),
    actions: { create: role === "owner" && prepare ? [{ id: "upload_receipt", label: "Agregar", icon: Plus, run: () => { uploads++; } }] : [], composer: [], starterEntries: [] },
    bridge: null, attachedReceipt: null, clearAttachedReceipt: () => {}, emailRefresh: { refresh: () => {}, refreshing: false, stalled: false }, retrySources: () => {},
  };
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  const render = () => act(async () => { root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}>{bar ? <header data-testid="top-bar"><BusinessHeader home={false} name={null} title="Bandeja" screen="inbox" /></header> : null}<Inbox /></BusinessContext.Provider></I18nextProvider>); });
  cleanup = async () => { await act(async () => root.unmount()); host.remove(); };
  await render();
  const settle = async (ready: () => boolean) => { for (let i = 0; i < 50; i++) { await act(async () => { await new Promise(resolve => setTimeout(resolve, 10)); }); if (ready()) return; } throw new Error(`Missing expected state: ${host.textContent}`); };
  await settle(() => host.querySelector('[data-testid="reception-row"], [data-testid="reception-empty"]') !== null);
  const click = async (node: HTMLElement | null | undefined) => { assert.ok(node); await act(async () => node.click()); };
  const tab = (key: string) => host.querySelector<HTMLButtonElement>(`#reception-tab-${key}`);
  const badge = (key: string) => tab(key)?.querySelector("span")?.textContent;
  const row = (name: string) => [...host.querySelectorAll<HTMLElement>('[data-testid="reception-row"]')].find(element => element.textContent?.includes(name));
  const remount = async () => { await act(async () => root.unmount()); const again = createRoot(host); await act(async () => { again.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}><Inbox /></BusinessContext.Provider></I18nextProvider>); }); cleanup = async () => { await act(async () => again.unmount()); host.remove(); }; await settle(() => host.querySelector('[data-testid="reception-row"]') !== null); };
  return { host, context, opened, remount, uploads: () => uploads, reloads: () => reloads, click, tab, badge, row, act, settle, async changeArrivals() { receipts = [...receipts.filter(receipt => receipt.id !== "review-receipt"), { ...receipts[0], id: "new-receipt", merchant: "Recibo sin admitir" }]; context = { ...context, revision: context.revision + 1 }; await render(); await settle(() => host.textContent?.includes("Actualizar lista") === true); }, async demote(id: string) { receipts = receipts.map(receipt => receipt.id === id ? { ...receipt, bandeja_group: { group: "attention" as const, reason: "missing_ncf", draft_id: receipt.bandeja_group?.draft_id ?? null, version: 9 } } : receipt); context = { ...context, revision: context.revision + 1 }; await render(); } };
}

const rows = (page: Awaited<ReturnType<typeof mount>>) => [...page.host.querySelectorAll<HTMLElement>('[data-testid="reception-row"]')];
const receiptIds = ["listo-dos", "listo-tres", "listo-uno", "problem-receipt", "reading-receipt", "review-receipt"];

for (const width of [1440, 390]) for (const role of ["owner", "accountant"] as const) test(`the live Bandeja renders Reception and ${role} actions at ${width}px`, async () => {
  // A desktop shell shows the top bar, which holds the one Agregar; a phone keeps Agregar in the Bandeja toolbar.
  const page = await mount({ width, role, bar: width >= 768 });
  const titles = [...page.host.querySelectorAll("h2")].filter(heading => heading.textContent === "Bandeja");
  assert.equal(titles.length, width < 768 ? 1 : 0, "desktop uses the existing Workspace header, phones retain the panel heading");
  const uploads = page.host.querySelectorAll<HTMLButtonElement>('[data-testid="business-primary-upload"]');
  assert.ok(uploads.length <= 1, "Agregar appears once");
  const upload = uploads[0] ?? null;
  if (upload) assert.ok(upload.closest(width < 768 ? '[data-testid="reception-add"]' : '[data-testid="top-bar"] [data-testid="add-menu-header"]'), width < 768 ? "a phone keeps Agregar in the toolbar" : "a wide screen keeps Agregar in the top bar");
  const review = page.host.querySelector<HTMLButtonElement>('[data-testid="business-primary-review"]');
  if (role === "owner") { assert.ok(upload); assert.equal(review, null); await page.click(upload); assert.equal(page.uploads(), 1); }
  else { assert.equal(upload, null); assert.ok(review); assert.equal(review.textContent, "Revisar recibos"); await page.click(review); assert.deepEqual(page.opened, [{ kind: "receipt", receiptId: "listo-dos", list: "inbox", receiptIds }]); }
});

test("a read-only owner sees no Add capability in the live Bandeja", async () => {
  const page = await mount({ prepare: false });
  assert.equal(page.host.querySelector('[data-testid="business-primary-upload"]'), null);
  assert.equal(page.host.querySelector('[data-testid="business-primary-review"]'), null);
});

for (const [who, options] of [["an accountant", { role: "accountant" as const }], ["an owner who cannot add", { prepare: false }], ["a viewer", { role: "accountant" as const, prepare: false, permissions: ["read"] as GrantedSpace["permissions"] }]] as const) test(`${who} gets no menu in the Bandeja, and Exportar is not here`, async () => {
  const page = await mount(options);
  assert.equal(page.host.querySelector('[data-testid="reception-add"]'), null);
  assert.equal(page.host.querySelector('[data-testid="business-primary-upload"]'), null);
  assert.equal(page.host.textContent?.includes("Exportar registros"), false);
  assert.equal(page.host.textContent?.includes("Más acciones"), false);
});

test("the owner keeps Agregar and the forwarding address, on the top bar or on a phone, and the Bandeja has no Más acciones", async () => {
  const page = await mount({ bar: true });
  assert.equal(page.host.querySelector('[data-testid="reception-add"]'), null, "the toolbar does not repeat Agregar");
  const bar = page.host.querySelector('[data-testid="top-bar"] [data-testid="add-menu-header"]');
  assert.ok(bar?.querySelector('[data-testid="business-primary-upload"]'), "the top bar holds Agregar");
  await cleanup(); cleanup = async () => {};
  document.body.innerHTML = "";

  const phone = await mount({ width: 390 });
  assert.ok(phone.host.querySelector('[data-testid="reception-add"] [data-testid="business-primary-upload"]'));
  await phone.click(phone.host.querySelector<HTMLButtonElement>('[data-testid="reception-add"] button[aria-haspopup="menu"]'));
  await phone.settle(() => document.querySelector('[role="menu"]')?.textContent?.includes("recibos-7f3a9c21") === true);
  const items = [...document.querySelectorAll('[role="menu"] [role="menuitem"]')].map(item => item.textContent);
  assert.deepEqual(items, ["Copiar dirección de reenvío"]);
});

test("the Bandeja opens on Todos with its four tabs, and nothing else from the old design", async () => {
  const page = await mount({ tweak: receipts => receipts.map(receipt => ({ ...receipt, activity: { state: "ready" as const, unread: false, completion_cursor: "c" } })) });
  assert.deepEqual([...page.host.querySelectorAll('[role="tab"]')].map(tab => tab.id), ["reception-tab-all", "reception-tab-attention", "reception-tab-listos", "reception-tab-eliminados"]);
  assert.equal(page.tab("all")?.getAttribute("aria-selected"), "true");
  assert.equal(page.badge("all"), undefined, "Todos has no count");
  for (const word of ["En proceso", "Archivados", "Más acciones", "Vista previa"]) assert.equal(page.host.textContent?.includes(word), false, word);
  assert.equal(rows(page).length, 9, "six receipts, one note and two emails");
  assert.equal(rows(page).filter(row => row.getAttribute("data-unseen") === "true").length, 0, "nothing is seeded as unseen");
  assert.deepEqual([...page.host.querySelectorAll("#reception-list > div:first-child > span:not(.sr-only)")].map(cell => cell.textContent).filter(Boolean), ["Contenido", "Adjunto", "Canal", "Canal", "Estado", "Llegada"], "Monto, Moneda and Remitente stay off; the second Canal is the heading the width swaps in");
});

const EMPTY_TITLE = { attention: "Nada necesita atención", listos: "No hay recibos listos", eliminados: "No hay documentos eliminados" } as const;
const BUSINESSES: Record<string, Record<keyof typeof EMPTY_TITLE, (receipts: ReceiptSummary[]) => ReceiptSummary[]>> = {
  "no documents": { attention: () => [], listos: () => [], eliminados: () => [] },
  "documents in Todo": { attention: receipts => receipts.filter(receipt => receipt.bandeja_group?.group === "listo"), listos: receipts => receipts.filter(receipt => receipt.bandeja_group?.group !== "listo"), eliminados: receipts => receipts },
};

for (const [business, tweaks] of Object.entries(BUSINESSES)) for (const view of ["attention", "listos", "eliminados"] as const) test(`on a Business with ${business}, an empty ${view} tab shows its own title and offers no Ver todo`, async () => {
  const page = await mount({ tweak: tweaks[view], receiptsOnly: true });
  assert.equal(rows(page).length > 0, business === "documents in Todo");
  await page.click(page.tab(view));
  await page.settle(() => page.host.querySelector('[data-testid="reception-empty"]') !== null);
  const empty = page.host.querySelector('[data-testid="reception-empty"]');
  assert.equal(empty?.querySelector("h3")?.textContent, EMPTY_TITLE[view]);
  assert.doesNotMatch(empty?.textContent ?? "", /Ver todo/, "Todas las fechas already widens the list; the empty tab adds no second way back");
});

test("the tab numbers are the server's, not a count of the rows loaded", async () => {
  const page = await mount();
  assert.deepEqual([page.badge("attention"), page.badge("listos")], ["96", "97"]);
  await page.click(page.tab("listos"));
  assert.deepEqual([page.badge("attention"), page.badge("listos")], ["96", "97"], "the active view does not move the numbers");
});

test("a receipt is unseen only when the server says its activity is unread, and never marks anything locally", async () => {
  const unread = (receipt: ReceiptSummary) => receipt.id === "review-receipt" ? { ...receipt, activity: { state: "ready" as const, unread: true, completion_cursor: "c1" } } : { ...receipt, activity: { state: "ready" as const, unread: false, completion_cursor: "c0" } };
  const page = await mount({ tweak: receipts => receipts.map(unread), markRead: async (_id, cursor) => ({ state: "ready", unread: false, completion_cursor: cursor }) });
  const dotted = () => rows(page).filter(row => row.getAttribute("data-unseen") === "true").map(row => row.textContent);
  assert.equal(dotted().length, 1);
  assert.match(dotted()[0] ?? "", /Recibo admitido/);
  await page.click(rows(page).find(row => row.textContent?.includes("Nota admitida"))!.querySelector<HTMLElement>("button"));
  assert.equal(dotted().length, 1, "opening a note marks nothing locally");
});

test("an open row keeps the server's unseen dot until the server says it was seen", async () => {
  const page = await mount({ tweak: receipts => receipts.map(receipt => ({ ...receipt, activity: { state: "ready" as const, unread: receipt.id === "review-receipt", completion_cursor: "c1" } })) });
  page.context.panel = { kind: "receipt", receiptId: "review-receipt", list: "inbox" };
  page.context.revision++;
  await page.remount();
  const open = page.row("Recibo admitido")!;
  assert.equal(open.getAttribute("aria-current"), "true");
  assert.equal(open.getAttribute("data-unseen"), "true", "opening alone is not the server's acknowledgement");
  assert.ok(open.querySelector('[class*="unseenDot"]'));
  page.context.records = { ...page.context.records, inbox: page.context.records.inbox!.map(receipt => ({ ...receipt, activity: { state: "ready" as const, unread: false, completion_cursor: "c1" } })) };
  page.context.source = { ...page.context.source, receiptPage: async () => ({ items: page.context.records.inbox!, activity: page.context.records.receiptActivity! }) };
  page.context.revision++;
  await page.remount();
  await page.settle(() => page.row("Recibo admitido")?.getAttribute("data-unseen") === "false");
  assert.equal(page.row("Recibo admitido")!.getAttribute("aria-current"), "true");
  assert.equal(page.row("Recibo admitido")!.querySelector('[class*="unseenDot"]'), null);
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

test("every row has one quiet Abrir, the row click does the same, and nothing else differs by state", async () => {
  const page = await mount();
  const buttons = () => rows(page).map(row => [...row.querySelectorAll("button")].at(-1)!);
  assert.deepEqual([...new Set(buttons().map(button => button.textContent))], ["Abrir"]);
  assert.equal(buttons().length, 9);
  const opened = async (name: string, press: (row: HTMLElement) => HTMLElement) => { page.opened.length = 0; await page.click(press(page.row(name)!)); return page.opened.at(-1); };
  const abrir = (row: HTMLElement) => [...row.querySelectorAll<HTMLElement>("button")].at(-1)!;
  const cell = (row: HTMLElement) => row.querySelector<HTMLElement>('[data-testid="reception-channel"]')!;
  for (const [name, target] of [
    ["Recibo admitido", { kind: "receipt", receiptId: "review-receipt", list: "inbox" }],
    ["Recibo en lectura", { kind: "receipt", receiptId: "reading-receipt", list: "inbox" }],
    ["Recibo con problema", { kind: "receipt", receiptId: "problem-receipt", list: "inbox" }],
    ["Nota admitida", { kind: "draft", draftId: "admitted-note", list: "inbox" }],
  ] as const) {
    assert.deepEqual(await opened(name, abrir), { ...target, receiptIds }, `Abrir on ${name}`);
    assert.deepEqual(await opened(name, cell), { ...target, receiptIds }, `the row click on ${name}`);
  }
});

const settings = (page: Awaited<ReturnType<typeof mount>>) => page.click(page.host.querySelector<HTMLElement>('button[aria-label="Opciones de vista"]'));
const toggleSender = (page: Awaited<ReturnType<typeof mount>>) => page.click([...document.querySelectorAll("label")].find(label => label.textContent === "Remitente")!.querySelector("input"));
const senderCells = (page: Awaited<ReturnType<typeof mount>>) => page.host.querySelectorAll('[data-testid="reception-sender"]').length;
const filterSender = async (page: Awaited<ReturnType<typeof mount>>, name: string) => {
  await page.click([...page.host.querySelectorAll<HTMLElement>("button")].find(button => button.textContent === "Filtros"));
  await page.click([...document.querySelectorAll<HTMLElement>('[role="tablist"][aria-orientation="vertical"] button')].find(button => button.textContent === "Remitente"));
  await page.click([...document.querySelectorAll("label")].find(label => label.textContent?.includes(name))!.querySelector("input"));
  await page.click([...document.querySelectorAll<HTMLElement>("button")].find(button => button.textContent === "Aplicar"));
};

test("Remitente is off by default, still offered, and filtering by it works either way", async () => {
  const page = await mount();
  assert.equal(senderCells(page), 0, "off for a person with no saved choice");
  await filterSender(page, "noticias@proveedor.example");
  assert.deepEqual(rows(page).map(row => row.textContent?.includes("Boletín semanal")), [true], "the filter works with the column off");
  await settings(page);
  await toggleSender(page);
  assert.equal(senderCells(page), 1);
  assert.equal(page.host.querySelector('[data-testid="reception-sender"]')?.textContent, "noticias@proveedor.example");
});

test("the tabs own status: Filtros adds nothing for a tab and the four tabs stay fixed", async () => {
  const page = await mount();
  for (const key of ["attention", "listos", "all"]) {
    await page.click(page.tab(key));
    assert.equal(page.host.querySelector('[data-testid="reception-filter-chips"]')?.textContent, "", "a tab adds no chip");
    assert.equal([...page.host.querySelectorAll("button")].find(button => button.textContent?.includes("Filtros"))?.textContent, "Filtros", "a tab adds no count");
  }
  await page.click([...page.host.querySelectorAll<HTMLElement>("button")].find(button => button.textContent === "Filtros"));
  assert.deepEqual([...document.querySelectorAll('[role="tablist"][aria-orientation="vertical"] button')].map(button => button.textContent), ["Canal", "Remitente"]);
  assert.equal(page.host.querySelectorAll('[role="tab"][id^="reception-tab-"]').length, 4);
});

test("the state column is Estado with the tag on Todos, Motivo with the plain reason on Necesitan atención, and gone on Listos", async () => {
  const page = await mount();
  const heading = (word: string) => [...page.host.querySelectorAll("#reception-list > div:first-child > span")].some(cell => cell.textContent === word);
  const estado = () => heading("Estado");
  const row = () => page.row("Recibo con problema")!;
  assert.equal(estado(), true);
  assert.equal(row().querySelector('[data-testid="status-pill"]')?.textContent, "Necesita atención");
  assert.equal(row().querySelector('[data-testid="reception-reason"]'), null, "the tag alone on Todos");
  assert.equal(heading("Motivo"), false);
  await page.click(page.tab("attention"));
  assert.equal(heading("Motivo"), true, "every row here needs attention, so the column names why");
  assert.equal(estado(), false);
  await page.click(page.host.querySelector<HTMLButtonElement>('button[aria-label="Opciones de vista"]'));
  const columns = [...document.querySelectorAll('section[aria-label="Columnas"] li')].map(item => item.textContent);
  assert.ok(columns.some(text => text?.startsWith("Motivo")), "the settings name the column as the header does");
  assert.ok(!columns.some(text => text?.startsWith("Estado")));
  assert.equal(row().querySelector('[data-testid="status-pill"]'), null, "no tag where the tab already says it");
  assert.equal(row().querySelector('[data-testid="reception-reason"]')?.textContent, "No se pudo leer");
  assert.equal(page.row("Recibo en lectura"), undefined, "a read still running shows only on Todos");
  await page.click(page.tab("listos"));
  assert.equal(estado(), false);
  assert.equal(heading("Motivo"), false);
  assert.equal(page.row("Listo uno")?.querySelector('[data-testid="status-pill"]'), null);
  assert.equal(page.row("Listo uno")?.querySelector('[data-testid="reception-reason"]'), null);
});

test("the file button names the file in one tooltip and keeps its label", async () => {
  const page = await mount();
  const { TOOLTIP_DELAY_MS } = await import("@/components/ui/Tooltip");
  const file = page.row("Recibo con problema")!.querySelector<HTMLButtonElement>('[data-testid="reception-original"]')!;
  const name = (page.context.records.inbox.find(receipt => receipt.id === "problem-receipt")!.filename)!;
  assert.ok(name);
  assert.equal(file.hasAttribute("title"), false, "a native title would show a second tooltip");
  assert.equal(file.getAttribute("aria-label"), `Abrir original: ${name}`);
  await page.act(async () => { file.dispatchEvent(new MouseEvent("mouseover", { bubbles: true })); });
  await page.act(async () => { await new Promise(resolve => setTimeout(resolve, TOOLTIP_DELAY_MS + 30)); });
  assert.equal(document.querySelectorAll('[role="tooltip"]').length, 1);
  assert.equal(document.querySelector('[role="tooltip"]')?.textContent, name);
});

test("the boxes live only on Listos, for the owner", async () => {
  const page = await mount();
  const boxes = () => page.host.querySelectorAll("#reception-list input[type=checkbox]").length;
  const slots = () => page.host.querySelectorAll('[class~="checkbox"]').length;
  assert.equal(page.host.querySelector('[data-testid="reception-preview"]')?.getAttribute("data-selectable"), "false");
  assert.equal(boxes(), 0);
  assert.equal(slots(), 0, "no empty box column either");
  await page.click(page.tab("attention"));
  assert.equal(boxes() + slots(), 0);
  await page.click(page.tab("listos"));
  assert.equal(boxes(), 4, "three rows and the page box");
});

test("the row returns to the tab it was opened from", async () => {
  const page = await mount();
  await page.click(page.tab("listos"));
  await page.click(box(page, "Listo uno"));
  await page.click([...page.row("Listo dos")!.querySelectorAll<HTMLElement>("button")].at(-1));
  assert.equal(page.opened.at(-1)?.kind, "receipt");
  await page.remount();
  assert.equal(page.tab("listos")?.getAttribute("aria-selected"), "true");
  assert.equal(box(page, "Listo uno")?.checked, true);
});

test("a WhatsApp receipt shows no sender instead of one inferred from its merchant", async () => {
  const page = await mount({ tweak: receipts => receipts.map(receipt => receipt.id === "review-receipt" ? { ...receipt, channel: "whatsapp" as const, email_delivery_ids: [] } : receipt) });
  await settings(page);
  await toggleSender(page);
  const row = rows(page).find(item => item.textContent?.includes("Recibo admitido"))!;
  const sender = row.querySelector('[data-testid="reception-sender"]');
  assert.equal(sender?.getAttribute("data-known"), "false");
  assert.equal(sender?.getAttribute("aria-label"), "Remitente no disponible");
});

const box = (page: Awaited<ReturnType<typeof mount>>, name: string) => page.row(name)?.querySelector<HTMLInputElement>('input[type="checkbox"]') ?? null;
const header = (page: Awaited<ReturnType<typeof mount>>) => page.host.querySelector<HTMLInputElement>('input[aria-label="Seleccionar esta página"]');
const approveSelected = (page: Awaited<ReturnType<typeof mount>>) => page.host.querySelector<HTMLButtonElement>('[data-testid="reception-approve-selected"]');
const confirmButton = () => document.querySelector<HTMLButtonElement>('[role="alertdialog"] button:last-of-type');
const answering = (outcome: (item: ListoItem) => Partial<ListoApproval> = () => ({ outcome: "applied" })) => {
  const calls: { items: ListoItem[]; key: string }[] = [];
  const approveListos: BusinessDataSource["approveListos"] = async (items, key) => { calls.push({ items: [...items], key }); return { results: items.map(item => ({ draft_id: item.draft_id, outcome: "applied" as const, ...outcome(item) })) }; };
  return { calls, approveListos };
};

test("the page box takes the Listos rows", async () => {
  const page = await mount();
  await page.click(page.tab("listos"));
  assert.ok(box(page, "Listo uno"));
  await page.click(header(page));
  assert.deepEqual(["uno", "dos", "tres"].map(name => box(page, `Listo ${name}`)?.checked), [true, true, true]);
  assert.equal(page.host.querySelector('[role="region"]')?.textContent?.includes("3 seleccionados"), true);
  await page.click(header(page));
  assert.equal(approveSelected(page), null, "taking the page box off clears the page");
});

for (const [who, options] of [["an accountant", { role: "accountant" as const }], ["a viewer", { prepare: false }]] as const) test(`${who} sees no selection and no Aprobar todos, on the server's word`, async () => {
  const page = await mount(options);
  assert.equal(page.host.querySelector('input[type="checkbox"]'), null);
  await page.click(page.tab("listos"));
  assert.equal(page.host.querySelector('input[type="checkbox"]'), null);
  assert.equal(page.host.querySelector('[data-testid="reception-approve-all"]'), null);
  assert.ok(page.row("Listo uno"), "the row itself still shows");
});

test("nothing is approved until the owner confirms the count", async () => {
  const { calls, approveListos } = answering();
  const page = await mount({ approveListos });
  await page.click(page.tab("listos"));
  await page.click(box(page, "Listo uno"));
  await page.click(box(page, "Listo tres"));
  await page.click(approveSelected(page));
  assert.equal(calls.length, 0);
  assert.match(document.querySelector('[role="alertdialog"]')?.textContent ?? "", /¿Aprobar 2 recibos\?/);
  await page.click([...document.querySelectorAll<HTMLButtonElement>('[role="alertdialog"] button')].find(button => button.textContent === "Cancelar"));
  assert.equal(calls.length, 0);
  assert.equal(box(page, "Listo uno")?.checked, true, "cancelling keeps the selection");
  await page.click(approveSelected(page));
  await page.click(confirmButton());
  await page.settle(() => calls.length === 1 && page.reloads() > 0);
  assert.deepEqual(calls[0].items, [{ draft_id: "draft-tres", version: 3 }, { draft_id: "draft-uno", version: 1 }]);
  assert.ok(calls[0].key);
  assert.equal(page.host.querySelector('[data-testid="reception-approval-failure"]'), null);
});

test("a second press of the confirm sends nothing more", async () => {
  const { calls, approveListos } = answering();
  const page = await mount({ approveListos });
  await page.click(page.tab("listos"));
  await page.click(box(page, "Listo uno"));
  await page.click(approveSelected(page));
  const button = confirmButton()!;
  await page.act(async () => { button.click(); button.click(); });
  await page.settle(() => page.reloads() > 0);
  assert.equal(calls.length, 1);
});

test("Aprobar todos sits on Listos and takes every Listos row in view, past the page", async () => {
  const { calls, approveListos } = answering();
  const page = await mount({ approveListos });
  assert.equal(page.host.querySelector('[data-testid="reception-approve-all"]'), null, "not on Todos");
  await page.click(page.tab("listos"));
  await page.click(page.host.querySelector<HTMLButtonElement>('[data-testid="reception-approve-all"]'));
  assert.match(document.querySelector('[role="alertdialog"]')?.textContent ?? "", /¿Aprobar 3 recibos\?/);
  await page.click(confirmButton());
  await page.settle(() => calls.length === 1);
  assert.deepEqual(calls[0].items.map(item => item.draft_id).sort(), ["draft-dos", "draft-tres", "draft-uno"]);
});

test("a new receipt or a poll leaves the selection alone, and a row that stops being Listos cannot be sent", async () => {
  const { calls, approveListos } = answering();
  const page = await mount({ approveListos });
  await page.click(page.tab("listos"));
  await page.click(box(page, "Listo uno"));
  await page.click(box(page, "Listo dos"));
  await page.changeArrivals();
  await page.settle(() => [...page.host.querySelectorAll("button")].some(button => button.textContent === "Actualizar lista"));
  assert.equal(box(page, "Listo uno")?.checked, true);
  await page.click([...page.host.querySelectorAll<HTMLButtonElement>("button")].find(button => button.textContent === "Actualizar lista"));
  assert.equal(box(page, "Listo dos")?.checked, true, "bringing the new row in keeps it too");
  await page.demote("listo-dos");
  await page.settle(() => !page.row("Listo dos"));
  assert.match(page.host.querySelector('[role="region"]')?.textContent ?? "", /1 seleccionado/);
  await page.click(approveSelected(page));
  await page.click(confirmButton());
  await page.settle(() => calls.length === 1);
  assert.deepEqual(calls[0].items.map(item => item.draft_id), ["draft-uno"]);
});

test("a partial failure says which, and those stay selected in Listos; only the unsettled one is replayed, under its own key", async () => {
  const { calls, approveListos } = answering(item => item.draft_id === "draft-dos" ? { outcome: "refused", code: "duplicate_comprobante" } : item.draft_id === "draft-tres" ? (calls.length > 1 ? { outcome: "applied" } : { outcome: "outcome_unknown", code: "business_recording_unsettled" }) : { outcome: "applied" });
  const page = await mount({ approveListos });
  await page.click(page.tab("listos"));
  await page.click(page.host.querySelector<HTMLButtonElement>('[data-testid="reception-approve-all"]'));
  await page.click(confirmButton());
  const failure = () => page.host.querySelector<HTMLElement>('[data-testid="reception-approval-failure"]');
  await page.settle(() => failure() !== null);
  assert.equal(failure()?.getAttribute("role"), "alert");
  assert.match(failure()?.textContent ?? "", /No se aprobaron 2 de 3/);
  const failedRows = [...page.host.querySelectorAll('[data-testid="reception-approval-failed-row"]')].map(row => row.textContent);
  assert.deepEqual(failedRows, ["Listo dosEste comprobante ya está registrado", "Listo tresNo sabemos si se aprobó. Reintenta para confirmarlo."]);
  assert.equal(box(page, "Listo uno")?.checked, false);
  assert.deepEqual([box(page, "Listo dos")?.checked, box(page, "Listo tres")?.checked], [true, true]);
  await page.click([...failure()!.querySelectorAll<HTMLButtonElement>("button")].find(button => button.textContent === "Reintentar"));
  await page.settle(() => calls.length === 2);
  assert.deepEqual(calls[1], { items: [{ draft_id: "draft-tres", version: 3 }], key: calls[0].key });
  await page.settle(() => /No se aprobó 1 de 3/.test(failure()?.textContent ?? ""));
  assert.equal([...failure()!.querySelectorAll("button")].some(button => button.textContent === "Reintentar"), false, "a refusal is not retried");
});

test("a request that fails shows what was refused, its Ref. and a way out", async () => {
  const approveListos: BusinessDataSource["approveListos"] = async () => { throw Object.assign(new Error("server"), { status: 500, code: "internal_error", requestId: "request-7f3a9c21" }); };
  const page = await mount({ approveListos });
  await page.click(page.tab("listos"));
  await page.click(box(page, "Listo uno"));
  await page.click(approveSelected(page));
  await page.click(confirmButton());
  const failure = () => page.host.querySelector<HTMLElement>('[data-testid="reception-approval-failure"]');
  await page.settle(() => failure() !== null);
  assert.match(failure()?.textContent ?? "", /Listo uno/);
  assert.match(failure()?.textContent ?? "", /Ref\./);
  assert.ok([...failure()!.querySelectorAll("button")].some(button => button.textContent === "Reintentar"));
  assert.equal(box(page, "Listo uno")?.checked, true);
});

test("the keyboard reaches the tabs by arrow and a Listos box by Tab order", async () => {
  const page = await mount();
  const tabs = page.host.querySelector<HTMLElement>('[role="tablist"]')!;
  page.tab("all")?.focus();
  await page.act(async () => { tabs.dispatchEvent(new KeyboardEvent("keydown", { key: "End", bubbles: true })); });
  assert.equal(page.tab("eliminados")?.getAttribute("aria-selected"), "true");
  assert.equal(document.activeElement, page.tab("eliminados"));
  await page.act(async () => { tabs.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true })); });
  assert.equal(document.activeElement, page.tab("listos"));
  assert.ok(box(page, "Listo uno")?.tabIndex !== -1);
});

const headings = (page: Awaited<ReturnType<typeof mount>>) => [...page.host.querySelectorAll<HTMLElement>("#reception-list [data-column]")].sort((a, b) => Number(a.style.getPropertyValue("--col")) - Number(b.style.getPropertyValue("--col"))).map(cell => cell.dataset.column);
const setting = (key: string) => document.querySelector<HTMLElement>(`[data-column-setting="${key}"]`);
const columnBox = (key: string) => setting(key)?.querySelector<HTMLInputElement>('input[type="checkbox"]');

test("Bandeja's column menu is the Registros menu: every column is a box, none is locked by name, and the action is no column", async () => {
  const page = await mount();
  await settings(page);
  const keys = [...document.querySelectorAll<HTMLElement>("[data-column-setting]")].map(row => row.dataset.columnSetting);
  assert.deepEqual(keys, ["document", "file", "source", "sender", "amount", "currency", "status", "arrival"]);
  for (const key of keys) {
    assert.ok(columnBox(key!), `${key} is a box`);
    assert.equal(columnBox(key!)?.disabled, false, `${key} can hide`);
    assert.equal(setting(key!)?.querySelectorAll("button").length, 3, `${key} moves up, down and by its handle`);
  }
  assert.equal(document.querySelector('[role="dialog"] svg.lucide-lock-keyhole'), null);
  assert.equal(document.querySelector('[role="dialog"]')?.textContent?.includes("Siguiente acción"), false);
  assert.deepEqual(headings(page), ["document", "file", "source", "status", "arrival"]);
});

test("Bandeja refuses to hide the last column a tab shows, and Estado does not count on Listos", async () => {
  const page = await mount();
  await settings(page);
  for (const key of ["file", "source", "arrival"]) await page.click(columnBox(key));
  assert.deepEqual(headings(page), ["document", "status"]);
  assert.equal(columnBox("document")?.disabled, true, "Listos would have no column: Estado is not drawn there");
  assert.equal(columnBox("status")?.disabled, false);
  await page.click(columnBox("document"));
  assert.deepEqual(headings(page), ["document", "status"]);
  await page.click(columnBox("status"));
  assert.deepEqual(headings(page), ["document"]);
  assert.equal(columnBox("document")?.disabled, true);
});

test("Bandeja keeps a reorder and a hidden column across a remount, with the cells in the same order as the titles", async () => {
  const page = await mount();
  await settings(page);
  const up = () => setting("arrival")!.querySelector<HTMLButtonElement>("button");
  while (!up()!.disabled) await page.click(up());
  await page.click(columnBox("file"));
  const expected = ["arrival", "document", "source", "status"];
  assert.deepEqual(headings(page), expected);
  const cells = () => [...page.row("Recibo admitido")!.children].map(cell => cell.className);
  assert.match(cells()[0], /arrival/);
  assert.match(cells().at(-1)!, /rowActions/, "the actions stay last");
  await page.remount();
  assert.deepEqual(headings(page), expected);
  await settings(page);
  await page.click([...document.querySelectorAll<HTMLButtonElement>('[role="dialog"] button')].find(button => button.textContent === "Restaurar valores iniciales"));
  assert.deepEqual(headings(page), ["document", "file", "source", "status", "arrival"]);
});
