import assert from "node:assert/strict";
import { describe, test } from "bun:test";
import { button, registerReceiptReviewPage, setup, type Dossier } from "./fixtures/receipt-review-page";

registerReceiptReviewPage();

/** A 2024 read on a 2026 upload. Only `yearToCheck`, the server's answer, differs between the cases. */
const readAs2024 = (yearToCheck: boolean) => (dossier: Dossier) => {
  dossier.facts.occurred_on = { state: "known", value: "2024-10-09", origin: "extracted", verified: false, source_ids: [] };
  dossier.sources[0] = { ...dossier.sources[0], received_at: "2026-10-10T14:20:00Z" };
  dossier.upload_year = 2026;
  dossier.year_to_check = yearToCheck;
};
const NOTE = '[data-testid="date-picker-upload-year"]';
const CALENDAR = 'button[aria-haspopup="dialog"]';

describe("the review's document date fixes a misread year in one click", () => {
  test("a dossier with a year to check offers its date in the upload year, and saves it only on the check", async () => {
    const page = await setup("fiscal", readAs2024(true));
    try {
      await page.openRow("occurred_on");
      const field = page.row("occurred_on");
      await page.act(async () => field.querySelector<HTMLButtonElement>(CALENDAR)!.click());
      const note = field.querySelector<HTMLElement>(NOTE);
      assert.match(note?.textContent ?? "", /Subido en 2026/, "the upload year is the dossier's");
      assert.equal([...field.querySelectorAll("button")].some((node) => node.textContent === "Hoy" || node.textContent === "Ayer"), false);
      await page.act(async () => button(note!, "Usar 9 oct 2026").click());
      assert.equal(page.writes.length, 0, "the button fills the field; the check saves");
      await page.act(async () => field.querySelector<HTMLButtonElement>(CALENDAR)!.click());
      assert.equal(field.querySelector(NOTE), null, "the date in the field is the person's now");
      await page.check("occurred_on");
      await page.wait(() => page.writes.length === 1);
      assert.deepEqual(page.writes[0].body, { occurred_on: { state: "known", value: "2026-10-09" } });
    } finally { await page.close(); }
  });

  test("the same 2024 date on the same 2026 upload offers nothing when the dossier has no year to check", async () => {
    const page = await setup("fiscal", readAs2024(false));
    try {
      await page.openRow("occurred_on");
      const field = page.row("occurred_on");
      await page.act(async () => field.querySelector<HTMLButtonElement>(CALENDAR)!.click());
      assert.ok(field.querySelector('[data-testid="date-picker-dialog"]'), "the calendar is open");
      assert.equal(field.querySelector(NOTE), null, "the browser compares no years");
    } finally { await page.close(); }
  });
});
