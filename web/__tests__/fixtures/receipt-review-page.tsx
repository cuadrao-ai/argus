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

export async function mount(overrides: (fixture: BusinessDataSource) => Partial<BusinessDataSource> = () => ({}), userId?: string) {
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
  const { useRunReviewShortcut } = await import("@/components/business-app/BusinessReviewShortcuts");
  let api: ReturnType<typeof useBusiness> | null = null;
  let shortcut: ReturnType<typeof useRunReviewShortcut> = () => false;
  function Probe() {
    api = useBusiness();
    shortcut = useRunReviewShortcut();
    return <BusinessPanel />;
  }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessConsentTestProvider accepted>
          <BusinessWorkspaceProvider source={source as never} userId={userId}>
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
  /** Runs a review shortcut the way the workspace's key handler does; false when the page offers none. */
  const runShortcut = (id: Parameters<typeof shortcut>[0]) => shortcut(id);
  return { act, root, host, wait, open, frame, source, i18n, api: () => api!, runShortcut };
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
  await page.open({ kind: "draft", draftId: dossierFixtureIds[id] }, () => Boolean(page.host.querySelector('[data-testid="receipt-current-facts"]') && page.host.querySelector('[data-testid="fiscal-declaration"]')));
  const row = (name: string) => page.host.querySelector<HTMLElement>(`[data-fact="${name}"]`)!;
  // A row opens from its value. The status slot before it can hold a button of its own.
  const open = async (name: string) => page.act(async () => (row(name).querySelector<HTMLButtonElement>("button[data-row-value]") ?? row(name).querySelector<HTMLButtonElement>("button"))!.click());
  const leave = (selector: string) => page.act(async () => { page.host.querySelector<HTMLElement>(selector)!.blur(); await new Promise((resolve) => setTimeout(resolve, 10)); });
  const action = (name: string, label: "Guardar" | "Cancelar") => row(name).querySelector<HTMLButtonElement>(`button[aria-label^="${label} · "]`)!;
  const check = (name: string) => page.act(async () => action(name, "Guardar").click());
  const dismiss = (name: string) => page.act(async () => action(name, "Cancelar").click());
  const press = (selector: string, key: string) => page.act(async () => { page.host.querySelector(selector)!.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true })); });
  return { ...page, writes, approvals: () => approvals, row, openRow: open, leave, action, check, dismiss, press, close: () => page.act(async () => page.root.unmount()) };
}

export async function fill(page: { host: ParentNode; act: (run: () => Promise<void>) => Promise<void> }, selector: string, value: string, element: typeof HTMLInputElement | typeof HTMLSelectElement | typeof HTMLTextAreaElement = HTMLInputElement) {
  const input = page.host.querySelector<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>(selector);
  assert.ok(input, selector);
  await page.act(async () => {
    input.focus();
    Object.getOwnPropertyDescriptor(element.prototype, "value")!.set!.call(input, value);
    input.dispatchEvent(new Event(element === HTMLSelectElement ? "change" : "input", { bubbles: true }));
  });
}


/** The server waits on the record's kind: the one state in which a purchase shows Compra/Venta. */
export const kindAsked = (dossier: Dossier) => { dossier.questions = [{ id: "question-kind", draft_id: dossier.draft_id, field: "kind", asked_of: "accountant", channel: "web", state: "open", prompt: "", allowed_answers: ["known"], answer_source_id: null, created_at: "2026-10-10T14:22:00Z" }]; };

type Host = { host: ParentNode; act: (run: () => Promise<void>) => Promise<void> };

/** Opens a pick row's list, as a press on the row does, and returns its options. */
export async function openList(page: Host, name: string) {
  const trigger = page.host.querySelector<HTMLButtonElement>(`[data-fact="${name}"] button[aria-haspopup="listbox"]`);
  assert.ok(trigger, `${name} opens no list`);
  if (trigger.getAttribute("aria-expanded") !== "true") await page.act(async () => trigger.click());
  return [...page.host.querySelectorAll<HTMLButtonElement>(`[data-fact="${name}"] [role="option"]`)];
}

/** Picks one option of a pick row. The pick saves at once: the row has no check. */
export async function pick(page: Host, name: string, value: string) {
  const option = (await openList(page, name)).find((item) => item.dataset.value === value);
  assert.ok(option, `${name} offers no ${value}`);
  await page.act(async () => option.click());
}
