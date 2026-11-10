import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { clientSpace, mountIntakeWorkspace, ownSpace } from "./helpers/intake-workspace";

// A typed note whose save could not be confirmed outlives Agregar: closing the panel must not drop its text or its
// idempotency key, or reopening and typing it again could save a second draft when the first one did land.
mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
  usePathname: () => "/biz",
}));

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1280, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
let page: Awaited<ReturnType<typeof mountIntakeWorkspace>> | null = null;
afterEach(async () => {
  await page?.unmount();
  page = null;
  (await import("@/components/layout/overlayStack")).resetOverlayStack();
  document.body.innerHTML = "";
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

test("an unconfirmed typed note survives closing Agregar and retries with its original key", async () => {
  page = await mountIntakeWorkspace(["lost", "ok"]);
  await page.openAgregar();
  await page.writeNote("Vendí 3 sacos de cemento a RD$1,500", "Venta");
  assert.deepEqual(page.rows(), [{ status: "uncertain", text: "Vendí 3 sacos de cemento a RD$1,500" }]);
  await page.closeAgregar();
  assert.equal(page.dialog(), null, "Agregar is closed");

  await page.openAgregar();
  assert.deepEqual(page.rows(), [{ status: "uncertain", text: "Vendí 3 sacos de cemento a RD$1,500" }], "reopening shows the same note, still unconfirmed");
  await page.retry();
  await page.settle();
  assert.equal(page.captures.length, 2);
  assert.deepEqual(page.captures[1], page.captures[0], "the retry repeats the original request and key");
  assert.deepEqual(page.captures[0].input, { text: "Vendí 3 sacos de cemento a RD$1,500", document_type: "venta" });
  assert.deepEqual(page.rows(), [{ status: "saved", text: "Vendí 3 sacos de cemento a RD$1,500" }]);

  await page.closeAgregar();
  await page.openAgregar();
  assert.deepEqual(page.rows(), [], "a saved note is finished, so closing forgets it");
});

test("closing Agregar forgets a refused typed note, which a retry would not change", async () => {
  page = await mountIntakeWorkspace(["refused"]);
  await page.openAgregar();
  await page.writeNote("Compré gasoil por RD$500", "Compra");
  assert.deepEqual(page.rows(), [{ status: "refused", text: "Compré gasoil por RD$500" }]);
  await page.closeAgregar();
  await page.openAgregar();
  assert.deepEqual(page.rows(), []);
  assert.equal(page.captures.length, 1);
});

test("an unconfirmed typed note stays with its Business, so a retry never sends it to another one", async () => {
  page = await mountIntakeWorkspace(["lost"], [ownSpace, clientSpace]);
  await page.openAgregar();
  await page.writeNote("Pagué RD$900 de flete", "Compra");
  assert.deepEqual(page.rows(), [{ status: "uncertain", text: "Pagué RD$900 de flete" }]);
  await page.closeAgregar();
  await page.choose("grant-own");
  await page.openAgregar();
  assert.deepEqual(page.rows(), [], "the other Business shows no note to retry");
  await page.closeAgregar();
  await page.choose("grant-admin");
  await page.openAgregar();
  assert.deepEqual(page.rows(), [{ status: "uncertain", text: "Pagué RD$900 de flete" }], "back in its Business, the note waits for its retry");
  assert.equal(page.captures.length, 1);
  await page.retry();
  await page.settle();
  assert.deepEqual(page.captures.map((capture) => capture.grant), ["grant-admin", "grant-admin"], "both attempts name the Business the note was typed in");
});

test("a file picked in Agregar is handed to the upload with the Business Agregar is open in", async () => {
  page = await mountIntakeWorkspace([], [ownSpace, clientSpace]);
  await page.openAgregar();
  await page.pickFile("factura.png");
  assert.deepEqual(page.uploads.map((upload) => upload.grant), ["grant-admin"]);
});
