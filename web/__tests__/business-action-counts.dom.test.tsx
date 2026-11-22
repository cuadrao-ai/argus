import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ReceiptActivityCounts, ReceiptDetail, ReceiptPage } from "@/lib/business-api";
import type { BusinessDossier } from "@/lib/business-dossier";
import type { BusinessDataSource } from "@/components/business-app/business-data";

// The real workspace over a small in-memory server. Once the first page is on screen the server stops answering
// every list and count read, so a count that changes after an action can only be the one the action answered with.
mock.module("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(""), usePathname: () => "/biz", useRouter: () => ({ push() {}, replace() {} }) }));
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1280, height: 900 });
  Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { configurable: true, writable: true, value: true });
});
afterAll(async () => { await GlobalRegistrator.unregister(); });
const cleanups: (() => Promise<void>)[] = [];
afterEach(async () => { while (cleanups.length) await cleanups.pop()!(); document.body.innerHTML = ""; });

const counts = (pending: number, attention: number, listos: number, eliminados: number): ReceiptActivityCounts => ({ reading_count: 0, unread_count: 0, presentation: "none", pending_review_count: pending, ready_to_review_count: listos, bandeja_attention_count: attention, bandeja_listo_count: listos, bandeja_eliminados_count: eliminados });
const BEFORE = counts(2, 1, 1, 1);
// No arithmetic on the rows on screen gives these numbers.
const ANSWERED = counts(41, 17, 23, 5);

async function mount() {
  window.history.replaceState(null, "", "/biz");
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const BusinessPanel = (await import("@/components/business-app/BusinessPanel")).default;
  const BusinessSidebarNav = (await import("@/components/business-app/BusinessSidebarNav")).default;
  const BusinessBottomTabs = (await import("@/components/business-app/BusinessBottomTabs")).default;
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { dossierFixtureIds } = await import("@/components/business-app/dossier-fixtures");
  const { setChosenGrant } = await import("@/lib/business-grant");
  setChosenGrant(null);
  const fixture = createFixtureBusinessDataSource({ chatAvailable: false });
  const ready = await fixture.receipt("rcpt-ferreteria");
  const blurry = await fixture.receipt("rcpt-blurry");
  const readyDossier = await fixture.dossier(dossierFixtureIds.ready);
  const capabilities: ("read" | "prepare" | "approve")[] = ["read", "prepare", "approve"];
  const deletion = { actor: { actor_id: "c93a5c81-2f69-4c0d-932e-1a7c5526c941", display_name: "María Pérez", shown_as: "name" as const }, at: "2026-11-12T10:00:00Z", purge_at: "2026-11-19T10:00:00Z", key: "earlier-delete", previous_state: { state: "open", group: "attention" as const } };
  let items: ReceiptDetail[] = [
    { ...blurry, id: "attention", merchant: "Documento equivocado", filename: "Documento equivocado", delete_available: true, bandeja_group: { group: "attention", reason: "unreadable", label: "cant_read", draft_id: null, version: null } },
    { ...ready, id: "ready", merchant: "Documento listo", draft_id: dossierFixtureIds.ready, version: readyDossier.version, missing_fields: [], delete_available: true, record_context: { ...ready.record_context!, capabilities }, bandeja_group: { group: "listo", reason: null, label: "ready", draft_id: dossierFixtureIds.ready, version: readyDossier.version } },
    { ...blurry, id: "deleted", merchant: "Documento eliminado", filename: "Documento eliminado", status: "dismissed", delete_available: false, restore_available: true, deleted: deletion, bandeja_group: { group: "eliminados", reason: null, label: null, draft_id: null, version: null } },
  ];
  let silent = false;
  let held: Promise<void> | null = null;
  let reads = 0;
  const read = <T,>(answer: () => T): Promise<T> => { reads += 1; return silent ? new Promise<T>(() => {}) : Promise.resolve(answer()); };
  // A receipt the lists stop naming can still be read by its id, as one accepted or moved to another tab can.
  const unlisted = new Set<string>();
  const page = (view: "inbox" | "all"): ReceiptPage => ({ items: items.filter(item => !unlisted.has(item.id) && (view === "all" || !item.deleted)), activity: BEFORE });
  const source: BusinessDataSource = {
    ...fixture,
    receipts: view => read(() => page(view).items),
    receiptPage: view => read(() => page(view)),
    receiptActivity: () => read(() => BEFORE),
    receipt: async id => items.find(item => item.id === id) ?? fixture.receipt(id),
    dossier: async () => ({ ...structuredClone(readyDossier), capabilities: capabilities as BusinessDossier["capabilities"], delete_available: true }),
    captures: async () => ({ items: [], has_more: false }),
    emailDeliveries: async () => [],
    spaces: async () => { const [own] = await fixture.spaces(); return [own, { ...own, space_id: "otro-negocio", grant_id: "otro-acceso", name: "Otro negocio", role: "accountant" as const }]; },
    deleteDocument: async id => { await held; return { document_id: id, deleted: true, inbox_counts: ANSWERED }; },
    restoreDocument: async id => ({ document_id: id, deleted: false, inbox_counts: ANSWERED }),
    purgeDocument: async id => ({ document_id: id, deleted: true, inbox_counts: ANSWERED }),
    approveDraft: async id => ({ ...structuredClone(readyDossier), draft_id: id, version: readyDossier.version + 1, review_state: "accepted", approval_available: false, approval_result: { status: "recorded", activity_id: `expense-${id}`, reviewed_version: readyDossier.version, approved_revision: readyDossier.version, approved_at: "2026-10-10T14:40:00Z", actor: readyDossier.history[0].actor }, inbox_counts: ANSWERED }),
    approveListos: async listed => ({ results: listed.map(item => ({ draft_id: item.draft_id, outcome: "applied" as const, activity_id: `expense-${item.draft_id}` })), inbox_counts: ANSWERED }),
  };
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  let api: ReturnType<typeof useBusiness>;
  const shell = { currentView: "workspace" as const, conversationId: null, isBelowTablet: false, sidebarCollapsed: false, greetingName: null, showWorkspace: () => undefined, newChat: () => undefined, prepareQuestion: () => undefined };
  function Probe() {
    api = useBusiness();
    return <div><BusinessSidebarNav shell={shell} /><BusinessBottomTabs shell={shell} /><BusinessPanel /></div>;
  }
  const host = document.createElement("div"); document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => { root.render(<I18nextProvider i18n={i18n}><BusinessConsentTestProvider accepted><BusinessWorkspaceProvider source={source}><Probe /></BusinessWorkspaceProvider></BusinessConsentTestProvider></I18nextProvider>); });
  cleanups.push(async () => { await act(async () => root.unmount()); host.remove(); });
  const wait = async (done: () => boolean, what: string) => {
    for (let i = 0; i < 80; i++) { if (done()) return; await act(async () => { await new Promise(resolve => setTimeout(resolve, 25)); }); }
    assert.fail(`did not settle: ${what}: ${document.body.textContent?.slice(0, 400)}`);
  };
  const text = (selector: string) => document.querySelector(selector)?.textContent ?? null;
  const shown = () => ({
    sidebar: text('[data-testid="business-inbox-count"]'),
    phoneTab: text('[data-testid="business-bottom-tabs"] button span.absolute'),
    attention: text('[data-testid="reception-count-attention"]'),
    listos: text('[data-testid="reception-count-listos"]'),
    eliminados: text('[data-testid="reception-count-eliminados"]'),
  });
  const on = (held: ReceiptActivityCounts) => ({ sidebar: String(held.pending_review_count), phoneTab: String(held.pending_review_count), attention: String(held.bandeja_attention_count), listos: String(held.bandeja_listo_count), eliminados: String(held.bandeja_eliminados_count) });
  await act(async () => api!.openPanel({ kind: "inbox" }));
  await wait(() => document.querySelectorAll('[data-testid="reception-row"]').length === 2 && shown().sidebar === "2", "the first page");
  assert.deepEqual(shown(), on(BEFORE));
  const click = async (element: Element | null | undefined) => { assert.ok(element, "the control is on the page"); await act(async () => (element as HTMLElement).click()); };
  const confirm = () => click([...document.querySelectorAll<HTMLButtonElement>('[role="alertdialog"] button')].find(node => node.textContent?.trim() !== "Cancelar" && node.textContent?.trim() !== "Ver documento"));
  /** From here the server answers the action and nothing else. */
  const acted = async (action: () => Promise<void>) => {
    silent = true;
    const before = reads;
    await action();
    await wait(() => shown().sidebar === "41", "the action's counts");
    assert.deepEqual(shown(), on(ANSWERED), "every count on screen is the action's answer");
    assert.deepEqual(api!.records.receiptActivity, ANSWERED);
    assert.ok(reads > before, "the lists were asked again, and none of those reads answered");
  };
  const server = { arrives: (id: string) => { items = [{ ...items[0], id, merchant: `Documento ${id}`, filename: `Documento ${id}` }, ...items]; }, loses: (id: string) => { items = items.filter(item => item.id !== id); }, unlists: (id: string) => { unlisted.add(id); } };
  const holdAnswers = () => { silent = true; const answer = Promise.withResolvers<void>(); held = answer.promise; return answer.resolve; };
  return { act, wait, click, confirm, acted, server, shown, holdAnswers, api: () => api! };
}

test("deleting a document shows the counts its answer carries", async () => {
  const page = await mount();
  await page.acted(async () => {
    await page.click(document.querySelector('button[aria-label="Eliminar Documento equivocado"]'));
    await page.confirm();
  });
});

test("restoring a document shows the counts its answer carries", async () => {
  const page = await mount();
  await page.click(document.getElementById("reception-tab-eliminados"));
  await page.wait(() => !!document.querySelector('[data-testid="deleted-document-row"]'), "the deleted row");
  await page.acted(() => page.click([...document.querySelectorAll("button")].find(node => node.textContent?.trim() === "Restaurar")));
});

test("purging a document shows the counts its answer carries", async () => {
  const page = await mount();
  await page.click(document.getElementById("reception-tab-eliminados"));
  await page.wait(() => !!document.querySelector('[data-testid="purge-document"]'), "the deleted row");
  await page.acted(async () => {
    await page.click(document.querySelector('[data-testid="purge-document"]'));
    await page.confirm();
  });
});

test("accepting one receipt shows the counts its answer carries", async () => {
  const page = await mount();
  await page.act(async () => page.api().openPanel({ kind: "receipt", receiptId: "ready", list: "inbox" }));
  await page.wait(() => !!document.querySelector("[data-review-primary]"), "the review");
  await page.acted(async () => {
    await page.click(document.querySelector("[data-review-primary]"));
    if (document.querySelector('[role="alertdialog"]')) await page.confirm();
  });
});

test("accepting the Listos together shows the counts the answer carries", async () => {
  const page = await mount();
  await page.click(document.getElementById("reception-tab-listos"));
  await page.acted(async () => {
    await page.click(document.querySelector('[data-testid="reception-approve-all"]'));
    await page.confirm();
  });
});

test("an open receipt's place follows the list the server last answered with (#2150)", async () => {
  const page = await mount();
  const place = () => document.querySelector('[data-testid="receipt-place"] span')?.textContent ?? null;
  const row = [...document.querySelectorAll('[data-testid="reception-row"]')].find(node => node.textContent?.includes("Documento listo"));
  await page.click([...row!.querySelectorAll("button")].find(node => node.textContent?.trim() === "Abrir"));
  await page.wait(() => place() !== null, "the open receipt's place");
  assert.equal(place(), "1 de 2");

  page.server.arrives("nuevo");
  await page.act(async () => page.api().reload());
  await page.wait(() => place() === "2 de 3", "a row arrived above");
  const move = (label: string) => document.querySelector<HTMLButtonElement>(`[data-testid="receipt-place"] button[aria-label="${label}"]`);
  assert.equal(move("Recibo anterior")?.disabled, false);

  page.server.loses("nuevo");
  await page.act(async () => page.api().reload());
  await page.wait(() => place() === "1 de 2", "the row above left");
  assert.equal(move("Recibo anterior")?.disabled, true);

  // The open receipt leaves the list: it keeps its slot until the person moves on, so next still works.
  page.server.unlists("ready");
  await page.act(async () => page.api().reload());
  await page.wait(() => document.querySelectorAll('[data-testid="reception-row"]').length === 1, "the open receipt left the list");
  assert.equal(place(), "1 de 2");
  await page.click(move("Recibo siguiente"));
  await page.wait(() => place() === "1 de 1", "the next receipt, alone in the list");
  assert.deepEqual(page.api().panel, { kind: "receipt", receiptId: "attention", list: "inbox", receiptIds: ["attention"] });
});

test("a receipt that left its list keeps its slot before the first row that followed it", async () => {
  const { followedReceipts } = await import("@/components/business-app/BusinessReviewShortcuts");
  assert.deepEqual(followedReceipts("b", ["a", "b", "c"], ["n", "a", "b", "c"]), ["n", "a", "b", "c"], "a listed receipt takes the list as it is");
  assert.deepEqual(followedReceipts("b", ["a", "b", "c", "d"], ["n", "a", "d"]), ["n", "a", "b", "d"], "its next row left too, so it sits before the one after");
  assert.deepEqual(followedReceipts("c", ["a", "b", "c"], ["a"]), ["a", "c"], "nothing that followed it is left, so it is last");
  assert.deepEqual(followedReceipts("x", ["a", "b"], ["a"]), ["a"], "a receipt the list never held has no slot");
  assert.deepEqual(followedReceipts(null, ["a", "b"], ["a"]), ["a"]);
});

test("an answer that lands after the person changed Business shows nothing on the other Business", async () => {
  const page = await mount();
  const release = page.holdAnswers();
  await page.click(document.querySelector('button[aria-label="Eliminar Documento equivocado"]'));
  await page.confirm();
  await page.act(async () => page.api().chooseBusiness("otro-acceso"));
  await page.wait(() => page.api().chosen?.grant_id === "otro-acceso" && page.api().records.receiptActivity === null, "the other Business");
  await page.act(async () => { release(); await new Promise(resolve => setTimeout(resolve, 50)); });
  assert.equal(page.api().records.receiptActivity, null, "the first Business's counts stay off this one");
  assert.notEqual(page.shown().sidebar, "41");
});
