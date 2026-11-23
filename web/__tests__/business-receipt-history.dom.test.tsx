import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import type { Window as HappyWindow } from "happy-dom";
import { afterAll, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ReactNode } from "react";
import type { BusinessDataSource } from "@/components/business-app/business-data";
import type { BusinessAccount } from "@/lib/business-api";
import type { BusinessDossier, BusinessDraftRevision, BusinessFacts } from "@/lib/business-dossier";
import type { DgiiDeclaration, DgiiField, DgiiFields } from "@/lib/business-dgii";

mock.module("next/navigation", () => ({
  usePathname: () => "/biz",
  useRouter: () => ({ push: () => {}, replace: () => {}, refresh: () => {}, prefetch: () => {} }),
  useSearchParams: () => new URLSearchParams(),
}));

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

async function render(node: ReactNode, { dgiiNames = false, lng = "es-419" } = {}) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const { dgiiChoiceLabel } = await import("@/lib/dgii-labels");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const english = (await import("@/public/locales/en/common.json")).default;
  const i18n = i18next.createInstance();
  if (dgiiNames) i18n.use(dgiiChoiceLabel);
  await i18n.init({ lng, resources: { "es-419": { translation: spanish }, en: { translation: english } }, interpolation: { escapeValue: false }, ...(dgiiNames ? { postProcess: dgiiChoiceLabel.name, postProcessPassResolved: true } : {}) });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => { root.render(<I18nextProvider i18n={i18n}>{node}</I18nextProvider>); });
  return { host, act, close: () => act(async () => { root.unmount(); host.remove(); }) };
}

const actor = (name: string, kind: "member" | "extractor" = "member") => ({ actor_id: name, actor_kind: kind, display_name: name, shown_as: "name", grant_id: "g", issuer_id: "o", issuer_display_name: "Dueño", issuer_shown_as: "name" });
const known = <T,>(value: T) => ({ state: "known" as const, value, origin: "member_set" as const, verified: false, source_ids: [] });
const unknown = { state: "unknown" as const, value: null, origin: null, verified: false as const, source_ids: [] };

function facts(amount: string, currency = "DOP"): BusinessFacts {
  return { kind: known("expense"), amount: known(amount), currency: known(currency), occurred_on: known("2026-10-09"), counterparty: known("Ferretería La Esquina"), funding: unknown, business_share: unknown, receipt_state: unknown, category_id: unknown, fiscal: null } as unknown as BusinessFacts;
}

function revision(version: number, at: string, who: ReturnType<typeof actor>, before: BusinessFacts | null, after: BusinessFacts): BusinessDraftRevision {
  return { draft_id: "d", version, actor: who, before, after, source_ids: [], turn_key: null, created_at: at };
}

/** Local times, so the "DD/MM, h:mm a.m." line is the same in every time zone. */
const at = (day: number, hour: number, minute: number) => new Date(2026, 9, day, hour, minute).toISOString();

/** What one event says: its lines, then who did it (null when nobody is named). */
const eventLines = (item: Element) => [...[...item.querySelectorAll("p")].map((line) => line.textContent), item.querySelector('[data-testid="history-who"] span')?.textContent ?? null];
const accepted = "Aceptado";

test("Historial shows the server's supporting-file deadline and restore offer on the latest unlink", async () => {
  const { default: ReceiptHistory } = await import("@/components/business-app/ReceiptHistory");
  const file = { source_id: "s1", receipt_id: "r1", filename: "respaldo.pdf", media_type: "application/pdf", size_bytes: 42, state: "unlinked" as const, purge_at: at(22, 14, 5), unlink_available: false, restore_available: true };
  const documentFacts = facts("1200.00");
  const history = ([["unlinked", 1], ["restored", 2], ["unlinked", 3]] as const).map(([supporting_change, version]) => ({
    ...revision(version, at(10 + version, 9, 0), actor("Ana Peña"), documentFacts, documentFacts),
    source_ids: [file.source_id], supporting_change, supporting_filename: file.filename,
  }));
  const onRestore = async () => {};
  for (const [supportingFiles, deadline, restore] of [
    [[file], true, true],
    [[{ ...file, restore_available: false }], true, false],
    [[], false, false],
  ] as const) {
    const page = await render(<ReceiptHistory history={history} accounts={[]} supportingFiles={[...supportingFiles]} onRestore={onRestore} />);
    try {
      const events = [...page.host.querySelectorAll('[data-testid="history-supporting"]')];
      assert.equal(events.length, 3, "earlier history survives a restore or expiry");
      const times = [...page.host.querySelectorAll(`time[datetime="${file.purge_at}"]`)];
      assert.deepEqual(times.map(time => time.closest("li")), deadline ? [events[0]] : []);
      if (deadline) assert.match(times[0].textContent ?? "", /^Se borra el 22 Oct 2026, 2:05/);
      assert.deepEqual([...page.host.querySelectorAll("button")].map(button => button.textContent), restore ? ["Restaurar"] : []);
    } finally { await page.close(); }
  }
});

describe("Historial", () => {
  test("reads what happened, newest first, with who and when in one gray line, and colours only the approval", async () => {
    const { default: ReceiptHistory } = await import("@/components/business-app/ReceiptHistory");
    const history = [
      revision(1, at(10, 9, 25), actor("Cuadrao", "extractor"), null, facts("1200.00")),
      revision(2, at(10, 13, 5), actor("Ana Peña"), facts("1200.00"), facts("1250.00")),
      revision(3, at(11, 8, 0), actor("Ana Peña"), facts("1250.00"), facts("1250.00", "USD")),
    ];
    const sources = [{ id: "s1", kind: "attachment", channel: "whatsapp", received_at: at(10, 9, 20), connection_id: "c", filename: "a.jpg", media_type: "image/jpeg" }] as BusinessDossier["sources"];
    const approval = { status: "recorded", activity_id: "x", reviewed_version: 3, approved_revision: 3, approved_at: at(11, 0, 5), actor: actor("Lucía Mateo") } as BusinessDossier["approval_result"];
    const page = await render(<ReceiptHistory history={history} accounts={[]} sources={sources} approval={approval} />);
    const section = page.host.querySelector('[data-testid="receipt-history"]')!;
    // One card per day, newest first: every event says what happened, who did it and when, in full.
    assert.deepEqual([...section.querySelectorAll('[data-testid="history-day"] h3')].map((title) => title.textContent), ["11 Oct 2026", "10 Oct 2026"]);
    assert.equal(section.querySelector("button"), null, "nothing folds: the tab is the Historial");
    assert.deepEqual([...section.querySelectorAll("li")].map(eventLines), [
      ["Moneda cambiada de DOP a USD", "Ana Peña"],
      [accepted, "Pasó a Registros", "Lucía Mateo"],
      ["Total cambiado de RD$ 1,200.00 a RD$ 1,250.00", "Ana Peña"],
      ["Leído", "Cuadrao"],
      ["Llegó por WhatsApp", "a.jpg", null],
    ]);
    const times = [...section.querySelectorAll("time")];
    assert.deepEqual(times.map((time) => time.getAttribute("datetime")), [at(11, 8, 0), at(11, 0, 5), at(10, 13, 5), at(10, 9, 25), at(10, 9, 20)]);
    for (const time of times) assert.match(time.textContent ?? "", /\d{1,2} \w+\.? 2026, \d{1,2}:\d{2}/, "the full date and time");
    assert.deepEqual([...section.querySelectorAll('[data-testid="history-dot"]')].map((dot) => dot.getAttribute("data-approved")), [null, "true", null, null, null], "only the acceptance is green");
    assert.doesNotMatch(section.textContent ?? "", /revisi[oó]n|tras aceptar|primer flujo|registrado|desconocido|segundos/i);
    await page.close();
  });

  test("the acceptance names no report: only the server knows whether a record goes into one", async () => {
    const { default: ReceiptHistory } = await import("@/components/business-app/ReceiptHistory");
    const approval = { status: "recorded", activity_id: "x", reviewed_version: 1, approved_revision: 1, approved_at: at(11, 0, 5), actor: actor("Lucía Mateo") } as BusinessDossier["approval_result"];
    for (const documentType of ["recibo", "venta", undefined] as const) {
      const page = await render(<ReceiptHistory documentType={documentType} history={[revision(1, at(10, 9, 25), actor("Cuadrao", "extractor"), null, facts("1200.00"))]} accounts={[]} sources={[]} approval={approval} />);
      const event = page.host.querySelector('[data-approved="true"]')!;
      assert.equal(event.querySelector('[data-testid="history-sub"]')?.textContent, "Pasó a Registros");
      assert.doesNotMatch(event.textContent ?? "", /60[67]|[Rr]eporte/);
      await page.close();
    }
  });

  test("names the channel a receipt came in by: Correo and Subido", async () => {
    const { default: ReceiptHistory } = await import("@/components/business-app/ReceiptHistory");
    for (const [channel, word] of [["email", "Correo"], ["web", "Subido"]] as const) {
      const sources = [{ id: "s", kind: "attachment", channel, received_at: at(10, 9, 0), connection_id: "c", filename: null, media_type: "application/pdf" }] as BusinessDossier["sources"];
      const page = await render(<ReceiptHistory history={[]} accounts={[]} sources={sources} />);
      assert.equal(page.host.querySelector("li p")?.textContent, `Llegó por ${word}`);
      await page.close();
    }
  });

  test("a chat proposal or a web action is not Recibido; the first file or WhatsApp message is", async () => {
    const { default: ReceiptHistory } = await import("@/components/business-app/ReceiptHistory");
    const sources = [
      { id: "p", kind: "agent_proposal", channel: "web", received_at: at(9, 8, 0), text: "Gasto de pintura" },
      { id: "w", kind: "web_action", channel: "web", received_at: at(9, 8, 30), text: "Revisó" },
      { id: "m", kind: "message", channel: "whatsapp", received_at: at(9, 9, 0), text: "Te mando el recibo" },
    ] as BusinessDossier["sources"];
    const page = await render(<ReceiptHistory history={[]} accounts={[]} sources={sources} />);
    assert.deepEqual([...page.host.querySelectorAll("li > p:first-of-type")].map((line) => line.textContent), ["Llegó por WhatsApp"]);
    await page.close();
    const proposalOnly = await render(<ReceiptHistory history={[]} accounts={[]} sources={sources.slice(0, 2)} />);
    assert.equal(proposalOnly.host.querySelector('[data-testid="receipt-history"]'), null);
    await proposalOnly.close();
  });

  test("an RNC the backend verifies reads RNC verificado", async () => {
    const { default: ReceiptHistory } = await import("@/components/business-app/ReceiptHistory");
    const withRnc = (verified: boolean) => ({ ...facts("500.00"), fiscal: { rnc: { ...known("131999888"), verified }, ncf: unknown, ecf: unknown, itbis: unknown } }) as unknown as BusinessFacts;
    const page = await render(<ReceiptHistory history={[revision(2, at(10, 9, 0), actor("Ana Peña"), withRnc(false), withRnc(true))]} accounts={[]} />);
    assert.deepEqual([...page.host.querySelectorAll("li > p:first-of-type")].map((line) => line.textContent), ["RNC verificado"]);
    await page.close();
  });

  test("events of one revision keep their field order", async () => {
    const { default: ReceiptHistory } = await import("@/components/business-app/ReceiptHistory");
    const page = await render(<ReceiptHistory history={[revision(2, at(10, 9, 0), actor("Ana Peña"), facts("100.00"), facts("200.00", "USD"))]} accounts={[]} />);
    assert.deepEqual([...page.host.querySelectorAll("li > p:first-of-type")].map((line) => line.textContent), ["Total cambiado de RD$ 100.00 a US$ 200.00", "Moneda cambiada de DOP a USD"]);
    await page.close();
  });

  for (const [documentType, name] of [["recibo", "Emisor"], ["venta", "Cliente"]] as const) test(`a name change on a ${documentType} reads ${name} cambiado`, async () => {
    const { default: ReceiptHistory } = await import("@/components/business-app/ReceiptHistory");
    const renamed = { ...facts("100.00"), counterparty: known("Colmado Duarte") } as unknown as BusinessFacts;
    const page = await render(<ReceiptHistory history={[revision(2, at(10, 9, 0), actor("Ana Peña"), facts("100.00"), renamed)]} accounts={[]} documentType={documentType} />);
    assert.deepEqual([...page.host.querySelectorAll("li > p:first-of-type")].map((line) => line.textContent), [`${name} cambiado de Ferretería La Esquina a Colmado Duarte`]);
    await page.close();
  });

  test("a confirmation that keeps the value adds no correction line", async () => {
    const { default: ReceiptHistory } = await import("@/components/business-app/ReceiptHistory");
    const read = facts("500.00");
    const confirmed = { ...read, amount: { ...read.amount, origin: "owner_stated" } } as BusinessFacts;
    const page = await render(<ReceiptHistory history={[revision(2, at(10, 9, 0), actor("Ana Peña"), read, confirmed)]} accounts={[]} />);
    assert.deepEqual([...page.host.querySelectorAll("li > p:first-of-type")].map((line) => line.textContent), ["Se revisó esta versión."]);
    await page.close();
  });

  test("a revision that creates the record lists only fields with a value", async () => {
    const { default: ReceiptHistory } = await import("@/components/business-app/ReceiptHistory");
    const created = { ...facts("500.00"), kind: unknown, occurred_on: unknown, counterparty: unknown } as unknown as BusinessFacts;
    const page = await render(<ReceiptHistory history={[revision(1, at(10, 9, 0), actor("Ana Peña"), null, created)]} accounts={[]} />);
    const text = [...page.host.querySelectorAll("li > p:first-of-type")].map((line) => line.textContent);
    assert.deepEqual(text.sort(), ["Moneda: DOP", "Total: RD$ 500.00"]);
    await page.close();
  });
});

describe("the AI reading state", () => {
  for (const reduced of [false, true]) test(`holds the General layout with a paper scan and dot ripple; reduced motion ${reduced}`, async () => {
    const { BusinessWorkspaceProvider } = await import("@/components/business-app/BusinessWorkspace");
    const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
    const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
    const ReceiptReviewPanel = (await import("@/components/business-app/ReceiptReviewPanel")).default;
    const fixture = createFixtureBusinessDataSource({ chatAvailable: false });
    const source: BusinessDataSource = {
      ...fixture,
      receipt: async (id, signal) => ({ ...await fixture.receipt(id, signal), draft_id: null, activity: { state: "reading", unread: false, completion_cursor: null }, bandeja: { por_revisar: false, con_problema: false, leyendo: true } }),
    };
    const device = (window as unknown as HappyWindow).happyDOM.settings.device;
    const original = device.prefersReducedMotion;
    device.prefersReducedMotion = reduced ? "reduce" : "no-preference";
    const sheet = document.createElement("style");
    sheet.textContent = readFileSync(new URL("../components/business-app/receipt-reading.module.css", import.meta.url), "utf8");
    document.head.append(sheet);
    const page = await render(<BusinessConsentTestProvider accepted><BusinessWorkspaceProvider source={source}><ReceiptReviewPanel target={{ kind: "receipt", id: "rcpt-ferreteria" }} /></BusinessWorkspaceProvider></BusinessConsentTestProvider>);
    try {
      for (let i = 0; i < 80 && !page.host.querySelector('[data-testid="receipt-viewer"]'); i++) await page.act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
      const state = page.host.querySelector('[role="status"][aria-label="Leyendo el documento"]');
      assert.ok(state, "the pending read is announced");
      assert.deepEqual([...state.querySelectorAll("h3")].map(heading => heading.textContent), ["Comprobante", "Reporte 606", "Montos"]);
      assert.deepEqual([...state.querySelectorAll("ul")].map(list => list.querySelectorAll("li").length), [4, 2, 3]);
      assert.doesNotMatch(state.textContent ?? "", /RD\$|0\.00|%/);
      assert.equal(state.querySelector("input, [role=progressbar]"), null);
      const band = page.host.querySelector('[data-testid="receipt-reading-band"]');
      const clip = band?.parentElement;
      const paper = clip?.previousElementSibling as HTMLElement;
      assert.ok(clip && paper?.matches("img, canvas"), "the band overlays the viewed page");
      assert.ok(clip.classList.contains("overflow-hidden"), "the scan stays inside the paper");
      for (const property of ["width", "height", "transform"] as const) assert.equal(clip.style[property], paper.style[property]);
      const ripple = page.host.querySelector('[data-testid="receipt-reading-ripple"]');
      const bar = state.querySelector("li span");
      for (const part of [bar, ripple, band]) {
        assert.ok(part);
        const motion = getComputedStyle(part).animation;
        if (reduced) assert.ok(!motion || motion === "none", "the board is still");
        else assert.ok(motion && motion !== "none", "the board animates");
      }
    } finally {
      await page.close();
      sheet.remove();
      device.prefersReducedMotion = original;
    }
  });
});

test("a purchase retyped as a sale hides its earlier 606 answer", async () => {
  const { default: ReceiptHistory } = await import("@/components/business-app/ReceiptHistory");
  const before = { ...facts("1000.00"), fiscal: { rnc: unknown, ncf: known("B0100000001"), ecf: unknown, itbis: unknown, include_606: unknown } };
  const answered = { ...before, fiscal: { ...before.fiscal, include_606: known(true) } };
  const sale = { ...answered, kind: known("income") } as BusinessFacts;
  const history = [revision(2, at(10, 9, 0), actor("Lía"), before, answered), revision(3, at(10, 10, 0), actor("Lía"), answered, sale)];
  const page = await render(<ReceiptHistory history={history} accounts={[]} documentType="venta" />);
  assert.equal(page.host.querySelector('[data-testid="history-606"]'), null);
  await page.close();
});

test("a draft the first Business RNC moved reads as a change through Cuadrao with its reason, not a second read", async () => {
  const { default: ReceiptHistory } = await import("@/components/business-app/ReceiptHistory");
  const sale = { ...facts("1200.00"), kind: known("income") } as unknown as BusinessFacts;
  const history = [
    revision(1, at(10, 9, 25), actor("Ana Peña", "extractor"), null, facts("1200.00")),
    { ...revision(2, at(11, 8, 0), actor("Ana Peña", "extractor"), facts("1200.00"), sale), reason: "business_rnc_set" as const },
  ];
  const page = await render(<ReceiptHistory history={history} accounts={[]} documentType="venta" />);
  const lines = [...page.host.querySelectorAll("li")].map(eventLines);
  assert.deepEqual(lines, [
    ["Actividad cambiada de Gasto a Ingreso", "Lo emitió tu negocio", "Ana Peña vía Cuadrao"],
    ["Leído", "Cuadrao"],
  ]);
  const chips = page.host.querySelector('[data-testid="history-diff"]')!;
  assert.deepEqual([chips.querySelector("del")?.textContent, chips.querySelector("ins")?.textContent], ["Gasto", "Ingreso"]);
  assert.equal(page.host.querySelector('[data-testid="history-note"]')?.textContent, "Lo emitió tu negocio");
  assert.ok(!(page.host.textContent ?? "").includes("Venta"));
  await page.close();
});

test("a pair settled as different purchases reads as one line naming the other document, not a generic change", async () => {
  const { default: ReceiptHistory } = await import("@/components/business-app/ReceiptHistory");
  const duplicate = { decision: "different_purchase" as const, other_draft_id: "draft-original", other_counterparty: "Ferretería Ochoa", other_filename: "factura.pdf" };
  const history = [
    revision(1, at(10, 9, 25), actor("Ana Peña", "extractor"), null, facts("1200.00")),
    { ...revision(2, at(11, 8, 0), actor("Ana Peña"), facts("1200.00"), facts("1200.00")), duplicate },
  ];
  const page = await render(<ReceiptHistory history={history} accounts={[]} />);
  const lines = [...page.host.querySelectorAll("li")].map(eventLines);
  assert.deepEqual(lines, [
    ["Marcado como compra distinta de Ferretería Ochoa, factura.pdf", "Ana Peña"],
    ["Leído", "Cuadrao"],
  ]);
  await page.close();
});

test("a pair settled as different purchases names a purged other document as deleted, never a raw key", async () => {
  const { default: ReceiptHistory } = await import("@/components/business-app/ReceiptHistory");
  const duplicate = { decision: "different_purchase" as const, other_draft_id: "draft-purged", other_counterparty: null, other_filename: null };
  const history = [{ ...revision(2, at(11, 8, 0), actor("Ana Peña"), facts("1200.00"), facts("1200.00")), duplicate }];
  const page = await render(<ReceiptHistory history={history} accounts={[]} />);
  const lines = [...page.host.querySelectorAll("li")].map(eventLines);
  assert.deepEqual(lines, [["Marcado como compra distinta de Documento eliminado", "Ana Peña"]]);
  await page.close();
});

describe("a fiscal save in Historial", () => {
  const field = (name: string, kind: DgiiField["kind"] = "money", options: string[] = []): DgiiField => ({ name, label: name, kind, options });
  const fields: DgiiFields = {
    "606": [field("id_type", "select", ["1", "2"]), field("category", "select", ["02"]), field("goods_amount"), field("itbis_withheld"), field("itbis_cost"), field("income_withholding_type", "select", ["02"]), field("payment_method", "select", ["03"])],
    "607": [field("income_type", "select", ["1"]), field("card")],
  };
  const declared = (form: "606" | "607", values: Record<string, string | null>) => ({ form, ...values }) as DgiiDeclaration;
  const save = (version: number, before: DgiiDeclaration | null, after: DgiiDeclaration): BusinessDraftRevision => ({ ...revision(version, at(12, 20, version), actor("Ana Pérez"), facts("3450.00"), facts("3450.00")), before_dgii: before, after_dgii: after });
  const entries = (host: HTMLElement) => [...host.querySelectorAll('[data-testid="receipt-history"] ol > li')];
  const changes = (entry: Element) => [...entry.querySelectorAll('[data-testid="history-change"]')].map((item) => [item.querySelector("span")?.textContent, item.querySelector("del")?.textContent ?? null, item.querySelector("ins")?.textContent]);

  test("a 606 save names the 606 and shows each field it changed, old struck through", async () => {
    const { default: ReceiptHistory } = await import("@/components/business-app/ReceiptHistory");
    const after = declared("606", { id_type: "1", goods_amount: "3450.00", itbis_cost: null });
    const page = await render(<ReceiptHistory history={[save(3, declared("606", { id_type: null }), after)]} accounts={[]} dgiiFields={fields} />, { dgiiNames: true });
    const [entry] = entries(page.host);
    assert.equal(entry.querySelector("p")?.textContent, "Datos del 606 guardados");
    assert.deepEqual(changes(entry), [["Tipo Id", "Desconocido", "01 - RNC"], ["Monto Facturado en Bienes", null, "RD$ 3,450.00"]]);
    assert.equal(entry.querySelector('[data-testid="history-more"]'), null, "two changes need no button");
    await page.close();
  });

  test("a 607 save names the 607", async () => {
    const { default: ReceiptHistory } = await import("@/components/business-app/ReceiptHistory");
    const page = await render(<ReceiptHistory history={[save(3, null, declared("607", { income_type: "1", card: "12980.00" }))]} accounts={[]} dgiiFields={fields} documentType="venta" />);
    const [entry] = entries(page.host);
    assert.equal(entry.querySelector("p")?.textContent, "Datos del 607 guardados");
    assert.deepEqual(changes(entry).map(([name]) => name), ["Tipo de Ingreso", "Tarjeta"]);
    await page.close();
  });

  test("more than two changes show two, then a button reveals the rest", async () => {
    const { default: ReceiptHistory } = await import("@/components/business-app/ReceiptHistory");
    const before = declared("606", { itbis_withheld: "0.00", income_withholding_type: null, category: null, payment_method: null });
    const after = declared("606", { itbis_withheld: "270.00", income_withholding_type: "02", category: "02", payment_method: "03" });
    const page = await render(<ReceiptHistory history={[save(4, before, after)]} accounts={[]} dgiiFields={fields} />);
    const [entry] = entries(page.host);
    assert.deepEqual(changes(entry).map(([name]) => name), ["Tipo de gasto", "ITBIS Retenido"]);
    const more = entry.querySelector<HTMLButtonElement>('[data-testid="history-more"]')!;
    assert.equal(more.tagName, "BUTTON");
    assert.equal(more.textContent, "Ver 2 cambios más");
    assert.equal(more.getAttribute("aria-expanded"), "false");
    assert.ok(more.querySelector("svg"), "the app's chevron");
    assert.equal(document.getElementById(more.getAttribute("aria-controls")!), entry.querySelector('[data-testid="history-changes"]'));
    await page.act(async () => { more.click(); });
    assert.equal(more.getAttribute("aria-expanded"), "true");
    assert.equal(more.textContent, "Ver menos");
    assert.deepEqual(changes(entry), [
      ["Tipo de gasto", "Desconocido", "Gastos por trabajos, suministros y servicios"],
      ["ITBIS Retenido", "RD$ 0.00", "RD$ 270.00"],
      ["Tipo de Retención en ISR", "Desconocido", "Honorarios por servicios"],
      ["Forma de pago", "Desconocido", "Tarjeta crédito/débito"],
    ]);
    await page.close();
    const three = await render(<ReceiptHistory history={[save(4, before, { ...after, payment_method: null })]} accounts={[]} dgiiFields={fields} />);
    assert.equal(three.host.querySelector('[data-testid="history-more"]')?.textContent, "Ver 1 cambio más");
    await three.close();
  });

  test("a withholding, income and ID code reads with its DGII name", async () => {
    const { default: ReceiptHistory } = await import("@/components/business-app/ReceiptHistory");
    const named: DgiiFields = { "606": [field("income_withholding_type", "select", ["02"])], "607": [field("id_type", "select", ["1", "2", "3"]), field("income_type", "select", ["1"])] };
    const page = await render(<>
      <ReceiptHistory history={[save(3, null, declared("606", { income_withholding_type: "02" }))]} accounts={[]} dgiiFields={named} />
      <ReceiptHistory history={[save(4, null, declared("607", { id_type: "3", income_type: "1" }))]} accounts={[]} dgiiFields={named} documentType="venta" />
    </>, { dgiiNames: true });
    assert.deepEqual(entries(page.host).map((entry) => changes(entry)), [
      [["Tipo de Retención en ISR", null, "02 - Honorarios por servicios"]],
      [["Tipo Identificación", null, "03 - Pasaporte o ID tributaria"], ["Tipo de Ingreso", null, "01 - Ingresos por operaciones (no financieros)"]],
    ]);
    await page.close();
  });

  test.each([
    ["es-419", ["01 - RNC", "02 - Cédula", "03 - Pasaporte o ID tributaria"]],
    ["en", ["01 - RNC", "02 - Cédula", "03 - Passport or tax ID"]],
  ])("Tipo Id reads with two digits in %s", async (lng, shown) => {
    const { default: ReceiptHistory } = await import("@/components/business-app/ReceiptHistory");
    const ids: DgiiFields = { "606": [], "607": [field("id_type", "select", ["1", "2", "3"])] };
    const page = await render(<>{["1", "2", "3"].map((code) => <ReceiptHistory key={code} history={[save(3, null, declared("607", { id_type: code }))]} accounts={[]} dgiiFields={ids} documentType="venta" />)}</>, { dgiiNames: true, lng });
    assert.deepEqual(entries(page.host).map((entry) => changes(entry)[0]?.[2]), shown);
    await page.close();
  });

  test("a save that changed no field reads Se revisó esta versión.", async () => {
    const { default: ReceiptHistory } = await import("@/components/business-app/ReceiptHistory");
    const same = declared("606", { itbis_cost: "180.00", category: null });
    const page = await render(<ReceiptHistory history={[save(5, same, { ...same }), save(6, null, declared("607", { income_type: null }))]} accounts={[]} dgiiFields={fields} />);
    assert.deepEqual(entries(page.host).map((entry) => entry.querySelector("p")?.textContent), ["Se revisó esta versión.", "Se revisó esta versión."]);
    await page.close();
  });

  test("Leído is Cuadrao's, not the person's", async () => {
    const { default: ReceiptHistory } = await import("@/components/business-app/ReceiptHistory");
    const page = await render(<ReceiptHistory history={[revision(1, at(12, 20, 0), actor("QA Owner", "extractor"), null, facts("3450.00"))]} accounts={[]} />);
    const [entry] = entries(page.host);
    assert.deepEqual(eventLines(entry), ["Leído", "Cuadrao"]);
    await page.close();
  });

  test("the card never says 606 / 607 and has no field dump", async () => {
    const { default: ReceiptHistory } = await import("@/components/business-app/ReceiptHistory");
    const history = [save(3, null, declared("606", { id_type: "1" })), save(4, null, declared("607", { card: "1.00" }))];
    const page = await render(<ReceiptHistory history={history} accounts={[]} dgiiFields={fields} />);
    const card = page.host.querySelector('[data-testid="receipt-history"]')!;
    assert.doesNotMatch(card.textContent ?? "", /606 \/ 607|Datos fiscales/);
    assert.equal(card.querySelector("details"), null);
    await page.close();
  });

  /** What the fiscal declaration editor shows for one field: an amount with its currency symbol, the chosen option, or the typed text. */
  const editorShows = (host: HTMLElement, name: string) => {
    const control = host.querySelector<HTMLInputElement | HTMLSelectElement>(`#fiscal-declaration-${name}, [data-testid="fiscal-declaration-${name}"]`)!;
    if (control instanceof HTMLSelectElement) return control.selectedOptions[0]?.textContent;
    const symbol = control.getAttribute("inputmode") === "decimal" ? control.parentElement?.querySelector("span")?.textContent : null;
    return symbol ? `${symbol} ${control.value}` : control.value;
  };

  test.each([
    { kind: "money", field: field("itbis_withheld"), value: "12980.5" },
    { kind: "select", field: field("id_type", "select", ["1", "2"]), value: "2" },
    { kind: "select with a DGII name", field: field("income_withholding_type", "select", ["02"]), value: "02" },
    { kind: "date", field: field("paid_on", "date"), value: "2026-11-12" },
    { kind: "text", field: field("modified_ncf", "text"), value: "B0100000123" },
  ])("a $kind value reads in Historial as the fiscal editor shows it", async ({ field: shown, value }) => {
    const { default: ReceiptHistory } = await import("@/components/business-app/ReceiptHistory");
    const { default: FiscalDeclarationEditor } = await import("@/components/business-app/FiscalDeclarationEditor");
    const { createDossierFixtures, dossierFixtureIds } = await import("@/components/business-app/dossier-fixtures");
    const fixture = await createDossierFixtures([{ id: "cash", type: "cash", currency: "DOP", nickname: "Caja" }] as BusinessAccount[]).dossier(dossierFixtureIds.fiscal);
    const dossier: BusinessDossier = { ...fixture, dgii: declared("606", { [shown.name]: value }), inheritance: {} };
    const only: DgiiFields = { "606": [shown], "607": [] };
    const saved = { ...revision(3, at(12, 20, 0), actor("Ana Pérez"), dossier.facts, dossier.facts), before_dgii: null, after_dgii: dossier.dgii };
    const page = await render(<>
      <FiscalDeclarationEditor dossier={dossier} fields={only} disabled={false} reviewFiscal={async () => dossier} onChanged={() => {}} onBusy={() => {}} onDirty={() => {}} />
      <ReceiptHistory history={[saved]} accounts={[]} dgiiFields={only} />
    </>);
    const [entry] = entries(page.host);
    const [[, , history]] = changes(entry);
    assert.equal(history, editorShows(page.host, shown.name));
    await page.close();
  });
});
