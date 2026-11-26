import assert from "node:assert/strict";
import { describe, test } from "bun:test";
import type { Window as HappyWindow } from "happy-dom";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import spanish from "@/public/locales/es-419/common.json";
import type { BandejaLabel, BusinessAccount, BusinessApprovalOptions, ReceiptDetail } from "@/lib/business-api";
import { LISTO_GAPS, type BusinessDossier, type ListoGap, type RncRegistryStatus } from "@/lib/business-dossier";
import type { BusinessContextValue, BusinessPanelState } from "@/components/business-app/BusinessWorkspace";
import { createDossierFixtures, dossierFixtureIds } from "@/components/business-app/dossier-fixtures";

const accounts: BusinessAccount[] = [{ id: "acct-ops", nickname: "Caja", currency: "DOP", type: "cash" }];

type Sent = { acceptGaps: readonly ListoGap[] | undefined };
type Mount = { fetchFile?: typeof fetch; detailsCard?: "support" | "note"; dossier: BusinessDossier; receipt?: ReceiptDetail; readReceipt?: () => ReceiptDetail; size?: "regular" | "narrow" | "page"; panel?: BusinessPanelState; list?: readonly ReceiptDetail[]; refuse?: Partial<Record<"approveDraft", unknown>> };

/** The dossier as a person opens it: from a draft alone, or from a receipt row, on a full page or in the tray at one of its two sizes. */
async function mount({ fetchFile, detailsCard, dossier, receipt, readReceipt, size = "page", panel, list = [], refuse = {} }: Mount) {
  GlobalRegistrator.register({ url: "http://localhost" });
  if (fetchFile) globalThis.fetch = fetchFile;
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  const { act, useState } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const es = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const { RecordTrayContext } = await import("@/components/business-app/record-tray");
  const { default: Panel } = await import("@/components/business-app/ReceiptReviewPanel");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: es } }, interpolation: { escapeValue: false } });
  const sent: Sent[] = [];
  const opened: BusinessPanelState[] = [];
  const context = {
    source: {
      mode: "live",
      dossier: async () => dossier,
      receipt: async () => readReceipt?.() ?? receipt,
      receipts: async () => list,
      receiptSource: async () => new Blob(["x"], { type: "image/png" }),
      dgiiFields: async () => ({ "606": [], "607": [] }),
      approveDraft: async (_id: string, _version: number, _key: string, _action: unknown, options?: BusinessApprovalOptions) => { sent.push({ acceptGaps: options?.acceptGaps }); if (refuse.approveDraft) throw refuse.approveDraft; return dossier; },
    },
    reload: () => undefined,
    records: { inbox: [], workspace: null },
    openPanel: (next: BusinessPanelState) => { opened.push(next); },
    guardPanel: () => () => undefined,
    panel: panel ?? (receipt ? { kind: "receipt", receiptId: receipt.id, list: "inbox" } : { kind: "draft", draftId: dossier.draft_id, list: "transactions" }),
    userId: "synthetic-member",
    chosen: { space_id: dossier.space_id, role: "owner", permissions: ["read", "download"], capabilities: ["read", "prepare", "approve"] },
    actions: { create: [] },
    revision: 0,
  } as unknown as BusinessContextValue;
  const host = document.createElement("div");
  document.body.appendChild(host);
  const slots = { footer: document.createElement("div"), summary: document.createElement("div"), headerActions: document.createElement("div") };
  for (const slot of Object.values(slots)) document.body.appendChild(slot);
  const resizes: boolean[] = [];
  function Tray({ children }: { children: React.ReactNode }) {
    const [narrow, setNarrow] = useState(size === "narrow");
    return <RecordTrayContext.Provider value={{ ...slots, setTitle: () => undefined, settleList: () => undefined, narrow, toggleNarrow: () => { resizes.push(!narrow); setNarrow(!narrow); } }}>{children}</RecordTrayContext.Provider>;
  }
  const target = receipt ? { kind: "receipt" as const, id: receipt.id } : { kind: "draft" as const, id: dossier.draft_id };
  const { ToastViewport } = await import("@/components/business-app/foundation/ToastViewport");
  const tree = <I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}><Panel target={target} detailsCard={detailsCard} /><ToastViewport /></BusinessContext.Provider></I18nextProvider>;
  const root = createRoot(host);
  await act(async () => root.render(size === "page" ? tree : <Tray>{tree}</Tray>));
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
  const all = <T extends Element>(selector: string) => [...document.body.querySelectorAll<T>(selector)];
  const tabs = () => all<HTMLButtonElement>('[role="tab"]').map((tab) => tab.textContent?.replace(/\d+$/, "") ?? "");
  const tab = (name: string) => all<HTMLButtonElement>('[role="tab"]').find((item) => item.textContent?.startsWith(name));
  const panelOf = (key: string) => document.body.querySelector<HTMLElement>(`[data-tab-panel="${key}"]`);
  const button = (label: string) => all<HTMLButtonElement>("button").find((item) => item.textContent?.trim() === label);
  const click = async (node: HTMLElement | null | undefined) => { assert.ok(node, "the control is on screen"); await act(async () => node.click()); await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); }); };
  const close = async () => { await act(async () => root.unmount()); document.body.innerHTML = ""; await GlobalRegistrator.unregister(); };
  return { act, all, tabs, tab, panelOf, button, click, sent, opened, resizes, close, text: () => document.body.textContent ?? "" };
}

const photoOrigin = {
  channel: "whatsapp",
  sent_by: { id: "s1", kind: "whatsapp", phone_last4: "0142" },
  received_at: "2026-11-19T13:41:00Z",
  filename: "foto-0412.jpg",
  size_bytes: 1_258_291,
} as const;

const photoSource = { id: "original", kind: "attachment", connection_id: "receipt-original", media_type: "image/jpeg",
  channel: photoOrigin.channel, received_at: photoOrigin.received_at, filename: photoOrigin.filename } as const;

async function fiscalDossier(over: Partial<BusinessDossier> = {}): Promise<BusinessDossier> {
  const dossier = await createDossierFixtures(accounts).dossier(dossierFixtureIds.fiscal);
  return { ...dossier, review_flags: [], duplicate_candidates: [], blockers: [], approval_available: true, approval_action: "record_expense", bandeja_group: { group: "listo", reason: null, label: "ready" }, listo_gaps: [], confirmable: [], ...over };
}

const attention = (gaps: readonly ListoGap[], confirmable: readonly ListoGap[] = []): Partial<BusinessDossier> => {
  const reasons = {
    missing_rnc: { field: "rnc", words: "business.transactions.layout.workflow.missing.missing_rnc" },
    invalid_ncf: { field: "ncf", words: "business.transactions.layout.workflow.missing.invalid_ncf" },
    missing_itbis: { field: "itbis", words: "business.dossier.placeholder.gap.missing_itbis.title" },
  };
  return {
    bandeja_group: { group: "attention", reason: gaps[0], label: "needs_attention" }, listo_gaps: gaps, confirmable,
    reasons: Object.fromEntries(Object.entries(reasons).filter(([code]) => gaps.some(gap => gap === code))),
  };
};

function receiptOf(dossier: BusinessDossier, over: Partial<ReceiptDetail> = {}): ReceiptDetail {
  return { id: `receipt-${dossier.draft_id}`, draft_id: dossier.draft_id, version: dossier.version, merchant: dossier.facts.counterparty.value, ...photoOrigin, media_type: photoSource.media_type, status: "review_ready", enterable: true, preparable: false, attention: null, activity: { state: "ready", unread: false }, bandeja: { por_revisar: true, con_problema: false, leyendo: false }, bandeja_group: { ...dossier.bandeja_group, draft_id: dossier.draft_id, version: dossier.version }, amount: "4720.00", currency: "DOP", occurred_on: "2026-11-18", ...over } as unknown as ReceiptDetail;
}

/** Words another lane owns: read from the locale, so this suite follows them. */
const copy = (spanish as unknown as { business: { dossier: { confirm: { accept_anyway: string }; duplicate_recorded: string; outcome_unknown: string; refresh: string; refused: string } } }).business.dossier;
const acceptedWord = (spanish as unknown as { business: { history: { approved: string } } }).business.history.approved;

describe("the v2 dossier frame", () => {
  const support = {
    source_id: "00000000-0000-4000-8000-000000000021", receipt_id: "00000000-0000-4000-8000-000000000022",
    filename: "respaldo.png", size_bytes: 1400, media_type: "image/png", state: "linked" as const,
    unlink_available: true, restore_available: false, purge_at: null,
  };

  for (const size of ["regular", "narrow"] as const) test(`Ver opens the backing file, then the strip returns to the receipt in ${size}`, async () => {
    const original = { ...photoSource, channel: "web" as const, filename: "comprobante.jpg" };
    const dossier = await fiscalDossier({
      supporting_files: [support], original_connection_id: original.connection_id, sources: [original],
      origin: { ...photoOrigin, channel: original.channel, filename: original.filename, sent_by: null },
    });
    const previousFetch = globalThis.fetch;
    const previousMock = process.env.NEXT_PUBLIC_MOCK_AUTH;
    process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
    const requested: string[] = [];
    const fetchFile = (async url => {
      requested.push(String(url));
      return new Response("backing file", { headers: { "Content-Type": support.media_type } });
    }) as typeof fetch;
    const page = await mount({ dossier, receipt: receiptOf(dossier), size, detailsCard: "support", fetchFile });
    try {
      assert.equal(page.tab("Detalles")?.getAttribute("aria-selected"), "true");
      if (size === "regular") await page.click(page.button("Comprobante"));
      const view = page.all<HTMLButtonElement>('[data-tab-panel="detalles"] button').find(button => button.getAttribute("aria-label")?.startsWith("Ver"));
      await page.click(view);
      if (size === "narrow") assert.equal(page.tab("Documento")?.getAttribute("aria-selected"), "true");
      else assert.equal(page.tab("Detalles")?.getAttribute("aria-selected"), "true");
      const download = () => page.all<HTMLAnchorElement>('[data-testid="dossier-document-foot"] a[download]')[0];
      const waitForDownload = async (name: string) => {
        const deadline = Date.now() + 1000;
        while (download()?.download !== name && Date.now() < deadline) {
          await page.act(async () => { await new Promise(resolve => setTimeout(resolve, 10)); });
        }
        assert.equal(download()?.download, name);
      };
      await waitForDownload(support.filename);
      assert.ok(requested.some(url => url.endsWith(`/receipts/${support.receipt_id}/source`)));
      await page.click(page.button("Comprobante"));
      await waitForDownload("comprobante.jpg");
    } finally {
      await page.close();
      globalThis.fetch = previousFetch;
      if (previousMock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
      else process.env.NEXT_PUBLIC_MOCK_AUTH = previousMock;
    }
  });

  for (const refuseUndo of [false, true]) test(`unlink blocks concurrent approval and Undo uses the new version (restore refused: ${refuseUndo})`, async () => {
    const dossier = await fiscalDossier({ draft_id: "00000000-0000-4000-8000-000000000020", version: 7, supporting_files: [support] });
    const page = await mount({ dossier, size: "regular" });
    await page.click(page.tab("Detalles"));
    const previousFetch = globalThis.fetch;
    const mockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
    process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
    const writes: [string, string | null][] = [];
    let finishUnlink!: () => void;
    const held = new Promise<void>(resolve => { finishUnlink = resolve; });
    globalThis.fetch = (async (input, init) => {
      const restore = String(input).endsWith("/restore");
      const purge = "2099-10-10T12:00:00Z";
      writes.push([String(init?.method), new Headers(init?.headers).get("X-Draft-Version")]);
      if (!restore) await held;
      if (restore && refuseUndo) return Response.json({ detail: { code: "supporting_file_restore_expired" } }, { status: 422 });
      const version = restore ? 9 : 8;
      const file = restore ? support : { ...support, state: "unlinked", unlink_available: false, restore_available: true, purge_at: purge };
      return Response.json({ result: { draft_id: dossier.draft_id, version, outcome: restore ? "restored" : "unlinked", source_id: support.source_id, purge_at: restore ? null : purge },
        dossier: { ...dossier, current_note: null, note_edit_available: true, supporting_append_available: true, annotation_unavailable_reason: null, version, supporting_files: [file] } });
    }) as typeof fetch;
    try {
      const remove = page.all<HTMLButtonElement>('[data-tab-panel="detalles"] button').find(button => button.getAttribute("aria-label")?.startsWith("Quitar"));
      await page.click(remove);
      assert.equal(page.all<HTMLButtonElement>("[data-review-primary]")[0]?.disabled, true, "approval waits for the file command");
      await page.act(async () => { finishUnlink(); await held; });
      assert.ok(page.text().includes("Archivo quitado."));
      await page.click(page.button("Deshacer"));
      assert.deepEqual(writes, [["DELETE", "7"], ["POST", "8"]]);
      if (refuseUndo) {
        assert.ok(page.text().includes("No pudimos restaurar el archivo."));
        assert.equal(page.tab("Detalles")?.getAttribute("aria-selected"), "true");
      } else assert.ok(page.panelOf("detalles")?.textContent?.includes(support.filename));
    } finally {
      finishUnlink();
      globalThis.fetch = previousFetch;
      if (mockAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
      else process.env.NEXT_PUBLIC_MOCK_AUTH = mockAuth;
      await page.close();
    }
  });

  for (const reduced of [false, true]) test(`the server settles the read and its rows land once, reduced motion ${reduced}`, async () => {
    const dossier = await fiscalDossier({ ...attention(["missing_rnc"]) });
    const completed = receiptOf(dossier);
    let current = receiptOf(dossier, { draft_id: null, status: "queued", read_pending: true, bandeja: { por_revisar: false, con_problema: false, leyendo: true } });
    const page = await mount({ dossier, receipt: current, readReceipt: () => current, size: "regular" });
    const effects: { row: string; delay: number; colors: string[] }[] = [];
    const animate = Element.prototype.animate;
    Element.prototype.animate = function (this: Element, frames: Keyframe[], options: KeyframeAnimationOptions) {
      const row = this.getAttribute("data-fact");
      if (row) effects.push({ row, delay: Number(options.delay), colors: frames.map(frame => String(frame.backgroundColor ?? "")) });
      return { cancel() {} } as Animation;
    } as typeof animate;
    const device = (window as unknown as HappyWindow).happyDOM.settings.device;
    device.prefersReducedMotion = reduced ? "reduce" : "no-preference";
    try {
      assert.equal(page.all('[data-testid="receipt-current-facts"]').length, 0);
      current = completed;
      await page.act(async () => { window.dispatchEvent(new Event("focus")); });
      assert.ok(page.all('[data-fact="rnc"]').length, "the server supplied the draft");
      if (reduced) assert.deepEqual(effects, [], "all fields are visible immediately");
      else {
        const rows = [...new Set(effects.map(effect => effect.row))];
        assert.equal(rows[0], "rnc");
        assert.equal(rows[1], "counterparty");
        assert.deepEqual(rows.map(row => effects.find(effect => effect.row === row)?.delay), rows.map((_, i) => i * 80));
        assert.ok(effects.some(effect => effect.row === "rnc" && effect.colors.includes("var(--d-warn-bg)")), "the problem row gets the amber wash");
        assert.ok(effects.some(effect => effect.row === "counterparty" && effect.colors.includes("var(--d-flash)")), "the clear row gets the green wash");
        const count = effects.length;
        await page.click(page.tab("Detalles"));
        await page.click(page.tab("General"));
        assert.equal(effects.length, count, "revisiting General does not replay the read");
      }
    } finally { Element.prototype.animate = animate; await page.close(); }
  });

  test("the regular size keeps the document beside four tabs, and the narrow size makes it the Documento tab", async () => {
    const dossier = await fiscalDossier();
    const page = await mount({ dossier, receipt: receiptOf(dossier), size: "regular" });
    try {
      assert.deepEqual(page.tabs(), ["General", "Datos fiscales", "Detalles", "Historial"]);
      const source = page.all('[data-testid="receipt-review-source"]');
      assert.equal(source.length, 1);
      assert.equal(source[0].closest('[role="tabpanel"]'), null, "the document sits beside the tabs");
      assert.equal(page.all('[data-testid="business-record-review"]')[0].getAttribute("data-size"), "regular");
      const size = page.all<HTMLButtonElement>('[data-testid="dossier-size"]')[0];
      assert.equal(size.getAttribute("aria-label"), "Reducir");
      assert.equal(size.disabled, false);
      await page.click(size);
      assert.deepEqual(page.resizes, [true]);
      assert.deepEqual(page.tabs(), ["General", "Documento", "Datos fiscales", "Detalles", "Historial"]);
      assert.equal(page.all<HTMLButtonElement>('[data-testid="dossier-size"]')[0].getAttribute("aria-label"), "Ampliar");
      await page.click(page.tab("Documento"));
      assert.ok(page.panelOf("documento")?.querySelector('[data-testid="receipt-review-source"]'), "the document is its own tab");
      assert.equal(page.panelOf("documento")?.hidden, false);
      assert.equal(page.panelOf("general")?.hidden, true);
    } finally { await page.close(); }
  });

  test("a full page, where a phone shows a record, is always narrow and has no size button", async () => {
    const dossier = await fiscalDossier();
    const page = await mount({ dossier, receipt: receiptOf(dossier) });
    try {
      assert.deepEqual(page.tabs(), ["General", "Documento", "Datos fiscales", "Detalles", "Historial"]);
      assert.equal(page.all('[data-testid="dossier-size"]').length, 0);
    } finally { await page.close(); }
  });

  test("General holds the grouped cards, and every row is the same grid", async () => {
    const dossier = await fiscalDossier({ declaration_editable: true });
    const page = await mount({ dossier, size: "regular" });
    try {
      const general = page.panelOf("general");
      assert.ok(general);
      assert.deepEqual([...general.querySelectorAll("section > div > h3")].map((title) => title.textContent), ["Comprobante", "Reporte 606", "Montos"]);
      assert.deepEqual([...general.querySelectorAll('[data-testid="receipt-facts-comprobante"] [data-fact]')].slice(0, 4).map((row) => row.getAttribute("data-fact")), ["rnc", "counterparty", "fiscal_number", "occurred_on"]);
      assert.deepEqual([...general.querySelectorAll('[data-testid="receipt-facts-montos"] li[data-fact]')].map((row) => row.getAttribute("data-fact")), ["net_amount", "itbis", "amount"]);
      assert.deepEqual([...general.querySelectorAll('[data-testid="receipt-facts-montos"] li[data-fact] > span:first-child')].map((label) => label.textContent), ["Subtotal", "ITBIS", "Total"]);
      for (const row of general.querySelectorAll("li[data-fact]")) assert.ok(row.children.length >= 3, "label, status slot and value");
      assert.match(general.querySelector('[data-testid="montos-currency"]')?.textContent ?? "", /^DOP/);
      assert.ok(!page.text().includes("Lo que dice el recibo"));
    } finally { await page.close(); }
  });

  test("Detalles distinguishes a typed web note from a file upload", async () => {
    const dossier = await fiscalDossier({ original_connection_id: null, origin: { ...photoOrigin, channel: "note", filename: null, size_bytes: null } });
    const page = await mount({ dossier, size: "regular" });
    try {
      await page.click(page.tab("Detalles"));
      assert.equal(page.panelOf("detalles")?.querySelector('[data-fact="channel"] > span:nth-child(3)')?.textContent, "Escrito aquí");
    } finally { await page.close(); }
  });

  for (const [sentBy, shown] of [
    [{ id: "member:someone", kind: "member", person: { display_name: "Marisol Peña", shown_as: "name" } }, "Marisol Peña"],
    [{ id: "whatsapp:link", kind: "whatsapp", phone_last4: "1234" }, "···1234"],
  ] as const) test(`Detalles shows WhatsApp under Canal and ${shown} under Enviado por`, async () => {
    const dossier = await fiscalDossier({ origin: { ...photoOrigin, sent_by: sentBy } });
    const page = await mount({ dossier, receipt: receiptOf(dossier), size: "regular" });
    try {
      await page.click(page.tab("Detalles"));
      const details = page.panelOf("detalles");
      assert.equal(details?.querySelector('[data-fact="channel"] > span:nth-child(3)')?.textContent, "WhatsApp");
      assert.equal(details?.querySelector('[data-fact="sent_by"] > span:nth-child(3)')?.textContent, shown);
    } finally { await page.close(); }
  });

  test("Datos fiscales, Detalles and Historial each hold their own content", async () => {
    const dossier = await fiscalDossier({ origin: photoOrigin });
    const page = await mount({ dossier, receipt: receiptOf(dossier), size: "regular" });
    try {
      await page.click(page.tab("Datos fiscales"));
      assert.ok(page.panelOf("fiscal")?.querySelector('[data-testid="fiscal-declaration"]'));
      assert.equal(page.panelOf("fiscal")?.hidden, false);
      await page.click(page.tab("Detalles"));
      const details = page.panelOf("detalles");
      assert.deepEqual([...(details?.querySelectorAll("h3") ?? [])].map((title) => title.textContent), ["Origen", "Nota", "Archivos de respaldo", "Archivo"]);
      assert.deepEqual([...(details?.querySelectorAll("li[data-fact] > span:first-child") ?? [])].map((label) => label.textContent), ["Canal", "Enviado por", "Llegada", "Nombre", "Tamaño"]);
      assert.equal(details?.querySelector('[data-fact="channel"] > span:nth-child(3)')?.textContent, "WhatsApp");
      assert.equal(details?.querySelector('[data-fact="filename"] > span:nth-child(3)')?.textContent, "foto-0412.jpg");
      assert.match(details?.querySelector('[data-fact="size"] > span:nth-child(3)')?.textContent ?? "", /1[.,]2\s?MB/);
      await page.click(page.tab("Historial"));
      assert.ok(page.panelOf("historial")?.querySelector('[data-testid="receipt-history"]'));
      assert.equal(page.panelOf("historial")?.hidden, false);
    } finally { await page.close(); }
  });
});

describe("the dossier's status is the server's", () => {
  const labels: [BandejaLabel, string][] = [["ready", "Listo para aceptar"], ["needs_attention", "Necesita atención"], ["reading", "Leyendo…"], ["cant_read", "No se pudo leer"]];
  for (const [label, words] of labels) {
    test(`the pill says the Bandeja label ${label}`, async () => {
      const page = await mount({ dossier: await fiscalDossier({ bandeja_group: { group: "attention", reason: null, label } }) });
      try {
        const pill = page.all('[data-testid="status-pill"]');
        assert.equal(pill.length, 1);
        assert.equal(pill[0].getAttribute("data-label"), label);
        assert.equal(pill[0].textContent, words);
      } finally { await page.close(); }
    });
  }

  test("a deleted record has no label, so the line says only that it is deleted", async () => {
    const page = await mount({ dossier: await fiscalDossier({ bandeja_group: { group: "eliminados", reason: null, label: null }, deleted: { deleted_at: "2026-11-20T10:00:00Z" } as BusinessDossier["deleted"] }) });
    try {
      assert.equal(page.all('[data-testid="status-pill"]').length, 0);
      assert.equal(page.all('[data-testid="dossier-deleted"]')[0]?.textContent, "Eliminado");
    } finally { await page.close(); }
  });

  test("one reason sits beside the pill and jumps to its row with a flash", async () => {
    const page = await mount({ dossier: await fiscalDossier(attention(["invalid_ncf"])), size: "regular" });
    try {
      const reason = page.all<HTMLButtonElement>('[data-testid="dossier-reason"]')[0];
      assert.equal(reason.textContent, "Revisa el NCF");
      assert.equal(page.all('[data-testid="dossier-problems"]').length, 0);
      assert.equal(page.tab("General")?.querySelector('[aria-label="1 por resolver"]')?.textContent, "1");
      const row = () => page.panelOf("general")?.querySelector('[data-fact="fiscal_number"]');
      assert.equal(row()?.getAttribute("data-attention"), "true");
      assert.equal(row()?.querySelector('[data-testid="row-status-fiscal_number"]')?.getAttribute("aria-label"), "El NCF no tiene el formato de la serie B o E.");
      assert.equal(row()?.getAttribute("data-flash"), null);
      await page.click(page.tab("Historial"));
      await page.click(reason);
      assert.equal(page.panelOf("general")?.hidden, false, "the jump switches to the problem's tab");
      assert.equal(row()?.getAttribute("data-flash"), "a");
      await page.click(reason);
      assert.equal(row()?.getAttribute("data-flash"), "b", "a second jump washes the row again");
    } finally { await page.close(); }
  });

  test("several reasons open the list of problems, item for item in the server's order", async () => {
    const gaps: ListoGap[] = ["missing_rnc", "invalid_ncf", "missing_itbis"];
    const page = await mount({ dossier: await fiscalDossier(attention(gaps)), size: "regular" });
    try {
      assert.equal(page.all('[data-testid="dossier-reason"]').length, 0);
      const open = page.all<HTMLButtonElement>('[data-testid="dossier-problems"]')[0];
      assert.equal(open.textContent, "3 por resolver");
      await page.click(open);
      const items = page.all<HTMLButtonElement>('[data-testid="dossier-problem-list"] [role="option"]');
      assert.equal(page.button(copy.confirm.accept_anyway), undefined);
      assert.deepEqual(items.map((item) => item.getAttribute("data-reason")), gaps);
      assert.deepEqual(items.map((item) => item.textContent), ["Falta el RNCComprobante · RNC", "Revisa el NCFComprobante · NCF", "Falta el ITBISMontos · ITBIS"]);
      await page.click(items[2]);
      assert.equal(page.all('[data-testid="dossier-problem-list"]').length, 0);
      assert.ok(page.panelOf("general")?.querySelector('[data-fact="itbis"]')?.getAttribute("data-flash"));
    } finally { await page.close(); }
  });

  test("every reason of the rule shows as itself: no reason falls back to a generic sentence", async () => {
    for (const reason of LISTO_GAPS) {
      const page = await mount({ dossier: await fiscalDossier(attention([reason])) });
      try {
        const shown = page.all('[data-testid="dossier-reason"]');
        assert.equal(shown.length, 1, reason);
        assert.ok(shown[0].textContent?.trim(), reason);
        assert.ok(!shown[0].textContent?.includes("business."), `${reason} has words`);
        assert.doesNotMatch(page.text(), /necesita más revisión/i, `${reason} shows no generic sentence`);
        assert.equal(page.all('[data-testid="approve-reason"]').length, 0, `${reason} leaves the footer quiet`);
      } finally { await page.close(); }
    }
  });

  test("blockers alone are no reason: only listo_gaps are", async () => {
    const page = await mount({ dossier: await fiscalDossier({ blockers: [{ code: "unknown_funding", field: "funding" }], approval_available: false }) });
    try {
      assert.equal(page.all('[data-testid="dossier-reason"], [data-testid="dossier-problems"]').length, 0);
      assert.equal(page.all('[data-testid="approve-reason"]').length, 0);
    } finally { await page.close(); }
  });
});

describe("accepting a record that is not Listos", () => {
  test("a source receipt is displayed even when there are no separate supporting files", async () => {
    const dossier = await fiscalDossier({ supporting_files: [], original_connection_id: photoSource.connection_id, origin: photoOrigin, sources: [photoSource] });
    const page = await mount({ dossier, receipt: receiptOf(dossier) });
    try {
      await page.click(page.tab("Documento"));
      assert.match(page.text(), /foto-0412.jpg/);
      await page.click(page.tab("Detalles"));
      assert.equal(page.all('[data-testid="dossier-supporting"] ul').length, 0);
      assert.match(page.all('[data-testid="dossier-supporting"]')[0]?.textContent ?? "", /Sin archivos de respaldo\./);
    } finally { await page.close(); }
  });

  for (const [extras, label] of [[false, "Subtotal + ITBIS"], [true, "Total calculado"]] as const) {
    test(`the amounts row renders the server's ${label} and signed difference in the receipt currency`, async () => {
      const dossier = await fiscalDossier({ ...attention(["review_flag"]), review_flags: [
        { code: "amounts_mismatch", field: "amount", confirm: false, difference: "-3.00", computed_sum: "128.00", includes_extra_charges: extras },
      ] });
      dossier.facts.currency = { state: "known", value: "USD", origin: "member_set", verified: true, source_ids: [] };
      dossier.facts.amount = { state: "known", value: "125", origin: "member_set", verified: true, source_ids: [] };
      const page = await mount({ dossier });
      try {
        document.documentElement.classList.add("dark");
        await page.click(page.all<HTMLButtonElement>("[data-review-primary]")[0]);
        const list = page.all('[data-testid="dossier-problem-list"]')[0];
        assert.equal(list.querySelector("h2")?.textContent, "Corrige 1 dato antes de aceptar");
        assert.equal(list.querySelectorAll('[role="option"]').length, 1);
        assert.ok(list.textContent?.includes(`Total US$ 125.00 · ${label} US$ 128.00 · Diferencia -US$ 3.00`));
        assert.equal(page.all('[data-testid="dossier-reason"]')[0]?.textContent, "Los montos no cuadran");
        assert.ok(list.closest(".dark"));
        assert.equal(document.activeElement, list.querySelector('[role="option"]'));
        assert.equal(page.button(copy.confirm.accept_anyway), undefined);
        assert.deepEqual(page.sent, []);
      } finally { await page.close(); }
    });
  }

  test("the negative difference stays together when the comparison wraps", async () => {
    const dossier = await fiscalDossier({
      ...attention(["review_flag"]),
      review_flags: [{ code: "amounts_mismatch", field: "amount", confirm: false, difference: "-3.00", computed_sum: "128.00", includes_extra_charges: true }],
    });
    const page = await mount({ dossier, size: "narrow" });
    try {
      await page.click(page.all<HTMLButtonElement>("[data-review-primary]")[0]);
      const difference = page.all('[data-testid="dossier-problem-list"] [role="option"] .whitespace-nowrap');
      assert.deepEqual(difference.map(part => part.textContent), ["Diferencia -RD$ 3.00"]);
    } finally { await page.close(); }
  });

  test("two warnings under one confirmable server gap each have their own field jump", async () => {
    const page = await mount({ dossier: await fiscalDossier({ ...attention(["review_flag"], ["review_flag"]), review_flags: [
      { code: "itbis_high", field: "itbis", confirm: false },
      { code: "amounts_mismatch", field: "amount", confirm: false, difference: "-3.00", computed_sum: "128.00", includes_extra_charges: true },
    ] }), size: "regular" });
    try {
      await page.click(page.all<HTMLButtonElement>("[data-review-primary]")[0]);
      const list = page.all('[data-testid="dossier-problem-list"]')[0];
      assert.equal(list.querySelector("h2")?.textContent, "2 por resolver");
      const items = list.querySelectorAll<HTMLButtonElement>('[role="option"]');
      assert.equal(items.length, 2);
      assert.match(items[0].textContent ?? "", /Montos · ITBIS/);
      assert.match(items[1].textContent ?? "", /Montos · Total/);
      assert.ok(page.button(copy.confirm.accept_anyway));
      assert.doesNotMatch(list.textContent ?? "", /606/);
      await page.click(items[1]);
      assert.equal(page.all('[data-testid="dossier-problem-list"]').length, 0);
      assert.ok(page.panelOf("general")?.querySelector('[data-fact="amount"]')?.getAttribute("data-flash"));
      assert.deepEqual(page.sent, []);
    } finally { await page.close(); }
  });

  for (const gap of ["missing_date", "missing_amount", "missing_currency"] as const) {
    test(`Aceptar explains ${gap} even when the server withholds the approval action`, async () => {
      const page = await mount({ dossier: await fiscalDossier({ ...attention([gap]), approval_action: null, approval_available: false }) });
      try {
        assert.ok(page.all('[data-testid="dossier-reason"]')[0]?.textContent);
        await page.click(page.button("Aceptar"));
        const list = page.all('[data-testid="dossier-problem-list"]')[0];
        assert.equal(list.querySelector("h2")?.textContent, "Corrige 1 dato antes de aceptar");
        assert.equal(list.querySelector('[role="option"]')?.getAttribute("data-reason"), gap);
        assert.equal(page.button(copy.confirm.accept_anyway), undefined);
        assert.deepEqual(page.sent, []);
      } finally { await page.close(); }
    });
  }

  test("accepting anyway sends the approve request the person confirmed", async () => {
    const page = await mount({ dossier: await fiscalDossier(attention(["invalid_ncf"], ["invalid_ncf"])) });
    try {
      await page.click(page.all<HTMLButtonElement>("[data-review-primary]")[0]);
      assert.equal(page.all('[data-testid="dossier-problem-list"] h2')[0]?.textContent, "1 por resolver");
      await page.click(page.button(copy.confirm.accept_anyway));
      assert.deepEqual(page.sent, [{ acceptGaps: ["invalid_ncf"] }]);
    } finally { await page.close(); }
  });

  test("a Listos record is accepted with no confirm", async () => {
    const page = await mount({ dossier: await fiscalDossier() });
    try {
      await page.click(page.all<HTMLButtonElement>("[data-review-primary]")[0]);
      assert.equal(page.all('[data-testid="dossier-problem-list"]').length, 0);
      assert.deepEqual(page.sent, [{ acceptGaps: undefined }]);
    } finally { await page.close(); }
  });
});

describe("what an action answered shows on every tab", () => {
  const OTHER_TABS = ["Documento", "Datos fiscales", "Detalles", "Historial"];
  /** The notice as a person on the open tab sees it: on screen, and in no tab's panel. */
  const shown = (node: Element | null | undefined, tab: string) => {
    assert.ok(node, `${tab}: the notice is on the page`);
    assert.equal(node.closest("[hidden]"), null, `${tab}: nothing hides it`);
    assert.equal(node.closest('[role="tabpanel"]'), null, `${tab}: it belongs to no tab`);
  };
  const notices = (page: Awaited<ReturnType<typeof mount>>) => page.all<HTMLElement>('[data-testid="dossier-notices"]')[0];

  for (const tab of OTHER_TABS) {
    test(`from ${tab}, accepting a comprobante already recorded says so and offers the recorded one`, async () => {
      const page = await mount({ dossier: await fiscalDossier(), size: "narrow", refuse: { approveDraft: { code: "duplicate_comprobante", status: 409, details: { record_id: "recorded-1" } } } });
      try {
        await page.click(page.tab(tab));
        await page.click(page.all<HTMLButtonElement>("[data-review-primary]")[0]);
        const notice = page.all('[data-testid="dossier-duplicate"]')[0];
        shown(notice, tab);
        assert.ok(notice.textContent?.includes(copy.duplicate_recorded));
      } finally { await page.close(); }
    });

    test(`from ${tab}, an accept whose answer never came says so and keeps its way out`, async () => {
      const page = await mount({ dossier: await fiscalDossier(), size: "narrow", refuse: { approveDraft: new TypeError("Failed to fetch") } });
      try {
        await page.click(page.tab(tab));
        await page.click(page.all<HTMLButtonElement>("[data-review-primary]")[0]);
        shown(notices(page), tab);
        assert.ok(notices(page).querySelector('[role="alert"]')?.textContent?.includes(copy.outcome_unknown));
        shown(page.button(copy.refresh), tab);
      } finally { await page.close(); }
    });

    test(`from ${tab}, a refused accept says why`, async () => {
      const page = await mount({ dossier: await fiscalDossier(), size: "narrow", refuse: { approveDraft: { code: "not_a_known_code", status: 422 } } });
      try {
        await page.click(page.tab(tab));
        await page.click(page.all<HTMLButtonElement>("[data-review-primary]")[0]);
        shown(notices(page), tab);
        assert.equal(notices(page).querySelector('[role="alert"] p')?.textContent, copy.refused);
      } finally { await page.close(); }
    });


  }

  test("with nothing to say the frame holds no notice region", async () => {
    const page = await mount({ dossier: await fiscalDossier(), size: "narrow" });
    try {
      assert.equal(page.all('[data-testid="dossier-notices"]').length, 0);
    } finally { await page.close(); }
  });
});

describe("the RNC row says what the DGII register says", () => {
  const statuses: [RncRegistryStatus, string, string][] = [
    ["verificado", "ok", "Verificado"],
    ["suspendido", "warn", "Suspendido en la DGII"],
    ["cese_temporal", "warn", "Cese temporal en la DGII"],
    ["dado_de_baja", "bad", "Dado de baja en la DGII"],
    ["not_found", "warn", "No aparece en la DGII"],
  ];
  for (const [status, tone, words] of statuses) {
    test(`${status} shows in the status slot`, async () => {
      const page = await mount({ dossier: await fiscalDossier({ rnc_registry_status: status }) });
      try {
        const slot = page.panelOf("general")?.querySelector('[data-testid="row-status-rnc"]');
        assert.equal(slot?.getAttribute("aria-label"), words);
        assert.equal(slot?.getAttribute("data-tone"), tone);
      } finally { await page.close(); }
    });
  }

  test("with no answer from the register the slot stays empty", async () => {
    const page = await mount({ dossier: await fiscalDossier({ rnc_registry_status: null }) });
    try {
      assert.equal(page.panelOf("general")?.querySelector('[data-testid="row-status-rnc"]'), null);
    } finally { await page.close(); }
  });
});

describe("one dossier from both lists", () => {
  test("the same accepted record opened from Bandeja and from Registros has the same header and tabs: its name and no pill", async () => {
    const accepted = await fiscalDossier({ review_state: "accepted", bandeja_group: { group: null, reason: null, label: "accepted" }, approval_available: false, approval_action: null, approval_result: { status: "recorded", activity_id: "a1", reviewed_version: 2, approved_revision: 2, approved_at: "2026-11-20T15:02:00Z", actor: { actor_kind: "owner", display_name: "Rosa Díaz" } as never } });
    const seen: { title: string | null; pills: number; status: number; tabs: string[]; accept: number }[] = [];
    const receipt = receiptOf(accepted, { status: "confirmed", bandeja_group: { group: null, reason: null, label: "accepted", draft_id: accepted.draft_id, version: accepted.version } });
    for (const entry of [{ receipt, panel: { kind: "receipt", receiptId: receipt.id, list: "inbox" } as BusinessPanelState }, { panel: { kind: "draft", draftId: accepted.draft_id, list: "transactions" } as BusinessPanelState }]) {
      const page = await mount({ dossier: accepted, ...entry });
      try {
        seen.push({ title: page.all("#receipt-review-title")[0]?.textContent ?? null, pills: page.all('[data-testid="status-pill"]').length, status: page.all('[data-testid="dossier-status"]').length, tabs: page.tabs(), accept: page.all("[data-review-primary]").length });
        assert.ok(page.panelOf("historial")?.textContent?.includes(acceptedWord), "Historial dates the acceptance");
        for (const key of ["general", "fiscal", "detalles"]) assert.ok(!page.panelOf(key)?.textContent?.includes(acceptedWord), "the word for accepted lives in Historial alone");
        assert.equal(page.all('[data-testid="receipt-business"], [data-testid="receipt-total"]').length, 0, "the header holds no Business name and no total");
      } finally { await page.close(); }
    }
    assert.deepEqual(seen[0], seen[1]);
    assert.deepEqual(seen[0], { title: accepted.facts.counterparty.value, pills: 0, status: 0, tabs: ["General", "Documento", "Datos fiscales", "Detalles", "Historial"], accept: 0 });
  });
});

describe("the jump card under N de M", () => {
  test("it lists the run in the list's order with each row's label, and opens the one picked", async () => {
    const dossier = await fiscalDossier();
    const first = receiptOf(dossier);
    const second = receiptOf(dossier, { id: "receipt-2", title: "Refrigeración Juan Martínez", merchant: "Sin revisar", activity: { state: "ready", unread: true } as ReceiptDetail["activity"], bandeja_group: { group: "attention", reason: "missing_rnc", label: "needs_attention", draft_id: "d2", version: 1 } });
    const reviewList = { scope: "batch" as const, receiptIds: [first.id, second.id] };
    const page = await mount({ dossier, receipt: first, size: "regular", list: [second, first], panel: { kind: "receipt", receiptId: first.id, list: "inbox", reviewList } });
    try {
      const jump = page.all<HTMLButtonElement>('[data-testid="dossier-jump"]')[0];
      assert.equal(jump.getAttribute("aria-label"), "Ver la lista, 1 de 2");
      await page.click(jump);
      const rows = page.all<HTMLButtonElement>('[data-testid="dossier-jump-card"] [role="option"]');
      assert.match(rows[1].textContent ?? "", /Refrigeración Juan Martínez/);
      assert.deepEqual(rows.map((row) => row.getAttribute("data-receipt")), [first.id, second.id]);
      assert.deepEqual(rows.map((row) => row.getAttribute("aria-selected")), ["true", "false"]);
      assert.deepEqual(rows.map((row) => row.querySelector('[data-testid="jump-pill"]')?.textContent), ["Listo para aceptar", "Necesita atención"]);
      assert.deepEqual(rows.map((row) => row.querySelectorAll('[aria-label="Sin abrir"]').length), [0, 1]);
      await page.click(rows[1]);
      assert.equal(page.all('[data-testid="dossier-jump-card"]').length, 0);
      assert.deepEqual(page.opened.at(-1), { kind: "receipt", receiptId: "receipt-2", list: "inbox", reviewList });
    } finally { await page.close(); }
  });

  test("the last document of a run has one verb", async () => {
    const dossier = await fiscalDossier();
    const first = receiptOf(dossier);
    for (const [receiptIds, buttons] of [[[first.id, "receipt-2"], 2], [["receipt-0", first.id], 1]] as const) {
      const page = await mount({ dossier, receipt: first, panel: { kind: "receipt", receiptId: first.id, list: "inbox", reviewList: { scope: "inbox", receiptIds } } });
      try {
        const footer = page.all('[data-testid="receipt-review-footer"]')[0];
        assert.equal([...footer.querySelectorAll("button")].filter((item) => !item.closest('[data-testid="receipt-more"]')).length, buttons);
        assert.equal(footer.querySelectorAll("[data-review-primary]").length, 1);
      } finally { await page.close(); }
    }
  });
});

describe("Historial", () => {
  test("it groups events by day, dates the acceptance, and shows no suggestion event and no read duration", async () => {
    const dossier = await fiscalDossier({ declaration_editable: true, declaration_suggestions: { category: { value: "02", source: "last_choice" }, payment_method: { value: "01", source: "receipt" } } });
    const page = await mount({ dossier, size: "regular" });
    try {
      const history = page.panelOf("historial");
      assert.ok(history?.querySelectorAll('[data-testid="history-day"]').length);
      const words = history?.textContent ?? "";
      assert.ok(!/sugeri|Última elección|Leído del recibo|segundos/i.test(words), "no suggestion event and no read time");
      assert.ok(history?.querySelectorAll("time").length, "every event carries its full time");
    } finally { await page.close(); }
  });
});
