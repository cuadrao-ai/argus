import assert from "node:assert/strict";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import FiscalDeclarationEditor from "@/components/business-app/FiscalDeclarationEditor";
import { createDossierFixtures, dossierFixtureIds } from "@/components/business-app/dossier-fixtures";
import { reviewDgii, type DgiiFields, type DgiiReview } from "@/lib/business-dgii";
import type { BusinessDossier } from "@/lib/business-dossier";
import { dgiiChoiceLabel } from "@/lib/dgii-labels";
import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";

export const fields: DgiiFields = { "606": [
  { name: "rnc", label: "RNC o Cédula", kind: "text", options: [] },
  { name: "ncf", label: "NCF", kind: "text", options: [] },
  { name: "itbis", label: "ITBIS Facturado", kind: "money", options: [] },
  { name: "category", label: "Tipo Bienes y Servicios Comprados", kind: "select", options: ["01", "09"] },
  { name: "payment_method", label: "Forma de Pago", kind: "select", options: ["01", "02"] },
  { name: "itbis_cost", label: "ITBIS llevado al Costo", kind: "money", options: [] },
], "607": [] };

export function registerDom(width?: number) {
  const original = { fetch: globalThis.fetch, mock: process.env.NEXT_PUBLIC_MOCK_AUTH };
  GlobalRegistrator.register({ url: "http://localhost/biz", ...(width ? { width } : {}) });
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { value: true, configurable: true, writable: true });
  return async () => {
    globalThis.fetch = original.fetch;
    if (original.mock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
    else process.env.NEXT_PUBLIC_MOCK_AUTH = original.mock;
    await GlobalRegistrator.unregister();
  };
}

export async function mountEditor(shape: { productionI18n?: boolean; fields?: DgiiFields; width?: number; dossier?: (dossier: BusinessDossier) => BusinessDossier } = {}) {
  const release = registerDom(shape.width);
  const fixture = await createDossierFixtures([{ id: "cash", type: "cash", currency: "DOP", nickname: "PRÁCTICA caja" }]).dossier(dossierFixtureIds.fiscal);
  const dossier = shape.dossier?.(fixture) ?? fixture;
  let current = dossier;
  const writes: { key: string | null; input: { version: number; dgii: DgiiReview } }[] = [];
  let fail = false;
  globalThis.fetch = async (url, init) => {
    if (String(url).startsWith("/locales/")) return Response.json(String(url).includes("/en/") ? english : spanish);
    const input = JSON.parse(String(init?.body)) as { version: number; dgii: DgiiReview };
    writes.push({ key: new Headers(init?.headers).get("Idempotency-Key"), input });
    if (fail) throw new Error("lost response");
    const restored = (input as unknown as { montos?: { restore_inherited?: string[] } }).montos?.restore_inherited ?? [];
    const declaration = { ...input.dgii.declaration };
    const inheritance = { ...current.inheritance };
    for (const name of restored) {
      const link = inheritance[name];
      if (link) { declaration[name] = link.value; inheritance[name] = { ...link, inherited: true }; }
    }
    return Response.json({ ...current, version: current.version + 1, dgii: declaration, inheritance });
  };
  const options = shape.productionI18n ? (await import("@/lib/i18n")).default.options : {};
  const namespace = shape.productionI18n ? "common" : "translation";
  const i18n = i18next.createInstance().use(dgiiChoiceLabel);
  await i18n.init({ postProcess: dgiiChoiceLabel.name, postProcessPassResolved: true, ...options, lng: "es-419", resources: { "es-419": { [namespace]: spanish }, en: { [namespace]: english } } });
  const host = document.createElement("div"); document.body.append(host);
  const root = createRoot(host);
  const changes: BusinessDossier[] = [];
  const dirty: boolean[] = [];
  const onChanged = (value: BusinessDossier) => { changes.push(value); current = value; render(); };
  const onDirty = (value: boolean) => { dirty.push(value); };
  const onBusy = () => {};
  const render = () => root.render(<I18nextProvider i18n={i18n}><FiscalDeclarationEditor key={current.version} dossier={current} fields={shape.fields ?? fields} reviewFiscal={reviewDgii} disabled={false} onChanged={onChanged} onBusy={onBusy} onDirty={onDirty} /></I18nextProvider>);
  await act(async () => render());
  const row = (name: string) => {
    const element = host.querySelector(`[data-fact="${name}"]`);
    assert.ok(element, name);
    return element;
  };
  const click = async (name: string, selector: string) => {
    const button = row(name).querySelector<HTMLButtonElement>(selector);
    assert.ok(button, `${name}: ${selector}`);
    await act(async () => button.click());
  };
  const open = (name: string) => click(name, "button[data-row-value]");
  const save = (name: string) => click(name, 'button[aria-label^="Guardar ·"]');
  const cancel = (name: string) => click(name, 'button[aria-label^="Cancelar ·"], button[aria-label^="Cancel ·"]');
  const input = async (name: string, value: string) => {
    const control = row(name).querySelector("input");
    assert.ok(control, name);
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
      assert.ok(setter); setter.call(control, value);
      control.dispatchEvent(new Event("input", { bubbles: true }));
    });
  };
  return { host, dossier, writes, dirty, changes, row, open, input, save, cancel, i18n, fail: () => { fail = true; }, dispose: async () => { await act(async () => root.unmount()); host.remove(); await release(); } };
}

export const field = (name: string, label: string, kind: DgiiFields["606"][number]["kind"] = "money", options: string[] = []) => ({ name, label, kind, options });
export const fullForm: DgiiFields = {
  "606": [
    field("id_type", "Tipo Id", "select", ["1", "2"]), field("modified_ncf", "NCF Modificado", "text"), field("paid_on", "Fecha Pago", "date"),
    field("services_amount", "Servicios"), field("itbis_cost", "ITBIS al Costo"), field("itbis_withheld", "ITBIS Retenido"),
    field("legal_tip", "Propina"), field("a_new_server_column", "Columna nueva"),
  ],
  "607": [field("income_type", "Tipo de Ingreso", "select", ["1"]), field("withheld_on", "Fecha de Retención", "date")],
};
