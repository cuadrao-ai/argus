import { expect, test, type Page } from "@playwright/test";
import { installBreakpointFixture } from "./support/breakpoint-fixture";
import { dossierFixtureIds } from "../components/business-app/dossier-fixtures";
async function setup(page: Page, width = 1280, language: "en" | "es-419" = "es-419") {
  await page.setViewportSize({ width, height: 900 });
  page.on("pageerror", (error) => { throw error; });
  await page.addInitScript(() => { const style = document.createElement("style"); style.textContent = "nextjs-portal { display: none !important; }"; document.addEventListener("DOMContentLoaded", () => document.head.appendChild(style)); });
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
  await installBreakpointFixture(page, { language, theme: "light", emptyChat: true });
}
async function chord(page: Page, suffix: string) {
  const command = await page.evaluate(() => /Mac|iPhone|iPad|iPod/.test(navigator.userAgent));
  await page.keyboard.press(`${command ? "Meta" : "Control"}+${suffix}`);
}
async function screenshot(page: Page, name: string) {
  const dir = process.env.CUADRAO_NAV_EVIDENCE_DIR;
  if (dir) await page.screenshot({ path: `${dir}/${test.info().project.name}-${name}.png` });
}
test("desktop navigation, searchable platform sheet, strict input and overlay blocking", async ({ page }) => {
  await setup(page);
  await page.goto("/dev/business-preview?chat=off");
  await expect(page.getByTestId("business-sidebar-nav")).toBeVisible();
  await expect(page.getByTestId("business-sidebar-nav").getByRole("button")).toHaveCount(4);
  await expect(page.getByRole("button", { name: "Recientes", exact: true })).toHaveCount(0);
  await expect(page.getByTestId("overview-real-expenses")).toBeVisible();
  await screenshot(page, "after-navigation-1280");
  await chord(page, "Slash");
  const sheet = page.getByRole("dialog", { name: "Atajos de teclado", exact: true });
  await expect(sheet).toBeVisible();
  await expect(sheet.locator('[data-workspace-shortcut="approve"]')).toContainText("Aprobar");
  await expect(sheet).not.toContainText("Argus");
  await expect(sheet).not.toContainText("Recientes");
  await screenshot(page, "after-shortcuts-1280");
  await sheet.getByRole("searchbox").fill("Aprobar");
  await expect(sheet.locator("[data-workspace-shortcut]")).toHaveCount(2);
  await sheet.getByRole("searchbox").fill("Enter");
  await expect(sheet.locator("[data-workspace-shortcut]")).toHaveCount(1);
  await chord(page, "Shift+KeyS");
  await expect(sheet).toBeVisible();
  await chord(page, "KeyK");
  await expect(page.getByRole("dialog")).toHaveCount(1);
  await page.keyboard.press("Escape");
  await expect(sheet).toHaveCount(0);
  await chord(page, "KeyK");
  await expect(page.getByRole("button", { name: "Cerrar búsqueda", exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  const command = await page.evaluate(() => /Mac/.test(navigator.userAgent));
  for (const [index, view] of ["overview", "inbox", "expenses", "updates"].entries()) {
    await chord(page, `${command ? "Alt" : "Shift"}+Digit${index + 1}`);
    await expect(page.getByTestId("business-sidebar-nav").getByRole("button").nth(index)).toHaveAttribute("aria-current", "page");
    if (view !== "overview") await expect(page).toHaveURL(new RegExp(`view=${view}`));
  }
  await chord(page, "Shift+Period");
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await chord(page, "Shift+Semicolon");
  await expect(page.getByRole("button", { name: "Perfil", exact: true })).toBeVisible();
  await chord(page, command ? "Alt+Digit1" : "Shift+Digit1");
  await expect(page).toHaveURL(/view=updates/);
  await page.keyboard.press("Escape");
  await chord(page, "Shift+Backslash");
  await page.getByTestId("business-sidebar-nav").getByRole("button", { name: "Gastos", exact: true }).focus();
  await expect(page.getByRole("tooltip", { name: /^Gastos ·/ })).toBeVisible();
  await screenshot(page, "after-collapsed-focus-1280");
  await page.keyboard.press("?");
  await expect(sheet).toHaveCount(0);
});
test("phone tabs have 44px targets and the approval footer stays above them", async ({ page }) => {
  await setup(page, 390);
  await page.goto(`/dev/business-preview?chat=off&draft=${dossierFixtureIds.ready}`);
  const tabs = page.getByTestId("business-bottom-tabs");
  await expect(tabs).toBeVisible();
  const footer = page.getByTestId("receipt-review-footer");
  await expect(footer).toBeVisible();
  await footer.scrollIntoViewIfNeeded();
  const tabBox = (await tabs.boundingBox())!;
  const footerBox = (await footer.boundingBox())!;
  expect(footerBox.y + footerBox.height).toBeLessThanOrEqual(tabBox.y + 1);
  for (const button of await tabs.getByRole("button").all()) {
    const box = (await button.boundingBox())!;
    expect(box.width).toBeGreaterThanOrEqual(44);
    expect(box.height).toBeGreaterThanOrEqual(44);
  }
  await screenshot(page, "after-review-390");
  await chord(page, "Slash");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await tabs.getByRole("button", { name: "Resumen", exact: true }).click();
  await expect(page).not.toHaveURL(/draft=/);
  await screenshot(page, "after-navigation-390");
});
test("review keys approve through existing revision action; edit keys focus fields; read-only does nothing", async ({ page }) => {
  await setup(page);
  await page.goto(`/dev/business-preview?chat=off&draft=${dossierFixtureIds.ready}`);
  await expect(page.getByRole("button", { name: "Aprobar", exact: true })).toBeEnabled();
  await chord(page, "Shift+KeyE");
  await expect(page.locator('[data-testid^="edit-"] input, [data-testid^="edit-"] select').first()).toBeFocused();
  await chord(page, "Shift+Enter");
  await expect(page.getByRole("button", { name: "Aprobar", exact: true })).toBeVisible();
  await page.getByRole("heading", { name: "Ferretería La Esquina", exact: true }).focus();
  await chord(page, "Shift+Enter");
  await expect(page.getByText(/Se registró un gasto/)).toBeVisible();
  await page.goto(`/dev/business-preview?chat=off&draft=${dossierFixtureIds.readOnly}`);
  await expect(page.getByTestId("receipt-current-facts")).toBeVisible();
  await chord(page, "Shift+Enter");
  await chord(page, "Shift+KeyE");
  await expect(page.locator('[data-testid^="edit-"]')).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Aprobar", exact: true })).toHaveCount(0);
});
test("previous/next preserve inbox order and approve-next records before moving", async ({ page }) => {
  await setup(page);
  await page.goto("/dev/business-preview?chat=off&view=inbox");
  await page.getByTestId("business-inbox-receipts").getByRole("button", { name: /Ferretería La Esquina/ }).click();
  await expect(page.getByLabel("Pagado desde")).toBeVisible();
  await page.getByRole("heading", { name: "Revisar recibo", exact: true }).focus();
  await chord(page, "Shift+ArrowDown");
  await expect(page).toHaveURL(/receipt=rcpt-papeleria/);
  await page.getByRole("heading", { name: "Revisar recibo", exact: true }).focus();
  await chord(page, "Shift+ArrowUp");
  await expect(page).toHaveURL(/receipt=rcpt-ferreteria/);
  await page.getByLabel("Pagado desde").selectOption({ index: 1 });
  await page.getByRole("button", { name: "Guardar detalles de revisión", exact: true }).click();
  await expect(page.getByRole("button", { name: "Aprobar y siguiente", exact: true })).toBeEnabled();
  await page.getByRole("heading", { name: "Ferretería La Esquina", exact: true }).focus();
  await chord(page, "Shift+KeyS");
  await expect(page).toHaveURL(/receipt=rcpt-papeleria/);
  await expect(page.getByRole("heading", { name: "Revisar recibo", exact: true })).toBeFocused();
});

test("reserved, repeated, composing, and editable keys leave Business actions alone", async ({ page }) => {
  await setup(page);
  await page.goto(`/dev/business-preview?chat=off&draft=${dossierFixtureIds.ready}`);
  await expect(page.getByRole("button", { name: "Aprobar", exact: true })).toBeEnabled();
  const results = await page.evaluate(() => {
    const command = /Mac|iPhone|iPad|iPod/.test(navigator.userAgent);
    const primary = command ? { metaKey: true } : { ctrlKey: true };
    const probe = (code: string, extra: KeyboardEventInit = {}, target: EventTarget = document) => {
      const event = new KeyboardEvent("keydown", { bubbles: true, cancelable: true, ...primary, shiftKey: true, key: code, code, ...extra });
      target.dispatchEvent(event);
      return event.defaultPrevented;
    };
    const results = [
      probe("Enter", { repeat: true }), probe("Enter", { isComposing: true }),
      probe("Enter", { altKey: true }), probe("Enter", { ctrlKey: true, metaKey: true }),
      probe("Enter", { shiftKey: false }), probe("Slash", { ctrlKey: false, metaKey: false, shiftKey: false, key: "?" }),
      ...["KeyW", "KeyR", "KeyL", "ArrowLeft", "ArrowRight", "Tab"].map((code) => probe(code, { shiftKey: false })),
    ];
    for (const tag of ["input", "textarea", "select", "div"]) {
      const target = document.createElement(tag);
      if (tag === "div") target.contentEditable = "true";
      document.body.appendChild(target);
      target.focus();
      results.push(probe("Enter", {}, target));
      target.remove();
    }
    return results;
  });
  expect(results).toEqual(Array(results.length).fill(false));
  await expect(page.getByRole("button", { name: "Aprobar", exact: true })).toBeEnabled();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("English Business uses existing labels without chat-only actions", async ({ page }) => {
  await setup(page, 1280, "en");
  await page.goto("/dev/business-preview?chat=off");
  await expect(page.getByTestId("business-sidebar-nav")).toBeVisible();
  await chord(page, "Slash");
  const sheet = page.getByRole("dialog", { name: "Keyboard shortcuts", exact: true });
  await expect(sheet).toBeVisible();
  await expect(sheet).not.toContainText("Recents");
  await expect(sheet).not.toContainText("Argus");
  await expect(sheet.locator('[data-workspace-shortcut="sidebar"]')).toContainText("Sidebar");
  await sheet.getByRole("searchbox").fill("Approve");
  await expect(sheet.locator("[data-workspace-shortcut]")).toHaveCount(2);
});
