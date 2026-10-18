import { mkdirSync } from "node:fs";
import { join } from "node:path";

import { expect, test, type Page } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { installBreakpointFixture } from "./support/breakpoint-fixture";

const shots = "/opt/cursor/artifacts/screenshots";
const title = "Cuadrao Business aún no está disponible para tu cuenta.";
const body = "Si crees que es un error, escríbenos a admin@cuadrao.ai.";

const businessOnly = process.env.NEXT_PUBLIC_BUSINESS_ONLY_WEB !== "false";
const pilot = process.env.NEXT_PUBLIC_BUSINESS_PILOT_ENABLED === "true";

async function signIn(page: Page): Promise<{ chat: string[]; biz: string[] }> {
  const chat: string[] = [];
  const biz: string[] = [];
  page.on("framenavigated", (frame) => {
    if (frame !== page.mainFrame()) return;
    const path = new URL(frame.url()).pathname;
    if (path === "/chat" || path.startsWith("/chat/")) chat.push(frame.url());
    if (path === "/biz" || path.startsWith("/biz/")) biz.push(frame.url());
  });
  await page.addInitScript(() => {
    window.localStorage.setItem("i18nextLng", "es-419");
  });
  await page.goto("/?auth=login");
  await page.getByPlaceholder("Correo electrónico").fill("owner@example.com");
  await page.getByPlaceholder("Contraseña").fill("correct-horse");
  await page.getByRole("button", { name: "Iniciar sesión", exact: true }).click();
  return { chat, biz };
}

async function installBusinessShell(page: Page) {
  await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
  const source = createFixtureBusinessDataSource({ chatAvailable: false });
  await page.route("**/api/v1/business/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.split("/business/")[1] ?? "";
    if (path === "workspace") return route.fulfill({ json: await source.workspace() });
    if (path === "space") return route.fulfill({ json: { id: "fixture-space", name: "Colmado de prueba" } });
    if (path === "spaces") return route.fulfill({ json: { spaces: (await source.spaces()).slice(0, 1) } });
    if (path === "overview") {
      return route.fulfill({
        json: { ...await source.overview("2026-10-01", "2026-10-31"), totals: [], fiscal_totals: [], without_fiscal_totals: [] },
      });
    }
    if (path === "receipts") {
      return route.fulfill({
        json: {
          items: [],
          activity: {
            reading_count: 0,
            unread_count: 0,
            presentation: "none",
            pending_review_count: 0,
            needs_attention_count: 0,
          },
        },
      });
    }
    if (path === "receipt-reading") return route.fulfill({ json: { enabled: true, available: true, can_change: false } });
    if (path === "email") return route.fulfill({ json: { enabled: true, receiving_address: "recibos@example.test" } });
    if (path === "email/deliveries" || path === "captures" || path === "updates") {
      return route.fulfill({ json: { items: [] } });
    }
    return route.fulfill({ status: 404, json: { code: "fixture_only" } });
  });
}

test.describe("signed-in home with business-only on", () => {
  test.skip(!businessOnly, "business-only is off for this run");

  test("pilot off shows Iris's closed copy, one sign-out, then business sign-in", async ({
    page,
  }) => {
    test.skip(pilot, "pilot is on for this run");
    await page.route("**/api/v1/auth/logout", async (route) => {
      await route.fulfill({
        status: route.request().method() === "OPTIONS" ? 204 : 200,
        contentType: "application/json",
        body: route.request().method() === "OPTIONS" ? "" : JSON.stringify({ success: true }),
      });
    });
    const visits = await signIn(page);
    const notice = page.getByTestId("business-home-closed");
    await expect(notice.getByRole("heading", { name: title })).toBeVisible();
    await expect(notice.getByRole("paragraph")).toHaveText(body);
    await expect(notice.getByRole("link", { name: "admin@cuadrao.ai" })).toHaveAttribute(
      "href",
      "mailto:admin@cuadrao.ai",
    );
    await expect(notice.getByRole("button")).toHaveCount(1);
    await expect(notice.getByRole("button", { name: "Cerrar sesión" })).toBeVisible();
    await expect(page).toHaveURL(/\/\?auth=login(?:&|$)/);
    expect(visits.chat).toEqual([]);
    expect(visits.biz).toEqual([]);

    mkdirSync(shots, { recursive: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(notice.getByRole("heading", { name: title })).toBeVisible();
    await page.screenshot({
      path: join(shots, "business-home-closed-390.png"),
      fullPage: true,
    });
    await page.setViewportSize({ width: 1280, height: 800 });
    await expect(notice.getByRole("heading", { name: title })).toBeVisible();
    await page.screenshot({
      path: join(shots, "business-home-closed-1280.png"),
      fullPage: true,
    });

    await notice.getByRole("button", { name: "Cerrar sesión" }).click();
    await expect(page.getByRole("button", { name: "Iniciar sesión", exact: true })).toBeVisible();
    await expect(notice).toHaveCount(0);
    await expect(page).toHaveURL(/\/\?auth=login(?:&|$)/);
    expect(visits.chat).toEqual([]);
    expect(visits.biz).toEqual([]);
  });

  test("pilot on lands on the business workspace", async ({ page }) => {
    test.skip(!pilot, "pilot is off for this run");
    await installBusinessShell(page);
    const biz = page.waitForResponse(
      (response) => new URL(response.url()).pathname === "/biz",
    );
    const visits = await signIn(page);
    const response = await biz;
    const location = response.headers()["location"] ?? "";
    expect(
      response.status(),
      `biz response ${response.status()} location=${location} url=${response.url()}`,
    ).toBe(200);
    await expect(page).toHaveURL(/\/biz(?:\?|$)/);
    await expect(page.getByTestId("overview-real-expenses")).toBeVisible();
    expect(visits.chat).toEqual([]);
    expect(visits.biz.length).toBeGreaterThan(0);
    mkdirSync(shots, { recursive: true });
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.screenshot({
      path: join(shots, "business-home-biz-1280.png"),
      fullPage: true,
    });
  });
});
