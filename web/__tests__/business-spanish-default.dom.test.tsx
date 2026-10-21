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
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});

afterAll(async () => {
  await GlobalRegistrator.unregister();
});

describe("the device remembers what the shell shows", () => {
  test("a language change updates the document and the device, and the next start reads it back", async () => {
    const { rememberShownLanguage, resolveLanguage, browserLanguageSources } = await import("@/lib/language-features");
    window.localStorage.removeItem("i18nextLng");
    assert.equal(resolveLanguage(browserLanguageSources(), true, true), "es-419");
    rememberShownLanguage("en");
    assert.equal(window.localStorage.getItem("i18nextLng"), "en");
    assert.equal(resolveLanguage(browserLanguageSources(), true, true), "en");
    assert.equal(resolveLanguage({ ...browserLanguageSources(), account: "es-419" }, true, true), "es-419");
    window.localStorage.removeItem("i18nextLng");
  });

  test("the provider writes the device on every language change", () => {
    const provider = readFileSync(join(root, "components/I18nProvider.tsx"), "utf-8");
    const onChange = provider.slice(provider.indexOf("const syncDocumentLanguage"), provider.indexOf("const handleInitialized"));
    assert.match(onChange, /rememberShownLanguage\(shown\)/);
    assert.match(provider, /i18n\.on\('languageChanged', syncDocumentLanguage\)/);
  });
});

describe("Business stays in Spanish for an en-US browser", () => {
  test("the shell and the document language are set in one place each", () => {
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

  async function renderShown(language: "es-419" | "en", readyText: string[]): Promise<string> {
    const { act } = await import("react");
    const { createRoot } = await import("react-dom/client");
    const i18next = (await import("i18next")).default;
    const { I18nextProvider } = await import("react-i18next");
    const { BusinessWorkspaceProvider } = await import("@/components/business-app/BusinessWorkspace");
    const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
    const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
    const { setChosenGrant } = await import("@/lib/business-grant");
    const BusinessOverviewPanel = (await import("@/components/business-app/BusinessOverviewPanel")).default;
    const ReceiptIntakeDialog = (await import("@/components/business-app/ReceiptIntakeDialog")).default;
    const ReceiptReviewPanel = (await import("@/components/business-app/ReceiptReviewPanel")).default;
    const { ReceiptUploadQueue } = await import("@/components/business-app/receipt-upload-queue");
    const { useChatWorkspace } = await import("@/components/chat/ChatWorkspace");
    function BusinessMark() {
      const workspace = useChatWorkspace();
      return <header>{workspace?.sidebarHeader?.({ currentView: "workspace", conversationId: null, isBelowTablet: false, sidebarCollapsed: false, showWorkspace: () => undefined, newChat: () => undefined, prepareQuestion: () => undefined } as never)}</header>;
    }

    setChosenGrant(null);
    const base = createFixtureBusinessDataSource({ chatAvailable: false });
    const i18n = i18next.createInstance();
    await i18n.init({
      lng: language,
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
              <BusinessMark />
              <BusinessOverviewPanel />
              <ReceiptIntakeDialog target="inbox" queue={queue} onClose={() => undefined} onReview={() => undefined} />
              <ReceiptReviewPanel target={{ kind: "receipt", id: "rcpt-ferreteria" }} />
            </BusinessWorkspaceProvider>
          </BusinessConsentTestProvider>
        </I18nextProvider>,
      );
    });
    const text = () => document.body.textContent ?? "";
    const ready = () => readyText.every((item) => text().includes(item));
    for (let i = 0; i < 80 && !ready(); i += 1) {
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
    }
    const visible = text();
    await act(async () => rootNode.unmount());
    host.remove();
    return visible;
  }

  const spanishCopy = ["Mi negocio", "Hola", "en la Bandeja", "Ingresos", "Agregar", "Escríbelo", "Se guardan como", "Compra", "Comercio", "Fecha"];
  const englishCopy = ["Welcome", "in the Inbox", "Income", "Add", "Write it", "Saved as", "Purchase", "Merchant", "Date"];
  const retiredEnglishCopy = ["Upload receipts", "Record expense", "Open inbox", "Actual expenses", "to review"];

  test("an en-US browser with a Spanish account sees overview, the Agregar sheet, and receipt review in Spanish", async () => {
    const visible = await renderShown("es-419", ["en la Bandeja", "Ingresos", "Agregar", "Escríbelo", "Comercio"]);
    for (const spanishText of spanishCopy) assert.ok(visible.includes(spanishText), spanishText);
    for (const englishText of [...englishCopy, ...retiredEnglishCopy]) assert.equal(visible.includes(englishText), false, englishText);
    assert.equal(window.navigator.language, "en-US");
  });

  test("an English account sees the same surfaces in English", async () => {
    const visible = await renderShown("en", ["in the Inbox", "Income", "Merchant", "Write it"]);
    for (const englishText of englishCopy) assert.ok(visible.includes(englishText), englishText);
    for (const spanishText of spanishCopy) assert.equal(visible.includes(spanishText), false, spanishText);
  });
});
