import assert from "node:assert/strict";
import { afterAll, beforeAll, mock } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ReceiptDetail } from "@/lib/business-api";
import type { BusinessDataSource } from "@/components/business-app/business-data";

export function registerReceiptReviewPage() {
  beforeAll(() => {
    mock.module("next/navigation", () => ({
      useSearchParams: () => new URLSearchParams(""),
      useRouter: () => ({ push: () => undefined, replace: () => undefined }),
      usePathname: () => "/biz",
    }));
    GlobalRegistrator.register({ url: "http://localhost/biz", width: 800, height: 900 });
    (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  });
  afterAll(async () => { await GlobalRegistrator.unregister(); });
}

export async function mount(overrides: (fixture: BusinessDataSource) => Partial<BusinessDataSource> = () => ({})) {
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

export function button(host: Element, text: string) {
  const found = [...host.querySelectorAll<HTMLButtonElement>("button")].find((item) => item.textContent === text);
  assert.ok(found, `missing button ${text}`);
  return found;
}

export type Dossier = Awaited<ReturnType<BusinessDataSource["dossier"]>>;

/** A review page over the sample's own server, with every write it sends kept in order. */
export async function setup(id: keyof typeof import("@/components/business-app/dossier-fixtures").dossierFixtureIds = "fiscal", change: (dossier: Dossier) => void = () => undefined, overrides: (fixture: BusinessDataSource) => Partial<BusinessDataSource> = () => ({})) {
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

export async function fill(page: { host: Element; act: (run: () => Promise<void>) => Promise<void> }, selector: string, value: string, element: typeof HTMLInputElement | typeof HTMLSelectElement = HTMLInputElement) {
  const input = page.host.querySelector<HTMLInputElement>(selector);
  assert.ok(input, selector);
  await page.act(async () => {
    input.focus();
    Object.getOwnPropertyDescriptor(element.prototype, "value")!.set!.call(input, value);
    input.dispatchEvent(new Event(element === HTMLSelectElement ? "change" : "input", { bubbles: true }));
  });
}

