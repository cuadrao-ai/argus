import assert from "node:assert/strict";
import { test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import FiscalDeclarationEditor from "@/components/business-app/FiscalDeclarationEditor";
import BusinessFiscalProfile from "@/components/business-app/BusinessFiscalProfile";
import { createDossierFixtures, dossierFixtureIds } from "@/components/business-app/dossier-fixtures";
import type { BusinessDossier } from "@/lib/business-dossier";
import spanish from "@/public/locales/es-419/common.json";

const fields = { "606": [
  { name: "rnc", label: "RNC o Cédula", kind: "text", options: [] },
  { name: "ncf", label: "NCF", kind: "text", options: [] },
  { name: "itbis", label: "ITBIS Facturado", kind: "money", options: [] },
  { name: "category", label: "Tipo Bienes y Servicios Comprados", kind: "select", options: ["01", "09"] },
  { name: "itbis_cost", label: "ITBIS llevado al Costo", kind: "money", options: [] },
], "607": [] };

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
  const dossier = await createDossierFixtures([{ id: "cash", type: "cash", currency: "DOP", nickname: "PRÁCTICA caja" }]).dossier(dossierFixtureIds.ready);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const writes: { key: string | null; input: Record<string, unknown> }[] = [];
  let fail = false;
  globalThis.fetch = async (url, init) => {
    if (String(url).endsWith("/fields")) return Response.json(fields);
    writes.push({ key: new Headers(init?.headers).get("Idempotency-Key"), input: JSON.parse(String(init?.body)) });
    if (fail) throw new Error("lost response");
    return Response.json({ ...dossier, version: dossier.version + 1 });
  };
  const host = document.createElement("div"); document.body.append(host);
  const root = createRoot(host);
  const changes: BusinessDossier[] = [];
  const dirty: boolean[] = [];
  await act(async () => { root.render(<I18nextProvider i18n={i18n}><FiscalDeclarationEditor dossier={dossier} disabled={false} onChanged={(value) => changes.push(value)} onBusy={() => {}} onDirty={(value) => dirty.push(value)} /></I18nextProvider>); });
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

test("human fiscal review keeps unknown tax values blank and sends one reviewed version", async () => {
  const view = await mountEditor();
  try {
    await view.input("RNC o Cédula", "199990021");
    await view.input("NCF", "B0100000001");
    await view.input("ITBIS Facturado", "180.00");
    assert.equal(view.dirty.at(-1), true);
    await view.save();
    const request = view.writes[0];
    assert.ok(request.key);
    assert.deepEqual(request.input, { version: view.dossier.version, dgii: { fiscal: { rnc: "199990021", ncf: "B0100000001", itbis: "180.00" }, declaration: { form: "606", category: null, itbis_cost: null, actual_refund: false, purchase_activity_id: null } } });
    assert.equal(view.changes.length, 1);
    assert.equal(view.dirty.at(-1), false);
  } finally { await view.dispose(); }
});

test("a lost fiscal review response retains the exact request key and blocks edits", async () => {
  const view = await mountEditor();
  try {
    await view.input("NCF", "B0100000001");
    view.fail(); await view.save();
    assert.ok(view.host.querySelector('[role="alert"]'));
    assert.ok([...view.host.querySelectorAll("input")].every((input) => input.disabled));
    await view.save();
    assert.deepEqual(view.writes[1], view.writes[0]);
    assert.equal(view.changes.length, 0);
    assert.equal(view.dirty.at(-1), true);
  } finally { await view.dispose(); }
});

test("an absent Business RNC shows No aplica and a read-only accountant cannot edit it", async () => {
  const release = registerDom();
  globalThis.fetch = async () => Response.json({ rnc: null, can_edit: false });
  const i18n = i18next.createInstance(); await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  try {
    await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessFiscalProfile /></I18nextProvider>));
    assert.match(host.textContent ?? "", /606 \/ 607 · No aplica/);
    assert.equal(host.querySelectorAll("input, button").length, 0);
  } finally { await act(async () => root.unmount()); host.remove(); await release(); }
});

test("the owner can save an eleven-digit filer cedula without losing leading zeros", async () => {
  const release = registerDom();
  const writes: unknown[] = [];
  globalThis.fetch = async (_url, init) => {
    if (!init?.body) return Response.json({ rnc: null, can_edit: true });
    writes.push(JSON.parse(String(init.body)));
    return Response.json({ rnc: "00100000001", can_edit: true });
  };
  const i18n = i18next.createInstance(); await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  try {
    await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessFiscalProfile /></I18nextProvider>));
    const input = host.querySelector("input"); const button = host.querySelector("button");
    assert.ok(input && button); assert.equal(input.maxLength, 11);
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
      assert.ok(setter); setter.call(input, "00100000001");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    assert.equal(button.disabled, false);
    await act(async () => button.click());
    assert.deepEqual(writes, [{ rnc: "00100000001", previous_rnc: null }]);
    assert.match(host.textContent ?? "", /00100000001/);
  } finally { await act(async () => root.unmount()); host.remove(); await release(); }
});
