import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import type { BusinessComparedField, BusinessDossier, BusinessDuplicateCandidate, BusinessDuplicateDecision } from "@/lib/business-dossier";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

type Mode = "success" | "deleted" | "error" | "stale" | "hold";
type Options = {
  closed?: boolean;
  noCandidates?: boolean;
  externalBusy?: boolean;
  decisions?: BusinessDuplicateDecision[];
  recommendation?: BusinessDuplicateDecision | null;
  differences?: BusinessComparedField[];
  basis?: BusinessDuplicateCandidate["basis"];
  /** The server's blockers; by default the duplicate and a missing funding answer. */
  blockers?: BusinessDossier["blockers"];
};

function candidate(options: Options): BusinessDuplicateCandidate {
  const recommendation = options.recommendation === undefined ? "different_purchase" : options.recommendation;
  return {
    draft_id: "draft-original",
    version: 3,
    basis: options.basis ?? "read_facts",
    decisions: options.decisions ?? ["different_purchase", "same_purchase"],
    comparison: {
      document: { draft_id: "draft-new", counterparty: "Ferretería Ochoa", occurred_on: "2026-11-03", amount: "1180.00", currency: "DOP", fiscal_number: recommendation === "same_purchase" ? "B0100000123" : "B0100000456", file: { connection_id: "file-new", filename: "factura-nueva.pdf", media_type: "application/pdf" }, received_at: "2026-11-04T12:00:00Z", approved_at: null },
      other: { draft_id: "draft-original", counterparty: "Ferretería Ochoa", occurred_on: "2026-11-03", amount: "1180.00", currency: "DOP", fiscal_number: recommendation === null ? null : "B0100000123", file: { connection_id: "file-original", filename: "factura.pdf", media_type: "application/pdf" }, received_at: "2026-11-03T12:00:00Z", approved_at: null },
      differences: options.differences ?? (recommendation === "same_purchase" ? ["file"] : ["fiscal_number", "file"]),
      recommendation,
    },
  };
}

async function mount(mode: Mode = "success", options: Options = {}) {
  const { act, useState } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { ReceiptDuplicateCompare, useDuplicateCompare } = await import("@/components/business-app/ReceiptDuplicateCompare");
  const { default: DossierAttentionStrip } = await import("@/components/business-app/DossierAttentionStrip");
  const { dossierAttention } = await import("@/components/business-app/dossier-attention");
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { dossierFixtureIds } = await import("@/components/business-app/dossier-fixtures");
  const fixture = await createFixtureBusinessDataSource().dossier(dossierFixtureIds.ready);
  const initial: BusinessDossier = {
    ...fixture, draft_id: "draft-new", version: 7,
    review_state: options.closed ? "accepted" : "open",
    capabilities: ["read", "prepare", "approve"],
    blockers: options.blockers ?? [{ code: "possible_duplicate", field: null }, { code: "fact_required", field: "funding" }],
    approval_available: false,
    duplicate_candidates: options.noCandidates ? [] : [candidate(options)],
  };
  const next: BusinessDossier = mode === "deleted"
    ? { ...initial, version: 8, duplicate_candidates: [], deleted: { actor: { actor_id: "owner", display_name: "Dueña" }, at: "2026-11-16T12:00:00Z", purge_at: "2026-11-23T12:00:00Z", key: "key", previous_state: { state: "open", group: "attention" } } }
    : { ...initial, version: 8, blockers: [{ code: "fact_required", field: "funding" }], duplicate_candidates: [] };
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const requests: { url: string; options?: RequestInit }[] = [];
  const fetchedSources: string[] = [];
  const deleted: string[] = [];
  const oldFetch = globalThis.fetch;
  let release = () => {};
  const hold = new Promise<void>((resolve) => { release = resolve; });
  globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    requests.push({ url: String(input), options: init });
    if (mode === "hold") await hold;
    if (mode === "error") throw new Error("Synthetic offline transport");
    return new Response(JSON.stringify(mode === "stale" ? { code: "stale_version" } : next), { status: mode === "stale" ? 409 : 200, headers: { "Content-Type": "application/json" } });
  };
  const context = {
    source: { mode: "live", receiptSource: async (id: string) => { fetchedSources.push(id); return new Blob(["%PDF-1.4"], { type: "application/pdf" }); } },
    openPanel: () => undefined,
    reload: () => undefined,
  } as unknown as BusinessContextValue;
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  function View() {
    const [dossier, setDossier] = useState(initial);
    const [busy, setBusy] = useState(false);
    const compare = useDuplicateCompare(dossier);
    return <I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}>
      {compare.candidate
        ? <ReceiptDuplicateCompare dossier={dossier} candidate={compare.candidate} busy={busy || options.externalBusy} onBack={compare.back} onBusyChange={setBusy} onChanged={setDossier} onDeleted={(gone) => deleted.push(gone.draft_id)} frame={(body, footer) => <section data-testid="frame">{body}<footer data-testid="frame-footer">{footer}</footer></section>} />
        : <section data-testid="frame"><DossierAttentionStrip items={dossierAttention(dossier, i18n.t.bind(i18n), "es-419")} onCompare={compare.open} compareDisabled={busy || options.externalBusy} /><p data-testid="review-form">Formulario</p></section>}
    </BusinessContext.Provider></I18nextProvider>;
  }
  await act(async () => { root.render(<View />); });
  const flush = () => act(async () => { for (let turn = 0; turn < 3; turn += 1) await new Promise((resolve) => setTimeout(resolve, 0)); });
  const strip = () => host.querySelector<HTMLElement>('[data-testid="dossier-attention"]');
  const box = () => host.querySelector<HTMLElement>('[data-testid="dossier-attention"] [data-testid="duplicate-entry"]');
  const view = () => host.querySelector<HTMLElement>('[data-testid="duplicate-compare"]');
  const button = (name: string) => Array.from(host.querySelectorAll<HTMLButtonElement>("button")).find((item) => item.textContent?.trim() === name);
  const footerButtons = () => Array.from(host.querySelectorAll<HTMLButtonElement>('[data-testid="frame-footer"] button')).map((item) => item.textContent?.trim());
  const row = (field: BusinessComparedField) => host.querySelector<HTMLElement>(`[data-testid="duplicate-compare-row"][data-field="${field}"]`);
  const compare = async () => { await act(async () => { button("Comparar")?.click(); }); await flush(); };
  return { host, requests, fetchedSources, deleted, act, flush, release, strip, box, view, button, footerButtons, row, compare, cleanup: async () => {
    release();
    await act(async () => { root.unmount(); });
    host.remove();
    globalThis.fetch = oldFetch;
  } };
}

const PRIMARY = "bg-[var(--cuadrao-green)]";
const DANGER_FILL = "bg-[#9e2f39]";
const sent = (ui: { requests: { options?: RequestInit }[] }, index = 0) => JSON.parse(String(ui.requests[index].options?.body));
const repeats = (node: Element | null) => (node?.textContent ?? "").match(/Parece repetido/g)?.length ?? 0;

test("the top box lists Parece repetido once, with why and only Comparar, among the other blockers", async () => {
  const ui = await mount();
  try {
    const box = ui.box();
    assert.ok(box);
    assert.match(box.textContent ?? "", /Parece repetido/);
    assert.equal(repeats(ui.host), 1);
    assert.ok(box.querySelector('[data-testid="duplicate-basis"]')?.textContent);
    assert.deepEqual(Array.from(box.querySelectorAll("button")).map((item) => item.textContent?.trim()), ["Comparar"]);
    assert.ok(ui.strip()?.querySelector('[data-field="funding"] button'), "the other blocker still renders");
    assert.doesNotMatch(ui.host.textContent ?? "", /Parece un recibo/);
    assert.equal(ui.button("Son compras distintas"), undefined);
    assert.equal(ui.button("Eliminar este duplicado"), undefined);
    assert.equal(ui.requests.length, 0);
  } finally { await ui.cleanup(); }
});

test("alone, the duplicate is the box: Parece repetido, its line and Comparar", async () => {
  const blocked = await mount("success", { blockers: [{ code: "possible_duplicate", field: null }] });
  // An RNC and NCF pair adds no blocker; the server still lists it, so it still shows here.
  const fiscal = await mount("success", { blockers: [], basis: "fiscal_number" });
  try {
    for (const ui of [blocked, fiscal]) {
      assert.equal(ui.strip()?.querySelector("h3")?.textContent, "Parece repetido");
      assert.equal(repeats(ui.host), 1);
      assert.equal(ui.host.querySelectorAll('[data-testid="duplicate-basis"]').length, 1);
      assert.deepEqual(Array.from(ui.strip()!.querySelectorAll("button")).map((item) => item.textContent?.trim()), ["Comparar"]);
    }
  } finally { await blocked.cleanup(); await fiscal.cleanup(); }
});

test("the box line follows the server's basis", async () => {
  const facts = await mount();
  const fiscal = await mount("success", { basis: "fiscal_number" });
  try {
    const read = facts.box()?.querySelector('[data-testid="duplicate-basis"]')?.textContent;
    const number = fiscal.box()?.querySelector('[data-testid="duplicate-basis"]')?.textContent;
    assert.ok(read && number);
    assert.notEqual(read, number);
    assert.match(number, /RNC/);
    assert.match(number, /NCF/);
  } finally { await facts.cleanup(); await fiscal.cleanup(); }
});

test("Comparar turns the panel into the compare view with both documents in the existing preview", async () => {
  const ui = await mount();
  try {
    await ui.compare();
    assert.equal(ui.box(), null);
    assert.equal(ui.host.querySelector('[data-testid="review-form"]'), null);
    assert.ok(ui.view());
    assert.equal(ui.host.querySelectorAll('[data-testid="frame"]').length, 1);
    assert.equal(ui.host.querySelectorAll('[data-testid="receipt-original-source"]').length, 2);
    assert.deepEqual(ui.fetchedSources.sort(), ["file-new", "file-original"]);
    assert.match(ui.view()?.textContent ?? "", /factura-nueva\.pdf/);
    assert.match(ui.view()?.textContent ?? "", /factura\.pdf/);
    assert.equal(document.activeElement?.getAttribute("data-testid"), "duplicate-compare-title");
  } finally { await ui.cleanup(); }
});

test("the diff shows both documents' values and marks each row as the server's differences say", async () => {
  const ui = await mount("success", { differences: ["amount", "file"] });
  try {
    await ui.compare();
    const rows = Array.from(ui.host.querySelectorAll<HTMLElement>('[data-testid="duplicate-compare-row"]')).map((item) => item.dataset.field);
    assert.deepEqual(rows, ["counterparty", "occurred_on", "amount", "currency", "fiscal_number", "file"]);
    for (const field of ["counterparty", "occurred_on", "currency", "fiscal_number"] as const) {
      assert.equal(ui.row(field)?.dataset.state, "same");
      assert.match(ui.row(field)?.textContent ?? "", /Igual/);
    }
    for (const field of ["amount", "file"] as const) {
      assert.equal(ui.row(field)?.dataset.state, "different");
      assert.match(ui.row(field)?.textContent ?? "", /Diferente/);
    }
    assert.match(ui.row("counterparty")?.textContent ?? "", /Ferretería Ochoa/);
    assert.match(ui.row("fiscal_number")?.textContent ?? "", /B0100000456/);
    assert.match(ui.row("fiscal_number")?.textContent ?? "", /B0100000123/);
    assert.match(ui.row("currency")?.textContent ?? "", /DOP/);
  } finally { await ui.cleanup(); }
});

test("a different NCF recommends two purchases and makes Son compras distintas the primary action", async () => {
  const ui = await mount("success", { recommendation: "different_purchase" });
  try {
    await ui.compare();
    assert.match(ui.view()?.textContent ?? "", /Mismo comercio, fecha, total y moneda\. El NCF es distinto: probablemente son dos compras distintas\./);
    assert.ok(ui.button("Son compras distintas")?.className.includes(PRIMARY));
    assert.ok(!ui.button("Eliminar este duplicado")?.className.includes(DANGER_FILL));
    assert.deepEqual(ui.footerButtons(), ["Volver", "Eliminar este duplicado", "Son compras distintas"]);
  } finally { await ui.cleanup(); }
});

test("the same NCF says it is the same document and makes Eliminar este duplicado the primary action", async () => {
  const ui = await mount("success", { recommendation: "same_purchase" });
  try {
    await ui.compare();
    assert.match(ui.host.querySelector('[data-testid="duplicate-recommendation"]')?.textContent ?? "", /Es el mismo documento/);
    assert.ok(ui.button("Eliminar este duplicado")?.className.includes(DANGER_FILL));
    assert.ok(!ui.button("Son compras distintas")?.className.includes(PRIMARY));
    assert.deepEqual(ui.footerButtons(), ["Volver", "Son compras distintas", "Eliminar este duplicado"]);
  } finally { await ui.cleanup(); }
});

test("with no NCF there is no recommendation and no primary action", async () => {
  const ui = await mount("success", { recommendation: null });
  try {
    await ui.compare();
    assert.equal(ui.host.querySelector('[data-testid="duplicate-recommendation"]'), null);
    assert.ok(!ui.button("Son compras distintas")?.className.includes(PRIMARY));
    assert.ok(!ui.button("Eliminar este duplicado")?.className.includes(DANGER_FILL));
  } finally { await ui.cleanup(); }
});

for (const [decisions, shown] of [
  [["same_purchase"], ["Volver", "Eliminar este duplicado"]],
  [["different_purchase"], ["Volver", "Son compras distintas"]],
  [[], ["Volver"]],
] as const) {
  test(`only the decisions the server lists render: ${decisions.join(", ") || "none"}`, async () => {
    const ui = await mount("success", { decisions: [...decisions], recommendation: "same_purchase" });
    try {
      await ui.compare();
      assert.deepEqual(ui.footerButtons(), shown);
    } finally { await ui.cleanup(); }
  });
}

test("someone who is not the owner gets no Eliminar, because the server does not list it", async () => {
  const ui = await mount("success", { decisions: ["different_purchase"], recommendation: "same_purchase" });
  try {
    await ui.compare();
    assert.equal(ui.button("Eliminar este duplicado"), undefined);
  } finally { await ui.cleanup(); }
});

test("Volver returns to the review with the box and its Comparar", async () => {
  const ui = await mount();
  try {
    await ui.compare();
    await ui.act(async () => { ui.button("Volver")?.click(); });
    await ui.flush();
    assert.equal(ui.view(), null);
    assert.ok(ui.host.querySelector('[data-testid="review-form"]'));
    assert.ok(ui.box());
    assert.equal(ui.requests.length, 0);
  } finally { await ui.cleanup(); }
});

test("Eliminar este duplicado sends same_purchase with both versions and hands off the deleted document", async () => {
  const ui = await mount("deleted", { recommendation: "same_purchase" });
  try {
    await ui.compare();
    await ui.act(async () => { ui.button("Eliminar este duplicado")?.click(); });
    await ui.flush();
    assert.equal(ui.requests.length, 1);
    assert.match(ui.requests[0].url, /\/business\/drafts\/draft-new\/duplicate-resolution$/);
    assert.equal(ui.requests[0].options?.method, "POST");
    assert.deepEqual(sent(ui), { version: 7, other_draft_id: "draft-original", other_version: 3, decision: "same_purchase" });
    assert.deepEqual(ui.deleted, ["draft-new"]);
  } finally { await ui.cleanup(); }
});

test("Son compras distintas sends different_purchase and the server's answer closes the compare view", async () => {
  const ui = await mount();
  try {
    await ui.compare();
    await ui.act(async () => { ui.button("Son compras distintas")?.click(); });
    await ui.flush();
    assert.deepEqual(sent(ui), { version: 7, other_draft_id: "draft-original", other_version: 3, decision: "different_purchase" });
    assert.equal(ui.view(), null);
    assert.equal(ui.box(), null);
    assert.ok(ui.strip()?.querySelector('[data-field="funding"]'), "the blocker left stays in the box");
    assert.ok(ui.host.querySelector('[data-testid="review-form"]'));
    assert.deepEqual(ui.deleted, []);
  } finally { await ui.cleanup(); }
});

test("in flight every decision is disabled and a second click cannot write", async () => {
  const ui = await mount("hold");
  try {
    await ui.compare();
    await ui.act(async () => { ui.button("Son compras distintas")?.click(); ui.button("Son compras distintas")?.click(); ui.button("Eliminar este duplicado")?.click(); });
    assert.equal(ui.requests.length, 1);
    assert.equal(ui.view()?.getAttribute("aria-busy"), "true");
    assert.ok(Array.from(ui.host.querySelectorAll<HTMLButtonElement>('[data-testid="frame-footer"] button')).every((item) => item.disabled));
    ui.release();
    await ui.flush();
  } finally { await ui.cleanup(); }
});

for (const mode of ["error", "stale"] as const) {
  test(`${mode} keeps the compare view with an alert; a retry repeats the same key and body`, async () => {
    const ui = await mount(mode);
    try {
      await ui.compare();
      await ui.act(async () => { ui.button("Son compras distintas")?.click(); });
      await ui.flush();
      assert.ok(ui.view());
      assert.ok(ui.host.querySelector('[role="alert"]'));
      await ui.act(async () => { ui.button("Son compras distintas")?.click(); });
      await ui.flush();
      assert.equal(ui.requests.length, 2);
      assert.deepEqual(ui.requests[0].options?.headers, ui.requests[1].options?.headers);
      assert.deepEqual(ui.requests[0].options?.body, ui.requests[1].options?.body);
    } finally { await ui.cleanup(); }
  });
}

for (const options of [{ closed: true }, { noCandidates: true }] as const) {
  test(`no Comparar for ${Object.keys(options)[0]}; the server's blocker still says Parece repetido`, async () => {
    const ui = await mount("success", options);
    try {
      assert.equal(ui.button("Comparar"), undefined);
      assert.equal(ui.host.querySelectorAll('[data-testid="duplicate-basis"]').length, 0);
      assert.equal(repeats(ui.strip()), 1);
      assert.doesNotMatch(ui.host.textContent ?? "", /Parece un recibo/);
    } finally { await ui.cleanup(); }
  });
}

test("no candidate and no blocker: nothing about a duplicate", async () => {
  const ui = await mount("success", { noCandidates: true, blockers: [{ code: "fact_required", field: "funding" }] });
  try {
    assert.equal(ui.box(), null);
    assert.equal(repeats(ui.host), 0);
  } finally { await ui.cleanup(); }
});

test("while the review is busy Comparar waits", async () => {
  const ui = await mount("success", { externalBusy: true });
  try {
    assert.ok(ui.button("Comparar")?.disabled);
    await ui.compare();
    assert.equal(ui.view(), null);
  } finally { await ui.cleanup(); }
});

test("the duplicate transport sends the decision it was given", async () => {
  const { resolveBusinessDuplicate } = await import("@/lib/business-api");
  const oldFetch = globalThis.fetch;
  const bodies: unknown[] = [];
  globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    bodies.push(JSON.parse(String(init?.body)));
    return new Response(JSON.stringify({}), { headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;
  try {
    for (const decision of ["same_purchase", "different_purchase"] as const) {
      await resolveBusinessDuplicate("draft-new", 7, "draft-original", 3, decision, `key-${decision}`).catch(() => undefined);
    }
    assert.deepEqual(bodies, [
      { version: 7, other_draft_id: "draft-original", other_version: 3, decision: "same_purchase" },
      { version: 7, other_draft_id: "draft-original", other_version: 3, decision: "different_purchase" },
    ]);
  } finally { globalThis.fetch = oldFetch; }
});

test("in the review panel the one Parece repetido sits in the top box with Comparar, and Comparar opens the compare view", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const { liveBusinessDataSource } = await import("@/components/business-app/business-data");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { dossierFixtureIds } = await import("@/components/business-app/dossier-fixtures");
  const { default: Review } = await import("@/components/business-app/ReceiptDossierReview");
  const fixture = await createFixtureBusinessDataSource().dossier(dossierFixtureIds.ready);
  const dossier: BusinessDossier = {
    ...fixture, draft_id: "draft-new", version: 7, review_state: "open",
    capabilities: ["read", "prepare", "approve"],
    blockers: [{ code: "fact_required", field: "funding" }, { code: "possible_duplicate", field: null }],
    approval_available: false,
    duplicate_candidates: [candidate({})],
  };
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const oldFetch = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL) => new URL(String(input)).pathname.endsWith("/business/drafts/draft-new/dossier")
    ? Response.json(dossier)
    : Response.json({ code: "not_found" }, { status: 404 })) as typeof fetch;
  const context = {
    source: liveBusinessDataSource,
    reload: () => undefined,
    records: { inbox: [], notes: [], notesError: false, notesTruncated: false, error: false, workspace: null },
    openPanel: () => undefined,
    actions: { create: [] },
    panel: { kind: "inbox" },
    revision: 0,
  } as unknown as BusinessContextValue;
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const settle = async () => { for (let turn = 0; turn < 5; turn += 1) await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); }); };
  try {
    await act(async () => { root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}><Review draftId="draft-new" /></BusinessContext.Provider></I18nextProvider>); });
    await settle();
    const strip = host.querySelector<HTMLElement>('[data-testid="dossier-attention"]');
    assert.ok(strip, "the top box is there");
    assert.equal(repeats(host), 1, "one Parece repetido on the whole panel");
    assert.equal(repeats(strip), 1, "and it is in the top box");
    assert.doesNotMatch(host.textContent ?? "", /Parece un recibo/);
    assert.equal(host.querySelector('[data-testid="receipt-duplicate-resolution"]'), null, "no second box lower down");
    const firstRow = host.querySelector('[data-fact]');
    assert.ok(firstRow && strip.compareDocumentPosition(firstRow) & Node.DOCUMENT_POSITION_FOLLOWING, "the box sits above the rows");
    assert.ok(strip.querySelector('[data-field="funding"] button'), "the other blocker still renders");
    const comparar = Array.from(strip.querySelectorAll<HTMLButtonElement>('[data-testid="duplicate-entry"] button'));
    assert.deepEqual(comparar.map((item) => item.textContent?.trim()), ["Comparar"]);
    await act(async () => { comparar[0].click(); });
    await settle();
    assert.ok(host.querySelector('[data-testid="duplicate-compare"]'), "Comparar opens the compare view");
    assert.equal(host.querySelector('[data-testid="dossier-attention"]'), null);
  } finally {
    await act(async () => { root.unmount(); });
    host.remove();
    globalThis.fetch = oldFetch;
  }
});

for (const outcome of ["settled", "failed"] as const) {
  test(`in the review panel, Son compras distintas ${outcome === "settled" ? "returns to the review with a toast, no amber entry and Aprobar ready" : "that fails keeps the compare view and retries with the same key"}`, async () => {
    const { act } = await import("react");
    const { createRoot } = await import("react-dom/client");
    const i18next = (await import("i18next")).default;
    const { I18nextProvider } = await import("react-i18next");
    const spanish = (await import("@/public/locales/es-419/common.json")).default;
    const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
    const { liveBusinessDataSource } = await import("@/components/business-app/business-data");
    const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
    const { dossierFixtureIds } = await import("@/components/business-app/dossier-fixtures");
    const { clearToasts, useToasts } = await import("@/components/business-app/foundation/toasts");
    const { default: Review } = await import("@/components/business-app/ReceiptDossierReview");
    const fixture = await createFixtureBusinessDataSource().dossier(dossierFixtureIds.ready);
    const dossier: BusinessDossier = {
      ...fixture, draft_id: "draft-new", version: 7, review_state: "open",
      capabilities: ["read", "prepare", "approve"],
      blockers: [{ code: "possible_duplicate", field: null }],
      approval_available: false,
      duplicate_candidates: [candidate({})],
    };
    const settled: BusinessDossier = { ...dossier, version: 8, blockers: [], approval_available: true, duplicate_candidates: [] };
    const i18n = i18next.createInstance();
    await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
    const decisions: RequestInit[] = [];
    const oldFetch = globalThis.fetch;
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(String(input)).pathname;
      if (path.endsWith("/business/drafts/draft-new/dossier")) return Response.json(dossier);
      if (path.endsWith("/business/drafts/draft-new/duplicate-resolution")) {
        decisions.push(init ?? {});
        if (outcome === "failed") throw new Error("Synthetic offline transport");
        return Response.json(settled);
      }
      return Response.json({ code: "not_found" }, { status: 404 });
    }) as typeof fetch;
    const context = {
      source: liveBusinessDataSource,
      reload: () => undefined,
      records: { inbox: [], notes: [], notesError: false, notesTruncated: false, error: false, workspace: null },
      openPanel: () => undefined,
      actions: { create: [] },
      panel: { kind: "inbox" },
      revision: 0,
    } as unknown as BusinessContextValue;
    function Toasts() { return <p data-testid="toasts">{useToasts().map((toast) => toast.text).join("|")}</p>; }
    clearToasts();
    const host = document.createElement("div");
    document.body.append(host);
    const root = createRoot(host);
    const settle = async () => { for (let turn = 0; turn < 5; turn += 1) await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); }); };
    const button = (name: string) => Array.from(host.querySelectorAll<HTMLButtonElement>("button")).find((item) => item.textContent?.trim() === name);
    try {
      await act(async () => { root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}><Review draftId="draft-new" /><Toasts /></BusinessContext.Provider></I18nextProvider>); });
      await settle();
      assert.ok(button("Aprobar")?.disabled, "the duplicate blocks Aprobar before the decision");
      await act(async () => { button("Comparar")?.click(); });
      await settle();
      await act(async () => { button("Son compras distintas")?.click(); });
      await settle();
      const toasts = () => host.querySelector('[data-testid="toasts"]')?.textContent;
      if (outcome === "settled") {
        assert.equal(host.querySelector('[data-testid="duplicate-compare"]'), null, "the compare view closed");
        assert.equal(host.querySelector('[data-testid="duplicate-entry"]'), null, "no amber Parece repetido entry");
        assert.equal(repeats(host.querySelector('[data-testid="dossier-attention"]')), 0);
        assert.equal(toasts(), "[PENDIENTE COPY] Marcado como compras distintas.");
        const approve = button("Aprobar");
        assert.ok(approve && !approve.disabled, "Aprobar is ready");
        assert.equal(document.activeElement, approve, "focus is on the review's main action");
        assert.equal(decisions.length, 1);
      } else {
        assert.ok(host.querySelector('[data-testid="duplicate-compare"]'), "the compare view stays");
        assert.ok(host.querySelector('[data-testid="duplicate-compare"] ~ * [role="alert"], [role="alert"]'));
        assert.equal(toasts(), "");
        await act(async () => { button("Son compras distintas")?.click(); });
        await settle();
        assert.equal(decisions.length, 2);
        assert.deepEqual(decisions[0].headers, decisions[1].headers);
        assert.equal(decisions[0].body, decisions[1].body);
      }
    } finally {
      await act(async () => { root.unmount(); });
      host.remove();
      clearToasts();
      globalThis.fetch = oldFetch;
    }
  });
}
