import assert from "node:assert/strict";
import { test } from "bun:test";
import type { BusinessMontosReview } from "@/lib/business-dossier";
import { registerReceiptReviewPage, setup, type Dossier } from "./fixtures/receipt-review-page";

registerReceiptReviewPage();

type Source = NonNullable<Dossier["net_amount"]>["source"];
type Page = Awaited<ReturnType<typeof setup>>;
const subtotal = (source: Source) => ({ amount: "2923.73", source });
const mark = (page: Page) => page.row("net_amount").querySelector('[data-testid="row-status-net_amount"]');
const restore = (page: Page) => page.row("net_amount").querySelector<HTMLButtonElement>('[data-restore-inherited="net_amount"]');
const pencil = (page: Page) => page.row("net_amount").querySelector('button[aria-label^="Editar detalles · "]');

test("the Subtotal says who gave it by the server's source alone, and stays editable in each", async () => {
  for (const [source, calculated, back] of [["calculated", true, false], ["edited", false, true], ["read", false, false]] as const) {
    const page = await setup("fiscal", (dossier) => { dossier.net_amount = subtotal(source); });
    try {
      assert.equal(mark(page)?.getAttribute("data-status") === "calculated", calculated, source);
      assert.equal(Boolean(restore(page)), back, source);
      assert.ok(pencil(page), `${source} keeps its pencil`);
    } finally { await page.close(); }
  }
});

test("putting a typed Subtotal back asks the server for its own, and the server's answer shows", async () => {
  let source: Source = "edited";
  const sent: BusinessMontosReview[] = [];
  const page = await setup("fiscal", (dossier) => { dossier.net_amount = subtotal(source); }, (fixture) => ({
    reviewMontos: async (draft, version, montos) => {
      sent.push(montos);
      source = "calculated";
      return { ...await fixture.dossier(draft), version: version + 1, net_amount: subtotal(source) };
    },
  }));
  try {
    // The one restore control and wording of a linked field. The server states no calculated amount beside a typed one, so none is named.
    assert.equal(restore(page)?.getAttribute("aria-label"), "Restaurar: -");
    assert.ok(restore(page)?.querySelector("svg.lucide-rotate-ccw"));
    await page.act(async () => restore(page)!.click());
    await page.wait(() => sent.length === 1 && !restore(page));
    assert.deepEqual(sent, [{ net_amount: { state: "unknown", value: null } }]);
    assert.equal(mark(page)?.getAttribute("data-status"), "calculated");
  } finally { await page.close(); }
});

test("a record nobody can edit offers no way back to the calculated Subtotal", async () => {
  const page = await setup("readOnly", (dossier) => { dossier.net_amount = subtotal("edited"); });
  try {
    assert.equal(restore(page), null);
    assert.equal(mark(page), null);
  } finally { await page.close(); }
});
