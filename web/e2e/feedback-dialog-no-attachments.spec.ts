import { mkdir } from "node:fs/promises";
import { join } from "node:path";

import { expect, test, type Page } from "@playwright/test";

import en from "../public/locales/en/common.json";
import { FREEZE_CSS, installBreakpointFixture } from "./support/breakpoint-fixture";
import { openSettings } from "./support/menu-settings-fixture";

/**
 * Opens the written feedback dialog the same way a registered user does from
 * Settings, then records the panel. FEEDBACK_DIALOG_SHOT_DIR keeps screenshots
 * for the #675 before/after evidence.
 *
 * Account and catalog reads come from the shared breakpoint fixture. This
 * spec only owns the feedback POST, which that fixture does not.
 */
async function openGeneralFeedback(page: Page) {
  await installBreakpointFixture(page, {
    account: "registered",
    language: "en",
    theme: "light",
    emptyChat: true,
  });
  await page.route("**/api/v1/feedback", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ success: true }),
    });
  });
  await page.goto("/chat?conversation=conversation-alpha", {
    waitUntil: "networkidle",
  });
  await expect(page.getByTestId("chat-input")).toBeVisible({ timeout: 15_000 });
  await page.addStyleTag({ content: FREEZE_CSS });
  await openSettings(page, {
    width: 1280,
    account: "registered",
    language: "en",
    theme: "light",
  });
  await page.getByRole("button", { name: en.feedback.eyebrow, exact: true }).click();
  await page
    .getByRole("button", { name: en.feedback.type.general, exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: en.feedback.title });
  await expect(dialog).toBeVisible();
  return dialog;
}

async function capture(page: Page, name: string) {
  const dir = process.env.FEEDBACK_DIALOG_SHOT_DIR;
  if (!dir) return;
  await mkdir(dir, { recursive: true });
  await page.addStyleTag({
    content:
      "nextjs-portal, [data-dev-mode-badge] { display: none !important; }",
  });
  await page.screenshot({
    path: join(dir, `${name}.png`),
    animations: "disabled",
  });
}

test("opens the written feedback dialog without an attachment picker", async ({
  page,
}) => {
  const dialog = await openGeneralFeedback(page);
  await expect(dialog.getByPlaceholder(en.feedback.details_placeholder)).toBeVisible();
  await expect(dialog.locator('input[type="file"]')).toHaveCount(0);
  await capture(page, "feedback-dialog-en");

  await dialog.getByPlaceholder(en.feedback.details_placeholder).fill(
    "The chat stayed clear.",
  );
  const posted = page.waitForRequest(
    (request) =>
      request.method() === "POST" &&
      new URL(request.url()).pathname.endsWith("/api/v1/feedback"),
  );
  await dialog.getByRole("button", { name: en.feedback.submit }).click();
  const payload = (await posted).postDataJSON() as {
    type: string;
    message: string;
    context?: Record<string, unknown>;
  };
  expect(payload.type).toBe("general");
  expect(payload.message).toBe("The chat stayed clear.");
  expect(payload.context).toEqual({
    surface: "sidebar",
    tags: [],
  });
  expect(payload.context).not.toHaveProperty("hasAttachments");
  expect(payload.context).not.toHaveProperty("attachmentCount");
  await expect(dialog.getByText(en.feedback.success_detail)).toBeVisible();
});
