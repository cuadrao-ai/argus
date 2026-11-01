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
  return { ...page, writes, approvals: () => approvals, row, openRow: open, leave, close: () => page.act(async () => page.root.unmount()) };
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
      assert.equal(page.host.querySelector('[data-testid="approve-reason"]')?.textContent, "Agrega la fecha para aprobar");
      assert.equal(button(page.host, "Aprobar").disabled, true);
      await fill(page, '[placeholder="dd/mm/aaaa"]', "31/02/2026");
      assert.equal(page.writes.length, 0, "a day that does not exist is not sent");
      await fill(page, '[placeholder="dd/mm/aaaa"]', "16/10/2026");
      await page.wait(() => page.writes.length === 1 && !page.host.querySelector('[data-testid="dossier-attention"]'));
      assert.deepEqual(page.writes[0].body, { occurred_on: { state: "known", value: "2026-10-16" } });
      assert.equal(button(page.host, "Aprobar").disabled, false);
      assert.equal(page.approvals(), 0, "saving never approves");
    } finally { await page.close(); }
  });

  test("ITBIS edits in place and saves on its own, carrying the other fiscal facts and the declaration unchanged", async () => {
    const page = await setup();
    try {
      await page.openRow("itbis");
      assert.equal(document.activeElement, page.host.querySelector('[data-testid="dossier-review-itbis"]'));
      await fill(page, '[data-testid="dossier-review-itbis"]', "500.00");
      await page.leave('[data-testid="dossier-review-itbis"]');
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

  test("the total and its currency are one row and one write; leaving a row unchanged writes nothing", async () => {
    const page = await setup();
    try {
      await page.openRow("counterparty");
      await page.leave('[data-testid="edit-counterparty"] input');
      assert.equal(page.host.querySelector('[data-testid="edit-counterparty"]'), null);
      await page.openRow("amount");
      await fill(page, '[data-testid="dossier-review-amount"]', "3600");
      await fill(page, '[data-testid="edit-amount"] select', "USD", HTMLSelectElement);
      await page.leave('[data-testid="edit-amount"] select');
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
      assert.ok(page.row("counterparty").querySelector('[data-testid="row-saving"]'), "focus left the first row, so it is saving");
      await fill(page, '[data-testid="edit-fiscal_number"] input', "e310000000777");
      await page.leave('[data-testid="edit-fiscal_number"] input');
      await page.wait(() => order.length === 2 && !page.host.querySelector('[data-testid="row-saving"]'));
      assert.deepEqual(order, [["facts", 2], ["fiscal", 3]]);
      assert.ok(page.row("fiscal_number").textContent?.includes("E310000000777"), "the server's clean value shows");
    } finally { await page.close(); }
  });

  test("a refused save says what failed with its reference and the way out, and keeps what was typed", async () => {
    const page = await setup("saveRefused");
    try {
      await page.openRow("itbis");
      await fill(page, '[data-testid="dossier-review-itbis"]', "1.00");
      await page.leave('[data-testid="dossier-review-itbis"]');
      await page.wait(() => Boolean(page.host.querySelector('[data-testid="row-save-failed"]')));
      const failure = page.row("itbis").querySelector('[data-testid="row-save-failed"]');
      assert.equal(failure?.getAttribute("role"), "alert");
      assert.ok(failure?.textContent?.includes("No se guardó ITBIS. Revisa el valor."));
      assert.ok(failure?.textContent?.includes("hola@cuadrao.ai"), "a refusal gives the contact line");
      assert.ok(failure?.querySelector('[data-testid="error-reference"]')?.textContent?.includes("Ref. sample-v"));
      assert.equal(page.host.querySelector<HTMLInputElement>('[data-testid="dossier-review-itbis"]')?.value, "1.00");
      assert.equal(button(page.host, "Aprobar").disabled, true, "nothing is approved while the row shows a value the record does not hold");
      await page.act(async () => button(failure!, "Cancelar").click());
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
      await page.leave('[data-testid="edit-counterparty"] input');
      await page.wait(() => Boolean(page.host.querySelector('[data-testid="row-save-failed"]')));
      const failure = page.row("counterparty").querySelector('[data-testid="row-save-failed"]')!;
      assert.ok(failure.textContent?.includes("No pudimos confirmar si Comercio o persona se guardó."));
      assert.ok(failure.querySelector('[data-testid="error-reference"]'), "a lost answer still shows a reference");
      assert.equal(button(page.host, "Aprobar").disabled, true);
      assert.ok(![...failure.querySelectorAll("button")].some((item) => item.textContent === "Cancelar"), "nothing may be dropped while its outcome is unknown");
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
      await page.wait(() => Boolean(page.host.querySelector('[data-testid="row-save-failed"]')));
      assert.ok(page.row("counterparty").textContent?.includes("Corrección de otra persona"), "the other person's change is on screen");
      assert.equal(page.host.querySelector<HTMLInputElement>('[data-testid="dossier-review-amount"]')?.value, "950.00");
      await page.act(async () => button(page.row("amount"), "Reintentar").click());
      await page.wait(() => Boolean(page.row("amount").querySelector('[data-testid="row-saved"]')));
      assert.ok(page.row("amount").textContent?.includes("RD$ 950.00"));
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
