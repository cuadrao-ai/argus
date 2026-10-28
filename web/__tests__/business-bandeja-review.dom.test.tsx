import assert from "node:assert/strict";
import { afterAll, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ReceiptActivityCounts, ReceiptSummary } from "@/lib/business-api";
import type { BusinessDataSource } from "@/components/business-app/business-data";
import { receptionRows, rowState, rowTitles, receptionTab, tabCount } from "./support/reception";

let search = "";
mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(search),
  useRouter: () => ({ push() {}, replace() {} }),
  usePathname: () => "/biz",
}));

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { configurable: true, writable: true, value: true });
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

const none: ReceiptActivityCounts = { reading_count: 0, unread_count: 0, presentation: "none", pending_review_count: 0, needs_attention_count: 0, ready_to_review_count: 0 };

// A desktop shell's top bar, which holds the one Agregar on every Business screen but Negocio.
const DESKTOP_SHELL = { currentView: "workspace", conversationId: null, isBelowTablet: false, sidebarCollapsed: false, showWorkspace: () => undefined, newChat: () => undefined, prepareQuestion: () => undefined, openSearch: undefined };

async function mount(overrides: Partial<BusinessDataSource> = {}, grant: string | null = null, { bar = false }: { bar?: boolean } = {}) {
  search = bar ? "view=inbox" : "";
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { setChosenGrant } = await import("@/lib/business-grant");
  const BusinessInboxPanel = (await import("@/components/business-app/BusinessInboxPanel")).default;
  const { useChatWorkspace } = await import("@/components/chat/ChatWorkspace");
  setChosenGrant(grant);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const fixture = createFixtureBusinessDataSource({ chatAvailable: false });
  const source = { ...fixture, captures: async () => ({ items: [] }), emailDeliveries: async () => [], ...overrides };
  let panel = "";
  function Probe() {
    const business = useBusiness();
    panel = business.panel.kind === "receipt" ? business.panel.receiptId : business.panel.kind;
    return <BusinessInboxPanel />;
  }
  function Bar() {
    const workspace = useChatWorkspace();
    return <header data-testid="top-bar">{workspace?.headerSearch?.(DESKTOP_SHELL as never)}</header>;
  }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessConsentTestProvider accepted>
          <BusinessWorkspaceProvider source={source as BusinessDataSource}>
            {bar ? <Bar /> : null}
            <Probe />
          </BusinessWorkspaceProvider>
        </BusinessConsentTestProvider>
      </I18nextProvider>,
    );
  });
  const settle = async (done: () => boolean) => {
    for (let i = 0; i < 40; i += 1) {
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 50)); });
      if (done()) return;
    }
    assert.fail(`the inbox did not settle: ${host.textContent?.slice(0, 240)}`);
  };
  return {
    act,
    host,
    settle,
    panel: () => panel,
    close: async () => { await act(async () => { root.unmount(); }); host.remove(); setChosenGrant(null); search = ""; },
  };
}

test("a Bandeja that has never been used says so and offers Agregar", async () => {
  const page = await mount({
    receiptPage: async () => ({ items: [], activity: none }),
  }, null, { bar: true });
  try {
    await page.settle(() => page.host.querySelector('[data-testid="reception-empty"]') !== null);
    const card = page.host.querySelector('[data-testid="reception-empty"]')!;
    assert.equal(card.getAttribute("data-empty-kind"), "first_run");
    assert.equal(card.querySelector("h3")?.textContent, "Tus archivos y notas llegan aquí");
    // On a wide screen the one Agregar lives in the top bar; the Bandeja toolbar does not repeat it.
    assert.equal(page.host.querySelector("[data-testid=top-bar] [data-testid=add-menu-header] [data-testid=business-primary-upload]")?.textContent, "Agregar", "the empty Bandeja offers Agregar");
    assert.equal(page.host.querySelectorAll("[data-testid=business-primary-upload]").length, 1, "Agregar is offered once");
  } finally { await page.close(); }
});

test("a Bandeja whose receipts were all approved, dismissed, or counted by an older server reads the same plain empty state", async () => {
  for (const activity of [{ ...none, confirmed_count: 3, dismissed_count: 0 }, { ...none, confirmed_count: 2, dismissed_count: 1 }, none]) {
    const page = await mount({ receiptPage: async () => ({ items: [], activity }) });
    try {
      await page.settle(() => page.host.querySelector('[data-testid="reception-empty"]') !== null);
      assert.equal(page.host.querySelector("h3")?.textContent, "Tus archivos y notas llegan aquí");
    } finally { await page.close(); }
  }
});

test("still-reading and unreadable receipts stay off the por revisar number", async () => {
  const fixture = (await import("@/components/business-app/fixture-data")).createFixtureBusinessDataSource();
  const ready = await fixture.receipt("rcpt-ferreteria");
  const blurry = await fixture.receipt("rcpt-blurry");
  const reading: ReceiptSummary = { ...ready, id: "rcpt-reading", status: "queued", merchant: "En lectura", activity: { state: "reading", unread: true, completion_cursor: null }, bandeja: { por_revisar: false, con_problema: false, leyendo: true } };
  const items = [ready, reading, blurry];
  const page = await mount({
    receiptPage: async () => ({ items, activity: { ...none, pending_review_count: 3, reading_count: 1, needs_attention_count: 1, ready_to_review_count: 1 } }),
  });
  try {
    await page.settle(() => /\d/.test(tabCount(page.host, "review") ?? ""));
    assert.deepEqual([tabCount(page.host, "review"), tabCount(page.host, "processing"), tabCount(page.host, "attention")], ["1", "1", "1"]);
    assert.equal(page.host.textContent?.includes("necesita tu atención"), false);
    assert.match(page.host.textContent ?? "", /Ferretería/);
    assert.equal((page.host.textContent ?? "").includes("DOP"), false);
  } finally { await page.close(); }
});

test("each view lists what the server flags, and a queued receipt the server is not reading never says Leyendo", async () => {
  const fixture = (await import("@/components/business-app/fixture-data")).createFixtureBusinessDataSource();
  const ready = await fixture.receipt("rcpt-ferreteria");
  const flags = (por_revisar: boolean, con_problema: boolean, leyendo: boolean) => ({ por_revisar, con_problema, leyendo });
  const queued: ReceiptSummary = { ...ready, id: "rcpt-queued", status: "queued", merchant: "En cola", activity: { state: "saved_unread", unread: false, completion_cursor: null }, bandeja: flags(false, false, false) };
  const flaggedProblem: ReceiptSummary = { ...ready, id: "rcpt-flagged", merchant: "Marcado", activity: { state: "ready", unread: false, completion_cursor: null }, bandeja: flags(false, true, false) };
  const page = await mount({
    receiptPage: async () => ({ items: [queued, flaggedProblem], activity: { ...none, pending_review_count: 2, needs_attention_count: 1 } }),
  });
  const choose = (key: "all" | "review" | "processing" | "attention") => page.act(async () => receptionTab(page.host, key)!.click());
  try {
    await page.settle(() => receptionRows(page.host).length === 2);
    await choose("review");
    assert.deepEqual(rowTitles(page.host), [], "neither row is flagged por revisar");
    assert.equal(page.host.querySelector('[data-testid="reception-empty"]')?.getAttribute("data-empty-kind"), "filtered");
    await choose("attention");
    assert.deepEqual(rowTitles(page.host), ["Marcado"]);
    await choose("all");
    assert.deepEqual(rowTitles(page.host).sort(), ["En cola", "Marcado"]);
    const row = receptionRows(page.host).find((item) => item.textContent?.includes("En cola"))!;
    assert.match(rowState(row), /^Guardado, sin leer/);
    assert.equal(row.textContent?.includes("Leyendo"), false);
  } finally { await page.close(); }
});

test("a contador gets Revisar recibos as the green primary and no upload", async () => {
  const page = await mount({}, "fixture-grant-client");
  try {
    await page.settle(() => page.host.querySelector('[data-testid="business-primary-review"]') !== null);
    const review = page.host.querySelector('[data-testid="business-primary-review"]') as HTMLButtonElement;
    assert.equal(review.textContent, "Revisar recibos");
    assert.equal(review.className.includes("bg-[var(--cuadrao-green)]"), true);
    assert.equal(page.host.querySelector('[data-testid="business-primary-upload"]'), null);
    assert.equal([...page.host.querySelectorAll("button")].some((button) => button.textContent?.trim() === "Subir recibo"), false);
    await page.act(async () => { review.click(); });
    assert.equal(page.panel(), "rcpt-ferreteria");
  } finally { await page.close(); }
});

test("the views stay while the list loads, with no count until one is known", async () => {
  const page = await mount({ receiptPage: () => new Promise(() => {}) });
  try {
    await page.settle(() => page.host.querySelector('[role="tablist"]') !== null);
    const bar = page.host.querySelector('[role="tablist"]')?.textContent ?? "";
    assert.match(bar, /Por revisar/);
    assert.equal(/\d/.test(bar), false, "an unknown count is never shown as 0");
  } finally { await page.close(); }
});
