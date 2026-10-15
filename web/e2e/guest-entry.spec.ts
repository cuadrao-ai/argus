import { expect, test, type Page, type Route } from "@playwright/test";

test.describe.configure({ timeout: 60_000 });

const GUEST_ID = "00000000-0000-4000-8000-000000000101";
const CONVERSATION_ID = "00000000-0000-4000-8000-000000000202";
const REPLACEMENT_CONVERSATION_ID =
  "00000000-0000-4000-8000-000000000303";
const EXPIRES_AT = "2026-07-31T18:00:00Z";
const DAY_END = "2026-07-25T00:00:00Z";
const EN_EXPIRY_DATE = new Intl.DateTimeFormat("en-US", {
  dateStyle: "medium",
}).format(new Date(EXPIRES_AT));
const ES_EXPIRY_DATE = new Intl.DateTimeFormat("es-419", {
  dateStyle: "medium",
}).format(new Date(EXPIRES_AT));

type GuestBootEvidence = {
  bootstrapCalls: number;
  profileProbeCalls: number;
  unauthenticatedProfileProbeCalls: number;
  usageCalls: number;
  conversationCreateCalls: number;
  streamCalls: number;
  starterEventCalls: number;
  requestOrder: string[];
  analyticsEvents: unknown[];
  profilePatches: unknown[];
  sentMessages: string[];
  bootstrapRequested: Promise<void>;
  releaseBootstrap: () => void;
  streamRequested: Promise<void>;
  releaseStream: () => void;
  persistedMessages: Array<{
    id: string;
    conversation_id: string;
    role: "user" | "assistant";
    content: string;
    created_at: string;
    metadata: Record<string, unknown>;
  }>;
};

type MockGuestJourneyOptions = {
  initiallyAuthenticated?: boolean;
  holdBootstrap?: boolean;
  holdStageStart?: boolean;
  renewedAfterExpiry?: boolean;
  publicAccountAccessEnabled?: boolean;
  bootstrapFailure?: {
    status: number;
    body: unknown;
  };
  profileRefreshFailure?: {
    status: number;
    body: unknown;
  };
  profileRefreshNull?: boolean;
  initialProfileNull?: boolean;
  initialProfileFailure?: {
    status: number;
    body: unknown;
  };
};

function guestMe(language: "en" | "es-419" = "en") {
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

function idleConversationActivity() {
  return {
    operation: { status: "idle", kind: null, updated_at: null },
    attention: { status: "none", cursor: null },
  };
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function mockGuestJourney(
  page: Page,
  options: MockGuestJourneyOptions = {},
): Promise<GuestBootEvidence> {
  let resolveBootstrapRequested!: () => void;
  const bootstrapRequested = new Promise<void>((resolve) => {
    resolveBootstrapRequested = resolve;
  });
  let releaseBootstrap!: () => void;
  const bootstrapRelease = new Promise<void>((resolve) => {
    releaseBootstrap = resolve;
  });
  let resolveStreamRequested!: () => void;
  const streamRequested = new Promise<void>((resolve) => {
    resolveStreamRequested = resolve;
  });
  let releaseStream!: () => void;
  const streamRelease = new Promise<void>((resolve) => {
    releaseStream = resolve;
  });
  let authenticated = options.initiallyAuthenticated ?? false;
  let authenticatedByBootstrap = false;
  let language: "en" | "es-419" = "en";
  const evidence: GuestBootEvidence = {
    bootstrapCalls: 0,
    profileProbeCalls: 0,
    unauthenticatedProfileProbeCalls: 0,
    usageCalls: 0,
    conversationCreateCalls: 0,
    streamCalls: 0,
    starterEventCalls: 0,
    requestOrder: [],
    analyticsEvents: [],
    profilePatches: [],
    sentMessages: [],
    bootstrapRequested,
    releaseBootstrap,
    streamRequested,
    releaseStream,
    persistedMessages: [],
  };
  await page.route("**/api/v1/auth/guest", async (route) => {
    evidence.bootstrapCalls += 1;
    evidence.requestOrder.push("/auth/guest");
    resolveBootstrapRequested();
    if (options.holdBootstrap) await bootstrapRelease;
    if (options.bootstrapFailure) {
      await fulfillJson(
        route,
        options.bootstrapFailure.body,
        options.bootstrapFailure.status,
      );
      return;
    }
    const payload = route.request().postDataJSON() as { language?: unknown };
    language = payload.language === "es-419" ? "es-419" : "en";
    await fulfillJson(route, {
      authenticated: true,
      reused: evidence.bootstrapCalls > 1,
      renewed_after_expiry: options.renewedAfterExpiry ?? false,
      public_account_access_enabled:
        options.publicAccountAccessEnabled ?? false,
      account_kind: "guest",
      user: guestMe(language).user,
    });
    authenticated = true;
    authenticatedByBootstrap = true;
  });

  await page.route("**/api/v1/me", async (route) => {
    if (route.request().method() === "PATCH") {
      evidence.profilePatches.push(route.request().postDataJSON());
      await fulfillJson(route, guestMe(language));
      return;
    }
    evidence.profileProbeCalls += 1;
    if (!authenticated) {
      evidence.unauthenticatedProfileProbeCalls += 1;
      if (options.initialProfileNull) {
        await fulfillJson(route, null);
        return;
      }
      if (options.initialProfileFailure) {
        await fulfillJson(
          route,
          options.initialProfileFailure.body,
          options.initialProfileFailure.status,
        );
        return;
      }
      await fulfillJson(
        route,
        {
          type: "about:blank",
          title: "Not authenticated",
          status: 401,
          code: "not_authenticated",
          detail: "No authenticated session is available.",
        },
        401,
      );
      return;
    }
    if (authenticatedByBootstrap) {
      evidence.requestOrder.push("/me");
      if (options.profileRefreshNull) {
        await fulfillJson(route, null);
        return;
      }
      if (options.profileRefreshFailure) {
        await fulfillJson(
          route,
          options.profileRefreshFailure.body,
          options.profileRefreshFailure.status,
        );
        return;
      }
    }
    await fulfillJson(route, guestMe(language));
  });

  await page.route("**/api/v1/me/usage", async (route) => {
    evidence.usageCalls += 1;
    evidence.requestOrder.push("/me/usage");
    await fulfillJson(route, {
      allowances: {
        compute: {
          hour: null,
          day: null,
          guest_session: null,
          available_now: true,
          limiting_window: null,
        },
        grounding: {
          hour: null,
          day: {
            used: 0,
            limit: 3,
            remaining: 3,
            period_end: DAY_END,
          },
          guest_session: null,
          available_now: true,
          limiting_window: "day",
        },
        execution: {
          hour: null,
          day: {
            used: 0,
            limit: 2,
            remaining: 2,
            period_end: DAY_END,
          },
          guest_session: {
            used: 0,
            limit: 2,
            remaining: 2,
            period_end: EXPIRES_AT,
          },
          available_now: true,
          limiting_window: "guest_session",
        },
      },
    });
  });

  await page.route("**/api/v1/conversations**", async (route) => {
    const url = new URL(route.request().url());
    const pathname = url.pathname;
    if (pathname.endsWith("/activity")) {
      await fulfillJson(route, idleConversationActivity());
      return;
    }
    if (pathname.endsWith("/messages")) {
      await fulfillJson(route, {
        items: evidence.persistedMessages,
        next_cursor: null,
      });
      return;
    }
    if (route.request().method() === "POST") {
      evidence.conversationCreateCalls += 1;
      evidence.requestOrder.push("/conversations");
      const createdConversationId = pathname.endsWith("/guest/replace")
        ? REPLACEMENT_CONVERSATION_ID
        : CONVERSATION_ID;
      if (createdConversationId === REPLACEMENT_CONVERSATION_ID) {
        evidence.persistedMessages = [];
      }
      await fulfillJson(route, {
        conversation: {
          id: createdConversationId,
          title: "New idea",
          title_source: "system_default",
          pinned: false,
          archived: false,
          created_at: "2026-07-24T18:00:00Z",
          updated_at: "2026-07-24T18:00:00Z",
          language: "en",
        },
      });
      return;
    }
    await fulfillJson(route, {
      items:
        evidence.persistedMessages.length > 0
          ? [
              {
                id: CONVERSATION_ID,
                title: "New idea",
                title_source: "system_default",
                pinned: false,
                archived: false,
                created_at: "2026-07-24T18:00:00Z",
                updated_at: "2026-07-24T18:00:00Z",
                language: "en",
                activity: idleConversationActivity(),
              },
            ]
          : [],
      next_cursor: null,
    });
  });

  await page.route("**/api/v1/history**", async (route) => {
    await fulfillJson(route, { items: [], next_cursor: null });
  });

  // Retired endpoint, kept as a tripwire: any call shows up in the evidence.
  await page.route("**/api/v1/analytics/guest-events", async (route) => {
    evidence.starterEventCalls += 1;
    evidence.requestOrder.push("/analytics/guest-events");
    evidence.analyticsEvents.push(route.request().postDataJSON());
    await fulfillJson(route, { success: true });
  });

  await page.route("**/api/v1/chat/stream", async (route) => {
    evidence.streamCalls += 1;
    evidence.requestOrder.push("/chat/stream");
    resolveStreamRequested();
    if (options.holdStageStart) await streamRelease;
    const body = route.request().postDataJSON() as { message?: string };
    evidence.sentMessages.push(body.message ?? "");
    evidence.persistedMessages = [
      {
        id: "msg-user",
        conversation_id: CONVERSATION_ID,
        role: "user",
        content: body.message ?? "",
        created_at: "2026-07-24T18:01:00Z",
        metadata: {},
      },
      {
        id: "msg-guest",
        conversation_id: CONVERSATION_ID,
        role: "assistant",
        content: "Let’s test that idea.",
        created_at: "2026-07-24T18:01:01Z",
        metadata: {},
      },
    ];
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: [
        'data: {"type":"stage_start","stage":"clarify"}',
        "",
        'data: {"type":"token","content":"Let’s test that idea."}',
        "",
        `data: {"type":"final","payload":{"stage_outcome":"ready_to_respond","assistant_response":"Let’s test that idea.","message_id":"msg-guest","conversation_id":"${CONVERSATION_ID}"}}`,
        "",
        "data: [DONE]",
        "",
      ].join("\n"),
    });
  });

  return evidence;
}

async function readGuestEmptySurface(page: Page) {
  const heading = page.getByRole("heading", { name: "Cuadrao", exact: true });
  const starterActions = page
    .getByTestId("starter-actions")
    .getByRole("button");
  await expect(heading).toBeVisible();
  await expect(starterActions).toHaveCount(3);

  return {
    headingGroup: await heading.locator("..").innerText(),
    placeholder: await page.getByTestId("chat-input").getAttribute("placeholder"),
    starterLabels: await starterActions.allTextContents(),
    headerHeadingCount: await page.locator("header h1").count(),
  };
}

test("@guest-shell Start over reuses the guest landing surface", async ({
  page,
}) => {
  const evidence = await mockGuestJourney(page, {
    initiallyAuthenticated: true,
  });
  await page.goto("/", { waitUntil: "domcontentloaded" });

  const landingSurface = await readGuestEmptySurface(page);
  expect(landingSurface.headerHeadingCount).toBe(0);

  const composer = page.getByTestId("chat-input");
  await composer.fill("Compare Apple with SPY");
  await composer.press("Enter");
  await expect(page.getByText("Let’s test that idea.")).toBeVisible();

  await page.getByRole("button", { name: "New chat" }).click();
  const dialog = page.getByRole("dialog", {
    name: "Start a new conversation?",
  });
  await dialog.getByRole("button", { name: "Start over" }).click();

  await expect(page).toHaveURL(
    new RegExp(`conversation=${REPLACEMENT_CONVERSATION_ID}`),
  );
  expect(await readGuestEmptySurface(page)).toEqual(landingSurface);
  expect(evidence.conversationCreateCalls).toBe(2);
});

test("@guest-shell keeps the neutral submission state until the first stream stage", async ({
  page,
}) => {
  const evidence = await mockGuestJourney(page, { holdStageStart: true });
  await page.goto("/", { waitUntil: "domcontentloaded" });

  const composer = page.getByTestId("chat-input");
  await composer.fill("Compare Apple with SPY");
  await composer.press("Enter");
  await evidence.streamRequested;

  await expect(
    page.getByText("Sending...", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Understanding your idea...", { exact: true }),
  ).toHaveCount(0);
  await expect(composer).toHaveAttribute("aria-disabled", "true");
  await expect(page.getByRole("region", { name: "Conversation" })).toHaveAttribute(
    "aria-busy",
    "true",
  );

  evidence.releaseStream();
  await expect(page.getByText("Let’s test that idea.")).toBeVisible();
  await expect(page.getByText("Sending...", { exact: true })).toHaveCount(
    0,
  );
});

test("@guest-shell sign-in cancels a pending first submit before routing", async ({
  page,
}) => {
  const evidence = await mockGuestJourney(page, { holdBootstrap: true });
  await page.goto("/", { waitUntil: "domcontentloaded" });

  const composer = page.getByTestId("chat-input");
  await composer.fill("Compare Apple with SPY");
  await composer.press("Enter");
  await evidence.bootstrapRequested;
  await expect(page.getByText("Sending...", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/?auth=login$/);

  evidence.releaseBootstrap();
  await page.waitForLoadState("networkidle");
  expect(evidence.requestOrder).toEqual(["/auth/guest"]);
  expect({
    usage: evidence.usageCalls,
    conversation: evidence.conversationCreateCalls,
    stream: evidence.streamCalls,
  }).toEqual({ usage: 0, conversation: 0, stream: 0 });
});

test("@guest-shell null profile refresh blocks admission before guest work", async ({
  page,
}) => {
  const evidence = await mockGuestJourney(page, { profileRefreshNull: true });
  await page.goto("/", { waitUntil: "domcontentloaded" });

  const composer = page.getByTestId("chat-input");
  await composer.fill("Compare Apple with SPY");
  await composer.press("Enter");

  await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
  await expect(composer).toHaveText("Compare Apple with SPY");
  expect(evidence.requestOrder).toEqual(["/auth/guest", "/me"]);
  expect({
    usage: evidence.usageCalls,
    conversation: evidence.conversationCreateCalls,
    stream: evidence.streamCalls,
  }).toEqual({ usage: 0, conversation: 0, stream: 0 });
});

test("@guest-shell a null landing profile stays auth-first without guest work", async ({
  page,
}) => {
  const evidence = await mockGuestJourney(page, { initialProfileNull: true });
  await page.goto("/", { waitUntil: "domcontentloaded" });

  await expect(page.getByRole("heading", { name: "Cuadrao", exact: true })).toBeVisible();
  await expect(page.getByTestId("chat-input")).toHaveCount(0);
  expect({
    bootstrap: evidence.bootstrapCalls,
    usage: evidence.usageCalls,
    conversation: evidence.conversationCreateCalls,
    stream: evidence.streamCalls,
  }).toEqual({ bootstrap: 0, usage: 0, conversation: 0, stream: 0 });
});

test("@guest-shell a null chat profile fails closed before admission", async ({
  page,
}) => {
  const evidence = await mockGuestJourney(page, { initialProfileNull: true });
  await page.goto("/chat", { waitUntil: "domcontentloaded" });

  await expect(page).toHaveURL(/\/?auth=login$/);
  await expect(page.getByTestId("chat-input")).toHaveCount(0);
  expect({
    bootstrap: evidence.bootstrapCalls,
    usage: evidence.usageCalls,
    conversation: evidence.conversationCreateCalls,
    stream: evidence.streamCalls,
  }).toEqual({ bootstrap: 0, usage: 0, conversation: 0, stream: 0 });
});

for (const preBootstrapSidebarCase of [
  {
    language: "en",
    retentionCopy: "Sign in to keep your history",
    expiryCopy: /Available until/,
    noRecentCopy: "No recent chats yet.",
    recentsLabel: "Recents",
    expandLabel: "Expand",
  },
  {
    language: "es-419",
    retentionCopy: "Inicia sesión para conservar tu historial",
    expiryCopy: /Disponible hasta/,
    noRecentCopy: "Aún no hay chats recientes.",
    recentsLabel: "Recientes",
    expandLabel: "Expandir",
  },
] as const) {
  test(`@guest-shell ${preBootstrapSidebarCase.language} pre-bootstrap sidebar makes no retention promise`, async ({
    page,
  }) => {
    await page.addInitScript((language) => {
      window.localStorage.setItem("i18nextLng", language);
    }, preBootstrapSidebarCase.language);
    const evidence = await mockGuestJourney(page);
    await page.goto("/", { waitUntil: "domcontentloaded" });

    await expect(page.getByTestId("chat-input")).toBeVisible();
    await page.getByRole("button", { name: preBootstrapSidebarCase.expandLabel, exact: true }).click();
    const sidebar = page.locator("aside");
    await expect
      .poll(async () => (await sidebar.boundingBox())?.width ?? 0)
      .toBeGreaterThanOrEqual(280);
    await sidebar
      .getByRole("button", { name: preBootstrapSidebarCase.recentsLabel })
      .click();
    await expect(
      sidebar.getByText(preBootstrapSidebarCase.noRecentCopy, { exact: true }),
    ).toBeVisible();
    await expect(sidebar.getByText(preBootstrapSidebarCase.retentionCopy, {
      exact: true,
    })).toHaveCount(0);
    await expect(sidebar.getByText(preBootstrapSidebarCase.expiryCopy)).toHaveCount(
      0,
    );
    expect({
      bootstrap: evidence.bootstrapCalls,
      usage: evidence.usageCalls,
      conversation: evidence.conversationCreateCalls,
      stream: evidence.streamCalls,
    }).toEqual({ bootstrap: 0, usage: 0, conversation: 0, stream: 0 });
  });
}

for (const entryCase of [
  {
    language: "en",
    text: "Compare Apple with SPY",
    earlyStage: "Understanding your idea...",
  },
  {
    language: "es-419",
    text: "Compara Apple con SPY",
    earlyStage: "Entendiendo tu idea...",
  },
] as const) {
  test(`@guest-shell ${entryCase.language} first typed send defers bootstrap and preserves request ordering`, async ({
    page,
  }) => {
    await page.addInitScript((language) => {
      window.localStorage.setItem("i18nextLng", language);
    }, entryCase.language);
    const evidence = await mockGuestJourney(page, { holdBootstrap: true });

    await page.goto("/", { waitUntil: "domcontentloaded" });

    const composer = page.getByTestId("chat-input");
    await expect(composer).toBeVisible({ timeout: 30_000 });
    expect(evidence.unauthenticatedProfileProbeCalls).toBeGreaterThanOrEqual(1);
    const idleProfileProbeCalls = evidence.profileProbeCalls;
    expect({
      bootstrap: evidence.bootstrapCalls,
      usage: evidence.usageCalls,
      conversation: evidence.conversationCreateCalls,
      stream: evidence.streamCalls,
    }).toEqual({ bootstrap: 0, usage: 0, conversation: 0, stream: 0 });
    expect(evidence.profilePatches).toEqual([]);

    await composer.fill(entryCase.text);
    expect(evidence.profileProbeCalls).toBe(idleProfileProbeCalls);
    expect({
      bootstrap: evidence.bootstrapCalls,
      usage: evidence.usageCalls,
      conversation: evidence.conversationCreateCalls,
      stream: evidence.streamCalls,
    }).toEqual({ bootstrap: 0, usage: 0, conversation: 0, stream: 0 });

    await composer.press("Enter");
    await evidence.bootstrapRequested;
    try {
      await expect(composer).toHaveAttribute("aria-disabled", "true");
      await expect(page.getByTestId("chat-send")).toBeDisabled();
      await expect(
        page.locator('[data-testid="chat-input"][aria-disabled="true"]'),
      ).toHaveCount(1);
      await expect(
        page.getByText(entryCase.earlyStage, { exact: true }),
      ).toHaveCount(0);
      await expect(
        page.getByText(
          /CAPTCHA|bot check|verifying you|checking your session/i,
        ),
      ).toHaveCount(0);
      expect({
        usage: evidence.usageCalls,
        conversation: evidence.conversationCreateCalls,
        stream: evidence.streamCalls,
      }).toEqual({ usage: 0, conversation: 0, stream: 0 });
      expect(evidence.requestOrder).toEqual(["/auth/guest"]);
    } finally {
      evidence.releaseBootstrap();
    }

    await expect(page.getByText("Let’s test that idea.")).toBeVisible();
    expect(evidence.requestOrder).toEqual([
      "/auth/guest",
      "/me",
      "/me/usage",
      "/conversations",
      "/chat/stream",
    ]);
    expect({
      bootstrap: evidence.bootstrapCalls,
      usage: evidence.usageCalls,
      conversation: evidence.conversationCreateCalls,
      stream: evidence.streamCalls,
      starterEvent: evidence.starterEventCalls,
    }).toEqual({
      bootstrap: 1,
      usage: 1,
      conversation: 1,
      stream: 1,
      starterEvent: 0,
    });
    expect(evidence.sentMessages).toEqual([entryCase.text]);
  });
}

test("@guest-shell private-alpha denial preserves the auth-first request-access fallback", async ({
  page,
}) => {
  const evidence = await mockGuestJourney(page, {
    initialProfileFailure: {
      status: 403,
      body: {
        type: "about:blank",
        title: "Private alpha access required",
        status: 403,
        code: "private_alpha_access_required",
        detail: "This account does not have private alpha access.",
      },
    },
  });

  await page.goto("/", { waitUntil: "domcontentloaded" });

  await expect(
    page.getByRole("button", { name: "Request access" }),
  ).toBeVisible();
  await expect(page.getByTestId("chat-input")).toHaveCount(0);
  expect(evidence.unauthenticatedProfileProbeCalls).toBeGreaterThanOrEqual(1);
  expect({
    bootstrap: evidence.bootstrapCalls,
    usage: evidence.usageCalls,
    conversation: evidence.conversationCreateCalls,
    stream: evidence.streamCalls,
  }).toEqual({ bootstrap: 0, usage: 0, conversation: 0, stream: 0 });
});

for (const starterEntryCase of [
  {
    language: "en",
    label: "Test Apple vs SPY",
    value: "Compare Apple with SPY over the last 12 months.",
  },
  {
    language: "es-419",
    label: "Prueba Apple vs SPY",
    value: "Compara Apple con SPY durante los últimos 12 meses.",
  },
] as const) {
  test(`@guest-shell ${starterEntryCase.language} first starter action coalesces admission and analytics`, async ({
    page,
  }) => {
    await page.addInitScript((language) => {
      window.localStorage.setItem("i18nextLng", language);
    }, starterEntryCase.language);
    const evidence = await mockGuestJourney(page);
    await page.goto("/", { waitUntil: "domcontentloaded" });

    await page
      .getByRole("button", { name: starterEntryCase.label })
      .evaluate((button: HTMLButtonElement) => {
        button.click();
        button.click();
      });
    await expect(page.getByText("Let’s test that idea.")).toBeVisible();

    expect(evidence.requestOrder).toEqual([
      "/auth/guest",
      "/me",
      "/me/usage",
      "/conversations",
      "/chat/stream",
    ]);
    expect({
      bootstrap: evidence.bootstrapCalls,
      usage: evidence.usageCalls,
      conversation: evidence.conversationCreateCalls,
      stream: evidence.streamCalls,
      starterEvent: evidence.starterEventCalls,
    }).toEqual({
      bootstrap: 1,
      usage: 1,
      conversation: 1,
      stream: 1,
      starterEvent: 0,
    });
    expect(evidence.sentMessages).toEqual([starterEntryCase.value]);
    // The browser sends no analytics of its own (SPEC 0, 0C-1).
    expect(evidence.analyticsEvents).toEqual([]);
  });
}

for (const failureCase of [
  {
    name: "bootstrap failure",
    options: {
      bootstrapFailure: {
        status: 503,
        body: {
          code: "guest_bootstrap_failed",
          detail: "Guest bootstrap failed.",
        },
      },
    },
    expectedOrder: ["/auth/guest"],
  },
  {
    name: "profile refresh failure",
    options: {
      profileRefreshFailure: {
        status: 503,
        body: {
          code: "profile_unavailable",
          detail: "Profile unavailable.",
        },
      },
    },
    expectedOrder: ["/auth/guest", "/me"],
  },
] as const) {
  test(`@guest-shell ${failureCase.name} blocks starter admission and emits no funnel event`, async ({
    page,
  }) => {
    const evidence = await mockGuestJourney(page, failureCase.options);
    await page.goto("/", { waitUntil: "domcontentloaded" });

    await page.getByRole("button", { name: "Test Apple vs SPY" }).click();

    await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
    expect(evidence.requestOrder).toEqual(failureCase.expectedOrder);
    expect({
      starterEvent: evidence.starterEventCalls,
      usage: evidence.usageCalls,
      conversation: evidence.conversationCreateCalls,
      stream: evidence.streamCalls,
    }).toEqual({ starterEvent: 0, usage: 0, conversation: 0, stream: 0 });
  });
}

test("@guest-shell verified starter actions keep their ordinary localized payloads", async ({
  page,
}) => {
  const evidence = await mockGuestJourney(page, {
    initiallyAuthenticated: true,
  });
  const starterCases = [
    {
      label: "Test Apple vs SPY",
      value: "Compare Apple with SPY over the last 12 months.",
    },
    {
      label: "Test Bitcoin (BTC) hold",
      value: "What if I bought Bitcoin this year so far?",
    },
    {
      label: "Test weekly Nvidia buys",
      value:
        "What if I bought $250 of Nvidia every week over the last 12 months?",
    },
  ];

  for (const starter of starterCases) {
    evidence.persistedMessages = [];
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: starter.label }).click();
    await expect(page.getByText("Let’s test that idea.")).toBeVisible();
    expect(evidence.sentMessages.at(-1)).toBe(starter.value);
    await expect(page.getByRole("button", { name: starter.label })).toHaveCount(
      0,
    );
  }
});

test("@guest-shell root re-entry restores the one server-owned guest conversation", async ({
  page,
}) => {
  const evidence = await mockGuestJourney(page);
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByTestId("chat-input").fill("Compare Apple with SPY");
  await page.getByTestId("chat-input").press("Enter");
  await expect(page.getByText("Let’s test that idea.")).toBeVisible();

  await page.goto("/", { waitUntil: "domcontentloaded" });

  await expect(page.getByText("Compare Apple with SPY")).toBeVisible();
  await expect(page.getByText("Let’s test that idea.")).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`conversation=${CONVERSATION_ID}`));
  expect(evidence.bootstrapCalls).toBe(1);
  expect(evidence.profilePatches).toEqual([]);
});

test("@registered-hydration keeps the composer locked until a delayed reload settles", async ({
  page,
}) => {
  let releaseHydration!: () => void;
  const hydrationBlocked = new Promise<void>((resolve) => {
    releaseHydration = resolve;
  });
  let messageLoadStarted!: () => void;
  const messageLoadPending = new Promise<void>((resolve) => {
    messageLoadStarted = resolve;
  });
  let messageLoadCount = 0;
  let streamPostCount = 0;

  await page.route("**/api/v1/me", async (route) => {
    await fulfillJson(route, {
      user: {
        id: GUEST_ID,
        email: "registered@example.test",
        username: null,
        display_name: null,
        language: "en",
        locale: "en-US",
        onboarding: {
          completed: true,
          stage: "ready",
          language_confirmed: true,
          primary_goal: "test_stock_idea",
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
        can_use_grounded_discovery: false,
        can_submit_feedback: true,
      },
    });
  });
  await page.route("**/api/v1/history**", async (route) => {
    await fulfillJson(route, { items: [], next_cursor: null });
  });
  await page.route("**/api/v1/conversations**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/activity")) {
      await fulfillJson(route, idleConversationActivity());
      return;
    }
    if (url.pathname.endsWith(`/${CONVERSATION_ID}/messages`)) {
      messageLoadCount += 1;
      if (messageLoadCount > 1) {
        await fulfillJson(route, { items: [], next_cursor: null });
        return;
      }
      messageLoadStarted();
      await hydrationBlocked;
      await fulfillJson(route, {
        items: [
          {
            id: "stale-user",
            conversation_id: CONVERSATION_ID,
            role: "user",
            content: "Persisted stale turn",
            created_at: "2026-07-24T17:00:00Z",
            metadata: {},
          },
          {
            id: "stale-assistant",
            conversation_id: CONVERSATION_ID,
            role: "assistant",
            content: "Persisted stale response",
            created_at: "2026-07-24T17:00:01Z",
            metadata: {},
          },
        ],
        next_cursor: null,
      });
      return;
    }
    await fulfillJson(route, { items: [], next_cursor: null });
  });
  await page.route("**/api/v1/chat/stream", async (route) => {
    streamPostCount += 1;
    const body = route.request().postDataJSON() as { message?: string };
    expect(body.message).toBe("Accepted while reload is pending");
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: [
        'data: {"type":"stage_start","stage":"clarify"}',
        "",
        'data: {"type":"token","content":"Local accepted response"}',
        "",
        `data: {"type":"final","payload":{"stage_outcome":"ready_to_respond","assistant_response":"Local accepted response","message_id":"local-assistant","conversation_id":"${CONVERSATION_ID}"}}`,
        "",
        "data: [DONE]",
        "",
      ].join("\n"),
    });
  });

  try {
    await page.goto(`/chat?conversation=${CONVERSATION_ID}`, {
      waitUntil: "domcontentloaded",
    });
    await messageLoadPending;
    const input = page.getByTestId("chat-input");
    await expect(input).toBeVisible();
    await expect(input).toBeDisabled();
    expect(streamPostCount).toBe(0);

    releaseHydration();

    await expect(input).toBeEnabled();
    await input.fill("Accepted while reload is pending");
    await input.press("Enter");
    await expect(page.getByText("Local accepted response")).toBeVisible();
    expect(messageLoadCount).toBe(2);
    expect(streamPostCount).toBe(1);
    await expect(input).toBeEnabled();
  } finally {
    releaseHydration();
  }
});

for (const expiredCase of [
  {
    language: "en",
    title: "This temporary chat has expired",
    detail: "Its messages and results can’t be recovered.",
    restart: "Start a new temporary chat",
    signIn: "Sign in",
  },
  {
    language: "es-419",
    title: "Este chat temporal venció",
    detail: "Sus mensajes y resultados no se pueden recuperar.",
    restart: "Iniciar un nuevo chat temporal",
    signIn: "Iniciar sesión",
  },
] as const) {
  test(`@guest-expiry ${expiredCase.language} shows honest recovery`, async ({
    page,
  }) => {
    await page.addInitScript((language) => {
      window.localStorage.setItem("i18nextLng", language);
    }, expiredCase.language);
    const evidence = await mockGuestJourney(page, {
      renewedAfterExpiry: true,
    });

    await page.goto("/", { waitUntil: "domcontentloaded" });

    const composer = page.getByTestId("chat-input");
    await expect(composer).toBeVisible();
    await expect(
      page.getByRole("heading", { name: expiredCase.title }),
    ).toHaveCount(0);
    await composer.fill(
      expiredCase.language === "es-419"
        ? "Compara Apple con SPY"
        : "Compare Apple with SPY",
    );
    await composer.press("Enter");

    await expect(
      page.getByRole("heading", { name: expiredCase.title }),
    ).toBeVisible();
    await expect(page.getByText(expiredCase.detail)).toBeVisible();
    await expect(
      page.getByRole("button", { name: expiredCase.restart }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: expiredCase.signIn }),
    ).toBeVisible();
    await expect(page.getByTestId("chat-input")).toHaveCount(0);
    expect(evidence.requestOrder).toEqual(["/auth/guest"]);
    expect({
      usage: evidence.usageCalls,
      conversation: evidence.conversationCreateCalls,
      stream: evidence.streamCalls,
    }).toEqual({ usage: 0, conversation: 0, stream: 0 });
  });
}

test("@guest-expiry public account capability offers in-place account creation", async ({
  page,
}) => {
  await mockGuestJourney(page, {
    renewedAfterExpiry: true,
    publicAccountAccessEnabled: true,
  });

  await page.goto("/", { waitUntil: "domcontentloaded" });

  await page.getByTestId("chat-input").fill("Compare Apple with SPY");
  await page.getByTestId("chat-input").press("Enter");
  await expect(
    page.getByRole("button", { name: "Create account" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(
    page.getByRole("button", { name: "Sign up", exact: true }),
  ).toBeVisible();
  await expect(page.getByPlaceholder("Name")).toBeVisible();
});

for (const failureCase of [
  { kind: "bootstrap", expectedOrder: ["/auth/guest"] },
  { kind: "refresh", expectedOrder: ["/auth/guest", "/me"] },
] as const) {
  for (const localizedCase of [
    {
      language: "en",
      text: "Compare Apple with SPY",
      retry: "Try again",
    },
    {
      language: "es-419",
      text: "Compara Apple con SPY",
      retry: "Intentar de nuevo",
    },
  ] as const) {
    test(`@guest-shell ${localizedCase.language} ${failureCase.kind} failure retains the draft without admission`, async ({
      page,
    }) => {
      await page.addInitScript((language) => {
        window.localStorage.setItem("i18nextLng", language);
      }, localizedCase.language);
      const failure = {
        status: 503,
        body: {
          type: "about:blank",
          title: "Service Unavailable",
          status: 503,
          code:
            failureCase.kind === "bootstrap"
              ? "guest_bootstrap_unavailable"
              : "profile_verification_unavailable",
          detail: "The temporary workspace is unavailable.",
        },
      };
      const evidence = await mockGuestJourney(
        page,
        failureCase.kind === "bootstrap"
          ? { bootstrapFailure: failure }
          : { profileRefreshFailure: failure },
      );

      await page.goto("/", { waitUntil: "domcontentloaded" });

      const composer = page.getByTestId("chat-input");
      await composer.fill(localizedCase.text);
      await composer.press("Enter");
      await expect(
        page.getByRole("button", { name: localizedCase.retry }),
      ).toBeVisible();
      await expect(composer).toHaveText(localizedCase.text);
      expect(evidence.requestOrder).toEqual(failureCase.expectedOrder);
      expect({
        usage: evidence.usageCalls,
        conversation: evidence.conversationCreateCalls,
        stream: evidence.streamCalls,
        starterEvent: evidence.starterEventCalls,
      }).toEqual({ usage: 0, conversation: 0, stream: 0, starterEvent: 0 });
    });
  }
}

test("@guest-shell capability chrome stays visible and opens typed conversion", async ({
  page,
}) => {
  const evidence = await mockGuestJourney(page, {
    initiallyAuthenticated: true,
  });
  let searchCalls = 0;
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.endsWith("/api/v1/search")) {
      searchCalls += 1;
    }
  });

  await page.goto("/", { waitUntil: "domcontentloaded" });

  await expect(
    page.getByText("Test an investing idea against history."),
  ).toBeVisible();
  await expect(page.getByTestId("chat-input")).toHaveAttribute(
    "aria-label",
    "What do you want to test?",
  );
  await expect(
    page.getByRole("button", { name: "Guest settings" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Chat options" })).toHaveCount(
    0,
  );
  const temporaryNotice = page.getByTestId("guest-temporary-notice");
  await expect(temporaryNotice).toHaveCount(1);
  await expect(temporaryNotice).toHaveText(
    `Temporary chat · available until ${EN_EXPIRY_DATE}`,
  );
  await expect(temporaryNotice).toHaveAttribute("datetime", EXPIRES_AT);
  await expect(temporaryNotice).toHaveAttribute("title", EXPIRES_AT);
  await expect(page.getByTestId("guest-sidebar-expiry")).toHaveCount(0);
  const composerBox = await page.getByTestId("chat-input").boundingBox();
  const noticeBox = await temporaryNotice.boundingBox();
  expect(noticeBox?.y ?? 0).toBeGreaterThan(
    (composerBox?.y ?? 0) + (composerBox?.height ?? 0),
  );
  await expect(page.getByTestId("guest-legal-before_message")).toContainText(
    "By messaging Argus",
  );
  await expect(
    page
      .getByTestId("guest-legal-before_message")
      .getByRole("link", { name: "Terms" }),
  ).toHaveAttribute("href", "/terms");
  await expect(
    page
      .getByTestId("guest-legal-before_message")
      .getByRole("link", { name: "Privacy" }),
  ).toHaveAttribute("href", "/privacy");
  await expect(page.getByTestId("guest-legal-before_message")).toContainText(
    "2026",
  );

  await page.getByRole("button", { name: "Sign in" }).click();
  const requestAccessDialog = page.getByRole("dialog", {
    name: "Request access to Cuadrao",
  });
  await expect(requestAccessDialog).toBeVisible();
  await expect(requestAccessDialog).toContainText(
    "Share your email to request access.",
  );
  await requestAccessDialog.getByRole("button", { name: "Cancel" }).click();
  await expect(requestAccessDialog).toHaveCount(0);
  await expect(page.getByTestId("guest-temporary-notice")).toHaveCount(1);
  await expect(page).toHaveURL(/\/chat$/);

  const settingsTrigger = page.getByRole("button", { name: "Guest settings" });
  await settingsTrigger.click();
  await expect(
    page.getByRole("menu", { name: "Guest settings" }),
  ).toBeVisible();
  await expect(page.getByText("Theme", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("menuitem")).toHaveCount(2);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("menu", { name: "Guest settings" })).toHaveCount(
    0,
  );
  await expect(settingsTrigger).toBeFocused();
  await settingsTrigger.click();
  await page.getByRole("button", { name: "Dark" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  await page.getByRole("menuitem", { name: "Language" }).click();
  await expect(page.getByRole("dialog", { name: "Language" })).toBeVisible();
  await page.getByRole("button", { name: /Español/ }).click();
  await expect(
    page.getByRole("button", { name: "Iniciar sesión" }),
  ).toBeVisible();
  await expect(page.getByTestId("guest-temporary-notice")).toHaveText(
    `Chat temporal · disponible hasta ${ES_EXPIRY_DATE}`,
  );
  const localizedSettingsTrigger = page.getByRole("button", {
    name: "Ajustes de invitado",
  });
  await expect(localizedSettingsTrigger).toBeFocused();
  await localizedSettingsTrigger.click();
  const localizedLanguageEntry = page.getByRole("menuitem", { name: "Idioma" });
  await expect(localizedLanguageEntry).toBeVisible();
  await expect(page.getByRole("menuitem", { name: "Language" })).toHaveCount(0);
  await localizedLanguageEntry.click();
  await expect(page.getByRole("dialog", { name: "Idioma" })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Cerrar selector de idioma" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");

  await page.getByRole("button", { name: "Expand", exact: true }).click();
  await expect(page.getByRole("button", { name: "Buscar" })).toBeVisible();
  await expect(page.getByTestId("guest-temporary-notice")).toHaveCount(1);
  await expect(page.locator("aside").getByText(/Chat temporal/)).toHaveCount(0);
  await page.getByRole("button", { name: "Buscar" }).click();
  await expect(
    page.getByText(
      "La búsqueda se limita a esta conversación temporal. El descubrimiento fundamentado más amplio aún no está disponible.",
    ),
  ).toBeVisible();
  expect(searchCalls).toBe(1);
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "Cerrar búsqueda" }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Collapse", exact: true }).click();
  await expect(page.getByTestId("guest-temporary-notice")).toHaveCount(1);

  await page.getByTestId("chat-input").fill("Compara Apple con SPY");
  await page.getByTestId("chat-input").press("Enter");
  await expect(page.getByText("Let’s test that idea.")).toBeVisible();
  await expect(page.getByTestId("guest-legal-after_message")).toContainText(
    "Solo con fines educativos",
  );
  await expect(page.getByTestId("guest-legal-before_message")).toHaveCount(0);
  await expect(page.getByTestId("guest-temporary-notice")).toHaveCount(1);
  await expect(
    page.getByRole("button", { name: "Opciones de chat" }),
  ).toHaveCount(0);
  expect(evidence.profilePatches).toEqual([]);

  await page.getByRole("button", { name: "Nuevo chat" }).click();
  const newChatDialog = page.getByRole("dialog", {
    name: "¿Quieres iniciar otra conversación?",
  });
  await expect(newChatDialog).toContainText(
    "Empezar de nuevo reemplaza esta conversación temporal. Inicia sesión para conservarla y comenzar otra.",
  );
  await expect(
    newChatDialog.getByRole("button", { name: "Empezar de nuevo" }),
  ).toBeVisible();
  await expect(
    newChatDialog.getByRole("button", {
      name: "Iniciar sesión para conservarla",
    }),
  ).toBeVisible();
  await newChatDialog.getByRole("button", { name: "Cancelar" }).click();
  await expect(newChatDialog).toHaveCount(0);
  await expect(page.getByText("Compara Apple con SPY")).toBeVisible();
});

test("@guest-shell mobile keeps composer, legal copy, and 44px controls reachable", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockGuestJourney(page, { initiallyAuthenticated: true });
  await page.goto("/", { waitUntil: "domcontentloaded" });

  const composer = page.getByTestId("chat-input");
  await expect(composer).toBeVisible();
  await expect(composer).toHaveAttribute(
    "aria-label",
    "What do you want to test?",
  );
  await expect(page.getByTestId("guest-legal-before_message")).toBeVisible();
  await expect(page.getByTestId("guest-temporary-notice")).toHaveCount(1);
  await expect(page.getByTestId("guest-sidebar-expiry")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Guest settings" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();

  const mobileSettingsTrigger = page.getByRole("button", {
    name: "Guest settings",
  });
  await mobileSettingsTrigger.click();
  const mobileSettingsMenu = page.getByRole("menu", {
    name: "Guest settings",
  });
  await expect(mobileSettingsMenu).toBeVisible();
  const mobileMenuBox = await mobileSettingsMenu.boundingBox();
  const mobileViewportWidth = await page.evaluate(() => window.innerWidth);
  expect(mobileMenuBox?.x ?? -1).toBeGreaterThanOrEqual(0);
  expect(
    (mobileMenuBox?.x ?? 0) + (mobileMenuBox?.width ?? 0),
  ).toBeLessThanOrEqual(mobileViewportWidth);
  await mobileSettingsTrigger.click();

  // The in-app browser reserves a narrow browser rail inside a 390px device
  // frame, so the app surface must also remain clean at its 354px content width.
  await page.setViewportSize({ width: 354, height: 844 });
  await mobileSettingsTrigger.click();
  const narrowMobileMenuBox = await mobileSettingsMenu.boundingBox();
  const narrowMobileViewportWidth = await page.evaluate(
    () => window.innerWidth,
  );
  expect(narrowMobileMenuBox?.x ?? -1).toBeGreaterThanOrEqual(0);
  expect(
    (narrowMobileMenuBox?.x ?? 0) + (narrowMobileMenuBox?.width ?? 0),
  ).toBeLessThanOrEqual(narrowMobileViewportWidth);
  await mobileSettingsTrigger.click();
  await page.setViewportSize({ width: 390, height: 844 });

  expect(
    await composer.evaluate((element) =>
      Number.parseFloat(window.getComputedStyle(element).fontSize),
    ),
  ).toBeGreaterThanOrEqual(16);
  for (const locator of [
    page.getByRole("button", { name: "Guest settings" }),
    page.getByRole("button", { name: "Sign in" }),
  ]) {
    const box = await locator.boundingBox();
    expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
  }
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);

  await page.getByRole("button", { name: "Expand", exact: true }).click();
  await expect
    .poll(async () => (await page.locator("aside").boundingBox())?.width ?? 0)
    .toBeGreaterThanOrEqual(280);
  await expect(page.getByRole("button", { name: "New chat" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Search" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Recents" })).toBeVisible();
  await expect(page.locator("aside").getByText(/Temporary chat/)).toHaveCount(
    0,
  );
  await expect(page.getByTestId("guest-temporary-notice")).toHaveCount(1);
  await page.getByRole("button", { name: "Collapse", exact: true }).click();
  await expect(page.getByTestId("guest-temporary-notice")).toHaveCount(1);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("@guest-shell hints require typed artifacts and dismiss locally without writes", async ({
  page,
}) => {
  const evidence = await mockGuestJourney(page, {
    initiallyAuthenticated: true,
  });
  let durableHintWrites = 0;
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (
      request.method() !== "GET" &&
      (url.pathname.includes("/evidence-artifacts/") ||
        url.pathname.endsWith("/api/v1/me"))
    ) {
      durableHintWrites += 1;
    }
  });

  evidence.persistedMessages = [
    {
      id: "msg-confirmation",
      conversation_id: CONVERSATION_ID,
      role: "assistant",
      content: "",
      created_at: "2026-07-24T18:01:01Z",
      metadata: {
        confirmation_card: {
          confirmation_id: "confirmation-1",
          confirmation_state: "active",
          title: "AAPL buy and hold",
          status: "ready_to_run",
          statusLabel: "Ready to run",          rows: [
            { key: "strategy", label: "Strategy", value: "Buy and hold" },
            { key: "assets", label: "Assets", value: "AAPL" },
            { key: "period", label: "Period", value: "Last 12 months" },
          ],
          assumptions: ["Long only"],
          actions: [],
        },
      },
    },
  ];

  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("guest-confirmation-hint")).toContainText(
    "Review the assumptions",
  );
  await page
    .getByTestId("guest-confirmation-hint")
    .getByRole("button", { name: "Dismiss hint" })
    .click();
  await expect(page.getByTestId("guest-confirmation-hint")).toHaveCount(0);

  evidence.persistedMessages = [
    {
      id: "msg-result",
      conversation_id: CONVERSATION_ID,
      role: "assistant",
      content: "AAPL finished ahead of its starting value.",
      created_at: "2026-07-24T18:02:00Z",
      metadata: {
        result_run_id: "run-1",
        latest_run_id: "run-1",
        result_conversation_id: CONVERSATION_ID,
        result_card: {
          title: "AAPL buy and hold",
          symbols: ["AAPL"],
          strategy_label: "Buy and hold",
          asset_class: "equity",
          date_range: {
            start: "2025-07-24",
            end: "2026-07-24",
            display: "Jul 24, 2025 to Jul 24, 2026",
          },
          status_label: "Simulation Complete",
          rows: [
            { key: "ending_value", label: "Ending value", value: "$11,200" },
            { key: "total_return_pct", label: "Total return", value: "12.0%" },
          ],
          benchmark_note: "AAPL finished 1.2 points ahead of SPY.",
          assumptions: ["Long only"],
          actions: [],
          evidence_artifact_id: "evidence-1",
        },
      },
    },
  ];

  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("guest-confirmation-hint")).toHaveCount(0);
  await expect(page.getByTestId("guest-result-hint")).toContainText(
    "Change the chart range",
  );
  await page.getByRole("button", { name: "Add decision" }).click();
  const decisionDialog = page.getByRole("dialog", {
    name: "Request access to Cuadrao",
  });
  await expect(decisionDialog).toContainText(
    "Share your email to request access.",
  );
  await decisionDialog.getByRole("button", { name: "Cancel" }).click();
  await expect(decisionDialog).toHaveCount(0);
  expect(durableHintWrites).toBe(0);

  await page
    .getByTestId("guest-result-hint")
    .getByRole("button", { name: "Dismiss hint" })
    .click();
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("guest-result-hint")).toHaveCount(0);
  expect(durableHintWrites).toBe(0);
});
