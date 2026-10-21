import { expect, test, type Page } from "@playwright/test";
import { installBreakpointFixture } from "./support/breakpoint-fixture";

// The eight founder test flows on the sample-data preview, recorded on video.
const PREVIEW = "/dev/business-preview";

test.use({ video: "on", launchOptions: { slowMo: 120 } });

async function openPreview(page: Page, url = PREVIEW, language: "en" | "es-419" = "en") {
  await page.route("**/*", (route) => {
    const { hostname } = new URL(route.request().url());
    return ["127.0.0.1", "localhost"].includes(hostname)
      ? route.continue()
      : route.abort("blockedbyclient");
  });
  await installBreakpointFixture(page, { language, theme: "light", emptyChat: true });
  await page.addInitScript(() => window.localStorage.setItem("argus:sidebar_mode", "expanded"));
  await page.goto(url);
}

const nav = (page: Page) => page.getByTestId("business-sidebar-nav");
const panel = (page: Page) => page.getByTestId("workspace-panel-region");
const heading = (page: Page, name: string) => panel(page).getByRole("heading", { name, exact: true });

const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);

async function chooseFile(page: Page, name: string, mimeType: string, buffer: Buffer) {
  await page.locator('input[type="file"]').first().setInputFiles({ name, mimeType, buffer });
}

test.describe("Business pilot walkthrough", () => {
  test.use({
    viewport: { width: 1280, height: 800 },
  });

  test("1 upload a receipt: rejections, then save with AI consent", async ({ page }) => {
    await openPreview(page);
    await page.getByTestId("business-create").click();
    await page.getByRole("menuitem", { name: "Upload receipt" }).click();
    const dialog = page.getByRole("dialog", { name: "Upload receipt" });
    await expect(dialog).toContainText("PDF, JPG or PNG, up to 10 MB");

    await chooseFile(page, "notes.txt", "text/plain", Buffer.from("hello"));
    await expect(dialog).toContainText("This file type isn't supported");
    await chooseFile(page, "IMG_0001.HEIC", "image/heic", PNG);
    await expect(dialog).toContainText("iPhone HEIC photo");
    await chooseFile(page, "huge.pdf", "application/pdf", Buffer.alloc(11 * 1024 * 1024, 1));
    await expect(dialog).toContainText("larger than 10 MB");

    await chooseFile(page, "ferreteria.png", "image/png", PNG);
    await expect(dialog).toContainText("ferreteria.png");
    await dialog.getByRole("checkbox").check();
    await dialog.getByRole("button", { name: "Save to Inbox" }).click();
    await expect(heading(page, "Review receipt")).toBeVisible();
    await expect(panel(page)).toContainText("Waiting to prepare");
  });

  test("2 legacy review stays bounded and receipt entry requires separate human approval", async ({ page }) => {
    await openPreview(page, `${PREVIEW}?view=inbox`);
    await panel(page).getByRole("button", { name: /Papelería Central/ }).click();
    await page.getByLabel(/Paid from/).selectOption({ label: "Tarjeta del negocio · USD" });
    await page.getByRole("button", { name: "Save review details" }).click();
    await expect(panel(page).getByRole("alert")).toBeVisible();
    await expect(page.getByRole("button", { name: "Approve expense", exact: true })).toHaveCount(0);

    await nav(page).getByRole("button", { name: /^Inbox/ }).click();
    await panel(page).getByRole("button", { name: /Ferretería La Esquina/ }).click();
    await page.getByLabel(/Paid from/).selectOption({ label: "Cuenta corriente · DOP" });
    await page.getByRole("button", { name: "Save review details" }).click();
    await page.getByRole("button", { name: "Approve expense", exact: true }).click();
    await expect(panel(page)).toContainText("One expense was recorded after approval");
    await panel(page).getByRole("button", { name: "Expenses", exact: true }).click();
    await expect(heading(page, "Expenses")).toBeVisible();
    await expect(panel(page)).toContainText("Ferretería La Esquina");
  });

  test("3 an unprepared receipt asks for AI consent", async ({ page }) => {
    await openPreview(page, `${PREVIEW}?receipt=rcpt-saved`);
    await expect(panel(page)).toContainText("sent to our AI provider only if you choose this");
    await page.getByRole("button", { name: "Prepare with AI" }).click();
    await expect(panel(page)).toContainText("Reading your receipt");
  });

  test("4 a receipt that needs attention explains itself", async ({ page }) => {
    await openPreview(page);
    await panel(page).getByRole("button", { name: /need your attention/ }).click();
    await expect(heading(page, "Inbox")).toBeVisible();
    await panel(page).getByRole("button", { name: /IMG_2209/ }).click();
    await expect(panel(page)).toContainText("We couldn't read this file");
  });

  test("5 record an expense by hand with a guarded amount", async ({ page }) => {
    await openPreview(page);
    await page.getByTestId("business-create").click();
    await page.getByRole("menuitem", { name: "Record expense" }).click();
    await page.getByLabel("Merchant").fill("Imprenta Rápida");
    const total = page.getByTestId("record-expense-amount");
    await total.click();
    await page.keyboard.type("12x50.5");
    await expect(total).toHaveValue("1,250.5");
    await page.getByLabel("Merchant").click();
    await expect(total).toHaveValue("1,250.50");
    await page.getByRole("button", { name: "Save expense" }).click();
    await expect(heading(page, "Expenses")).toBeVisible();
    await expect(panel(page)).toContainText("Imprenta Rápida");
    await expect(panel(page)).toContainText("RD$ 1,250.50");
  });

  test("6 composer keeps its draft, attaches a receipt, New chat opens a chat", async ({ page }) => {
    await openPreview(page);
    await page.getByTestId("chat-input").click();
    await page.keyboard.type("What did I spend on paint?");
    await nav(page).getByRole("button", { name: /^Inbox/ }).click();
    await nav(page).getByRole("button", { name: /^Overview/ }).click();
    await expect(page.getByTestId("chat-input")).toHaveText("What did I spend on paint?");

    await page.getByTestId("business-composer-add").click();
    await page.getByRole("menuitem", { name: "Add a receipt" }).click();
    await chooseFile(page, "almuerzo.png", "image/png", PNG);
    await page.getByRole("button", { name: "Save to Inbox" }).click();
    await expect(page.getByTestId("composer-attached-receipt")).toContainText("Saved to Inbox");
    await expect(page.getByTestId("chat-input")).toHaveText("What did I spend on paint?");

    await page.getByRole("button", { name: /^New chat/ }).click();
    await expect(page.locator('[data-business-home="new_chat"]')).toBeVisible();
  });
});

test.describe("Business pilot walkthrough on a phone", () => {
  test.use({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  });

  test("7 phone: drawer, header Create and the upload sheet", async ({ page }) => {
    await openPreview(page);
    await page.getByTestId("chat-shell-menu-trigger").click();
    const drawerNav = page.getByTestId("business-sidebar-nav");
    // Five receipts wait in the sample Bandeja; the email itself is not one of them.
    await expect(drawerNav.getByRole("button", { name: /^Inbox/ })).toHaveText("Inbox5");
    await page.keyboard.press("Escape");
    await page.getByTestId("business-create-compact").click();
    await expect(page.getByRole("menuitem")).toHaveText(["Upload receipt", "Record expense", "Save a note"]);
    await page.getByRole("menuitem", { name: "Upload receipt" }).click();
    await expect(page.getByText("PDF, JPG, PNG, up to 10 MB", { exact: false })).toBeVisible();
  });

  test("8 Spanish: navigation, overview and receipt review", async ({ page }) => {
    await openPreview(page, PREVIEW, "es-419");
    await expect(heading(page, "Mi negocio")).toBeVisible();
    await page.getByTestId("chat-shell-menu-trigger").click();
    await expect(page.getByTestId("business-sidebar-nav")).toContainText("Bandeja");
    await page.getByTestId("business-sidebar-nav").getByRole("button", { name: /^Bandeja/ }).click();
    await panel(page).getByRole("button", { name: /Ferretería La Esquina/ }).click();
    await expect(heading(page, "Revisar recibo")).toBeVisible();
    await expect(panel(page)).toContainText("Pagado desde");
  });
});
