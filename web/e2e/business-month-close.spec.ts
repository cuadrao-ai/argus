import { expect, test, type Page } from "@playwright/test";
import { monthCloseSampleDocuments, monthCloseSummary } from "../lib/business-month-close";
import { installBreakpointFixture } from "./support/breakpoint-fixture";

function monthKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}

function summaryFor(offset: number) {
  const now = new Date();
  const month = new Date(now.getFullYear(), now.getMonth() + offset, 1);
  const key = monthKey(month);
  return monthCloseSummary(monthCloseSampleDocuments(now).filter((item) => item.occurred_on.startsWith(key)));
}

async function shot(page: Page, name: string) {
  const directory = process.env.CUADRAO_MONTH_CLOSE_EVIDENCE_DIR;
  if (directory) await page.screenshot({ path: `${directory}/${name}.png`, fullPage: true });
}

async function setup(page: Page, width: number) {
  await page.setViewportSize({ width, height: 900 });
  page.on("pageerror", (error) => {
    throw error;
  });
  await page.addInitScript(() => {
    const style = document.createElement("style");
    style.textContent = "nextjs-portal { display: none !important; }";
    document.addEventListener("DOMContentLoaded", () => document.head.appendChild(style));
  });
  await page.route("**/*", (route) => (["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort()));
  await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
}

async function openMonth(page: Page) {
  await page.goto("/dev/business-preview?chat=off&view=month_close");
  await expect(page.getByTestId("month-close-net")).toBeVisible();
}

test.describe("cuadrar el mes", () => {
  for (const [width, prefix] of [
    [1280, "desktop"],
    [390, "mobile"],
  ] as const) {
    test(`summary, marks, blockers, and close in es-419 at ${width}px`, async ({ page }) => {
      await setup(page, width);
      await openMonth(page);
      const current = summaryFor(0);
      const previous = summaryFor(-1);
      await expect(page.getByRole("heading", { name: "Cuadrar el mes" })).toBeVisible();
      await expect(page.getByTestId("month-close-net")).toContainText("Resultado neto");
      await expect(page.getByTestId("month-close-net")).toContainText("RD$");
      await expect(page.getByTestId("month-close-net")).toHaveAttribute("data-amount", current.net_before_itbis);
      await expect(page.getByTestId("month-close-itbis")).toContainText("ITBIS por pagar");
      await expect(page.getByTestId("month-close-itbis")).toHaveAttribute("data-amount", current.itbis_owed);
      await expect(page.getByTestId("month-close-blockers")).toContainText("Farmacia Central no tiene RNC");
      await expect(page.getByTestId("month-close-blockers")).toContainText("Suplidores del Caribe no tiene NCF ni e-CF");
      await expect(page.getByTestId("month-close-close")).toBeDisabled();
      await expect(page.getByTestId("month-close-reason")).toBeVisible();
      await page.getByTestId("month-close-filter-pendiente").click();
      await expect(page.locator('[data-document-id="inv-colmado"]')).toHaveCount(0);
      await expect(page.locator('[data-document-id="inv-taller"]')).toBeVisible();
      await page.getByTestId("month-close-filter-all").click();
      await page.getByRole("radio", { name: "Más antigua" }).click();
      const dates = await page.getByTestId("month-close-row").evaluateAll((rows) => rows.map((row) => row.querySelector("time")?.getAttribute("dateTime") ?? ""));
      expect(dates).toEqual([...dates].sort());
      await page.getByRole("radio", { name: "Más reciente" }).click();
      const blocker = page.getByRole("link", { name: "Farmacia Central no tiene RNC" });
      await blocker.focus();
      await page.keyboard.press("Enter");
      await expect(page.locator('[data-document-id="inv-farmacia"]')).toBeFocused();
      await shot(page, `${prefix}-open-blockers`);

      await page.getByRole("button", { name: "Marcar cobrado, Taller Hermanos Peña" }).click();
      await expect(page.locator('[data-document-id="inv-taller"]')).toHaveAttribute("data-status", "cobrado");
      await page.getByRole("button", { name: "Marcar pagado, Edenorte" }).click();
      await expect(page.locator('[data-document-id="rcpt-edenorte"]')).toHaveAttribute("data-status", "pagado");
      await expect(page.getByTestId("month-close-net")).toHaveAttribute("data-amount", current.net_before_itbis);
      await expect(page.getByTestId("month-close-close")).toBeDisabled();
      await expect(page.getByTestId("month-close-blockers")).toContainText("Transporte Díaz");
      await shot(page, `${prefix}-after-marking`);

      await page.getByRole("radio", { name: "Mes pasado" }).click();
      await expect(page.getByTestId("month-close-net")).toHaveAttribute("data-amount", previous.net_before_itbis);
      await expect(page.getByTestId("month-close-itbis")).toHaveAttribute("data-amount", previous.itbis_owed);
      await expect(page.getByTestId("month-close-close")).toBeDisabled();
      await page.getByRole("button", { name: "Marcar cobrado, Panadería Luna" }).click();
      await page.getByRole("button", { name: "Marcar pagado, Limpieza Rosa" }).click();
      await expect(page.getByTestId("month-close-blockers")).toHaveCount(0);
      await expect(page.getByTestId("month-close-close")).toBeEnabled();
      await shot(page, `${prefix}-ready-to-close`);

      await page.getByTestId("month-close-close").click();
      const dialog = page.getByRole("dialog", { name: "¿Cerrar este mes?" });
      await expect(dialog).toBeVisible();
      await dialog.getByTestId("month-close-confirm").click();
      await expect(page.getByTestId("month-close-closed")).toContainText("Mes cerrado");
      await expect(page.getByTestId("month-close-mark-cobrado")).toHaveCount(0);
      await expect(page.getByTestId("month-close-mark-pagado")).toHaveCount(0);
      await expect(page.locator('[data-document-id="inv-luna"]')).toHaveAttribute("data-status", "cobrado");
      await expect(page.locator('[data-document-id="inv-luna"]')).toHaveAttribute("data-locked", "true");
      await expect(page.locator('[data-document-id="rcpt-rosa"]')).toHaveAttribute("data-status", "pagado");
      await shot(page, `${prefix}-closed`);
    });
  }
});
