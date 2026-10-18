import assert from "node:assert/strict";
import { afterAll, beforeAll, test, spyOn } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot } from "react-dom/client";
import BusinessTransferEntry from "@/components/business-app/BusinessTransferEntry";
import { getChosenGrant, setChosenGrant } from "@/lib/business-grant";

const originalFetch = globalThis.fetch;
const originalAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
const id = "4100626b-f480-4249-97bd-04bdc03f1a15";
const transfer = { id, space_id: "39d12d09-bebe-4992-b6dc-cb1a84d52438", status: "pending", expires_at: "2026-10-26T01:05:00+00:00", business_name: "Colmado Rosa", owner_name: "Ana", target_name: "Rosa", role: "target", grant_id: "af2d018e-6e6c-4fc7-9602-9b0b31ff9bc0" };
beforeAll(() => { GlobalRegistrator.register({ url: `https://app.example.test/biz?transfer=${id}` }); (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; process.env.NEXT_PUBLIC_MOCK_AUTH = "true"; });
afterAll(async () => { globalThis.fetch = originalFetch; if (originalAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = originalAuth; await GlobalRegistrator.unregister(); });

async function mount(role: "owner" | "target" | "nonmember", status = "pending") {
  const calls: { path: string; method: string }[] = [];
  globalThis.fetch = async (url, init) => {
    const path = new URL(String(url)).pathname;
    const method = init?.method ?? "GET";
    calls.push({ path, method });
    return Response.json(method === "GET" ? { transfers: role === "nonmember" ? [] : [{ ...transfer, role, status }] } : { id, space_id: transfer.space_id, status: "accepted" });
  };
  const host = document.createElement("div"); document.body.append(host);
  const root = createRoot(host);
  await act(async () => { root.render(<BusinessTransferEntry transferId={id} />); });
  return { calls, close: async () => { await act(async () => root.unmount()); host.remove(); } };
}

test("email link loads recipient choices without accepting on GET, then explicit accept uses the saved ID", async () => {
  const reload = spyOn(window.location, "assign").mockImplementation(() => undefined);
  const view = await mount("target");
  try {
    assert.ok(document.body.textContent?.includes("Ana quiere transferirte Colmado Rosa."));
    assert.equal(getChosenGrant(), transfer.grant_id);
    assert.deepEqual(view.calls, [{ path: "/api/v1/business/ownership-transfers", method: "GET" }]);
    const accept = [...document.querySelectorAll("button")].find(button => button.textContent === "Aceptar transferencia"); assert.ok(accept);
    await act(async () => { accept.click(); accept.click(); });
    assert.equal(view.calls.filter(call => call.method === "POST").length, 1);
    assert.equal(view.calls[1].path, `/api/v1/business/ownership-transfers/${id}/accept`);
    assert.equal(reload.mock.calls[0][0], `/biz?transfer=${id}`);
  } finally { reload.mockRestore(); await view.close(); }
});

test("owner link shows withdrawal, and a nonmember link exposes no transfer details or actions", async () => {
  const owner = await mount("owner");
  try {
    assert.ok(document.body.textContent?.includes("Esperando que Rosa acepte."));
    assert.ok(document.body.textContent?.includes("Retirar solicitud"));
    assert.equal(document.body.textContent?.includes("Aceptar transferencia"), false);
  } finally { await owner.close(); }
  const outsider = await mount("nonmember");
  try {
    assert.equal(document.body.textContent?.includes("Colmado Rosa"), false);
    assert.equal(document.body.textContent?.includes("Aceptar transferencia"), false);
    assert.equal(document.body.textContent?.includes("Retirar solicitud"), false);
    assert.ok(outsider.calls.every(call => call.method === "GET"));
  } finally { await outsider.close(); }
});

test("accepted-target email selects the named Business even when another grant was selected, using only GET", async () => {
  setChosenGrant("cd7f3c3a-05c5-41de-b920-a8fe34d19d64");
  const view = await mount("target", "accepted");
  try {
    assert.equal(getChosenGrant(), transfer.grant_id);
    assert.ok(document.body.textContent?.includes("Transferencia completada"));
    assert.equal(document.body.textContent?.includes("Aceptar transferencia"), false);
    assert.ok(view.calls.every(call => call.method === "GET"));
  } finally { setChosenGrant(null); await view.close(); }
});
