import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot } from "react-dom/client";
import BusinessTransferDialog, { businessTransferCopyEs, type BusinessTransferView } from "@/components/business-app/BusinessTransferDialog";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

async function mount() {
  const host = document.createElement("div"); document.body.append(host);
  const root = createRoot(host);
  const calls: string[] = [];
  const request: BusinessTransferView = { kind: "request", members: [{ grant_id: "editar-1", name: "Rosa", eligible: true, reason: null }], onRequest: (id, name) => { calls.push(`request:${id}:${name}`); } };
  const render = async (view = request, submitting = false) => {
    await act(async () => root.render(<BusinessTransferDialog businessName="Taller Luna" copy={businessTransferCopyEs} view={view} state={submitting ? { kind: "submitting" } : { kind: "idle" }} onDismiss={() => { calls.push("dismiss"); }} />));
  };
  await render();
  const button = (text: string) => { const found = [...document.querySelectorAll("button")].find((item) => item.textContent === text || item.getAttribute("aria-label") === text); assert.ok(found); return found; };
  const enter = async (selector: string, value: string) => {
    const field = document.querySelector(selector); assert.ok(field instanceof HTMLInputElement || field instanceof HTMLSelectElement);
    await act(async () => { Object.getOwnPropertyDescriptor(field instanceof HTMLInputElement ? HTMLInputElement.prototype : HTMLSelectElement.prototype, "value")!.set!.call(field, value); field.dispatchEvent(new Event(field instanceof HTMLInputElement ? "input" : "change", { bubbles: true })); });
  };
  return { calls, render, button, enter, close: async () => { await act(async () => root.unmount()); host.remove(); } };
}

test("request needs an existing selected member and exact current name; Cancelar only dismisses", async () => {
  const view = await mount();
  try {
    assert.ok(document.body.textContent?.includes("Elige un miembro del negocio. Será dueño cuando acepte."));
    assert.equal(view.button("Solicitar transferencia").disabled, true);
    await act(async () => document.querySelector<HTMLInputElement>('input[type="radio"][value="editar-1"]')!.click());
    await view.enter('input:not([type="radio"])', "Taller Luna ");
    assert.equal(view.button("Solicitar transferencia").disabled, true);
    await view.enter('input:not([type="radio"])', "Taller Luna");
    await act(async () => view.button("Solicitar transferencia").click());
    assert.deepEqual(view.calls, ["request:editar-1:Taller Luna"]);
    await act(async () => view.button("Cancelar").click());
    assert.deepEqual(view.calls, ["request:editar-1:Taller Luna", "dismiss"]);
  } finally { await view.close(); }
});

test("pending withdrawal is a separate explicit action", async () => {
  const view = await mount();
  try {
    await view.render({ kind: "pending", targetName: "Rosa", onWithdraw: () => { view.calls.push("withdraw"); } });
    assert.ok(document.body.textContent?.includes("Esperando que Rosa acepte."));
    assert.equal(document.body.textContent?.includes("Cancelar transferencia"), false);
    await act(async () => view.button("Retirar solicitud").click());
    assert.deepEqual(view.calls, ["withdraw"]);
  } finally { await view.close(); }
});

test("recipient accepts or declines; submission blocks repeated actions", async () => {
  const view = await mount();
  try {
    const recipient: BusinessTransferView = { kind: "recipient", ownerName: "Lucas", onAccept: () => { view.calls.push("accept"); }, onDecline: () => { view.calls.push("decline"); } };
    await view.render(recipient, true);
    assert.ok(document.body.textContent?.includes("Lucas quiere transferirte Taller Luna. Si aceptas, serás su dueño y Lucas podrá seguir editando."));
    assert.equal(view.button("Aceptar transferencia").disabled, true);
    assert.equal(view.button("Rechazar").disabled, true);
    await view.render(recipient);
    await act(async () => view.button("Rechazar").click());
    await act(async () => view.button("Aceptar transferencia").click());
    assert.deepEqual(view.calls, ["decline", "accept"]);
    await view.render({ kind: "declined", targetName: "Rosa" });
    assert.ok(document.body.textContent?.includes("Rosa rechazó la transferencia. Taller Luna sigue siendo tuyo."));
  } finally { await view.close(); }
});

test("empty member list and expired request use the approved text", async () => {
  const view = await mount();
  try {
    await view.render({ kind: "request", members: [], onRequest: () => { view.calls.push("request"); } });
    assert.ok(document.body.textContent?.includes("Para transferir el negocio, primero invita a un miembro."));
    assert.equal(view.button("Solicitar transferencia").disabled, true);
    await view.render({ kind: "expired", targetName: "Rosa" });
    assert.ok(document.body.textContent?.includes("La solicitud a Rosa venció."));
    assert.deepEqual(view.calls, []);
  } finally { await view.close(); }
});


test("transfer candidates show server eligibility and cannot select an ineligible member", async () => {
  const view = await mount();
  try {
    await view.render({ kind: "request", members: [
      { grant_id: "editar-1", name: "Rosa", eligible: true, reason: null },
      { grant_id: "blocked", name: "Sol", eligible: false, reason: "owns_open_business" },
    ], onRequest: () => { view.calls.push("request"); } });
    const blocked = document.querySelector<HTMLInputElement>('input[type="radio"][value="blocked"]');
    assert.ok(blocked);
    assert.equal(blocked.disabled, true);
    assert.ok(document.body.textContent?.includes("Ya es dueño de otro negocio abierto."));
    await act(async () => blocked.click());
    await view.enter('input:not([type="radio"])', "Taller Luna");
    assert.equal(view.button("Solicitar transferencia").disabled, true);
    assert.deepEqual(view.calls, []);
  } finally { await view.close(); }
});
