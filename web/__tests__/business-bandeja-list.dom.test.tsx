import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessCapture, ReceiptSummary } from "@/lib/business-api";
import type { BusinessDataSource } from "@/components/business-app/business-data";
import type { BusinessPanelState } from "@/components/business-app/BusinessWorkspace";

// The real workspace and panel router over the sample source. The sample's
// Bandeja holds Ferretería La Esquina and IMG_2209 as new since the last
// visit, Papelería Central to review, and IMG_2209 (unreadable), IMG_2215
// and colmado-oct with a problem.
let search = "";
mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(search),
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
  usePathname: () => "/biz",
}));

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 800, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

const unmounts: (() => Promise<void>)[] = [];
afterEach(async () => {
  while (unmounts.length) await unmounts.pop()!();
  document.body.innerHTML = "";
  search = "";
});

const NAMES = ["Ferretería La Esquina", "Papelería Central", "IMG_2209.jpg", "IMG_2215.jpg", "colmado-oct.jpg"];

const note = (draft_id: string, text: string, received_at: string): BusinessCapture =>
  ({ draft_id, version: 2, revision: 1, source_id: `${draft_id}-1`, text, received_at, review_state: "open" });

async function mount({ width = 800, overrides = () => ({}), panel }: { width?: number; overrides?: (fixture: BusinessDataSource) => Partial<BusinessDataSource>; panel?: BusinessPanelState } = {}) {
  (window as unknown as { happyDOM: { setViewport: (size: { width: number; height: number }) => void } }).happyDOM.setViewport({ width, height: 900 });
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const BusinessPanel = (await import("@/components/business-app/BusinessPanel")).default;
  const { setChosenGrant } = await import("@/lib/business-grant");
  const { clearToasts } = await import("@/components/business-app/foundation/toasts");
  setChosenGrant(null);
  // The toast store outlives a test file; another file's error toast must not show here.
  clearToasts();
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const fixture = createFixtureBusinessDataSource({ chatAvailable: true });
  const source = { ...fixture, captures: async () => [], ...overrides(fixture) };
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
          <BusinessWorkspaceProvider source={source as BusinessDataSource}>
            <Probe />
          </BusinessWorkspaceProvider>
        </BusinessConsentTestProvider>
      </I18nextProvider>,
    );
  });
  unmounts.push(() => act(async () => root.unmount()));
  const settle = async (done: () => boolean, what: string) => {
    for (let i = 0; i < 80; i += 1) {
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
      if (done()) return;
    }
    throw new Error(`timed out waiting for ${what}: ${document.body.textContent?.slice(0, 300)}`);
  };
  const segment = (key: "review" | "problem" | "all") => host.querySelector<HTMLButtonElement>(`[data-testid="bandeja-segments"] [data-segment="${key}"]`);
  const names = (within: ParentNode = host) => [...within.querySelectorAll<HTMLElement>('[data-testid="bandeja-row"], [data-testid="bandeja-note"]')]
    .map((row) => NAMES.find((name) => row.textContent?.includes(name)) ?? row.querySelector("span span span")?.textContent ?? "");
  const choose = async (key: "review" | "problem" | "all") => {
    await act(async () => segment(key)!.click());
    assert.equal(segment(key)?.getAttribute("aria-checked"), "true");
  };
  const open = (next: BusinessPanelState) => act(async () => api!.openPanel(next));
  if (panel) await open(panel);
  return { act, host, settle, segment, names, choose, open, api: () => api! };
}

const inboxReady = (page: Awaited<ReturnType<typeof mount>>) =>
  page.settle(() => page.host.querySelector('[data-testid="bandeja-row"]') !== null, "the Bandeja rows");

describe("the Bandeja segments", () => {
  test("Por revisar, Con problema and Todo each list their receipts, newest first, and show their counts", async () => {
    const page = await mount({ panel: { kind: "inbox" } });
    await inboxReady(page);
    assert.equal(page.segment("review")?.getAttribute("aria-checked"), "true", "Por revisar is the first view");
    assert.equal(page.segment("review")?.textContent, "Por revisar4");
    assert.equal(page.segment("problem")?.textContent, "Con problema3");
    assert.equal(page.segment("all")?.textContent, "Todo");
    assert.deepEqual(page.names(), ["Ferretería La Esquina", "Papelería Central", "IMG_2215.jpg", "colmado-oct.jpg"]);
    await page.choose("problem");
    assert.deepEqual(page.names(), ["IMG_2209.jpg", "IMG_2215.jpg", "colmado-oct.jpg"]);
    await page.choose("all");
    assert.deepEqual(page.names(), ["Ferretería La Esquina", "IMG_2209.jpg", "Papelería Central", "IMG_2215.jpg", "colmado-oct.jpg"]);
  });

  test("a segment with nothing in it says so and Ver todo shows every receipt", async () => {
    const page = await mount({
      panel: { kind: "inbox" },
      overrides: (fixture) => ({
        receiptPage: async (view) => {
          const shown = await fixture.receiptPage!(view);
          return { ...shown, items: shown.items.filter((item) => item.status !== "needs_attention") };
        },
      }),
    });
    await inboxReady(page);
    await page.choose("problem");
    const empty = page.host.querySelector('[data-testid="bandeja-segment-empty"]');
    assert.equal(empty?.querySelector("h3")?.textContent, "Ningún recibo con problemas");
    const all = [...(empty?.querySelectorAll("button") ?? [])].find((button) => button.textContent === "Ver todo");
    assert.ok(all, "Ver todo");
    await page.act(async () => all.click());
    assert.equal(page.segment("all")?.getAttribute("aria-checked"), "true");
    assert.deepEqual(page.names(), ["Ferretería La Esquina", "Papelería Central"]);
  });
});

describe("new since the last visit", () => {
  test("receipts the server marks unread sit under Nuevo desde tu última visita, the rest under Antes", async () => {
    const page = await mount({ panel: { kind: "inbox" } });
    await inboxReady(page);
    await page.choose("all");
    const fresh = page.host.querySelector('[data-testid="bandeja-new"]')!;
    const earlier = page.host.querySelector('[data-testid="bandeja-earlier"]')!;
    assert.equal(fresh.querySelector("h3")?.textContent, "Nuevo desde tu última visita");
    assert.equal(earlier.querySelector("h3")?.textContent, "Antes");
    assert.deepEqual(page.names(fresh), ["Ferretería La Esquina", "IMG_2209.jpg"]);
    assert.deepEqual(page.names(earlier), ["Papelería Central", "IMG_2215.jpg", "colmado-oct.jpg"]);
    assert.ok(fresh.compareDocumentPosition(earlier) & Node.DOCUMENT_POSITION_FOLLOWING, "new comes first");
  });

  test("with nothing new there is one list and no group headings", async () => {
    const page = await mount({
      panel: { kind: "inbox" },
      overrides: (fixture) => ({
        receiptPage: async (view) => {
          const shown = await fixture.receiptPage!(view);
          return { ...shown, items: shown.items.map((item): ReceiptSummary => ({ ...item, activity: item.activity ? { ...item.activity, unread: false } : item.activity })) };
        },
      }),
    });
    await inboxReady(page);
    assert.equal(page.host.querySelector('[data-testid="bandeja-new"]'), null);
    assert.equal(page.host.querySelector('[data-testid="business-inbox-receipts"] h3'), null);
    assert.deepEqual(page.names(page.host.querySelector('[data-testid="bandeja-earlier"]')!), ["Ferretería La Esquina", "Papelería Central", "IMG_2215.jpg", "colmado-oct.jpg"]);
  });
});

describe("typed notes in the list", () => {
  const NOTES = [
    note("draft-a", "Ayer compré pintura para el taller.", "2000-01-02T14:00:00Z"),
    note("draft-a", "Pagué con mi dinero.", "2000-01-02T15:30:00Z"),
  ];

  test("an open note is a Por revisar row with its latest words and earlier count, never a problem, and opens its draft", async () => {
    const page = await mount({ panel: { kind: "inbox" }, overrides: () => ({ captures: async () => NOTES }) });
    await page.settle(() => page.host.querySelector('[data-testid="bandeja-note"]') !== null, "the note row");
    assert.equal(page.segment("review")?.textContent, "Por revisar5");
    const row = page.host.querySelector('[data-testid="bandeja-note"]')!;
    assert.ok(row.textContent?.includes("Pagué con mi dinero."));
    assert.ok(!row.textContent?.includes("Ayer compré pintura"), "one row per draft, its latest note");
    assert.match(row.textContent ?? "", /Nota escrita · .+ · 1 nota anterior/);
    assert.equal(page.names().at(-1), "Pagué con mi dinero.", "the oldest row sits last");
    await page.choose("problem");
    assert.equal(page.host.querySelector('[data-testid="bandeja-note"]'), null);
    await page.choose("all");
    await page.act(async () => page.host.querySelector<HTMLButtonElement>('[data-testid="bandeja-note"] button')!.click());
    assert.deepEqual(page.api().panel, { kind: "draft", draftId: "draft-a", list: "inbox" });
  });

  test("a notes outage says so above the receipts it still lists", async () => {
    const page = await mount({ panel: { kind: "inbox" }, overrides: () => ({ captures: async () => { throw new Error("offline"); } }) });
    await page.settle(() => page.host.querySelector('[role="alert"]') !== null, "the notes alert");
    assert.equal(page.host.querySelector('[role="alert"]')?.textContent, "No pudimos cargar tus notas");
    assert.equal(page.host.querySelector('[data-testid="bandeja-note"]'), null);
    assert.equal(page.names().length, 4);
  });

  test("a full page of notes says it shows the latest ones", async () => {
    const many = Array.from({ length: 50 }, (_, index) => note(`draft-${index}`, `Nota ${index}`, `2000-01-01T00:${String(index).padStart(2, "0")}:00Z`));
    const page = await mount({ panel: { kind: "inbox" }, overrides: () => ({ captures: async () => many }) });
    await page.settle(() => page.host.querySelector('[data-testid="bandeja-note"]') !== null, "the note rows");
    assert.ok(page.host.textContent?.includes("Se muestran las últimas 50 notas guardadas."));
  });
});

describe("email behind Ver correos", () => {
  test("Ver correos opens the receiving address and the received emails in one sheet, and Cerrar puts them away", async () => {
    const page = await mount({ panel: { kind: "inbox" } });
    await inboxReady(page);
    assert.equal(document.querySelector('[data-testid="bandeja-emails"]'), null);
    const button = page.host.querySelector<HTMLButtonElement>('[data-testid="bandeja-open-emails"]')!;
    assert.equal(button.textContent, "Ver correos");
    await page.act(async () => button.click());
    await page.settle(() => document.querySelector('[data-testid="bandeja-emails"] [data-testid="email-address"]') !== null, "the email sheet");
    const sheet = document.querySelector('[data-testid="bandeja-emails"]')!;
    assert.equal(sheet.querySelector('[data-testid="email-copy-address"]')?.textContent, "Copiar dirección");
    const received = sheet.querySelector('section[aria-labelledby="email-received-title"]');
    assert.equal(received && document.getElementById(received.getAttribute("aria-labelledby")!)?.textContent, "Correos recibidos", "the received emails are in the sheet");
    const close = [...document.querySelectorAll<HTMLButtonElement>("button")].find((item) => item.getAttribute("aria-label") === "Cerrar" || item.textContent === "Cerrar");
    assert.ok(close, "Cerrar");
    await page.act(async () => close.click());
    await page.settle(() => document.querySelector('[data-testid="bandeja-emails"]') === null, "the sheet to close");
  });

  test("a link to one email opens the Bandeja with the email sheet already open", async () => {
    const page = await mount({ panel: { kind: "inbox", emailId: "delivery-1" } });
    await page.settle(() => document.querySelector('[data-testid="bandeja-emails"]') !== null, "the email sheet");
    assert.equal(page.api().panel.kind, "inbox");
  });
  test("on a desktop, See the first email from a record in the tray opens the email sheet over the Bandeja", async () => {
    const page = await mount({ width: 1280, panel: { kind: "inbox" } });
    await inboxReady(page);
    await page.open({ kind: "receipt", receiptId: "rcpt-papeleria", list: "inbox" });
    await page.settle(() => document.querySelector('[data-testid="side-drawer"]') !== null, "the record tray");
    await page.open({ kind: "inbox", emailId: "delivery-1" });
    await page.settle(() => document.querySelector('[data-testid="bandeja-emails"]') !== null, "the email sheet");
  });
});

test("an old Novedades link lands on the Bandeja", async () => {
  search = "view=updates";
  const page = await mount();
  await inboxReady(page);
  assert.equal(page.api().panel.kind, "inbox");
  assert.equal(page.host.querySelector("h2")?.textContent, "Bandeja");
  assert.equal(document.body.textContent?.includes("Novedades"), false);
});
