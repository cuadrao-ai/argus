import assert from "node:assert/strict";
import { afterAll, beforeAll, test, spyOn } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot } from "react-dom/client";
import BusinessLifecycleEntry from "@/components/business-app/BusinessLifecycleEntry";
import BusinessLifecycleControls from "@/components/business-app/BusinessLifecycleControls";
import { getBusinessSpaces } from "@/lib/business-api";
import ProfileDeleteRequestDialog from "@/components/sidebar/ProfileDeleteRequestDialog";
import { getChosenGrant, setChosenGrant } from "@/lib/business-grant";

const originalFetch = globalThis.fetch;
const originalAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
const businesses = [
  { space_id: "39d12d09-bebe-4992-b6dc-cb1a84d52438", name: "Colmado Rosa", grant_id: "af2d018e-6e6c-4fc7-9602-9b0b31ff9bc0", role: "owner", members: [{ grant_id: "4100626b-f480-4249-97bd-04bdc03f1a15", name: "Rosa" }] },
  { space_id: "49767c9c-9f8a-4af7-82e3-bcc065e09a19", name: "Taller Sol", grant_id: "b3acd38c-2e99-49aa-888f-4ee3a6268066", role: "owner", members: [] },
];
beforeAll(() => { GlobalRegistrator.register({ url: "https://app.example.test/biz" }); (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; process.env.NEXT_PUBLIC_MOCK_AUTH = "true"; });
afterAll(async () => { globalThis.fetch = originalFetch; setChosenGrant(null); if (originalAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = originalAuth; await GlobalRegistrator.unregister(); });

async function mount(element: React.ReactNode, failCommand = false, deny = false) {
  const calls: { path: string; method: string; key: string | null; grant: string | null; query: string; body?: unknown }[] = [];
  globalThis.fetch = async (url, init) => {
    const path = new URL(String(url)).pathname; const method = init?.method ?? "GET";
    calls.push({ path, method, key: new Headers(init?.headers).get("Idempotency-Key"), grant: new Headers(init?.headers).get("X-Business-Grant"), query: new URL(String(url)).search, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    if (deny) return Response.json({ detail: { code: "business_unavailable" } }, { status: 404 });
    if (method === "POST") return failCommand ? Response.json({ detail: { code: "unavailable" } }, { status: 503 }) : Response.json({ space_id: businesses[0].space_id, name: businesses[0].name, closed_at: "2026-10-18T05:00:00Z", reopen_until: "2026-11-17T05:00:00Z" });
    if (path.endsWith("/ownership-transfers")) return Response.json({ transfers: [] });
    if (path.endsWith("/closed-spaces")) return Response.json({ spaces: [{ space_id: businesses[1].space_id, name: businesses[1].name, closed_at: "2026-10-18T05:00:00Z", reopen_until: "2026-11-17T05:00:00Z" }] });
    return Response.json({ spaces: businesses });
  };
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  await act(async () => { root.render(element); });
  return { calls, close: async () => { await act(async () => root.unmount()); host.remove(); } };
}
function button(label: string) { const found = [...document.querySelectorAll("button")].find(item => item.textContent === label); assert.ok(found); return found; }
async function enter(value: string) { const input = document.querySelector('input:not([type="date"])'); assert.ok(input); await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value); input.dispatchEvent(new Event("input", { bubbles: true })); }); }

test("actual deletion dialog discovers each owned Business and blocks deletion with distinct action links", async () => {
  let submitted = 0;
  const view = await mount(<ProfileDeleteRequestDialog discoverBusinesses={getBusinessSpaces} state="idle" supportMailto="mailto:support@example.test" onClose={() => undefined} onSubmit={() => { submitted++; }} />);
  try {
    for (const business of businesses) {
      assert.ok(document.body.textContent?.includes(`Eres el único dueño de ${business.name}. Transfiérelo o ciérralo antes de borrar tu cuenta.`));
      for (const action of ["transfer", "close"]) assert.ok(document.querySelector(`a[href="/biz?lifecycle=${action}&business=${business.space_id}"]`));
    }
    const submit = [...document.querySelectorAll("button")].find(item => item.textContent === "Delete account" || item.textContent === "settings.profile.request_deletion.confirm"); assert.ok(submit?.disabled);
    await act(async () => submit.click()); assert.equal(submitted, 0);
  } finally { await view.close(); }
});

test("close entry binds target, existing explicit-date export and stable retry key without nested forms", async () => {
  const view = await mount(<BusinessLifecycleEntry spaceId={businesses[0].space_id} action="close" />, true);
  try {
    assert.equal(getChosenGrant(), businesses[0].grant_id);
    assert.equal(document.querySelectorAll("form form").length, 0);
    assert.equal(document.querySelectorAll('input[type="date"]').length, 2);
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

test("transfer entry preserves approved empty-target copy and GET has no effects", async () => {
  const view = await mount(<BusinessLifecycleEntry spaceId={businesses[1].space_id} action="transfer" />);
  try { assert.ok(document.body.textContent?.includes("Para transferir el negocio, primero invita a un miembro.")); assert.equal(button("Solicitar transferencia").disabled, true); assert.ok(view.calls.every(call => call.method === "GET")); } finally { await view.close(); }
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

test("readiness denial reveals no names or mutation controls", async () => {
  const view = await mount(<BusinessLifecycleEntry spaceId={businesses[0].space_id} action="close" />, false, true);
  try { assert.equal(document.body.textContent?.includes(businesses[0].name), false); assert.equal(document.body.textContent?.includes("Cerrar negocio"), false); assert.ok(view.calls.every(call => call.method === "GET")); } finally { await view.close(); }
});


test("close export selects the second owned Business and preserves the existing dated API", async () => {
  const originalCreate = URL.createObjectURL, originalRevoke = URL.revokeObjectURL;
  URL.createObjectURL = () => "blob:synthetic"; URL.revokeObjectURL = () => undefined;
  const view = await mount(<BusinessLifecycleEntry spaceId={businesses[1].space_id} action="close" />);
  try {
    const dates = [...document.querySelectorAll('input[type="date"]')];
    for (const [index, value] of ["2026-10-01", "2026-10-18"].entries()) await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(dates[index], value);
      dates[index].dispatchEvent(new Event("input", { bubbles: true }));
      dates[index].dispatchEvent(new Event("change", { bubbles: true }));
    });
    await act(async () => button("Download CSV, Excel and originals").click());
    const exported = view.calls.find(call => call.path.endsWith("/business/exports")); assert.ok(exported);
    assert.equal(exported.grant, businesses[1].grant_id);
    assert.equal(exported.query, "?start=2026-10-01&end=2026-10-18");
    assert.equal(exported.method, "GET");
  } finally { await view.close(); URL.createObjectURL = originalCreate; URL.revokeObjectURL = originalRevoke; }
});
