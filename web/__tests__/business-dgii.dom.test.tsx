import assert from "node:assert/strict";
import { test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import FiscalDeclarationEditor from "@/components/business-app/FiscalDeclarationEditor";
import { reviewDgii, reviewPurchase } from "@/lib/business-dgii";
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

async function mountEditor() {
  const release = registerDom();
  const dossier = await createDossierFixtures([{ id: "cash", type: "cash", currency: "DOP", nickname: "PRÁCTICA caja" }]).dossier(dossierFixtureIds.fiscal);
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
  await act(async () => { root.render(<I18nextProvider i18n={i18n}><FiscalDeclarationEditor dossier={dossier} fields={fields as never} reviewFiscal={reviewDgii} disabled={false} onChanged={(value) => changes.push(value)} onBusy={() => {}} onDirty={(value) => dirty.push(value)} /></I18nextProvider>); });
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
    assert.deepEqual([...view.host.querySelectorAll("label")].map((node) => node.textContent).slice(0, 2), ["Formato606607", "ITBIS llevado al Costo"]);
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
