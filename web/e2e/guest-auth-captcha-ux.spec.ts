import { expect, test } from "@playwright/test";

import en from "../public/locales/en/common.json";
import es from "../public/locales/es-419/common.json";

const SCREENSHOT_DIR =
  "../docs/release-evidence/screenshots/issue-321";
const BROWSER_CHECK_DIR =
  "../docs/reports/evidence/business-signin-browser-check";

type FakeTurnstileMode = "visible" | "stuck";

declare global {
  interface Window {
    completeCaptchaForTest?: () => void;
    escapeReachedBackground?: number;
    rejectCaptchaForTest?: () => void;
  }
}

async function prepareCaptcha(
  page: import("@playwright/test").Page,
  language: "en" | "es-419",
  mode: FakeTurnstileMode,
) {
  await page.addInitScript(
    ({ language: selectedLanguage, mode: selectedMode }) => {
      window.localStorage.setItem("i18nextLng", selectedLanguage);
      window.localStorage.setItem("argus-theme", "dark");
      window.escapeReachedBackground = 0;
      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
          window.escapeReachedBackground =
            (window.escapeReachedBackground ?? 0) + 1;
        }
      });
      Object.defineProperty(window, "turnstile", {
        configurable: true,
        value: {
          render(
            container: HTMLElement,
            options: {
              theme?: "auto" | "light" | "dark";
              "before-interactive-callback"?: () => void;
              callback?: (token: string) => void;
              "error-callback"?: () => boolean;
            },
          ) {
            document.documentElement.dataset.renderedTurnstileTheme =
              options.theme;
            window.completeCaptchaForTest = () => {
              options.callback?.("test-captcha-token");
            };
            window.rejectCaptchaForTest = () => {
              options["error-callback"]?.();
            };
            if (selectedMode === "visible") {
              const frame = document.createElement("iframe");
              frame.title = "Turnstile test challenge";
              frame.style.width = "300px";
              frame.style.height = "65px";
              frame.style.border = "0";
              frame.srcdoc =
                options.theme === "dark"
                  ? "<!doctype html><html><body style='margin:0;background:#222;color:#f5f5f5;font:15px system-ui;display:flex;align-items:center;height:65px'><div style='width:22px;height:22px;border:2px solid #aaa;margin:0 12px 0 16px'></div><strong>Verify you are human</strong></body></html>"
                  : "<!doctype html><html><body style='margin:0;background:#fff;color:#171717;font:15px system-ui;display:flex;align-items:center;height:65px'><div style='width:22px;height:22px;border:2px solid #666;margin:0 12px 0 16px'></div><strong>Verify you are human</strong></body></html>";
              container.appendChild(frame);
              options["before-interactive-callback"]?.();
            }
            return "issue-321-test-widget";
          },
          remove() {},
        },
      });
    },
    { language, mode },
  );
}

async function submitLogin(page: import("@playwright/test").Page) {
  await page.goto("/?auth=login");
  await page.locator('input[type="email"]').fill("captcha-probe@example.com");
  await page.locator('input[type="password"]').fill("not-a-real-password");
  await page.locator('button[type="submit"]').click();
}

for (const fixture of [
  {
    language: "en" as const,
    label: "Verifying you’re not a bot…",
    screenshot: "forced-visible-challenge-en.png",
  },
  {
    language: "es-419" as const,
    label: "Verificando que no eres un bot…",
    screenshot: "forced-visible-challenge-es-419.png",
  },
]) {
  test(`forced interactive challenge has a ${fixture.language} visual shell`, async ({
    page,
  }) => {
    await prepareCaptcha(page, fixture.language, "visible");
    if (fixture.language === "en") {
      await page.route("**/api/v1/auth/login", async (route) => {
        await new Promise((resolve) => setTimeout(resolve, 5_500));
        await route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({ code: "internal_error" }),
        });
      });
    }
    await submitLogin(page);

    const shell = page.getByTestId("turnstile-challenge-shell");
    await expect(shell).toBeVisible();
    await expect(shell).toHaveAttribute("role", "dialog");
    await expect(shell.getByRole("heading", { name: fixture.label })).toBeVisible();
    await expect(shell.getByTitle("Turnstile test challenge")).toBeVisible();
    await expect(shell).toBeFocused();
    await expect(page.locator("html")).toHaveAttribute(
      "data-rendered-turnstile-theme",
      "dark",
    );

    await page.locator('input[type="email"]').evaluate((input) => {
      (input as HTMLInputElement).focus();
    });
    await expect(shell).toBeFocused();

    await page.keyboard.press("Escape");
    await expect(shell).toBeVisible();
    await expect
      .poll(() => page.evaluate(() => window.escapeReachedBackground ?? -1))
      .toBe(0);

    await page.waitForTimeout(250);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/${fixture.screenshot}`,
      fullPage: true,
    });

    await page.evaluate((complete) => {
      if (complete) window.completeCaptchaForTest?.();
      else window.rejectCaptchaForTest?.();
    }, fixture.language === "en");
    await expect(shell).toHaveCount(0);
    await expect(
      page.getByRole("button", {
        name: /Sign in|Iniciar sesión|Try again|Intentar de nuevo/,
      }),
    ).toBeFocused({ timeout: 8_000 });
  });
}

test("a stuck shared CAPTCHA times out and leaves login ready", async ({
  page,
}) => {
  test.setTimeout(25_000);
  await prepareCaptcha(page, "en", "stuck");
  await submitLogin(page);

  await expect(page.getByTestId("auth-submit-spinner")).toBeVisible();
  await page.screenshot({
    path: `${BROWSER_CHECK_DIR}/spinner-while-browser-check.png`,
    fullPage: true,
  });
  await expect(
    page.getByText(en.auth.errors.browser_check_failed),
  ).toBeVisible({ timeout: 18_000 });
  await page.screenshot({
    path: `${BROWSER_CHECK_DIR}/browser-check-retry-en.png`,
    fullPage: true,
  });
  await expect(page.getByPlaceholder("Email address")).toHaveValue(
    "captcha-probe@example.com",
  );
  await expect(page.getByPlaceholder("Password")).toHaveValue(
    "not-a-real-password",
  );
  await expect(
    page.getByRole("button", { name: en.auth.errors.browser_check_retry, exact: true }),
  ).toBeEnabled();
  await expect(page.getByTestId("turnstile-challenge-shell")).toHaveCount(0);
});

test("a stuck shared CAPTCHA shows the Spanish retry", async ({ page }) => {
  test.setTimeout(25_000);
  await prepareCaptcha(page, "es-419", "stuck");
  await submitLogin(page);

  await expect(page.getByText(es.auth.errors.browser_check_failed)).toBeVisible({
    timeout: 18_000,
  });
  await expect(
    page.getByRole("button", {
      name: es.auth.errors.browser_check_retry,
      exact: true,
    }),
  ).toBeEnabled();
  await page.screenshot({
    path: `${BROWSER_CHECK_DIR}/browser-check-retry-es-419.png`,
    fullPage: true,
  });
});
