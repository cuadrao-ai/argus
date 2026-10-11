import { expect, test, type Page } from "@playwright/test";
import { expectOneCanonicalCard } from "./auth-card-assertions";

const signupEmail = "confirmation-state@example.com";
const password = "correct-horse-battery-staple";

function corsHeaders(page: Page): Record<string, string> {
  return {
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Allow-Headers": "content-type",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Origin": new URL(page.url()).origin,
    Vary: "Origin",
  };
}

async function fillAndSubmitSignup(page: Page): Promise<void> {
  await page.goto("/?auth=signup");
  await page.locator('input[type="text"]').fill("Confirmation State");
  await page.locator('input[type="email"]').fill(signupEmail);
  await page.locator('input[type="password"]').fill(password);
  await page.getByRole("button", { name: "Sign up" }).click();
}

function testAccessToken(): string {
  const encode = (value: Record<string, unknown>) =>
    Buffer.from(JSON.stringify(value)).toString("base64url");
  return [
    encode({ alg: "none", typ: "JWT" }),
    encode({
      aud: "authenticated",
      email: signupEmail,
      exp: Math.floor(Date.now() / 1000) + 3600,
      role: "authenticated",
      sub: "user-confirmed",
    }),
    "test-signature",
  ].join(".");
}

test("sessionless signup focuses check-email state without navigating", async ({
  page,
}) => {
  await page.route("**/api/v1/auth/signup", async (route) => {
    if (route.request().method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: corsHeaders(page) });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      headers: corsHeaders(page),
      body: JSON.stringify({
        user: { id: "user-pending", email: signupEmail },
        session: null,
      }),
    });
  });

  await fillAndSubmitSignup(page);

  const state = page.getByTestId("auth-check-email");
  await expect(state).toBeVisible();
  await expect(state.getByRole("heading", { name: "Check your email" }))
    .toBeFocused();
  await expectOneCanonicalCard(state.locator("xpath=.."));
  await expect(page).not.toHaveURL(/\/chat(?:\?|$)/);
});

test("Spanish sessionless signup renders and focuses the localized check-email state", async ({
  page,
}) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("i18nextLng", "es-419");
  });
  await page.route("**/api/v1/auth/signup", async (route) => {
    if (route.request().method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: corsHeaders(page) });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      headers: corsHeaders(page),
      body: JSON.stringify({
        user: { id: "user-pending-es", email: signupEmail },
        session: null,
      }),
    });
  });

  await page.goto("/?auth=signup");
  await page.getByPlaceholder("Nombre").fill("Estado de confirmación");
  await page.getByPlaceholder("Correo electrónico").fill(signupEmail);
  await page.getByPlaceholder("Contraseña").fill(password);
  await page.getByRole("button", { name: "Registrarse" }).click();

  const state = page.getByTestId("auth-check-email");
  await expect(state).toBeVisible();
  await expect(state.getByRole("heading", { name: "Revisa tu correo" }))
    .toBeFocused();
  await expect(page).not.toHaveURL(/\/chat(?:\?|$)/);
});

test("session-bearing signup keeps the existing chat redirect", async ({
  page,
}) => {
  const accessToken = testAccessToken();
  await page.route("**/api/v1/auth/signup", async (route) => {
    if (route.request().method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: corsHeaders(page) });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      headers: corsHeaders(page),
      body: JSON.stringify({
        user: { id: "user-confirmed", email: signupEmail },
        session: {
          access_token: accessToken,
          refresh_token: "test-refresh-token",
          expires_in: 3600,
        },
      }),
    });
  });
  await page.route("**/auth/v1/user", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "user-confirmed",
        email: signupEmail,
        aud: "authenticated",
        role: "authenticated",
      }),
    });
  });

  const chatUrlPromise = page.waitForURL(/\/chat(?:\?|$)/, {
    waitUntil: "commit",
    timeout: 5_000,
  });
  await fillAndSubmitSignup(page);
  await chatUrlPromise;

  await expect(page.getByTestId("auth-check-email")).toHaveCount(0);
});
