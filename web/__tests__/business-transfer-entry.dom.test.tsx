import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test, spyOn } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import spanish from "@/public/locales/es-419/common.json";
import { createRoot } from "react-dom/client";
import BusinessTransferEntry from "@/components/business-app/BusinessTransferEntry";
import { BusinessContext } from "@/components/business-app/business-context";
import { ToastViewport } from "@/components/business-app/foundation/ToastViewport";
import { clearToasts } from "@/components/business-app/foundation/toasts";

const SWITCH = "NEXT_PUBLIC_CUADRAO_BUSINESS_LIFECYCLE_CONTROLS_ENABLED";
const originalFetch = globalThis.fetch;
const originalAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
const originalSwitch = process.env[SWITCH];
const id = "4100626b-f480-4249-97bd-04bdc03f1a15";
const space = "39d12d09-bebe-4992-b6dc-cb1a84d52438";
const grant = "af2d018e-6e6c-4fc7-9602-9b0b31ff9bc0";
const rosaGrant = "5200626b-f480-4249-97bd-04bdc03f1a15";
const transfer = { id, space_id: space, status: "pending", expires_at: "2026-12-04T17:45:00+00:00", business_name: "Colmado Rosa", owner_name: "Ana", owner_shown_as: "name", target_name: "Rosa", target_shown_as: "name", role: "target", grant_id: grant };
const owned = { space_id: space, name: "Colmado Rosa", grant_id: grant, member_count: 1, reopen_until: "2026-12-20T17:45:00Z", export_windows: [], members: [{ grant_id: rosaGrant, name: "Rosa", shown_as: "name", eligible: true, reason: null }] };
const ANSWER = { accept: "accepted", decline: "declined", withdraw: "cancelled" } as const;

beforeAll(() => { GlobalRegistrator.register({ url: `https://app.example.test/biz?transfer=${id}` }); (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; process.env.NEXT_PUBLIC_MOCK_AUTH = "true"; process.env[SWITCH] = "true"; });
afterEach(() => { clearToasts(); process.env[SWITCH] = "true"; });
afterAll(async () => {
  globalThis.fetch = originalFetch;
  if (originalAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = originalAuth;
  if (originalSwitch === undefined) delete process.env[SWITCH]; else process.env[SWITCH] = originalSwitch;
  await GlobalRegistrator.unregister();
});

type Server = { role?: "owner" | "target" | "nonmember"; status?: string; uncertain?: boolean; failReads?: number; owns?: boolean; requested?: boolean; hold?: Promise<void> };

async function mount(target: { transferId?: string; startSpaceId?: string }, server: Server = {}) {
  window.history.replaceState(null, "", target.startSpaceId ? `/biz?lifecycle=transfer&business=${target.startSpaceId}` : `/biz?transfer=${target.transferId}`);
  const role = server.role ?? "target";
  let status = server.status ?? "pending";
  let listed = !target.startSpaceId || Boolean(server.requested);
  let failReads = server.failReads ?? 0;
  const calls: { path: string; method: string; key: string | null; body?: unknown }[] = [];
  globalThis.fetch = async (url, init) => {
    const path = new URL(String(url)).pathname.replace("/api/v1/business", "");
    const method = init?.method ?? "GET";
    calls.push({ path, method, key: new Headers(init?.headers).get("Idempotency-Key"), body: init?.body ? JSON.parse(String(init.body)) : undefined });
    if (method === "POST") {
      if (path.endsWith("/ownership-transfers")) listed = true;
      else status = ANSWER[path.split("/").pop() as keyof typeof ANSWER];
      return server.uncertain ? Response.json({ code: "unavailable" }, { status: 503 }) : Response.json({ id, space_id: space, status });
    }
    if (server.hold) await server.hold;
    if (failReads > 0) { failReads -= 1; return Response.json({ code: "unavailable" }, { status: 500 }); }
    if (path === "/owned-spaces") return Response.json({ spaces: server.owns === false ? [] : [owned] });
    return Response.json({ transfers: role === "nonmember" || !listed ? [] : [{ ...transfer, role: target.startSpaceId ? "owner" : role, status }] });
  };
  const workspace: string[] = [];
  const context = { chosen: null, chooseBusiness: (grantId: string | null) => { workspace.push(`choose:${grantId}`); }, reload: () => { workspace.push("reload"); }, openPanel: (panel: { kind: string; tab?: string }) => { workspace.push(`open:${panel.kind}:${panel.tab}`); } } as never;
  const host = document.createElement("div"); document.body.append(host);
  const root = createRoot(host);
  const i18n = i18next.createInstance(); await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  await act(async () => { root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}><BusinessTransferEntry {...target} /><ToastViewport /></BusinessContext.Provider></I18nextProvider>); });
  for (let turn = 0; turn < 50 && document.querySelector('[data-view="loading"]'); turn += 1) await act(async () => new Promise(resolve => setTimeout(resolve, 2)));
  const settle = async () => { for (let turn = 0; turn < 10; turn += 1) await act(async () => new Promise(resolve => setTimeout(resolve, 2))); };
  const press = async (label: string, times = 1) => {
    const found = [...document.querySelectorAll("button")].find(item => item.textContent === label); assert.ok(found, `button ${label}`);
    await act(async () => { for (let turn = 0; turn < times; turn += 1) found.click(); });
    await settle();
  };
  return {
    calls, workspace, press,
    posts: () => calls.filter(call => call.method === "POST"),
    dialog: () => document.querySelector('[role="dialog"]'),
    labels: () => [...document.querySelectorAll('[role="dialog"] button')].map(item => item.textContent).filter(Boolean),
    toast: () => document.querySelector('[data-testid="toast"]')?.textContent ?? null,
    close: async () => { await act(async () => root.unmount()); host.remove(); },
  };
}

test("the email link opens one question; accepting once enters the Business with its toast", async () => {
  const reload = spyOn(window.location, "assign").mockImplementation(() => undefined);
  const view = await mount({ transferId: id });
  try {
    assert.equal(document.querySelectorAll('[role="dialog"]').length, 1);
    assert.equal(document.querySelector('[role="alertdialog"]'), null);
    assert.equal(document.querySelector('[data-testid="side-drawer"]'), null);
    assert.equal(view.dialog()?.querySelector("h2")?.textContent, "¿Aceptar Colmado Rosa?");
    assert.ok(view.dialog()?.textContent?.includes("Ana podrá seguir editando."));
    assert.deepEqual(view.calls.map(call => `${call.method} ${call.path}`), ["GET /ownership-transfers"]);
    assert.deepEqual(view.workspace, [], "opening the link moves nothing");
    await view.press("Aceptar transferencia", 2);
    assert.deepEqual(view.posts().map(call => call.path), [`/ownership-transfers/${id}/accept`], "one answer, sent once");
    assert.deepEqual(view.workspace, [`choose:${grant}`, "reload"], "the app enters the Business");
    assert.ok(view.toast()?.includes("Transferencia completada"));
    assert.equal(view.dialog(), null);
    assert.equal(new URL(window.location.href).searchParams.has("transfer"), false);
    assert.equal(reload.mock.calls.length, 0, "no page reload");
  } finally { reload.mockRestore(); await view.close(); }
});

test("declining shows its toast and leaves the person where they were", async () => {
  const view = await mount({ transferId: id });
  try {
    await view.press("Rechazar");
    assert.deepEqual(view.posts().map(call => call.path), [`/ownership-transfers/${id}/decline`]);
    assert.ok(view.toast()?.includes("Transferencia rechazada"));
    assert.equal(view.dialog(), null);
    assert.deepEqual(view.workspace, []);
  } finally { await view.close(); }
});

test("the owner's pending request opens in the same dialog; withdrawing shows the toast and closes it", async () => {
  const view = await mount({ transferId: id }, { role: "owner" });
  try {
    assert.equal(view.dialog()?.querySelector("h2")?.textContent, "Transferir este negocio");
    assert.ok(view.dialog()?.textContent?.includes("Esperando que Rosa acepte."));
    assert.ok(view.dialog()?.textContent?.includes("Vence 4 de diciembre de 2026"));
    assert.deepEqual(view.labels(), ["Retirar solicitud"]);
    await view.press("Retirar solicitud", 2);
    assert.deepEqual(view.posts().map(call => call.path), [`/ownership-transfers/${id}/withdraw`]);
    assert.ok(view.toast()?.includes("Transferencia retirada"));
    assert.equal(view.dialog(), null);
  } finally { await view.close(); }
});

for (const action of ["accept", "decline", "withdraw"] as const) {
  test(`${action} not confirmed: its sentence stays in the dialog with Actualizar, which reads the server and never answers twice`, async () => {
    const view = await mount({ transferId: id }, { role: action === "withdraw" ? "owner" : "target", uncertain: true });
    try {
      await view.press(action === "accept" ? "Aceptar transferencia" : action === "decline" ? "Rechazar" : "Retirar solicitud");
      assert.equal(view.posts().length, 1);
      assert.equal(document.querySelectorAll('[role="dialog"]').length, 1);
      assert.equal(view.dialog()?.querySelector('[role="alert"] p')?.textContent, spanish.business.lifecycle.errors[`${action}_uncertain`]);
      assert.deepEqual(view.labels(), ["Actualizar"]);
      assert.equal(view.toast(), null);
      await view.press("Actualizar");
      assert.equal(view.posts().length, 1);
      assert.equal(view.calls.filter(call => call.method === "GET").length, 2);
      // The server says the answer landed, so the dialog ends as it would have.
      assert.ok(view.toast()?.includes(action === "accept" ? "Transferencia completada" : action === "decline" ? "Transferencia rechazada" : "Transferencia retirada"));
      assert.equal(view.dialog(), null);
      assert.deepEqual(view.workspace.filter(step => step.startsWith("choose")), action === "accept" ? [`choose:${grant}`] : action === "withdraw" ? [`choose:${grant}`] : []);
    } finally { await view.close(); }
  });
}

const LINK_STATES: [string, Server, string, string[]][] = [
  ["a link that is not the person's", { role: "nonmember" }, "Esta transferencia no está disponible con tu acceso actual.", []],
  ["a withdrawn request, to its recipient", { status: "cancelled" }, "Esta transferencia no está disponible con tu acceso actual.", []],
  ["an expired request, to its recipient", { status: "expired" }, "Esta solicitud venció.", []],
  ["a declined request, to its recipient", { status: "declined" }, "Transferencia rechazada", []],
  ["an accepted request, to its recipient", { status: "accepted" }, "Transferencia completada", []],
  ["a declined request, to the owner", { role: "owner", status: "declined" }, "Rosa rechazó la transferencia. Colmado Rosa sigue siendo tuyo.", []],
  ["an expired request, to the owner", { role: "owner", status: "expired" }, "La solicitud a Rosa venció.", []],
  ["an accepted request, to the former owner", { role: "owner", status: "accepted" }, "Transferencia completada", []],
  ["a withdrawn request, to the owner", { role: "owner", status: "cancelled" }, "Transferencia retirada", []],
];
for (const [name, server, words, actions] of LINK_STATES) {
  test(`${name}: the same dialog, existing words, no answer sent`, async () => {
    const view = await mount({ transferId: id }, server);
    try {
      assert.equal(document.querySelectorAll('[role="dialog"]').length, 1);
      assert.equal(document.querySelector('[data-testid="side-drawer"]'), null);
      assert.equal(view.dialog()?.querySelector("h2")?.textContent, "Transferir este negocio");
      assert.equal(view.dialog()?.querySelector('[data-testid="business-transfer"] p')?.textContent, words);
      assert.deepEqual(view.labels(), actions);
      assert.ok(view.calls.every(call => call.method === "GET"));
      if (server.role === "nonmember") assert.equal(document.body.textContent?.includes("Colmado Rosa"), false);
    } finally { await view.close(); }
  });
}

test("a link that did not load says so with Reintentar, which reads it again", async () => {
  const view = await mount({ transferId: id }, { failReads: 1 });
  try {
    assert.equal(view.dialog()?.querySelector('[role="alert"]')?.textContent, "No pudimos cargar la transferencia. Intenta otra vez.");
    assert.deepEqual(view.labels(), ["Reintentar"]);
    await view.press("Reintentar");
    assert.equal(view.dialog()?.querySelector("h2")?.textContent, "¿Aceptar Colmado Rosa?");
    assert.equal(view.calls.length, 2);
  } finally { await view.close(); }
});

test("with the lifecycle switch off the transfer link draws nothing and asks the server nothing", async () => {
  process.env[SWITCH] = "false";
  const linked = await mount({ transferId: id });
  try {
    assert.equal(linked.dialog(), null);
    assert.equal(document.body.textContent, "");
    assert.deepEqual(linked.calls, []);
  } finally { await linked.close(); }
  delete process.env[SWITCH];
  const started = await mount({ startSpaceId: space });
  try {
    assert.equal(started.dialog(), null);
    assert.deepEqual(started.calls, []);
    assert.deepEqual(started.workspace, []);
  } finally { await started.close(); }
});

test("the owner starts over Negocio; Solicitar sends once and the same dialog turns to Pendiente", async () => {
  const reload = spyOn(window.location, "assign").mockImplementation(() => undefined);
  const view = await mount({ startSpaceId: space });
  try {
    assert.deepEqual(view.workspace, [`choose:${grant}`, "open:business:datos"], "the Negocio page of that Business is behind the dialog");
    assert.ok(view.calls.every(call => call.method === "GET"));
    const dialog = view.dialog();
    assert.ok(dialog?.textContent?.includes("Escribe Colmado Rosa para confirmar."));
    await act(async () => document.querySelector<HTMLInputElement>('input[type="radio"]')!.click());
    const field = document.querySelector<HTMLInputElement>('input:not([type="radio"])')!;
    await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(field, "Colmado Rosa"); field.dispatchEvent(new Event("input", { bubbles: true })); });
    await view.press("Solicitar transferencia", 2);
    assert.equal(view.posts().length, 1);
    assert.equal(view.posts()[0].path, `/spaces/${space}/ownership-transfers`);
    assert.deepEqual(view.posts()[0].body, { target_grant_id: rosaGrant, confirmation: "Colmado Rosa" });
    assert.ok(view.posts()[0].key);
    assert.equal(document.querySelector('[role="alertdialog"]'), null);
    assert.equal(view.dialog(), dialog, "the dialog that asked is the one that now waits");
    assert.ok(dialog?.textContent?.includes("Esperando que Rosa acepte."));
    assert.deepEqual(view.labels(), ["Retirar solicitud"]);
    assert.equal(reload.mock.calls.length, 0, "no page reload");
    await view.press("Retirar solicitud");
    assert.ok(view.toast()?.includes("Transferencia retirada"));
    assert.equal(view.dialog(), null);
    assert.equal(window.location.search, "", "closing leaves no transfer address behind");
  } finally { reload.mockRestore(); await view.close(); }
});

test("a request that was not confirmed stays in the dialog and retries with the same key", async () => {
  const view = await mount({ startSpaceId: space }, { uncertain: true });
  try {
    await act(async () => document.querySelector<HTMLInputElement>('input[type="radio"]')!.click());
    const field = document.querySelector<HTMLInputElement>('input:not([type="radio"])')!;
    await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(field, "Colmado Rosa"); field.dispatchEvent(new Event("input", { bubbles: true })); });
    await view.press("Solicitar transferencia");
    assert.equal(view.dialog()?.querySelector('[role="alert"] p')?.textContent, "No pudimos confirmar la solicitud. Tu selección sigue aquí. Reintenta para comprobar el resultado.");
    assert.equal(document.querySelector<HTMLInputElement>('input[type="radio"]')!.checked, true);
    await view.press("Solicitar transferencia");
    assert.equal(view.posts().length, 2);
    assert.equal(view.posts()[0].key, view.posts()[1].key);
  } finally { await view.close(); }
});

test("starting while a request is pending opens that request; a Business that is not the person's shows nothing of it", async () => {
  const pending = await mount({ startSpaceId: space }, { requested: true });
  try {
    assert.ok(pending.dialog()?.textContent?.includes("Esperando que Rosa acepte."));
    assert.deepEqual(pending.labels(), ["Retirar solicitud"]);
    assert.deepEqual(pending.workspace, [`choose:${grant}`, "open:business:datos"], "Negocio is behind it too");
  } finally { await pending.close(); }
  const outsider = await mount({ startSpaceId: space }, { owns: false });
  try {
    assert.equal(outsider.dialog()?.querySelector('[role="alert"]')?.textContent, "Este negocio no está disponible con tu acceso actual.");
    assert.equal(document.body.textContent?.includes("Colmado Rosa"), false);
    assert.deepEqual(outsider.labels(), []);
  } finally { await outsider.close(); }
});

test("closing the owner's dialog while it loads ignores the late answer: no Business switch, no panel", async () => {
  let release = () => {};
  const hold = new Promise<void>(resolve => { release = resolve; });
  const view = await mount({ startSpaceId: space }, { hold });
  try {
    assert.ok(document.querySelector('[data-view="loading"]'), "still loading");
    const x = view.dialog()?.querySelector<HTMLButtonElement>("button[aria-label]");
    assert.ok(x, "the dialog's close button");
    await act(async () => x!.click());
    await act(async () => { release(); });
    for (let turn = 0; turn < 10; turn += 1) await act(async () => new Promise(resolve => setTimeout(resolve, 2)));
    assert.deepEqual(view.workspace, [], "the late answer changes nothing the person sees");
    assert.equal(view.dialog(), null);
  } finally { release(); await view.close(); }
});
