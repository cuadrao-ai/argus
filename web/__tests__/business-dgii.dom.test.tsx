import assert from "node:assert/strict";
import { test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import FiscalDeclarationEditor from "@/components/business-app/FiscalDeclarationEditor";
import { reviewDgii, reviewPurchase, type DgiiFields } from "@/lib/business-dgii";
import BusinessFiscalProfile from "@/components/business-app/BusinessFiscalProfile";
import { createDossierFixtures, dossierFixtureIds } from "@/components/business-app/dossier-fixtures";
import type { BusinessDossier } from "@/lib/business-dossier";
import spanish from "@/public/locales/es-419/common.json";

const fields = { "606": [
  { name: "rnc", label: "RNC o Cédula", kind: "text", options: [] },
  { name: "ncf", label: "NCF", kind: "text", options: [] },
  { name: "itbis", label: "ITBIS Facturado", kind: "money", options: [] },
  { name: "category", label: "Tipo Bienes y Servicios Comprados", kind: "select", options: ["01", "09"] },
  { name: "payment_method", label: "Forma de Pago", kind: "select", options: ["01", "02"] },
  { name: "itbis_cost", label: "ITBIS llevado al Costo", kind: "money", options: [] },
], "607": [] } as const satisfies Record<"606" | "607", readonly unknown[]>;

function registerDom() {
  const original = { fetch: globalThis.fetch, mock: process.env.NEXT_PUBLIC_MOCK_AUTH };
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { value: true, configurable: true, writable: true });
  return async () => {
    globalThis.fetch = original.fetch;
    if (original.mock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
    else process.env.NEXT_PUBLIC_MOCK_AUTH = original.mock;
    await GlobalRegistrator.unregister();
  };
}

async function mountEditor(shape: { fields?: DgiiFields; dossier?: (dossier: BusinessDossier) => BusinessDossier } = {}) {
  const release = registerDom();
  const fixture = await createDossierFixtures([{ id: "cash", type: "cash", currency: "DOP", nickname: "PRÁCTICA caja" }]).dossier(dossierFixtureIds.fiscal);
  const dossier = shape.dossier?.(fixture) ?? fixture;
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const writes: { key: string | null; input: Record<string, unknown> }[] = [];
  let fail = false;
  globalThis.fetch = async (url, init) => {
    writes.push({ key: new Headers(init?.headers).get("Idempotency-Key"), input: JSON.parse(String(init?.body)) });
    if (fail) throw new Error("lost response");
    return Response.json({ ...dossier, version: dossier.version + 1 });
  };
  const host = document.createElement("div"); document.body.append(host);
  const root = createRoot(host);
  const changes: BusinessDossier[] = [];
  const dirty: boolean[] = [];
  await act(async () => { root.render(<I18nextProvider i18n={i18n}><FiscalDeclarationEditor dossier={dossier} fields={(shape.fields ?? fields) as never} reviewFiscal={reviewDgii} disabled={false} onChanged={(value) => changes.push(value)} onBusy={() => {}} onDirty={(value) => dirty.push(value)} /></I18nextProvider>); });
  const input = async (label: string, value: string) => {
    const control = [...host.querySelectorAll("label")].find((node) => node.firstChild?.textContent === label)?.querySelector("input");
    assert.ok(control);
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
      assert.ok(setter); setter.call(control, value);
      control.dispatchEvent(new Event("input", { bubbles: true }));
    });
  };
  const save = async () => { const button = [...host.querySelectorAll("button")].find((node) => node.textContent === "Guardar revisión fiscal"); assert.ok(button); await act(async () => button.click()); };
  return { host, dossier, writes, dirty, changes, input, save, fail: () => { fail = true; }, dispose: async () => { await act(async () => root.unmount()); host.remove(); await release(); } };
}

test("the form holds the rest of the 606: the facts with their own row are not fields here, and it sends them unchanged", async () => {
  const view = await mountEditor();
  try {
    assert.equal(view.host.querySelector("details")?.open, false, "closed by default");
    assert.equal(view.host.querySelector("summary")?.textContent, "Más datos fiscales");
    assert.deepEqual([...view.host.querySelectorAll("label")].map((node) => node.firstChild?.textContent).slice(0, 1), ["ITBIS llevado al Costo"]);
    await view.input("ITBIS llevado al Costo", "12.00");
    assert.equal(view.dirty.at(-1), true);
    await view.save();
    const request = view.writes[0];
    assert.ok(request.key);
    assert.deepEqual(request.input, { version: view.dossier.version, dgii: { fiscal: { rnc: "131999888", ncf: "B0100000099", itbis: "526.27" }, declaration: { form: "606", category: null, itbis_cost: "12.00", payment_method: null, actual_refund: false, purchase_activity_id: null } } });
    assert.equal(view.changes.length, 1);
    assert.equal(view.dirty.at(-1), false);
  } finally { await view.dispose(); }
});

const field = (name: string, label: string, kind: DgiiFields["606"][number]["kind"] = "money", options: string[] = []) => ({ name, label, kind, options });
const fullForm: DgiiFields = {
  "606": [
    field("id_type", "Tipo Id", "select", ["1", "2"]), field("modified_ncf", "NCF Modificado", "text"), field("paid_on", "Fecha Pago", "date"),
    field("services_amount", "Servicios"), field("itbis_cost", "ITBIS al Costo"), field("itbis_withheld", "ITBIS Retenido"),
    field("legal_tip", "Propina"), field("a_new_server_column", "Columna nueva"),
  ],
  "607": [field("income_type", "Tipo de Ingreso", "select", ["1"]), field("withheld_on", "Fecha de Retención", "date")],
};
const groupsOf = (host: Element) => [...host.querySelectorAll<HTMLElement>("[data-group]")].map((group) => [group.dataset.group, group.querySelector("h4")?.textContent]);

test("the fields read in five groups, every field the server sends stays, and no date is a native input", async () => {
  const view = await mountEditor({ fields: fullForm });
  try {
    assert.deepEqual(groupsOf(view.host), [["identity", "Identificación"], ["amounts", "Montos"], ["itbis", "ITBIS"], ["retentions", "Retenciones"], ["other", "Otros"]]);
    const other = view.host.querySelector('[data-group="other"]');
    assert.ok(other?.textContent?.includes("Columna nueva"), "a column no group names still shows");
    assert.equal(view.host.querySelectorAll('input[type="date"]').length, 0);
    assert.ok(view.host.querySelector('[data-group="identity"] [aria-label="Abrir calendario"]'), "the date is our calendar");
    assert.ok(view.host.querySelector('[data-testid="fiscal-declaration-services_amount"]'), "an amount is our money field");
  } finally { await view.dispose(); }
});

test("a date reaches the server as a day, and text that is not a date holds the save and says why", async () => {
  const view = await mountEditor({ fields: fullForm });
  try {
    const date = view.host.querySelector<HTMLInputElement>("#fiscal-declaration-paid_on");
    assert.ok(date);
    const type = (text: string) => act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(date, text);
      date.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await type("31/02/2026");
    await view.save();
    assert.equal(view.writes.length, 0, "a day that does not exist is not sent");
    assert.ok(view.host.querySelector('[role="alert"]')?.textContent?.includes("fecha válida"));
    await type("15/10/2026");
    await view.save();
    assert.equal((view.writes[0].input as { dgii: { declaration: Record<string, unknown> } }).dgii.declaration.paid_on, "2026-10-15");
  } finally { await view.dispose(); }
});

test("Formato shows only when the record does not say the form", async () => {
  const formato = (host: Element) => [...host.querySelectorAll("label")].some((node) => node.textContent?.startsWith("Formato"));
  const known = await mountEditor({ fields: fullForm });
  assert.equal(formato(known.host), false, "an expense is a 606");
  await known.dispose();
  const income = await mountEditor({ fields: fullForm, dossier: (dossier) => ({ ...dossier, facts: { ...dossier.facts, kind: { ...dossier.facts.kind, state: "known", value: "income" } as never } }) });
  assert.equal(formato(income.host), false, "income is a 607");
  assert.ok(income.host.querySelector("#fiscal-declaration-withheld_on"), "and it shows the 607's fields");
  await income.dispose();
  const open = await mountEditor({ fields: fullForm, dossier: (dossier) => ({ ...dossier, facts: { ...dossier.facts, kind: { state: "unknown", value: null, origin: null, verified: false, source_ids: [] } as never } }) });
  assert.equal(formato(open.host), true, "an unknown kind leaves the choice");
  await open.dispose();
  const saved = await mountEditor({ fields: fullForm, dossier: (dossier) => ({ ...dossier, dgii: { form: "607" } }) });
  assert.equal(formato(saved.host), true, "a saved declaration that disagrees stays changeable");
  await saved.dispose();
});

test("a lost fiscal review response retains the exact request key and blocks edits", async () => {
  const view = await mountEditor();
  try {
    await view.input("ITBIS llevado al Costo", "12.00");
    view.fail(); await view.save();
    assert.ok(view.host.querySelector('[role="alert"] [data-testid="error-reference"]'), "the failure shows its reference");
    assert.ok([...view.host.querySelectorAll("input")].every((input) => input.disabled));
    await view.save();
    assert.deepEqual(view.writes[1], view.writes[0]);
    assert.equal(view.changes.length, 0);
    assert.equal(view.dirty.at(-1), true);
  } finally { await view.dispose(); }
});

test("an owner's 606 choice is one purchase write with its key, not a declaration", async () => {
  const sent: { url: string; key: string | null; body: unknown }[] = [];
  const original = globalThis.fetch;
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  globalThis.fetch = async (url, init) => { sent.push({ url: String(url), key: new Headers(init?.headers).get("Idempotency-Key"), body: JSON.parse(String(init?.body)) }); return Response.json({}); };
  try {
    await reviewPurchase("draft-1", 4, { category: "02" }, "key-1");
    assert.ok(sent[0].url.endsWith("/business/drafts/draft-1/review"));
    assert.equal(sent[0].key, "key-1");
    assert.deepEqual(sent[0].body, { version: 4, purchase: { category: "02" } });
  } finally { globalThis.fetch = original; }
});

test("an absent Business RNC shows No aplica and a read-only accountant cannot edit it", async () => {
  const release = registerDom();
  globalThis.fetch = async () => Response.json({ name: "Taller Norte", tax_id: null, can_edit: false });
  const i18n = i18next.createInstance(); await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  try {
    await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessFiscalProfile /></I18nextProvider>));
    assert.match(host.textContent ?? "", /Taller Norte/);
    assert.match(host.textContent ?? "", /No aplica/);
    assert.equal(host.querySelectorAll("input, button, select").length, 0);
  } finally { await act(async () => root.unmount()); host.remove(); await release(); }
});

test("the owner can save an eleven-digit filer cedula without losing leading zeros", async () => {
  const release = registerDom();
  const writes: unknown[] = [];
  globalThis.fetch = async (_url, init) => {
    if (!init?.body) return Response.json({ name: "Mi negocio", tax_id: null, can_edit: true });
    writes.push(JSON.parse(String(init.body)));
    return Response.json({ name: "Taller Norte", tax_id: { type: "cedula", value: "00100000001" }, can_edit: true });
  };
  const i18n = i18next.createInstance(); await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  try {
    await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessFiscalProfile /></I18nextProvider>));
    const name = host.querySelector<HTMLInputElement>('input[name="business-name"]');
    const kind = host.querySelector<HTMLSelectElement>('select[name="tax-id-type"]');
    const value = host.querySelector<HTMLInputElement>('input[name="tax-id-value"]');
    const button = host.querySelector("button");
    assert.ok(name && kind && value && button);
    assert.equal(value.maxLength, 13);
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
      assert.ok(setter);
      setter.call(name, "Taller Norte");
      name.dispatchEvent(new Event("input", { bubbles: true }));
      kind.value = "cedula";
      kind.dispatchEvent(new Event("change", { bubbles: true }));
      setter.call(value, "001-0000000-1");
      value.dispatchEvent(new Event("input", { bubbles: true }));
    });
    assert.equal(button.disabled, false);
    await act(async () => button.click());
    assert.deepEqual(writes, [{
      name: "Taller Norte",
      previous_name: "Mi negocio",
      tax_id: { type: "cedula", value: "001-0000000-1" },
      previous_tax_id: null,
    }]);
    assert.equal(value.value, "00100000001", "the saved number keeps its leading zeros");
    assert.equal(kind.value, "cedula");
  } finally { await act(async () => root.unmount()); host.remove(); await release(); }
});
