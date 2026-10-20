import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";

const checkboxCopy = /^(I confirm I'm 18 or older\.|Confirmo que tengo 18 años o más\.)$/;
const cors = { "Access-Control-Allow-Origin": "http://127.0.0.1:3067", "Access-Control-Allow-Credentials": "true", "Access-Control-Allow-Headers": "*" };
const disclosure = "When you create your account, we save with it when you confirmed you're 18 or older. We don't store your date of birth.";

test("signup requires confirmation and submits its exact instant without storing it", async ({ page }) => {
  const signupBodies: Record<string, unknown>[] = [];
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    if (request.method() === "OPTIONS") return route.fulfill({ status: 204, headers: cors });
    if (request.url().endsWith("/auth/signup")) {
      signupBodies.push(request.postDataJSON());
      return route.fulfill({ status: 200, headers: cors, json: { user: { id: "age-user" }, session: null } });
    }
    return route.fulfill({ status: 401, headers: cors, json: { code: "unauthorized" } });
  });
  await page.goto("/?auth=signup");
  const checkbox = page.getByRole("checkbox", { name: checkboxCopy });
  await expect(checkbox).toBeVisible();
  const submit = page.getByRole("button", { name: /^(Sign up|Crear cuenta)$/ });
  await expect(submit).toBeDisabled();
  await checkbox.check();
  await expect(submit).toBeEnabled();
  expect(await page.evaluate(() => localStorage.getItem("cuadrao-age-confirmed-at"))).toBeNull();
  await page.getByPlaceholder(/Email address|Correo electrónico/).fill("adult@example.com");
  await page.getByPlaceholder(/Password|Contraseña/, { exact: true }).fill("password123");
  await mkdir("../docs/reports/evidence/age-confirmation", { recursive: true });
  await page.screenshot({ path: "../docs/reports/evidence/age-confirmation/signup-confirmed.png", fullPage: true });
  await submit.click();
  await expect.poll(() => signupBodies.length).toBe(1);
  expect(signupBodies[0].age_confirmed_at).toEqual(expect.any(String));
  expect(String(signupBodies[0].age_confirmed_at)).toMatch(/^\d{4}-\d{2}-\d{2}T/);
  expect(await page.evaluate(() => localStorage.getItem("cuadrao-age-confirmed-at"))).toBeNull();
  await expect(page.getByTestId("auth-check-email")).toBeVisible();
});

test("privacy renders the approved age confirmation disclosure", async ({ page }) => {
  await page.goto("/privacy");
  await expect(page.getByText(disclosure)).toBeVisible();
  await expect(page.getByText("We store when you confirmed you are 18 or older")).toHaveCount(0);
  await page.screenshot({ path: "../docs/reports/evidence/age-confirmation/privacy.png", fullPage: true });
});
