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
  const source = { ...fixture, captures: async () => ({ items: [] }), ...overrides(fixture) };
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
    assert.equal(page.segment("problem")?.textContent, "Con problema5", "the server counts the two emails that brought no receipt");
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
    assert.ok(!all.className.includes("bg-[var(--cuadrao-green)]"), "changing the filter is a quiet action, not a second primary");
    await page.act(async () => all.click());
    assert.equal(page.segment("all")?.getAttribute("aria-checked"), "true");
    assert.deepEqual(page.names(), ["Ferretería La Esquina", "Papelería Central"]);
  });
});

describe("a list that did not load", () => {
  // No receipts, and the notes and emails requests fail in ways that can pass:
  // a 500 and a 503 that is not one of the server's refusals for good.
  const NOTHING = { items: [], activity: { reading_count: 0, unread_count: 0, presentation: "none" as const, pending_review_count: 0, needs_attention_count: 0, ready_to_review_count: 0 } };
  const failing = ({ notes = () => Object.assign(new Error("API error 500"), { status: 500, code: "internal_error" }), emails = () => Object.assign(new Error("API error 503"), { status: 503, code: "service_unavailable" }) }: { notes?: () => Error; emails?: () => Error } = {}) => {
    const calls = { receipts: 0, notes: 0, emails: 0 };
    let fail = true;
    const overrides = () => ({
      receiptPage: async (view: string) => { if (view === "inbox") calls.receipts += 1; return NOTHING; },
      captures: async () => { calls.notes += 1; if (fail) throw notes(); return { items: [] }; },
      emailDeliveries: async () => { calls.emails += 1; if (fail) throw emails(); return []; },
    });
    return { calls, overrides, recover: () => { fail = false; } };
  };
  const failure = (page: { host: HTMLElement }) => page.host.querySelector<HTMLElement>('[data-testid="bandeja-sources-failed"]');

  test("never claims nothing to review: one failure names both lists, and no empty state shows in any segment", async () => {
    const { overrides } = failing();
    const page = await mount({ panel: { kind: "inbox" }, overrides });
    await page.settle(() => failure(page)?.textContent?.includes("notas ni tus correos") === true, "one failure for both lists");
    assert.equal(page.host.querySelectorAll('[role="alert"]').length, 1, "one line, not one per list");
    assert.match(failure(page)!.textContent ?? "", /^No pudimos cargar tus notas ni tus correos\./);
    assert.ok([...failure(page)!.querySelectorAll("button")].some((button) => button.textContent === "Reintentar"));
    for (const key of ["review", "problem", "all"] as const) {
      await page.choose(key);
      assert.equal(page.host.querySelector('[data-testid="bandeja-segment-empty"]'), null, `${key} claims no empty segment`);
      assert.equal(page.host.querySelector('[data-testid="business-inbox-empty"]'), null, `${key} claims no empty Bandeja`);
    }
  });

  test("a count the server does not send reads -, never 0, while a list is down", async () => {
    const { overrides } = failing();
    const page = await mount({ panel: { kind: "inbox" }, overrides: () => ({ ...overrides(), receiptPage: async () => ({ items: [], activity: null }) }) });
    await page.settle(() => failure(page) !== null && page.segment("review")?.textContent !== "Por revisar", "the failure and the settled count");
    assert.equal(page.segment("review")?.textContent, "Por revisar-");
    assert.equal(page.segment("problem")?.textContent, "Con problema-");
  });

  test("the server's counts read - while a list is down, and come back once every list loaded", async () => {
    const { overrides, recover } = failing();
    const page = await mount({ panel: { kind: "inbox" }, overrides: () => ({ ...overrides(), receiptPage: async () => ({ ...NOTHING, activity: { ...NOTHING.activity, ready_to_review_count: 3, needs_attention_count: 2 } }) }) });
    await page.settle(() => failure(page) !== null && page.segment("review")?.textContent !== "Por revisar", "the failure and the settled count");
    assert.equal(page.segment("review")?.textContent, "Por revisar-", "a 3 beside a list that failed would contradict it");
    assert.equal(page.segment("problem")?.textContent, "Con problema-");
    recover();
    await page.act(async () => [...failure(page)!.querySelectorAll("button")].find((button) => button.textContent === "Reintentar")!.click());
    await page.settle(() => failure(page) === null, "the recovery");
    assert.equal(page.segment("review")?.textContent, "Por revisar3");
    assert.equal(page.segment("problem")?.textContent, "Con problema2");
  });

  test("a server reference reads short, keeps the full id in its title and copies the full id", async () => {
    const requestId = "4ea79978-ce17-4853-b232-b2a72f4c9ce7";
    const copied: string[] = [];
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: async (value: string) => { copied.push(value); } } });
    const page = await mount({ panel: { kind: "inbox" }, overrides: () => ({ captures: async () => { throw Object.assign(new Error("API error 500"), { status: 500, requestId }); } }) });
    await page.settle(() => failure(page)?.querySelector('[data-testid="error-reference"]') != null, "the reference");
    const reference = failure(page)!.querySelector<HTMLButtonElement>('[data-testid="error-reference"]')!;
    assert.equal(reference.querySelector("[data-reference-short]")?.textContent, "Ref. 4ea79978");
    assert.equal(reference.title, requestId);
    assert.ok(reference.textContent?.includes(requestId), "the accessible name carries the full id");
    await page.act(async () => reference.click());
    assert.deepEqual(copied, [requestId]);
  });

  test("Reintentar asks again only for the lists that failed, and their recovery shows the true empty state", async () => {
    const { calls, overrides, recover } = failing();
    const page = await mount({ panel: { kind: "inbox" }, overrides });
    await page.settle(() => failure(page) !== null, "the failure");
    const before = { ...calls };
    recover();
    const retry = [...failure(page)!.querySelectorAll("button")].find((button) => button.textContent === "Reintentar")!;
    await page.act(async () => retry.click());
    await page.settle(() => page.host.querySelector('[data-testid="business-inbox-empty"]') !== null, "the true empty state");
    assert.equal(failure(page), null);
    assert.equal(calls.receipts, before.receipts, "the receipts loaded, so the Bandeja does not ask for them again");
    assert.equal(calls.notes, before.notes + 1);
    assert.equal(calls.emails, before.emails + 1);
  });
});

describe("a list the server refused for good", () => {
  // Lucas's LAN preview: the Business routes answer 404 business_unavailable
  // and email receiving answers 503 email_capture_unavailable. Asking again
  // gets the same answer.
  const NOTHING = { items: [], activity: { reading_count: 0, unread_count: 0, presentation: "none" as const, pending_review_count: 0, needs_attention_count: 0, ready_to_review_count: 0 } };
  const BUSINESS_OFF = () => Object.assign(new Error("Business is not available."), { status: 404, code: "business_unavailable" });
  const EMAIL_OFF = () => Object.assign(new Error("Email receiving is unavailable."), { status: 503, code: "email_capture_unavailable" });
  const failure = (page: { host: HTMLElement }) => page.host.querySelector<HTMLElement>('[data-testid="bandeja-sources-failed"]');
  const actions = (page: { host: HTMLElement }) => [...(failure(page)?.querySelectorAll("button") ?? [])].filter((button) => button.dataset.testid !== "error-reference").map((button) => button.textContent);

  test("offers no Reintentar, says how to reach us, and claims no empty state or count", async () => {
    const calls = { notes: 0, emails: 0 };
    const page = await mount({ panel: { kind: "inbox" }, overrides: () => ({
      receiptPage: async () => ({ ...NOTHING, activity: { ...NOTHING.activity, ready_to_review_count: 3 } }),
      captures: async () => { calls.notes += 1; throw BUSINESS_OFF(); },
      emailDeliveries: async () => { calls.emails += 1; throw EMAIL_OFF(); },
    }) });
    await page.settle(() => failure(page) !== null && page.segment("review")?.textContent !== "Por revisar", "the failure and the settled count");
    assert.match(failure(page)!.textContent ?? "", /^No pudimos cargar tus notas ni tus correos\./);
    assert.deepEqual(actions(page), [], "asking again gets the same refusal");
    assert.match(failure(page)!.textContent ?? "", /escríbenos a hola@cuadrao\.ai/);
    assert.doesNotMatch(failure(page)!.textContent ?? "", /conexión/);
    assert.equal(page.segment("review")?.textContent, "Por revisar-", "a 3 beside a list that failed would contradict it");
    assert.equal(page.host.querySelector('[data-testid="business-inbox-empty"]'), null);
    assert.equal(page.host.querySelector('[data-testid="bandeja-segment-empty"]'), null);
    const before = { ...calls };
    window.dispatchEvent(new Event("offline"));
    window.dispatchEvent(new Event("online"));
    await page.settle(() => true, "a reconnect");
    assert.deepEqual(calls, before, "a reconnect does not ask again for a list the server refused");
  });

  test("a refused Bandeja says so with no Reintentar and without blaming the connection", async () => {
    const page = await mount({ panel: { kind: "inbox" }, overrides: () => ({ receiptPage: async () => { throw BUSINESS_OFF(); } }) });
    const error = () => page.host.querySelector('[data-testid="business-inbox-error"]');
    await page.settle(() => error() !== null, "the Bandeja error");
    assert.equal(error()!.querySelectorAll("button").length, 0);
    assert.match(error()!.textContent ?? "", /Cuadrao Business aún no está disponible para tu cuenta\./);
    assert.doesNotMatch(error()!.textContent ?? "", /conexión/);
  });

  test("beside a list that can pass, Reintentar asks again only for that one", async () => {
    const calls = { notes: 0, emails: 0 };
    let emailsDown = true;
    const page = await mount({ panel: { kind: "inbox" }, overrides: () => ({
      receiptPage: async () => NOTHING,
      captures: async () => { calls.notes += 1; throw BUSINESS_OFF(); },
      emailDeliveries: async () => { calls.emails += 1; if (emailsDown) throw Object.assign(new Error("API error 500"), { status: 500, code: "internal_error" }); return []; },
    }) });
    await page.settle(() => failure(page) !== null, "the failure");
    assert.match(failure(page)!.textContent ?? "", /^No pudimos cargar tus notas ni tus correos\./);
    assert.deepEqual(actions(page), ["Reintentar"]);
    const before = { ...calls };
    emailsDown = false;
    await page.act(async () => [...failure(page)!.querySelectorAll("button")].find((button) => button.textContent === "Reintentar")!.click());
    await page.settle(() => calls.emails > before.emails && !/correos/.test(failure(page)?.textContent ?? ""), "the emails back");
    assert.equal(calls.notes, before.notes, "the refused notes are not asked for again");
    assert.match(failure(page)!.textContent ?? "", /^No pudimos cargar tus notas\./);
    assert.deepEqual(actions(page), [], "only the refusal is left, so no Reintentar");
  });
});

describe("nothing left to review", () => {
  test("Por revisar says the receipts are up to date, apart from a Bandeja that has none at all", async () => {
    const page = await mount({
      panel: { kind: "inbox" },
      overrides: (fixture) => ({
        receiptPage: async (view) => {
          const shown = await fixture.receiptPage!(view);
          return { ...shown, items: shown.items.map((item) => ({ ...item, bandeja: item.bandeja ? { ...item.bandeja, por_revisar: false } : item.bandeja })) };
        },
      }),
    });
    const empty = () => page.host.querySelector('[data-testid="bandeja-segment-empty"]');
    await page.settle(() => empty() !== null, "the empty Por revisar");
    assert.equal(empty()?.querySelector("h3")?.textContent, "Tus recibos están al día.");
    assert.equal(page.host.querySelector('[data-testid="business-inbox-empty"]'), null, "the Bandeja still holds receipts under Todo");
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
  // The server counts the notes before each one over the whole draft, not the page.
  const NOTES = [
    note("draft-a", "Ayer compré pintura para el taller.", "2000-01-02T14:00:00Z"),
    { ...note("draft-a", "Pagué con mi dinero.", "2000-01-02T15:30:00Z"), earlier_count: 1 },
  ];

  test("an open note is a Por revisar row with its latest words and earlier count, never a problem, and opens its draft", async () => {
    // The server counts the one open draft with the four receipts.
    const page = await mount({
      panel: { kind: "inbox" },
      overrides: (fixture) => ({
        captures: async () => ({ items: NOTES }),
        receiptPage: async (view) => {
          const shown = await fixture.receiptPage!(view);
          return { ...shown, activity: shown.activity && { ...shown.activity, ready_to_review_count: shown.activity.ready_to_review_count + 1 } };
        },
      }),
    });
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
    const page = await mount({ panel: { kind: "inbox" }, overrides: () => ({ captures: async () => { throw Object.assign(new Error("not served"), { status: 404 }); } }) });
    await page.settle(() => page.host.querySelector('[data-testid="bandeja-sources-failed"]') !== null, "the notes failure");
    await inboxReady(page);
    assert.equal(page.host.querySelectorAll('[role="alert"]').length, 1);
    assert.match(page.host.querySelector('[data-testid="bandeja-sources-failed"]')?.textContent ?? "", /^No pudimos cargar tus notas\.Reintentar$/);
    assert.equal(page.host.querySelector('[data-testid="bandeja-note"]'), null);
    assert.equal(page.names().length, 4);
  });

  test("the server's has_more, not a full page, says older notes wait in search", async () => {
    const many = Array.from({ length: 50 }, (_, index) => note(`draft-${index}`, `Nota ${index}`, `2000-01-01T00:${String(index).padStart(2, "0")}:00Z`));
    const full = await mount({ panel: { kind: "inbox" }, overrides: () => ({ captures: async () => ({ items: many, has_more: false }) }) });
    await full.settle(() => full.host.querySelector('[data-testid="bandeja-note"]') !== null, "the note rows");
    assert.ok(!full.host.textContent?.includes("Se muestran las últimas 50 notas guardadas."), "fifty notes and nothing past them is the whole list");
    while (unmounts.length) await unmounts.pop()!();
    document.body.innerHTML = "";
    const more = await mount({ panel: { kind: "inbox" }, overrides: () => ({ captures: async () => ({ items: many.slice(0, 3), has_more: true }) }) });
    await more.settle(() => more.host.querySelector('[data-testid="bandeja-note"]') !== null, "the note rows");
    assert.ok(more.host.textContent?.includes("Se muestran las últimas 50 notas guardadas."));
  });

  test("a draft's note says how many came before it as the server counts them, past the page", async () => {
    const page = await mount({ panel: { kind: "inbox" }, overrides: () => ({ captures: async () => ({ items: [{ ...note("draft-b", "Era en efectivo.", "2000-01-03T10:00:00Z"), earlier_count: 4 }] }) }) });
    await page.settle(() => page.host.querySelector('[data-testid="bandeja-note"]') !== null, "the note row");
    assert.match(page.host.querySelector('[data-testid="bandeja-note"]')?.textContent ?? "", /4 notas anteriores/);
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

  test("a retry the server refuses says so on that email row, with Reintentar still there, and shows no toast", async () => {
    let attempts = 0;
    const page = await mount({ panel: { kind: "inbox" }, overrides: () => ({ retryEmailDelivery: async (id: string) => { attempts += 1; if (attempts === 1) throw new Error("refused"); return { id }; } }) });
    await inboxReady(page);
    await page.choose("problem");
    await page.settle(() => emailRow(page, "facturas@farmaciacarol.example") !== undefined, "the farmacia row");
    const row = () => emailRow(page, "facturas@farmaciacarol.example")!;
    const retry = () => [...row().querySelectorAll("button")].find((button) => button.textContent === "Reintentar")!;
    await page.act(async () => retry().click());
    await page.settle(() => row().querySelector('[role="alert"]') !== null, "the inline failure");
    assert.equal(row().querySelector('[role="alert"]')!.textContent, "No se pudo solicitar el reintento. Los adjuntos guardados no cambian.");
    assert.equal(document.querySelector('[data-testid="toast"]'), null, "the failure is on the row, not in a toast");
    assert.ok(retry(), "Reintentar is still on the row");
    await page.act(async () => retry().click());
    await page.settle(() => attempts === 2, "the second request");
    assert.equal(row().querySelector('[role="alert"]'), null, "asking again clears the failure");
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

  test("an old link to one email opens that email, and an old Correos link lands on Reception with the history action", async () => {
    search = "email=email-boletin";
    const linked = await mount({ width: 1280 });
    assert.deepEqual(linked.api().panel, { kind: "email", emailId: "email-boletin" });
    await linked.settle(() => emailDetail() !== null, "the linked email");
    search = "view=inbox&segment=emails";
    const old = await mount();
    assert.deepEqual(old.api().panel, { kind: "business", tab: "correo" });
    await old.settle(() => [...old.host.querySelectorAll("button")].some(button=>button.textContent?.includes("Ver correos recibidos")), "the history action");
  });
});

describe("the email history in Negocio", () => {
  const emailDetail = () => document.querySelector('[data-testid="email-detail"]');
  test("Reception keeps the address visible and opens email history in a dossier", async () => {
    const page = await mount({ panel: { kind: "business", tab: "correo" } });
    await page.settle(() => page.host.querySelector('[data-testid="email-copy-address"]') !== null, "the receiving address");
    assert.equal(page.host.querySelector('[data-testid="email-history"]'),null);
    await page.act(async()=>[...page.host.querySelectorAll("button")].find(button=>button.textContent?.includes("Ver correos recibidos"))!.click());
    await page.settle(()=>document.querySelectorAll('[data-testid="email-history"] [data-testid="email-delivery-row"]').length===5,"history dossier");
    const history = document.querySelector('[data-testid="email-history"]')!;
    assert.equal(history.querySelector("h3")?.textContent, "Historial");
    assert.equal(history.querySelector('[data-testid="email-refresh"]')?.getAttribute("aria-label"), "Actualizar");
    assert.ok(history.closest('[data-testid="side-drawer"], [role="dialog"]'), "history uses the shared panel");
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
