import { expect, test } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { installBreakpointFixture } from "./support/breakpoint-fixture";

test("production approve-next keeps the next receipt title focused", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
  await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
  const source = createFixtureBusinessDataSource({ chatAvailable: false });
  await page.route("**/api/v1/business/**", async (route) => {
    const url = new URL(route.request().url());
    const parts = url.pathname.split("/business/")[1].split("/");
    const body = route.request().postDataJSON() ?? {};
    try {
    let json: unknown;
    if (parts[0] === "space") json = { id: "fixture-space", name: "Mi negocio" };
    else if (parts[0] === "spaces") json = { spaces: await source.spaces() };
    else if (parts[0] === "workspace") json = await source.workspace();
    else if (parts[0] === "overview") json = await source.overview("2026-10-01", "2026-10-31");
    else if (parts[0] === "receipt-reading") json = { enabled: true, available: true, can_change: false };
    else if (parts[0] === "receipts" && parts.length === 1) json = await source.receiptPage!(url.searchParams.get("view") === "all" ? "all" : "inbox");
    else if (parts[0] === "receipts" && parts[2] === "review") json = await source.saveReview(parts[1], body.version, body.fields);
    else if (parts[0] === "receipts" && parts[2] === "read") json = { ok: true };
    else if (parts[0] === "receipts" && parts.length === 2) json = await source.receipt(parts[1]);
    else if (parts[0] === "drafts" && parts[2] === "dossier") json = await source.dossier(parts[1]);
    else if (parts[0] === "drafts" && parts[2] === "approve") json = await source.approveDraft(parts[1], body.version, "synthetic-key");
    else if (parts[0] === "email" && parts.length === 1) json = await source.emailIntake();
    else if (["captures", "updates", "expenses"].includes(parts[0]) || parts.join("/") === "email/deliveries") json = { items: [] };
    else return route.fulfill({ status: 404, json: { code: "fixture_only" } });
    return route.fulfill({ json });
    } catch (error) {
      const failure = error as { status?: number; code?: string };
      return route.fulfill({ status: failure.status ?? 500, json: { code: failure.code ?? "fixture_failure" } });
    }
  });
  await page.goto("/biz?view=inbox");
  await page.getByTestId("business-inbox-receipts").getByRole("button", { name: /Ferretería La Esquina/ }).click();
  await page.getByLabel("Pagado desde").selectOption({ index: 1 });
  await page.getByRole("button", { name: "Guardar detalles de revisión", exact: true }).click();
  await page.getByRole("button", { name: "Aprobar y siguiente", exact: true }).click();
  await expect(page).toHaveURL(/receipt=rcpt-papeleria/);
  await expect(page.getByRole("heading", { name: "Revisar recibo", exact: true })).toBeFocused();
});
