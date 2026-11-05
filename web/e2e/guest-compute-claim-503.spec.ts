import { expect, test, type Page, type Route } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const GUEST_ID = "00000000-0000-4000-8000-000000000677";
const CONVERSATION_ID = "00000000-0000-4000-8000-000000000678";
const EXPIRES_AT = "2026-09-30T18:00:00Z";
const RAW_SERVER_DETAIL = "Argus could not start this turn. Please try again.";
const EVIDENCE_DIR = path.resolve(
  __dirname,
  "../../docs/reports/evidence/677",
);

const COPY = {
  en: {
    language: "en" as const,
    prompt: "Compare Apple with SPY",
    error: "Argus could not start this turn. Try again in a moment.",
    retrySoon: /Retry in \d+ seconds?/,
    retry: "Retry",
    success: "Let’s test that idea.",
    screenshot: "en-claim-503.png",
  },
  "es-419": {
    language: "es-419" as const,
    prompt: "Compara Apple con SPY",
    error: "Argus no pudo iniciar este turno. Inténtalo de nuevo en un momento.",
    retrySoon: /Reintentar en \d+ segundos?/,
    retry: "Reintentar",
    success: "Probemos esa idea.",
    screenshot: "es-419-claim-503.png",
  },
};

type ClaimEvidence = {
  sentMessages: string[];
  streamCalls: number;
  streamStatuses: number[];
};

type ClaimJourneyOptions = {
  claimFailures?: number;
};

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function guestMe(language: "en" | "es-419") {
  return {
    user: {
      id: GUEST_ID,
      email: null,
      username: null,
      display_name: null,
      language,
      locale: language === "es-419" ? "es-419" : "en-US",
      onboarding: {
        completed: false,
        stage: "language_selection",
        language_confirmed: false,
        primary_goal: null,
      },
    },
    account_kind: "guest",
    guest: {
      expires_at: EXPIRES_AT,
      conversation_id: CONVERSATION_ID,
      conversation_limit: 1,
      simulation_limit: 1,
      feedback_limit: 5,
    },
    capabilities: {
      can_create_additional_conversation: false,
      can_manage_conversation: false,
      can_save_decision: false,
      can_manage_account: false,
      can_use_omnisearch: true,
      can_search_current_workspace: true,
      can_use_grounded_discovery: false,
      can_submit_feedback: true,
    },
  };
}

async function mockGuestClaimJourney(
  page: Page,
  language: "en" | "es-419",
  successText: string,
  options: ClaimJourneyOptions = {},
): Promise<ClaimEvidence> {
  const claimFailures = options.claimFailures ?? 1;
  let authenticated = false;
  const evidence: ClaimEvidence = {
    sentMessages: [],
    streamCalls: 0,
    streamStatuses: [],
  };

  await page.route("**/api/v1/auth/guest", async (route) => {
    authenticated = true;
    await fulfillJson(route, {
      authenticated: true,
      reused: false,
      renewed_after_expiry: false,
      public_account_access_enabled: false,
      account_kind: "guest",
      user: guestMe(language).user,
    });
  });

  await page.route("**/api/v1/me", async (route) => {
    if (!authenticated) {
      await fulfillJson(
        route,
        {
          type: "about:blank",
          title: "Not authenticated",
          status: 401,
          code: "not_authenticated",
        },
        401,
      );
      return;
    }
    await fulfillJson(route, guestMe(language));
  });

  await page.route("**/api/v1/me/usage", async (route) => {
    await fulfillJson(route, { allowances: {} });
  });

  await page.route("**/api/v1/conversations**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/activity")) {
      await fulfillJson(route, {
        operation: { status: "idle", kind: null, updated_at: null },
        attention: { status: "none", cursor: null },
      });
      return;
    }
    if (url.pathname.endsWith("/messages")) {
      await fulfillJson(route, { items: [], next_cursor: null });
      return;
    }
    if (route.request().method() === "POST") {
      await fulfillJson(route, {
        conversation: {
          id: CONVERSATION_ID,
          title: "New idea",
          title_source: "system_default",
          pinned: false,
          archived: false,
          created_at: "2026-09-25T18:00:00Z",
          updated_at: "2026-09-25T18:00:00Z",
          language,
        },
      });
      return;
    }
    await fulfillJson(route, { items: [], next_cursor: null });
  });

  await page.route("**/api/v1/history**", async (route) => {
    await fulfillJson(route, { items: [], next_cursor: null });
  });

  await page.route("**/api/v1/chat/stream", async (route) => {
    evidence.streamCalls += 1;
    const body = route.request().postDataJSON() as { message?: string };
    evidence.sentMessages.push(body.message ?? "");
    if (evidence.streamCalls <= claimFailures) {
      evidence.streamStatuses.push(503);
      await route.fulfill({
        status: 503,
        contentType: "application/problem+json",
        headers: {
          "Retry-After": "3",
          "Access-Control-Allow-Origin": new URL(page.url()).origin,
          "Access-Control-Allow-Credentials": "true",
          // Stands in for the backend CORS expose_headers fix in #678.
          // Without it, a cross-origin browser hides Retry-After and the
          // client falls back to 15s. Same-origin reads the header either way.
          "Access-Control-Expose-Headers": "Retry-After, X-Request-Id",
        },
        body: JSON.stringify({
          type: "about:blank",
          title: "Service Temporarily Unavailable",
          status: 503,
          code: "guest_compute_claim_unavailable",
          detail: RAW_SERVER_DETAIL,
        }),
      });
      return;
    }
    evidence.streamStatuses.push(200);
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: [
        'data: {"type":"stage_start","stage":"clarify"}',
        "",
        `data: {"type":"token","content":"${successText}"}`,
        "",
        `data: {"type":"final","payload":{"stage_outcome":"ready_to_respond","assistant_response":"${successText}","message_id":"msg-guest","conversation_id":"${CONVERSATION_ID}"}}`,
        "",
        "data: [DONE]",
        "",
      ].join("\n"),
    });
  });

  return evidence;
}

for (const locale of ["en", "es-419"] as const) {
  const copy = COPY[locale];

  test(`guest 503 claim error localizes ${locale} and waits for Retry-After`, async ({
    page,
  }) => {
    await page.addInitScript((language) => {
      window.localStorage.setItem("i18nextLng", language);
    }, copy.language);
    const evidence = await mockGuestClaimJourney(
      page,
      copy.language,
      copy.success,
    );
    await page.goto("/", { waitUntil: "domcontentloaded" });

    const composer = page.getByTestId("chat-input");
    await expect(composer).toBeVisible({ timeout: 15_000 });
    await composer.fill(copy.prompt);
    await composer.press("Enter");

    const notice = page.getByRole("status").filter({ hasText: copy.error });
    await expect(notice).toBeVisible();
    await expect(page.getByText(RAW_SERVER_DETAIL)).toHaveCount(0);
    await expect(page.getByText(copy.prompt, { exact: true })).toBeVisible();

    const retry = notice.getByRole("button");
    await expect(retry).toBeDisabled();
    await expect(retry).toHaveText(copy.retrySoon);

    await mkdir(EVIDENCE_DIR, { recursive: true });
    await notice.screenshot({
      path: path.join(EVIDENCE_DIR, copy.screenshot),
      animations: "disabled",
    });

    await expect(retry).toBeEnabled({ timeout: 8_000 });
    await expect(retry).toHaveText(copy.retry);
    await retry.click();

    await expect(page.getByText(copy.success)).toBeVisible();
    await expect(page.getByText(copy.prompt, { exact: true })).toHaveCount(1);
    await expect(notice).toHaveCount(0);
    expect(evidence.streamCalls).toBe(2);
    expect(evidence.streamStatuses).toEqual([503, 200]);
    expect(evidence.sentMessages).toEqual([copy.prompt, copy.prompt]);
  });
}

test("guest 503 then retry 503 keeps the local transcript and Retry countdown", async ({
  page,
}) => {
  const copy = COPY.en;
  await page.addInitScript((language) => {
    window.localStorage.setItem("i18nextLng", language);
  }, copy.language);
  const evidence = await mockGuestClaimJourney(page, copy.language, copy.success, {
    claimFailures: 2,
  });
  await page.goto("/", { waitUntil: "domcontentloaded" });

  const composer = page.getByTestId("chat-input");
  await expect(composer).toBeVisible({ timeout: 15_000 });
  await composer.fill(copy.prompt);
  await composer.press("Enter");

  const notice = page.getByRole("status").filter({ hasText: copy.error });
  await expect(notice).toBeVisible();
  await expect(page.getByText(copy.prompt, { exact: true })).toBeVisible();

  const retry = notice.getByRole("button");
  await expect(retry).toBeDisabled();
  await expect(retry).toHaveText(copy.retrySoon);
  await expect(retry).toBeEnabled({ timeout: 8_000 });
  await expect(retry).toHaveText(copy.retry);
  await retry.click();

  await expect(notice).toBeVisible();
  await expect(page.getByText(copy.prompt, { exact: true })).toBeVisible();
  await expect(page.getByText(RAW_SERVER_DETAIL)).toHaveCount(0);
  await expect(retry).toBeDisabled();
  await expect(retry).toHaveText(copy.retrySoon);
  await expect(page.getByRole("heading", { name: "argus" })).toHaveCount(0);

  await mkdir(EVIDENCE_DIR, { recursive: true });
  await page.screenshot({
    path: path.join(EVIDENCE_DIR, "en-claim-503-retry-again.png"),
    animations: "disabled",
  });

  await expect(retry).toBeEnabled({ timeout: 8_000 });
  await expect(retry).toHaveText(copy.retry);
  await retry.click();

  await expect(page.getByText(copy.success)).toBeVisible();
  await expect(page.getByText(copy.prompt, { exact: true })).toHaveCount(1);
  await expect(notice).toHaveCount(0);
  expect(evidence.streamCalls).toBe(3);
  expect(evidence.streamStatuses).toEqual([503, 503, 200]);
  expect(evidence.sentMessages).toEqual([copy.prompt, copy.prompt, copy.prompt]);
});
