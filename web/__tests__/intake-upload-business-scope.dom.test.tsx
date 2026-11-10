import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { clientSpace, mountIntakeWorkspace, ownSpace } from "./helpers/intake-workspace";

// The upload queue outlives Agregar and holds every Business's files. An action taken in one Business (reviewing
// what it saved, closing Agregar, picking a file) must leave another Business's files and their upload keys alone,
// or a failed upload can no longer be retried once the person returns to the Business it was picked in.
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

const A = clientSpace.grant_id;
const B = ownSpace.grant_id;

test("reviewing what one Business saved keeps another Business's failed upload, which still retries with its key", async () => {
  page = await mountIntakeWorkspace([], [ownSpace, clientSpace], ["lost", "ok", "ok"]);
  await page.openAgregar();
  await page.pickFile("factura.png");
  assert.deepEqual(page.uploadRows(), ["failed"], "A's upload failed");
  await page.closeAgregar();

  await page.choose(B);
  await page.openAgregar();
  await page.pickFile("venta.png");
  assert.deepEqual(page.uploadRows(), ["saved"], "B lists only its own, saved upload");
  await page.reviewSaved();
  await page.settle();
  assert.equal(page.dialog(), null, "reviewing closes Agregar");
  await page.openAgregar();
  assert.deepEqual(page.uploadRows(), [], "B's reviewed upload is forgotten");
  await page.closeAgregar();

  await page.choose(A);
  await page.openAgregar();
  assert.deepEqual(page.uploadRows(), ["failed"], "back in A, the failed upload still waits for its retry");
  await page.retryFile("factura.png");
  assert.deepEqual(page.uploads, [{ key: page.uploads[0].key, grant: A }, { key: page.uploads[1].key, grant: B }, { key: page.uploads[0].key, grant: A }], "the retry repeats A's original key, to A");
  assert.deepEqual(page.uploadRows(), ["saved"]);
});

test("closing Agregar in one Business forgets only that Business's finished uploads", async () => {
  page = await mountIntakeWorkspace([], [ownSpace, clientSpace], ["ok", "ok"]);
  await page.openAgregar();
  await page.pickFile("factura.png");
  assert.deepEqual(page.uploadRows(), ["saved"]);

  await page.choose(B);
  assert.deepEqual(page.uploadRows(), [], "B sees none of A's uploads");
  await page.pickFile("venta.png");
  assert.deepEqual(page.uploadRows(), ["saved"]);
  await page.closeAgregar();
  await page.openAgregar();
  assert.deepEqual(page.uploadRows(), [], "closing forgot B's finished upload");
  await page.closeAgregar();

  await page.choose(A);
  await page.openAgregar();
  assert.deepEqual(page.uploadRows(), ["saved"], "A's saved upload is still listed");
  assert.ok(page.button("Revisar los recibos guardados"), "A can still review it");
});

test("the same file picked in two Businesses uploads to each; one Business's copy never hides the other's", async () => {
  page = await mountIntakeWorkspace([], [ownSpace, clientSpace], ["lost", "ok"]);
  await page.openAgregar();
  await page.pickFile("recibo.png", 1_700_000_000_000);
  assert.deepEqual(page.uploadRows(), ["failed"]);
  await page.closeAgregar();

  await page.choose(B);
  await page.openAgregar();
  await page.pickFile("recibo.png", 1_700_000_000_000);
  assert.deepEqual(page.uploads.map((upload) => upload.grant), [A, B], "B's copy is uploaded to B");
  assert.deepEqual(page.uploadRows(), ["saved"]);
});

test("closing Agregar in a Business forgets the typed notes that Business finished", async () => {
  page = await mountIntakeWorkspace(["ok"], [ownSpace, clientSpace]);
  await page.openAgregar();
  await page.writeNote("Pagué RD$900 de flete", "Compra");
  assert.deepEqual(page.rows(), [{ status: "saved", text: "Pagué RD$900 de flete" }]);
  await page.closeAgregar();
  await page.openAgregar();
  assert.deepEqual(page.rows(), [], "the saved note is finished, so closing forgot it");
  assert.deepEqual(page.captures.map((capture) => capture.grant), [A]);
});

test("opening the composer in one Business starts it clean without touching another Business's unfinished composer file", async () => {
  page = await mountIntakeWorkspace([], [ownSpace, clientSpace], ["ok", "lost"]);
  await page.choose(B);
  await page.openComposer();
  await page.pickFile("adjunto.png");
  assert.equal(page.composer(), null, "a saved composer file attaches and closes the composer");

  await page.choose(A);
  await page.openComposer();
  await page.pickFile("factura.png");
  assert.deepEqual(page.uploadRows(), ["failed"], "A's composer upload failed");
  await page.closeComposer();

  await page.choose(B);
  await page.openComposer();
  assert.deepEqual(page.uploadRows(), [], "B's composer starts clean");
  await page.closeComposer();

  await page.choose(A);
  await page.openComposer();
  assert.deepEqual(page.uploadRows(), ["failed"], "A's failed composer file still waits for its retry");
  assert.deepEqual(page.uploads.map((upload) => upload.grant), [B, A]);
});
