import { expect, test } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import type { ReceiptDetail } from "../lib/business-api";
import { installReceiptBusiness } from "./support/business-receipt-fixture";

for (const width of [1280, 390]) {
  for (const count of [1, 28]) {
    test(`receipt navigation stays in the ${count}-item tab at ${width}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      const source = createFixtureBusinessDataSource({ chatAvailable: false });
      const template = await source.receipt("rcpt-ferreteria");
      const receipts: ReceiptDetail[] = Array.from({ length: count + 1 }, (_, index) => ({
        ...template,
        id: `navigation-${index}`,
        merchant: `Recibo de prueba ${index}`,
        draft_id: null,
        status: "needs_attention",
        enterable: false,
        preparable: false,
        attention: "missing_ncf",
        activity: null,
        received_at: new Date(Date.UTC(2026, 9, 31, 12, 0, -index)).toISOString(),
        bandeja: { por_revisar: true, con_problema: index !== 0, leyendo: false },
        bandeja_group: { group: index === 0 ? "listo" : "attention", reason: index === 0 ? null : "missing_ncf", draft_id: null, version: null },
      }));
      await installReceiptBusiness(page, (parts, route) => {
        if (parts[0] !== "receipts") return undefined;
        if (parts.length === 1) return Promise.resolve({ items: receipts, activity: { reading_count: 0, unread_count: 0, presentation: "none", pending_review_count: receipts.length, needs_attention_count: count, ready_to_review_count: receipts.length, bandeja_attention_count: count, bandeja_listo_count: 1 } });
        if (parts.length === 2) return Promise.resolve(receipts.find(receipt => receipt.id === parts[1]));
        if (parts[2] === "source") return route.fulfill({ status: 404, json: { code: "fixture_only" } }).then(() => null);
        return undefined;
      });
      await page.goto("/biz?view=inbox");
      await expect(page.getByTestId("reception-row").first()).toContainText("Recibo de prueba 0");
      await page.getByRole("tab", { name: /^Necesitan atención/ }).click();
      await expect(page.getByTestId("reception-row").first()).toContainText("Recibo de prueba 1");
      await page.getByTestId("reception-row").first().getByRole("button", { name: "Abrir", exact: true }).click();
      const place = page.getByTestId("receipt-place");
      await expect(place).toContainText(`1 de ${count}`);
      await expect(place.getByRole("button").first()).toBeDisabled();
      if (count === 1) {
        await expect(place.getByRole("button").last()).toBeDisabled();
      } else {
        await place.getByRole("button").last().click();
        await expect(page).toHaveURL(/receipt=navigation-2/);
        await expect(place).toContainText("2 de 28");
        await place.getByRole("button").first().click();
        await expect(page).toHaveURL(/receipt=navigation-1/);
        await expect(place).toContainText("1 de 28");
      }
      await page.screenshot({ path: test.info().outputPath(`receipt-navigation-${count}-${width}.png`) });
    });
  }
}
