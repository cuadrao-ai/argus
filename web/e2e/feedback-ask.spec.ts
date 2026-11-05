import { mkdir } from "node:fs/promises";
import { join } from "node:path";

import { expect, test, type Page, type Route } from "@playwright/test";

import en from "../public/locales/en/common.json";
import es419 from "../public/locales/es-419/common.json";

/**
 * The feedback ask in a real browser, in both workspace languages: it asks
 * after a result, a tap saves a rating with the result's pointers and none of
 * the conversation's text, "tell us more" opens the existing dialog, and
 * closing the ask holds across a reload.
 *
 * FEEDBACK_ASK_LIVE_API=1 sends feedback to the real backend instead of a stub,
 * so the saves are the real endpoint's. FEEDBACK_ASK_EVIDENCE_DIR keeps
 * screenshots.
 */

type Language = "en" | "es-419";

const COPY = { en: en.feedback, "es-419": es419.feedback } as const;
const CONVERSATION_ID = "feedback-ask";
const RESULT_MESSAGE_ID = `${CONVERSATION_ID}-2`;
const NOW = "2026-09-11T12:00:00.000Z";
const RESULT_REGION = "Hero + Delta Evidence Card";

const RESULT_CARD = {
  title: "AAPL Buy and Hold",
  symbols: ["AAPL"],
  strategy_label: "Buy and Hold",
  asset_class: "equity",
  date_range: {
    start: "2025-09-01",
    end: "2026-09-01",
    display: "September 1, 2025 to September 1, 2026",
  },
  status_label: "Simulation Complete",
  rows: [
    { key: "cash_value", label: "Ending value", value: "$10,000 -> $12,500" },
    { key: "total_return_pct", label: "Total return", value: "+25.0%" },
    { key: "max_drawdown_pct", label: "Worst drop", value: "-8.2%" },
  ],
  assumptions: ["No fees", "No slippage"],
  actions: [],
  benchmark_note: "Universe: AAPL. Benchmark: SPY.",
  chart: null,
  evidence_artifact_id: `${CONVERSATION_ID}-evidence`,
};

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function transcript(language: Language) {
  return [
    {
      id: `${CONVERSATION_ID}-1`,
      conversation_id: CONVERSATION_ID,
      role: "user",
      content:
        language === "es-419"
          ? "Prueba comprar y mantener AAPL"
          : "Test buy and hold on AAPL",
      created_at: NOW,
      metadata: {},
    },
    {
      id: RESULT_MESSAGE_ID,
      conversation_id: CONVERSATION_ID,
      role: "assistant",
      content: "AAPL ended higher over the window.",
      created_at: NOW,
      metadata: {
        result_card: RESULT_CARD,
        result_run_id: `${CONVERSATION_ID}-run`,
        result_conversation_id: CONVERSATION_ID,
      },
    },
  ];
}

async function installFixture(page: Page, language: Language) {
  await page.addInitScript((lang) => {
    window.localStorage.setItem("i18nextLng", lang);
    window.localStorage.setItem("argus-theme", "light");
  }, language);

  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const method = route.request().method();

    if (url.pathname.endsWith("/api/v1/feedback") && method === "POST") {
      if (process.env.FEEDBACK_ASK_LIVE_API === "1") return route.continue();
      return json(route, { success: true });
    }

    if (url.pathname.endsWith("/api/v1/me")) {
      return json(route, {
        user: {
          id: "feedback-ask-user",
          email: "qa@example.com",
          username: "qa",
          display_name: "Feedback Ask QA",
          language,
          locale: language === "es-419" ? "es-419" : "en-US",
          onboarding: {
            completed: true,
            stage: "completed",
            language_confirmed: true,
            primary_goal: null,
          },
        },
        account_kind: "registered",
        guest: null,
        capabilities: {
          can_create_additional_conversation: true,
          can_manage_conversation: true,
          can_save_decision: true,
          can_manage_account: true,
          can_use_omnisearch: true,
          can_search_current_workspace: true,
          can_use_grounded_discovery: true,
          can_submit_feedback: true,
        },
        public_account_access_enabled: false,
      });
    }

    if (url.pathname.endsWith("/api/v1/conversations") && method === "GET") {
      return json(route, {
        items: [
          {
            id: CONVERSATION_ID,
            title: "Feedback ask",
            title_source: "user_renamed",
            pinned: false,
            archived: false,
            deleted_at: null,
            created_at: NOW,
            updated_at: NOW,
            last_message_preview: "AAPL buy and hold",
            language,
            activity: null,
          },
        ],
        next_cursor: null,
      });
    }

    if (url.pathname.endsWith(`/conversations/${CONVERSATION_ID}/messages`)) {
      return json(route, { items: transcript(language), next_cursor: null });
    }

    return json(route, {});
  });
}

async function capture(page: Page, name: string) {
  const dir = process.env.FEEDBACK_ASK_EVIDENCE_DIR;
  if (!dir) return;
  await mkdir(dir, { recursive: true });
  await page.addStyleTag({
    content:
      "nextjs-portal, [data-dev-mode-badge] { display: none !important; }",
  });
  await page.screenshot({ path: join(dir, `${name}.png`) });
}

async function openConversation(page: Page) {
  await page.goto(`/chat?conversation=${CONVERSATION_ID}`);
  await expect(page.getByRole("region", { name: RESULT_REGION })).toBeVisible();
}

async function reloadConversation(page: Page) {
  await page.reload();
  await expect(page.getByRole("region", { name: RESULT_REGION })).toBeVisible();
}

function feedbackPosted(page: Page) {
  return page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/feedback") &&
      response.request().method() === "POST",
  );
}

/** Pointers may travel; no message of the conversation, and no card text, ever does. */
function expectNoConversationText(body: unknown, language: Language) {
  const serialized = JSON.stringify(body);
  for (const message of transcript(language)) {
    expect(serialized).not.toContain(message.content);
  }
  expect(serialized).not.toContain(RESULT_CARD.title);
}

async function tapGoodAndOpenDialog(page: Page, language: Language) {
  const copy = COPY[language];
  const ask = page.getByTestId("feedback-ask");
  const tapSaved = feedbackPosted(page);
  await ask
    .getByRole("button", { name: copy.ask.answers.positive, exact: true })
    .click();
  const tap = await tapSaved;
  await ask.getByRole("button", { name: copy.ask.tell_more }).click();
  const dialog = page.getByRole("dialog", { name: copy.title });
  await expect(dialog).toBeVisible();
  return { tap, dialog };
}

for (const language of ["en", "es-419"] as const) {
  const copy = COPY[language];

  test(`${language}: asks after a result, saves a tap, and offers the dialog`, async ({
    page,
  }) => {
    await installFixture(page, language);
    await openConversation(page);

    const ask = page.getByTestId("feedback-ask");
    await expect(ask).toBeVisible();
    await expect(ask).toContainText(copy.ask.question);
    for (const rating of ["negative", "neutral", "positive"] as const) {
      await expect(
        ask.getByRole("button", { name: copy.ask.answers[rating], exact: true }),
      ).toBeVisible();
    }
    await capture(page, `${language}-1-ask-after-result`);

    const tapSaved = feedbackPosted(page);
    await ask
      .getByRole("button", { name: copy.ask.answers.positive, exact: true })
      .click();
    const tap = await tapSaved;
    expect(tap.status()).toBe(200);
    const rated = tap.request().postDataJSON();
    expect(rated.type).toBe("general");
    expect(rated.context).toMatchObject({
      source: "feedback_ask",
      surface: "chat",
      conversation_id: CONVERSATION_ID,
      message_id: RESULT_MESSAGE_ID,
      evidence_artifact_id: RESULT_CARD.evidence_artifact_id,
      rating: "positive",
      tags: [],
    });
    expect(rated.context).not.toHaveProperty("hasAttachments");
    expect(rated.context).not.toHaveProperty("attachmentCount");
    expectNoConversationText(rated, language);

    await expect(ask).toContainText(copy.ask.thanks);
    const tellUsMore = ask.getByRole("button", { name: copy.ask.tell_more });
    await expect(tellUsMore).toBeFocused();
    await capture(page, `${language}-2-tap-saved`);

    await tellUsMore.click();
    const dialog = page.getByRole("dialog", { name: copy.title });
    await expect(dialog).toBeVisible();
    const includeConversation = dialog.getByRole("checkbox", {
      name: copy.include_conversation_context,
    });
    await expect(includeConversation).toBeVisible();
    await expect(includeConversation).not.toBeChecked();
    await expect(ask).toHaveCount(0);
    await expect(dialog.locator('input[type="file"]')).toHaveCount(0);
    await capture(page, `${language}-3-tell-us-more-dialog`);

    // Unticked, the detail carries the ask's source and nothing that points at the conversation.
    await dialog.getByRole("textbox").fill(
      language === "es-419"
        ? "La tarjeta del resultado fue clara."
        : "The result card was clear.",
    );
    const detailSaved = feedbackPosted(page);
    await dialog.getByRole("button", { name: copy.submit }).click();
    const detail = await detailSaved;
    expect(detail.status()).toBe(200);
    expect(detail.request().postDataJSON().context).toEqual({
      source: "feedback_ask",
      surface: "chat",
      tags: [],
    });

    await reloadConversation(page);
    await expect(page.getByTestId("feedback-ask")).toHaveCount(0);
  });

  test(`${language}: the dialog attaches the result's pointers only when ticked`, async ({
    page,
  }) => {
    await installFixture(page, language);
    await openConversation(page);

    const { dialog } = await tapGoodAndOpenDialog(page, language);
    await dialog
      .getByRole("checkbox", { name: copy.include_conversation_context })
      .check();
    await dialog.getByRole("textbox").fill(
      language === "es-419" ? "Quiero ver más fechas." : "I want to see more dates.",
    );
    const detailSaved = feedbackPosted(page);
    await dialog.getByRole("button", { name: copy.submit }).click();
    const detail = (await detailSaved).request().postDataJSON();

    expect(detail.context).toMatchObject({
      source: "feedback_ask",
      surface: "chat",
      conversation_id: CONVERSATION_ID,
      message_id: RESULT_MESSAGE_ID,
    });
    expect(detail.context).not.toHaveProperty("rating");
    expectNoConversationText(detail, language);
  });

  test(`${language}: a dismissal holds after a reload`, async ({ page }) => {
    await installFixture(page, language);
    await openConversation(page);

    const ask = page.getByTestId("feedback-ask");
    await expect(ask).toBeVisible();
    await ask.getByRole("button", { name: copy.ask.dismiss }).click();
    await expect(ask).toHaveCount(0);

    await reloadConversation(page);
    await expect(page.getByTestId("feedback-ask")).toHaveCount(0);
    await capture(page, `${language}-4-dismissed-after-reload`);
  });

  test(`${language}: a failed tap keeps the ask open`, async ({ page }) => {
    await installFixture(page, language);
    await page.route("**/api/v1/feedback", (route) =>
      json(route, { code: "unavailable" }, 503),
    );
    await openConversation(page);

    const ask = page.getByTestId("feedback-ask");
    const good = ask.getByRole("button", {
      name: copy.ask.answers.positive,
      exact: true,
    });
    await good.click();
    await expect(page.getByText(copy.error)).toBeVisible();
    await expect(good).toBeEnabled();
    await expect(ask).not.toContainText(copy.ask.thanks);
    await capture(page, `${language}-5-failed-tap-stays-open`);

    await reloadConversation(page);
    await expect(page.getByTestId("feedback-ask")).toBeVisible();
  });

  test(`${language}: sending the next turn closes an unanswered ask for good`, async ({
    page,
  }) => {
    await installFixture(page, language);
    await openConversation(page);
    await expect(page.getByTestId("feedback-ask")).toBeVisible();

    await page.locator("[contenteditable='true']").first().click();
    await page.keyboard.type(
      language === "es-419" ? "Ahora prueba con SPY" : "Now try SPY",
    );
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("feedback-ask")).toHaveCount(0);

    await reloadConversation(page);
    await expect(page.getByTestId("feedback-ask")).toHaveCount(0);
    await capture(page, `${language}-6-next-turn-closed-after-reload`);
  });
}
