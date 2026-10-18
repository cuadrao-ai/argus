import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterAll, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";
import type { BusinessDataSource } from "@/components/business-app/business-data";

mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
  usePathname: () => "/biz",
}));

const root = join(import.meta.dir, "..");

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  Object.defineProperty(window.navigator, "language", { configurable: true, value: "en-US" });
  Object.defineProperty(window.navigator, "languages", { configurable: true, value: ["en-US", "en"] });
  window.localStorage.setItem("i18nextLng", "en");
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});

afterAll(async () => {
  await GlobalRegistrator.unregister();
});

describe("Business stays in Spanish for an en-US browser", () => {
  test("the signed-in shell and the document language do not take the account's English", () => {
    const chat = readFileSync(join(root, "components/chat/ChatInterface.tsx"), "utf-8");
    const session = readFileSync(join(root, "components/chat/useInitialChatSession.ts"), "utf-8");
    const provider = readFileSync(join(root, "components/I18nProvider.tsx"), "utf-8");
    const layout = readFileSync(join(root, "app/layout.tsx"), "utf-8");
    for (const source of [chat, session]) {
      assert.match(source, /commitShellLanguage\(/);
      assert.equal(source.includes("i18n.changeLanguage"), false);
    }
    assert.match(provider, /documentLanguage\(/);
    assert.match(layout, /documentLanguage\(/);
    assert.equal(layout.includes('lang="en"'), false);
  });

  test("overview, upload, record expense, and receipt review render Spanish", async () => {
    const { accountLanguageToApply, commitShellLanguage, documentLanguage } = await import("@/lib/language-features");
    const calls: string[] = [];
    await commitShellLanguage(
      { language: "en", changeLanguage: async (next: string) => { calls.push(next); } },
      true,
      "en",
      true,
    );
    assert.deepEqual(calls, ["es-419"]);
    const language = accountLanguageToApply(true, "en", true);
    assert.equal(language, "es-419");
    assert.equal(window.localStorage.getItem("i18nextLng"), "en");
    assert.equal(documentLanguage(language, true, true), "es");
    assert.equal(documentLanguage("en", true, true), "es");
    assert.equal(documentLanguage("es-419", false, true), "es-419");
    document.documentElement.lang = documentLanguage(language, true, true);

    const { act } = await import("react");
    const { createRoot } = await import("react-dom/client");
    const i18next = (await import("i18next")).default;
    const { I18nextProvider } = await import("react-i18next");
    const { BusinessWorkspaceProvider } = await import("@/components/business-app/BusinessWorkspace");
    const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
    const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
    const { setChosenGrant } = await import("@/lib/business-grant");
    const BusinessOverviewPanel = (await import("@/components/business-app/BusinessOverviewPanel")).default;
    const RecordExpenseDialog = (await import("@/components/business-app/RecordExpenseDialog")).default;
    const ReceiptIntakeDialog = (await import("@/components/business-app/ReceiptIntakeDialog")).default;
    const ReceiptReviewPanel = (await import("@/components/business-app/ReceiptReviewPanel")).default;
    const { ReceiptUploadQueue } = await import("@/components/business-app/receipt-upload-queue");

    setChosenGrant(null);
    const base = createFixtureBusinessDataSource({ chatAvailable: false });
    const i18n = i18next.createInstance();
    await i18n.init({
      lng: language ?? "en",
      resources: {
        en: { translation: english },
        "es-419": { translation: spanish },
      },
      interpolation: { escapeValue: false },
    });
    const source = {
      ...base,
      spaces: async () => [{ space_id: "own", name: "My business", grant_id: "own-grant", role: "owner" as const, capabilities: ["read", "prepare", "approve"], access_seen: true }],
      overview: async (from: string, to: string | null) => ({ ...await base.overview(from, to), totals: [], fiscal_totals: [], without_fiscal_totals: [] }),
    } satisfies Partial<BusinessDataSource>;
    const queue = new ReceiptUploadQueue(async () => { throw new Error("unused"); }, () => undefined);
    const host = document.createElement("div");
    document.body.appendChild(host);
    const rootNode = createRoot(host);
    await act(async () => {
      rootNode.render(
        <I18nextProvider i18n={i18n}>
          <BusinessConsentTestProvider accepted>
            <BusinessWorkspaceProvider source={source as never}>
              <BusinessOverviewPanel />
              <RecordExpenseDialog isOpen onClose={() => undefined} onRecorded={() => undefined} />
              <ReceiptIntakeDialog target="inbox" queue={queue} onClose={() => undefined} onReview={() => undefined} />
              <ReceiptReviewPanel target={{ kind: "receipt", id: "rcpt-ferreteria" }} />
            </BusinessWorkspaceProvider>
          </BusinessConsentTestProvider>
        </I18nextProvider>,
      );
    });
    const text = () => document.body.textContent ?? "";
    const ready = () => ["Abrir la bandeja", "Subir recibos", "Registrar gasto", "Pagado desde"].every((item) => text().includes(item));
    for (let i = 0; i < 80 && !ready(); i += 1) {
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
    }
    const visible = text();
    for (const spanishText of [
      "Mi negocio",
      "Abrir la bandeja",
      "Gastos reales",
      "Todavía no hay gastos guardados en este período.",
      "Con valor fiscal",
      "Ninguno con valor fiscal en este período.",
      "Subir recibos",
      "Registrar gasto",
      "Comercio",
      "Fecha",
      "Categoría",
      "Moneda",
      "Pagado desde",
    ]) {
      assert.ok(visible.includes(spanishText), spanishText);
    }
    for (const englishText of ["Upload receipts", "My business", "Record expense", "Open inbox", "Actual expenses", "Merchant", "Paid from"]) {
      assert.equal(visible.includes(englishText), false, englishText);
    }
    assert.equal(document.documentElement.lang, "es");
    assert.equal(window.navigator.language, "en-US");
    await act(async () => rootNode.unmount());
  });
});
