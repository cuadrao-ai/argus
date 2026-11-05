import {
  expect,
  test,
  type Page,
  type Route,
} from "@playwright/test";
import { expectOneCanonicalCard } from "./auth-card-assertions";

const GUEST_ID = "00000000-0000-4000-8000-000000000501";
const CONVERSATION_ID = "00000000-0000-4000-8000-000000000502";
const REGISTERED_ID = "00000000-0000-4000-8000-000000000503";
const EXPIRES_AT = "2026-08-07T18:00:00Z";
const APPROVED_EMAIL = "approved-guest@example.com";
const PASSWORD = "correct-horse-battery-staple";

type MockGuestJourneyState = {
  registered: boolean;
};

function corsHeaders(page: Page): Record<string, string> {
  return {
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Allow-Headers": "authorization, content-type",
    "Access-Control-Allow-Methods": "GET, PATCH, POST, OPTIONS",
    "Access-Control-Allow-Origin": new URL(page.url()).origin,
    Vary: "Origin",
  };
}

async function fulfillJson(
  route: Route,
  page: Page,
  body: unknown,
  status = 200,
): Promise<void> {
  if (route.request().method() === "OPTIONS") {
    await route.fulfill({ status: 204, headers: corsHeaders(page) });
    return;
  }
  await route.fulfill({
    status,
    contentType: "application/json",
    headers: corsHeaders(page),
    body: JSON.stringify(body),
  });
}

function guestMe(
  publicAccountAccessEnabled = false,
  language: "en" | "es-419" = "en",
) {
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
      can_use_grounded_discovery: true,
      can_submit_feedback: true,
    },
    public_account_access_enabled: publicAccountAccessEnabled,
  };
}

function registeredMe(
  publicAccountAccessEnabled = false,
  language: "en" | "es-419" = "en",
) {
  return {
    user: {
      ...guestMe(publicAccountAccessEnabled, language).user,
      id: REGISTERED_ID,
      email: APPROVED_EMAIL,
      onboarding: {
        completed: true,
        stage: "complete",
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
    public_account_access_enabled: publicAccountAccessEnabled,
  };
}

function testAccessToken(
  email: string | null,
  isAnonymous: boolean,
  subject = GUEST_ID,
): string {
  const encode = (value: Record<string, unknown>) =>
    Buffer.from(JSON.stringify(value)).toString("base64url");
  return [
    encode({ alg: "none", typ: "JWT" }),
    encode({
      aud: "authenticated",
      email,
      exp: Math.floor(Date.now() / 1000) + 3600,
      is_anonymous: isAnonymous,
      role: "authenticated",
      sub: subject,
    }),
    "test-signature",
  ].join(".");
}

async function installGuestSession(page: Page): Promise<void> {
  const expiresAt = Math.floor(Date.now() / 1000) + 3600;
  const session = {
    access_token: testAccessToken(null, true),
    refresh_token: "guest-refresh-token",
    expires_in: 3600,
    expires_at: expiresAt,
    token_type: "bearer",
    user: {
      id: GUEST_ID,
      email: null,
      aud: "authenticated",
      role: "authenticated",
      is_anonymous: true,
      app_metadata: {
        provider: "anonymous",
        providers: ["anonymous"],
      },
      user_metadata: {},
      identities: [],
      created_at: "2026-07-31T18:00:00Z",
      updated_at: "2026-07-31T18:00:00Z",
    },
  };
  const cookieValue = `base64-${Buffer.from(JSON.stringify(session)).toString(
    "base64url",
  )}`;
  await page.addInitScript(
    ({ value }) => {
      document.cookie = `sb-test-project-auth-token=${value}; Path=/; SameSite=Lax`;
    },
    { value: cookieValue },
  );
}

async function mockGuestJourney(
  page: Page,
  publicAccountAccessEnabled = false,
  language: "en" | "es-419" = "en",
  conversationHasContent = false,
): Promise<MockGuestJourneyState> {
  const state = { registered: false };
  await page.route("**/api/v1/auth/guest", (route) =>
    fulfillJson(route, page, {
      authenticated: true,
      reused: false,
      renewed_after_expiry: false,
      public_account_access_enabled: publicAccountAccessEnabled,
      account_kind: "guest",
      user: guestMe(publicAccountAccessEnabled, language).user,
    }),
  );
  await page.route("**/api/v1/me", (route) =>
    fulfillJson(
      route,
      page,
      state.registered
        ? registeredMe(publicAccountAccessEnabled, language)
        : guestMe(publicAccountAccessEnabled, language),
    ),
  );
  await page.route("**/api/v1/me/usage", (route) =>
    fulfillJson(route, page, {
      allowances: {
        compute: { available_now: true, limiting_window: null },
        grounding: { available_now: true },
        execution: { available_now: true },
      },
    }),
  );
  await page.route("**/api/v1/history**", (route) =>
    fulfillJson(route, page, { items: [], next_cursor: null }),
  );
  await page.route("**/api/v1/conversations**", (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname.endsWith("/messages")) {
      return fulfillJson(route, page, {
        items: conversationHasContent
          ? [
              {
                id: "00000000-0000-4000-8000-000000000505",
                conversation_id: CONVERSATION_ID,
                role: "user",
                content: "Preserve this guest idea",
                created_at: "2026-07-31T18:00:00Z",
                metadata: {},
              },
            ]
          : [],
        next_cursor: null,
      });
    }
    return fulfillJson(route, page, {
      items: [
        {
          id: CONVERSATION_ID,
          title: "Temporary idea",
          title_source: "system_default",
          pinned: false,
          archived: false,
          created_at: "2026-07-31T18:00:00Z",
          updated_at: "2026-07-31T18:00:00Z",
          language: "en",
        },
      ],
      next_cursor: null,
    });
  });
  return state;
}

async function mockApprovedGuestSignup(
  page: Page,
  state: MockGuestJourneyState,
  bodies: Array<Record<string, unknown>>,
  authorizationHeaders: string[],
): Promise<void> {
  const accessToken = testAccessToken(APPROVED_EMAIL, false, REGISTERED_ID);
  let pendingAction: Record<string, unknown> | null = null;
  await page.route("**/api/v1/auth/guest/handoffs", async (route) => {
    if (route.request().method() !== "OPTIONS") {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      bodies.push(body);
      pendingAction =
        typeof body.pending_action === "object" && body.pending_action !== null
          ? (body.pending_action as Record<string, unknown>)
          : null;
      authorizationHeaders.push(
        route.request().headers().authorization ?? "",
      );
      await fulfillJson(
        route,
        page,
        {
          handoff_id: "00000000-0000-4000-8000-000000000504",
          expires_at: EXPIRES_AT,
        },
        201,
      );
      return;
    }
    await fulfillJson(route, page, {}, 204);
  });
  await page.route("**/api/v1/auth/guest/signup", async (route) => {
    if (route.request().method() !== "OPTIONS") {
      bodies.push(route.request().postDataJSON() as Record<string, unknown>);
      authorizationHeaders.push(
        route.request().headers().authorization ?? "",
      );
      state.registered = true;
      await fulfillJson(
        route,
        page,
        {
          authenticated: true,
          account_kind: "registered",
          user: { id: REGISTERED_ID, email: APPROVED_EMAIL },
          session: {
            access_token: accessToken,
            refresh_token: "registered-refresh-token",
            expires_in: 3600,
          },
          guest_claim: {
            conversation_id: CONVERSATION_ID,
            pending_action: pendingAction,
          },
        },
        200,
      );
      return;
    }
    await fulfillJson(route, page, {}, 204);
  });
  await page.route("**/auth/v1/user", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: REGISTERED_ID,
        email: APPROVED_EMAIL,
        aud: "authenticated",
        role: "authenticated",
        is_anonymous: false,
        app_metadata: { provider: "email", providers: ["email"] },
        user_metadata: {},
        identities: [],
        created_at: "2026-07-31T18:00:00Z",
        updated_at: "2026-07-31T18:00:00Z",
      }),
    }),
  );
}

async function mockAcceptedAccessRequest(
  page: Page,
  bodies?: Array<Record<string, unknown>>,
): Promise<void> {
  await page.route("**/api/v1/auth/access-requests", async (route) => {
    if (route.request().method() !== "OPTIONS") {
      bodies?.push(route.request().postDataJSON() as Record<string, unknown>);
    }
    await fulfillJson(route, page, { accepted: true }, 202);
  });
}

test("gated landing opens request access by default", async ({ page }) => {
  await page.goto("/");

  const requestButton = page.getByRole("button", {
    name: "Request access",
    exact: true,
  });
  await expect(requestButton).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  await requestButton.click();

  await expect(page).toHaveURL(/\?auth=request$/);
  await expect(
    page.getByRole("heading", { name: "Request access to Cuadrao" }),
  ).toBeVisible();
});

test("landing request route submits a generic request and focuses acceptance", async ({
  page,
}) => {
  const bodies: Array<Record<string, unknown>> = [];
  await mockAcceptedAccessRequest(page, bodies);
  await page.goto("/?auth=request");

  const email = page.getByRole("textbox", { name: "Email address" });
  await expect(
    page.getByRole("heading", { name: "Request access to Cuadrao" }),
  ).toBeVisible();
  await expect(page.getByText(/If approved, we’ll email you/)).toBeVisible();
  await expect(email).toBeFocused();
  await email.fill("person@example.com");
  await page.getByRole("button", { name: "Request access" }).click();

  const acceptedHeading = page.getByRole("heading", {
    name: "Request received",
  });
  await expect(acceptedHeading).toBeFocused();
  await expectOneCanonicalCard(acceptedHeading.locator("xpath=../.."));
  await expect(page.getByText(/If access is approved/)).toBeVisible();
  expect(bodies).toEqual([
    { email: "person@example.com", language: "en" },
  ]);
});

test("approval signup and existing login remain separate landing modes", async ({
  page,
}) => {
  await page.goto("/?auth=request");
  await page.getByRole("button", { name: "Sign up" }).click();

  await expect(page).toHaveURL(/\?auth=signup$/);
  await expect(page.getByPlaceholder("Name")).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign up" })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Request access to Cuadrao" }),
  ).toHaveCount(0);

  await page.goto("/?auth=request");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\?auth=login$/);
  await expect(page.getByRole("button", { name: "Sign In" })).toBeVisible();
});

test("request failure stays generic and retry-safe", async ({ page }) => {
  await page.route("**/api/v1/auth/access-requests", (route) =>
    fulfillJson(
      route,
      page,
      {
        status: 503,
        code: "access_request_unavailable",
        detail: "This email is already approved on the allowlist.",
      },
      503,
    ),
  );
  await page.goto("/?auth=request");
  await page.getByRole("textbox", { name: "Email address" }).fill(
    "person@example.com",
  );
  await page.getByRole("button", { name: "Request access" }).click();

  await expect(page.locator("p[role='alert']")).toHaveText(
    "We couldn’t send your request. Please try again.",
  );
  await expect(
    page.getByText("This email is already approved on the allowlist."),
  ).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Request access" }))
    .toBeEnabled();
});

test("request state is localized in Latin American Spanish", async ({
  page,
}) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("i18nextLng", "es-419");
  });
  const bodies: Array<Record<string, unknown>> = [];
  await mockAcceptedAccessRequest(page, bodies);
  await page.goto("/?auth=request");

  await expect(
    page.getByRole("heading", { name: "Solicita acceso a Cuadrao" }),
  ).toBeVisible();
  await expect(page.getByText(/Si se aprueba, te enviaremos/)).toBeVisible();
  await page.getByRole("textbox", { name: "Correo electrónico" }).fill(
    "persona@example.com",
  );
  await page.getByRole("button", { name: "Solicitar acceso" }).click();
  await expect(
    page.getByRole("heading", { name: "Solicitud recibida" }),
  ).toBeFocused();
  expect(bodies).toEqual([
    { email: "persona@example.com", language: "es-419" },
  ]);
});

test("gated guest conversion wraps the mounted conversation and restores focus", async ({
  page,
}) => {
  await mockGuestJourney(page);
  await mockAcceptedAccessRequest(page);
  await page.goto("/chat");
  const opener = page.getByRole("button", { name: "Sign in" });
  const chatInput = page.getByTestId("chat-input");
  await expect(page).toHaveURL(/\/chat(?:\?|$)/, { timeout: 10_000 });
  await expect(chatInput).toBeVisible({ timeout: 60_000 });

  await opener.click();
  let dialog = page.getByRole("dialog", {
    name: "Request access to Cuadrao",
  });
  await expect(dialog).toBeVisible();
  await expect(chatInput).toHaveCount(1);
  await dialog.getByRole("button", { name: "Sign up" }).click();
  dialog = page.getByRole("dialog", { name: "Create your account" });
  await expect(dialog.getByPlaceholder("Name")).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(opener).toBeFocused();

  await opener.click();
  dialog = page.getByRole("dialog", {
    name: "Request access to Cuadrao",
  });
  await dialog.getByRole("button", { name: "Sign in" }).click();
  dialog = page.getByRole("dialog", { name: "Sign in" });
  await expect(dialog.getByRole("button", { name: "Sign In" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(opener).toBeFocused();

  await opener.click();
  dialog = page.getByRole("dialog", {
    name: "Request access to Cuadrao",
  });
  await dialog.getByRole("textbox", { name: "Email address" }).fill(
    "guest@example.com",
  );
  await dialog.getByRole("button", { name: "Request access" }).click();
  dialog = page.getByRole("dialog", { name: "Request received" });
  await expect(
    dialog.getByRole("heading", { name: "Request received" }),
  ).toBeFocused();
  await expectOneCanonicalCard(dialog);
  await expect(chatInput).toHaveCount(1);
});

test("Spanish guest conversion submits the localized access request", async ({
  page,
}) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("i18nextLng", "es-419");
  });
  const bodies: Array<Record<string, unknown>> = [];
  await mockGuestJourney(page, false, "es-419");
  await mockAcceptedAccessRequest(page, bodies);
  await page.goto("/chat");
  const chatInput = page.getByTestId("chat-input");
  await expect(chatInput).toBeVisible({ timeout: 60_000 });

  await page.getByRole("button", { name: "Iniciar sesión" }).click();
  let dialog = page.getByRole("dialog", {
    name: "Solicita acceso a Cuadrao",
  });
  await expect(dialog.getByText(/Si se aprueba, te enviaremos/)).toBeVisible();
  await dialog.getByRole("textbox", { name: "Correo electrónico" }).fill(
    "invitada@example.com",
  );
  await dialog.getByRole("button", { name: "Solicitar acceso" }).click();
  dialog = page.getByRole("dialog", { name: "Solicitud recibida" });
  await expect(
    dialog.getByRole("heading", { name: "Solicitud recibida" }),
  ).toBeFocused();
  await expect(chatInput).toHaveCount(1);
  expect(bodies).toEqual([
    { email: "invitada@example.com", language: "es-419" },
  ]);
});

test("enabled guest account access preserves the direct auth flow", async ({
  page,
}) => {
  await mockGuestJourney(page, true);
  await page.goto("/chat");
  await expect(page).toHaveURL(/\/chat(?:\?|$)/, { timeout: 10_000 });
  await expect(page.getByTestId("chat-input")).toBeVisible({
    timeout: 60_000,
  });

  await page.getByRole("button", { name: "Sign in" }).click();
  let dialog = page.getByRole("dialog", { name: "Sign in" });
  await expect(dialog).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Request access to Cuadrao" }),
  ).toHaveCount(0);

  await dialog.getByRole("button", { name: "Sign up" }).click();
  dialog = page.getByRole("dialog", { name: "Create your account" });
  await expect(dialog.getByPlaceholder("Name")).toBeVisible();
});

test("approved guest creates a distinct identity while public signup is gated", async ({
  page,
}) => {
  const bodies: Array<Record<string, unknown>> = [];
  const authorizationHeaders: string[] = [];
  const state = await mockGuestJourney(page, false, "en", true);
  await mockApprovedGuestSignup(
    page,
    state,
    bodies,
    authorizationHeaders,
  );
  await installGuestSession(page);
  await page.goto("/chat");
  await expect(page.getByTestId("chat-input")).toBeVisible({
    timeout: 60_000,
  });
  await expect(page).toHaveURL(new RegExp(`conversation=${CONVERSATION_ID}`));
  await expect(page.getByText("Preserve this guest idea")).toBeVisible();

  await page.getByRole("button", { name: "Sign in" }).click();
  let dialog = page.getByRole("dialog", {
    name: "Request access to Cuadrao",
  });
  await dialog.getByRole("button", { name: "Sign up" }).click();
  dialog = page.getByRole("dialog", { name: "Create your account" });
  await dialog.getByPlaceholder("Email address").fill(APPROVED_EMAIL);
  await dialog.getByPlaceholder("Password").fill(PASSWORD);
  await dialog.getByRole("button", { name: "Sign up" }).click();

  await expect.poll(() => bodies.length).toBe(2);
  await expect.poll(() => state.registered).toBe(true);

  await expect(dialog).toHaveCount(0);
  await expect(page.getByTestId("chat-input")).toHaveCount(1);
  expect(bodies).toHaveLength(2);
  expect(bodies[0]).toMatchObject({
    handoff_kind: "new_account_signup",
    destination_email: APPROVED_EMAIL,
    source_conversation_id: CONVERSATION_ID,
  });
  expect(bodies[1]).toEqual({
    email: APPROVED_EMAIL,
    password: PASSWORD,
    captcha_token: "argus-local-browser-qa",
    language: "en",
    display_name: null,
  });
  expect(authorizationHeaders).toEqual(["", ""]);
});
