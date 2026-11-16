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
  const { ReceiptDuplicateCompare, ReceiptDuplicateResolution, useDuplicateCompare } = await import("@/components/business-app/ReceiptDuplicateCompare");
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { dossierFixtureIds } = await import("@/components/business-app/dossier-fixtures");
  const fixture = await createFixtureBusinessDataSource().dossier(dossierFixtureIds.ready);
  const initial: BusinessDossier = {
    ...fixture, draft_id: "draft-new", version: 7,
    review_state: options.closed ? "accepted" : "open",
    capabilities: ["read", "prepare", "approve"],
    blockers: [{ code: "possible_duplicate", field: null }, { code: "fact_required", field: "funding" }],
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
        : <section data-testid="frame"><p data-testid="review-form">Formulario</p><ReceiptDuplicateResolution dossier={dossier} busy={busy || options.externalBusy} onCompare={compare.open} /></section>}
    </BusinessContext.Provider></I18nextProvider>;
  }
  await act(async () => { root.render(<View />); });
  const flush = () => act(async () => { for (let turn = 0; turn < 3; turn += 1) await new Promise((resolve) => setTimeout(resolve, 0)); });
  const box = () => host.querySelector<HTMLElement>('[data-testid="receipt-duplicate-resolution"]');
  const view = () => host.querySelector<HTMLElement>('[data-testid="duplicate-compare"]');
  const button = (name: string) => Array.from(host.querySelectorAll<HTMLButtonElement>("button")).find((item) => item.textContent?.trim() === name);
  const footerButtons = () => Array.from(host.querySelectorAll<HTMLButtonElement>('[data-testid="frame-footer"] button')).map((item) => item.textContent?.trim());
  const row = (field: BusinessComparedField) => host.querySelector<HTMLElement>(`[data-testid="duplicate-compare-row"][data-field="${field}"]`);
  const compare = async () => { await act(async () => { button("Comparar")?.click(); }); await flush(); };
  return { host, requests, fetchedSources, deleted, act, flush, release, box, view, button, footerButtons, row, compare, cleanup: async () => {
    release();
    await act(async () => { root.unmount(); });
    host.remove();
    globalThis.fetch = oldFetch;
  } };
}

const PRIMARY = "bg-[var(--cuadrao-green)]";
const DANGER_FILL = "bg-[#9e2f39]";
const sent = (ui: { requests: { options?: RequestInit }[] }, index = 0) => JSON.parse(String(ui.requests[index].options?.body));

test("the box says Parece repetido, why, and offers only Comparar", async () => {
  const ui = await mount();
  try {
    const box = ui.box();
    assert.ok(box);
    assert.match(box.textContent ?? "", /Parece repetido/);
    assert.ok(box.querySelector('[data-testid="duplicate-basis"]')?.textContent);
    assert.deepEqual(Array.from(box.querySelectorAll("button")).map((item) => item.textContent?.trim()), ["Comparar"]);
    assert.equal(ui.button("Son compras distintas"), undefined);
    assert.equal(ui.button("Eliminar este duplicado"), undefined);
    assert.equal(ui.requests.length, 0);
  } finally { await ui.cleanup(); }
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
  test(`no box for ${Object.keys(options)[0]}`, async () => {
    const ui = await mount("success", options);
    try {
      assert.equal(ui.box(), null);
      assert.equal(ui.button("Comparar"), undefined);
    } finally { await ui.cleanup(); }
  });
}

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
