import assert from "node:assert/strict";
import { describe, test } from "bun:test";
import type { BusinessDataSource } from "@/components/business-app/business-data";
import { button, fill, mount, registerReceiptReviewPage, setup } from "./fixtures/receipt-review-page";

registerReceiptReviewPage();

describe("approving sends only the suggestions on screen", () => {
  async function approveWith(dgiiFields?: (fixture: BusinessDataSource) => BusinessDataSource["dgiiFields"]) {
    const { dossierFixtureIds } = await import("@/components/business-app/dossier-fixtures");
    const sent: unknown[] = [];
    const page = await mount((fixture) => ({
      approveDraft: async (id, version, key, action, options) => { sent.push(options?.suggestions); return fixture.approveDraft(id, version, key, action, options); },
      ...(dgiiFields ? { dgiiFields: dgiiFields(fixture) } : {}),
    }));
    await page.open({ kind: "draft", draftId: dossierFixtureIds.fiscal }, () => Boolean(page.host.querySelector('[data-fact="category"]') || page.host.querySelector('[data-testid="receipt-facts-choices"] [role="alert"]')));
    const approve = async () => {
      await page.act(async () => button(page.host, "Aceptar").click());
      await page.wait(() => sent.length === 1);
    };
    return { ...page, sent, approve, close: () => page.act(async () => page.root.unmount()) };
  }

  test("while the tax fields load, no select shows and the approval saves no suggestion", async () => {
    const page = await approveWith(() => () => new Promise(() => undefined));
    try {
      assert.equal(page.host.querySelector('[data-fact="category"] select'), null, "no select is drawn yet");
      await page.approve();
      assert.deepEqual(page.sent, [undefined]);
    } finally { await page.close(); }
  });

  test("the approve shortcut reads the same rows: no select drawn, no suggestion sent", async () => {
    const page = await approveWith(() => () => new Promise(() => undefined));
    try {
      await page.act(async () => { assert.equal(page.runShortcut("approve"), true); });
      await page.wait(() => page.sent.length === 1);
      assert.deepEqual(page.sent, [undefined]);
    } finally { await page.close(); }
  });

  test("when the tax fields failed to load, the approval saves no suggestion", async () => {
    const page = await approveWith(() => async () => { throw new Error("tax fields unavailable"); });
    try {
      assert.ok(page.host.querySelector('[data-testid="receipt-facts-choices"] [role="alert"]'), "the load error shows");
      await page.approve();
      assert.deepEqual(page.sent, [undefined]);
    } finally { await page.close(); }
  });

  test("a suggested code the list does not offer shows Sin dato, so the approval does not save it", async () => {
    const page = await approveWith((fixture) => async () => {
      const fields = await fixture.dgiiFields();
      const category = fields["606"].find((field) => field.name === "category")!;
      category.options = category.options.filter((code) => code !== "02");
      return fields;
    });
    try {
      const row = page.host.querySelector('[data-fact="category"]');
      assert.equal(row?.querySelector("[data-row-value]")?.textContent, "Sin dato");
      await page.approve();
      assert.deepEqual(page.sent, [{ payment_method: { value: "03", source: "last_choice" } }]);
    } finally { await page.close(); }
  });

  test("a choice the person changed sends no suggestion for it", async () => {
    const sent: unknown[] = [];
    const page = await setup("fiscal", () => undefined, (fixture) => ({
      approveDraft: async (id, version, key, action, options) => { sent.push(options?.suggestions); return fixture.approveDraft(id, version, key, action, options); },
    }));
    try {
      await page.openRow("payment_method");
      await fill(page, '[data-fact="payment_method"] select', "01", HTMLSelectElement);
      await page.check("payment_method");
      await page.wait(() => Boolean(page.row("payment_method").querySelector('[data-testid="row-saved"]')));
      await page.act(async () => button(page.host, "Aceptar").click());
      await page.wait(() => sent.length === 1);
      assert.deepEqual(sent, [{ category: { value: "02", source: "last_choice" } }]);
    } finally { await page.close(); }
  });
});
