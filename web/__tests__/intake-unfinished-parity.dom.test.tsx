import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { mountIntakeWorkspace } from "./helpers/intake-workspace";

// A typed note still saving, or whose save is unconfirmed, is as easy to lose on a refresh as a file still uploading.
// Every place the workspace holds the person back for an unfinished upload holds them back for such a note too.
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

test("leaving the page asks first while a typed note is still saving, and not once it is saved", async () => {
  page = await mountIntakeWorkspace(["hold"]);
  await page.openAgregar();
  assert.equal(page.leavingAsks(), false, "nothing is in flight yet");
  await page.writeNote("Compré gasoil por RD$500", "Compra");
  assert.deepEqual(page.rows().map((row) => row.status), ["saving"]);
  assert.equal(page.uploads.length, 0, "no file is uploading");
  assert.equal(page.leavingAsks(), true, "a save in flight would be lost on refresh");
  await page.releaseHeld();
  assert.deepEqual(page.rows().map((row) => row.status), ["saved"]);
  assert.equal(page.leavingAsks(), false, "a saved note needs nothing from this page");
});

test("leaving the page asks first while a typed note is unconfirmed, even with Agregar closed", async () => {
  page = await mountIntakeWorkspace(["lost", "ok"]);
  await page.openAgregar();
  await page.writeNote("Vendí 3 sacos de cemento a RD$1,500", "Venta");
  assert.deepEqual(page.rows().map((row) => row.status), ["uncertain"]);
  await page.closeAgregar();
  assert.equal(page.leavingAsks(), true, "the retained note still needs its retry");
  await page.openAgregar();
  await page.retry();
  await page.settle();
  assert.deepEqual(page.rows().map((row) => row.status), ["saved"]);
  assert.equal(page.leavingAsks(), false);
});

test("a refused typed note does not hold the page: a retry would not change it", async () => {
  page = await mountIntakeWorkspace(["refused"]);
  await page.openAgregar();
  await page.writeNote("Compré gasoil por RD$500", "Compra");
  assert.deepEqual(page.rows().map((row) => row.status), ["refused"]);
  assert.equal(page.leavingAsks(), false);
});

test("Agregar offers the saved receipts for review only once no typed note is still saving or unconfirmed", async () => {
  page = await mountIntakeWorkspace(["lost", "ok"], undefined, ["ok"]);
  await page.openAgregar();
  await page.pickFile("factura.png");
  assert.deepEqual(page.uploadRows(), ["saved"]);
  assert.ok(page.button("Revisar los recibos guardados"), "with every file saved, the review step shows");
  await page.writeNote("Pagué RD$900 de flete", "Compra");
  assert.deepEqual(page.rows().map((row) => row.status), ["uncertain"]);
  assert.equal(page.button("Revisar los recibos guardados"), undefined, "an unconfirmed note keeps the person here, like a failed file");
  await page.retry();
  await page.settle();
  assert.deepEqual(page.rows().map((row) => row.status), ["saved"]);
  assert.ok(page.button("Revisar los recibos guardados"), "once the note is saved, the review step returns");
});
