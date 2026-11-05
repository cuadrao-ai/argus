import { expect, test } from "@playwright/test";
import {
  COPY,
  RAW_SERVER_DETAIL,
  VIEWPORTS,
  captureEvidence,
  installComputeLimitJourney,
  sendQuestion,
} from "./fixtures/compute-limit-journey";

test.use({ timezoneId: "America/Santo_Domingo" });

for (const language of ["en", "es-419"] as const) {
  for (const viewport of VIEWPORTS) {
    test(`signed-in 503 preserves the turn through manual retries: ${language}, ${viewport.name}`, async ({ page }) => {
      await page.setViewportSize(viewport);
      const copy = COPY[language];
      const evidence = await installComputeLimitJourney(page, {
        account: "registered", language, status: 503, failures: 2, retryAfter: "3",
      });
      await sendQuestion(page, language);

      const notice = page.getByRole("status").filter({ hasText: copy.claimError });
      await expect(notice).toBeVisible();
      await expect(page.getByText(RAW_SERVER_DETAIL, { exact: true })).toHaveCount(0);
      await expect(page.getByText(copy.prompt, { exact: true })).toHaveCount(1);
      const retry = notice.getByRole("button");
      await expect(retry).toHaveCount(1);
      await expect(retry).toBeDisabled();
      await expect(retry).toHaveText(copy.retrySoon);
      await captureEvidence(page, `registered-503-${language}-${viewport.name}`);

      for (const attempt of [1, 2]) {
        await page.clock.fastForward(4_000);
        await expect(retry).toBeEnabled();
        await expect(retry).toHaveText(copy.retry);
        expect(evidence.streamStatuses).toEqual(Array(attempt).fill(503));
        await retry.click();
        if (attempt === 1) {
          await expect(retry).toBeDisabled();
          await expect(retry).toHaveText(copy.retrySoon);
          await expect(page.getByText(copy.prompt, { exact: true })).toHaveCount(1);
          await expect(page.getByText(RAW_SERVER_DETAIL, { exact: true })).toHaveCount(0);
          await captureEvidence(page, `registered-503-repeated-${language}-${viewport.name}`);
        }
      }

      await expect(page.getByText(copy.success, { exact: true })).toBeVisible();
      await expect(page.getByText(copy.prompt, { exact: true })).toHaveCount(1);
      await expect(notice).toHaveCount(0);
      expect(evidence.streamStatuses).toEqual([503, 503, 200]);
      expect(evidence.sentMessages).toEqual([copy.prompt, copy.prompt, copy.prompt]);
    });
  }
}

test("signed-in claim failure in a new chat keeps its prompt and uses the 15-second fallback", async ({ page }) => {
  const copy = COPY.en;
  const evidence = await installComputeLimitJourney(page, {
    account: "registered", language: "en", status: 503, newConversation: true,
  });
  await sendQuestion(page, "en", true);
  const notice = page.getByRole("status").filter({ hasText: copy.claimError });
  await expect(notice).toBeVisible();
  const retry = notice.getByRole("button");
  await expect(retry).toBeDisabled();
  await expect(page.getByText(copy.prompt, { exact: true })).toHaveCount(1);
  await page.clock.fastForward(10_000);
  await expect(retry).toBeDisabled();
  expect(evidence.streamStatuses).toEqual([503]);
  await page.clock.fastForward(6_000);
  await expect(retry).toBeEnabled();
  expect(evidence.streamStatuses).toEqual([503]);
  await retry.click();
  await expect(page.getByText(copy.success, { exact: true })).toBeVisible();
  expect(evidence.sentMessages).toEqual([copy.prompt, copy.prompt]);
});
