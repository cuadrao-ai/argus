import { expect, test, type Page } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { installBreakpointFixture } from "./support/breakpoint-fixture";

const evidence = process.env.CUADRAO_SIDEBAR_EVIDENCE_DIR;
const baseline = process.env.CUADRAO_SIDEBAR_BASELINE === "true";
async function setup(page: Page, count = 2, theme: "light" | "dark" = "light") {
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
  await installBreakpointFixture(page, { language: "es-419", theme, emptyChat: true });
  const source = createFixtureBusinessDataSource({ chatAvailable: false });
  await page.route("**/api/v1/business/**", async (route) => {
    const path = new URL(route.request().url()).pathname.split("/business/")[1];
    let json: unknown;
    if (path === "spaces") json = { spaces: (await source.spaces()).slice(0, count).map((space, i) => ({ ...space, name: i ? "Panadería Sol" : "Colmado La Esquina" })) };
    else if (path === "space") json = { id: "fixture-space", name: "Colmado La Esquina" };
    else if (path === "workspace") json = await source.workspace();
    else if (path === "overview") json = await source.overview("2026-10-01", "2026-10-31");
    else if (path === "receipts") json = await source.receiptPage!("inbox");
    else if (path === "access") json = { grants: [], invites: [] };
    else if (path === "receipt-reading") json = { enabled: true, available: true, can_change: false };
    else if (path === "email") json = { enabled: true, receiving_address: "recibos@example.test" };
    else if (["email/deliveries", "captures", "updates", "expenses"].includes(path)) json = { items: [] };
    else return route.fulfill({ status: 404, json: { code: "fixture_only" } });
    return route.fulfill({ json });
  });
  await page.goto("/biz");
  await page.addStyleTag({ content: "nextjs-portal { display: none !important; }" });
  await expect(page.getByTestId("workspace-panel-region")).toBeVisible();
}
async function capture(page: Page, name: string) {
  if (evidence) await page.screenshot({ path: `${evidence}/${baseline ? "before" : "after"}-${name}.png`, fullPage: true, animations: "disabled" });
}
for (const theme of ["light", "dark"] as const) {
  test(`sidebar order, targets and working destinations in ${theme}`, async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await setup(page, 2, theme);
    await expect(page.getByTestId("business-switcher")).toContainText(baseline ? "Colmado La Esquina" : "CE");
    await capture(page, `expanded-${theme}`);
    if (baseline) return;
    const sidebar = page.locator("aside");
    const nav = page.getByTestId("business-sidebar-nav");
    await expect(nav.getByRole("button")).toHaveText([/Inicio/, /Bandeja/, /Recibos/, /Notificaciones/]);
    expect((await nav.boundingBox())!.y).toBeLessThan(180);
    const icons = await sidebar.locator("button > div > svg, button > svg").evaluateAll((nodes) => nodes.map((node) => ({ cls: node.getAttribute("class"), width: node.getBoundingClientRect().width, stroke: node.getAttribute("stroke-width") })));
    const navIcons = icons.filter((icon) => /lucide-(search|house|inbox|receipt-text|bell)/.test(icon.cls ?? ""));
    expect(navIcons).toHaveLength(5);
    expect(new Set(navIcons.map((icon) => icon.cls)).size).toBe(5);
    for (const icon of navIcons) { expect(icon.width).toBe(20); expect(icon.stroke).toBe("2"); }
    const business = page.getByTestId("business-mark-trigger");
    const person = page.getByTestId("sidebar-person-trigger");
    for (const target of [business, person]) { const box = (await target.boundingBox())!; expect(box.width).toBeGreaterThanOrEqual(44); expect(box.height).toBeGreaterThanOrEqual(44); }
    expect((await business.boundingBox())!.y).toBeGreaterThan(700);
    await person.click();
    await expect(page.locator("[data-profile-menu-surface]")).toBeVisible();
    await page.keyboard.press("Escape");
    await business.click();
    await expect(page.getByRole("menuitem", { name: "Equipo y accesos" })).toBeFocused();
    await capture(page, `business-menu-${theme}`);
    await page.getByRole("menuitem", { name: "Cambiar de negocio" }).click();
    await expect(page.getByRole("option")).toHaveText([/Colmado La Esquina/, /Panadería Sol/]);
    await page.keyboard.press("End");
    await page.keyboard.press("Enter");
    await business.click();
    await expect(page.getByTestId("business-current-name")).toHaveText("Panadería Sol");
    await page.keyboard.press("Escape");
    await expect(business).toBeFocused();
    await business.click();
    await page.getByRole("menuitem", { name: "Equipo y accesos" }).click();
    await expect(page).toHaveURL(/view=access/);
    for (const [name, view] of [["Inicio", "overview"], ["Bandeja", "inbox"], ["Recibos", "expenses"], ["Notificaciones", "updates"]]) {
      await nav.getByRole("button", { name: new RegExp(name) }).click();
      await expect(page).toHaveURL(view === "overview" ? /\/biz$/ : new RegExp(`view=${view}`));
      await expect(page.getByTestId("workspace-panel-region")).toBeVisible();
    }
    await sidebar.getByRole("button", { name: /^Buscar/ }).click();
    await expect(page.getByRole("textbox", { name: "Buscar gastos y recibos" })).toBeFocused();
  });
}
test("one business has access but no switch action; collapse persists per person", async ({ page }) => {
  test.skip(baseline);
  await page.setViewportSize({ width: 1280, height: 900 });
  await setup(page, 1);
  await page.getByTestId("business-mark-trigger").click();
  await expect(page.getByRole("menuitem", { name: "Cambiar de negocio" })).toHaveCount(0);
  await expect(page.getByRole("menuitem", { name: "Equipo y accesos" })).toBeVisible();
  await page.keyboard.press("Escape");
  await page.locator("aside").getByRole("button", { name: "Contraer", exact: true }).click();
  await expect(page.locator("aside")).toHaveCSS("width", "56px");
  await expect(page.getByTestId("business-inbox-count")).toHaveText("5");
  await capture(page, "collapsed");
  await page.reload();
  await expect(page.locator("aside")).toHaveCSS("width", "56px");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(page.getByTestId("business-sidebar-nav").getByRole("button").first()).toHaveCSS("transition-duration", "0s");
});

for (const theme of ["light", "dark"] as const) {
  test(`phone drawer keeps both identity targets and working menus in ${theme}`, async ({ page }) => {
    test.skip(baseline);
    await page.setViewportSize({ width: 390, height: 844 });
    await setup(page, 2, theme);
    await page.getByTestId("chat-shell-menu-trigger").click();
    const drawer = page.getByTestId("sidebar-drawer");
    await expect(drawer).toBeVisible();
    await capture(page, `phone-drawer-${theme}`);
    const business = drawer.getByTestId("business-mark-trigger");
    const person = drawer.getByTestId("sidebar-person-trigger");
    for (const target of [business, person]) { const box = (await target.boundingBox())!; expect(box.width).toBeCloseTo(44, 2); expect(box.height).toBeCloseTo(44, 2); }
    await business.click();
    await expect(page.getByRole("menuitem", { name: "Equipo y accesos" })).toBeFocused();
    await capture(page, `phone-menu-${theme}`);
    await page.keyboard.press("Escape");
    await expect(drawer).toBeVisible();
    await expect(business).toBeFocused();
    await person.click();
    await expect(page.locator("[data-profile-menu-surface]")).toBeVisible();
    await page.keyboard.press("Escape");
    await business.click();
    await page.getByRole("menuitem", { name: "Equipo y accesos" }).click();
    await expect(page).toHaveURL(/view=access/);
    await expect(drawer).toHaveCount(0);
  });
}
