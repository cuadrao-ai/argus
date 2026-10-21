import { expect, test, type Locator, type Page } from "@playwright/test";
import { currentMonthKey, formatMonthLabel, monthCloseSampleDocuments, monthCloseSummary, shiftMonthKey } from "../lib/business-month-close";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { fulfillAcceptedBusinessConsent, installBreakpointFixture } from "./support/breakpoint-fixture";
import { monthCloseWire, OPEN_ITEMS_WIRE } from "./support/month-close-wire";

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
      await expect(nav.getByRole("button", { name: "Transacciones", exact: true })).toBeVisible();
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
      await expect(net).toContainText(/Falta marcar \d+ documentos/);
      await expect(net).not.toContainText("RD$");

      const checklist = page.getByTestId("month-close-checklist");
      await expect(checklist).toContainText("Para cerrar");
      await expect(page.getByTestId("month-close-task-review")).toContainText(/Revisa \d+ recibos? en la Bandeja/);
      const fiscal = page.getByTestId("month-close-task-fiscal");
      await expect(fiscal).toContainText("Completa el RNC o NCF de 3 documentos");
      await expect(fiscal).toContainText("Necesario para cerrar el mes");
      await expect(page.getByTestId("month-close-blockers")).toHaveCount(0);
      await fiscal.getByRole("button", { name: "Ver cuáles" }).click();
      await expect(page.getByTestId("month-close-blockers")).toContainText("Farmacia Central no tiene RNC");
      await expect(page.getByTestId("month-close-blockers")).toContainText("Suplidores del Caribe no tiene NCF ni e-CF");
      // Cerrar stays hidden while steps are left; a line says how many.
      await expect(page.getByTestId("month-close-close")).toHaveCount(0);
      await expect(page.getByTestId("month-close-steps-note")).toContainText(/Cuando termines/);
      await page.locator("#business-overview-title").scrollIntoViewIfNeeded();
      await shot(page, `${prefix}-inicio`);
      await shot(page, `${prefix}-locked-close`, page.getByTestId("month-close-checklist"));

      const receivable = page.getByTestId("month-close-receivable");
      const payable = page.getByTestId("month-close-payable");
      await expect(page.getByText("Pendiente hoy", { exact: true })).toBeVisible();
      await expect(receivable.getByTestId("month-close-receivable-total")).toContainText("RD$");
      await expect(receivable.getByTestId("month-close-receivable-overdue")).toContainText(/\d+ vencidas/);
      await expect(payable.getByTestId("month-close-payable-overdue")).toContainText(/\d+ vencidas/);
      await expect(receivable.getByTestId("month-close-lateness").first()).toContainText("tarde");

      await page.getByRole("button", { name: "Marcar cobrado, Taller Hermanos Peña" }).click();
      await expect(page.getByRole("button", { name: "Marcar cobrado, Taller Hermanos Peña" })).toHaveCount(0);
      await page.getByRole("button", { name: "Marcar pagado, Edenorte" }).click();
      await expect(page.getByRole("button", { name: "Marcar pagado, Edenorte" })).toHaveCount(0);
      await expect(net).toHaveAttribute("data-state", "pending");
      await expect(net).not.toContainText("RD$");
      await expect(page.getByTestId("month-close-close")).toHaveCount(0);
      await expect(page.getByTestId("month-close-blockers")).toContainText("Transporte Díaz");

      await expect(page.getByTestId("month-close-month")).toHaveText(formatMonthLabel(currentMonthKey(new Date())));
      await expect(page.getByTestId("month-close-month-next")).toBeDisabled();
      await page.getByRole("button", { name: "Mes anterior" }).click();
      await expect(page.getByTestId("month-close-month")).toHaveText(formatMonthLabel(shiftMonthKey(currentMonthKey(new Date()), -1)));
      await expect(net).toHaveAttribute("data-state", "pending");
      await expect(net).toContainText(/Falta marcar \d+ documentos/);
      await expect(net).not.toContainText("RD$");
      await expect(page.getByTestId("month-close-itbis")).toHaveAttribute("data-amount", previous.itbis_owed);
      await expect(page.getByTestId("month-close-close")).toHaveCount(0);
      await expect(page.getByTestId("month-close-steps-note")).toContainText(/Cuando termines/);
      await expect(page.getByTestId("month-close-blockers")).toHaveCount(0);
      await shot(page, `${prefix}-pendiente`);

      await page.getByRole("button", { name: "Marcar cobrado, Panadería Luna" }).click();
      await page.getByRole("button", { name: "Marcar pagado, Limpieza Rosa" }).click();
      await expect(net).toHaveAttribute("data-state", "final");
      await expect(net).toHaveAttribute("data-amount", previous.net_before_itbis);
      await expect(net).toContainText("RD$");
      // The Bandeja still holds receipts to review, so Cerrar stays hidden and the line names the one step left.
      await expect(page.getByTestId("month-close-close")).toHaveCount(0);
      await expect(page.getByTestId("month-close-task-review")).toContainText(/Revisa \d+ recibos? en la Bandeja/);
      await expect(page.getByTestId("month-close-steps-note")).toContainText("Cuando termines el paso que falta, podrás cerrar");
      await expect(page.getByTestId("month-close-task-settle")).toHaveCount(0);
      await shot(page, `${prefix}-one-step-left`);
    });

    test(`empty, loading, and overdue layouts in es-419 at ${width}px`, async ({ page }) => {
      await setup(page, width);
      await page.goto("/dev/business-preview?chat=off&monthClose=loading");
      const loading = page.getByTestId("month-close-loading");
      await expect(loading).toHaveAttribute("data-layout", "loading");
      await expect(page.getByTestId("month-close-loading-card")).toHaveCount(4);
      await expect(page.getByTestId("month-close-loading-row")).toHaveCount(3);
      await loading.scrollIntoViewIfNeeded();
      await shot(page, `${prefix}-loading`);

      await page.goto("/dev/business-preview?chat=off&monthClose=empty");
      const empty = page.getByTestId("month-close-empty");
      await expect(empty).toHaveAttribute("data-layout", "empty");
      await expect(empty).toContainText("Este mes no tiene documentos");
      await expect(empty.getByRole("button", { name: "Elegir mes", exact: true })).toBeVisible();
      await empty.scrollIntoViewIfNeeded();
      await shot(page, `${prefix}-empty`);

      await page.goto("/dev/business-preview?chat=off");
      await expect(page.getByTestId("month-close-cards")).toBeVisible();
      const receivable = page.getByTestId("month-close-receivable");
      await expect(receivable.getByTestId("month-close-receivable-overdue")).toContainText(/\d+ vencidas/);
      const late = receivable.getByTestId("month-close-lateness");
      await expect(late.filter({ hasText: "tarde" }).first()).toHaveAttribute("data-tone", /.+/);
      await expect(receivable).toContainText("Farmacia Central");
      await expect(receivable.getByRole("button", { name: "Marcar cobrado, Farmacia Central" })).toBeVisible();
      await receivable.scrollIntoViewIfNeeded();
      await shot(page, `${prefix}-overdue`, receivable);
    });
  }

  test("marks in a row share one toast, Deshacer reopens them, and an emptied list says it is done", async ({ page }) => {
    await setup(page, 1280);
    await openHome(page);
    const receivable = page.getByTestId("month-close-receivable");
    const toast = page.getByTestId("toast-viewport");
    const names = ["Panadería Luna", "Farmacia Central", "Taller Hermanos Peña"];
    for (const name of names) await receivable.getByRole("button", { name: `Marcar cobrado, ${name}` }).click();
    await expect(toast).toContainText("3 facturas cobradas.");
    await expect(toast.getByRole("button", { name: "Deshacer" })).toHaveCount(1);
    await expect(receivable).toContainText("Todo cobrado");
    await expect(receivable.getByTestId("month-close-row")).toHaveCount(0);

    await toast.getByRole("button", { name: "Deshacer" }).click();
    for (const name of names) await expect(receivable.getByRole("button", { name: `Marcar cobrado, ${name}` })).toBeVisible();
    await expect(receivable).not.toContainText("Todo cobrado");
  });
});

test.describe("Pendiente hoy on the live wire", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  async function openWire(page: Page) {
    await page.route("**/*", (route) => (["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort()));
    await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
    const source = createFixtureBusinessDataSource({ chatAvailable: false });
    const state = { failMarks: true, marks: 0, settled: false };
    await page.route("**/api/v1/business/**", async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const path = url.pathname.split("/business/")[1];
      if (path === "workspace") return route.fulfill({ json: await source.workspace() });
      if (path === "space") return route.fulfill({ json: { id: "fixture-space", name: "Colmado de prueba" } });
      if (path === "spaces") return route.fulfill({ json: { spaces: (await source.spaces()).slice(0, 1) } });
      if (path === "overview") return route.fulfill({ json: await source.overview("2026-10-01", "2026-10-31") });
      if (path === "receipts") return route.fulfill({ json: { items: [], activity: { reading_count: 0, unread_count: 0, presentation: "none" } } });
      if (path === "receipt-reading") return route.fulfill({ json: { enabled: false, available: true, can_change: false } });
      if (path === "email") return route.fulfill({ json: { enabled: true, receiving_address: "recibos@example.test" } });
      if (path === "email/deliveries" || path === "captures") return route.fulfill({ json: { items: [] } });
      if (path === "consent") return fulfillAcceptedBusinessConsent(route);
      if (path === "month-close") return route.fulfill({ json: monthCloseWire(url.searchParams.get("month") ?? "2026-10") });
      if (path === "open-items") {
        return route.fulfill({ json: state.settled ? { cuentas_por_cobrar: { count: 0, totals: [], items: [] }, cuentas_por_pagar: OPEN_ITEMS_WIRE.cuentas_por_pagar } : OPEN_ITEMS_WIRE });
      }
      if (path?.startsWith("month-close/documents/") && request.method() === "PATCH") {
        state.marks++;
        if (state.failMarks) return route.fulfill({ status: 503, json: { code: "synthetic_failure" } });
        state.settled = true;
        return route.fulfill({ json: { status: "cobrado" } });
      }
      return route.fulfill({ status: 404, json: { code: "fixture_only" } });
    });
    await page.goto("/biz");
    await expect(page.getByTestId("month-close-receivable")).toBeVisible();
    return state;
  }

  test("a failed mark says so beside the work with Reintentar, and the retry confirms with one toast", async ({ page }) => {
    const state = await openWire(page);
    const mark = page.getByRole("button", { name: "Marcar cobrado, Colmado La Esquina" });
    await mark.click();
    const problem = page.getByTestId("month-close-work-problem");
    await expect(problem).toContainText("No pudimos guardar el cambio");
    await expect(page.getByTestId("toast-viewport")).not.toContainText("cobrada");
    await expect(mark).toBeVisible();

    state.failMarks = false;
    await problem.getByRole("button", { name: "Reintentar" }).click();
    await expect(problem).toHaveCount(0);
    await expect(page.getByTestId("toast-viewport")).toContainText("Factura de Colmado La Esquina cobrada.");
    await expect(page.getByTestId("month-close-nothing-open")).toContainText("Todo al día");
    expect(state.marks).toBe(2);
  });

  test("being offline docks one banner at the top and leaves the toasts alone", async ({ page }) => {
    await openWire(page);
    await expect(page.getByTestId("connection-banner")).toHaveCount(0);
    await page.context().setOffline(true);
    await expect(page.getByTestId("connection-banner")).toBeVisible();
    await expect(page.getByTestId("connection-banner")).toHaveCount(1);
    await expect(page.getByTestId("toast-viewport")).not.toContainText(/conexión|internet/i);
    await page.context().setOffline(false);
    await expect(page.getByTestId("connection-banner")).toHaveCount(0);
  });

  test("a failed month close says so inside the confirm alert and the month stays open", async ({ page }) => {
    const state = await openWire(page);
    state.failMarks = false;
    await page.getByRole("button", { name: "Marcar cobrado, Colmado La Esquina" }).click();
    await page.getByTestId("month-close-close").click();
    const dialog = page.getByRole("alertdialog", { name: "¿Cerrar este mes?" });
    await dialog.getByTestId("confirm-dialog-confirm").click();
    await expect(dialog.getByTestId("confirm-dialog-error")).toContainText("No pudimos cerrar el mes");
    await expect(page.getByTestId("toast-viewport")).not.toContainText("No pudimos cerrar el mes");
    await dialog.getByRole("button", { name: "Volver" }).click();
    await expect(dialog).toHaveCount(0);
    await expect(page.getByTestId("month-close-closed")).toHaveCount(0);
  });
});
