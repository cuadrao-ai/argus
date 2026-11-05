import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";

// Negocio, Datos: the name and RNC form on the shared field, over the same
// fiscal-profile read and write it used before.
const mockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
const realFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = realFetch;
  document.body.innerHTML = "";
});
afterAll(async () => {
  if (mockAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  else process.env.NEXT_PUBLIC_MOCK_AUTH = mockAuth;
  await GlobalRegistrator.unregister();
});

const rnc = () => `1${Array.from({ length: 8 }, () => Math.floor(Math.random() * 10)).join("")}`;

async function mount(start: { name: string; tax_id: { type: "rnc" | "cedula"; value: string } | null }, failWrites = false) {
  const writes: unknown[] = [];
  globalThis.fetch = (async (_url: string, init?: RequestInit) => {
    if (!init?.body) return Response.json({ ...start, can_edit: true });
    const body = JSON.parse(String(init.body));
    writes.push(body);
    if (failWrites) return Response.json({ detail: "unavailable" }, { status: 500 });
    return Response.json({ name: body.name, tax_id: body.tax_id, can_edit: true });
  }) as typeof fetch;
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { default: BusinessFiscalProfile } = await import("@/components/business-app/BusinessFiscalProfile");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessFiscalProfile /></I18nextProvider>));
  for (let i = 0; i < 40 && !host.querySelector("form"); i += 1) {
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)); });
  }
  const field = (name: string) => host.querySelector<HTMLInputElement>(`[name="${name}"]`) as HTMLInputElement;
  const note = (name: string) => document.getElementById(`${field(name).id}-note`)?.textContent;
  const type = (name: string, value: string) => act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(field(name), value);
    field(name).dispatchEvent(new Event("input", { bubbles: true }));
  });
  const leave = (name: string) => act(async () => { field(name).focus(); field(name).blur(); });
  const save = () => act(async () => { host.querySelector<HTMLButtonElement>('button[type="submit"]')?.click(); });
  return { host, writes, field, note, type, leave, save, close: () => act(async () => root.unmount()) };
}

describe("Negocio, Datos", () => {
  test("every field has a label above it and the RNC is text with a numeric keyboard", async () => {
    const form = await mount({ name: "Ferretería Luna", tax_id: { type: "rnc", value: rnc() } });
    try {
      const labels = [...form.host.querySelectorAll("label")].map((label) => [label.textContent, form.host.querySelector(`#${CSS.escape(label.htmlFor)}`)?.tagName]);
      assert.deepEqual(labels, [["Nombre del negocio *", "INPUT"], ["Identificación", "SELECT"], ["Número(Opcional)", "INPUT"]]);
      assert.equal(form.field("tax-id-value").type, "text");
      assert.equal(form.field("tax-id-value").inputMode, "numeric");
      assert.equal(form.note("tax-id-value"), "9 dígitos. Puedes usar guiones.");
    } finally {
      await form.close();
    }
  });

  test("a short RNC waits for the owner to leave the field, then names the length and clears once fixed", async () => {
    const form = await mount({ name: "Ferretería Luna", tax_id: null });
    try {
      await form.type("tax-id-value", "1234");
      assert.equal(form.field("tax-id-value").getAttribute("aria-invalid"), null);
      await form.leave("tax-id-value");
      assert.equal(form.note("tax-id-value"), "Un RNC tiene 9 dígitos.");
      const value = rnc();
      await form.type("tax-id-value", value);
      assert.equal(form.note("tax-id-value"), "9 dígitos. Puedes usar guiones.");
      await form.save();
      assert.deepEqual(form.writes, [{ name: "Ferretería Luna", previous_name: "Ferretería Luna", tax_id: { type: "rnc", value }, previous_tax_id: null }]);
    } finally {
      await form.close();
    }
  });

  test("a failed save says so beside the form, with Reintentar under its text, and keeps what was typed", async () => {
    const form = await mount({ name: "Ferretería Luna", tax_id: null }, true);
    try {
      const value = rnc();
      await form.type("tax-id-value", value);
      await form.save();
      for (let i = 0; i < 20 && !form.host.querySelector('[role="alert"]'); i += 1) {
        await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)); });
      }
      const alert = form.host.querySelector('[role="alert"]');
      const retry = alert?.querySelector("button");
      assert.equal(retry?.textContent, "Reintentar");
      assert.equal(retry?.parentElement, alert?.querySelector("p")?.parentElement, "the retry sits in the text's column");
      assert.equal(form.field("tax-id-value").value, value);
      await act(async () => retry?.click());
      assert.equal(form.writes.length, 2, "Reintentar sends the save again");
    } finally {
      await form.close();
    }
  });

  test("saving without a name lists it in the summary and sends nothing", async () => {
    const form = await mount({ name: "Ferretería Luna", tax_id: null });
    try {
      await form.type("business-name", "");
      await form.save();
      const summary = form.host.querySelector('[data-testid="form-error-summary"]');
      assert.deepEqual([...(summary?.querySelectorAll("a") ?? [])].map((link) => link.textContent), ["Nombre del negocio"]);
      assert.equal(form.note("business-name"), "Escribe el nombre del negocio.");
      assert.deepEqual(form.writes, []);
    } finally {
      await form.close();
    }
  });
});
