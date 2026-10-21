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
  async function mountEditor(expense: Record<string, unknown>) {
    const dossier = structuredClone(await createDossierFixtures([{ id: "cash", type: "cash", currency: "DOP", nickname: "caja" }]).dossier(dossierFixtureIds.ready));
    globalThis.fetch = async (url) => {
      if (String(url).includes("/fields")) return Response.json({ "606": [], "607": [] });
      return Response.json({ items: [expense] });
    };
    const view = await render(<FiscalDeclarationEditor dossier={dossier} disabled={false} onChanged={() => undefined} onBusy={() => undefined} onDirty={() => undefined} />);
    const refund = view.host.querySelector<HTMLInputElement>('input[type="checkbox"]');
    assert.ok(refund);
    await act(async () => refund.click());
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 50)); });
    const options = [...view.host.querySelectorAll("select option")].map((option) => option.textContent ?? "");
    return { view, options };
  }
  const expense = { id: "exp-1", merchant: "Ferretería", amount: "1234.5", currency: "USD", occurred_on: "2026-10-01", category_id: null, account_id: null, receipt_id: null };

  test("offers each purchase with its amount through the shared formatter", async () => {
    const { view, options } = await mountEditor(expense);
    try {
      assert.ok(options.some((text) => text.includes("US$ 1,234.50")), options.join(" | "));
      assert.ok(!options.some((text) => /1234\.5 USD/.test(text)));
    } finally { await view.dispose(); }
  });

  test("a purchase with no currency reads as unknown", async () => {
    const { view, options } = await mountEditor({ ...expense, currency: null });
    try {
      const own = options.find((text) => text.includes("Ferretería")) ?? "";
      assert.match(own, /· -$/);
      assert.doesNotMatch(own, /RD\$|DOP|1234/);
    } finally { await view.dispose(); }
  });
});
