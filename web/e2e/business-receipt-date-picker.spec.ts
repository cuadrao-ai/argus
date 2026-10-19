import { expect, test } from "@playwright/test";
import { SHOT_DIR, expectTargets, installReceiptBusiness, noHorizontalScroll, openReceipt } from "./support/business-receipt-fixture";

test.skip(process.env.NEXT_PUBLIC_BUSINESS_PILOT_ENABLED !== "true", "/biz needs the Business pilot server");

for (const width of [1440, 390] as const) {
  test.describe(`receipt date picker at ${width}`, () => {
    test.use({ viewport: { width, height: 900 } });

    test("the date reads as a day, opens one Monday month, and every target is 44px", async ({ page }) => {
      await installReceiptBusiness(page);
      await openReceipt(page, /Ferretería La Esquina/);
      const fields = page.getByTestId("receipt-review-fields");
      const input = fields.getByLabel("Fecha", { exact: true });
      await expect(page.locator('input[type="date"]')).toHaveCount(0);
      await expect(input).toHaveAttribute("placeholder", "dd/mm/aaaa");
      await expect(input).toHaveValue(/^\d{1,2} [a-z]+ \d{4}$/);
      await input.scrollIntoViewIfNeeded();
      await page.screenshot({ path: `${SHOT_DIR}/date-picker-closed-${width}.png` });

      await fields.getByRole("button", { name: "[placeholder] business.date_picker.open" }).click();
      const dialog = page.getByTestId("date-picker-dialog");
      await expect(dialog).toBeVisible();
      await expect(dialog.locator("th")).toHaveText(["lu", "ma", "mi", "ju", "vi", "sá", "do"]);
      await expect(dialog.getByRole("grid")).toBeVisible();
      await expectTargets(page, '[data-testid="date-picker-dialog"] button');
      await expectTargets(page, '[data-testid="receipt-review-fields"] button[aria-haspopup="dialog"]');
      await noHorizontalScroll(page);
      const box = (await dialog.boundingBox())!;
      if (width < 720) {
        expect(Math.round(box.y + box.height)).toBe(900);
        expect(Math.round(box.width)).toBe(width);
      } else {
        const field = (await input.boundingBox())!;
        expect(box.y).toBeGreaterThanOrEqual(field.y + field.height);
        expect(box.width).toBeLessThan(400);
      }
      await page.screenshot({ path: `${SHOT_DIR}/date-picker-open-${width}.png` });

      await page.keyboard.press("ArrowRight");
      await page.keyboard.press("Enter");
      await expect(dialog).toHaveCount(0);
      await input.fill("05/10/2026");
      await input.blur();
      await expect(input).toHaveValue("5 oct 2026");
      await input.focus();
      await expect(input).toHaveValue("05/10/2026");
    });
  });
}
