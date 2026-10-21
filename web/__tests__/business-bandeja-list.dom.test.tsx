import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessCapture, ReceiptSummary } from "@/lib/business-api";
import type { BusinessDataSource } from "@/components/business-app/business-data";
import type { BusinessPanelState } from "@/components/business-app/BusinessWorkspace";

// The real workspace and panel router over the sample source. The sample's
// Bandeja holds Ferretería La Esquina and IMG_2209 as new since the last
// visit, Papelería Central to review, and IMG_2209 (unreadable), IMG_2215
// and colmado-oct with a problem. colmado-oct arrived by email.
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
    const page = await mount({ panel: { kind: "inbox" }, overrides: () => ({ emailDeliveries: async () => [] }) });
    await inboxReady(page);
    assert.equal(page.segment("review")?.getAttribute("aria-checked"), "true", "Por revisar is the first view");
    assert.equal(page.segment("review")?.textContent, "Por revisar4");
    await page.settle(() => page.segment("problem")?.textContent === "Con problema3", "the problem count");
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
        emailDeliveries: async () => [],
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

describe("emails in the Bandeja", () => {
  // The sample's emails: the ferretería's and the colmado's each saved a receipt, the gas station's is still
  // being read, the boletín's zip could not be saved, and the farmacia's hit an inactive address and can be retried.
  const emailRows = (page: { host: HTMLElement }) => [...page.host.querySelectorAll<HTMLElement>('[data-testid="bandeja-email"]')];
  const emailRow = (page: { host: HTMLElement }, sender: string) => emailRows(page).find((row) => row.textContent?.includes(sender));
  const emailDetail = () => document.querySelector('[data-testid="email-detail"]');

  test("the segments are Por revisar, Con problema and Todo; nothing is called Correos", async () => {
    const page = await mount({ panel: { kind: "inbox" } });
    await inboxReady(page);
    const segments = [...page.host.querySelectorAll<HTMLElement>('[data-testid="bandeja-segments"] [data-segment]')];
    assert.deepEqual(segments.map((segment) => segment.dataset.segment), ["review", "problem", "all"]);
    assert.equal(page.host.querySelector('[data-testid="bandeja-emails"]'), null);
  });

  test("an email that brought no receipt is a Con problema row with its sender, its subject in quotes and why, and Reintentar only when the server allows it", async () => {
    const page = await mount({ panel: { kind: "inbox" } });
    await inboxReady(page);
    await page.settle(() => page.segment("problem")?.textContent === "Con problema5", "the problem count with the two emails");
    await page.choose("problem");
    assert.deepEqual(page.names(), ["IMG_2209.jpg", "IMG_2215.jpg", "colmado-oct.jpg"], "the receipt rows are unchanged");
    assert.equal(emailRows(page).length, 2);
    const boletin = emailRow(page, "noticias@proveedor.example")!;
    assert.match(boletin.textContent ?? "", /Correo de noticias@proveedor\.example/);
    assert.match(boletin.textContent ?? "", /“Boletín semanal” · Este tipo de archivo no se puede guardar como recibo · /);
    assert.equal([...boletin.querySelectorAll("button")].some((button) => button.textContent === "Reintentar"), false, "not retryable");
    const farmacia = emailRow(page, "facturas@farmaciacarol.example")!;
    assert.match(farmacia.textContent ?? "", /“Factura Farmacia Carol” · Esta dirección no está activa · /);
    assert.ok([...farmacia.querySelectorAll("button")].some((button) => button.textContent === "Reintentar"), "a retryable email offers Reintentar on its row");
  });

  test("Todo lists every email that brought no receipt beside the receipts, and an email whose file became a receipt is no row of its own", async () => {
    const page = await mount({ panel: { kind: "inbox" } });
    await inboxReady(page);
    await page.choose("all");
    await page.settle(() => emailRows(page).length === 3, "the three email rows");
    assert.deepEqual(page.names().length, 5, "the five receipts stay");
    assert.equal(emailRow(page, "ventas@ferreterialaesquina.example"), undefined, "the ferretería's email is its receipt");
    assert.equal(emailRow(page, "ventas@colmadoelprimo.example"), undefined, "the colmado's email is its receipt");
    assert.ok(emailRow(page, "facturas@estacion.example"), "the email still being read");
  });

  test("an email still being read waits under Todo like a receipt being read, so Por revisar lists exactly what it counts", async () => {
    const page = await mount({ panel: { kind: "inbox" } });
    await inboxReady(page);
    assert.equal(emailRows(page).length, 0, "Por revisar holds no reading email");
    await page.choose("all");
    await page.settle(() => emailRows(page).some((row) => row.dataset.standing === "reading"), "the reading email row");
    const reading = emailRows(page).find((row) => row.dataset.standing === "reading")!;
    assert.equal(reading.dataset.standing, "reading");
    assert.match(reading.textContent ?? "", /Correo de facturas@estacion\.example/);
    assert.match(reading.textContent ?? "", /“Recibo de combustible” · Leyendo…/);
    assert.ok(reading.querySelector('[data-testid="receipt-reading-ring"]'), "it reads like a receipt still being read");
    assert.equal(page.segment("review")?.textContent, "Por revisar4");
  });

  test("a repeat of a file already saved is never a problem row", async () => {
    const repeat = { id: "email-repeat", state: "captured" as const, received_at: "2026-10-13T17:14:00Z", updated_at: "2026-10-13T17:14:00Z", original_document_id: null, retryable: false, subject: "Factura otra vez", sender: "ventas@repetido.example", sent_at: null, error_code: null, parts: [{ id: "1.2", filename: "factura.pdf", media_type: "application/pdf", state: "captured" as const, document_id: "rcpt-papeleria", error_code: null, repeat_of_delivery_id: "email-ferreteria" }] };
    const uploaded = { ...repeat, id: "email-uploaded", sender: "ventas@subido.example", parts: [{ ...repeat.parts[0], repeat_of_delivery_id: null, repeat_of_upload: true }] };
    const page = await mount({ panel: { kind: "inbox" }, overrides: () => ({ emailDeliveries: async () => [repeat, uploaded] }) });
    await inboxReady(page);
    await page.settle(() => page.segment("problem")?.textContent === "Con problema3", "the problem count without emails");
    await page.choose("all");
    assert.equal(emailRows(page).length, 0);
  });

  test("on a desktop an email row opens the email beside the list, and the tray closes back to it", async () => {
    const page = await mount({ width: 1280, panel: { kind: "inbox" } });
    await inboxReady(page);
    await page.choose("problem");
    await page.settle(() => emailRow(page, "noticias@proveedor.example") !== undefined, "the boletín row");
    await page.act(async () => emailRow(page, "noticias@proveedor.example")!.querySelector("button")!.click());
    assert.deepEqual(page.api().panel, { kind: "email", emailId: "email-boletin" });
    await page.settle(() => emailDetail() !== null, "the email detail");
    assert.ok(emailDetail()!.closest('[data-testid="side-drawer"]'), "the email sits in the record tray");
    assert.ok(page.host.querySelector('[data-testid="bandeja-segments"]'), "the list stays beside it");
    assert.equal(emailRow(page, "noticias@proveedor.example")?.getAttribute("aria-current"), "true");
    assert.ok(emailDetail()!.textContent?.includes("boletin.zip"));
  });

  test("on a phone an email is the whole page with a way back to the Bandeja", async () => {
    const page = await mount({ width: 390, panel: { kind: "email", emailId: "email-boletin" } });
    await page.settle(() => emailDetail() !== null, "the email detail");
    assert.equal(document.querySelector('[data-testid="side-drawer"]'), null);
    assert.equal(page.host.querySelector('[data-testid="email-record"] h2')?.textContent, "Correo de noticias@proveedor.example");
    const back = [...page.host.querySelectorAll<HTMLButtonElement>('[data-testid="email-record"] button')].find((button) => button.textContent === "Bandeja");
    assert.ok(back, "a way back");
    await page.act(async () => back.click());
    assert.deepEqual(page.api().panel, { kind: "inbox" });
  });

  test("Reintentar on an email row asks the server again and says so", async () => {
    const retried: string[] = [];
    const page = await mount({ panel: { kind: "inbox" }, overrides: () => ({ retryEmailDelivery: async (id: string) => { retried.push(id); return { id }; } }) });
    await inboxReady(page);
    await page.choose("problem");
    await page.settle(() => emailRow(page, "facturas@farmaciacarol.example") !== undefined, "the farmacia row");
    const retry = [...emailRow(page, "facturas@farmaciacarol.example")!.querySelectorAll("button")].find((button) => button.textContent === "Reintentar")!;
    await page.act(async () => retry.click());
    await page.settle(() => retried.length === 1, "the retry request");
    assert.deepEqual(retried, ["email-farmacia"]);
    assert.equal(page.api().panel.kind, "inbox", "Reintentar does not open the email");
  });

  test("a receipt that arrived by email says Llegó por correo · Ver correo, and Ver correo opens that email beside the list", async () => {
    const page = await mount({ width: 1280, panel: { kind: "inbox" } });
    await inboxReady(page);
    await page.open({ kind: "receipt", receiptId: "rcpt-ambiguous", list: "inbox" });
    await page.settle(() => document.querySelector('[data-testid="receipt-source-channel"]') !== null, "the record's source");
    const channel = document.querySelector('[data-testid="receipt-source-channel"]')!;
    assert.equal(channel.textContent, "Llegó por correo · Ver correo");
    await page.act(async () => channel.querySelector("button")!.click());
    assert.deepEqual(page.api().panel, { kind: "email", emailId: "email-colmado" });
    await page.settle(() => emailDetail() !== null, "the email detail");
    assert.ok(emailDetail()!.closest('[data-testid="side-drawer"]'), "the same tray");
    assert.ok(emailDetail()!.textContent?.includes("colmado-oct.jpg"));
  });

  test("an old link to one email opens that email, and an old Correos link lands on Correo de recibos with its history", async () => {
    search = "email=email-boletin";
    const linked = await mount({ width: 1280 });
    assert.deepEqual(linked.api().panel, { kind: "email", emailId: "email-boletin" });
    await linked.settle(() => emailDetail() !== null, "the linked email");
    search = "view=inbox&segment=emails";
    const old = await mount();
    assert.deepEqual(old.api().panel, { kind: "business", tab: "correo" });
    await old.settle(() => old.host.querySelector('[data-testid="email-history"] [data-testid="email-delivery-row"]') !== null, "the email history");
  });
});

describe("the email history in Negocio", () => {
  const emailDetail = () => document.querySelector('[data-testid="email-detail"]');
  test("Correo de recibos keeps the receiving address on top, then a quiet Historial of every email with its refresh", async () => {
    const page = await mount({ panel: { kind: "business", tab: "correo" } });
    await page.settle(() => page.host.querySelectorAll('[data-testid="email-history"] [data-testid="email-delivery-row"]').length === 5 && page.host.querySelector('[data-testid="email-copy-address"]') !== null, "the address and the history");
    const history = page.host.querySelector('[data-testid="email-history"]')!;
    assert.equal(history.querySelector("h3")?.textContent, "Historial");
    assert.equal(history.querySelector('[data-testid="email-refresh"]')?.getAttribute("aria-label"), "Actualizar");
    assert.ok(page.host.querySelector('[data-testid="email-address"]')!.compareDocumentPosition(history) & Node.DOCUMENT_POSITION_FOLLOWING, "the address comes first");
    await page.act(async () => history.querySelector<HTMLButtonElement>('[data-testid="email-delivery-row"]')!.click());
    await page.settle(() => emailDetail() !== null, "the opened email");
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
