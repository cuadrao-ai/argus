import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ReactNode } from "react";
import type { BusinessDataSource } from "@/components/business-app/business-data";
import type { BusinessDossier, BusinessDraftRevision, BusinessFacts } from "@/lib/business-dossier";

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

async function render(node: ReactNode) {
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
  await act(async () => { root.render(<I18nextProvider i18n={i18n}>{node}</I18nextProvider>); });
  return { host, act, close: () => act(async () => { root.unmount(); host.remove(); }) };
}

const actor = (name: string, kind: "member" | "extractor" = "member") => ({ actor_id: name, actor_kind: kind, display_name: name, grant_id: "g", issuer_id: "o", issuer_display_name: "Dueño" });
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
    assert.equal(section.querySelector("h3")?.textContent, "Historial");
    const lines = () => [...section.querySelectorAll("li")].map((item) => [...item.querySelectorAll("p")].map((line) => line.textContent));
    assert.deepEqual(lines(), [
      ["Moneda cambiada de DOP a USD", "Ana Peña · 11/10, 8:00 a.m."],
      ["Aprobado", "Lucía Mateo · 11/10, 12:05 a.m."],
      ["Monto cambiado de RD$ 1,200.00 a RD$ 1,250.00", "Ana Peña · 10/10, 1:05 p.m."],
    ], "collapsed to the newest three");
    const dots = [...section.querySelectorAll<HTMLElement>('[data-testid="history-dot"]')].map((dot) => dot.style.backgroundColor);
    assert.deepEqual(dots, ["#56635e", "#2f5a49", "#56635e"], "gray dots except the status change");
    assert.equal(section.querySelectorAll("li svg").length, 0, "no icon per event");
    const seeAll = [...section.querySelectorAll("button")].find((button) => button.textContent === "Ver todo")!;
    await page.act(async () => { seeAll.click(); });
    assert.deepEqual(lines().slice(3), [["Leído", "Cuadrao · 10/10, 9:25 a.m."], ["Recibido · WhatsApp", "10/10, 9:20 a.m."]]);
    assert.equal([...section.querySelectorAll("button")].some((button) => button.textContent === "Ver todo"), false);
    assert.doesNotMatch(section.textContent ?? "", /revisi[oó]n|tras aprobar|primer flujo|registrado|desconocido/i);
    assert.equal(document.activeElement, section.querySelectorAll("li")[3], "focus lands on the first event Ver todo revealed");
    await page.close();
  });

  test("names the channel a receipt came in by: Correo and Subido", async () => {
    const { default: ReceiptHistory } = await import("@/components/business-app/ReceiptHistory");
    for (const [channel, word] of [["email", "Correo"], ["web", "Subido"]] as const) {
      const sources = [{ id: "s", kind: "attachment", channel, received_at: at(10, 9, 0), connection_id: "c", filename: null, media_type: "application/pdf" }] as BusinessDossier["sources"];
      const page = await render(<ReceiptHistory history={[]} accounts={[]} sources={sources} />);
      assert.equal(page.host.querySelector("li p")?.textContent, `Recibido · ${word}`);
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
    assert.deepEqual([...page.host.querySelectorAll("li > p:first-of-type")].map((line) => line.textContent), ["Recibido · WhatsApp"]);
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
    assert.deepEqual([...page.host.querySelectorAll("li > p:first-of-type")].map((line) => line.textContent), ["Monto cambiado de RD$ 100.00 a US$ 200.00", "Moneda cambiada de DOP a USD"]);
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
    assert.deepEqual(text.sort(), ["Moneda: DOP", "Monto: RD$ 500.00"]);
    await page.close();
  });
});

describe("historyWhen", () => {
  test("writes DD/MM, h:mm with a.m. and p.m.", async () => {
    const { historyWhen } = await import("@/components/business-app/ReceiptHistory");
    assert.equal(historyWhen(at(10, 9, 25), "a.m.", "p.m."), "10/10, 9:25 a.m.");
    assert.equal(historyWhen(at(3, 13, 5), "a.m.", "p.m."), "03/10, 1:05 p.m.");
    assert.equal(historyWhen(at(3, 0, 5), "a.m.", "p.m."), "03/10, 12:05 a.m.");
    assert.equal(historyWhen(at(3, 12, 0), "a.m.", "p.m."), "03/10, 12:00 p.m.");
  });
});

describe("the AI reading state", () => {
  test("holds Proveedor, NCF, ITBIS and Total as empty bars, says Leyendo tu recibo…, sweeps the source, and hides the total", async () => {
    const { BusinessWorkspaceProvider } = await import("@/components/business-app/BusinessWorkspace");
    const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
    const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
    const ReceiptReviewPanel = (await import("@/components/business-app/ReceiptReviewPanel")).default;
    const fixture = createFixtureBusinessDataSource({ chatAvailable: false });
    const source: BusinessDataSource = {
      ...fixture,
      receipt: async (id, signal) => ({ ...await fixture.receipt(id, signal), activity: { state: "reading", unread: false, completion_cursor: null }, bandeja: { por_revisar: false, con_problema: false, leyendo: true } }),
    };
    const page = await render(<BusinessConsentTestProvider accepted><BusinessWorkspaceProvider source={source}><ReceiptReviewPanel target={{ kind: "receipt", id: "rcpt-ferreteria" }} /></BusinessWorkspaceProvider></BusinessConsentTestProvider>);
    for (let i = 0; i < 80 && !page.host.querySelector('[data-testid="receipt-reading-state"]'); i += 1) await page.act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
    const state = page.host.querySelector('[data-testid="receipt-reading-state"]')!;
    assert.equal(state.querySelector('[role="status"]')?.textContent, "Leyendo tu recibo…");
    assert.deepEqual([...state.querySelectorAll("dt")].map((label) => label.textContent), ["Proveedor", "NCF", "ITBIS", "Total"]);
    assert.ok([...state.querySelectorAll("dd")].every((bar) => bar.textContent === "" && bar.className.includes("bg-[#e3ebe1]")));
    assert.equal(page.host.querySelector('[data-testid="receipt-total"]'), null, "the amount waits for the read");
    assert.doesNotMatch(page.host.querySelector('[data-testid="receipt-top-block"]')?.textContent ?? "", /RD\$|0\.00/);
    assert.ok(page.host.querySelector('[data-testid="receipt-review-source"] [data-testid="receipt-reading-band"]'), "the band sweeps the source");
    assert.equal(page.host.querySelector('[data-testid="receipt-review-fields"] input'), null, "no field to fill before the read returns");
    await page.close();
  });
});
