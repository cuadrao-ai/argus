import assert from "node:assert/strict";
import { describe, test } from "bun:test";
import { button, registerReceiptReviewPage, setup, type Dossier } from "./fixtures/receipt-review-page";

registerReceiptReviewPage();

const readAs = (day: string, receivedAt: string) => (dossier: Dossier) => {
  dossier.facts.occurred_on = { state: "known", value: day, origin: "extracted", verified: false, source_ids: [] };
  dossier.sources[0] = { ...dossier.sources[0], received_at: receivedAt };
};

describe("the review's document date fixes a misread year in one click", () => {
  test("a receipt read as 2024 but uploaded in 2026 offers its date in 2026, and saves it only on the check", async () => {
    const page = await setup("fiscal", readAs("2024-10-09", "2026-10-10T14:20:00Z"));
    try {
      await page.openRow("occurred_on");
      const field = page.row("occurred_on");
      await page.act(async () => field.querySelector<HTMLButtonElement>('button[aria-haspopup="dialog"]')!.click());
      const note = field.querySelector<HTMLElement>('[data-testid="date-picker-upload-year"]');
      assert.match(note?.textContent ?? "", /Subido en 2026/, "the upload year comes from the dossier's first source");
      assert.equal([...field.querySelectorAll("button")].some((node) => node.textContent === "Hoy" || node.textContent === "Ayer"), false);
      await page.act(async () => button(note!, "Usar 9 oct 2026").click());
      assert.equal(page.writes.length, 0, "the button fills the field; the check saves");
      await page.check("occurred_on");
      await page.wait(() => page.writes.length === 1);
      assert.deepEqual(page.writes[0].body, { occurred_on: { state: "known", value: "2026-10-09" } });
    } finally { await page.close(); }
  });
});
