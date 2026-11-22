import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import type { BusinessComparedField, BusinessDossier, BusinessDuplicateCandidate, BusinessDuplicateDecision, ListoGap } from "@/lib/business-dossier";
import { formatTimestamp } from "@/components/business-app/business-format";

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
  decisions?: BusinessDuplicateDecision[];
  recommendation?: BusinessDuplicateDecision | null;
  differences?: BusinessDuplicateCandidate["comparison"]["differences"];
  basis?: BusinessDuplicateCandidate["basis"];
  /** The other document is already approved. */
  approved?: boolean;
  /** The server's blockers; by default the duplicate and a missing funding answer. */
  blockers?: BusinessDossier["blockers"];
  /** The server's gaps for them; by default the duplicate and the blockers. */
  gaps?: ListoGap[];
};

/** What the server says of an open record with these gaps, or of an accepted one. */
function standing(gaps: readonly ListoGap[], accepted = false): Pick<BusinessDossier, "listo_gaps" | "bandeja_group"> {
  if (accepted) return { listo_gaps: [], bandeja_group: { group: null, reason: null, label: "accepted" } };
  return gaps.length
    ? { listo_gaps: gaps, bandeja_group: { group: "attention", reason: gaps[0], label: "needs_attention" } }
    : { listo_gaps: [], bandeja_group: { group: "listo", reason: null, label: "ready" } };
}

function candidate(options: Options): BusinessDuplicateCandidate {
  const recommendation = options.recommendation === undefined ? "different_purchase" : options.recommendation;
  return {
    draft_id: "draft-original",
    version: 3,
    basis: options.basis ?? "read_facts",
    decisions: options.decisions ?? ["different_purchase", "same_purchase"],
    comparison: {
      document: { draft_id: "draft-new", counterparty: "Ferretería Ochoa", occurred_on: "2026-11-03", amount: "1180.00", currency: "DOP", fiscal_number: recommendation === "same_purchase" ? "B0100000123" : "B0100000456", file: { connection_id: "file-new", filename: "factura-nueva.pdf", media_type: "application/pdf", channel: "web", received_at: "2026-11-04T12:00:00Z" }, received_at: "2026-11-04T12:00:00Z", approved_at: null, state: "open" },
      other: { draft_id: "draft-original", counterparty: "Ferretería Ochoa", occurred_on: "2026-11-03", amount: "1180.00", currency: "DOP", fiscal_number: recommendation === null ? null : "B0100000123", file: { connection_id: "file-original", filename: "factura.pdf", media_type: "application/pdf", channel: "whatsapp", received_at: "2026-11-03T12:00:00Z" }, received_at: "2026-11-03T12:00:00Z", approved_at: options.approved ? "2026-11-03T15:00:00Z" : null, state: options.approved ? "accepted" : "open" },
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
  const { DossierStatus } = await import("@/components/business-app/dossier/DossierHeader");
  const { dossierProblems } = await import("@/components/business-app/dossier-attention");
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { dossierFixtureIds } = await import("@/components/business-app/dossier-fixtures");
  const fixture = await createFixtureBusinessDataSource().dossier(dossierFixtureIds.ready);
  const initial: BusinessDossier = {
    ...fixture, draft_id: "draft-new", version: 7,
    review_state: options.closed ? "accepted" : "open",
    capabilities: ["read", "prepare", "approve"],
    blockers: options.blockers ?? [{ code: "possible_duplicate", field: null }, { code: "fact_required", field: "funding" }],
    ...standing(options.gaps ?? ["duplicate", "blocked"], options.closed),
    approval_available: false,
    duplicate_candidates: options.noCandidates ? [] : [candidate(options)],
  };
  const next: BusinessDossier = mode === "deleted"
    ? { ...initial, version: 8, duplicate_candidates: [], deleted: { actor: { actor_id: "owner", display_name: "Dueña" }, at: "2026-11-16T12:00:00Z", purge_at: "2026-11-23T12:00:00Z", key: "key", previous_state: { state: "open", group: "attention" } } }
    : { ...initial, version: 8, blockers: [{ code: "fact_required", field: "funding" }], ...standing(["blocked"]), duplicate_candidates: [] };
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
    // As the review panel wires its header: a problem that names a document to compare opens Comparar.
    const problems = dossierProblems(dossier, i18n.t.bind(i18n));
    return <I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}>
      {compare.candidate
        ? <ReceiptDuplicateCompare dossier={dossier} candidate={compare.candidate} busy={busy} onBack={compare.back} onBusyChange={setBusy} onChanged={(next) => { setDossier(next); compare.settled(); }} onDeleted={(gone) => deleted.push(gone.draft_id)} frame={(body, footer) => <section data-testid="frame">{body}<footer data-testid="frame-footer">{footer}</footer></section>} />
        : <section data-testid="frame"><DossierStatus label={dossier.bandeja_group?.label} problems={problems} onProblem={(problem) => { if (problem.compare) compare.open(problem.compare); }} /><p data-testid="review-form">Formulario</p></section>}
    </BusinessContext.Provider></I18nextProvider>;
  }
  await act(async () => { root.render(<View />); });
  const flush = () => act(async () => { for (let turn = 0; turn < 3; turn += 1) await new Promise((resolve) => setTimeout(resolve, 0)); });
  const status = () => host.querySelector<HTMLElement>('[data-testid="dossier-status"]');
  /** Several problems wait behind "N por resolver"; this opens their list. One sits beside the pill already. */
  const showProblems = async () => {
    const several = host.querySelector<HTMLElement>('[data-testid="dossier-problems"]');
    if (several && several.getAttribute("aria-expanded") !== "true") await act(async () => { several.click(); });
  };
  /** The problems as the header shows them once its list is open: the reason, its words and the document it compares with. */
  const problems = async () => {
    await showProblems();
    return Array.from(host.querySelectorAll<HTMLElement>('[data-testid="dossier-reason"], [data-testid="dossier-problem-list"] [role="option"]')).map((item) => ({ reason: item.dataset.reason ?? null, text: item.textContent ?? "", compare: item.dataset.compare ?? null }));
  };
  /** The "Parece repetido" problem that opens Comparar, once the list is open. */
  const entry = async () => { await showProblems(); return host.querySelector<HTMLElement>('[data-testid="dossier-status"] [data-compare]'); };
  const view = () => host.querySelector<HTMLElement>('[data-testid="duplicate-compare"]');
  const button = (name: string) => Array.from(host.querySelectorAll<HTMLButtonElement>("button")).find((item) => item.textContent?.trim() === name);
  const footerButtons = () => Array.from(host.querySelectorAll<HTMLButtonElement>('[data-testid="frame-footer"] button')).map((item) => item.textContent?.trim());
  const row = (field: BusinessComparedField | "file") => host.querySelector<HTMLElement>(`[data-testid="duplicate-compare-row"][data-field="${field}"]`);
  const compare = async () => { const item = await entry(); assert.ok(item, "Parece repetido opens Comparar"); await act(async () => { item.click(); }); await flush(); };
  return { host, requests, fetchedSources, deleted, act, flush, release, status, problems, entry, view, button, footerButtons, row, compare, cleanup: async () => {
    release();
    await act(async () => { root.unmount(); });
    host.remove();
    globalThis.fetch = oldFetch;
  } };
}

const LABELS = { counterparty: "Comercio", occurred_on: "Fecha", amount: "Total", currency: "Moneda", fiscal_number: "NCF" } as const;
const PRIMARY = "bg-[var(--cuadrao-green)]";
const DANGER_FILL = "bg-[#9e2f39]";
// Class tokens, not substrings: a pressed fill such as active:bg-[#9e2f39]/[0.08] is not the fill.
const hasClass = (element: Element | undefined, token: string) => Boolean(element?.className.split(/\s+/).includes(token));
const sent = (ui: { requests: { options?: RequestInit }[] }, index = 0) => JSON.parse(String(ui.requests[index].options?.body));
const repeats = (node: Element | null) => (node?.textContent ?? "").match(/Parece repetido/g)?.length ?? 0;

test("the header lists Parece repetido once among the other problems, and only it opens Comparar", async () => {
  const ui = await mount();
  try {
    assert.equal(ui.status()?.querySelector('[data-testid="status-pill"]')?.textContent, "Necesita atención");
    assert.equal(ui.host.querySelector('[data-testid="dossier-problems"]')?.textContent, "2 por resolver");
    const shown = await ui.problems();
    assert.deepEqual(shown.map((item) => [item.reason, item.compare]), [["duplicate", "draft-original"], ["blocked", null]], "the other problem still renders");
    assert.match(shown[0].text, /^Parece repetido/);
    assert.equal(repeats(ui.host), 1);
    assert.doesNotMatch(ui.host.textContent ?? "", /Parece un recibo/);
    assert.equal(ui.button("Son compras distintas"), undefined);
    assert.equal(ui.button("Eliminar este duplicado"), undefined);
    assert.equal(ui.requests.length, 0);
  } finally { await ui.cleanup(); }
});

test("alone, the duplicate is the reason beside the pill, and it opens Comparar", async () => {
  // A pair with the same RNC and NCF adds no blocker; the server still names it a gap.
  const facts = await mount("success", { blockers: [], gaps: ["duplicate"] });
  const fiscal = await mount("success", { blockers: [], gaps: ["duplicate"], basis: "fiscal_number" });
  try {
    for (const ui of [facts, fiscal]) {
      const reason = ui.host.querySelector<HTMLElement>('[data-testid="dossier-reason"]');
      assert.equal(reason?.textContent, "Parece repetido");
      assert.equal(reason?.dataset.compare, "draft-original");
      assert.equal(ui.host.querySelector('[data-testid="dossier-problems"]'), null);
      assert.equal(repeats(ui.host), 1);
      await ui.compare();
      assert.ok(ui.view());
    }
  } finally { await facts.cleanup(); await fiscal.cleanup(); }
});

test("why it looks repeated follows the server's basis", async () => {
  const { dossierProblems } = await import("@/components/business-app/dossier-attention");
  const i18next = (await import("i18next")).default;
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { dossierFixtureIds } = await import("@/components/business-app/dossier-fixtures");
  const fixture = await createFixtureBusinessDataSource().dossier(dossierFixtureIds.ready);
  const why = (basis: BusinessDuplicateCandidate["basis"]) => dossierProblems({ ...fixture, listo_gaps: ["duplicate"], duplicate_candidates: [candidate({ basis })] }, i18n.t.bind(i18n))[0].text;
  const read = why("read_facts");
  const number = why("fiscal_number");
  assert.ok(read && number);
  assert.notEqual(read, number);
  assert.match(number, /RNC/);
  assert.match(number, /NCF/);
});

test("Comparar turns the panel into the compare view with both documents in the existing preview", async () => {
  const ui = await mount();
  try {
    await ui.compare();
    assert.equal(ui.status(), null);
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
    assert.deepEqual(rows, ["counterparty", "occurred_on", "amount", "currency", "fiscal_number"]);
    for (const field of ["counterparty", "occurred_on", "currency", "fiscal_number"] as const) assert.equal(ui.row(field)?.dataset.state, "same");
    assert.equal(ui.row("amount")?.dataset.state, "different");
    assert.match(ui.row("counterparty")?.textContent ?? "", /Ferretería Ochoa/);
    assert.match(ui.row("fiscal_number")?.textContent ?? "", /B0100000456/);
    assert.match(ui.row("fiscal_number")?.textContent ?? "", /B0100000123/);
    assert.match(ui.row("currency")?.textContent ?? "", /DOP/);
  } finally { await ui.cleanup(); }
});

test("only a Diferente row carries the shared chip, an Igual row a quiet check, both right after the field name", async () => {
  const ui = await mount("success", { differences: ["amount", "fiscal_number"] });
  try {
    await ui.compare();
    const { StatusChip } = await import("@/components/business-app/foundation/StatusChip");
    const { createRoot } = await import("react-dom/client");
    const { act } = await import("react");
    const probe = document.createElement("div");
    const probeRoot = createRoot(probe);
    await act(async () => { probeRoot.render(<StatusChip tone="warning">x</StatusChip>); });
    const shared = probe.firstElementChild as HTMLElement;
    for (const field of ["counterparty", "occurred_on", "amount", "currency", "fiscal_number"] as const) {
      const line = ui.row(field)!;
      const different = field === "amount" || field === "fiscal_number";
      const head = line.querySelector("th")!;
      const marker = head.querySelector<HTMLElement>("[data-compare-marker]")!;
      assert.ok(marker, `${field} has a marker`);
      assert.equal(marker.dataset.compareMarker, different ? "different" : "same");
      // The marker sits on the left, right after the field name, before either value.
      assert.equal(line.firstElementChild, head);
      assert.equal(marker.previousElementSibling?.textContent, LABELS[field]);
      assert.ok(marker.compareDocumentPosition(line.querySelector("td")!) & Node.DOCUMENT_POSITION_FOLLOWING);
      assert.equal(line.querySelectorAll("[data-compare-marker]").length, 1);
      if (different) {
        assert.equal(marker.textContent, "Diferente");
        assert.equal(marker.className, shared.className);
        assert.equal(marker.getAttribute("style"), shared.getAttribute("style"));
      } else {
        assert.equal(marker.getAttribute("aria-label"), "Igual");
        assert.equal(marker.getAttribute("role"), "img");
        assert.equal(marker.tagName.toLowerCase(), "svg");
      }
      assert.doesNotMatch(Array.from(line.querySelectorAll("td")).map((cell) => cell.textContent).join(" "), /Igual|Diferente/, "no words on the right");
    }
    assert.equal(ui.view()?.querySelectorAll('[data-compare-marker="different"]').length, 2);
    assert.match(ui.row("amount")!.className, /bg-\[#fdf6ec\]/, "the Diferente tint stays");
    assert.doesNotMatch(ui.row("currency")!.className, /bg-\[#fdf6ec\]/);
    await act(async () => { probeRoot.unmount(); });
  } finally { await ui.cleanup(); }
});

test("each column head names its document's file, with Este or the other's state, its channel and when it arrived", async () => {
  const saved = await mount();
  const approved = await mount("success", { approved: true });
  try {
    for (const [ui, state] of [[saved, "Guardado antes"], [approved, "Aceptado"]] as const) {
      await ui.compare();
      const heads = Array.from(ui.view()!.querySelectorAll<HTMLElement>("thead [data-compare-side]"));
      assert.deepEqual(heads.map((head) => head.dataset.compareSide), ["document", "other"]);
      const [mine, theirs] = heads;
      assert.equal(mine.querySelector("[data-compare-file]")?.textContent, "factura-nueva.pdf");
      assert.equal(mine.querySelector("[data-compare-arrival]")?.textContent, `Este · Carga web · ${formatTimestamp("2026-11-04T12:00:00Z", "es-419")}`);
      assert.equal(theirs.querySelector("[data-compare-file]")?.textContent, "factura.pdf");
      assert.equal(theirs.querySelector("[data-compare-arrival]")?.textContent, `${state} · WhatsApp · ${formatTimestamp("2026-11-03T12:00:00Z", "es-419")}`);
      assert.doesNotMatch(ui.view()?.textContent ?? "", /Este documento|El otro documento/);
    }
  } finally { await saved.cleanup(); await approved.cleanup(); }
});

test("the diff has no Archivo row: the heads name the files and the previews show them", async () => {
  const ui = await mount("success", { differences: ["file"] });
  try {
    await ui.compare();
    assert.equal(ui.row("file"), null);
    assert.doesNotMatch(ui.view()?.querySelector("table")?.textContent ?? "", /Archivo/);
    assert.equal(ui.view()?.querySelectorAll('[data-compare-marker="different"]').length, 0);
  } finally { await ui.cleanup(); }
});

test("a different NCF recommends two purchases and makes Son compras distintas the primary action", async () => {
  const ui = await mount("success", { recommendation: "different_purchase" });
  try {
    await ui.compare();
    assert.match(ui.view()?.textContent ?? "", /Mismo comercio, fecha, total y moneda\. El NCF es distinto: probablemente son dos compras distintas\./);
    assert.ok(hasClass(ui.button("Son compras distintas"), PRIMARY));
    assert.ok(!hasClass(ui.button("Eliminar este duplicado"), DANGER_FILL));
    assert.deepEqual(ui.footerButtons(), ["Volver", "Eliminar este duplicado", "Son compras distintas"]);
  } finally { await ui.cleanup(); }
});

test("the same NCF says it is the same document and makes Eliminar este duplicado the primary action", async () => {
  const ui = await mount("success", { recommendation: "same_purchase" });
  try {
    await ui.compare();
    assert.match(ui.host.querySelector('[data-testid="duplicate-recommendation"]')?.textContent ?? "", /Es el mismo documento/);
    assert.ok(hasClass(ui.button("Eliminar este duplicado"), DANGER_FILL));
    assert.ok(!hasClass(ui.button("Son compras distintas"), PRIMARY));
    assert.deepEqual(ui.footerButtons(), ["Volver", "Son compras distintas", "Eliminar este duplicado"]);
  } finally { await ui.cleanup(); }
});

test("with no NCF there is no recommendation and no primary action", async () => {
  const ui = await mount("success", { recommendation: null });
  try {
    await ui.compare();
    assert.equal(ui.host.querySelector('[data-testid="duplicate-recommendation"]'), null);
    assert.ok(!hasClass(ui.button("Son compras distintas"), PRIMARY));
    assert.ok(!hasClass(ui.button("Eliminar este duplicado"), DANGER_FILL));
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

test("Volver returns to the review with focus back on Parece repetido", async () => {
  const ui = await mount("success", { blockers: [], gaps: ["duplicate"] });
  try {
    await ui.compare();
    await ui.act(async () => { ui.button("Volver")?.click(); });
    await ui.flush();
    assert.equal(ui.view(), null);
    assert.ok(ui.host.querySelector('[data-testid="review-form"]'));
    assert.equal(document.activeElement, await ui.entry(), "focus is on the reason that opened Comparar");
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
    assert.equal(repeats(ui.host), 0);
    assert.deepEqual((await ui.problems()).map((item) => item.text), ["Tiene algo pendiente"], "the problem left stays in the header");
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

test("an accepted record has no status line, so nothing about a duplicate and no Comparar", async () => {
  const ui = await mount("success", { closed: true });
  try {
    assert.equal(ui.status(), null);
    assert.equal(await ui.entry(), null);
    assert.equal(repeats(ui.host), 0);
  } finally { await ui.cleanup(); }
});

test("with no candidate listed the server's gap still says Parece repetido, with nothing to compare", async () => {
  const ui = await mount("success", { noCandidates: true, blockers: [], gaps: ["duplicate"] });
  try {
    const reason = ui.host.querySelector<HTMLElement>('[data-testid="dossier-reason"]');
    assert.equal(reason?.textContent, "Parece repetido");
    assert.equal(await ui.entry(), null, "no Comparar");
    await ui.act(async () => { reason?.click(); });
    await ui.flush();
    assert.equal(ui.view(), null);
    assert.doesNotMatch(ui.host.textContent ?? "", /Parece un recibo/);
  } finally { await ui.cleanup(); }
});

test("no duplicate gap: nothing about a duplicate, even with a candidate listed", async () => {
  const ui = await mount("success", { blockers: [{ code: "fact_required", field: "funding" }], gaps: ["blocked"] });
  try {
    assert.deepEqual((await ui.problems()).map((item) => item.text), ["Tiene algo pendiente"]);
    assert.equal(await ui.entry(), null);
    assert.equal(repeats(ui.host), 0);
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

test("in the review panel the one Parece repetido sits in the header's problem list, above the rows, and opens the compare view", async () => {
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
    ...standing(["duplicate", "blocked"]),
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
    const status = host.querySelector<HTMLElement>('[data-testid="dossier-status"]');
    assert.ok(status, "the header's status line is there");
    const firstRow = host.querySelector('[data-fact]');
    assert.ok(firstRow && status.compareDocumentPosition(firstRow) & Node.DOCUMENT_POSITION_FOLLOWING, "the status sits above the rows");
    await act(async () => { status.querySelector<HTMLElement>('[data-testid="dossier-problems"]')?.click(); });
    const options = Array.from(status.querySelectorAll<HTMLElement>('[data-testid="dossier-problem-list"] [role="option"]'));
    assert.deepEqual(options.map((item) => item.dataset.reason), ["duplicate", "blocked"], "the other problem still renders");
    assert.equal(repeats(host), 1, "one Parece repetido on the whole panel");
    assert.equal(repeats(status), 1, "and it is in the header");
    assert.doesNotMatch(host.textContent ?? "", /Parece un recibo/);
    assert.equal(host.querySelector('[data-testid="receipt-duplicate-resolution"]'), null, "no second box lower down");
    assert.equal(options[0].dataset.compare, "draft-original");
    await act(async () => { options[0].click(); });
    await settle();
    assert.ok(host.querySelector('[data-testid="duplicate-compare"]'), "Parece repetido opens the compare view");
  } finally {
    await act(async () => { root.unmount(); });
    host.remove();
    globalThis.fetch = oldFetch;
  }
});

for (const outcome of ["settled", "failed"] as const) {
  test(`in the review panel, Son compras distintas ${outcome === "settled" ? "returns to the review with a toast, no Parece repetido and Aceptar ready" : "that fails keeps the compare view and retries with the same key"}`, async () => {
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
      blockers: [],
      ...standing(["duplicate"]),
      approval_available: false,
      duplicate_candidates: [candidate({})],
    };
    const settled: BusinessDossier = { ...dossier, version: 8, blockers: [], ...standing([]), approval_available: true, duplicate_candidates: [] };
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
      assert.ok(button("Aceptar")?.disabled, "the duplicate blocks Aceptar before the decision");
      const reason = host.querySelector<HTMLElement>('[data-testid="dossier-reason"]');
      assert.equal(reason?.dataset.compare, "draft-original");
      await act(async () => { reason?.click(); });
      await settle();
      await act(async () => { button("Son compras distintas")?.click(); });
      await settle();
      const toasts = () => host.querySelector('[data-testid="toasts"]')?.textContent;
      if (outcome === "settled") {
        assert.equal(host.querySelector('[data-testid="duplicate-compare"]'), null, "the compare view closed");
        assert.equal(repeats(host), 0, "Parece repetido is gone");
        assert.equal(host.querySelector('[data-testid="status-pill"]')?.textContent, "Listo para aceptar");
        assert.equal(toasts(), "Marcado como compras distintas.");
        const approve = button("Aceptar");
        assert.ok(approve && !approve.disabled, "Aceptar is ready");
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

test("in the review panel, while a row holds an unsaved edit Parece repetido does not open Comparar, and the edit stays", async () => {
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
    blockers: [],
    ...standing(["duplicate"]),
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
    guardPanel: () => () => undefined,
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
    await act(async () => { host.querySelector<HTMLElement>('[data-fact="counterparty"] [data-row-value]')?.click(); });
    const input = host.querySelector<HTMLInputElement>('[data-testid="edit-counterparty"] input');
    assert.ok(input, "the row is open");
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, "Otro nombre");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => { host.querySelector<HTMLElement>('[data-testid="dossier-reason"]')?.click(); });
    await settle();
    assert.equal(host.querySelector('[data-testid="duplicate-compare"]'), null, "Comparar waits for the edit");
    assert.equal(host.querySelector<HTMLInputElement>('[data-testid="edit-counterparty"] input')?.value, "Otro nombre", "and the edit stays");
  } finally {
    await act(async () => { root.unmount(); });
    host.remove();
    globalThis.fetch = oldFetch;
  }
});
