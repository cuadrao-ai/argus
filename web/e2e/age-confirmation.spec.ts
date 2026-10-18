import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";

const checkboxCopy = "Confirmo que tengo 18 años o más.";
const cors = { "Access-Control-Allow-Origin": "http://127.0.0.1:3067", "Access-Control-Allow-Credentials": "true", "Access-Control-Allow-Headers": "*" };

test("first guest action and campaign bootstrap wait for confirmation, retained after reload", async ({ page }) => {
  const requests: { path: string; body: Record<string, unknown> }[] = [];
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === "OPTIONS") return route.fulfill({ status: 204, headers: cors });
    if (request.method() === "POST") requests.push({ path, body: request.postDataJSON() ?? {} });
    if (path.endsWith("/auth/guest")) return route.fulfill({ status: 200, headers: cors, json: { authenticated: true, reused: false, account_kind: "guest", user: { id: "age-guest" }, session: null } });
    return route.fulfill({ status: 401, headers: cors, json: { code: "unauthorized", detail: "fixture" } });
  });
  await page.goto("/?utm_campaign=age-gate-proof");
  const checkbox = page.getByRole("checkbox", { name: checkboxCopy });
  await expect(checkbox).toBeVisible();
  await expect(page.getByRole("combobox").first()).toBeDisabled();
  await page.waitForTimeout(300);
  expect(requests).toHaveLength(0);
  await mkdir("../docs/reports/evidence/age-confirmation", { recursive: true });
  await page.screenshot({ path: "../docs/reports/evidence/age-confirmation/guest-before.png", fullPage: true });
  await checkbox.check();
  await expect.poll(() => requests.filter(({ path }) => path.endsWith("/auth/guest")).length).toBe(1);
  const timestamp = await page.evaluate(() => localStorage.getItem("cuadrao-age-confirmed-at"));
  expect(timestamp).toBeTruthy();
  expect(requests[0].body.age_confirmed_at).toBe(timestamp);
  await page.reload();
  await expect(checkbox).toHaveCount(0);
  expect(await page.evaluate(() => localStorage.getItem("cuadrao-age-confirmed-at"))).toBe(timestamp);
  await page.screenshot({ path: "../docs/reports/evidence/age-confirmation/guest-after.png", fullPage: true });
  await page.goto("/?auth=signup");
  await expect(page.getByRole("checkbox", { name: checkboxCopy })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^(Sign up|Crear cuenta)$/ })).toBeEnabled();
  expect(await page.evaluate(() => localStorage.getItem("cuadrao-age-confirmed-at"))).toBe(timestamp);
});

test("signup requires confirmation and submits its exact instant", async ({ page }) => {
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
  await page.getByPlaceholder(/Email address|Correo electrónico/).fill("adult@example.com");
  await page.getByPlaceholder(/Password|Contraseña/, { exact: true }).fill("password123");
  await page.screenshot({ path: "../docs/reports/evidence/age-confirmation/signup-confirmed.png", fullPage: true });
  await submit.click();
  await expect.poll(() => signupBodies.length).toBe(1);
  expect(signupBodies[0].age_confirmed_at).toBe(await page.evaluate(() => localStorage.getItem("cuadrao-age-confirmed-at")));
  await expect(page.getByTestId("auth-check-email")).toBeVisible();
});


test("privacy renders the approved age confirmation disclosure", async ({ page }) => {
  await page.goto("/privacy");
  await expect(page.getByText(/We store when you confirmed you are 18 or older/)).toBeVisible();
  await page.screenshot({ path: "../docs/reports/evidence/age-confirmation/privacy.png", fullPage: true });
});
