import assert from "node:assert/strict";
import { afterAll, beforeAll, test, spyOn } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import spanish from "@/public/locales/es-419/common.json";
import english from "@/public/locales/en/common.json";
import { createRoot } from "react-dom/client";
import BusinessLifecycleEntry from "@/components/business-app/BusinessLifecycleEntry";
import BusinessLifecycleControls from "@/components/business-app/BusinessLifecycleControls";
import { invalidateBrowserAuth } from "@/lib/browser-auth-generation";
import { getChosenGrant, setChosenGrant } from "@/lib/business-grant";

const originalFetch = globalThis.fetch;
const originalAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
const businesses = [
  { space_id: "39d12d09-bebe-4992-b6dc-cb1a84d52438", name: "Colmado Rosa", grant_id: "af2d018e-6e6c-4fc7-9602-9b0b31ff9bc0", role: "owner", capabilities: ["read", "prepare", "approve"], access_seen: true, member_count: 1, reopen_until: "2026-11-20T17:45:00Z", has_other_owner: false, export_windows: [{ start: "2025-01-01", end: "2025-12-31", record_count: 40 }, { start: "2026-01-01", end: "2026-10-21", record_count: 12 }], members: [{ grant_id: "4100626b-f480-4249-97bd-04bdc03f1a15", name: "Rosa", shown_as: "name", eligible: true, reason: null }] },
  { space_id: "49767c9c-9f8a-4af7-82e3-bcc065e09a19", name: "Taller Sol", grant_id: "b3acd38c-2e99-49aa-888f-4ee3a6268066", role: "owner", capabilities: ["read", "prepare", "approve"], access_seen: true, member_count: 0, reopen_until: "2026-11-20T17:45:00Z", has_other_owner: true, export_windows: [{ start: "2024-01-01", end: "2024-12-31", record_count: 3 }, { start: "2025-01-01", end: "2025-12-31", record_count: 5 }], members: [] },
];
beforeAll(() => { GlobalRegistrator.register({ url: "https://app.example.test/biz" }); (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; process.env.NEXT_PUBLIC_MOCK_AUTH = "true"; });
afterAll(async () => { globalThis.fetch = originalFetch; setChosenGrant(null); if (originalAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = originalAuth; await GlobalRegistrator.unregister(); });

async function mount(element: React.ReactNode, {
  commandFailure, deny = false, failExportOnce = false, locale = "es-419",
}: { commandFailure?: Response; deny?: boolean; failExportOnce?: boolean; locale?: "en" | "es-419" } = {}) {
  const calls: { path: string; method: string; key: string | null; grant: string | null; query: string; body?: unknown }[] = [];
  let failedExport = false;
  globalThis.fetch = async (url, init) => {
    const path = new URL(String(url)).pathname; const method = init?.method ?? "GET";
    calls.push({ path, method, key: new Headers(init?.headers).get("Idempotency-Key"), grant: new Headers(init?.headers).get("X-Business-Grant"), query: new URL(String(url)).search, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    if (path.endsWith("/business/exports")) {
      if (failExportOnce && calls.filter(call => call.path.endsWith("/business/exports")).length === 2 && !failedExport) {
        failedExport = true;
        return Response.json({ detail: { code: "unavailable" } }, { status: 503 });
      }
      return new Response("synthetic zip", { headers: { "Content-Type": "application/zip" } });
    }
    if (deny) return Response.json({ detail: { code: "business_unavailable" } }, { status: 404 });
    if (method === "POST") return commandFailure?.clone() ?? Response.json({ space_id: businesses[0].space_id, name: businesses[0].name, closed_at: "2026-10-18T05:00:00Z", reopen_until: "2026-11-17T05:00:00Z" });
    if (path.endsWith("/ownership-transfers")) return Response.json({ transfers: [] });
    if (path.endsWith("/closed-spaces")) return Response.json({ spaces: [{ space_id: businesses[1].space_id, name: businesses[1].name, closed_at: "2026-10-18T05:00:00Z", reopen_until: "2026-11-17T05:00:00Z" }] });
    return Response.json({ spaces: businesses });
  };
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  const i18n = i18next.createInstance(); await i18n.init({ lng: locale, resources: { "es-419": { translation: spanish }, en: { translation: english } } });
  await act(async () => { root.render(<I18nextProvider i18n={i18n}>{element}</I18nextProvider>); });
  return { calls, close: async () => { await act(async () => root.unmount()); host.remove(); } };
}
function button(label: string) { const found = [...document.querySelectorAll("button")].find(item => item.textContent === label); assert.ok(found); return found; }
async function enter(value: string) { const input = document.querySelector('input:not([type="date"])'); assert.ok(input); await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value); input.dispatchEvent(new Event("input", { bubbles: true })); }); }

test("close entry binds server export windows and stable retry key without nested forms", async () => {
  const view = await mount(<BusinessLifecycleEntry spaceId={businesses[0].space_id} />, { commandFailure: Response.json({ detail: { code: "unavailable" } }, { status: 503 }) });
  try {
    assert.equal(getChosenGrant(), businesses[0].grant_id);
    assert.equal(document.querySelectorAll("form form").length, 0);
    assert.equal(document.querySelectorAll('input[type="date"]').length, 0);
    assert.ok(document.querySelector('[data-testid="business-close-dialog"]'), "closing opens the centered dialog");
    assert.ok(document.body.textContent?.includes("Ene – Dic 2025 · 40 registros"), "the count is the server's");
    assert.equal(document.body.textContent?.includes("original"), false);
    await act(async () => button("Continuar sin descargar").click());
    assert.equal(button("Cerrar negocio").disabled, true);
    await enter(businesses[0].name);
    await act(async () => { button("Cerrar negocio").click(); button("Cerrar negocio").click(); });
    await act(async () => button("Cerrar negocio").click());
    const commands = view.calls.filter(call => call.method === "POST");
    assert.equal(commands.length, 2); assert.equal(commands[0].key, commands[1].key);
    assert.ok(commands[0].path.endsWith(`/${businesses[0].space_id}/close`));
    assert.deepEqual(commands[0].body, { confirmation: businesses[0].name });
  } finally { await view.close(); }
});

test("closed listing reopens the selected Business once", async () => {
  const reload = spyOn(window.location, "assign").mockImplementation(() => undefined);
  const view = await mount(<BusinessLifecycleControls />);
  try {
    assert.equal(document.querySelectorAll('a[href*="lifecycle=close"]').length, 2);
    await act(async () => { button("Reabrir negocio").click(); button("Reabrir negocio").click(); });
    const commands = view.calls.filter(call => call.method === "POST"); assert.equal(commands.length, 1); assert.ok(commands[0].path.endsWith(`/${businesses[1].space_id}/reopen`)); assert.equal(reload.mock.calls[0][0], "/biz");
  } finally { reload.mockRestore(); await view.close(); }
});

test.each([
  ["es-419", "business_rnc_registered", "Este RNC ya está registrado en Cuadrao."],
  ["en", "business_rnc_registered", "This RNC is already registered in Cuadrao."],
  ["es-419", "business_reopen_expired", spanish.business.lifecycle.errors.reopen_expired],
  ["en", "unavailable", english.business.lifecycle.errors.reopen_uncertain],
] as const)("a refused reopen keeps the Business closed and shows its error in the card (%s, %s)", async (locale, code, expected) => {
  const space = businesses[1].space_id;
  const copy = locale === "en" ? english : spanish;
  const reference = "reopen-test-0001";
  const reload = spyOn(window.location, "assign").mockImplementation(() => undefined);
  const view = await mount(<BusinessLifecycleControls />, {
    locale, commandFailure: Response.json({ code, request_id: reference }, { status: code === "unavailable" ? 503 : 409 }),
  });
  try {
    const reopen = button(copy.business.lifecycle.reopen.action);
    const card = reopen.closest("article");
    assert.ok(card);
    await act(async () => reopen.click());
    assert.deepEqual(view.calls.filter(call => call.method === "POST").map(call => call.path), [`/api/v1/business/spaces/${space}/reopen`]);
    const alert = card.querySelector('[role="alert"]');
    assert.equal(alert?.querySelector("p")?.textContent, expected);
    assert.equal(alert?.querySelector('[data-testid="error-reference"]')?.getAttribute("title"), reference);
    assert.ok(card.textContent?.includes(copy.business.lifecycle.closed_status));
    assert.equal(reopen.disabled, false);
    assert.equal(reload.mock.calls.length, 0);
  } finally { reload.mockRestore(); await view.close(); }
});

test("the Dueño card offers Transferir only when no other Dueño holds the Business", async () => {
  const view = await mount(<BusinessLifecycleControls />);
  try {
    const [alone, shared] = businesses.map(business => (action: string) => document.querySelectorAll(`a[href*="lifecycle=${action}"][href*="${business.space_id}"]`).length);
    assert.deepEqual([alone("transfer"), alone("close")], [1, 1]);
    assert.deepEqual([shared("transfer"), shared("close")], [0, 1]);
  } finally { await view.close(); }
});

test("readiness denial reveals no names or mutation controls", async () => {
  const view = await mount(<BusinessLifecycleEntry spaceId={businesses[0].space_id} />, { deny: true });
  try { assert.equal(document.body.textContent?.includes(businesses[0].name), false); assert.equal(document.body.textContent?.includes("Cerrar negocio"), false); assert.ok(view.calls.every(call => call.method === "GET")); } finally { await view.close(); }
});


test("close export uses only server windows for the selected Business and resumes without duplicate downloads", async () => {
  const originalCreate = URL.createObjectURL, originalRevoke = URL.revokeObjectURL;
  const saved: string[] = [];
  URL.createObjectURL = () => "blob:synthetic"; URL.revokeObjectURL = () => undefined;
  const save = spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) { saved.push(this.download); });
  const view = await mount(<BusinessLifecycleEntry spaceId={businesses[1].space_id} />, { failExportOnce: true });
  try {
    assert.equal(document.querySelectorAll('input[type="date"]').length, 0);
    await act(async () => { button("Descargar copia").click(); button("Descargar copia").click(); });
    assert.equal(saved.length, 1);
    assert.ok(document.querySelector('[role="alert"]'));
    await act(async () => button("Reintentar").click());
    const exported = view.calls.filter(call => call.path.endsWith("/business/exports"));
    assert.deepEqual(exported.map(call => call.query), ["?start=2024-01-01&end=2024-12-31", "?start=2025-01-01&end=2025-12-31", "?start=2025-01-01&end=2025-12-31"]);
    assert.ok(exported.every(call => call.grant === businesses[1].grant_id && call.method === "GET"));
    assert.deepEqual(saved, ["business-export-2024-01-01-2024-12-31.zip", "business-export-2025-01-01-2025-12-31.zip"]);
    // The same toast as Exportar registros: the same bytes again, never a second request.
    const toast = document.querySelector('[data-testid="toast"]');
    assert.ok(toast?.textContent?.includes("Listo. Revisa tus descargas"));
    await act(async () => button("Descargar de nuevo").click());
    assert.deepEqual(saved.slice(2), ["business-export-2025-01-01-2025-12-31.zip"]);
    assert.equal(view.calls.filter(call => call.path.endsWith("/business/exports")).length, 3);
    assert.equal(document.querySelector('[data-testid="toast"]'), null);
    const downloaded = () => [...document.querySelectorAll('[data-testid="business-close-period"]')].map(row => row.getAttribute("data-status"));
    assert.deepEqual(downloaded(), ["downloaded", "downloaded"]);
    await act(async () => button("Continuar").click());
    await act(async () => button("Cancelar").click());
    assert.deepEqual(downloaded(), ["downloaded", "downloaded"], "returning from confirmation must keep initiated export windows");
    assert.equal([...document.querySelectorAll("button")].some(item => item.textContent === "Descargar copia"), false);
    assert.equal(view.calls.some(call => call.method === "POST"), false);
  } finally { await view.close(); (await import("@/components/business-app/foundation/toasts")).clearToasts(); save.mockRestore(); URL.createObjectURL = originalCreate; URL.revokeObjectURL = originalRevoke; }
});


test("empty export history stays empty and never invents an export request", async () => {
  const windows = businesses[1].export_windows;
  businesses[1].export_windows = [];
  const view = await mount(<BusinessLifecycleEntry spaceId={businesses[1].space_id} />);
  try {
    assert.ok(document.body.textContent?.includes("No hay registros ni comprobantes para descargar."));
    assert.equal([...document.querySelectorAll("button")].some(item => item.textContent === "Descargar copia"), false);
    assert.equal(view.calls.some(call => call.path.endsWith("/business/exports")), false);
    await act(async () => button("Continuar").click());
    assert.ok(document.body.textContent?.includes("Escribe Taller Sol para confirmar."));
  } finally { await view.close(); businesses[1].export_windows = windows; }
});


for (const boundary of ["unmount", "account change"] as const) {
  test(`an export response after ${boundary} cannot start a download`, async () => {
    const originalCreate = URL.createObjectURL, originalRevoke = URL.revokeObjectURL;
    let saved = 0;
    URL.createObjectURL = () => "blob:synthetic"; URL.revokeObjectURL = () => undefined;
    const save = spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => { saved += 1; });
    const view = await mount(<BusinessLifecycleEntry spaceId={businesses[0].space_id} />);
    let release: (response: Response) => void = () => undefined;
    let signal: AbortSignal | null | undefined;
    let closed = false;
    globalThis.fetch = async (_url, init) => { signal = init?.signal; return new Promise<Response>(resolve => { release = resolve; }); };
    try {
      await act(async () => button("Descargar copia").click());
      assert.ok(signal);
      if (boundary === "unmount") { await view.close(); closed = true; assert.equal(signal.aborted, true); }
      else invalidateBrowserAuth();
      await act(async () => release(new Response("synthetic zip")));
      assert.equal(saved, 0);
    } finally { if (!closed) await view.close(); save.mockRestore(); URL.createObjectURL = originalCreate; URL.revokeObjectURL = originalRevoke; }
  });
}
