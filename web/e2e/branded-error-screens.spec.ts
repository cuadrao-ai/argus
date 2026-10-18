import { expect, test, type Page } from "@playwright/test";

const frameworkText = /This page could not be found|Application error|supabase/i;

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("i18nextLng", "es-419");
  });
  await page.route("**/api/v1/me", (route) => route.fulfill({
    status: 401,
    contentType: "application/json",
    body: JSON.stringify({ detail: "unauthorized" }),
  }));
});

async function hideDevOverlay(page: Page) {
  await page.locator('[aria-label="Open Next.js Dev Tools"]').evaluateAll((nodes) => {
    for (const node of nodes) node.remove();
  });
}

async function shot(page: Page, name: string) {
  const dir = process.env.BRANDED_STATUS_SHOTS;
  if (!dir) return;
  await hideDevOverlay(page);
  await page.screenshot({ path: `${dir}/${name}.png` });
}

for (const width of [390, 1280]) {
  test(`an unknown recovery type at ${width} is the link screen`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/auth/recovery?error=access_denied&type=not-a-flow");
    await expect(page.getByRole("heading", { level: 1, name: "Este enlace ya venció o ya se usó." })).toBeVisible();
    await expect(page.getByRole("heading", { name: "No encontramos esta página." })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Pedir un enlace nuevo" })).toHaveAttribute("href", "/auth/forgot-password");
    await expect(page.locator("body")).not.toContainText(frameworkText);
    await shot(page, `unknown-type-${width}`);
  });

  test(`a confirm failure at ${width} uses the link screen`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/auth/confirm/error?error=access_denied&error_code=otp_expired&type=invite");
    await expect(page.getByText("Pide a quien te invitó que te envíe otra invitación.")).toBeVisible();
    await expect(page.locator("body")).not.toContainText(frameworkText);
    await shot(page, `confirm-invite-${width}`);
  });

  test(`the server screen at ${width} names the retry, home, reference, and address`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/dev/error-screen?screen=server");
    await expect(page.getByRole("heading", { level: 1, name: "Algo salió mal de nuestro lado." })).toBeVisible();
    await expect(page.getByRole("button", { name: "Intentar de nuevo" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Ir a Inicio" })).toBeVisible();
    await expect(page.getByText("c0ffee00")).toBeVisible();
    await expect(page.getByRole("link", { name: "admin@cuadrao.ai" })).toBeVisible();
    await expect(page.locator("body")).not.toContainText(frameworkText);
    await shot(page, `server-${width}`);
  });

  test(`a removed member at ${width} can return to their businesses`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/dev/error-screen?screen=removed");
    await expect(page.getByRole("heading", { level: 1, name: "No tienes acceso a este negocio." })).toBeVisible();
    await expect(page.getByRole("button", { name: "Ir a mis negocios" })).toBeVisible();
    await shot(page, `removed-${width}`);
  });

  test(`offline at ${width} is a banner that keeps the file name`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/dev/error-screen?screen=offline");
    await expect(page.getByText("Sin conexión. Revisa tu internet.")).toBeVisible();
    await expect(page.getByText("factura.pdf")).toBeVisible();
    await expect(page.getByRole("button", { name: "Reintentar" })).toBeVisible();
    await shot(page, `offline-${width}`);
  });
}

test("an ended session on the login screen says so and keeps the return path", async ({ page }) => {
  await page.goto("/?auth=login&notice=session_ended&return_to=%2Fbiz%3Freceipt%3Dr1");
  await expect(page.getByTestId("session-ended")).toHaveText("Tu sesión terminó. Entra de nuevo.");
  await expect(page.locator("body")).not.toContainText(frameworkText);
  await shot(page, "session-ended-1280");
});
