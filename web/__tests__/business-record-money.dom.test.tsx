import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import { BankMatchSuggestionCard, type BankMatchSuggestionCardProps } from "@/components/business-app/BankMatchSuggestion";
import { ReceiptReadPurchases } from "@/components/business-app/ReceiptDossierReview";
import FiscalDeclarationEditor from "@/components/business-app/FiscalDeclarationEditor";
import { createDossierFixtures, dossierFixtureIds } from "@/components/business-app/dossier-fixtures";
import type { BusinessDossier } from "@/lib/business-dossier";
import spanish from "@/public/locales/es-419/common.json";

const originalFetch = globalThis.fetch;
const originalMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { value: true, configurable: true, writable: true });
});
afterAll(async () => {
  globalThis.fetch = originalFetch;
  if (originalMockAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMockAuth;
  await GlobalRegistrator.unregister();
});

async function render(node: React.ReactNode) {
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}>{node}</I18nextProvider>));
  return { host, dispose: async () => { await act(async () => root.unmount()); host.remove(); } };
}

const side = { occurredOn: "01/10/2026", description: "Ferretería Luna" };
function card(line: { amount: string; currency: string | null }, document: { amount: string; currency: string | null }): BusinessMatchProps {
  return { line: { ...side, ...line }, document: { ...side, kind: "receipt", ...document }, onConfirm: () => undefined, onDecline: () => undefined, enabled: true };
}
type BusinessMatchProps = BankMatchSuggestionCardProps;

describe("a bank match suggestion shows money through the shared formatter", () => {
  test("each side keeps its own currency, symbol and exact decimals", async () => {
    const view = await render(<BankMatchSuggestionCard {...card({ amount: "-1500.5", currency: "DOP" }, { amount: "1234.5", currency: "USD" })} />);
    try {
      const line = view.host.querySelector('[data-testid="bank-match-line"]')?.textContent ?? "";
      const document = view.host.querySelector('[data-testid="bank-match-document"]')?.textContent ?? "";
      assert.match(line, /-RD\$ 1,500\.50/);
      assert.match(document, /US\$ 1,234\.50/);
      assert.doesNotMatch(line + document, /\d (DOP|USD)\b/);
    } finally { await view.dispose(); }
  });

  test("a currency without decimals shows none", async () => {
    const view = await render(<BankMatchSuggestionCard {...card({ amount: "1500", currency: "JPY" }, { amount: "1500", currency: "JPY" })} />);
    try {
      const line = view.host.querySelector('[data-testid="bank-match-line"]')?.textContent ?? "";
      assert.match(line, /1,500(?![.\d])/);
    } finally { await view.dispose(); }
  });

  test("a missing currency reads as unknown, never as pesos", async () => {
    const view = await render(<BankMatchSuggestionCard {...card({ amount: "-1500.00", currency: null }, { amount: "1500.00", currency: null })} />);
    try {
      const line = view.host.querySelector('[data-testid="bank-match-line"] p:last-child')?.textContent;
      const document = view.host.querySelector('[data-testid="bank-match-document"] p:last-child')?.textContent;
      assert.equal(line, "-");
      assert.equal(document, "-");
      assert.doesNotMatch(view.host.textContent ?? "", /RD\$|DOP/);
    } finally { await view.dispose(); }
  });
});

async function readDossier(purchases: BusinessDossier["read_purchases"], currency: string | null): Promise<BusinessDossier> {
  const dossier = structuredClone(await createDossierFixtures([{ id: "cash", type: "cash", currency: "DOP", nickname: "caja" }]).dossier(dossierFixtureIds.ready));
  dossier.read_purchases = purchases;
  dossier.read_total = "2000.5";
  dossier.unrecorded_purchases = 1;
  dossier.facts.currency = currency ? { state: "known", value: currency, origin: "extracted", verified: false, source_ids: [] } : { state: "unknown", value: null, origin: null, verified: false, source_ids: [] };
  return dossier;
}

describe("the purchases read on a receipt", () => {
  test("show each amount in its own currency through the shared formatter", async () => {
    const dossier = await readDossier([
      { index: 1, amount: "1234.5", currency: "USD", occurred_on: null, merchant: "Uno", kind_hint: null },
      { index: 2, amount: "99", currency: "DOP", occurred_on: null, merchant: "Dos", kind_hint: null },
    ], "USD");
    const view = await render(<ReceiptReadPurchases dossier={dossier} />);
    try {
      const rows = [...view.host.querySelectorAll("li")].map((item) => item.textContent ?? "");
      assert.match(rows[0], /US\$ 1,234\.50/);
      assert.match(rows[1], /RD\$ 99\.00/);
      assert.doesNotMatch(rows.join(" "), /\d (USD|DOP)\b/);
    } finally { await view.dispose(); }
  });

  test("a purchase with no currency reads as unknown, and so does the remainder note", async () => {
    const dossier = await readDossier([{ index: 1, amount: "1234.5", currency: null, occurred_on: null, merchant: "Uno", kind_hint: null }], null);
    dossier.review_state = "accepted";
    dossier.facts.amount = { state: "known", value: "10", origin: "member_set", verified: false, source_ids: [] };
    const view = await render(<ReceiptReadPurchases dossier={dossier} />);
    try {
      const row = view.host.querySelector("li span:last-child")?.textContent;
      assert.equal(row, "-");
      const note = view.host.querySelector('[data-testid="dossier-read-remainder"]')?.textContent ?? "";
      assert.doesNotMatch(note, /1234|2000|RD\$/);
    } finally { await view.dispose(); }
  });
});

describe("the original purchase picker in the tax details", () => {
  const candidate = { id: "act-1", merchant: "Ferretería", amount: "1234.50", currency: "USD", occurred_on: "2026-10-01" };
  async function mountEditor(candidates: BusinessDossier["refund_candidates"], answer: (body: Record<string, unknown>) => Response = () => Response.json({})) {
    const dossier = { ...structuredClone(await createDossierFixtures([{ id: "cash", type: "cash", currency: "DOP", nickname: "caja" }]).dossier(dossierFixtureIds.ready)), refund_candidates: candidates };
    const asked: string[] = [];
    const sent: Record<string, unknown>[] = [];
    globalThis.fetch = async (url, init) => {
      asked.push(String(url));
      if (String(url).includes("/fields")) return Response.json({ "606": [], "607": [] });
      const body = JSON.parse(String(init?.body ?? "{}"));
      sent.push(body);
      return answer(body);
    };
    const view = await render(<FiscalDeclarationEditor dossier={dossier} disabled={false} onChanged={() => undefined} onBusy={() => undefined} onDirty={() => undefined} />);
    const refund = view.host.querySelector<HTMLInputElement>('input[type="checkbox"]');
    assert.ok(refund);
    await act(async () => refund.click());
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 50)); });
    const rows = () => [...view.host.querySelectorAll<HTMLElement>('[data-testid="refund-candidate"]')];
    const pick = (index: number) => act(async () => rows()[index].querySelector<HTMLInputElement>('input[type="radio"]')!.click());
    const save = async () => {
      const button = [...view.host.querySelectorAll("button")].find((node) => node.textContent === "Guardar revisión fiscal");
      assert.ok(button);
      await act(async () => button.click());
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)); });
    };
    return { view, rows, pick, save, asked, sent };
  }

  test("lists the server's candidates with each amount through the shared formatter and asks for no window of its own", async () => {
    const { view, rows, asked } = await mountEditor([candidate, { ...candidate, id: "act-2", merchant: null, amount: "980.00", currency: "DOP", occurred_on: "2026-09-28" }]);
    try {
      assert.equal(rows().length, 2);
      assert.match(rows()[0].textContent ?? "", /Ferretería.*US\$ 1,234\.50/);
      assert.doesNotMatch(rows()[0].textContent ?? "", /1234\.5 USD/);
      assert.match(rows()[1].textContent ?? "", /^-/, "a candidate with no merchant names none");
      assert.match(rows()[1].textContent ?? "", /RD\$ 980\.00/);
      assert.deepEqual(asked.filter((url) => !url.includes("/fields")), [], "no expenses request picks purchases in the browser");
    } finally { await view.dispose(); }
  });

  test("with no candidates it says so", async () => {
    const { view } = await mountEditor([]);
    try {
      assert.equal(view.host.querySelector('[data-testid="refund-candidates-none"]')?.textContent, "No hay compras aprobadas para elegir.");
    } finally { await view.dispose(); }
  });

  test("a candidate the server refuses says so in place, keeps the choice, and another can be picked and saved", async () => {
    const { view, rows, pick, save, sent } = await mountEditor(
      [candidate, { ...candidate, id: "act-2", merchant: "Colmado" }],
      (body) => (body.dgii as { declaration: { purchase_activity_id: string } }).declaration.purchase_activity_id === "act-1"
        ? Response.json({ code: "recorded_correction_unsupported" }, { status: 422 })
        : Response.json({}),
    );
    try {
      await pick(0);
      await save();
      const refused = rows()[0].querySelector('[data-testid="refund-candidate-refused"]');
      assert.equal(refused?.textContent, "Esa compra no se puede usar para este reembolso. Elige otra.");
      assert.equal(rows()[0].querySelector<HTMLInputElement>('input[type="radio"]')?.checked, true, "the choice stays");
      assert.equal(view.host.querySelectorAll('[role="alert"]').length, 1, "one message, beside the purchase");
      assert.equal(rows()[1].querySelector<HTMLInputElement>('input[type="radio"]')?.disabled, false);
      await pick(1);
      assert.equal(view.host.querySelector('[data-testid="refund-candidate-refused"]'), null);
      await save();
      assert.deepEqual(sent.map((body) => (body.dgii as { declaration: { purchase_activity_id: string } }).declaration.purchase_activity_id), ["act-1", "act-2"]);
      assert.equal(view.host.querySelector('[role="alert"]'), null);
    } finally { await view.dispose(); }
  });
});
