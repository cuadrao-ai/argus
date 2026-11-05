import { expect, test, type Page } from "@playwright/test";

const frameworkText = "This page could not be found";

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
  test(`unknown route at ${width} is the branded missing page`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/no-such-page");
    const heading = page.getByRole("heading", { level: 1, name: "No encontramos esta página." });
    await expect(heading).toBeVisible();
    await expect(page.getByText("Puede que el enlace esté viejo o mal copiado.")).toBeVisible();
    const link = page.getByRole("link", { name: "Ir a Cuadrao" });
    await expect(link).toHaveAttribute("href", "/?auth=login");
    await expect(page.locator("body")).not.toContainText(frameworkText);
    const box = await link.boundingBox();
    expect(box?.height).toBeGreaterThanOrEqual(44);
    await hideDevOverlay(page);
    await page.keyboard.press("Tab");
    await expect(link).toBeFocused();
    const ring = await link.evaluate((node) => getComputedStyle(node).boxShadow);
    expect(ring).not.toBe("none");
    await shot(page, `404-${width}`);
  });
}

for (const width of [390, 1280]) {
  test(`an expired recovery link at ${width} shows the branded screen`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/auth/recovery?error=access_denied&error_code=otp_expired");
    await expect(page.getByRole("heading", { level: 1, name: "Este enlace ya venció o ya se usó." })).toBeVisible();
    const link = page.getByRole("link", { name: "Pedir un enlace nuevo" });
    await expect(link).toHaveAttribute("href", "/auth/forgot-password");
    await expect(page.locator("body")).not.toContainText(frameworkText);
    await expect(page.locator("body")).not.toContainText("Checking your recovery link");
    await shot(page, `recovery-${width}`);
  });

  test(`an expired invite at ${width} shows the invitation line`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/auth/link-error?error=access_denied&error_code=otp_expired&type=invite");
    await expect(page.getByText("Pide a quien te invitó que te envíe otra invitación.")).toBeVisible();
    await expect(page.getByRole("link", { name: "Ir a Cuadrao" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Pedir un enlace nuevo" })).toHaveCount(0);
    await shot(page, `invite-${width}`);
  });
}

test("a signed-in missing page follows the signed-in home", async ({ page }) => {
  await page.route("**/api/v1/me", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      user: { id: "user-1", email: "ada@example.test" },
      account_kind: "registered",
    }),
  }));
  await page.goto("/no-such-page");
  await expect(page.getByRole("link", { name: "Ir a Cuadrao" })).toHaveAttribute("href", "/?auth=login");
});
