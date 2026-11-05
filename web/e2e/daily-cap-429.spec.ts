import { expect, test, type Page } from "@playwright/test";
import en from "../public/locales/en/common.json";
import es from "../public/locales/es-419/common.json";
import {
  COPY,
  MIDNIGHT_RETRY_AFTER,
  RAW_SERVER_DETAIL,
  RECEIVED_AT,
  VIEWPORTS,
  captureEvidence,
  installComputeLimitJourney,
  sendQuestion,
  submitQuestion,
} from "./fixtures/compute-limit-journey";

test.use({ timezoneId: "America/Santo_Domingo" });

async function expectDailyCapNotice(page: Page, language: keyof typeof COPY) {
  const notice = page.getByTestId("daily-cap-notice");
  await expect(notice).toHaveCount(1);
  await expect(notice).toBeVisible();
  await expect(notice).toHaveAttribute("role", "status");
  await expect(notice.getByText(COPY[language].capError, { exact: true })).toBeVisible();

  const message = page.locator("[data-message-id]").filter({ has: notice });
  await expect(message).toHaveCount(0);
  const copy = language === "en" ? en : es;
  await expect(notice.getByRole("button", { name: copy.common.close, exact: true })).toHaveCount(1);
  await expect(notice.getByRole("button", { includeHidden: true })).toHaveCount(1);
  await expect(page.getByTestId("conversation-transcript-region").getByText(COPY[language].capError, { exact: true })).toHaveCount(0);
  const composer = page.getByTestId("chat-input");
  await expect(composer).toBeEnabled();
  await expect.poll(async () => {
    const noticeBox = await notice.boundingBox();
    const composerBox = await composer.boundingBox();
    return Boolean(noticeBox && composerBox && noticeBox.y + noticeBox.height <= composerBox.y);
  }).toBe(true);
}

for (const language of ["en", "es-419"] as const) {
  for (const viewport of VIEWPORTS) {
    for (const account of ["guest", "registered"] as const) {
      for (const header of ["midnight", "missing"] as const) {
        test(`daily cap states the local reset: ${account}, ${language}, ${viewport.name}, ${header} header`, async ({ page }) => {
          await page.setViewportSize(viewport);
          const evidence = await installComputeLimitJourney(page, {
            account, language, status: 429,
            retryAfter: header === "midnight" ? MIDNIGHT_RETRY_AFTER : undefined,
          });
          await sendQuestion(page, language);
          const copy = COPY[language];
          await expectDailyCapNotice(page, language);
          await expect(page.getByText(copy.prompt, { exact: true })).toHaveCount(1);
          await expect(page.locator("[data-message-id]")).toHaveCount(evidence.persistedMessageCount + 1);
          await expect(page.getByText(RAW_SERVER_DETAIL, { exact: true })).toHaveCount(0);
          await expect(page.getByText(/wait a moment|espera un momento/i)).toHaveCount(0);
          await expect(page.getByRole("button", { name: copy.retrySoon })).toHaveCount(0);
          expect(evidence.streamStatuses).toEqual([429]);
          if (viewport.name === "mobile") {
            await expect.poll(async () => {
              const question = await page.getByText(copy.prompt, { exact: true }).boundingBox();
              const notice = await page.getByTestId("daily-cap-notice").boundingBox();
              return Boolean(question && notice && question.y + question.height <= notice.y);
            }).toBe(true);
          }
          if (header === "midnight") {
            await captureEvidence(page, `${account}-429-${language}-${viewport.name}`);
          }
        });
      }
    }
  }
}

test("a new chat keeps the rejected question and its daily reset notice", async ({ page }) => {
  const evidence = await installComputeLimitJourney(page, {
    account: "registered", language: "en", status: 429,
    retryAfter: MIDNIGHT_RETRY_AFTER, newConversation: true,
  });
  await sendQuestion(page, "en", true);
  await expectDailyCapNotice(page, "en");
  await expect(page.getByText(COPY.en.prompt, { exact: true })).toHaveCount(1);
  await expect(page.locator("[data-message-id]")).toHaveCount(evidence.persistedMessageCount + 1);
  expect(evidence.streamStatuses).toEqual([429]);
});

test("the first guest question can show its account notice after bootstrap", async ({ page }) => {
  const evidence = await installComputeLimitJourney(page, {
    account: "guest", language: "es-419", status: 429,
    retryAfter: MIDNIGHT_RETRY_AFTER, newConversation: true, bootstrapGuest: true,
  });
  await sendQuestion(page, "es-419", true);
  await expectDailyCapNotice(page, "es-419");
  await expect(page.getByText(COPY["es-419"].prompt, { exact: true })).toHaveCount(1);
  await expect(page.locator("[data-message-id]")).toHaveCount(evidence.persistedMessageCount + 1);
  expect(evidence.guestBootstraps).toBe(1);
  expect(evidence.streamStatuses).toEqual([429]);
  await page.reload({ waitUntil: "networkidle" });
  await expectDailyCapNotice(page, "es-419");
  expect(evidence.guestBootstraps).toBe(1);
});

async function cappedAccount(page: Page, options: { failures?: number; controlClock?: boolean; holdSuccess?: boolean } = {}) {
  return installComputeLimitJourney(page, {
    account: "registered", language: "en", status: 429,
    retryAfter: MIDNIGHT_RETRY_AFTER, ...options,
  });
}

test("repeated daily caps keep one composer notice and never retry automatically", async ({ page }) => {
  const evidence = await cappedAccount(page, { failures: 2, controlClock: true });
  await sendQuestion(page, "en");
  await expectDailyCapNotice(page, "en");
  await submitQuestion(page, "en");
  await expect.poll(() => evidence.streamStatuses).toEqual([429, 429]);
  await expectDailyCapNotice(page, "en");
  await expect(page.locator("[data-message-id]")).toHaveCount(evidence.persistedMessageCount + 2);
  await page.clock.fastForward(60_000);
  await expectDailyCapNotice(page, "en");
  expect(evidence.streamStatuses).toEqual([429, 429]);
});

test("the same account keeps its notice after reload and New chat navigation", async ({ page }) => {
  const evidence = await cappedAccount(page);
  await sendQuestion(page, "en");
  await expectDailyCapNotice(page, "en");
  await page.reload({ waitUntil: "networkidle" });
  await expectDailyCapNotice(page, "en");
  await page.getByRole("button", { name: en.chat.new_chat, exact: true }).click();
  await expectDailyCapNotice(page, "en");
  expect(evidence.streamStatuses).toEqual([429]);
});

test("dismissal survives reload and the next rejection shows the notice again", async ({ page }) => {
  const evidence = await cappedAccount(page, { failures: 2 });
  await sendQuestion(page, "en");
  await expectDailyCapNotice(page, "en");
  await page.getByTestId("daily-cap-notice").getByRole("button", { name: en.common.close, exact: true }).click();
  await expect(page.getByTestId("daily-cap-notice")).toHaveCount(0);
  await page.reload({ waitUntil: "networkidle" });
  await expect(page.getByTestId("chat-input")).toBeEnabled();
  await expect(page.getByTestId("daily-cap-notice")).toHaveCount(0);
  await submitQuestion(page, "en");
  await expectDailyCapNotice(page, "en");
  expect(evidence.streamStatuses).toEqual([429, 429]);
});

for (const wake of ["timer", "focus"] as const) {
  test(`the daily-cap notice expires at reset via ${wake}`, async ({ page }) => {
    const evidence = await cappedAccount(page, { controlClock: true });
    await sendQuestion(page, "en");
    await expectDailyCapNotice(page, "en");
    const untilAfterReset = Number(MIDNIGHT_RETRY_AFTER) * 1_000 + 1_000;
    if (wake === "timer") {
      await page.clock.fastForward(untilAfterReset);
    } else {
      // Move wall time without firing the expiry timer, then resume the tab.
      await page.clock.setSystemTime(new Date(RECEIVED_AT.getTime() + untilAfterReset));
      await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    }
    await expect(page.getByTestId("daily-cap-notice")).toHaveCount(0);
    await expect(page.getByTestId("chat-input")).toBeEnabled();
    expect(evidence.streamStatuses).toEqual([429]);
  });
}

test("an accepted manual question clears the notice across reload", async ({ page }) => {
  const evidence = await cappedAccount(page);
  await sendQuestion(page, "en");
  await expectDailyCapNotice(page, "en");
  await submitQuestion(page, "en");
  await expect(page.getByText(COPY.en.success, { exact: true })).toBeVisible();
  await expect(page.getByTestId("daily-cap-notice")).toHaveCount(0);
  expect(evidence.streamStatuses).toEqual([429, 200]);
  await page.reload({ waitUntil: "networkidle" });
  await expect(page.getByTestId("chat-input")).toBeEnabled();
  await expect(page.getByTestId("daily-cap-notice")).toHaveCount(0);
});

test("a successful admitted structured action clears the daily question notice", async ({ page }) => {
  const evidence = await installComputeLimitJourney(page, {
    account: "registered", language: "en", status: 429,
    retryAfter: MIDNIGHT_RETRY_AFTER, withResponseOption: true,
  });
  await sendQuestion(page, "en");
  await expectDailyCapNotice(page, "en");
  await page.getByRole("button", { name: en.chat.coverage_recovery.actions.change_dates, exact: true }).click();
  await expect(page.getByText(COPY.en.success, { exact: true })).toBeVisible();
  expect(evidence.streamStatuses).toEqual([429, 200]);
  expect(evidence.sentActionTypes).toEqual([null, "select_response_option"]);
  await expect(page.getByTestId("daily-cap-notice")).toHaveCount(0);
  await page.reload({ waitUntil: "networkidle" });
  await expect(page.getByTestId("chat-input")).toBeEnabled();
  await expect(page.getByTestId("daily-cap-notice")).toHaveCount(0);
});

test("a successful cancellation retains the daily question notice", async ({ page }) => {
  const evidence = await installComputeLimitJourney(page, {
    account: "registered", language: "en", status: 429,
    retryAfter: MIDNIGHT_RETRY_AFTER, withConfirmationHistory: true,
  });
  await sendQuestion(page, "en");
  await expectDailyCapNotice(page, "en");
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.getByText(en.chat.confirmation.status.draft_canceled, { exact: true })).toBeVisible();
  expect(evidence.streamStatuses).toEqual([429, 200]);
  expect(evidence.sentActionTypes).toEqual([null, "cancel_confirmation"]);
  await expectDailyCapNotice(page, "en");
  await page.reload({ waitUntil: "networkidle" });
  await expectDailyCapNotice(page, "en");
});

test("an accepted response clears the account notice after navigating to New chat", async ({ page }) => {
  const evidence = await cappedAccount(page, { holdSuccess: true });
  await sendQuestion(page, "en");
  await expectDailyCapNotice(page, "en");
  await submitQuestion(page, "en");
  await expect.poll(() => evidence.streamStatuses).toEqual([429, 200]);
  await page.getByRole("button", { name: en.chat.new_chat, exact: true }).click();
  await expect(page.getByText(COPY.en.prompt, { exact: true })).toHaveCount(0);
  await expectDailyCapNotice(page, "en");
  evidence.releaseSuccess();
  await expect(page.getByTestId("daily-cap-notice")).toHaveCount(0);
  await expect(page.getByTestId("chat-input")).toBeEnabled();
  expect(evidence.streamStatuses).toEqual([429, 200]);
});

test("a different account never inherits the previous account's notice", async ({ page }) => {
  const evidence = await cappedAccount(page);
  const profileResponse = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/v1/me");
  await sendQuestion(page, "en");
  await expectDailyCapNotice(page, "en");
  // Derive the second account from the existing mocked profile, without a second fixture.
  const profile = await (await profileResponse).json();
  await page.route("**/api/v1/me", (route) => route.fulfill({
    json: { ...profile, user: { ...profile.user, id: "another-registered-account" } },
  }));
  await page.reload({ waitUntil: "networkidle" });
  await expect(page.getByTestId("chat-input")).toBeEnabled();
  await expect(page.getByTestId("daily-cap-notice")).toHaveCount(0);
  expect(evidence.streamStatuses).toEqual([429]);
});
