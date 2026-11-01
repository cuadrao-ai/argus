import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ReceiptDetail } from "@/lib/business-api";
import type { BusinessDataSource } from "@/components/business-app/business-data";

mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
  usePathname: () => "/biz",
}));

beforeAll(() => {
  // Below the desktop stop a record is the whole page; record-tray.dom.test.tsx covers the desktop tray.
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 800, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

async function mount(overrides: (fixture: BusinessDataSource) => Partial<BusinessDataSource> = () => ({})) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const english = (await import("@/public/locales/en/common.json")).default;
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const BusinessPanel = (await import("@/components/business-app/BusinessPanel")).default;
  const { setChosenGrant } = await import("@/lib/business-grant");
  setChosenGrant(null);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish }, en: { translation: english } }, interpolation: { escapeValue: false } });
  const fixture = createFixtureBusinessDataSource({ chatAvailable: true });
  // The email's own document stands in for a receipt saved with reading off.
  const source = {
    ...fixture,
    receipt: async (id: string, signal?: AbortSignal): Promise<ReceiptDetail> => {
      const found = await fixture.receipt(id, signal);
      return id === "rcpt-saved" ? { ...found, email_original: false, activity: { state: "saved_unread", unread: true, completion_cursor: null } } : found;
    },
    ...overrides(fixture),
  };
  let api: ReturnType<typeof useBusiness> | null = null;
  function Probe() {
    api = useBusiness();
    return <BusinessPanel />;
  }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessConsentTestProvider accepted>
          <BusinessWorkspaceProvider source={source as never}>
            <Probe />
          </BusinessWorkspaceProvider>
        </BusinessConsentTestProvider>
      </I18nextProvider>,
    );
  });
  const wait = async (done: () => boolean) => {
    for (let i = 0; i < 80; i += 1) {
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
      if (done()) return;
    }
    throw new Error(`timed out: ${host.textContent?.slice(0, 300)}`);
  };
  const open = async (panel: Parameters<ReturnType<typeof useBusiness>["openPanel"]>[0], ready: () => boolean) => {
    await act(async () => api!.openPanel(panel));
    await wait(ready);
  };
  const pages = () => host.querySelectorAll('[data-testid="business-record-review"]');
  const frame = () => {
    const [page] = pages();
    return {
      count: pages().length,
      source: page?.querySelector('[data-testid="receipt-review-source"]') ?? null,
      fields: page?.querySelector('[data-testid="receipt-review-fields"]') ?? null,
      title: page?.querySelector("#receipt-review-title")?.textContent ?? null,
    };
  };
  return { act, root, host, wait, open, frame, source, i18n, api: () => api! };
}

function button(host: Element, text: string) {
  const found = [...host.querySelectorAll<HTMLButtonElement>("button")].find((item) => item.textContent === text);
  assert.ok(found, `missing button ${text}`);
  return found;
}

const keys: [string, number][] = [];
type Dossier = Awaited<ReturnType<BusinessDataSource["dossier"]>>;

/** A review page over the sample's own server, with every write it sends kept in order. */
async function setup(id: keyof typeof import("@/components/business-app/dossier-fixtures").dossierFixtureIds = "fiscal", change: (dossier: Dossier) => void = () => undefined, overrides: (fixture: BusinessDataSource) => Partial<BusinessDataSource> = () => ({})) {
  const { dossierFixtureIds } = await import("@/components/business-app/dossier-fixtures");
  const writes: { kind: string; version: number; body: unknown; key: string }[] = [];
  let approvals = 0;
  const page = await mount((fixture) => ({
    dossier: async (draft) => { const dossier = await fixture.dossier(draft); change(dossier); return dossier; },
    reviewDraft: async (draft, version, facts, key) => { writes.push({ kind: "facts", version, body: facts, key }); const next = await fixture.reviewDraft(draft, version, facts, key); change(next); return next; },
    reviewFiscal: async (draft, version, review, key) => { writes.push({ kind: "fiscal", version, body: review, key }); const next = await fixture.reviewFiscal(draft, version, review, key); change(next); return next; },
    reviewPurchase: async (draft, version, purchase, key) => { writes.push({ kind: "purchase", version, body: purchase, key }); const next = await fixture.reviewPurchase(draft, version, purchase, key); change(next); return next; },
    approveDraft: async () => { approvals += 1; throw new Error("probe records the separate approval call"); },
    ...overrides(fixture),
  }));
  await page.open({ kind: "draft", draftId: dossierFixtureIds[id] }, () => Boolean(page.host.querySelector('[data-testid="receipt-current-facts"]') && page.host.querySelector('[data-testid="fiscal-declaration"] summary')));
  await page.wait(() => Boolean(page.host.querySelector('[data-fact="category"] option') || !page.host.querySelector('[data-testid="receipt-facts-choices"]')));
  const row = (name: string) => page.host.querySelector<HTMLElement>(`[data-fact="${name}"]`)!;
  const open = async (name: string) => page.act(async () => row(name).querySelector<HTMLButtonElement>("button")!.click());
  const leave = (selector: string) => page.act(async () => { page.host.querySelector<HTMLElement>(selector)!.blur(); await new Promise((resolve) => setTimeout(resolve, 10)); });
  const action = (name: string, label: "Guardar" | "Cancelar") => row(name).querySelector<HTMLButtonElement>(`button[aria-label^="${label} · "]`)!;
  const check = (name: string) => page.act(async () => action(name, "Guardar").click());
  const dismiss = (name: string) => page.act(async () => action(name, "Cancelar").click());
  const press = (selector: string, key: string) => page.act(async () => { page.host.querySelector(selector)!.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true })); });
  return { ...page, writes, approvals: () => approvals, row, openRow: open, leave, action, check, dismiss, press, close: () => page.act(async () => page.root.unmount()) };
}

async function fill(page: { host: Element; act: (run: () => Promise<void>) => Promise<void> }, selector: string, value: string, element: typeof HTMLInputElement | typeof HTMLSelectElement = HTMLInputElement) {
  const input = page.host.querySelector<HTMLInputElement>(selector);
  assert.ok(input, selector);
  await page.act(async () => {
    input.focus();
    Object.getOwnPropertyDescriptor(element.prototype, "value")!.set!.call(input, value);
    input.dispatchEvent(new Event(element === HTMLSelectElement ? "change" : "input", { bubbles: true }));
  });
}

describe("the receipt dossier on an open draft", () => {
  test("the six facts lead, then the two choices; what was removed is gone, in both languages", async () => {
    const page = await setup();
    try {
      assert.deepEqual([...page.host.querySelectorAll('[data-testid="receipt-current-facts"] [data-fact]')].map((row) => row.getAttribute("data-fact")), ["document_type", "counterparty", "occurred_on", "amount", "rnc", "fiscal_number", "itbis", "category", "payment_method"]);
      for (const gone of ["Confirmar", "Comprobante", "Actividad", "Parte del negocio", "Categoría", "Cómo se pagó", "Consultar registro actual", "por revisar"]) assert.ok(!page.host.querySelector('[data-testid="business-record-review"]')?.textContent?.includes(gone), gone);
      assert.ok(page.host.querySelector('[data-testid="receipt-more"] [data-testid="receipt-mark-personal"]'), "Personal stays in Más");
      assert.equal(page.host.querySelector('[data-testid="receipt-business"]')?.textContent, "Taller Lucía · negocio de muestra");
      assert.ok(button(page.host, "Aprobar"), "nothing blocks this record");
      assert.equal(page.host.querySelector('[data-testid="approve-reason"]'), null);
      assert.equal(page.host.querySelector('[data-testid="dossier-attention"]'), null, "no blocker, no top box");
      assert.equal(page.host.querySelector<HTMLDetailsElement>('[data-testid="fiscal-declaration"]')?.open, false, "the rest of the 606 stays closed");
      assert.ok(page.host.querySelector('[data-testid="fiscal-declaration"] summary')?.textContent?.includes("Más datos fiscales"));
      await page.act(async () => { await page.i18n.changeLanguage("en"); });
      assert.ok(button(page.host, "Approve expense"));
      assert.ok(page.row("category").textContent?.includes("Expense type"));
      for (const copy of ["Tipo de gasto", "Forma de pago", "Más datos fiscales"]) assert.ok(!page.host.textContent?.includes(copy), copy);
      await page.act(async () => { await page.i18n.changeLanguage("es-419"); });
      assert.equal(page.writes.length, 0);
    } finally { await page.close(); }
  });

  test("the top box and the footer say what blocks, and only that", async () => {
    const page = await setup("fiscalBlocked");
    try {
      const box = page.host.querySelector('[data-testid="dossier-attention"]');
      assert.deepEqual([...box!.querySelectorAll("li")].map((item) => item.textContent), ["Fecha de actividad"]);
      assert.ok(box?.textContent?.startsWith("Falta para aprobar"));
      assert.equal(page.host.querySelector('[data-testid="approve-reason"]'), null, "the box says it, so the footer does not");
      assert.equal(page.host.querySelector('[data-testid="business-record-review"]')?.textContent?.includes("Agrega la fecha para aprobar"), false, "nor does the row");
      assert.ok(page.row("occurred_on").querySelector('[data-testid="attention-marker"]'), "the row keeps its marker");
      assert.equal(button(page.host, "Aprobar").disabled, true);
      await page.openRow("occurred_on");
      await fill(page, '[placeholder="dd/mm/aaaa"]', "31/02/2026");
      await page.check("occurred_on");
      assert.equal(page.writes.length, 0, "a day that does not exist is not sent");
      assert.ok(page.row("occurred_on").querySelector('[role="alert"]')?.textContent?.includes("dd/mm/aaaa"), "and the row says why it stayed open");
      await fill(page, '[placeholder="dd/mm/aaaa"]', "16/10/2026");
      await page.check("occurred_on");
      await page.wait(() => page.writes.length === 1 && !page.host.querySelector('[data-testid="dossier-attention"]'));
      assert.deepEqual(page.writes[0].body, { occurred_on: { state: "known", value: "2026-10-16" } });
      assert.equal(button(page.host, "Aprobar").disabled, false);
      assert.equal(page.approvals(), 0, "saving never approves");
    } finally { await page.close(); }
  });

  test("ITBIS edits in place and saves on the check, carrying the other fiscal facts and the declaration unchanged", async () => {
    const page = await setup();
    try {
      await page.openRow("itbis");
      assert.equal(document.activeElement, page.host.querySelector('[data-testid="dossier-review-itbis"]'));
      await fill(page, '[data-testid="dossier-review-itbis"]', "500.00");
      await page.check("itbis");
      await page.wait(() => Boolean(page.row("itbis").querySelector('[data-testid="row-saved"]')));
      assert.deepEqual(page.writes.map(({ kind, version }) => [kind, version]), [["fiscal", 2]]);
      const { fiscal, declaration } = page.writes[0].body as { fiscal: unknown; declaration: Record<string, unknown> };
      assert.deepEqual(fiscal, { rnc: "131999888", ncf: "B0100000099", itbis: "500.00" });
      assert.equal(declaration.form, "606");
      assert.equal(declaration.category, null);
      assert.ok(page.row("itbis").textContent?.includes("RD$ 500.00"));
      assert.equal(page.host.querySelector('[data-testid="dossier-review-itbis"]'), null, "the row closes once it is saved");
      assert.equal(page.approvals(), 0);
    } finally { await page.close(); }
  });

  test("the total and its currency are one row and one write; saving a row unchanged writes nothing", async () => {
    const page = await setup();
    try {
      await page.openRow("counterparty");
      await page.check("counterparty");
      assert.equal(page.host.querySelector('[data-testid="edit-counterparty"]'), null);
      await page.openRow("amount");
      await fill(page, '[data-testid="dossier-review-amount"]', "3600");
      await fill(page, '[data-testid="edit-amount"] select', "USD", HTMLSelectElement);
      await page.check("amount");
      await page.wait(() => Boolean(page.row("amount").querySelector('[data-testid="row-saved"]')));
      assert.deepEqual(page.writes.map(({ body }) => body), [{ amount: { state: "known", value: "3600.00" }, currency: { state: "known", value: "USD" } }]);
      assert.ok(page.row("amount").textContent?.includes("US$ 3,600.00"));
    } finally { await page.close(); }
  });

  test("the two choices offer the server's labels, save on their own, and never hold approval", async () => {
    const page = await setup();
    try {
      const options = (name: string) => [...page.row(name).querySelectorAll("option")].map((option) => option.textContent);
      assert.equal(options("category").length, 12, "Elegir and José's 11");
      assert.equal(options("category")[2], "Gastos por trabajos, suministros y servicios");
      assert.equal(options("payment_method").length, 8, "Elegir and José's 7");
      assert.equal(options("payment_method")[3], "Tarjeta crédito/débito");
      assert.equal(page.row("category").querySelector("select")?.value, "", "a suggestion is not a choice");
      assert.equal(button(page.host, "Aprobar").disabled, false, "blank choices do not block");
      assert.ok(page.host.querySelector('[data-testid="expense-type-suggestion"]')?.textContent?.includes("Gastos por trabajos, suministros y servicios"));
      await page.act(async () => button(page.row("category"), "Usar").click());
      await page.wait(() => Boolean(page.row("category").querySelector('[data-testid="row-saved"]')));
      assert.deepEqual(page.writes.map(({ kind, body }) => [kind, body]), [["purchase", { category: "02" }]]);
      assert.equal(page.row("category").querySelector("select")?.value, "02");
      assert.equal(page.host.querySelector('[data-testid="expense-type-suggestion"]'), null);
      await fill(page, '[data-fact="payment_method"] select', "03", HTMLSelectElement);
      await page.wait(() => Boolean(page.row("payment_method").querySelector('[data-testid="row-saved"]')));
      assert.deepEqual(page.writes[1].body, { payment_method: "03" });
      assert.equal(page.writes[1].version, page.writes[0].version + 1, "each save stands on the last one");
    } finally { await page.close(); }
  });

  test("edits made in a row keep their order: a second save waits for the first and takes its version", async () => {
    const order: [string, number][] = [];
    const page = await setup("fiscal", undefined, (fixture) => ({
      reviewDraft: async (draft, version, facts, key) => { order.push(["facts", version]); await new Promise((resolve) => setTimeout(resolve, 40)); return fixture.reviewDraft(draft, version, facts, key); },
      reviewFiscal: async (draft, version, review, key) => { order.push(["fiscal", version]); return fixture.reviewFiscal(draft, version, review, key); },
    }));
    try {
      await page.openRow("counterparty");
      await fill(page, '[data-testid="edit-counterparty"] input', "Ferretería Norte");
      await page.openRow("fiscal_number");
      await fill(page, '[data-testid="edit-fiscal_number"] input', "e310000000777");
      await page.check("counterparty");
      assert.equal(page.action("counterparty", "Guardar").getAttribute("aria-busy"), "true", "the check shows the row working");
      await page.check("fiscal_number");
      await page.wait(() => order.length === 2 && !page.host.querySelector('[data-row-open]'));
      assert.deepEqual(order, [["facts", 2], ["fiscal", 3]]);
      assert.ok(page.row("fiscal_number").textContent?.includes("E310000000777"), "the server's clean value shows");
    } finally { await page.close(); }
  });

  test("a refused save says what failed with its reference and the way out, and keeps what was typed", async () => {
    const page = await setup("saveRefused");
    try {
      await page.openRow("itbis");
      await fill(page, '[data-testid="dossier-review-itbis"]', "1.00");
      await page.check("itbis");
      await page.wait(() => Boolean(page.host.querySelector('[data-testid="row-save-failed"]')));
      const failure = page.row("itbis").querySelector('[data-testid="row-save-failed"]');
      assert.equal(failure?.getAttribute("role"), "alert");
      assert.ok(failure?.textContent?.includes("No se guardó ITBIS. Revisa el valor."));
      assert.ok(failure?.textContent?.includes("hola@cuadrao.ai"), "a refusal gives the contact line");
      assert.ok(failure?.querySelector('[data-testid="error-reference"]')?.textContent?.includes("Ref. sample-v"));
      assert.equal(page.host.querySelector<HTMLInputElement>('[data-testid="dossier-review-itbis"]')?.value, "1.00");
      assert.equal(button(page.host, "Aprobar").disabled, true, "nothing is approved while the row shows a value the record does not hold");
      await page.dismiss("itbis");
      assert.equal(page.host.querySelector('[data-testid="row-save-failed"]'), null);
      assert.equal(button(page.host, "Aprobar").disabled, false);
      assert.ok(page.row("itbis").textContent?.includes("RD$ 526.27"));
      await fill(page, '[data-fact="category"] select', "05", HTMLSelectElement);
      await page.wait(() => Boolean(page.row("category").querySelector('[data-testid="row-save-failed"]')));
      assert.equal(button(page.host, "Aprobar").disabled, true);
      await page.act(async () => button(page.row("category"), "Cancelar").click());
      assert.equal(button(page.host, "Aprobar").disabled, false, "a refused choice has a way out, so it never holds approval");
    } finally { await page.close(); }
  });

  test("a save whose answer never came pauses approval and retries with its same key and version", async () => {
    let lost = true;
    const page = await setup("fiscal", undefined, (fixture) => ({
      reviewDraft: async (draft, version, facts, key) => {
        keys.push([key, version]);
        const next = await fixture.reviewDraft(draft, version, facts, key);
        if (lost) { lost = false; throw new TypeError("the answer was lost"); }
        return next;
      },
    }));
    try {
      await page.openRow("counterparty");
      await fill(page, '[data-testid="edit-counterparty"] input', "Ferretería Norte");
      await page.press('[data-testid="edit-counterparty"] input', "Enter");
      await page.wait(() => Boolean(page.host.querySelector('[data-testid="row-save-failed"]')));
      const failure = page.row("counterparty").querySelector('[data-testid="row-save-failed"]')!;
      assert.ok(failure.textContent?.includes("No pudimos confirmar si Comercio o persona se guardó."));
      assert.ok(failure.querySelector('[data-testid="error-reference"]'), "a lost answer still shows a reference");
      assert.equal(button(page.host, "Aprobar").disabled, true);
      assert.equal(page.action("counterparty", "Cancelar").disabled, true, "nothing may be dropped while its outcome is unknown");
      await page.press('[data-testid="edit-counterparty"] input', "Escape");
      assert.ok(page.host.querySelector('[data-testid="edit-counterparty"]'), "Escape drops nothing either");
      await page.act(async () => button(failure, "Reintentar").click());
      await page.wait(() => Boolean(page.row("counterparty").querySelector('[data-testid="row-saved"]')));
      assert.deepEqual(keys[1], keys[0], "the server answers one save once");
      assert.equal(button(page.host, "Aprobar").disabled, false);
      assert.ok(page.row("counterparty").textContent?.includes("Ferretería Norte"));
    } finally { await page.close(); }
  });

  test("a version conflict loads the current record, keeps the edit, and retries on the new version", async () => {
    const page = await setup("saveConcurrent", undefined, (fixture) => ({
      reviewDraft: async (draft, version, facts, key) => {
        try { return await fixture.reviewDraft(draft, version, facts, key); }
        catch (error) { if (error instanceof TypeError) throw Object.assign(new Error("stale"), { status: 409, code: "stale_version", requestId: "sample-stale" }); throw error; }
      },
    }));
    try {
      await page.openRow("amount");
      await fill(page, '[data-testid="dossier-review-amount"]', "950");
      await page.leave('[data-testid="dossier-review-amount"]');
      await page.check("amount");
      await page.wait(() => Boolean(page.host.querySelector('[data-testid="row-save-failed"]')));
      assert.ok(page.row("counterparty").textContent?.includes("Corrección de otra persona"), "the other person's change is on screen");
      assert.equal(page.host.querySelector<HTMLInputElement>('[data-testid="dossier-review-amount"]')?.value, "950.00");
      await page.act(async () => button(page.row("amount"), "Reintentar").click());
      await page.wait(() => Boolean(page.row("amount").querySelector('[data-testid="row-saved"]')));
      assert.ok(page.row("amount").textContent?.includes("RD$ 950.00"));
    } finally { await page.close(); }
  });

  test("a row saves only when asked: leaving the field writes nothing, and the check or Enter saves", async () => {
    const page = await setup();
    try {
      await page.openRow("counterparty");
      await fill(page, '[data-testid="edit-counterparty"] input', "Ferretería Norte");
      await page.leave('[data-testid="edit-counterparty"] input');
      assert.equal(page.writes.length, 0);
      assert.ok(page.host.querySelector('[data-testid="edit-counterparty"]'), "the row stays open");
      await page.press('[data-testid="edit-counterparty"] input', "Enter");
      await page.wait(() => Boolean(page.row("counterparty").querySelector('[data-testid="row-saved"]')));
      assert.equal(page.writes.length, 1);
      assert.equal(page.host.querySelector('[data-row-open]'), null);
      assert.ok(page.row("counterparty").textContent?.includes("Ferretería Norte"));
    } finally { await page.close(); }
  });

  test("the X and Escape cancel: the value comes back, nothing is sent, and focus returns to the row", async () => {
    const page = await setup();
    try {
      for (const leave of [() => page.dismiss("counterparty"), () => page.press('[data-testid="edit-counterparty"] input', "Escape")]) {
        await page.openRow("counterparty");
        assert.equal(document.activeElement, page.host.querySelector('[data-testid="edit-counterparty"] input'));
        await fill(page, '[data-testid="edit-counterparty"] input', "Otro nombre");
        await leave();
        await page.act(async () => { await new Promise((resolve) => requestAnimationFrame(resolve)); });
        assert.equal(page.host.querySelector('[data-row-open]'), null);
        assert.ok(page.row("counterparty").textContent?.includes("Ferretería La Esquina"));
        assert.equal(document.activeElement, page.row("counterparty").querySelector("button"));
      }
      assert.equal(page.writes.length, 0);
    } finally { await page.close(); }
  });

  test("an unsaved row holds approval and names itself beside Aprobar; an unchanged one holds nothing", async () => {
    const page = await setup();
    try {
      await page.openRow("itbis");
      assert.equal(button(page.host, "Aprobar").disabled, false, "nothing typed, nothing held");
      await fill(page, '[data-testid="dossier-review-itbis"]', "500.00");
      assert.equal(button(page.host, "Aprobar").disabled, true);
      assert.equal(page.host.querySelector('[data-testid="approve-reason"]')?.textContent, "Guarda o cancela ITBIS para aprobar.");
      await page.dismiss("itbis");
      assert.equal(button(page.host, "Aprobar").disabled, false);
      assert.equal(page.host.querySelector('[data-testid="approve-reason"]'), null);
    } finally { await page.close(); }
  });

  test("leaving with an unsaved row warns first, by any way out; keeping stays, discarding goes", async () => {
    const page = await setup();
    const dialog = () => document.querySelector('[role="alertdialog"]');
    try {
      await page.openRow("counterparty");
      await page.act(async () => page.api().openPanel({ kind: "inbox" }));
      assert.equal(dialog(), null, "an open row with nothing typed loses nothing");
      await page.wait(() => !page.host.querySelector('[data-testid="business-record-review"]'));
    } finally { await page.close(); }
    const held = await setup();
    try {
      await held.openRow("counterparty");
      await fill(held, '[data-testid="edit-counterparty"] input', "Otro nombre");
      const unload = new Event("beforeunload", { cancelable: true });
      window.dispatchEvent(unload);
      assert.equal(unload.defaultPrevented, true, "a reload or a closed tab warns too");
      await held.act(async () => held.api().openPanel({ kind: "inbox" }));
      assert.ok(dialog()?.textContent?.includes("¿Descartar los cambios?"));
      await held.act(async () => button(dialog()!, "Seguir editando").click());
      assert.equal(dialog(), null);
      assert.equal(held.host.querySelector<HTMLInputElement>('[data-testid="edit-counterparty"] input')?.value, "Otro nombre", "the typed value stays");
      await held.act(async () => held.api().chooseBusiness("another-grant"));
      assert.ok(dialog(), "switching Business warns too");
      await held.act(async () => button(dialog()!, "Seguir editando").click());
      await held.act(async () => held.api().openPanel({ kind: "inbox" }));
      await held.act(async () => button(dialog()!, "Descartar cambios").click());
      await held.wait(() => !held.host.querySelector('[data-testid="business-record-review"]'));
      assert.equal(held.writes.length, 0);
    } finally { await held.close(); }
  });

  test("Tipo is a fact row: the pencil opens its two options, the check saves through the type write, the X cancels", async () => {
    const typed: { version: number; documentType: string }[] = [];
    const page = await setup("fiscal", () => undefined, (fixture) => ({ setDocumentType: async (draft, version, documentType, key) => { typed.push({ version, documentType }); return fixture.setDocumentType(draft, version, documentType, key); } }));
    try {
      assert.equal(page.host.querySelector('[role="radiogroup"], [data-segment]'), null);
      assert.match(page.row("document_type").textContent ?? "", /Tipo\s*Compra/);
      await page.openRow("document_type");
      const select = () => page.row("document_type").querySelector("select")!;
      assert.deepEqual([...select().options].map((option) => option.textContent), ["Compra", "Venta"]);
      await fill(page, '[data-fact="document_type"] select', "venta", HTMLSelectElement);
      assert.equal(typed.length, 0, "picking saves nothing");
      await page.dismiss("document_type");
      assert.equal(page.row("document_type").querySelector("select"), null);
      assert.match(page.row("document_type").textContent ?? "", /Compra/);
      assert.equal(typed.length, 0, "the X sends nothing");

      await page.openRow("document_type");
      await fill(page, '[data-fact="document_type"] select', "venta", HTMLSelectElement);
      await page.check("document_type");
      await page.wait(() => /Venta/.test(page.row("document_type").textContent ?? ""));
      assert.deepEqual(typed.map(({ version, documentType }) => [version, documentType]), [[2, "venta"]]);
      assert.ok(page.row("document_type").querySelector('[data-testid="row-saved"]'));
      assert.equal(page.row("document_type").getAttribute("data-type"), "venta");
    } finally { await page.close(); }
  });

  test("an unchanged Tipo closes without a write, and a held choice stops approval by name", async () => {
    const typed: { version: number; documentType: string }[] = [];
    const page = await setup("fiscal", () => undefined, (fixture) => ({ setDocumentType: async (draft, version, documentType, key) => { typed.push({ version, documentType }); return fixture.setDocumentType(draft, version, documentType, key); } }));
    try {
      await page.openRow("document_type");
      await page.check("document_type");
      assert.equal(page.row("document_type").querySelector("select"), null);
      assert.equal(typed.length, 0);
      await page.openRow("document_type");
      await fill(page, '[data-fact="document_type"] select', "venta", HTMLSelectElement);
      assert.match(page.host.querySelector('[data-testid="approve-reason"]')?.textContent ?? "", /Tipo/);
    } finally { await page.close(); }
  });

  test("a refused Tipo says the record is fixed, with its reference, and keeps the shown type", async () => {
    const page = await setup("fiscal", () => undefined, () => ({ setDocumentType: async () => { throw Object.assign(new Error("locked"), { status: 422, code: "document_type_locked", requestId: "req-type-locked" }); } }));
    try {
      await page.openRow("document_type");
      await fill(page, '[data-fact="document_type"] select', "venta", HTMLSelectElement);
      await page.check("document_type");
      await page.wait(() => Boolean(page.row("document_type").querySelector('[data-testid="row-save-failed"]')));
      assert.match(page.row("document_type").textContent ?? "", /ya está aprobado/);
      assert.match(page.row("document_type").textContent ?? "", /Ref\./);
      assert.equal(page.row("document_type").getAttribute("data-type"), "recibo");
      await page.dismiss("document_type");
      assert.equal(page.row("document_type").querySelector('[data-testid="row-save-failed"]'), null);
    } finally { await page.close(); }
  });

  test("a row opened with nothing changed warns nobody; only an unsaved change holds the way out", async () => {
    const page = await setup();
    try {
      await page.openRow("itbis");
      const event = new Event("beforeunload", { cancelable: true });
      window.dispatchEvent(event);
      assert.equal(event.defaultPrevented, false);
      await fill(page, '[data-testid="dossier-review-itbis"]', "600.00");
      const held = new Event("beforeunload", { cancelable: true });
      window.dispatchEvent(held);
      assert.equal(held.defaultPrevented, true);
    } finally { await page.close(); }
  });

  test("a record with no fiscal number marks Sin recibo through the review's facts, and takes it back", async () => {
    const page = await setup("noNumber");
    try {
      const mark = () => page.host.querySelector<HTMLButtonElement>('[data-testid="mark-no-receipt"]')!;
      assert.match(page.row("fiscal_number").textContent ?? "", /Sin comprobante fiscal/);
      assert.equal(mark().textContent, "Marcar sin recibo");
      await page.act(async () => mark().click());
      await page.wait(() => /Sin recibo/.test(page.row("fiscal_number").textContent ?? ""));
      assert.deepEqual(page.writes.map(({ kind, version, body }) => [kind, version, body]), [["facts", 2, { receipt_state: { state: "known", value: "no_receipt" } }]]);
      assert.match(page.row("fiscal_number").textContent ?? "", /del revisor/);
      assert.ok(page.row("fiscal_number").querySelector('[data-testid="row-saved"]'));
      assert.equal(mark().textContent, "Deshacer");

      await page.act(async () => mark().click());
      await page.wait(() => /Marcar sin recibo/.test(page.row("fiscal_number").textContent ?? ""));
      assert.deepEqual(page.writes[1].body, { receipt_state: { state: "unknown", value: null } });
      assert.match(page.row("fiscal_number").textContent ?? "", /Sin comprobante fiscal/);
    } finally { await page.close(); }
  });

  test("Sin recibo never asks for an RNC: the row is blank and approval goes straight through", async () => {
    const page = await setup("noNumber");
    try {
      assert.ok(page.row("rnc").querySelector('[data-testid="rnc-status"]'));
      await page.act(async () => page.host.querySelector<HTMLButtonElement>('[data-testid="mark-no-receipt"]')!.click());
      await page.wait(() => !page.row("rnc").querySelector('[data-testid="rnc-status"]'));
      await page.act(async () => button(page.host, "Aprobar").click());
      assert.equal(document.querySelector('[role="alertdialog"]'), null);
      assert.equal(page.approvals(), 1);
    } finally { await page.close(); }
  });

  test("a record with a fiscal number offers no Sin recibo mark", async () => {
    const page = await setup();
    try {
      assert.equal(page.host.querySelector('[data-testid="mark-no-receipt"]'), null);
    } finally { await page.close(); }
  });

  test("a refused Sin recibo holds approval, shows its reference under the row, and cancels", async () => {
    const page = await setup("noNumber", () => undefined, () => ({ reviewDraft: async () => { throw Object.assign(new Error("refused"), { status: 422, code: "validation_error", requestId: "req-no-receipt" }); } }));
    try {
      await page.act(async () => page.host.querySelector<HTMLButtonElement>('[data-testid="mark-no-receipt"]')!.click());
      await page.wait(() => Boolean(page.row("fiscal_number").querySelector('[data-testid="row-save-failed"]')));
      assert.match(page.row("fiscal_number").textContent ?? "", /Ref\./);
      assert.equal(button(page.host, "Aprobar").disabled, true);
      await page.act(async () => button(page.row("fiscal_number"), "Cancelar").click());
      assert.equal(button(page.host, "Aprobar").disabled, false);
    } finally { await page.close(); }
  });

  test("Historial shows the owner choices by the server's labels", async () => {
    const page = await setup("fiscalDeclared");
    try {
      const fold = page.host.querySelector('[data-testid="receipt-history"]');
      await page.wait(() => Boolean(fold?.querySelector("details dd")));
      const shown = fold?.querySelector("details")?.textContent ?? "";
      assert.match(shown, /Gastos por trabajos, suministros y servicios/);
      assert.match(shown, /Tarjeta crédito\/débito/);
      const values = [...fold!.querySelectorAll("details dd")].map((item) => item.textContent);
      assert.equal(values.includes("02"), false);
      assert.equal(values.includes("03"), false);
    } finally { await page.close(); }
  });

  test("Historial owns what changed: the raw web actions are gone and the correction is there", async () => {
    const page = await setup();
    try {
      await page.openRow("counterparty");
      await fill(page, '[data-testid="edit-counterparty"] input', "Ferretería Norte");
      await page.check("counterparty");
      await page.wait(() => Boolean(page.row("counterparty").querySelector('[data-testid="row-saved"]')));
      const shown = page.host.querySelector('[data-testid="business-record-review"]')!;
      for (const gone of ["Revisiones en la web", "Acción enviada originalmente"]) assert.ok(!shown.textContent?.includes(gone), gone);
      assert.ok(page.host.querySelector('[data-testid="receipt-history"]')?.textContent?.includes("Ferretería Norte"));
    } finally { await page.close(); }
  });

  test("Tab walks the six facts in reading order, and a saved row hands Tab on from itself", async () => {
    const page = await setup();
    try {
      const stops = [...page.host.querySelectorAll<HTMLElement>('[data-testid="receipt-facts-activity"] button, [data-testid="receipt-facts-fiscal"] button')].filter((item) => item.closest("[data-fact]") && item.tabIndex === 0).map((item) => item.closest<HTMLElement>("[data-fact]")!.dataset.fact);
      assert.deepEqual(stops.filter((fact) => fact !== "document_type"), ["counterparty", "occurred_on", "amount", "rnc", "fiscal_number", "itbis"]);
      await page.openRow("counterparty");
      await fill(page, '[data-testid="edit-counterparty"] input', "Ferretería Norte");
      await page.press('[data-testid="edit-counterparty"] input', "Enter");
      await page.wait(() => document.activeElement === page.row("counterparty").querySelector("button"));
    } finally { await page.close(); }
  });

  test("the total line shows only when the server says the parts do not add up, with the server's figures", async () => {
    const quiet = await setup();
    try { assert.equal(quiet.host.querySelector('[data-testid="total-mismatch"]'), null); } finally { await quiet.close(); }
    const page = await setup("totalsOff");
    try {
      assert.equal(page.row("amount").querySelector('[data-testid="total-mismatch"]')?.textContent, "Subtotal + ITBIS = RD$ 3,449.00, no RD$ 3,450.00");
    } finally { await page.close(); }
  });

  test("Corregir on a flagged value opens that value's row", async () => {
    const page = await setup("fiscal", (dossier) => { dossier.review_flags = [{ code: "ncf_malformed", field: "ncf", confirm: true }]; });
    try {
      await page.act(async () => button(page.host, "Aprobar").click());
      const dialog = document.querySelector('[role="alertdialog"]');
      assert.ok(dialog);
      await page.act(async () => button(dialog, "Corregir").click());
      await page.wait(() => Boolean(page.host.querySelector('[data-testid="edit-fiscal_number"] input')));
    } finally { await page.close(); }
  });

  test("prepare-only access has the locked line and no approval; read-only has no edit control", async () => {
    for (const capabilities of [["read", "prepare"], ["read"]] as const) {
      const page = await setup("fiscal", (dossier) => { dossier.capabilities = [...capabilities]; dossier.declaration_editable = capabilities.length === 2; });
      try {
        assert.equal(page.host.textContent?.includes("Puedes revisar y preparar este recibo. El dueño lo aprueba."), capabilities.length === 2);
        // The footer keeps Más; it offers no approval.
        assert.ok(![...page.host.querySelectorAll('[data-testid="receipt-review-footer"] button')].some((item) => item.textContent?.startsWith("Aprobar")));
        if (capabilities.length === 1) {
          assert.equal(page.host.querySelector('[data-fact="amount"] button'), null);
          assert.equal(page.host.querySelector('[data-fact="itbis"] button'), null);
          assert.equal(page.host.querySelector('[data-fact="category"]'), null, "no declaration to read and none to write");
        }
        assert.equal(page.approvals(), 0);
      } finally { await page.close(); }
    }
  });
});
