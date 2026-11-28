import { afterAll, afterEach, beforeAll, expect, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { I18nextProvider } from "react-i18next";
import i18next from "i18next";
import WhatsAppHeldFiles from "@/components/settings/WhatsAppHeldFiles";
import { clearToasts } from "@/components/business-app/foundation/toasts";
import spanish from "@/public/locales/es-419/common.json";
import type { WhatsAppHeldFile } from "@/lib/whatsapp-link-api";

const i18n = i18next.createInstance();
const originalFetch = globalThis.fetch;
const mockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
let root: Root;

beforeAll(async () => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
});
afterEach(async () => {
  if (root) await act(async () => root.unmount());
  document.body.replaceChildren();
  clearToasts();
  globalThis.fetch = originalFetch;
});
afterAll(async () => {
  if (mockAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  else process.env.NEXT_PUBLIC_MOCK_AUTH = mockAuth;
  await GlobalRegistrator.unregister();
});

const held = (reason: WhatsAppHeldFile["reason"], reading = false): WhatsAppHeldFile => ({
  id: reason, reason, reading, media_type: "image/jpeg",
  held_at: new Date().toISOString(), expires_at: new Date(Date.now() + 7 * 86400000).toISOString(),
  preview_url: "/api/v1/whatsapp/held-files/" + reason + "/preview",
});
const businesses = ["Taller de prueba", "Colmado de prueba", "Imprenta de prueba"].map((name, i) => ({ name, space_id: String(i) }));

async function open(files = [held("no_buyer_rnc")], receiving = businesses) {
  const submitted: unknown[] = [];
  const pending = Promise.withResolvers<Response>();
  const network = { listUnavailable: false };
  const view = { files, receiving_businesses: receiving };
  globalThis.fetch = (async (input, init) => {
    const path = new URL(String(input)).pathname;
    if (path.endsWith("/assign")) {
      submitted.push(JSON.parse(String(init?.body)));
      return pending.promise;
    }
    if (path.endsWith("/preview")) return new Response(new Blob(["fixture"], { type: "image/jpeg" }));
    if (path.endsWith("/held-files")) return network.listUnavailable ? new Response(null, { status: 503 }) : Response.json(view);
    throw new Error(path);
  }) as typeof fetch;
  const host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  const counts: number[] = [];
  await act(async () => root.render(<I18nextProvider i18n={i18n}>
    <WhatsAppHeldFiles onBack={() => {}} onCountChange={count => counts.push(count)} />
  </I18nextProvider>));
  return { pending, view, submitted, counts, network };
}
const button = (text: string) => [...document.querySelectorAll("button")].find(node => node.textContent === text)!;
const click = async (el: HTMLElement) => act(async () => el.click());
const option = (name: string) => [...document.querySelectorAll<HTMLElement>('[role="option"]')].find(el => el.textContent === name)!;

test("a chosen eligible Business receives the held file only after confirmation", async () => {
  const { submitted, pending, view, counts } = await open();
  expect(document.body.textContent).toContain("Sin RNC del comprador");
  expect(document.body.textContent).toContain("Se borra en 7 días");
  expect(button("Asignar").disabled).toBe(true);
  await click(button("Elige un negocio"));
  expect(document.querySelectorAll('[role="option"]')).toHaveLength(3);
  await click(option(businesses[0].name));
  await click(button("Asignar"));
  expect(submitted).toEqual([{ business_id: "0" }]);
  expect(button("Asignar").getAttribute("aria-busy")).toBe("true");
  expect(document.body.textContent).toContain("Sin RNC del comprador");
  view.files = [];
  await act(async () => pending.resolve(new Response(null, { status: 204 })));
  expect(document.activeElement?.textContent).toBe("Todo al día");
  expect(counts.at(-1)).toBe(0);
  expect(document.body.textContent).toContain("Archivo asignado a Taller de prueba.");
});

test("a lost grant leaves the file and removes that Business from the next picker", async () => {
  const { pending, view } = await open();
  await click(button("Elige un negocio"));
  await click(option(businesses[1].name));
  await click(button("Asignar"));
  view.receiving_businesses = [businesses[0], businesses[2]];
  await act(async () => pending.resolve(Response.json({ code: "business_permission_denied" }, { status: 403 })));
  expect(document.querySelector('[role="alert"]')?.textContent).toBe(spanish.workspace_setup_preview.upload_denied);
  expect(button("Asignar").disabled).toBe(true);
  await click(document.querySelector<HTMLButtonElement>('[aria-haspopup="listbox"]')!);
  expect(option(businesses[1].name)).toBeUndefined();
  expect(option(businesses[2].name)).toBeDefined();
});

test("reading prevents assignment, while tomorrow and failed reads can go to the single Business", async () => {
  await open([held("no_match", true), held("held_read_cap"), held("read_failed")], [businesses[0]]);
  expect(document.querySelector('[aria-haspopup="listbox"]')).toBeNull();
  expect(document.body.textContent).toContain("Leyendo…");
  expect(document.body.textContent).toContain(spanish.business.file_read.held_day);
  expect(document.body.textContent).toContain(spanish.business.bandeja.label.cant_read);
  expect([...document.querySelectorAll("button")].filter(el => el.textContent === "Asignar").map(el => el.disabled)).toEqual([true, false, false]);
});

test("without an eligible Business files stay visible with the setup notice", async () => {
  await open([held("no_eligible_business")], []);
  expect(document.body.textContent).toContain("Sin leer");
  expect(document.body.textContent).toContain(spanish.settings.whatsapp.setup_title);
  expect(button("Asignar")).toBeUndefined();
});

test("desktop picker moves focus with arrows and Escape restores its trigger", async () => {
  await open();
  const trigger = button("Elige un negocio");
  trigger.focus();
  await click(trigger);
  const first = option(businesses[0].name);
  expect(document.activeElement).toBe(first);
  await act(async () => first.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true })));
  expect(document.activeElement).toBe(option(businesses[1].name));
  await act(async () => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
  expect(document.querySelector('[role="listbox"]')).toBeNull();
  expect(document.activeElement).toBe(trigger);
});

test("the phone opens a content-fit sheet and choosing moves focus to Assign", async () => {
  const originalWidth = window.innerWidth;
  window.innerWidth = 390;
  try {
    await open();
    const trigger = button("Elige un negocio");
    await click(trigger);
    const sheet = document.querySelector('[role="dialog"]');
    expect(sheet?.getAttribute("data-snap")).toBe("fit");
    await click(option(businesses[2].name));
    await act(async () => { await new Promise<void>(resolve => requestAnimationFrame(() => resolve())); });
    expect(document.querySelector('[role="dialog"]')).toBeNull();
    expect(document.activeElement).toBe(button("Asignar"));
    expect(trigger.textContent).toBe(businesses[2].name);
  } finally {
    window.innerWidth = originalWidth;
  }
});

test("a read starting after selection refuses assignment and keeps the file visible", async () => {
  const { pending, view } = await open([held("no_match")], [businesses[0]]);
  await click(button("Asignar"));
  view.files = [held("no_match", true)];
  await act(async () => pending.resolve(Response.json({ code: "document_busy" }, { status: 409 })));
  expect(button("Asignar").disabled).toBe(true);
  expect(document.body.textContent).toContain("Leyendo…");
  expect(document.querySelector('[data-testid="toast"]')).toBeNull();
});

test("one adoption reconciles all held rows the server assigned together", async () => {
  const { pending, view, counts } = await open([held("no_buyer_rnc"), held("no_match")], [businesses[0]]);
  await click(button("Asignar"));
  view.files = [];
  await act(async () => pending.resolve(new Response(null, { status: 204 })));
  expect(counts.at(-1)).toBe(0);
  expect(document.activeElement?.textContent).toBe("Todo al día");
});

test("a failed refresh after adoption preserves the confirmed removal and allows retry", async () => {
  const { pending, network, view, counts, submitted } = await open([held("no_buyer_rnc"), held("no_match")], [businesses[0]]);
  await click(button("Asignar"));
  view.files = [];
  network.listUnavailable = true;
  await act(async () => pending.resolve(new Response(null, { status: 204 })));
  expect(counts.at(-1)).toBe(1);
  expect(document.body.textContent).not.toContain("Sin RNC del comprador");
  expect(document.body.textContent).toContain("Archivo asignado a Taller de prueba.");
  expect(document.querySelector('[role="alert"]')).toBeTruthy();
  network.listUnavailable = false;
  await click(button(spanish.common.retry));
  expect(counts.at(-1)).toBe(0);
  expect(submitted).toHaveLength(1);
});

test("refusal of the sole Business requires a new choice even if exactly one replacement is eligible", async () => {
  const { pending, view, submitted } = await open([held("no_buyer_rnc")], [businesses[0]]);
  await click(button("Asignar"));
  view.receiving_businesses = [businesses[1]];
  await act(async () => pending.resolve(Response.json({ code: "business_permission_denied" }, { status: 403 })));
  expect(document.querySelector('[role="alert"]')?.textContent).toBe(spanish.workspace_setup_preview.upload_denied);
  expect(button("Asignar").disabled).toBe(true);
  const trigger = document.querySelector<HTMLButtonElement>('[aria-haspopup="listbox"]')!;
  expect(trigger.textContent).toBe(businesses[0].name);
  await click(trigger);
  expect(option(businesses[0].name)).toBeUndefined();
  await click(option(businesses[1].name));
  expect(button("Asignar").disabled).toBe(false);
  expect(submitted).toEqual([{ business_id: businesses[0].space_id }]);
});
