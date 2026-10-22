import assert from "node:assert/strict";
import { afterAll, beforeAll, spyOn, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot } from "react-dom/client";
import BusinessApp from "@/components/business-app/BusinessApp";
import { setChosenGrant } from "@/lib/business-grant";

const spaceId = "39d12d09-bebe-4992-b6dc-cb1a84d52438";
const originalFetch = globalThis.fetch;
const originalAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;

beforeAll(() => {
  GlobalRegistrator.register({ url: "https://app.example.test/biz" });
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
});

afterAll(async () => {
  globalThis.fetch = originalFetch;
  setChosenGrant(null);
  if (originalAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  else process.env.NEXT_PUBLIC_MOCK_AUTH = originalAuth;
  await GlobalRegistrator.unregister();
});

for (const action of ["close", "transfer"] as const) {
  for (const denied of [false, true]) {
    test(`cancel routed ${action} navigates to Business without a blank page${denied ? " when readiness is denied" : ""}`, async () => {
      window.history.replaceState(null, "", `/biz?lifecycle=${action}&business=${spaceId}`);
      const methods: string[] = [];
      globalThis.fetch = async (url, init) => {
        methods.push(init?.method ?? "GET");
        if (denied) return Response.json({ detail: { code: "business_unavailable" } }, { status: 404 });
        if (String(url).includes("ownership-transfers")) return Response.json({ transfers: [] });
        return Response.json({ spaces: [{
          space_id: spaceId,
          name: "Colmado Rosa",
          grant_id: "af2d018e-6e6c-4fc7-9602-9b0b31ff9bc0",
          member_count: 0, reopen_until: "2026-11-20T17:45:00Z", export_windows: [], members: [],
        }] });
      };
      const navigate = spyOn(window.location, "assign").mockImplementation(() => undefined);
      const host = document.createElement("div");
      document.body.append(host);
      const root = createRoot(host);
      try {
        await act(async () => root.render(<BusinessApp lifecycle={{ spaceId, action }} />));
        const cancel = [...document.querySelectorAll("button")].find(button => button.textContent === "Cancelar" || button.getAttribute("aria-label") === "Cancelar");
        assert.ok(cancel);
        await act(async () => cancel.click());
        assert.notEqual(document.body.textContent?.trim(), "", "cancel leaves the entire Business page empty");
        assert.deepEqual(navigate.mock.calls.map(call => call[0]), ["/biz"]);
        assert.ok(methods.length > 0);
        assert.ok(methods.every(method => method === "GET"));
      } finally {
        await act(async () => root.unmount());
        host.remove();
        navigate.mockRestore();
      }
    });
  }
}
