import { mkdirSync } from "node:fs";
import { join } from "node:path";

import { expect, test, type Page } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { installBreakpointFixture } from "./support/breakpoint-fixture";

function screenshotDir(): string {
  const configured = process.env.E2E_SCREENSHOT_DIR?.trim();
  const directory = configured ? configured : "test-results";
  const folded = directory.replaceAll("\\", "/");
  const forbidden =
    folded === "/opt/cursor/artifacts" ||
    folded.startsWith("/opt/cursor/artifacts/") ||
    folded === "docs/reports/evidence" ||
    folded.startsWith("docs/reports/evidence/") ||
    folded.includes("/docs/reports/evidence/") ||
    folded.endsWith("/docs/reports/evidence");
  if (forbidden) throw new Error("screenshot directory is not a test output path");
  return directory;
}

const shots = screenshotDir();
const title = "Cuadrao Business aún no está disponible para tu cuenta.";
const body = "Si crees que es un error, escríbenos a admin@cuadrao.ai.";
const logoutError = "No pudimos cerrar la sesión en este navegador. Inténtalo de nuevo.";

function channel(value: number): number {
  const unit = value / 255;
  return unit <= 0.04045 ? unit / 12.92 : ((unit + 0.055) / 1.055) ** 2.4;
}

function contrastRatio(foreground: string, background: string): number {
  const parse = (color: string) => {
    const match = color.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
    if (!match) throw new Error(`unreadable color ${color}`);
    return match.slice(1, 4).map((part) => channel(Number(part)));
  };
  const [first, second] = [foreground, background].map((color) => {
    const [red, green, blue] = parse(color);
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
  });
  const lighter = Math.max(first, second);
  const darker = Math.min(first, second);
  return (lighter + 0.05) / (darker + 0.05);
}

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
    const signOut = notice.getByRole("button", { name: "Cerrar sesión" });
    const colors = await signOut.evaluate((node) => {
      const style = getComputedStyle(node);
      return { color: style.color, backgroundColor: style.backgroundColor, fontSize: style.fontSize };
    });
    const ratio = contrastRatio(colors.color, colors.backgroundColor);
    console.log(`closed-home sign-out contrast ${ratio.toFixed(3)} ${colors.color} on ${colors.backgroundColor} at ${colors.fontSize}`);
    expect(ratio, `${colors.color} on ${colors.backgroundColor}`).toBeGreaterThanOrEqual(4.5);
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

  test("a rejected sign-out stays on the closed home and shows the error once", async ({ page }) => {
    test.skip(pilot, "pilot is on for this run");
    let logoutPosts = 0;
    await page.route("**/api/v1/auth/logout", async (route) => {
      if (route.request().method() === "OPTIONS") {
        return route.fulfill({ status: 204, body: "" });
      }
      logoutPosts += 1;
      return route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ success: false }),
      });
    });
    await signIn(page);
    const notice = page.getByTestId("business-home-closed");
    const signOut = notice.getByRole("button", { name: "Cerrar sesión" });
    await signOut.click();
    await expect(notice).toBeVisible();
    await expect(page.getByRole("alert").filter({ hasText: logoutError })).toHaveText(logoutError);
    await expect(page.getByRole("button", { name: "Iniciar sesión", exact: true })).toHaveCount(0);
    expect(logoutPosts).toBe(1);
  });

  test("pilot off keeps /biz and the signed-in root off a 404 and off a loop", async ({ page }) => {
    test.skip(pilot, "pilot is on for this run");
    await page.route("**/api/v1/me", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ account_kind: "registered", id: "owner-1" }),
      });
    });
    await page.addInitScript(() => {
      window.localStorage.setItem("i18nextLng", "es-419");
    });
    const documents: string[] = [];
    page.on("response", (response) => {
      if (response.request().resourceType() !== "document") return;
      documents.push(`${response.status()} ${new URL(response.url()).pathname}`);
    });
    const root = await page.goto("/");
    expect(root?.status(), documents.join(" | ")).toBe(200);
    await expect(page.getByTestId("business-home-closed")).toBeVisible();
    await expect(page).toHaveURL(/\/\?auth=login(?:&|$)/);
    const followed = await page.goto("/biz");
    expect(followed?.status(), documents.join(" | ")).toBe(200);
    await expect(page.getByTestId("business-home-closed")).toBeVisible();
    await expect(page).toHaveURL(/\/\?auth=login(?:&|$)/);
    await expect(page).not.toHaveURL(/\/chat(?:\?|$)/);
    await expect(page).not.toHaveURL(/\/biz(?:\?|$)/);
    expect(documents.filter((entry) => entry.startsWith("404"))).toEqual([]);
    expect(documents.filter((entry) => entry.includes("/chat"))).toEqual([]);
    expect(documents.length).toBeLessThan(8);
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
