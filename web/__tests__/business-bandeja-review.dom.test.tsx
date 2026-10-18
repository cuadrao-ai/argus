import assert from "node:assert/strict";
import { afterAll, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ReceiptActivityCounts, ReceiptSummary } from "@/lib/business-api";
import type { BusinessDataSource } from "@/components/business-app/business-data";

mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ push() {}, replace() {} }),
  usePathname: () => "/biz",
}));

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { configurable: true, writable: true, value: true });
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

const none: ReceiptActivityCounts = { reading_count: 0, unread_count: 0, presentation: "none", pending_review_count: 0, needs_attention_count: 0 };

async function mount(overrides: Partial<BusinessDataSource> = {}, grant: string | null = null) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { setChosenGrant } = await import("@/lib/business-grant");
  const BusinessInboxPanel = (await import("@/components/business-app/BusinessInboxPanel")).default;
  setChosenGrant(grant);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const fixture = createFixtureBusinessDataSource({ chatAvailable: false });
  const source = { ...fixture, captures: async () => [], ...overrides };
  let panel = "";
  function Probe() {
    const business = useBusiness();
    panel = business.panel.kind === "receipt" ? business.panel.receiptId : business.panel.kind;
    return <BusinessInboxPanel />;
  }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessWorkspaceProvider source={source as BusinessDataSource}>
          <Probe />
        </BusinessWorkspaceProvider>
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
    close: async () => { await act(async () => { root.unmount(); }); host.remove(); setChosenGrant(null); },
  };
}

test("a Bandeja that has never been used keeps the plain empty copy", async () => {
  const page = await mount({
    receiptPage: async () => ({ items: [], activity: none }),
  });
  try {
    await page.settle(() => page.host.querySelector('[data-testid="business-inbox-empty"]') !== null);
    const empty = page.host.querySelector('[data-testid="business-inbox-empty"]')?.textContent ?? "";
    assert.equal(empty.includes("Todo aprobado"), false);
    assert.equal(empty.includes("Sube un recibo"), true);
  } finally { await page.close(); }
});

test("an approved Bandeja reads the locked empty line", async () => {
  const fixture = (await import("@/components/business-app/fixture-data")).createFixtureBusinessDataSource();
  const confirmed = { ...(await fixture.receipt("rcpt-confirmed")), status: "confirmed" as const };
  const page = await mount({
    receiptPage: async (view) => ({ items: view === "all" ? [confirmed] : [], activity: none }),
  });
  try {
    await page.settle(() => (page.host.textContent ?? "").includes("Todo aprobado. Pa'que cuadre."));
    assert.equal(page.host.textContent?.includes("Todo aprobado. Pa'que cuadre."), true);
  } finally { await page.close(); }
});

test("still-reading and unreadable receipts stay off the por revisar number", async () => {
  const fixture = (await import("@/components/business-app/fixture-data")).createFixtureBusinessDataSource();
  const ready = await fixture.receipt("rcpt-ferreteria");
  const blurry = await fixture.receipt("rcpt-blurry");
  const reading: ReceiptSummary = { ...ready, id: "rcpt-reading", status: "queued", read_pending: true, merchant: "En lectura", activity: { state: "reading", unread: true, completion_cursor: null } };
  const items = [ready, reading, blurry];
  const page = await mount({
    receiptPage: async (view) => ({ items: view === "all" ? items : items, activity: { ...none, pending_review_count: 3, reading_count: 1, needs_attention_count: 1 } }),
  });
  try {
    await page.settle(() => page.host.querySelector('[data-testid="bandeja-por-revisar"]') !== null);
    assert.equal(page.host.querySelector('[data-testid="bandeja-por-revisar"]')?.textContent, "1 por revisar");
    assert.equal(page.host.querySelector('[data-testid="bandeja-aside"]')?.textContent, "1 todavía leyéndose. 1 no se pudo leer.");
    assert.equal(page.host.textContent?.includes("necesita tu atención"), false);
    assert.equal(/Revisar \d+ recibo/.test(page.host.textContent ?? ""), false);
    assert.match(page.host.textContent ?? "", /RD\$/);
    assert.equal((page.host.textContent ?? "").includes("DOP"), false);
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
