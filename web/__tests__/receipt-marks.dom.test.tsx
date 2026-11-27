import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessOverview } from "@/lib/business-api";
import type { BusinessDossier } from "@/lib/business-dossier";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});


async function setup() {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const settle = () => act(async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); });
  return { act, root, host, settle, I18nextProvider, i18n };
}

describe("the Overview's two totals", () => {
  test("the Overview no longer carries the Gastos reales and Con valor fiscal cards, and an empty Bandeja adds no review line or zero count", async () => {
    const env = await setup();
    const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
    const { default: BusinessOverviewPanel } = await import("@/components/business-app/BusinessOverviewPanel");
    const overview: BusinessOverview = { from: "2026-10-01", to: "2026-10-31", today: "2026-10-13", totals: [{ currency: "DOP", amount: "5000.00", count: 3 }], fiscal_totals: [{ currency: "DOP", amount: "3500.00", count: 2 }], without_fiscal_totals: [{ currency: "DOP", amount: "1500.00", count: 1 }], last_received_at: null, last_confirmed_at: null, outside_period_count: 0, outside_period_latest_on: null };
    const value = { source: { mode: "fixture" }, records: { overview, inbox: [], notes: [], workspace: null, error: false, notesError: false, notesTruncated: false }, panel: { kind: "overview" }, period: { key: "this_month", from: "2026-10-01", to: null }, setPeriod: () => undefined, openPanel: () => undefined, actions: { starterEntries: [], create: [] }, chosen: null } as unknown as BusinessContextValue;
    await env.act(async () => { env.root.render(<env.I18nextProvider i18n={env.i18n}><BusinessContext.Provider value={value}><BusinessOverviewPanel /></BusinessContext.Provider></env.I18nextProvider>); });
    assert.equal(env.host.querySelector('[data-testid="overview-real-expenses"]'), null);
    assert.equal(env.host.querySelector('[data-testid="overview-fiscal-expenses"]'), null);
    assert.ok(env.host.querySelector('section[aria-labelledby="business-overview-title"]'), "the Inicio region renders");
    assert.equal(env.host.querySelector('[data-testid="inicio-por-revisar"]'), null, "the old review card is gone");
    assert.equal(env.host.querySelector('[data-testid="month-close-task-review"]'), null, "nothing to review adds no checklist line");
    assert.equal(/Revisa 0 |0 por revisar/.test(env.host.textContent ?? ""), false);
    await env.act(async () => env.root.unmount());
  });
});

describe("the receipt page's marks card", () => {
  const OWNER = { actor_id: "o", actor_kind: "member", display_name: "Dueño", shown_as: "name", grant_id: "own", issuer_id: "o", issuer_display_name: "Dueño", issuer_shown_as: "name" };
  const ACCOUNTANT = { actor_id: "a", actor_kind: "member", display_name: "Lía", shown_as: "name", grant_id: "g", issuer_id: "o", issuer_display_name: "Dueño", issuer_shown_as: "name" };
  const share = (kind: "all" | "none", origin: string) => ({ state: "known", value: { kind }, origin, verified: true, source_ids: ["s"] });
  const dossier = (over: Partial<BusinessDossier> = {}, personal = false, ncf = true, answer: boolean | null = null, markedBy: "owner" | "accountant" = "owner"): BusinessDossier =>
    ({
      draft_id: "d-1",
      version: 3,
      capabilities: ["read", "prepare"],
      facts_editable: true,
      history: [
        { version: 2, actor: markedBy === "owner" ? OWNER : ACCOUNTANT, before: { business_share: share("all", "extracted") }, after: { business_share: share(personal ? "none" : "all", markedBy === "owner" ? "owner_stated" : "member_set") }, source_ids: [], created_at: "2026-10-13T09:00:00Z" },
        { version: 3, actor: ACCOUNTANT, before: null, after: {}, source_ids: [], created_at: "2026-10-13T10:00:00Z" },
      ],
      // The marks as the server reads them: the card renders these, never its own reading of the facts.
      personal,
      personal_marked_by: personal && markedBy === "accountant" ? { display_name: "Lía", email: null, shown_as: "name" } : null,
      fiscal_value: ncf ? "ncf" : null,
      fiscal_question_applies: personal && ncf,
      include_606: personal && ncf ? answer : null,
      include_606_by: personal && ncf && answer !== null ? { display_name: "Lía", email: null, shown_as: "name" } : null,
      fiscal_known: true,
      facts: {
        business_share: share(personal ? "none" : "all", markedBy === "owner" ? "owner_stated" : "member_set"),
        fiscal: ncf ? { rnc: { state: "unknown", value: null, origin: null, verified: false, source_ids: [] }, ncf: { state: "known", value: "B0100000001", origin: "extracted", verified: false, source_ids: ["s"] }, ecf: { state: "unknown", value: null, origin: null, verified: false, source_ids: [] }, itbis: { state: "unknown", value: null, origin: null, verified: false, source_ids: [] }, include_606: answer === null ? { state: "unknown", value: null, origin: null, verified: false, source_ids: [] } : { state: "known", value: answer, origin: "member_set", verified: true, source_ids: ["s"] } } : null,
      },
      ...over,
    }) as unknown as BusinessDossier;

  async function mountCard(d: BusinessDossier, role: "owner" | "accountant", { refuseAfter, bare = false }: { refuseAfter?: Promise<void>; bare?: boolean } = {}) {
    const env = await setup();
    const React = await import("react");
    const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
    const { default: ReceiptMarksCard } = await import("@/components/business-app/ReceiptMarksCard");
    const { ToastViewport } = await import("@/components/business-app/foundation/ToastViewport");
    const { clearToasts } = await import("@/components/business-app/foundation/toasts");
    clearToasts();
    const calls: string[] = [];
    let current = d;
    const value = {
      chosen: role === "owner" ? null : { space_id: "s", name: "Colmado Peña", grant_id: "g", role: "accountant", capabilities: ["read", "prepare"], access_seen: true },
      reload: () => undefined,
      source: {
        markPersonal: async (id: string, version: number, personal: boolean) => {
          calls.push(`mark:${personal}:${version}`);
          if (refuseAfter) { await refuseAfter; throw new Error("conflict"); }
          return dossier({ version: version + 1 }, personal, current.fiscal_value !== null, null);
        },
        decideFiscalInclusion: async (id: string, version: number, include: boolean) => {
          calls.push(`606:${include}:${version}`);
          if (refuseAfter) { await refuseAfter; throw new Error("conflict"); }
          return dossier({ version: version + 1, fiscal_inclusion_available: current.fiscal_inclusion_available }, true, true, include);
        },
      },
    } as unknown as BusinessContextValue;
    const changed: BusinessDossier[] = [];
    // The receipt page keeps the dossier the server returns and renders the card from it.
    let setBusy!: (value: boolean) => void;
    function Page() {
      const [busy, changeBusy] = React.useState(false);
      setBusy = changeBusy;
      const [shown, setShown] = React.useState(d);
      return <ReceiptMarksCard dossier={shown} busy={busy} bare={bare} onChanged={(next) => { changed.push(next); current = next; setShown(next); }} />;
    }
    await env.act(async () => { env.root.render(<env.I18nextProvider i18n={env.i18n}><BusinessContext.Provider value={value}><Page /><ToastViewport /></BusinessContext.Provider></env.I18nextProvider>); });
    const toggle = () => env.host.querySelector('[data-testid="receipt-mark-personal"]') as HTMLButtonElement;
    return { ...env, calls, changed, toggle, setBusy };
  }

  for (const answer of [null, true, false]) {
    test(`a personal sale with an NCF has no 606 block with answer ${answer}`, async () => {
      const page = await mountCard(dossier({ document_type: "venta", fiscal_question_applies: false, fiscal_inclusion_available: true }, true, true, answer), "accountant");
      assert.equal(page.host.querySelector('[data-testid="receipt-606"]'), null);
      assert.equal(page.toggle().getAttribute("aria-checked"), "true");
      await page.act(async () => page.root.unmount());
    });
  }

  test("the owner marks and unmarks; the 606 is read-only for the owner: pending, included or not", async () => {
    const page = await mountCard(dossier({}, false, false), "owner");
    assert.equal(page.toggle().getAttribute("role"), "switch");
    assert.equal(page.toggle().getAttribute("aria-label"), "Personal");
    assert.equal(page.toggle().getAttribute("aria-checked"), "false");
    assert.equal(page.host.querySelector('[data-testid="receipt-606"]'), null, "nothing to decide without a fiscal number");
    await page.act(async () => { page.toggle().click(); });
    await page.settle();
    assert.deepEqual(page.calls, ["mark:true:3"]);
    assert.equal(page.changed.length, 1);
    assert.equal(page.toggle().getAttribute("aria-checked"), "true", "the saved mark stays on");
    await page.act(async () => page.root.unmount());
    const pending = await mountCard(dossier({}, true, true, null), "owner");
    assert.equal(pending.host.querySelector('[data-testid="receipt-606-state"]')?.textContent, "Pendiente del contador");
    assert.equal(pending.host.querySelector('[data-testid="personal-marked-dot"]'), null, "the owner's own mark");
    assert.equal(pending.host.querySelector('[data-testid="receipt-606-yes"]'), null, "the owner never answers");
    assert.equal(pending.toggle().getAttribute("aria-checked"), "true");
    await pending.act(async () => { pending.toggle().click(); });
    await pending.settle();
    assert.deepEqual(pending.calls, ["mark:false:3"]);
    assert.equal(pending.toggle().getAttribute("aria-checked"), "false", "unmarked");
    await pending.act(async () => pending.root.unmount());
    const included = await mountCard(dossier({}, true, true, true), "owner");
    assert.equal(included.host.querySelector('[data-testid="receipt-606-state"]')?.textContent, "Incluido en 606");
    await included.act(async () => included.root.unmount());
  });

  test("the owner undoes the accountant's mark in one tap", async () => {
    const page = await mountCard(dossier({}, true, true, null, "accountant"), "owner");
    assert.equal(page.toggle().getAttribute("aria-checked"), "true");
    await page.act(async () => { page.toggle().click(); });
    await page.settle();
    assert.deepEqual(page.calls, ["mark:false:3"]);
    assert.equal(page.changed.length, 1);
    await page.act(async () => page.root.unmount());
  });

  test("a pending dossier command retires the earlier Personal Undo", async () => {
    const page = await mountCard(dossier({}, false, true), "owner");
    try {
      await page.act(async () => page.toggle().click());
      await page.settle();
      const toast = page.host.querySelector('[data-testid="toast-viewport"]')!;
      assert.match(toast.textContent ?? "", /Deshacer/);
      await page.act(async () => page.setBusy(true));
      assert.doesNotMatch(toast.textContent ?? "", /Deshacer/);
    } finally { await page.act(async () => page.root.unmount()); }
  });

  test("leaving the dossier retires its Personal Undo", async () => {
    const page = await mountCard(dossier({}, false, true), "owner");
    const { ToastViewport } = await import("@/components/business-app/foundation/ToastViewport");
    try {
      await page.act(async () => page.toggle().click());
      await page.settle();
      assert.match(page.host.textContent ?? "", /Deshacer/);
      await page.act(async () => page.root.render(<page.I18nextProvider i18n={page.i18n}><ToastViewport /></page.I18nextProvider>));
      assert.doesNotMatch(page.host.textContent ?? "", /Deshacer/);
    } finally { await page.act(async () => page.root.unmount()); }
  });

  test("a saved Personal change offers Deshacer, which puts it back; a refused one rolls the switch back and says so in the card with Reintentar", async () => {
    const page = await mountCard(dossier({}, false, true), "owner");
    await page.act(async () => { page.toggle().click(); });
    await page.settle();
    assert.equal(page.toggle().getAttribute("aria-checked"), "true");
    const { clearToasts } = await import("@/components/business-app/foundation/toasts");
    const toast = page.host.querySelector('[data-testid="toast-viewport"]')!;
    assert.ok(toast.textContent?.includes("Marcado como personal."), toast.textContent ?? "");
    const undo = [...toast.querySelectorAll("button")].find((b) => b.textContent === "Deshacer") as HTMLButtonElement;
    assert.ok(undo, "the success toast offers Deshacer");
    await page.act(async () => { undo.click(); });
    await page.settle();
    assert.deepEqual(page.calls, ["mark:true:3", "mark:false:4"], "Deshacer reverses the saved revision");
    assert.equal(page.toggle().getAttribute("aria-checked"), "false", "back to not personal");
    await page.act(async () => page.root.unmount());

    let answer!: () => void;
    const refused = await mountCard(dossier({}, false, true), "owner", { refuseAfter: new Promise<void>((done) => { answer = done; }) });
    await refused.act(async () => { refused.toggle().click(); });
    assert.equal(refused.toggle().getAttribute("aria-checked"), "true", "the switch flips before the server answers");
    assert.equal(refused.toggle().getAttribute("aria-busy"), "true", "and shows it is waiting");
    await refused.act(async () => { answer(); });
    await refused.settle();
    assert.deepEqual(refused.calls, ["mark:true:3"]);
    assert.equal(refused.changed.length, 0);
    assert.equal(refused.toggle().getAttribute("aria-checked"), "false", "a refusal rolls the switch back");
    const error = refused.host.querySelector('[data-testid="receipt-marks-problem"]')!;
    assert.equal(error.getAttribute("role"), "alert", "a refusal says so in the card, not in a toast");
    assert.ok(error.textContent?.includes("No pudimos guardar el cambio."), error.textContent ?? "");
    assert.ok([...error.querySelectorAll("button")].some((b) => b.textContent === "Reintentar"), "with Reintentar");
    await refused.act(async () => refused.root.unmount());
    clearToasts();
  });

  test("an accepted record gives a prepare-only person no Personal control, on the card or in Más", async () => {
    const accepted = dossier({ facts_editable: false }, false, true, null, "accountant");
    const card = await mountCard(accepted, "accountant");
    assert.equal(card.host.querySelector('[data-testid="receipt-mark-personal"]'), null);
    await card.act(async () => card.root.unmount());
    const menu = await mountCard(accepted, "accountant", { bare: true });
    assert.equal(menu.host.querySelector<HTMLButtonElement>('[data-testid="receipt-mark-personal"]')?.disabled, true);
    await menu.act(async () => menu.root.unmount());
  });

  test("a read-only grant has no control", async () => {
    const page = await mountCard(dossier({ capabilities: ["read"], facts_editable: false } as Partial<BusinessDossier>, true, true, null, "accountant"), "accountant");
    assert.equal(page.host.querySelector('[data-testid="receipt-mark-personal"]'), null);
    assert.equal(page.host.querySelector('[data-testid="receipt-606-yes"]'), null);
    await page.act(async () => page.root.unmount());
  });

  test("the accountant with prepare marks Personal too, and sees Sí and No, 44px each, only for a personal receipt with a fiscal number", async () => {
    const page = await mountCard(dossier({ fiscal_inclusion_available: true }, true, true, null), "accountant");
    assert.equal(page.toggle().getAttribute("aria-checked"), "true", "the accountant holds the Personal switch too");
    assert.ok(!page.host.textContent?.includes("Solo el dueño"));
    assert.ok(page.host.textContent?.includes("¿Incluir en 606?"));
    const yes = page.host.querySelector('[data-testid="receipt-606-yes"]') as HTMLButtonElement;
    const no = page.host.querySelector('[data-testid="receipt-606-no"]') as HTMLButtonElement;
    assert.equal(yes.textContent, "Sí");
    assert.equal(no.textContent, "No");
    assert.ok(yes.className.includes("min-h-11") && no.className.includes("min-h-11"));
    await page.act(async () => { no.click(); });
    await page.settle();
    assert.deepEqual(page.calls, ["606:false:3"]);
    await page.act(async () => page.root.unmount());
    const answered = await mountCard(dossier({}, true, true, false), "accountant");
    assert.equal(answered.host.querySelector('[data-testid="receipt-606-state"]')?.textContent, "Fuera del 606 por Lía");
    assert.equal(answered.host.querySelector('[data-testid="receipt-606-yes"]'), null);
    await answered.act(async () => answered.root.unmount());
    const notPersonal = await mountCard(dossier({}, false, true, null), "accountant");
    assert.equal(notPersonal.host.querySelector('[data-testid="receipt-606"]'), null);
    await notPersonal.act(async () => notPersonal.root.unmount());
  });

  test("the 606 question shows only when the server says the caller may answer it, whatever the role reads like", async () => {
    const refused = await mountCard(dossier({ fiscal_inclusion_available: false }, true, true, null), "accountant");
    assert.equal(refused.host.querySelector('[data-testid="receipt-606-yes"]'), null, "a prepare-holder the server does not let answer gets no buttons");
    assert.equal(refused.host.querySelector('[data-testid="receipt-606-state"]')?.textContent, "Pendiente del contador");
    await refused.act(async () => refused.root.unmount());
    const older = await mountCard(dossier({}, true, true, null), "accountant");
    assert.equal(older.host.querySelector('[data-testid="receipt-606-yes"]'), null, "a server that sends no flag answers no");
    await older.act(async () => older.root.unmount());
  });

  describe("inside Más", () => {
    const row606 = (host: HTMLElement) => host.querySelector<HTMLButtonElement>('[data-testid="receipt-606"]');
    const switchOf = (row: HTMLElement) => row.querySelector("[data-switch-indicator]")?.getAttribute("data-switch-indicator");

    test("Personal is a 44px row with its icon and a small switch on the right; a tap anywhere on the row toggles it", async () => {
      const page = await mountCard(dossier({}, false, true), "owner", { bare: true });
      const personal = page.toggle();
      assert.equal(personal.getAttribute("role"), "menuitemcheckbox");
      assert.equal(personal.getAttribute("aria-checked"), "false");
      assert.ok(personal.className.includes("min-h-11"));
      assert.equal(personal.firstElementChild?.tagName.toLowerCase(), "svg");
      assert.equal(personal.lastElementChild?.getAttribute("data-switch-indicator"), "off", "the switch sits on the right");
      assert.equal(personal.querySelector('[role="switch"], button'), null, "the row is the one control");
      assert.equal(page.host.querySelector('[data-testid="record-marks"]'), null, "rows only, no chips");
      await page.act(async () => { (personal.querySelector("span span") as HTMLElement).click(); });
      await page.settle();
      assert.deepEqual(page.calls, ["mark:true:3"]);
      assert.equal(page.toggle().getAttribute("aria-checked"), "true");
      assert.equal(switchOf(page.toggle()), "on");
      const toast = page.host.querySelector('[data-testid="toast-viewport"]')!;
      assert.ok([...toast.querySelectorAll("button")].some((b) => b.textContent === "Deshacer"), "the saved change still offers Deshacer");
      await page.act(async () => page.root.unmount());
      const { clearToasts } = await import("@/components/business-app/foundation/toasts");
      clearToasts();
    });

    test("Incluir en el 606 shows only under Personal on, when the question applies; null and false show off, true shows on, with no other words", async () => {
      const off = await mountCard(dossier({ fiscal_inclusion_available: true }, false, true), "accountant", { bare: true });
      assert.equal(row606(off.host), null, "Personal off: no 606 row");
      await off.act(async () => off.root.unmount());
      const sale = await mountCard(dossier({ document_type: "venta", fiscal_question_applies: false, fiscal_inclusion_available: true }, true, true, null), "accountant", { bare: true });
      assert.equal(row606(sale.host), null, "the question does not apply: no 606 row");
      await sale.act(async () => sale.root.unmount());
      for (const [answer, shown] of [[null, "false"], [false, "false"], [true, "true"]] as const) {
        const page = await mountCard(dossier({ fiscal_inclusion_available: true }, true, true, answer), "accountant", { bare: true });
        const row = row606(page.host)!;
        assert.ok(row, `answer ${answer}: the row is there`);
        assert.equal(row.getAttribute("role"), "menuitemcheckbox");
        assert.equal(row.getAttribute("aria-checked"), shown, `answer ${answer}`);
        assert.equal(row.textContent, "Incluir en el 606");
        assert.equal(row.previousElementSibling, page.toggle(), "right under Personal");
        assert.ok(row.className.includes("min-h-11") && row.firstElementChild?.tagName.toLowerCase() === "svg");
        assert.ok(!/Pendiente del contador|Esperando al contable|Sin responder|¿/.test(page.host.textContent ?? ""), page.host.textContent ?? "");
        await page.act(async () => page.root.unmount());
      }
    });

    test("the person who may answer flips the 606 switch both ways through the same 606 answer", async () => {
      const page = await mountCard(dossier({ fiscal_inclusion_available: true }, true, true, null), "accountant", { bare: true });
      await page.act(async () => { row606(page.host)!.click(); });
      await page.settle();
      assert.equal(row606(page.host)!.getAttribute("aria-checked"), "true");
      await page.act(async () => { row606(page.host)!.click(); });
      await page.settle();
      assert.deepEqual(page.calls, ["606:true:3", "606:false:4"]);
      assert.equal(row606(page.host)!.getAttribute("aria-checked"), "false");
      await page.act(async () => page.root.unmount());
    });

    test("someone who cannot answer sees the 606 switch locked, with no words", async () => {
      for (const [who, record] of [
        ["the owner", dossier({ fiscal_inclusion_available: false }, true, true, true)],
        ["a read-only grant", dossier({ capabilities: ["read"], facts_editable: false, fiscal_inclusion_available: true } as Partial<BusinessDossier>, true, true, null, "accountant")],
      ] as const) {
        const page = await mountCard(record, who === "the owner" ? "owner" : "accountant", { bare: true });
        const row = row606(page.host)!;
        assert.ok(row, who);
        assert.equal(row.disabled, true, `${who}: locked`);
        assert.equal(row.textContent, "Incluir en el 606", who);
        await page.act(async () => row.click());
        await page.settle();
        assert.deepEqual(page.calls, [], `${who}: nothing is sent`);
        await page.act(async () => page.root.unmount());
      }
    });

    test("a refused 606 answer rolls the switch back and says so in the menu with Reintentar", async () => {
      let answer!: () => void;
      const page = await mountCard(dossier({ fiscal_inclusion_available: true }, true, true, null), "accountant", { bare: true, refuseAfter: new Promise<void>((done) => { answer = done; }) });
      await page.act(async () => { row606(page.host)!.click(); });
      assert.equal(row606(page.host)!.getAttribute("aria-checked"), "true", "flips before the server answers");
      assert.equal(row606(page.host)!.getAttribute("aria-busy"), "true");
      assert.equal(page.toggle().disabled, true, "Personal waits for the 606 answer");
      await page.act(async () => { answer(); });
      await page.settle();
      assert.equal(row606(page.host)!.getAttribute("aria-checked"), "false", "rolled back");
      const error = page.host.querySelector('[data-testid="receipt-marks-problem"]')!;
      assert.equal(error.getAttribute("role"), "alert");
      assert.ok(error.textContent?.includes("No pudimos guardar la respuesta."), error.textContent ?? "");
      const retry = [...error.querySelectorAll("button")].find((b) => b.textContent === "Reintentar");
      assert.ok(retry, "with Reintentar");
      await page.act(async () => retry.click());
      await page.settle();
      assert.deepEqual(page.calls, ["606:true:3", "606:true:3"], "Reintentar sends the same answer again");
      await page.act(async () => page.root.unmount());
    });
  });
});

describe("the review page's fiscal details", () => {
  async function facts(fiscal: Record<string, unknown> | null, lng: "es-419" | "en" = "es-419") {
    const env = await setup();
    if (lng === "en") {
      env.i18n.addResourceBundle("en", "translation", (await import("@/public/locales/en/common.json")).default);
      await env.i18n.changeLanguage("en");
    }
    const { default: ReceiptRecordFacts } = await import("@/components/business-app/ReceiptRecordFacts");
    const unknown = { state: "unknown", value: null, origin: null, verified: false, source_ids: [] };
    const ncf = fiscal && (fiscal as { ncf?: { state?: string } }).ncf?.state === "known";
    const d = { draft_id: "d-1", version: 1, capabilities: ["read"], blockers: [], questions: [], history: [], sources: [], fiscal_known: true, fiscal_value: ncf ? "ncf" : null, facts: { kind: unknown, amount: unknown, currency: unknown, occurred_on: unknown, counterparty: unknown, funding: unknown, business_share: unknown, receipt_state: unknown, category_id: unknown, fiscal } } as unknown as BusinessDossier;
    await env.act(async () => { env.root.render(<env.I18nextProvider i18n={env.i18n}><ReceiptRecordFacts dossier={d} accounts={[]} /></env.I18nextProvider>); });
    return env;
  }
  const unknown = { state: "unknown", value: null, origin: null, verified: false, source_ids: [] };

  test("a record without an NCF or an e-CF reads Sin comprobante fiscal in its fiscal row, never No registrado", async () => {
    for (const fiscal of [null, { rnc: unknown, ncf: unknown, ecf: unknown, itbis: unknown }]) {
      const env = await facts(fiscal);
      const section = env.host.querySelector('[data-testid="receipt-facts-comprobante"]')!;
      assert.ok(section, "the fiscal details are there");
      const row = section.querySelector('[data-fact="fiscal_number"]')!;
      assert.equal(row.firstElementChild?.textContent, "NCF");
      assert.equal(row.querySelector("[data-row-value]")?.textContent, "Sin comprobante fiscal");
      assert.equal(section.querySelector('[data-fact="ncf"]'), null);
      assert.equal(section.querySelector('[data-fact="ecf"]'), null);
      assert.ok(!/No registrado|Sin registrar|Not recorded/.test(section.textContent ?? ""));
      await env.act(async () => env.root.unmount());
    }
  });

  test("in English it reads No fiscal receipt number; a record with an NCF shows its number", async () => {
    const english = await facts(null, "en");
    assert.equal(english.host.querySelector('[data-fact="fiscal_number"] [data-row-value]')?.textContent, "No fiscal receipt number");
    await english.act(async () => english.root.unmount());
    const withNcf = await facts({ rnc: unknown, ncf: { state: "known", value: "B0100000001", origin: "extracted", verified: false, source_ids: ["s"] }, ecf: unknown, itbis: unknown });
    assert.equal(withNcf.host.querySelector('[data-fact="ncf"]'), null);
    assert.equal(withNcf.host.querySelector('[data-fact="fiscal_number"] [data-row-value]')?.textContent, "B0100000001");
    // A number the read suggested says so in the row's status slot.
    assert.equal(withNcf.host.querySelector('[data-testid="row-status-fiscal_number"]')?.getAttribute("data-status"), "reading");
    await withNcf.act(async () => withNcf.root.unmount());
  });
});

describe("one owner for the marks", () => {
  test("the card draws no chip for a grantee's mark, the owner's mark or after an unmark", async () => {
    const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
    const { default: ReceiptMarksCard } = await import("@/components/business-app/ReceiptMarksCard");
    const owner = { chosen: null, reload: () => undefined, source: {} } as unknown as BusinessContextValue;
    const cases: { name: string; personal: boolean; by: string | null }[] = [
      { name: "grantee mark", personal: true, by: "Marta" },
      { name: "owner mark", personal: true, by: null },
      { name: "unmarked", personal: false, by: null },
    ];
    for (const item of cases) {
      const server = { personal: item.personal, personal_marked_by: item.by ? { display_name: item.by, email: null, shown_as: "name" } : null, fiscal_value: "ncf" as const, include_606: null };
      const env = await setup();
      await env.act(async () => { env.root.render(<env.I18nextProvider i18n={env.i18n}><BusinessContext.Provider value={owner}><ReceiptMarksCard dossier={{ draft_id: "d-1", version: 3, capabilities: ["read", "prepare"], history: [], facts: { business_share: { state: "unknown", value: null, origin: null, verified: false, source_ids: [] }, fiscal: null }, ...server } as unknown as BusinessDossier} onChanged={() => undefined} /></BusinessContext.Provider></env.I18nextProvider>); });
      assert.equal(env.host.querySelector("[data-mark]"), null, item.name);
      assert.equal(env.host.textContent?.includes("Marcado por"), false, `${item.name}: no Marcado por`);
      await env.act(async () => env.root.unmount());
    }
  });
});

describe("the server states what the browser used to guess", () => {
  test("the 606 line names whoever answered, even when the owner edited the record afterwards", async () => {
    const env = await setup();
    const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
    const { default: ReceiptMarksCard } = await import("@/components/business-app/ReceiptMarksCard");
    const accountant = { chosen: { space_id: "s", name: "Colmado Peña", grant_id: "g", role: "accountant", capabilities: ["read", "prepare"], access_seen: true }, reload: () => undefined, source: {} } as unknown as BusinessContextValue;
    const ownerEdit = { draft_id: "d-1", version: 5, actor: { actor_id: "o", actor_kind: "member", display_name: "Dueño", shown_as: "name", grant_id: "own", issuer_id: "o", issuer_display_name: "Dueño", issuer_shown_as: "name" }, before: {}, after: {}, source_ids: [], turn_key: null, created_at: "2026-10-13T11:00:00Z" };
    const record = { draft_id: "d-1", version: 5, capabilities: ["read", "prepare"], history: [ownerEdit], facts: {}, personal: true, fiscal_known: true, fiscal_value: "ncf", fiscal_question_applies: true, include_606: false, include_606_by: { display_name: "Lía", email: null, shown_as: "name" } } as unknown as BusinessDossier;
    await env.act(async () => { env.root.render(<env.I18nextProvider i18n={env.i18n}><BusinessContext.Provider value={accountant}><ReceiptMarksCard dossier={record} onChanged={() => undefined} /></BusinessContext.Provider></env.I18nextProvider>); });
    assert.equal(env.host.querySelector('[data-testid="receipt-606-state"]')?.textContent, "Fuera del 606 por Lía");
    await env.act(async () => env.root.unmount());
  });

  test("the history reads a 606 answer as Sí or No, never true or false", async () => {
    const env = await setup();
    const { default: ReceiptHistory } = await import("@/components/business-app/ReceiptHistory");
    const unknown = { state: "unknown", value: null, origin: null, verified: false, source_ids: [] };
    const base = { kind: unknown, amount: unknown, currency: unknown, occurred_on: unknown, counterparty: unknown, funding: unknown, business_share: unknown, receipt_state: unknown, category_id: unknown };
    const fiscal = (answer: unknown) => ({ rnc: unknown, ncf: { state: "known", value: "B01", origin: "extracted", verified: false, source_ids: ["s"] }, ecf: unknown, itbis: unknown, include_606: answer });
    const revision = { draft_id: "d-1", version: 4, actor: { actor_id: "a", actor_kind: "member", display_name: "Lía", shown_as: "name", grant_id: "g", issuer_id: "o", issuer_display_name: "Dueño", issuer_shown_as: "name" }, before: { ...base, fiscal: fiscal(unknown) }, after: { ...base, fiscal: fiscal({ state: "known", value: true, origin: "member_set", verified: true, source_ids: ["s"] }) }, source_ids: ["s"], turn_key: null, created_at: "2026-10-13T10:00:00Z" };
    await env.act(async () => { env.root.render(<env.I18nextProvider i18n={env.i18n}><ReceiptHistory history={[revision] as never} accounts={[]} /></env.I18nextProvider>); });
    const text = env.host.textContent ?? "";
    assert.ok(text.includes("Sí"), text);
    assert.ok(!/\btrue\b|\bfalse\b/.test(text), text);
    assert.equal(env.host.querySelector('[data-testid="history-606"] p')?.textContent, "¿Incluir en 606? cambiado de Pendiente del contador a Sí");
    // A read that creates the record leaves the 606 open: no 606 row, never "Sin registrar".
    const created = { ...revision, version: 1, before: null, after: { ...base, fiscal: fiscal(unknown) } };
    await env.act(async () => { env.root.render(<env.I18nextProvider i18n={env.i18n}><ReceiptHistory history={[created] as never} accounts={[]} /></env.I18nextProvider>); });
    assert.equal(env.host.querySelector('[data-testid="history-606"]'), null);
    assert.ok(!(env.host.textContent ?? "").includes("Incluir en 606"));
    await env.act(async () => env.root.unmount());
  });
});
