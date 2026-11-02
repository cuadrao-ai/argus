import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessDataSource } from "@/components/business-app/business-data";
import type { PurchaseChoice } from "@/lib/business-dgii";
import { createBusinessReportHttpFixture } from "./fixtures/business-report-http-fixture";

// The real workspace over the sample's server, answering as a live source, so
// Registros runs BusinessReportsPanel and not the sample's own list.
mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
  usePathname: () => "/biz",
}));

const originalMock = process.env.NEXT_PUBLIC_MOCK_AUTH;
beforeAll(() => {
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1280, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
  if (originalMock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMock;
});

const cleanups: (() => Promise<void>)[] = [];
afterEach(async () => {
  while (cleanups.length) await cleanups.pop()!();
  document.body.innerHTML = "";
});

type Dossier = Awaited<ReturnType<BusinessDataSource["dossier"]>>;
type Options = {
  width?: number;
  record?: "fiscal" | "income";
  /** What the server would answer on this dossier: frozen, read-only, and so on. */
  serve?: (dossier: Dossier) => void;
  reviewPurchase?: BusinessDataSource["reviewPurchase"];
};
const NO_RECEIPT = "Las correcciones después del registro no están disponibles en este primer flujo.";

async function mount({ width = 1280, record = "fiscal", serve = () => undefined, reviewPurchase }: Options = {}) {
  (window as unknown as { happyDOM: { setViewport: (size: { width: number; height: number }) => void } }).happyDOM.setViewport({ width, height: 900 });
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { dossierFixtureIds } = await import("@/components/business-app/dossier-fixtures");
  const BusinessPanel = (await import("@/components/business-app/BusinessPanel")).default;
  const { setChosenGrant } = await import("@/lib/business-grant");
  setChosenGrant(null);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });

  const fixture = createFixtureBusinessDataSource({ chatAvailable: true });
  const draftId = dossierFixtureIds[record];
  const start = await fixture.dossier(draftId);
  if (start.approval_available) await fixture.approveDraft(draftId, start.version, "approve-with-no-606-data", start.approval_action!);

  // One recorded row: the server's verdict on it moves as the 606 answers do.
  const report = createBusinessReportHttpFixture();
  report.records.splice(1);
  const [row] = report.records;
  Object.assign(row, { draft_id: draftId, counterparty: "Ferretería La Esquina", stage: "needs_fiscal_data", export_missing: "expense_type_missing", export_missing_several: true });
  report.controls.overview = { needs_review: 0, awaiting_approval: 0, ready_for_export: 0 };
  const verdict = ({ dgii }: Dossier) => {
    const missing = [dgii?.category ? null : "expense_type_missing", dgii?.payment_method ? null : "payment_method_missing"].filter(Boolean) as string[];
    Object.assign(row, missing.length ? { stage: "needs_fiscal_data", export_missing: missing[0], export_missing_several: missing.length > 1 } : { stage: "ready_for_export", export_missing: null, export_missing_several: false });
  };

  const writes: { version: number; purchase: PurchaseChoice }[] = [];
  const served = async (read: Promise<Dossier>) => { const dossier = await read; serve(dossier); return dossier; };
  const source = {
    ...fixture,
    mode: "live" as const,
    dossier: (id: string) => served(fixture.dossier(id)),
    reviewPurchase: reviewPurchase ?? (async (id: string, version: number, purchase: PurchaseChoice, key: string) => {
      writes.push({ version, purchase });
      const next = await served(fixture.reviewPurchase(id, version, purchase, key));
      verdict(next);
      return next;
    }),
  };
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    if (new URL(String(input), "http://127.0.0.1").pathname.endsWith("/me")) return Response.json({ user: { id: "synthetic-person", email: "persona@example.com" } });
    return report.request(input, init);
  }) as typeof fetch;

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
  cleanups.push(async () => { await act(async () => root.unmount()); globalThis.fetch = originalFetch; });
  const wait = async (done: () => boolean, what: string) => {
    for (let i = 0; i < 80; i += 1) {
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
      if (done()) return;
    }
    throw new Error(`timed out waiting for ${what}: ${document.body.textContent?.slice(0, 400)}`);
  };
  const facts = () => document.querySelector<HTMLElement>('[data-testid="receipt-current-facts"]');
  const choice = (name: "category" | "payment_method") => document.querySelector<HTMLSelectElement>(`[data-fact="${name}"] select`);
  const chip = () => document.querySelector(`[data-record-key="${row.row_id}"] [data-record-workflow]`)?.textContent ?? null;
  const pick = async (name: "category" | "payment_method", value: string) => {
    const select = choice(name);
    assert.ok(select, `${name} offers its control`);
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")!.set!.call(select, value);
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });
  };
  const queries = () => report.calls.filter((call) => call.path.endsWith("/reports/query")).length;
  await act(async () => api!.openPanel({ kind: "transactions" }));
  const openRecord = async () => {
    await wait(() => chip() !== null, "the recorded row");
    await act(async () => document.querySelector<HTMLElement>(`[data-record-key="${row.row_id}"]`)!.click());
    await wait(() => facts() !== null, "the record's dossier");
    await wait(() => !document.querySelector('[data-testid="receipt-facts-choices"]') || Boolean(document.querySelector('[data-fact="category"] option, [data-fact="category"] dd span')), "the tax fields");
  };
  const openDirectly = async () => {
    await act(async () => api!.openPanel({ kind: "draft", draftId, list: "transactions" }));
    await wait(() => facts() !== null, "the record's dossier");
    await wait(() => !document.querySelector('[data-testid="receipt-facts-choices"]') || Boolean(document.querySelector('[data-fact="category"] option, [data-fact="category"] dd span')), "the tax fields");
  };
  const section = () => document.querySelector<HTMLElement>('[data-testid="receipt-facts-choices"]');
  return { act, wait, writes, chip, choice, pick, facts, queries, section, openRecord, openDirectly };
}

describe("a recorded purchase with 606 data still missing", () => {
  test("opens from live Registros with both choices, and the chip follows each save with nothing else reloading", async () => {
    const page = await mount();
    await page.wait(() => document.querySelector("[data-report-connected]") !== null && page.chip() !== null, "live Registros");
    assert.equal(page.chip(), "Faltan datos fiscales");
    await page.openRecord();

    assert.match(page.section()?.textContent ?? "", /Para el 606/);
    assert.equal(page.choice("category")?.disabled, false);
    assert.equal(page.choice("payment_method")?.disabled, false);
    assert.equal(page.choice("category")?.querySelectorAll("option").length, 12, "the same 11 types and Elegir as before approval");
    assert.equal(page.choice("payment_method")?.querySelectorAll("option").length, 8, "the same 7 forms and Elegir as before approval");
    assert.equal(page.facts()?.querySelector('[data-fact="amount"] button'), null, "the recorded facts stay locked");
    assert.equal(document.body.textContent?.includes(NO_RECEIPT), false, "the screen does not deny what it offers");

    const dossier = page.facts();
    const list = document.querySelector("[data-report-connected]");
    const asked = page.queries();
    await page.pick("category", "02");
    await page.wait(() => page.chip() === "Falta la forma de pago", "the chip after Tipo de gasto");
    assert.ok(page.queries() > asked, "Registros asked the server again");
    await page.wait(() => page.choice("category")?.value === "02", "the saved Tipo de gasto");
    await page.pick("payment_method", "03");
    await page.wait(() => page.chip() === "Listo", "the chip after the last missing fact");

    assert.deepEqual(page.writes.map(({ purchase }) => purchase), [{ category: "02" }, { payment_method: "03" }], "only the 606 choices go out");
    assert.equal(page.writes[1].version, page.writes[0].version + 1, "each save stands on the last one");
    assert.equal(page.facts(), dossier, "the dossier stayed on screen");
    assert.equal(document.querySelector("[data-report-connected]"), list, "the list stayed on screen");
  });

  test("a phone reaches the same choices on the full-page record and saves them", async () => {
    const page = await mount({ width: 390 });
    await page.openDirectly();
    await page.pick("category", "02");
    await page.wait(() => page.writes.length === 1, "the save");
    assert.deepEqual(page.writes[0].purchase, { category: "02" });
  });

  test("a save refused because an export froze the line locks the fields from the current record", async () => {
    let frozen = false;
    const page = await mount({
      serve: (dossier) => { if (frozen) dossier.declaration_editable = false; },
      reviewPurchase: async () => {
        frozen = true;
        throw Object.assign(new Error("refused"), { status: 422, code: "fiscal_declaration_exported", requestId: "req-frozen-606" });
      },
    });
    await page.openDirectly();
    assert.equal(page.choice("category")?.disabled, false);
    await page.pick("category", "02");
    await page.wait(() => page.choice("category")?.disabled === true, "the locked field");
    assert.equal(page.choice("payment_method")?.disabled, true);
    assert.equal(page.choice("category")?.value, "", "the field shows what the record holds");
    assert.ok(document.querySelector('[data-fact="category"] [data-testid="row-save-failed"]')?.textContent?.includes("Ref."), "the refusal keeps its reference");
  });
});

describe("a recorded purchase that cannot take a change", () => {
  const held = (dossier: Dossier) => Object.assign(dossier, { dgii: { form: "606", category: "02", payment_method: null } });

  test("after an export the choices read as locked with their values", async () => {
    const page = await mount({ serve: (dossier) => { held(dossier); dossier.declaration_editable = false; } });
    await page.openDirectly();
    assert.equal(page.choice("category")?.value, "02");
    assert.equal(page.choice("category")?.disabled, true);
    assert.equal(page.choice("payment_method")?.disabled, true);
    assert.equal(document.body.textContent?.includes(NO_RECEIPT), true);
    assert.equal(document.querySelector('[data-testid="expense-type-suggestion"]'), null);
  });

  test("someone who cannot edit reads the values with no control", async () => {
    const page = await mount({ serve: (dossier) => { held(dossier); dossier.declaration_editable = false; dossier.capabilities = ["read"]; } });
    await page.openDirectly();
    const section = page.section();
    assert.ok(section);
    assert.equal(section.querySelector("select, button, input"), null);
    assert.match(section.querySelector('[data-fact="category"]')?.textContent ?? "", /Gastos por trabajos, suministros y servicios/);
    assert.match(section.querySelector('[data-fact="payment_method"]')?.textContent ?? "", /Forma de pago\s*-/);
  });

  test("an income and a record with no comprobante have no Para el 606", async () => {
    const income = await mount({ record: "income", serve: (dossier) => Object.assign(dossier, { review_state: "accepted", approval_result: { status: "recorded", activity_id: "70000000-0000-4000-8000-000000000009", reviewed_version: 2, approved_revision: 2, approved_at: "2026-10-10T14:40:00Z", actor: dossier.history[0].actor } }) });
    await income.openDirectly();
    assert.equal(income.section(), null);
    await cleanups.pop()!();
    document.body.innerHTML = "";
    const none = await mount({ serve: (dossier) => { dossier.sin_comprobante = true; dossier.declaration_editable = false; } });
    await none.openDirectly();
    assert.equal(none.section(), null);
  });
});
