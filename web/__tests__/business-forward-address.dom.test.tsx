import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

let receiving: string | null = null;
const source = { emailIntake: async () => ({ enabled: true, receiving_address: receiving }) };
let revision = 0;
mock.module("@/components/business-app/BusinessWorkspace", () => ({
  useBusiness: () => ({ source, revision }),
}));
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });
afterEach(() => { receiving = null; revision = 0; });

test("address consumers refresh when the Business changes after activation", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { useForwardAddress } = await import("@/components/business-app/useForwardAddress");
  function Consumer() { return <p>{useForwardAddress() ?? "No address"}</p>; }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  try {
    await act(async () => root.render(<Consumer />));
    assert.equal(host.textContent, "No address");
    receiving = "shared@receipts.example.test";
    revision += 1;
    await act(async () => root.render(<Consumer />));
    assert.equal(host.textContent, receiving);
  } finally {
    await act(async () => root.unmount());
    host.remove();
  }
});
