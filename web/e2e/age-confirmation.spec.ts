import { expect, test, type Route } from "@playwright/test";

const disclosure = "When you create your account, we save with it when you confirmed you're 18 or older. We don't store your date of birth.";

function cors(route: Route) {
  return {
    "Access-Control-Allow-Origin": route.request().headers().origin ?? "*",
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Allow-Headers": "*",
  };
}

test("signup has no age checkbox and posts without an age confirmation", async ({ page }) => {
  const signupBodies: Record<string, unknown>[] = [];
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    if (request.method() === "OPTIONS") return route.fulfill({ status: 204, headers: cors(route) });
    if (request.url().endsWith("/auth/signup")) {
      signupBodies.push(request.postDataJSON());
      return route.fulfill({ status: 200, headers: cors(route), json: { user: { id: "age-user" }, session: null } });
    }
    return route.fulfill({ status: 401, headers: cors(route), json: { code: "unauthorized" } });
  });
  await page.goto("/?auth=signup");
  const submit = page.getByRole("button", { name: /^(Sign up|Registrarse)$/ });
  await expect(submit).toBeEnabled();
  await expect(page.getByRole("checkbox")).toHaveCount(0);
  await page.getByPlaceholder(/Email address|Correo electrónico/).fill("adult@example.com");
  await page.getByPlaceholder(/Password|Contraseña/, { exact: true }).fill("password123");
  await submit.click();
  await expect.poll(() => signupBodies.length).toBe(1);
  expect(signupBodies[0]).not.toHaveProperty("age_confirmed_at");
  await expect(page.getByTestId("auth-check-email")).toBeVisible();
});

test("privacy keeps the age confirmation disclosure", async ({ page }) => {
  await page.goto("/privacy");
  await expect(page.getByText(disclosure)).toBeVisible();
});
