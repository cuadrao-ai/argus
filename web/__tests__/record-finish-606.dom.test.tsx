import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessDataSource } from "@/components/business-app/business-data";
import type { BusinessExpenseDetail } from "@/lib/business-api";
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
  target?: "draft" | "expense";
  missing?: string[];
  /** What the server would answer on this dossier: read-only, and so on. */
  serve?: (dossier: Dossier) => void;
};

async function mount({ width = 1280, record = "fiscal", target = "draft", missing, serve = () => undefined }: Options = {}) {
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
  const { ShellAccount } = await import("./support/shell-account");
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
  Object.assign(row, { draft_id: draftId, counterparty: "Ferretería La Esquina", ready: false, missing: ["expense_type_missing", "payment_method_missing"], stage: "needs_fiscal_data", fiscal_data: "missing", export_missing: "expense_type_missing", export_missing_several: true });
  if (target === "expense") Object.assign(row, { draft_id: null, row_id: `expense:${row.linked_activity_ids[0]}` });
  const reasons = {
    expense_type_missing: { field: "category", words: "business.transactions.layout.workflow.missing.expense_type_missing" },
    payment_method_missing: { field: "payment_method", words: "business.transactions.layout.workflow.missing.payment_method_missing" },
    supplier_id: { field: "rnc", words: "business.transactions.layout.workflow.missing.missing_rnc" },
  };
  let detailMissing = missing ?? [...row.missing];
  report.controls.overview = { not_ready: 1, needs_review: 0, needs_fiscal_data: 0, ready_for_export: 0, exported: 0 };
  const verdict = ({ dgii }: Dossier) => {
    const missing = [dgii?.category ? null : "expense_type_missing", dgii?.payment_method ? null : "payment_method_missing"].filter(Boolean) as string[];
    detailMissing = missing;
    Object.assign(row, { ready: missing.length === 0, missing }, missing.length ? { stage: "needs_fiscal_data", fiscal_data: "missing", export_missing: missing[0], export_missing_several: missing.length > 1 } : { stage: "ready_for_export", fiscal_data: "complete", export_missing: null, export_missing_several: false });
  };

  const writes: { version: number; purchase: PurchaseChoice }[] = [];
  const detailVersions: number[] = [];
  const served = (dossier: Dossier) => {
    detailVersions.push(dossier.version);
    Object.assign(dossier, { missing: detailMissing, reasons });
    serve(dossier);
    return dossier;
  };
  const source = {
    ...fixture,
    mode: "live" as const,
    dossier: async (id: string) => served(await fixture.dossier(id)),
    expense: async (id: string): Promise<BusinessExpenseDetail> => ({
      missing: id === row.linked_activity_ids[0] ? detailMissing : [], reasons,
      id, merchant: `Registro ${id}`, amount: "100.00", currency: "DOP", category_id: null, account_id: null,
      occurred_on: "2026-10-01", receipt_id: null, draft_id: null, recorded_at: "2026-10-01T12:00:00Z", revision: 1,
    } as BusinessExpenseDetail),
    reviewPurchase: async (id: string, version: number, purchase: PurchaseChoice, key: string) => {
      writes.push({ version, purchase });
      const next = await fixture.reviewPurchase(id, version, purchase, key);
      verdict(next);
      return served(next);
    },
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
            <ShellAccount member="synthetic-person" dismissed={["registros-intro"]}><Probe /></ShellAccount>
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
  const section = () => document.querySelector<HTMLElement>('[data-testid="receipt-facts-choices"]');
  type Choice = "category" | "payment_method";
  const choiceRow = (name: Choice) => section()?.querySelector<HTMLElement>(`[data-fact="${name}"]`);
  const listButton = (name: Choice) => choiceRow(name)?.querySelector<HTMLButtonElement>('button[aria-haspopup="listbox"]');
  const options = (name: Choice) => [...choiceRow(name)!.querySelectorAll<HTMLButtonElement>('[role="option"]')];
  const toggleChoice = async (name: Choice) => {
    await wait(() => Boolean(listButton(name)), `the ${name} list`);
    await act(async () => listButton(name)!.click());
  };
  const valueOf = (name: Choice) => choiceRow(name)?.querySelector("[data-row-value]")?.textContent;
  const chip = () => document.querySelector(`[data-record-key="${row.row_id}"] [data-record-status]`)?.textContent ?? null;
  const pick = async (name: Choice, value: string) => {
    await toggleChoice(name);
    const option = options(name).find((item) => item.dataset.value === value);
    assert.ok(option, `${name} offers ${value}`);
    await act(async () => option.click());
  };
  const queries = () => report.calls.filter((call) => call.path.endsWith("/reports/query")).length;
  await act(async () => api!.openPanel({ kind: "transactions" }));
  const openRecord = async () => {
    await wait(() => chip() !== null, "the recorded row");
    await act(async () => {
      const selected = document.querySelector<HTMLElement>(`[data-record-key="${row.row_id}"]`)!;
      (selected.matches("tr") ? selected : selected.querySelector<HTMLButtonElement>("button")!).click();
    });
    await wait(() => target === "expense" ? document.querySelector('[data-testid="record-facts-comprobante"]') !== null : facts() !== null, "the record's detail");
  };
  const openDirectly = async () => {
    await act(async () => api!.openPanel({ kind: "draft", draftId, list: "transactions" }));
    await wait(() => target === "expense" ? document.querySelector('[data-testid="record-facts-comprobante"]') !== null : facts() !== null, "the record's detail");
  };
  const openFromSearch = async () => {
    const { searchKindGroups } = await import("@/components/business-app/business-search-groups");
    const expense = { ...await source.expense(row.linked_activity_ids[0]), draft_id: target === "draft" ? draftId : null };
    const groups = searchKindGroups({
      t: i18n.t.bind(i18n), locale: "es-419", source, accounts: [], openPanel: api!.openPanel, stateWord: () => "",
    }, "Registro", { expenses: [expense], ventas: [], accounts: [], receipts: [], email_deliveries: [], email_senders: [], next_cursors: {} });
    await act(async () => groups.expenses.hits[0].open!());
    await wait(() => target === "expense" ? document.querySelector('[data-testid="record-facts-comprobante"]') !== null : facts() !== null, "the search result's detail");
  };
  const openOtherExpense = async () => {
    await act(async () => api!.openPanel({ kind: "expense", expenseId: "00000000-0000-4000-8000-000000009999" }));
    await wait(() => document.querySelector("#receipt-review-title")?.textContent === "Registro 00000000-0000-4000-8000-000000009999", "the other expense");
  };
  return { act, wait, writes, detailVersions, chip, listButton, options, toggleChoice, valueOf, pick, facts, queries, section, openRecord, openDirectly, openFromSearch, openOtherExpense };
}

describe("opened records show only their server readiness list", () => {
  const missing = ["expense_type_missing", "payment_method_missing", "supplier_id"];
  const words = ["Falta el tipo de gasto", "Falta la forma de pago", "Falta el RNC"];
  const shown = () => [...document.querySelectorAll("[data-record-missing-list] li")].map((item) => item.textContent);

  for (const target of ["expense", "draft"] as const) {
    for (const entry of ["openFromSearch", "openRecord"] as const) {
      test(`${target}: ${entry} shows the record's ordered missing reasons and words`, async () => {
        const page = await mount({ target, missing });
        await page[entry]();
        assert.deepEqual(shown(), words);
      });
    }

    test(`${target}: a clean detail has no missing list even when the report row has gaps`, async () => {
      const page = await mount({ target, missing: [] });
      await page.openRecord();
      assert.deepEqual(shown(), []);
    });

    test(`${target}: on a phone, the way back puts focus on the live report row that opened it`, async () => {
      const page = await mount({ width: 390, target, missing: [] });
      await page.openRecord();
      assert.equal(document.querySelector('[data-testid="business-record-review"]')?.getAttribute("data-presentation"), "page", "the record is the page");
      await page.act(async () => [...document.querySelectorAll("button")].find((button) => button.textContent === "Registros")!.click());
      const opener = () => {
        const selected = document.querySelector<HTMLElement>("[data-record-key]");
        return selected?.matches("tr") ? selected : selected?.querySelector("button") ?? null;
      };
      await page.wait(() => opener() !== null && document.activeElement === opener(), "focus on the row that opened the record");
    });

    test(`${target}: another opened record never inherits the selected report's reasons`, async () => {
      const page = await mount({ target, missing });
      await page.openRecord();
      assert.deepEqual(shown(), words);
      await page.openOtherExpense();
      assert.deepEqual(shown(), [], "a different target has no readiness answer from the previous selection");
    });
  }
});

describe("a recorded purchase with 606 data still missing", () => {
  test("opens from live Registros with both choices, and the chip follows each save with nothing else reloading", async () => {
    const page = await mount();
    await page.wait(() => document.querySelector("[data-report-connected]") !== null && page.chip() !== null, "live Registros");
    assert.equal(page.chip(), "Faltan 2 datos");
    await page.openRecord();

    assert.equal(page.section()?.querySelector("h3")?.textContent, "Reporte 606");
    for (const [name, options] of [["category", 11], ["payment_method", 7]] as const) {
      await page.toggleChoice(name);
      assert.equal(page.listButton(name)?.disabled, false);
      assert.equal(page.options(name).length, options);
      await page.toggleChoice(name);
    }
    assert.ok(page.facts()?.querySelector('[data-fact="amount"] button[data-row-value]'), "the server enables the accepted Total");
    assert.equal(page.facts()?.querySelector('[data-fact="category_id"]'), null, "tipo de gasto is the only classification a Business record shows");
    assert.equal(page.facts()?.textContent?.includes("Categoría"), false);

    const dossier = page.facts();
    const list = document.querySelector("[data-report-connected]");
    const asked = page.queries();
    await page.pick("category", "02");
    const reasons = () => [...document.querySelectorAll("[data-record-missing-list] li")].map((item) => item.textContent);
    await page.wait(() => reasons().length === 1 && page.queries() > asked, "the reason and refreshed Registros after Tipo de gasto");
    assert.equal(page.chip(), "Falta la forma de pago", "the status names the remaining server reason");
    assert.deepEqual(reasons(), ["Falta la forma de pago"], "the open record follows the refreshed server missing list");
    await page.wait(() => page.valueOf("category")?.includes("Gastos por trabajos") === true, "the saved Tipo de gasto");
    await page.pick("payment_method", "03");
    await page.wait(() => page.chip() === null, "the empty status after the last missing fact");
    assert.equal(document.querySelector("[data-record-missing-list]"), null, "the ready response clears the open record reasons");

    assert.deepEqual(page.writes.map(({ purchase }) => purchase), [{ category: "02" }, { payment_method: "03" }], "only the 606 choices go out");
    assert.equal(page.writes[1].version, page.writes[0].version + 1, "each save stands on the last one");
    assert.equal(page.facts(), dossier, "the dossier stayed on screen");
    assert.equal(document.querySelector("[data-report-connected]"), list, "the list stayed on screen");
  });

  test("a phone opened from the live report refreshes its full missing list after every save", async () => {
    const page = await mount({ width: 390 });
    const reasons = () => [...document.querySelectorAll("[data-record-missing-list] li")].map((item) => item.textContent);
    await page.openRecord();
    assert.equal(document.querySelector("[data-report-connected]"), null, "the phone record unmounts Registros");
    assert.deepEqual(reasons(), ["Falta el tipo de gasto", "Falta la forma de pago"]);
    const dossier = page.facts();
    const asked = page.queries();
    const detailCount = page.detailVersions.length;
    const version = page.detailVersions[detailCount - 1];
    await page.pick("category", "02");
    await page.wait(() => page.valueOf("category")?.includes("Gastos por trabajos") === true, "the phone's saved Tipo de gasto");
    await page.wait(() => reasons().join("|") === "Falta la forma de pago", "the phone's refreshed server missing list");
    assert.equal(page.queries(), asked, "the unmounted report stays idle after saving");
    await page.pick("payment_method", "03");
    await page.wait(() => page.valueOf("payment_method") === "Tarjeta crédito/débito", "the phone's saved Forma de pago");
    await page.wait(() => document.querySelector("[data-record-missing-list]") === null, "the phone's ready response clears the reasons");
    assert.deepEqual(page.detailVersions.slice(detailCount), [version + 1, version + 2], "each save returns the refreshed dossier once");
    assert.equal(page.queries(), asked, "neither save issues a Registros query");
    assert.equal(page.facts(), dossier, "the phone record stays open across both saves");
    assert.deepEqual(page.writes.map(({ purchase }) => purchase), [{ category: "02" }, { payment_method: "03" }]);
  });

  test("a phone reaches the same choices on the full-page record and saves them", async () => {
    const page = await mount({ width: 390 });
    await page.openDirectly();
    await page.pick("category", "02");
    await page.wait(() => page.writes.length === 1, "the save");
    assert.deepEqual(page.writes[0].purchase, { category: "02" });
  });
});

describe("a recorded purchase that cannot take a change", () => {
  const held = (dossier: Dossier) => Object.assign(dossier, { dgii: { form: "606", category: "02", payment_method: null } });

  test("someone who cannot edit reads the values with no control", async () => {
    const page = await mount({ serve: (dossier) => { held(dossier); dossier.declaration_editable = false; dossier.capabilities = ["read"]; } });
    await page.openDirectly();
    const section = page.section();
    assert.ok(section);
    await page.wait(() => /Gastos por trabajos, suministros y servicios/.test(section.querySelector('[data-fact="category"]')?.textContent ?? ""), "the type's label");
    assert.equal(section.querySelector("select, button, input"), null);
    const unanswered = section.querySelector('[data-fact="payment_method"]');
    assert.equal(unanswered?.firstElementChild?.textContent, "Forma de pago");
    assert.equal(unanswered?.querySelector('[data-row-value][data-empty="true"]')?.textContent, "Sin dato");
  });

  test("an income and a record with no comprobante have no Reporte 606 card", async () => {
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
