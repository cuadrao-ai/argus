import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessCapture, ReceiptSummary } from "@/lib/business-api";
import type { BusinessDataSource } from "@/components/business-app/business-data";
import type { BusinessPanelState } from "@/components/business-app/BusinessWorkspace";
import { receptionRows, rowState, rowTitles, receptionTab, tabCount } from "./support/reception";

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
  const segment = receptionTab.bind(null, host);
  const names = (within: ParentNode = host) => rowTitles(within);
  const choose = async (key: "all" | "review" | "processing" | "attention") => {
    await act(async () => segment(key)!.click());
    assert.equal(segment(key)?.getAttribute("aria-selected"), "true");
  };
  const open = (next: BusinessPanelState) => act(async () => api!.openPanel(next));
  if (panel) await open(panel);
  return { act, host, settle, segment, names, choose, open, api: () => api! };
}

const inboxReady = (page: Awaited<ReturnType<typeof mount>>) =>
  page.settle(() => receptionRows(page.host).length > 0, "the Bandeja rows");

const failureOf = (page: { host: HTMLElement }) => page.host.querySelector<HTMLElement>('[role="alert"]');
const FAILED = "No pudimos cargar tus notas ni tus correos.";

describe("the Bandeja views", () => {
  test("Todos opens first; each view lists its arrivals newest first and shows the server's count", async () => {
    const page = await mount({ panel: { kind: "inbox" } });
    await inboxReady(page);
    assert.equal(page.segment("all")?.getAttribute("aria-selected"), "true", "Todos is the first view");
    assert.deepEqual(["review", "processing", "attention"].map((key) => tabCount(page.host, key as "review")), ["4", "1", "5"], "the server counts the two emails that brought no receipt");
    await page.choose("review");
    assert.deepEqual(page.names(), ["Ferretería La Esquina", "Papelería Central", "IMG_2215.jpg", "colmado-oct.jpg"]);
    await page.choose("attention");
    assert.deepEqual(page.names().sort(), ["Boletín semanal", "Factura Farmacia Carol", "IMG_2209.jpg", "IMG_2215.jpg", "colmado-oct.jpg"]);
    await page.choose("all");
    assert.equal(page.names().length, 9, "every receipt, plus the three emails that are rows of their own");
  });

  test("a view with nothing in it says so and Limpiar filtros returns to Todos", async () => {
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
    await page.choose("attention");
    const empty = page.host.querySelector('[data-testid="reception-empty"]');
    assert.equal(empty?.getAttribute("data-empty-kind"), "filtered");
    assert.equal(empty?.querySelector("h3")?.textContent, "No hay contenido en esta vista");
    const clear = [...(empty?.querySelectorAll("button") ?? [])].find((button) => button.textContent === "Limpiar filtros");
    assert.ok(clear, "Limpiar filtros");
    assert.ok(!clear.className.includes("bg-[var(--cuadrao-green)]"), "changing the view is a quiet action, not a second primary");
    await page.act(async () => clear.click());
    assert.equal(page.segment("all")?.getAttribute("aria-selected"), "true");
    assert.ok(page.names().includes("Papelería Central"));
  });
});

describe("a list that did not load", () => {
  const NOTHING = { items: [], activity: { reading_count: 0, unread_count: 0, presentation: "none" as const, pending_review_count: 0, needs_attention_count: 0, ready_to_review_count: 0 } };
  const failing = () => {
    const calls = { receipts: 0, notes: 0, emails: 0 };
    let fail = true;
    const overrides = () => ({
      receiptPage: async () => { calls.receipts += 1; return NOTHING; },
      captures: async () => { calls.notes += 1; if (fail) throw Object.assign(new Error("API error 500"), { status: 500, code: "internal_error" }); return { items: [] }; },
      emailDeliveries: async () => { calls.emails += 1; if (fail) throw Object.assign(new Error("API error 503"), { status: 503, code: "service_unavailable" }); return []; },
    });
    return { calls, overrides, recover: () => { fail = false; } };
  };

  test("never claims nothing to review: the failure is said once and no empty state shows in any view", async () => {
    const { overrides } = failing();
    const page = await mount({ panel: { kind: "inbox" }, overrides });
    await page.settle(() => failureOf(page)?.textContent?.includes(FAILED) === true, "the failure");
    assert.equal(page.host.querySelectorAll('[role="alert"]').length, 1, "one line, not one per list");
    assert.ok([...failureOf(page)!.querySelectorAll("button")].some((button) => button.textContent === "Reintentar"));
    for (const key of ["all", "review", "processing", "attention"] as const) {
      await page.choose(key);
      assert.equal(page.host.querySelector('[data-testid="reception-empty"]'), null, `${key} claims no empty view`);
    }
  });

  test("the server's counts read - while a list is down, and come back once every list loaded", async () => {
    const { overrides, recover } = failing();
    const page = await mount({ panel: { kind: "inbox" }, overrides: () => ({ ...overrides(), receiptPage: async () => ({ ...NOTHING, activity: { ...NOTHING.activity, ready_to_review_count: 3, needs_attention_count: 2 } }) }) });
    await page.settle(() => failureOf(page) !== null, "the failure");
    assert.equal(tabCount(page.host, "review"), "-", "a 3 beside a list that failed would contradict it");
    assert.equal(tabCount(page.host, "attention"), "-");
    recover();
    await page.act(async () => [...failureOf(page)!.querySelectorAll("button")].find((button) => button.textContent === "Reintentar")!.click());
    await page.settle(() => tabCount(page.host, "review") === "3", "the recovery");
    assert.equal(tabCount(page.host, "attention"), "2");
  });

  test("a count the server does not send reads -, never 0", async () => {
    const page = await mount({ panel: { kind: "inbox" }, overrides: () => ({ receiptPage: async () => ({ items: [], activity: null }), emailDeliveries: async () => [] }) });
    await page.settle(() => page.host.querySelector('[data-testid="reception-empty"]') !== null, "the settled list");
    assert.equal(tabCount(page.host, "review"), "-");
    assert.equal(tabCount(page.host, "attention"), "-");
  });

  describe("a server reference", () => {
    const requestId = "4ea79978-ce17-4853-b232-b2a72f4c9ce7";
    const serverError = () => Object.assign(new Error("API error 500"), { status: 500, requestId });
    const reference = (page: { host: HTMLElement }) => failureOf(page)?.querySelector<HTMLButtonElement>('[data-testid="error-reference"]') ?? null;
    const assertShortAndCopyable = async (page: Awaited<ReturnType<typeof mount>>) => {
      const copied: string[] = [];
      Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: async (value: string) => { copied.push(value); } } });
      const shown = reference(page)!;
      assert.equal(shown.querySelector("[data-reference-short]")?.textContent, "Ref. 4ea79978");
      assert.equal(shown.title, requestId);
      assert.ok(shown.textContent?.includes(requestId), "the accessible name carries the full id");
      await page.act(async () => shown.click());
      assert.deepEqual(copied, [requestId]);
    };

    test("a notes failure reads short, keeps the full id in its title and copies the full id", async () => {
      const page = await mount({ panel: { kind: "inbox" }, overrides: () => ({ captures: async () => { throw serverError(); } }) });
      await page.settle(() => reference(page) !== null, "the reference");
      await assertShortAndCopyable(page);
    });

    test("an emails failure carries its reference", async () => {
      const page = await mount({ panel: { kind: "inbox" }, overrides: () => ({ emailDeliveries: async () => { throw serverError(); } }) });
      await page.settle(() => reference(page) !== null, "the reference");
      await assertShortAndCopyable(page);
    });

    test("a failed full read of the arrivals carries its reference", async () => {
      const page = await mount({ panel: { kind: "inbox" }, overrides: fixture => ({ receiptPage: async (view, signal) => { if (view === "all") throw serverError(); return fixture.receiptPage!(view, signal); } }) });
      await page.settle(() => reference(page) !== null, "the reference");
      await assertShortAndCopyable(page);
    });
  });

  describe("the line names the list that failed", () => {
    const SERVER = () => Object.assign(new Error("API error 500"), { status: 500, code: "internal_error" });
    const EMAIL_OFF = () => Object.assign(new Error("Email receiving is unavailable."), { status: 503, code: "email_capture_unavailable" });
    const line = (page: { host: HTMLElement }) => failureOf(page)?.querySelector("p")?.textContent ?? "";
    test("only the notes failed", async () => {
      const page = await mount({ panel: { kind: "inbox" }, overrides: () => ({ receiptPage: async () => NOTHING, captures: async () => { throw SERVER(); } }) });
      await page.settle(() => failureOf(page) !== null, "the failure");
      assert.match(line(page), /^No pudimos cargar tus notas\./);
      assert.doesNotMatch(line(page), /correos|todo el contenido/);
    });
    test("only the emails failed", async () => {
      const page = await mount({ panel: { kind: "inbox" }, overrides: () => ({ receiptPage: async () => NOTHING, emailDeliveries: async () => { throw SERVER(); } }) });
      await page.settle(() => failureOf(page) !== null, "the failure");
      assert.match(line(page), /^No pudimos cargar tus correos\./);
      assert.doesNotMatch(line(page), /notas|todo el contenido/);
    });
    test("refused email capture names the emails and keeps the contact line", async () => {
      const page = await mount({ panel: { kind: "inbox" }, overrides: () => ({ receiptPage: async () => NOTHING, emailDeliveries: async () => { throw EMAIL_OFF(); } }) });
      await page.settle(() => failureOf(page) !== null, "the failure");
      assert.match(line(page), /^No pudimos cargar tus correos\./);
      assert.match(line(page), /escríbenos a hola@cuadrao\.ai/);
      assert.equal([...failureOf(page)!.querySelectorAll("button")].some((button) => button.textContent === "Reintentar"), false);
    });
    test("a failed read of the arrivals keeps the general line", async () => {
      const page = await mount({ panel: { kind: "inbox" }, overrides: fixture => ({ receiptPage: async (view, signal) => { if (view === "all") throw SERVER(); return fixture.receiptPage!(view, signal); } }) });
      await page.settle(() => failureOf(page) !== null, "the failure");
      assert.match(line(page), /^No pudimos cargar todo el contenido\./);
    });
  });

  test("Reintentar asks again only for the lists that failed, and their recovery shows the true empty state", async () => {
    const { calls, overrides, recover } = failing();
    const page = await mount({ panel: { kind: "inbox" }, overrides });
    await page.settle(() => failureOf(page) !== null, "the failure");
    const before = { ...calls };
    recover();
    const retry = [...failureOf(page)!.querySelectorAll("button")].find((button) => button.textContent === "Reintentar")!;
    await page.act(async () => retry.click());
    await page.settle(() => page.host.querySelector('[data-testid="reception-empty"]') !== null, "the true empty state");
    assert.equal(page.host.querySelector('[data-testid="reception-empty"]')?.getAttribute("data-empty-kind"), "first_run");
    assert.equal(failureOf(page), null);
    assert.equal(calls.receipts, before.receipts, "the receipts loaded, so the Bandeja does not ask for them again");
    assert.equal(calls.notes, before.notes + 1);
    assert.equal(calls.emails, before.emails + 1);
  });
});

describe("a list the server refused for good", () => {
  // The Business routes answer 404 business_unavailable and email receiving answers
  // 503 email_capture_unavailable. Asking again gets the same answer.
  const NOTHING = { items: [], activity: { reading_count: 0, unread_count: 0, presentation: "none" as const, pending_review_count: 0, needs_attention_count: 0, ready_to_review_count: 0 } };
  const BUSINESS_OFF = () => Object.assign(new Error("Business is not available."), { status: 404, code: "business_unavailable" });
  const EMAIL_OFF = () => Object.assign(new Error("Email receiving is unavailable."), { status: 503, code: "email_capture_unavailable" });
  const actions = (page: { host: HTMLElement }) => [...(failureOf(page)?.querySelectorAll("button") ?? [])].filter((button) => button.dataset.testid !== "error-reference").map((button) => button.textContent);

  test("offers no Reintentar, claims no empty state and no count", async () => {
    const calls = { notes: 0, emails: 0 };
    const page = await mount({ panel: { kind: "inbox" }, overrides: () => ({
      receiptPage: async () => ({ ...NOTHING, activity: { ...NOTHING.activity, ready_to_review_count: 3 } }),
      captures: async () => { calls.notes += 1; throw BUSINESS_OFF(); },
      emailDeliveries: async () => { calls.emails += 1; throw EMAIL_OFF(); },
    }) });
    await page.settle(() => failureOf(page) !== null, "the failure");
    assert.deepEqual(actions(page), [], "asking again gets the same refusal");
    assert.match(failureOf(page)!.textContent ?? "", /No pudimos cargar tus notas ni tus correos\./, "the line names what was refused");
    assert.match(failureOf(page)!.textContent ?? "", /escríbenos a hola@cuadrao\.ai/, "a refusal always has a way out");
    assert.equal(tabCount(page.host, "review"), "-", "a 3 beside a list that failed would contradict it");
    assert.equal(page.host.querySelector('[data-testid="reception-empty"]'), null);
    const before = { ...calls };
    window.dispatchEvent(new Event("offline"));
    window.dispatchEvent(new Event("online"));
    await page.settle(() => true, "a reconnect");
    assert.deepEqual(calls, before, "a reconnect does not ask again for a list the server refused");
  });

  test("a refused Bandeja says so with no Reintentar and without blaming the connection", async () => {
    const page = await mount({ panel: { kind: "inbox" }, overrides: () => ({ receiptPage: async () => { throw BUSINESS_OFF(); } }) });
    await page.settle(() => failureOf(page) !== null, "the Bandeja error");
    assert.equal(failureOf(page)!.querySelectorAll("button").length, 0);
    assert.match(failureOf(page)!.textContent ?? "", /Cuadrao Business aún no está disponible para tu cuenta\./);
    assert.match(failureOf(page)!.textContent ?? "", /escríbenos a hola@cuadrao\.ai/);
    assert.doesNotMatch(failureOf(page)!.textContent ?? "", /conexión/);
  });

  test("beside a list that can pass, Reintentar asks again only for that one", async () => {
    const calls = { notes: 0, emails: 0 };
    let emailsDown = true;
    const page = await mount({ panel: { kind: "inbox" }, overrides: () => ({
      receiptPage: async () => NOTHING,
      captures: async () => { calls.notes += 1; throw BUSINESS_OFF(); },
      emailDeliveries: async () => { calls.emails += 1; if (emailsDown) throw Object.assign(new Error("API error 500"), { status: 500, code: "internal_error" }); return []; },
    }) });
    await page.settle(() => failureOf(page) !== null, "the failure");
    assert.deepEqual(actions(page), ["Reintentar"]);
    assert.doesNotMatch(failureOf(page)!.textContent ?? "", /escríbenos/, "a retry is the way out while one list can pass");
    const before = { ...calls };
    emailsDown = false;
    await page.act(async () => [...failureOf(page)!.querySelectorAll("button")].find((button) => button.textContent === "Reintentar")!.click());
    await page.settle(() => calls.emails > before.emails, "the emails back");
    assert.equal(calls.notes, before.notes, "the refused notes are not asked for again");
    assert.deepEqual(actions(page), [], "only the refusal is left, so no Reintentar");
  });
});

describe("what arrived since the last visit", () => {
  const unseen = (page: { host: HTMLElement }) => receptionRows(page.host).filter((row) => row.dataset.unseen === "true").map((row) => rowTitles(row.parentElement!)[[...row.parentElement!.children].indexOf(row)]);

  test("receipts the server marks unread carry the No visto dot, and nothing else does", async () => {
    const page = await mount({ panel: { kind: "inbox" } });
    await inboxReady(page);
    assert.deepEqual(unseen(page).sort(), ["Ferretería La Esquina", "IMG_2209.jpg"]);
  });

  test("with nothing unread no row carries the dot", async () => {
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
    assert.deepEqual(unseen(page), []);
  });
});

describe("typed notes in the list", () => {
  const NOTES = [
    note("draft-a", "Ayer compré pintura para el taller.", "2000-01-02T14:00:00Z"),
    { ...note("draft-a", "Pagué con mi dinero.", "2000-01-02T15:30:00Z"), earlier_count: 1 },
  ];
  const noteRows = (page: { host: HTMLElement }) => receptionRows(page.host).filter((row) => row.dataset.kind === "note");

  test("an open note is a Por revisar row with its latest words, never a problem, and its dossier opens the draft", async () => {
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
    await page.settle(() => noteRows(page).length === 1, "the note row");
    assert.equal(tabCount(page.host, "review"), "5");
    const row = noteRows(page)[0];
    assert.ok(row.textContent?.includes("Pagué con mi dinero."));
    assert.ok(!row.textContent?.includes("Ayer compré pintura"), "one row per draft, its latest note");
    assert.equal(rowState(row), "Lista para revisar");
    await page.choose("review");
    assert.equal(noteRows(page).length, 1);
    await page.choose("attention");
    assert.equal(noteRows(page).length, 0);
    await page.choose("all");
    await page.act(async () => noteRows(page)[0].querySelector<HTMLButtonElement>("button")!.click());
    const dossier = page.host.ownerDocument.querySelector('[data-testid="reception-dossier"]')!;
    assert.ok(dossier.textContent?.includes("Pagué con mi dinero."), "the dossier shows the verbatim note");
    const review = document.querySelector<HTMLButtonElement>('[class~="detailFooter"] button')!;
    assert.equal(review.textContent, "Revisar");
    await page.act(async () => review.click());
    assert.deepEqual(page.api().panel, { kind: "draft", draftId: "draft-a", list: "inbox" });
  });

  test("a notes outage says so above the receipts it still lists", async () => {
    const page = await mount({ panel: { kind: "inbox" }, overrides: () => ({ captures: async () => { throw Object.assign(new Error("not served"), { status: 404 }); } }) });
    await page.settle(() => failureOf(page) !== null, "the notes failure");
    await page.settle(() => page.names().includes("Ferretería La Esquina"), "the receipts it still lists");
    assert.equal(page.host.querySelectorAll('[role="alert"]').length, 1);
    assert.equal(noteRows(page).length, 0);
  });

  test("the server's has_more, not a full page, says older notes wait in search", async () => {
    const many = Array.from({ length: 50 }, (_, index) => note(`draft-${index}`, `Nota ${index}`, `2000-01-01T00:${String(index).padStart(2, "0")}:00Z`));
    const full = await mount({ panel: { kind: "inbox" }, overrides: () => ({ captures: async () => ({ items: many, has_more: false }) }) });
    await full.settle(() => noteRows(full).length > 0, "the note rows");
    assert.ok(!full.host.textContent?.includes("Se muestran las últimas 50 notas guardadas."), "fifty notes and nothing past them is the whole list");
    while (unmounts.length) await unmounts.pop()!();
    document.body.innerHTML = "";
    const more = await mount({ panel: { kind: "inbox" }, overrides: () => ({ captures: async () => ({ items: many.slice(0, 3), has_more: true }) }) });
    await more.settle(() => noteRows(more).length > 0, "the note rows");
    assert.ok(more.host.textContent?.includes("Se muestran las últimas 50 notas guardadas."));
  });
});

describe("emails in the Bandeja", () => {
  // The sample's emails: the ferretería's and the colmado's each saved a receipt, the gas station's is still
  // being read, the boletín's zip could not be saved, and the farmacia's hit an inactive address and can be retried.
  const emailRows = (page: { host: HTMLElement }) => receptionRows(page.host).filter((row) => row.dataset.kind === "email");
  const emailRow = (page: { host: HTMLElement }, text: string) => emailRows(page).find((row) => row.textContent?.includes(text));
  const emailDetail = () => document.querySelector('[data-testid="email-detail"]');

  test("an email that brought no receipt is a Necesitan atención row with its sender, its subject and why", async () => {
    const page = await mount({ panel: { kind: "inbox" } });
    await inboxReady(page);
    await page.choose("attention");
    assert.equal(emailRows(page).length, 2);
    const boletin = emailRow(page, "Boletín semanal")!;
    assert.match(boletin.textContent ?? "", /noticias@proveedor\.example/);
    assert.match(rowState(boletin), /Necesita atención/);
    assert.match(boletin.textContent ?? "", /Este tipo de archivo no se puede guardar como recibo/);
    const farmacia = emailRow(page, "Factura Farmacia Carol")!;
    assert.match(farmacia.textContent ?? "", /facturas@farmaciacarol\.example/);
    assert.match(farmacia.textContent ?? "", /Esta dirección no está activa/);
    assert.equal(boletin.querySelector('[data-testid="reception-sender"]')?.getAttribute("data-known"), "true");
  });

  test("Todos lists every email that brought no receipt beside the receipts, and an email whose file became a receipt is no row of its own", async () => {
    const page = await mount({ panel: { kind: "inbox" } });
    await inboxReady(page);
    await page.settle(() => emailRows(page).length === 3, "the three email rows");
    assert.equal(emailRow(page, "ventas@ferreterialaesquina.example"), undefined, "the ferretería's email is its receipt");
    assert.equal(emailRow(page, "ventas@colmadoelprimo.example"), undefined, "the colmado's email is its receipt");
    assert.ok(emailRow(page, "facturas@estacion.example"), "the email still being read");
  });

  test("an email still being read waits under En proceso, not Por revisar", async () => {
    const page = await mount({ panel: { kind: "inbox" } });
    await inboxReady(page);
    await page.choose("review");
    assert.equal(emailRows(page).length, 0, "Por revisar holds no reading email");
    await page.choose("processing");
    await page.settle(() => emailRows(page).length === 1, "the reading email row");
    assert.match(emailRows(page)[0].textContent ?? "", /Recibo de combustible/);
    assert.equal(tabCount(page.host, "review"), "4");
  });

  test("on a desktop an email row opens the email in the dossier beside the list", async () => {
    const page = await mount({ width: 1280, panel: { kind: "inbox" } });
    await inboxReady(page);
    await page.choose("attention");
    await page.act(async () => emailRow(page, "noticias@proveedor.example")!.querySelector("button")!.click());
    await page.settle(() => emailDetail() !== null, "the email detail");
    assert.ok(page.host.querySelector('[role="tablist"]'), "the list stays beside it");
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

  test("Reintentar in the email dossier asks the server again and says so", async () => {
    const retried: string[] = [];
    const page = await mount({ width: 1280, panel: { kind: "inbox" }, overrides: () => ({ retryEmailDelivery: async (id: string) => { retried.push(id); return { id }; } }) });
    await inboxReady(page);
    await page.choose("attention");
    await page.act(async () => emailRow(page, "facturas@farmaciacarol.example")!.querySelector("button")!.click());
    await page.settle(() => [...document.querySelectorAll("button")].some((button) => button.textContent === "Reintentar"), "the dossier's Reintentar");
    await page.act(async () => [...document.querySelectorAll<HTMLButtonElement>("button")].find((button) => button.textContent === "Reintentar")!.click());
    await page.settle(() => retried.length === 1, "the retry request");
    assert.deepEqual(retried, ["email-farmacia"]);
  });

  test("a retry the server refuses says so in the dossier, with Reintentar still there, and shows no toast", async () => {
    let attempts = 0;
    const page = await mount({ width: 1280, panel: { kind: "inbox" }, overrides: () => ({ retryEmailDelivery: async (id: string) => { attempts += 1; if (attempts === 1) throw new Error("refused"); return { id }; } }) });
    await inboxReady(page);
    await page.choose("attention");
    await page.act(async () => emailRow(page, "facturas@farmaciacarol.example")!.querySelector("button")!.click());
    const dossier = () => document.querySelector('[data-testid="reception-dossier"]')!;
    const retry = () => [...dossier().querySelectorAll("button")].find((button) => button.textContent === "Reintentar")!;
    await page.settle(() => dossier().querySelector("button") !== null && [...dossier().querySelectorAll("button")].some((button) => button.textContent === "Reintentar"), "the dossier's Reintentar");
    await page.act(async () => retry().click());
    await page.settle(() => dossier().querySelector('[role="alert"]') !== null, "the inline failure");
    assert.equal(dossier().querySelector('[role="alert"]')!.textContent, "No se pudo solicitar el reintento. Los adjuntos guardados no cambian.");
    assert.equal(document.querySelector('[data-testid="toast"]'), null, "the failure is in the dossier, not in a toast");
    assert.ok(retry(), "Reintentar is still there");
    await page.act(async () => retry().click());
    await page.settle(() => attempts === 2, "the second request");
    assert.equal(dossier().querySelector('[role="alert"]'), null, "asking again clears the failure");
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
  assert.equal(document.body.textContent?.includes("Novedades"), false);
});
