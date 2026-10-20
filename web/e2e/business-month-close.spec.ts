import { expect, test, type Locator, type Page } from "@playwright/test";
import { currentMonthKey, formatMonthLabel, monthCloseSampleDocuments, monthCloseSummary, shiftMonthKey } from "../lib/business-month-close";
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

async function shot(page: Page, name: string, target?: Locator) {
  const directory = process.env.CUADRAO_MONTH_CLOSE_EVIDENCE_DIR;
  if (!directory) return;
  const path = `${directory}/${name}.png`;
  if (target) await target.screenshot({ path });
  else await page.screenshot({ path });
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

async function openHome(page: Page) {
  await page.goto("/dev/business-preview?chat=off");
  await expect(page.getByTestId("month-close-cards")).toBeVisible();
}

test.describe("inicio is the month close", () => {
  for (const [width, prefix] of [
    [1280, "desktop"],
    [390, "mobile"],
  ] as const) {
    test(`four cards, pending net, fiscal lock, and close in es-419 at ${width}px`, async ({ page }) => {
      await setup(page, width);
      await openHome(page);
      const current = summaryFor(0);
      const previous = summaryFor(-1);
      const nav = width >= 720 ? page.getByTestId("business-sidebar-nav") : page.getByTestId("business-bottom-tabs");
      await expect(nav.getByRole("button", { name: "Inicio", exact: true })).toBeVisible();
      await expect(page.getByRole("button", { name: "Facturas", exact: true })).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Transacciones", exact: true })).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Exportar", exact: true })).toHaveCount(0);

      await expect(page.getByTestId("month-close-income")).toContainText("Ingresos");
      await expect(page.getByTestId("month-close-income")).toContainText("RD$");
      await expect(page.getByTestId("month-close-income")).toHaveAttribute("data-amount", current.income_before_itbis);
      await expect(page.getByTestId("month-close-expenses")).toContainText("Gastos");
      await expect(page.getByTestId("month-close-expenses")).toHaveAttribute("data-amount", current.expense_before_itbis);
      await expect(page.getByTestId("month-close-itbis")).toContainText("ITBIS a pagar");
      await expect(page.getByTestId("month-close-itbis")).toContainText("RD$");
      await expect(page.getByTestId("month-close-itbis")).toHaveAttribute("data-amount", current.itbis_owed);

      const net = page.getByTestId("month-close-net");
      await expect(net).toContainText("Resultado neto");
      await expect(net).toHaveAttribute("data-state", "pending");
      await expect(net).not.toHaveAttribute("data-amount");
      await expect(net).toContainText("Pendiente");
      await expect(net).toContainText("documentos pendientes");
      await expect(net).not.toContainText("RD$");

      await expect(page.getByTestId("month-close-receivable")).toBeVisible();
      await expect(page.getByTestId("month-close-payable")).toBeVisible();
      await expect(page.getByTestId("month-close-blockers")).toContainText("Farmacia Central no tiene RNC");
      await expect(page.getByTestId("month-close-blockers")).toContainText("Suplidores del Caribe no tiene NCF ni e-CF");
      await expect(page.getByTestId("month-close-close")).toBeDisabled();
      await expect(page.getByTestId("month-close-reason")).toContainText("Falta el RNC o el NCF");
      await page.locator("#business-overview-title").scrollIntoViewIfNeeded();
      await shot(page, `${prefix}-inicio`);

      const blocker = page.getByRole("link", { name: "Farmacia Central no tiene RNC" });
      await shot(page, `${prefix}-locked-close`, page.getByTestId("month-close-blockers"));
      await blocker.focus();
      await page.keyboard.press("Enter");
      await expect(page.locator('[data-document-id="inv-farmacia"]')).toBeFocused();

      await page.getByRole("button", { name: "Marcar cobrado, Taller Hermanos Peña" }).click();
      await expect(page.getByRole("button", { name: "Marcar cobrado, Taller Hermanos Peña" })).toHaveCount(0);
      await page.getByRole("button", { name: "Marcar pagado, Edenorte" }).click();
      await expect(page.getByRole("button", { name: "Marcar pagado, Edenorte" })).toHaveCount(0);
      await expect(net).toHaveAttribute("data-state", "pending");
      await expect(net).not.toContainText("RD$");
      await expect(page.getByTestId("month-close-close")).toBeDisabled();
      await expect(page.getByTestId("month-close-blockers")).toContainText("Transporte Díaz");

      await expect(page.getByTestId("month-close-month")).toHaveText(formatMonthLabel(currentMonthKey(new Date())));
      await expect(page.getByTestId("month-close-month-next")).toBeDisabled();
      await page.getByRole("button", { name: "Mes anterior" }).click();
      await expect(page.getByTestId("month-close-month")).toHaveText(formatMonthLabel(shiftMonthKey(currentMonthKey(new Date()), -1)));
      await expect(net).toHaveAttribute("data-state", "pending");
      await expect(net).toContainText("documentos pendientes");
      await expect(net).not.toContainText("RD$");
      await expect(page.getByTestId("month-close-itbis")).toHaveAttribute("data-amount", previous.itbis_owed);
      await expect(page.getByTestId("month-close-close")).toBeEnabled();
      await expect(page.getByTestId("month-close-blockers")).toHaveCount(0);
      await shot(page, `${prefix}-pendiente`);

      await page.getByRole("button", { name: "Marcar cobrado, Panadería Luna" }).click();
      await page.getByRole("button", { name: "Marcar pagado, Limpieza Rosa" }).click();
      await expect(net).toHaveAttribute("data-state", "final");
      await expect(net).toHaveAttribute("data-amount", previous.net_before_itbis);
      await expect(net).toContainText("RD$");
      await expect(page.getByTestId("month-close-close")).toBeEnabled();

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
      await expect(net).toHaveAttribute("data-amount", previous.net_before_itbis);
      await shot(page, `${prefix}-closed`);
    });

    test(`empty, loading, and overdue layouts in es-419 at ${width}px`, async ({ page }) => {
      await setup(page, width);
      await page.goto("/dev/business-preview?chat=off&monthClose=loading");
      const loading = page.getByTestId("month-close-loading");
      await expect(loading).toHaveAttribute("data-layout", "loading");
      await expect(page.getByTestId("month-close-loading-card")).toHaveCount(4);
      await expect(page.getByTestId("month-close-loading-row")).toHaveCount(6);
      await loading.scrollIntoViewIfNeeded();
      await shot(page, `${prefix}-loading`);

      await page.goto("/dev/business-preview?chat=off&monthClose=empty");
      const empty = page.getByTestId("month-close-empty");
      await expect(empty).toHaveAttribute("data-layout", "empty");
      await expect(empty).toContainText("Este mes no tiene documentos");
      await expect(page.getByTestId("month-close-empty-action")).toHaveText("Elegir mes");
      await empty.scrollIntoViewIfNeeded();
      await shot(page, `${prefix}-empty`);

      await page.goto("/dev/business-preview?chat=off");
      await expect(page.getByTestId("month-close-cards")).toBeVisible();
      await page.getByTestId("month-close-state-overdue").click();
      const overdue = page.getByTestId("month-close-overdue");
      await expect(overdue).toHaveAttribute("data-layout", "overdue");
      await expect(overdue).toContainText("Farmacia Central");
      await expect(overdue).toContainText("Vencida");
      await expect(overdue).not.toContainText("Taller Hermanos Peña");
      await overdue.scrollIntoViewIfNeeded();
      await shot(page, `${prefix}-overdue`);
    });
  }
});
